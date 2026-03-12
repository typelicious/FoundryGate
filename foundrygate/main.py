"""FoundryGate – FastAPI application.

OpenAI-compatible /v1/chat/completions proxy that routes requests
through a 3-layer classification engine to the optimal provider.
"""

# ruff: noqa: E501

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from starlette.datastructures import UploadFile

from . import __version__
from .config import Config, load_config
from .hooks import AppliedHooks, HookExecutionError, RequestHookContext, apply_request_hooks
from .metrics import MetricsStore, calc_cost
from .providers import ProviderBackend, ProviderError
from .router import Router, RoutingDecision
from .updates import UpdateChecker

logger = logging.getLogger("foundrygate")

# ── Globals (initialized in lifespan) ──────────────────────────
_config: Config
_providers: dict[str, ProviderBackend] = {}
_router: Router
_metrics: MetricsStore
_update_checker: UpdateChecker


def _client_error_response(message: str, *, error_type: str, status_code: int) -> JSONResponse:
    """Return a client-facing JSON error without exposing internal exception details."""
    return JSONResponse({"error": message, "type": error_type}, status_code=status_code)


def _request_hook_error_response(exc: Exception) -> JSONResponse:
    """Return a sanitized request-hook failure response."""
    logger.warning("Request hook processing failed: %s", exc)
    return _client_error_response(
        "Request hook processing failed",
        error_type="request_hook_error",
        status_code=500,
    )


def _invalid_request_response(message: str, *, exc: Exception | None = None) -> JSONResponse:
    """Return a sanitized invalid-request response."""
    if exc is not None:
        logger.info("Invalid request rejected: %s", exc)
    return _client_error_response(message, error_type="invalid_request_error", status_code=400)


async def _refresh_local_worker_probes(force: bool = False) -> None:
    """Refresh local-worker health state when probes are due."""
    timeout_seconds = float(_config.health.get("timeout_seconds", 10))
    check_interval = float(_config.health.get("check_interval_seconds", 300))
    recovery_interval = float(_config.health.get("recovery_check_interval_seconds", 60))

    for provider in _providers.values():
        if provider.contract != "local-worker":
            continue

        interval = recovery_interval if not provider.health.healthy else check_interval
        due = (
            force
            or provider.health.last_check == 0
            or (time.time() - provider.health.last_check) >= interval
        )

        if not due:
            continue

        ok = await provider.probe_health(timeout_seconds=timeout_seconds)
        logger.info(
            "Local worker probe: %s -> %s",
            provider.name,
            "healthy" if ok else "unhealthy",
        )


def _collect_routing_headers(request: Request) -> dict[str, str]:
    """Return the request headers that are relevant for routing decisions."""
    prefixes = ("x-openclaw", "x-foundrygate")
    return {k.lower(): v for k, v in request.headers.items() if k.lower().startswith(prefixes)}


def _match_client_profile_rule(match: dict, headers: dict[str, str]) -> bool:
    """Evaluate one client profile match block."""
    if not match:
        return True
    if "all" in match:
        return all(_match_client_profile_rule(item, headers) for item in match["all"])
    if "any" in match:
        return any(_match_client_profile_rule(item, headers) for item in match["any"])
    if "header_present" in match:
        return all(header_name in headers for header_name in match["header_present"])
    if "header_contains" in match:
        for header_name, patterns in match["header_contains"].items():
            header_value = headers.get(header_name, "").lower()
            if any(pattern.lower() in header_value for pattern in patterns):
                return True
        return False
    return False


def _resolve_client_profile(
    config: Config, headers: dict[str, str], profile_override: str | None = None
) -> tuple[str, dict[str, object]]:
    """Resolve the active client profile and its routing hints from request headers."""
    profiles_cfg = config.client_profiles
    default_profile = profiles_cfg.get("default", "generic")
    active_profile = default_profile

    if profile_override and profile_override in profiles_cfg.get("profiles", {}):
        active_profile = profile_override
    elif profile_override:
        logger.warning("Ignoring unknown request hook profile override: %s", profile_override)

    elif profiles_cfg.get("enabled"):
        for rule in profiles_cfg.get("rules", []):
            if _match_client_profile_rule(rule.get("match", {}), headers):
                active_profile = rule["profile"]
                break

    hints = profiles_cfg.get("profiles", {}).get(active_profile, {})
    return active_profile, hints


def _resolve_client_tag(headers: dict[str, str], client_profile: str) -> str:
    """Return a stable client tag for metrics and trace grouping."""
    if headers.get("x-foundrygate-client"):
        return headers["x-foundrygate-client"].strip().lower()
    if headers.get("x-openclaw-source"):
        return "openclaw"
    return client_profile


def _build_attempt_order(
    primary_provider: str,
    *,
    required_capabilities: list[str] | None = None,
) -> list[str]:
    """Return the provider attempt order for one routed request."""
    attempt_order = []
    for provider_name in [primary_provider, *_config.fallback_chain]:
        provider = _providers.get(provider_name)
        if not provider or provider_name in attempt_order:
            continue
        if required_capabilities and any(
            not provider.capabilities.get(capability) for capability in required_capabilities
        ):
            continue
        attempt_order.append(provider_name)
    return attempt_order


def _serialize_provider(name: str) -> dict[str, Any] | None:
    """Return one provider snapshot for API responses."""
    provider = _providers.get(name)
    if not provider:
        return None

    return {
        "name": name,
        "model": provider.model,
        "backend": provider.backend_type,
        "contract": provider.contract,
        "tier": provider.tier,
        "healthy": provider.health.healthy,
        "capabilities": provider.capabilities,
        "context_window": provider.context_window,
        "limits": provider.limits,
        "cache": provider.cache,
    }


def _estimate_request_dimensions(body: dict[str, Any]) -> dict[str, int | str]:
    """Return lightweight request-dimension estimates for debugging and routing preview."""
    messages = body.get("messages", [])
    system_parts = []
    full_parts = []
    for msg in messages:
        content = msg.get("content") or ""
        if isinstance(content, list):
            content = " ".join(part.get("text") or "" for part in content if isinstance(part, dict))
        if msg.get("role") == "system":
            system_parts.append(content)
        full_parts.append(content)

    full_text = "\n".join(full_parts)
    system_text = "\n".join(system_parts)
    estimated_input_tokens = max(1, len(full_text) // 4) if full_text else 0
    stable_prefix_tokens = max(1, len(system_text) // 4) if system_text else 0
    requested_output_tokens = (
        body.get("max_tokens") if isinstance(body.get("max_tokens"), int) else 0
    )
    return {
        "estimated_input_tokens": estimated_input_tokens,
        "stable_prefix_tokens": stable_prefix_tokens,
        "requested_output_tokens": requested_output_tokens,
        "estimated_total_tokens": estimated_input_tokens + requested_output_tokens,
        "cache_preference": str(_collect_request_cache_preference(body) or ""),
    }


def _estimate_image_request_dimensions(body: dict[str, Any], *, capability: str) -> dict[str, Any]:
    """Return lightweight image-request details for debugging and routing preview."""
    return {
        "prompt_chars": len(str(body.get("prompt") or "")),
        "requested_size": body.get("size") or "",
        "requested_outputs": body.get("n") if isinstance(body.get("n"), int) else 1,
        "capability": capability,
    }


def _collect_request_cache_preference(body: dict[str, Any]) -> str:
    """Return one request-level cache preference."""
    metadata = body.get("metadata") if isinstance(body.get("metadata"), dict) else {}
    if isinstance(metadata.get("cache_preference"), str):
        return metadata["cache_preference"].strip().lower()
    return ""


def _merge_routing_context_headers(headers: dict[str, str], body: dict[str, Any]) -> dict[str, str]:
    """Return routing headers plus request-body dimension hints."""
    merged = dict(headers)
    cache_preference = _collect_request_cache_preference(body)
    if cache_preference:
        merged["x-foundrygate-cache"] = cache_preference
    return merged


async def _apply_request_hooks(
    body: dict[str, Any], headers: dict[str, str]
) -> tuple[dict[str, Any], AppliedHooks]:
    """Apply configured request hooks before route resolution."""
    model_requested = str(body.get("model", "auto"))
    applied = await apply_request_hooks(
        _config.request_hooks,
        RequestHookContext(
            body=dict(body),
            headers=headers,
            model_requested=model_requested,
        ),
    )
    return applied.body, applied


async def _resolve_route_preview(
    body: dict[str, Any], headers: dict[str, str]
) -> tuple[RoutingDecision, str, str, list[str], str, AppliedHooks, dict[str, Any]]:
    """Resolve one request into a routing decision without calling a provider."""
    body, hook_state = await _apply_request_hooks(body, headers)
    messages = body.get("messages", [])
    model_requested = body.get("model", "auto")
    tools = body.get("tools")
    max_tokens = body.get("max_tokens") if isinstance(body.get("max_tokens"), int) else None

    client_profile, profile_hints = _resolve_client_profile(
        _config,
        headers,
        profile_override=hook_state.profile_override,
    )
    client_tag = _resolve_client_tag(headers, client_profile)

    if model_requested != "auto" and model_requested in _providers:
        decision = RoutingDecision(
            provider_name=model_requested,
            layer="direct",
            rule_name="explicit-model",
            confidence=1.0,
            reason=f"Directly requested provider: {model_requested}",
        )
    else:
        health_map = {name: p.health.to_dict() for name, p in _providers.items()}
        decision = await _router.route(
            messages,
            model_requested=model_requested,
            has_tools=bool(tools),
            requested_max_tokens=max_tokens,
            client_profile=client_profile,
            profile_hints=profile_hints,
            hook_hints=hook_state.routing_hints,
            applied_hooks=hook_state.applied_hooks,
            headers=_merge_routing_context_headers(headers, body),
            provider_health=health_map,
        )

    return (
        decision,
        client_profile,
        client_tag,
        _build_attempt_order(decision.provider_name),
        model_requested,
        hook_state,
        body,
    )


def _collect_image_request_fields(body: dict[str, Any]) -> dict[str, Any]:
    """Return a narrow, validated subset of image-generation request fields."""
    fields: dict[str, Any] = {}
    if isinstance(body.get("n"), int) and body["n"] > 0:
        fields["n"] = body["n"]
    for key in ("size", "quality", "response_format", "style", "background", "user"):
        value = body.get(key)
        if isinstance(value, str) and value.strip():
            fields[key] = value.strip()
    return fields


def _parse_optional_positive_int(value: Any, *, field_name: str) -> int | None:
    """Return one optional positive integer field from request data."""
    if value in (None, ""):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Field '{field_name}' must be a positive integer") from exc
    if parsed <= 0:
        raise ValueError(f"Field '{field_name}' must be a positive integer")
    return parsed


def _extract_image_edit_request_fields(form_data: dict[str, Any]) -> dict[str, Any]:
    """Return the validated scalar fields for one image-edit request."""
    prompt = form_data.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("Image editing requires a non-empty 'prompt' field")

    model = form_data.get("model")
    if model is None:
        model = "auto"
    elif not isinstance(model, str) or not model.strip():
        raise ValueError("Field 'model' must be a non-empty string when provided")

    payload: dict[str, Any] = {
        "prompt": prompt.strip(),
        "model": model.strip() if isinstance(model, str) else "auto",
    }

    n = _parse_optional_positive_int(form_data.get("n"), field_name="n")
    if n is not None:
        payload["n"] = n

    for key in ("size", "response_format", "user"):
        value = form_data.get(key)
        if isinstance(value, str) and value.strip():
            payload[key] = value.strip()

    return payload


async def _read_uploaded_file(
    value: Any, *, field_name: str, required: bool
) -> dict[str, Any] | None:
    """Read one uploaded file into a normalized payload."""
    if value is None:
        if required:
            raise ValueError(f"Image editing requires file field '{field_name}'")
        return None

    if not isinstance(value, UploadFile):
        raise ValueError(f"Field '{field_name}' must be an uploaded file")

    content = await value.read()
    if not content:
        raise ValueError(f"Uploaded file '{field_name}' must not be empty")

    return {
        "filename": value.filename or field_name,
        "content": content,
        "content_type": value.content_type or "application/octet-stream",
    }


async def _resolve_image_route_preview(
    body: dict[str, Any], headers: dict[str, str], *, capability: str = "image_generation"
) -> tuple[RoutingDecision, str, str, list[str], str, AppliedHooks, dict[str, Any]]:
    """Resolve one image-generation request without calling a provider."""
    body, hook_state = await _apply_request_hooks(body, headers)
    prompt = body.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("Image request requires a non-empty 'prompt' string")

    model_requested = str(body.get("model", "auto"))
    client_profile, profile_hints = _resolve_client_profile(
        _config,
        headers,
        profile_override=hook_state.profile_override,
    )
    client_tag = _resolve_client_tag(headers, client_profile)

    if model_requested != "auto":
        provider = _providers.get(model_requested)
        if not provider:
            raise ValueError(f"Unknown image provider '{model_requested}'")
        if not provider.capabilities.get(capability):
            raise ValueError(f"Provider '{model_requested}' does not support {capability}")
        decision = RoutingDecision(
            provider_name=model_requested,
            layer="direct",
            rule_name=f"explicit-{capability}-model",
            confidence=1.0,
            reason=f"Directly requested image provider: {model_requested}",
            details={"required_capability": capability},
        )
    else:
        decision = _router.route_capability_request(
            capability=capability,
            request_text=prompt,
            model_requested=model_requested,
            client_profile=client_profile,
            profile_hints=profile_hints,
            hook_hints=hook_state.routing_hints,
            applied_hooks=hook_state.applied_hooks,
            headers=headers,
            provider_health={name: p.health.to_dict() for name, p in _providers.items()},
        )
        if not decision:
            raise ValueError(f"No provider with capability '{capability}' is available")

    return (
        decision,
        client_profile,
        client_tag,
        _build_attempt_order(
            decision.provider_name,
            required_capabilities=[capability],
        ),
        model_requested,
        hook_state,
        body,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    global _config, _providers, _router, _metrics, _update_checker

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    _config = load_config()
    logger.info("Loaded config with %d providers", len(_config.providers))

    # Initialize provider backends
    for name, pcfg in _config.providers.items():
        if not pcfg.get("api_key"):
            logger.warning("Provider %s has no API key, skipping", name)
            continue
        _providers[name] = ProviderBackend(name, pcfg)
        logger.info("  ✓ %s → %s (%s)", name, pcfg["model"], pcfg.get("tier", "default"))

    _router = Router(_config)
    await _refresh_local_worker_probes(force=True)
    _update_checker = UpdateChecker(
        current_version=__version__,
        enabled=bool(_config.update_check.get("enabled", True)),
        repository=str(_config.update_check.get("repository", "typelicious/FoundryGate")),
        api_base=str(_config.update_check.get("api_base", "https://api.github.com")),
        check_interval_seconds=int(_config.update_check.get("check_interval_seconds", 21600)),
        timeout_seconds=float(_config.update_check.get("timeout_seconds", 5.0)),
    )

    # Metrics
    _metrics = MetricsStore(db_path=_config.metrics["db_path"])
    if _config.metrics.get("enabled"):
        _metrics.init()

    logger.info(
        "FoundryGate ready on %s:%s",
        _config.server.get("host", "127.0.0.1"),
        _config.server.get("port", 8090),
    )

    yield

    # Shutdown
    for p in _providers.values():
        await p.close()
    await _update_checker.close()
    _metrics.close()
    logger.info("FoundryGate shut down")


app = FastAPI(
    title="FoundryGate",
    version="0.5.0",
    description="Local OpenAI-compatible routing gateway for OpenClaw and other clients.",
    lifespan=lifespan,
)


# ── Health / Info endpoints ────────────────────────────────────


@app.get("/health")
async def health():
    await _refresh_local_worker_probes()
    return {
        "status": "ok",
        "providers": {
            name: {
                **p.health.to_dict(),
                "contract": p.contract,
                "backend": p.backend_type,
                "tier": p.tier,
                "capabilities": p.capabilities,
                "context_window": p.context_window,
                "limits": p.limits,
                "cache": p.cache,
            }
            for name, p in _providers.items()
        },
    }


@app.get("/v1/models")
async def list_models():
    """OpenAI-compatible model listing."""
    models = []
    # Expose a virtual "auto" model + each real provider
    models.append(
        {
            "id": "auto",
            "object": "model",
            "owned_by": "foundrygate",
            "description": "Auto-routed to optimal provider",
        }
    )
    for name, p in _providers.items():
        models.append(
            {
                "id": name,
                "object": "model",
                "owned_by": p.backend_type,
                "description": f"{p.model} ({p.tier})",
                "contract": p.contract,
                "capabilities": p.capabilities,
                "context_window": p.context_window,
                "limits": p.limits,
                "cache": p.cache,
            }
        )
    return {"object": "list", "data": models}


@app.get("/api/stats")
async def stats(
    provider: str | None = None,
    modality: str | None = None,
    client_profile: str | None = None,
    client_tag: str | None = None,
    layer: str | None = None,
    success: bool | None = None,
):
    """Full statistics: totals, per-provider, routing breakdown, time series."""
    filters = {
        "provider": provider,
        "modality": modality,
        "client_profile": client_profile,
        "client_tag": client_tag,
        "layer": layer,
        "success": success,
    }
    return {
        "totals": _metrics.get_totals(**filters),
        "providers": _metrics.get_provider_summary(**filters),
        "modalities": _metrics.get_modality_breakdown(**filters),
        "routing": _metrics.get_routing_breakdown(**filters),
        "clients": _metrics.get_client_breakdown(**filters),
        "hourly": _metrics.get_hourly_series(24),
        "daily": _metrics.get_daily_totals(30),
    }


@app.get("/api/recent")
async def recent(
    limit: int = 50,
    provider: str | None = None,
    modality: str | None = None,
    client_profile: str | None = None,
    client_tag: str | None = None,
    layer: str | None = None,
    success: bool | None = None,
):
    """Recent request log."""
    return {
        "requests": _metrics.get_recent(
            limit,
            provider=provider,
            modality=modality,
            client_profile=client_profile,
            client_tag=client_tag,
            layer=layer,
            success=success,
        )
    }


@app.get("/api/traces")
async def traces(
    limit: int = 50,
    provider: str | None = None,
    modality: str | None = None,
    client_profile: str | None = None,
    client_tag: str | None = None,
    layer: str | None = None,
    success: bool | None = None,
):
    """Recent enriched route traces for debugging and policy tuning."""
    return {
        "traces": _metrics.get_recent(
            limit,
            provider=provider,
            modality=modality,
            client_profile=client_profile,
            client_tag=client_tag,
            layer=layer,
            success=success,
        )
    }


@app.get("/api/update")
async def update_status(force: bool = False):
    """Return cached or fresh release update metadata."""
    status = await _update_checker.get_status(force=force)
    return status.to_dict()


@app.post("/api/route")
async def preview_route(request: Request):
    """Dry-run one routing decision without sending a provider request."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    headers = _collect_routing_headers(request)
    try:
        (
            decision,
            client_profile,
            client_tag,
            attempt_order,
            model_requested,
            hook_state,
            effective_body,
        ) = await _resolve_route_preview(body, headers)
    except HookExecutionError as exc:
        return _request_hook_error_response(exc)

    return {
        "requested_model": model_requested,
        "resolved_profile": client_profile,
        "client_tag": client_tag,
        "routing_headers": headers,
        "applied_hooks": hook_state.applied_hooks,
        "hook_notes": hook_state.notes,
        "hook_errors": hook_state.errors,
        "effective_request": {
            "modality": "chat",
            "model": effective_body.get("model", "auto"),
            "has_tools": bool(effective_body.get("tools")),
            **_estimate_request_dimensions(effective_body),
        },
        "decision": decision.to_dict(),
        "selected_provider": _serialize_provider(decision.provider_name),
        "attempt_order": [_serialize_provider(name) for name in attempt_order],
    }


@app.post("/api/route/image")
async def preview_image_route(request: Request):
    """Dry-run one image routing decision without sending a provider request."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    capability = str(body.get("capability") or "image_generation").strip().lower()
    if capability not in {"image_generation", "image_editing"}:
        return _invalid_request_response(
            "Invalid image route preview request",
            exc=ValueError("Unsupported capability"),
        )

    headers = _collect_routing_headers(request)
    preview_body = dict(body)
    preview_body.pop("capability", None)
    try:
        (
            decision,
            client_profile,
            client_tag,
            attempt_order,
            model_requested,
            hook_state,
            effective_body,
        ) = await _resolve_image_route_preview(preview_body, headers, capability=capability)
    except HookExecutionError as exc:
        return _request_hook_error_response(exc)
    except ValueError as exc:
        return _invalid_request_response("Invalid image route preview request", exc=exc)

    return {
        "requested_model": model_requested,
        "resolved_profile": client_profile,
        "client_tag": client_tag,
        "routing_headers": headers,
        "applied_hooks": hook_state.applied_hooks,
        "hook_notes": hook_state.notes,
        "hook_errors": hook_state.errors,
        "effective_request": {
            "modality": capability,
            "model": effective_body.get("model", "auto"),
            **_estimate_image_request_dimensions(effective_body, capability=capability),
        },
        "decision": decision.to_dict(),
        "selected_provider": _serialize_provider(decision.provider_name),
        "attempt_order": [_serialize_provider(name) for name in attempt_order],
    }


@app.post("/v1/images/generations")
async def image_generations(request: Request):
    """OpenAI-compatible image generation endpoint."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    headers = _collect_routing_headers(request)
    try:
        (
            decision,
            client_profile,
            client_tag,
            attempt_order,
            model_requested,
            hook_state,
            effective_body,
        ) = await _resolve_image_route_preview(body, headers)
    except HookExecutionError as exc:
        return _request_hook_error_response(exc)
    except ValueError as exc:
        return _invalid_request_response("Invalid image generation request", exc=exc)

    prompt = effective_body["prompt"].strip()
    image_fields = _collect_image_request_fields(effective_body)
    errors: list[str] = []

    for provider_name in attempt_order:
        provider = _providers.get(provider_name)
        if not provider:
            continue
        if not provider.health.healthy and provider_name != attempt_order[0]:
            continue

        try:
            result = await provider.generate_image(
                prompt,
                extra_body=image_fields,
            )
            if _config.metrics.get("enabled") and isinstance(result, dict):
                _metrics.log_request(
                    provider=provider_name,
                    model=provider.model,
                    layer=decision.layer,
                    rule_name=decision.rule_name,
                    latency_ms=(result.get("_foundrygate") or {}).get("latency_ms", 0),
                    requested_model=model_requested,
                    modality="image_generation",
                    client_profile=client_profile,
                    client_tag=client_tag,
                    decision_reason=decision.reason,
                    confidence=decision.confidence,
                    attempt_order=attempt_order,
                )

            resp = JSONResponse(result)
            resp.headers["X-FoundryGate-Provider"] = provider_name
            resp.headers["X-FoundryGate-Profile"] = client_profile
            resp.headers["X-FoundryGate-Layer"] = decision.layer
            resp.headers["X-FoundryGate-Rule"] = decision.rule_name
            resp.headers["X-FoundryGate-Hooks"] = ",".join(hook_state.applied_hooks)
            resp.headers["X-FoundryGate-Hook-Errors"] = str(len(hook_state.errors))
            return resp
        except ProviderError as exc:
            errors.append(f"{provider_name}: {exc.detail}")
            logger.warning(
                "Image provider %s failed: %s, trying next...",
                provider_name,
                exc.detail[:200],
            )
            if _config.metrics.get("enabled"):
                _metrics.log_request(
                    provider=provider_name,
                    model=provider.model,
                    layer=decision.layer,
                    rule_name=decision.rule_name,
                    success=False,
                    error=exc.detail[:500],
                    requested_model=model_requested,
                    modality="image_generation",
                    client_profile=client_profile,
                    client_tag=client_tag,
                    decision_reason=decision.reason,
                    confidence=decision.confidence,
                    attempt_order=attempt_order,
                )

    return JSONResponse(
        {
            "error": {
                "message": f"All image providers failed: {'; '.join(errors)}",
                "type": "provider_error",
                "attempts": errors,
            }
        },
        status_code=502,
    )


@app.post("/v1/images/edits")
async def image_edits(request: Request):
    """OpenAI-compatible image editing endpoint."""
    try:
        form = await request.form()
        form_data = dict(form.multi_items())
        body = _extract_image_edit_request_fields(form_data)
        image = await _read_uploaded_file(form_data.get("image"), field_name="image", required=True)
        mask = await _read_uploaded_file(form_data.get("mask"), field_name="mask", required=False)
    except ValueError as exc:
        return _invalid_request_response("Invalid image editing request", exc=exc)
    except Exception as exc:
        logger.warning("Failed to parse image editing form: %s", exc)
        return _invalid_request_response("Invalid image editing request")

    headers = _collect_routing_headers(request)
    try:
        (
            decision,
            client_profile,
            client_tag,
            attempt_order,
            model_requested,
            hook_state,
            effective_body,
        ) = await _resolve_image_route_preview(body, headers, capability="image_editing")
    except HookExecutionError as exc:
        return _request_hook_error_response(exc)
    except ValueError as exc:
        return _invalid_request_response("Invalid image editing request", exc=exc)

    prompt = effective_body["prompt"].strip()
    errors: list[str] = []

    for provider_name in attempt_order:
        provider = _providers.get(provider_name)
        if not provider:
            continue
        if not provider.health.healthy and provider_name != attempt_order[0]:
            continue

        try:
            result = await provider.edit_image(
                prompt,
                image=image,
                mask=mask,
                n=effective_body.get("n", 1),
                size=effective_body.get("size"),
                response_format=effective_body.get("response_format"),
                user=effective_body.get("user"),
            )
            if _config.metrics.get("enabled") and isinstance(result, dict):
                _metrics.log_request(
                    provider=provider_name,
                    model=provider.model,
                    layer=decision.layer,
                    rule_name=decision.rule_name,
                    latency_ms=(result.get("_foundrygate") or {}).get("latency_ms", 0),
                    requested_model=model_requested,
                    modality="image_editing",
                    client_profile=client_profile,
                    client_tag=client_tag,
                    decision_reason=decision.reason,
                    confidence=decision.confidence,
                    attempt_order=attempt_order,
                )

            resp = JSONResponse(result)
            resp.headers["X-FoundryGate-Provider"] = provider_name
            resp.headers["X-FoundryGate-Profile"] = client_profile
            resp.headers["X-FoundryGate-Layer"] = decision.layer
            resp.headers["X-FoundryGate-Rule"] = decision.rule_name
            resp.headers["X-FoundryGate-Hooks"] = ",".join(hook_state.applied_hooks)
            resp.headers["X-FoundryGate-Hook-Errors"] = str(len(hook_state.errors))
            return resp
        except ProviderError as exc:
            errors.append(f"{provider_name}: {exc.detail}")
            logger.warning(
                "Image editing provider %s failed: %s, trying next...",
                provider_name,
                exc.detail[:200],
            )
            if _config.metrics.get("enabled"):
                _metrics.log_request(
                    provider=provider_name,
                    model=provider.model,
                    layer=decision.layer,
                    rule_name=decision.rule_name,
                    success=False,
                    error=exc.detail[:500],
                    requested_model=model_requested,
                    modality="image_editing",
                    client_profile=client_profile,
                    client_tag=client_tag,
                    decision_reason=decision.reason,
                    confidence=decision.confidence,
                    attempt_order=attempt_order,
                )

    return JSONResponse(
        {
            "error": {
                "message": f"All image editing providers failed: {'; '.join(errors)}",
                "type": "provider_error",
                "attempts": errors,
            }
        },
        status_code=502,
    )


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    """Minimal self-contained dashboard – no build step, no deps."""
    return _DASHBOARD_HTML


# ── Main completion endpoint ───────────────────────────────────


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    """
    OpenAI-compatible chat completion endpoint.

    If model is "auto" or omitted: routes through the 3-layer engine.
    If model matches a provider name: routes directly to that provider.
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    headers = _collect_routing_headers(request)
    try:
        (
            decision,
            client_profile,
            client_tag,
            attempt_order,
            model_requested,
            hook_state,
            effective_body,
        ) = await _resolve_route_preview(body, headers)
    except HookExecutionError as exc:
        return _request_hook_error_response(exc)
    messages = effective_body.get("messages", [])
    stream = effective_body.get("stream", False)
    temperature = effective_body.get("temperature")
    max_tokens = effective_body.get("max_tokens")
    tools = effective_body.get("tools")

    logger.info(
        "Route: %s [%s/%s] %.1fms",
        decision.provider_name,
        decision.layer,
        decision.rule_name,
        decision.elapsed_ms,
    )

    # ── Execute with fallback ──────────────────────────────

    errors: list[str] = []

    for provider_name in attempt_order:
        provider = _providers.get(provider_name)
        if not provider:
            continue
        if not provider.health.healthy and provider_name != attempt_order[0]:
            continue  # Skip known-unhealthy fallbacks (but always try the chosen one)

        try:
            result = await provider.complete(
                messages,
                stream=stream,
                temperature=temperature,
                max_tokens=max_tokens,
                tools=tools,
            )

            # Log metrics with cost (cache-aware)
            if _config.metrics.get("enabled") and isinstance(result, dict):
                usage = result.get("usage", {})
                cg = result.get("_foundrygate", {})
                pt = usage.get("prompt_tokens", 0)
                ct = usage.get("completion_tokens", 0)
                ch = cg.get("cache_hit_tokens", 0)
                cm = cg.get("cache_miss_tokens", 0)
                provider_cfg = _config.provider(provider_name)
                pricing = provider_cfg.get("pricing", {}) if provider_cfg else {}
                cost = calc_cost(pt, ct, pricing, cache_hit=ch, cache_miss=cm)
                _metrics.log_request(
                    provider=provider_name,
                    model=provider.model,
                    layer=decision.layer,
                    rule_name=decision.rule_name,
                    prompt_tokens=pt,
                    completion_tokens=ct,
                    cache_hit=ch,
                    cache_miss=cm,
                    cost_usd=cost,
                    latency_ms=cg.get("latency_ms", 0),
                    requested_model=model_requested,
                    modality="chat",
                    client_profile=client_profile,
                    client_tag=client_tag,
                    decision_reason=decision.reason,
                    confidence=decision.confidence,
                    attempt_order=attempt_order,
                )

            if stream:
                return StreamingResponse(
                    result,
                    media_type="text/event-stream",
                    headers={
                        "X-FoundryGate-Provider": provider_name,
                        "X-FoundryGate-Profile": client_profile,
                        "X-FoundryGate-Hooks": ",".join(hook_state.applied_hooks),
                        "X-FoundryGate-Hook-Errors": str(len(hook_state.errors)),
                    },
                )

            # Add routing info to response headers (non-streaming)
            resp = JSONResponse(result)
            resp.headers["X-FoundryGate-Provider"] = provider_name
            resp.headers["X-FoundryGate-Profile"] = client_profile
            resp.headers["X-FoundryGate-Layer"] = decision.layer
            resp.headers["X-FoundryGate-Rule"] = decision.rule_name
            resp.headers["X-FoundryGate-Hooks"] = ",".join(hook_state.applied_hooks)
            resp.headers["X-FoundryGate-Hook-Errors"] = str(len(hook_state.errors))
            return resp

        except ProviderError as e:
            errors.append(f"{provider_name}: {e.detail}")
            logger.warning("Provider %s failed: %s, trying next...", provider_name, e.detail[:200])
            if _config.metrics.get("enabled"):
                _metrics.log_request(
                    provider=provider_name,
                    model=provider.model,
                    layer=decision.layer,
                    rule_name=decision.rule_name,
                    success=False,
                    error=e.detail[:500],
                    requested_model=model_requested,
                    modality="chat",
                    client_profile=client_profile,
                    client_tag=client_tag,
                    decision_reason=decision.reason,
                    confidence=decision.confidence,
                    attempt_order=attempt_order,
                )
            continue

    # All providers failed
    return JSONResponse(
        {
            "error": {
                "message": f"All providers failed: {'; '.join(errors)}",
                "type": "provider_error",
                "attempts": errors,
            }
        },
        status_code=502,
    )


# ── CLI entry point ────────────────────────────────────────────


def main():
    """Run with: python -m foundrygate"""
    import uvicorn

    config = load_config()
    uvicorn.run(
        "foundrygate.main:app",
        host=config.server.get("host", "127.0.0.1"),
        port=config.server.get("port", 8090),
        log_level=config.server.get("log_level", "info"),
        reload=False,
    )


# ── Dashboard HTML ─────────────────────────────────────────────

_DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>FoundryGate</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:system-ui,-apple-system,sans-serif;background:#0a0a0f;color:#e0e0e0;padding:20px}
h1{font-size:1.4em;color:#7af;margin-bottom:4px}
.sub{color:#888;font-size:.85em}
.topbar{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:16px;flex-wrap:wrap}
.actions{display:flex;gap:8px;align-items:center}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin-bottom:24px}
.card,.filters,.sect{background:#14141f;border:1px solid #222;border-radius:10px}
.card{padding:16px}
.card .label{font-size:.75em;color:#888;text-transform:uppercase;letter-spacing:.5px}
.card .value{font-size:1.8em;font-weight:700;color:#7af;margin-top:2px}
.card .value.cost{color:#5e5}
.card .value.err{color:#f66}
.card .detail{font-size:.75em;color:#666;margin-top:4px}
.filters{padding:14px 16px;margin-bottom:16px}
.filters h2,.sect h2{font-size:1em;color:#aaa;margin-bottom:10px}
.filters .summary{margin-top:8px;color:#7f8aa3;font-size:.8em}
.filters-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:10px}
label{display:flex;flex-direction:column;gap:6px;font-size:.75em;color:#888;text-transform:uppercase;letter-spacing:.5px}
input,select{background:#0f1117;color:#e0e0e0;border:1px solid #2a2d38;border-radius:8px;padding:8px 10px;font-size:.9em}
button{background:#222;color:#ddd;border:1px solid #333;border-radius:8px;padding:8px 12px;cursor:pointer;font-size:.85em}
button:hover{background:#2a2a3a}
.filters-actions{display:flex;gap:8px;margin-top:12px;flex-wrap:wrap}
.sect{padding:14px 16px;margin-bottom:16px}
table{width:100%;border-collapse:collapse;font-size:.85em}
th{text-align:left;padding:8px 10px;border-bottom:2px solid #333;color:#888;font-weight:600;text-transform:uppercase;font-size:.7em;letter-spacing:.5px}
td{padding:7px 10px;border-bottom:1px solid #1a1a2a;vertical-align:top}
tr:hover td{background:#1a1a2a}
.mono{font-family:'SF Mono',Consolas,monospace;font-size:.8em}
.tag{display:inline-block;padding:2px 8px;border-radius:999px;font-size:.72em;font-weight:600}
.tag-policy{background:#243247;color:#9fc3ff}
.tag-static{background:#2a2a4a;color:#99f}
.tag-heuristic{background:#203726;color:#9f9}
.tag-hook{background:#3b2c1d;color:#ffcf8a}
.tag-profile{background:#2a2140;color:#d5b3ff}
.tag-direct{background:#3a3a2a;color:#ff9}
.tag-fallback{background:#3a2222;color:#f99}
.tag-llm-classify{background:#1d3b3b;color:#9ff}
.tag-healthy{background:#203726;color:#9f9}
.tag-unhealthy{background:#3a2222;color:#f99}
.pill{display:inline-block;padding:2px 6px;border-radius:6px;background:#1c2230;color:#9db2d1;font-size:.72em}
#status{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px}
.empty{color:#666;padding:8px 0}
.note{color:#666;font-size:.78em}
</style>
</head>
<body>
<div class="topbar">
  <div>
    <h1><span id="status"></span>FoundryGate</h1>
    <div class="sub">Local AI Gateway Dashboard</div>
  </div>
  <div class="actions">
    <button type="button" onclick="applyFilters()">Apply Filters</button>
    <button type="button" onclick="resetFilters()">Clear</button>
    <button type="button" onclick="load()">Refresh</button>
    <span id="ago" class="mono note"></span>
  </div>
</div>

<div class="filters">
  <h2>Filters</h2>
  <div class="filters-grid">
    <label>Provider<input id="filter-provider" placeholder="local-worker"></label>
    <label>Modality
      <select id="filter-modality">
        <option value="">All modalities</option>
        <option value="chat">chat</option>
        <option value="image_generation">image_generation</option>
        <option value="image_editing">image_editing</option>
      </select>
    </label>
    <label>Client Profile<input id="filter-profile" placeholder="openclaw"></label>
    <label>Client Tag<input id="filter-client" placeholder="codex"></label>
    <label>Layer
      <select id="filter-layer">
        <option value="">All layers</option>
        <option value="policy">policy</option>
        <option value="static">static</option>
        <option value="heuristic">heuristic</option>
        <option value="hook">hook</option>
        <option value="profile">profile</option>
        <option value="llm-classify">llm-classify</option>
        <option value="fallback">fallback</option>
        <option value="direct">direct</option>
      </select>
    </label>
    <label>Status
      <select id="filter-success">
        <option value="">All</option>
        <option value="true">Success</option>
        <option value="false">Failure</option>
      </select>
    </label>
  </div>
  <div class="filters-actions">
    <span class="note">Filters apply to stats, traces, and recent requests.</span>
  </div>
  <div id="filter-summary" class="summary"></div>
</div>

<div class="grid" id="cards"></div>

<div class="sect">
  <h2>Provider Health</h2>
  <table id="health"><thead><tr>
    <th>Provider</th><th>Status</th><th>Contract</th><th>Tier</th><th>Context</th><th>Limits</th><th>Cache</th><th>Latency</th><th>Last Error</th>
  </tr></thead><tbody></tbody></table>
</div>

<div class="sect">
  <h2>Client Breakdown</h2>
  <table id="clients"><thead><tr>
    <th>Modality</th><th>Profile</th><th>Client Tag</th><th>Provider</th><th>Layer</th><th>Requests</th><th>Cost</th><th>Avg Latency</th>
  </tr></thead><tbody></tbody></table>
</div>

<div class="sect">
  <h2>Modality Breakdown</h2>
  <table id="modalities"><thead><tr>
    <th>Modality</th><th>Provider</th><th>Layer</th><th>Requests</th><th>Cost</th><th>Avg Latency</th>
  </tr></thead><tbody></tbody></table>
</div>

<div class="sect">
  <h2>Routing Rules</h2>
  <table id="routing"><thead><tr>
    <th>Layer</th><th>Rule</th><th>Provider</th><th>Requests</th><th>Cost</th><th>Avg Latency</th>
  </tr></thead><tbody></tbody></table>
</div>

<div class="sect">
  <h2>Route Traces</h2>
  <table id="traces"><thead><tr>
    <th>Time</th><th>Provider</th><th>Profile</th><th>Client</th><th>Layer</th><th>Reason</th><th>Confidence</th><th>Attempts</th>
  </tr></thead><tbody></tbody></table>
</div>

<div class="sect">
  <h2>Recent Requests</h2>
  <table id="recent"><thead><tr>
    <th>Time</th><th>Provider</th><th>Layer</th><th>Rule</th><th>Tokens</th><th>Cost</th><th>Latency</th><th>Status</th>
  </tr></thead><tbody></tbody></table>
</div>

<script>
const $ = s => document.querySelector(s);
const fmt = (n,d=2) => n!=null ? Number(n).toLocaleString('en',{minimumFractionDigits:d,maximumFractionDigits:d}) : '—';
const fmtUsd = n => n!=null ? '$'+fmt(n,4) : '—';
const fmtTok = n => n!=null ? (n>=1e6?(n/1e6).toFixed(1)+'M':n>=1e3?(n/1e3).toFixed(1)+'K':''+n) : '0';
const fmtMs = n => n!=null ? fmt(n,0)+'ms' : '—';
const ago = ts => {if(!ts)return '—';const s=Date.now()/1000-ts;return s<60?Math.round(s)+'s ago':s<3600?Math.round(s/60)+'m ago':Math.round(s/3600)+'h ago';};
const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',\"'\":'&#39;'}[ch]));
const layerTag = l => `<span class="tag tag-${esc((l||'unknown').toLowerCase())}">${esc(l||'unknown')}</span>`;
const statusTag = ok => ok ? '<span class="tag tag-healthy">healthy</span>' : '<span class="tag tag-unhealthy">unhealthy</span>';

function currentFilters(){
  const params = new URLSearchParams();
  const mapping = {
    provider: $('#filter-provider').value.trim(),
    modality: $('#filter-modality').value.trim(),
    client_profile: $('#filter-profile').value.trim(),
    client_tag: $('#filter-client').value.trim(),
    layer: $('#filter-layer').value.trim(),
    success: $('#filter-success').value.trim(),
  };
  Object.entries(mapping).forEach(([key, value]) => {
    if (value) params.set(key, value);
  });
  return params;
}

function syncFiltersFromUrl(){
  const params = new URLSearchParams(window.location.search);
  $('#filter-provider').value = params.get('provider') || '';
  $('#filter-modality').value = params.get('modality') || '';
  $('#filter-profile').value = params.get('client_profile') || '';
  $('#filter-client').value = params.get('client_tag') || '';
  $('#filter-layer').value = params.get('layer') || '';
  $('#filter-success').value = params.get('success') || '';
}

function describeFilters(params){
  const entries = [];
  for (const [key, value] of params.entries()){
    entries.push(`${key}=${value}`);
  }
  $('#filter-summary').textContent = entries.length
    ? `Active filters: ${entries.join(', ')}`
    : 'No active filters';
}

function persistFilters(params){
  const qs = params.toString();
  const next = qs ? `${window.location.pathname}?${qs}` : window.location.pathname;
  window.history.replaceState({}, '', next);
  describeFilters(params);
}

function applyFilters(){ load(); }

function resetFilters(){
  ['#filter-provider','#filter-modality','#filter-profile','#filter-client','#filter-layer','#filter-success'].forEach(sel => {
    $(sel).value = '';
  });
  load();
}

function emptyRow(colspan, label){
  return `<tr><td colspan="${colspan}" class="empty">${esc(label)}</td></tr>`;
}

function formatLimits(provider){
  const limits = provider?.limits || {};
  const parts = [];
  if (limits.max_input_tokens) parts.push(`in ${fmtTok(limits.max_input_tokens)}`);
  if (limits.max_output_tokens) parts.push(`out ${fmtTok(limits.max_output_tokens)}`);
  return parts.length ? esc(parts.join(' / ')) : '—';
}

async function load(){
  try{
    const query = currentFilters();
    persistFilters(query);
    const queryStr = query.toString();
    const suffix = queryStr ? `?${queryStr}` : '';
    const [health, stats, traces, rec, update] = await Promise.all([
      fetch('/health').then(r=>r.json()),
      fetch(`/api/stats${suffix}`).then(r=>r.json()),
      fetch(`/api/traces${suffix}${suffix ? '&' : '?'}limit=20`).then(r=>r.json()),
      fetch(`/api/recent${suffix}${suffix ? '&' : '?'}limit=20`).then(r=>r.json()),
      fetch('/api/update').then(r=>r.json()).catch(() => ({enabled:false,status:'unavailable'}))
    ]);

    const totals = stats.totals || {};
    const providers = Object.values(health.providers || {});
    const healthyProviders = providers.filter(provider => provider.healthy).length;
    const unhealthyProviders = providers.length - healthyProviders;
    const modalityRows = stats.modalities || [];
    const topModality = modalityRows.length ? modalityRows[0].modality : '—';
    $('#status').style.background = '#5e5';
    $('#ago').textContent = ago(totals.last_request);

    $('#cards').innerHTML = `
      <div class="card"><div class="label">Requests</div><div class="value">${fmtTok(totals.total_requests || 0)}</div></div>
      <div class="card"><div class="label">Cost</div><div class="value cost">${fmtUsd(totals.total_cost_usd || 0)}</div></div>
      <div class="card"><div class="label">Tokens</div><div class="value">${fmtTok((totals.total_prompt_tokens||0)+(totals.total_compl_tokens||0))}</div><div class="detail">${fmtTok(totals.total_prompt_tokens||0)} in / ${fmtTok(totals.total_compl_tokens||0)} out</div></div>
      <div class="card"><div class="label">Avg Latency</div><div class="value">${fmtMs(totals.avg_latency_ms || 0)}</div></div>
      <div class="card"><div class="label">Cache Hit Rate</div><div class="value cost">${fmt(totals.cache_hit_pct || 0,1)}%</div><div class="detail">${fmtTok(totals.total_cache_hit || 0)} hit / ${fmtTok(totals.total_cache_miss || 0)} miss</div></div>
      <div class="card"><div class="label">Failures</div><div class="value ${(totals.total_failures||0)>0?'err':''}">${totals.total_failures || 0}</div></div>
      <div class="card"><div class="label">Healthy Providers</div><div class="value">${healthyProviders}/${providers.length}</div><div class="detail">${unhealthyProviders} unhealthy</div></div>
      <div class="card"><div class="label">Top Modality</div><div class="value">${esc(topModality)}</div><div class="detail">${modalityRows.length} modality groups</div></div>
      <div class="card"><div class="label">Release Status</div><div class="value ${update.update_available ? 'cost' : ''}">${esc(update.latest_version || update.current_version || 'n/a')}</div><div class="detail">${update.enabled ? (update.update_available ? 'Update available' : update.status === 'ok' ? 'Up to date' : 'Update check unavailable') : 'Update checks disabled'}</div></div>
    `;

    const providerRows = Object.entries(health.providers || {}).map(([name, provider]) => `<tr>
      <td><strong>${esc(name)}</strong></td>
      <td>${statusTag(provider.healthy)}</td>
      <td>${esc(provider.contract || 'generic')}</td>
      <td>${esc(provider.tier || 'default')}</td>
      <td class="mono">${provider.context_window ? fmtTok(provider.context_window) : '—'}</td>
      <td class="mono">${formatLimits(provider)}</td>
      <td><span class="pill">${esc((provider.cache && provider.cache.mode) || 'none')}</span></td>
      <td class="mono">${fmtMs(provider.avg_latency_ms)}</td>
      <td class="mono">${esc(provider.last_error || '—')}</td>
    </tr>`);
    $('#health tbody').innerHTML = providerRows.length ? providerRows.join('') : emptyRow(9, 'No provider health data');

    const clientRows = (stats.clients || []).map(row => `<tr>
      <td><span class="pill">${esc(row.modality || 'chat')}</span></td>
      <td>${esc(row.client_profile || 'generic')}</td>
      <td>${esc(row.client_tag || '—')}</td>
      <td>${esc(row.provider)}</td>
      <td>${layerTag(row.layer)}</td>
      <td>${row.requests}</td>
      <td class="mono">${fmtUsd(row.cost_usd)}</td>
      <td class="mono">${fmtMs(row.avg_latency_ms)}</td>
    </tr>`);
    $('#clients tbody').innerHTML = clientRows.length ? clientRows.join('') : emptyRow(8, 'No client rows for the current filter set');

    const modalityRowsHtml = modalityRows.map(row => `<tr>
      <td><span class="pill">${esc(row.modality || 'chat')}</span></td>
      <td>${esc(row.provider)}</td>
      <td>${layerTag(row.layer)}</td>
      <td>${row.requests}</td>
      <td class="mono">${fmtUsd(row.cost_usd)}</td>
      <td class="mono">${fmtMs(row.avg_latency_ms)}</td>
    </tr>`);
    $('#modalities tbody').innerHTML = modalityRowsHtml.length ? modalityRowsHtml.join('') : emptyRow(6, 'No modality rows for the current filter set');

    const routingRows = (stats.routing || []).map(row => `<tr>
      <td>${layerTag(row.layer)}</td>
      <td class="mono">${esc(row.rule_name)}</td>
      <td>${esc(row.provider)}</td>
      <td>${row.requests}</td>
      <td class="mono">${fmtUsd(row.cost_usd)}</td>
      <td class="mono">${fmtMs(row.avg_latency_ms)}</td>
    </tr>`);
    $('#routing tbody').innerHTML = routingRows.length ? routingRows.join('') : emptyRow(6, 'No routing rows for the current filter set');

    const traceRows = (traces.traces || []).map(row => `<tr>
      <td class="mono">${ago(row.timestamp)}</td>
      <td>${esc(row.provider)}</td>
      <td>${esc(row.client_profile || 'generic')} <span class="pill">${esc(row.modality || 'chat')}</span></td>
      <td>${esc(row.client_tag || '—')}</td>
      <td>${layerTag(row.layer)}</td>
      <td class="mono">${esc(row.decision_reason || row.rule_name)}</td>
      <td class="mono">${fmt(row.confidence || 0, 2)}</td>
      <td class="mono">${esc((row.attempt_order || []).join(' -> ') || '—')}</td>
    </tr>`);
    $('#traces tbody').innerHTML = traceRows.length ? traceRows.join('') : emptyRow(8, 'No traces for the current filter set');

    const recentRows = (rec.requests || []).map(row => `<tr>
      <td class="mono">${ago(row.timestamp)}</td>
      <td>${esc(row.provider)}</td>
      <td>${layerTag(row.layer)} <span class="pill">${esc(row.modality || 'chat')}</span></td>
      <td class="mono">${esc(row.rule_name)}</td>
      <td class="mono">${fmtTok((row.prompt_tok||0)+(row.compl_tok||0))}</td>
      <td class="mono">${fmtUsd(row.cost_usd)}</td>
      <td class="mono">${fmtMs(row.latency_ms)}</td>
      <td>${row.success ? 'yes' : 'no'}</td>
    </tr>`);
    $('#recent tbody').innerHTML = recentRows.length ? recentRows.join('') : emptyRow(8, 'No recent requests for the current filter set');
  }catch(e){
    $('#status').style.background = '#f66';
    $('#filter-summary').textContent = 'Failed to load dashboard data';
    console.error(e);
  }
}
syncFiltersFromUrl();
load();
setInterval(load, 30000);
</script>
</body></html>"""
