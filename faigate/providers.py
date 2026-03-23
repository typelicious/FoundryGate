"""Provider backends – unified async interface to LLM APIs."""

from __future__ import annotations

import logging
import re
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import httpx

from .lane_registry import get_provider_transport_binding

logger = logging.getLogger("faigate.providers")
_UNRESOLVED_ENV_RE = re.compile(r"\$\{[^}]+}")


@dataclass
class ProviderHealth:
    """Tracks health state for a single provider."""

    name: str
    healthy: bool = True
    consecutive_failures: int = 0
    last_check: float = 0.0
    last_error: str = ""
    avg_latency_ms: float = 0.0
    _latencies: list[float] = field(default_factory=list)

    def record_success(self, latency_ms: float) -> None:
        self.healthy = True
        self.consecutive_failures = 0
        self.last_check = time.time()
        self.last_error = ""
        self._latencies.append(latency_ms)
        if len(self._latencies) > 20:
            self._latencies = self._latencies[-20:]
        self.avg_latency_ms = sum(self._latencies) / len(self._latencies)

    def record_failure(self, error: str, max_failures: int = 3) -> None:
        self.consecutive_failures += 1
        self.last_check = time.time()
        self.last_error = error
        if self.consecutive_failures >= max_failures:
            self.healthy = False
            logger.warning(
                "Provider %s marked unhealthy after %d failures: %s",
                self.name,
                self.consecutive_failures,
                error,
            )

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "healthy": self.healthy,
            "consecutive_failures": self.consecutive_failures,
            "avg_latency_ms": round(self.avg_latency_ms, 1),
            "last_error": self.last_error,
        }


class ProviderBackend:
    """Calls an OpenAI-compatible or Google GenAI endpoint."""

    def __init__(self, name: str, cfg: dict):
        self.name = name
        self.contract = cfg.get("contract", "generic")
        self.backend_type = cfg.get("backend", "openai-compat")
        self.base_url = cfg["base_url"].rstrip("/")
        self.api_key = cfg.get("api_key", "")
        self.model = cfg["model"]
        self.max_tokens = cfg.get("max_tokens", 8000)
        self.tier = cfg.get("tier", "default")
        self.capabilities = dict(cfg.get("capabilities", {}))
        self.context_window = cfg.get("context_window")
        self.limits = dict(cfg.get("limits", {}))
        self.cache = dict(cfg.get("cache", {}))
        self.image = dict(cfg.get("image", {}))
        self.lane = dict(cfg.get("lane", {}))
        self.transport = {
            **get_provider_transport_binding(
                name,
                backend=self.backend_type,
                contract=self.contract,
            ),
            **dict(cfg.get("transport", {})),
        }
        self.health = ProviderHealth(name=name)
        self._last_probe_strategy = ""
        self._last_probe_payload = ""
        self._last_probe_verified = False

        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(120.0, connect=10.0),
            limits=httpx.Limits(max_connections=20),
        )

    async def close(self) -> None:
        await self._client.aclose()

    def _transport_path(self, key: str, default: str = "") -> str:
        value = str(self.transport.get(key, default) or default).strip()
        return value

    def _transport_url(self, path: str) -> str:
        cleaned = str(path or "").strip()
        if not cleaned:
            return self.base_url
        return f"{self.base_url}{cleaned}"

    def _authorization_headers(self, *, content_type: str | None = None) -> dict[str, str]:
        headers: dict[str, str] = {}
        auth_mode = str(self.transport.get("auth_mode", "bearer") or "bearer").strip().lower()
        if auth_mode == "bearer" and self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        if content_type:
            headers["Content-Type"] = content_type
        if "openrouter" in self.base_url:
            headers["HTTP-Referer"] = "https://faigate.local"
            headers["X-Title"] = "fusionAIze Gate"
        return headers

    def _classify_request_readiness_issue(self, detail: str) -> tuple[str, str]:
        lowered = str(detail or "").lower()
        if not lowered:
            return "degraded", "runtime reported an unspecified provider issue"
        if "quota" in lowered or "insufficient_quota" in lowered:
            return "quota-exhausted", "quota appears exhausted for this route"
        if "rate limit" in lowered or "429" in lowered:
            return "rate-limited", "rate-limit pressure is active on this route"
        if (
            "auth" in lowered
            or "unauthorized" in lowered
            or "forbidden" in lowered
            or "invalid api key" in lowered
            or "incorrect api key" in lowered
        ):
            return "auth-invalid", "authentication failed for this route"
        if "model" in lowered and ("unavailable" in lowered or "not found" in lowered):
            return "model-unavailable", "the configured model is not currently available"
        if "not found" in lowered or "unknown url" in lowered or "unsupported path" in lowered:
            return "endpoint-mismatch", "the configured endpoint path does not look compatible"
        if "timeout" in lowered:
            return "timeout", "upstream timed out recently"
        if "connection error" in lowered or "transport" in lowered:
            return "transport-error", "the route is reachable by config but not transport-ready"
        return "degraded", detail[:160]

    def _request_readiness_action(self, status: str) -> str:
        normalized = str(status or "").strip().lower()
        if normalized in {"ready", "ready-verified"}:
            return "route can carry live traffic"
        if normalized == "ready-compat":
            return "keep the route available, but revalidate it periodically"
        if normalized == "missing-key":
            return "add the missing API key before routing traffic here"
        if normalized == "unresolved-key":
            return "resolve the ${ENV_VAR} placeholder in the runtime environment"
        if normalized == "auth-invalid":
            return "rotate or fix the API key before retrying this route"
        if normalized == "endpoint-mismatch":
            return "review the configured base URL and transport paths for this route"
        if normalized == "model-unavailable":
            return "switch models or reroute within the same lane if possible"
        if normalized in {"quota-exhausted", "rate-limited"}:
            return "deprioritize this route until quota or rate pressure recovers"
        if normalized == "transport-error":
            return "treat this route as degraded until connectivity recovers"
        return "inspect the last route error before relying on this provider"

    def _probe_payload_preview(self) -> str:
        payload_kind = str(self.transport.get("probe_payload_kind", "default") or "default")
        payload_text = str(self.transport.get("probe_payload_text", "ping") or "ping")
        payload_max_tokens = int(self.transport.get("probe_payload_max_tokens", 1) or 1)
        text_preview = payload_text if len(payload_text) <= 24 else payload_text[:21] + "..."
        return (
            f"{payload_kind} | user='{text_preview}' | max_tokens={payload_max_tokens}"
        )

    def _mark_probe_success(self, strategy: str, latency_ms: float) -> None:
        self._last_probe_strategy = strategy
        self._last_probe_payload = self._probe_payload_preview()
        self._last_probe_verified = True
        self.health.record_success(latency_ms)

    def _mark_probe_failure(self, detail: str) -> None:
        self._last_probe_verified = False
        self.health.record_failure(detail)

    async def _probe_via_models(self, *, timeout_seconds: float) -> bool:
        url = self._transport_url(self._transport_path("models_path", "/models"))
        headers = self._authorization_headers()
        t0 = time.time()
        resp = await self._client.get(url, headers=headers, timeout=timeout_seconds)
        latency = (time.time() - t0) * 1000
        if resp.status_code >= 400:
            raise ProviderError(self.name, resp.status_code, resp.text[:500])
        self._mark_probe_success("models", latency)
        return True

    def _build_chat_probe_body(self) -> dict[str, Any]:
        probe_text = str(self.transport.get("probe_payload_text", "ping") or "ping")
        return {
            "model": self.model,
            "messages": [{"role": "user", "content": probe_text}],
            "max_tokens": int(self.transport.get("probe_payload_max_tokens", 1) or 1),
            "stream": False,
        }

    async def _probe_via_chat(self, *, timeout_seconds: float) -> bool:
        url = self._transport_url(self._transport_path("chat_path", "/chat/completions"))
        headers = self._authorization_headers(content_type="application/json")
        body = self._build_chat_probe_body()
        t0 = time.time()
        resp = await self._client.post(url, json=body, headers=headers, timeout=timeout_seconds)
        latency = (time.time() - t0) * 1000
        if resp.status_code >= 400:
            raise ProviderError(self.name, resp.status_code, resp.text[:500])
        self._mark_probe_success("chat", latency)
        return True

    def request_readiness(self) -> dict[str, Any]:
        """Return operator-facing request-readiness for one configured route."""
        requires_api_key = bool(self.transport.get("requires_api_key", True))
        probe_strategy = str(self.transport.get("probe_strategy", "models") or "models")
        probe_strategy = probe_strategy.replace("-", "_")
        compatibility = str(self.transport.get("compatibility", "native") or "native")
        profile = str(self.transport.get("profile", "") or "")
        probe_confidence = str(self.transport.get("probe_confidence", "medium") or "medium")
        notes = list(self.transport.get("notes", []) or [])
        verified_via = self._last_probe_strategy or ""
        probe_payload = self._last_probe_payload or self._probe_payload_preview()

        if requires_api_key and not self.api_key:
            status = "missing-key"
            return {
                "ready": False,
                "status": status,
                "reason": "provider is configured without an API key",
                "probe_strategy": probe_strategy,
                "compatibility": compatibility,
                "profile": profile,
                "probe_confidence": probe_confidence,
                "notes": notes,
                "probe_payload": probe_payload,
                "verified_via": verified_via,
                "operator_hint": self._request_readiness_action(status),
            }
        if requires_api_key and _UNRESOLVED_ENV_RE.search(self.api_key or ""):
            status = "unresolved-key"
            return {
                "ready": False,
                "status": status,
                "reason": "provider still carries an unresolved ${ENV_VAR} placeholder",
                "probe_strategy": probe_strategy,
                "compatibility": compatibility,
                "profile": profile,
                "probe_confidence": probe_confidence,
                "notes": notes,
                "probe_payload": probe_payload,
                "verified_via": verified_via,
                "operator_hint": self._request_readiness_action(status),
            }
        if self.health.last_error:
            status, reason = self._classify_request_readiness_issue(self.health.last_error)
            recovered = self.health.healthy and status == "degraded"
            final_status = "ready" if recovered else status
            return {
                "ready": recovered,
                "status": final_status,
                "reason": "route responded successfully" if recovered else reason,
                "probe_strategy": probe_strategy,
                "compatibility": compatibility,
                "profile": profile,
                "probe_confidence": probe_confidence,
                "notes": notes,
                "probe_payload": probe_payload,
                "verified_via": verified_via,
                "operator_hint": self._request_readiness_action(final_status),
            }
        if self._last_probe_verified:
            status = "ready-verified"
            return {
                "ready": True,
                "status": status,
                "reason": f"route passed a live {verified_via or probe_strategy} probe recently",
                "probe_strategy": probe_strategy,
                "compatibility": compatibility,
                "profile": profile,
                "probe_confidence": "high",
                "notes": notes,
                "probe_payload": probe_payload,
                "verified_via": verified_via or probe_strategy,
                "operator_hint": self._request_readiness_action(status),
            }
        if compatibility != "native" and probe_confidence != "high":
            status = "ready-compat"
            return {
                "ready": True,
                "status": status,
                "reason": (
                    "route looks request-ready, but this transport profile is still based on "
                    f"{probe_confidence}-confidence compatibility assumptions"
                ),
                "probe_strategy": probe_strategy,
                "compatibility": compatibility,
                "profile": profile,
                "probe_confidence": probe_confidence,
                "notes": notes,
                "probe_payload": probe_payload,
                "verified_via": verified_via,
                "operator_hint": self._request_readiness_action(status),
            }
        status = "ready"
        return {
            "ready": True,
            "status": status,
            "reason": "route looks request-ready from config and recent runtime state",
            "probe_strategy": probe_strategy,
            "compatibility": compatibility,
            "profile": profile,
            "probe_confidence": probe_confidence,
            "notes": notes,
            "probe_payload": probe_payload,
            "verified_via": verified_via,
            "operator_hint": self._request_readiness_action(status),
        }

    async def probe_health(self, timeout_seconds: float = 10.0) -> bool:
        """Probe a provider without sending a completion request.

        For OpenAI-compatible providers this uses GET /models. For Google GenAI,
        which does not expose a compatible models listing here, probing is skipped.
        """
        if self.backend_type == "google-genai":
            return self.health.healthy
        strategy = str(self.transport.get("probe_strategy", "models") or "models").strip().lower()
        strategy = strategy.replace("-", "_")
        if strategy == "none":
            return self.health.healthy
        try:
            if strategy == "chat":
                return await self._probe_via_chat(timeout_seconds=timeout_seconds)
            if strategy == "models_or_chat":
                try:
                    return await self._probe_via_models(timeout_seconds=timeout_seconds)
                except ProviderError as exc:
                    status, _reason = self._classify_request_readiness_issue(exc.detail)
                    if status not in {"endpoint-mismatch", "model-unavailable", "degraded"}:
                        raise
                    return await self._probe_via_chat(timeout_seconds=timeout_seconds)
            if not self.transport.get("supports_models_probe", True):
                return self.health.healthy
            return await self._probe_via_models(timeout_seconds=timeout_seconds)
        except ProviderError as e:
            self._mark_probe_failure(f"Probe HTTP {e.status}: {e.detail}")
            return False
        except httpx.TimeoutException as e:
            self._mark_probe_failure(f"Probe timeout: {e}")
            return False
        except httpx.ConnectError as e:
            self._mark_probe_failure(f"Probe connection error: {e}")
            return False

    async def generate_image(
        self,
        prompt: str,
        *,
        model_override: str | None = None,
        n: int = 1,
        size: str | None = None,
        quality: str | None = None,
        response_format: str | None = None,
        style: str | None = None,
        background: str | None = None,
        user: str | None = None,
        extra_body: dict[str, Any] | None = None,
    ) -> dict:
        """Send an OpenAI-compatible image generation request."""
        if self.backend_type != "openai-compat":
            raise ProviderError(
                self.name,
                0,
                f"Image generation is not implemented for backend '{self.backend_type}'",
            )

        model = model_override or self.model
        body: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "n": n,
        }
        if size:
            body["size"] = size
        if quality:
            body["quality"] = quality
        if response_format:
            body["response_format"] = response_format
        if style:
            body["style"] = style
        if background:
            body["background"] = background
        if user:
            body["user"] = user
        if extra_body:
            body.update(extra_body)

        headers = self._authorization_headers(content_type="application/json")
        url = self._transport_url(
            self._transport_path("image_generation_path", "/images/generations")
        )
        t0 = time.time()

        try:
            resp = await self._client.post(url, json=body, headers=headers)
            latency = (time.time() - t0) * 1000

            if resp.status_code >= 400:
                error_text = resp.text[:500]
                self.health.record_failure(f"HTTP {resp.status_code}: {error_text}")
                raise ProviderError(self.name, resp.status_code, error_text)

            self.health.record_success(latency)
            data = resp.json()
            data["_faigate"] = {
                "provider": self.name,
                "model": model,
                "latency_ms": round(latency, 1),
                "modality": "image_generation",
            }
            return data

        except httpx.TimeoutException as e:
            self.health.record_failure(f"Timeout: {e}")
            raise ProviderError(self.name, 0, f"Timeout: {e}") from e
        except httpx.ConnectError as e:
            self.health.record_failure(f"Connection error: {e}")
            raise ProviderError(self.name, 0, f"Connection error: {e}") from e

    async def edit_image(
        self,
        prompt: str,
        *,
        image: dict[str, Any],
        mask: dict[str, Any] | None = None,
        model_override: str | None = None,
        n: int = 1,
        size: str | None = None,
        response_format: str | None = None,
        user: str | None = None,
        extra_fields: dict[str, Any] | None = None,
    ) -> dict:
        """Send an OpenAI-compatible image editing request."""
        if self.backend_type != "openai-compat":
            raise ProviderError(
                self.name,
                0,
                f"Image editing is not implemented for backend '{self.backend_type}'",
            )

        model = model_override or self.model
        data: dict[str, str] = {
            "model": model,
            "prompt": prompt,
            "n": str(n),
        }
        if size:
            data["size"] = size
        if response_format:
            data["response_format"] = response_format
        if user:
            data["user"] = user
        if extra_fields:
            for key, value in extra_fields.items():
                if value is None:
                    continue
                data[key] = str(value)

        files = [
            (
                "image",
                (
                    image["filename"],
                    image["content"],
                    image.get("content_type") or "application/octet-stream",
                ),
            )
        ]
        if mask:
            files.append(
                (
                    "mask",
                    (
                        mask["filename"],
                        mask["content"],
                        mask.get("content_type") or "application/octet-stream",
                    ),
                )
            )

        headers = self._authorization_headers()
        url = self._transport_url(self._transport_path("image_edit_path", "/images/edits"))
        t0 = time.time()

        try:
            resp = await self._client.post(url, data=data, files=files, headers=headers)
            latency = (time.time() - t0) * 1000

            if resp.status_code >= 400:
                error_text = resp.text[:500]
                self.health.record_failure(f"HTTP {resp.status_code}: {error_text}")
                raise ProviderError(self.name, resp.status_code, error_text)

            self.health.record_success(latency)
            data = resp.json()
            data["_faigate"] = {
                "provider": self.name,
                "model": model,
                "latency_ms": round(latency, 1),
                "modality": "image_editing",
            }
            return data

        except httpx.TimeoutException as e:
            self.health.record_failure(f"Timeout: {e}")
            raise ProviderError(self.name, 0, f"Timeout: {e}") from e
        except httpx.ConnectError as e:
            self.health.record_failure(f"Connection error: {e}")
            raise ProviderError(self.name, 0, f"Connection error: {e}") from e

    # ── OpenAI-compatible completion ───────────────────────────

    async def complete(
        self,
        messages: list[dict],
        *,
        model_override: str | None = None,
        stream: bool = False,
        temperature: float | None = None,
        max_tokens: int | None = None,
        tools: list[dict] | None = None,
        extra_body: dict | None = None,
    ) -> dict | AsyncIterator[bytes]:
        """Send a chat completion request. Returns the full JSON response."""

        model = model_override or self.model
        t0 = time.time()

        if self.backend_type == "google-genai":
            return await self._complete_google(
                messages,
                model=model,
                stream=stream,
                temperature=temperature,
                max_tokens=max_tokens,
            )

        # OpenAI-compatible path (DeepSeek, OpenRouter, etc.)
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens or self.max_tokens,
        }
        if temperature is not None:
            body["temperature"] = temperature
        if tools:
            body["tools"] = tools
        if stream:
            body["stream"] = True
        if extra_body:
            body.update(extra_body)

        headers = self._authorization_headers(content_type="application/json")
        url = self._transport_url(self._transport_path("chat_path", "/chat/completions"))

        try:
            if stream:
                return self._stream_response(url, headers, body, t0)

            resp = await self._client.post(url, json=body, headers=headers)
            latency = (time.time() - t0) * 1000

            if resp.status_code >= 400:
                error_text = resp.text[:500]
                self.health.record_failure(f"HTTP {resp.status_code}: {error_text}")
                raise ProviderError(self.name, resp.status_code, error_text)

            self.health.record_success(latency)
            data = resp.json()

            # Extract cache metrics from DeepSeek/OpenAI responses
            usage = data.get("usage", {})
            cache_hit = usage.get("prompt_cache_hit_tokens", 0)
            cache_miss = usage.get("prompt_cache_miss_tokens", 0)

            # Tag the response with routing metadata
            data["_faigate"] = {
                "provider": self.name,
                "model": model,
                "latency_ms": round(latency, 1),
                "cache_hit_tokens": cache_hit,
                "cache_miss_tokens": cache_miss,
            }
            return data

        except httpx.TimeoutException as e:
            self.health.record_failure(f"Timeout: {e}")
            raise ProviderError(self.name, 0, f"Timeout: {e}") from e
        except httpx.ConnectError as e:
            self.health.record_failure(f"Connection error: {e}")
            raise ProviderError(self.name, 0, f"Connection error: {e}") from e

    async def _stream_response(
        self, url: str, headers: dict, body: dict, t0: float
    ) -> AsyncIterator[bytes]:
        """Yield SSE chunks for streaming responses."""
        async with self._client.stream("POST", url, json=body, headers=headers) as resp:
            if resp.status_code >= 400:
                error_text = await resp.aread()
                self.health.record_failure(f"HTTP {resp.status_code}")
                raise ProviderError(self.name, resp.status_code, error_text.decode()[:500])

            first_chunk = True
            async for line in resp.aiter_lines():
                if first_chunk:
                    self.health.record_success((time.time() - t0) * 1000)
                    first_chunk = False
                yield (line + "\n").encode()

    # ── Google GenAI path ──────────────────────────────────────

    async def _complete_google(
        self,
        messages: list[dict],
        model: str,
        stream: bool,
        temperature: float | None,
        max_tokens: int | None,
    ) -> dict:
        """Convert OpenAI format → Google GenAI format → back."""

        # Convert messages to Google format.
        # Google rejects payloads where parts[*].text is null/None, so we
        # coerce content=None (valid in OpenAI tool/assistant messages) → "".
        contents = []
        system_instruction = None
        for msg in messages:
            role = msg.get("role", "user")
            text = msg.get("content") or ""  # coerce None → ""
            if isinstance(text, list):
                # Multimodal content array → flatten to plain text for Gemini
                text = " ".join(part.get("text") or "" for part in text if isinstance(part, dict))
            if role == "system":
                system_instruction = text
            elif role == "assistant":
                contents.append({"role": "model", "parts": [{"text": text}]})
            else:
                contents.append({"role": "user", "parts": [{"text": text}]})

        body: dict[str, Any] = {"contents": contents}
        if system_instruction:
            body["systemInstruction"] = {"parts": [{"text": system_instruction}]}

        gen_config: dict[str, Any] = {}
        if max_tokens:
            gen_config["maxOutputTokens"] = max_tokens
        if temperature is not None:
            gen_config["temperature"] = temperature
        if gen_config:
            body["generationConfig"] = gen_config

        url = f"{self.base_url}/models/{model}:generateContent?key={self.api_key}"
        t0 = time.time()

        try:
            resp = await self._client.post(url, json=body)
            latency = (time.time() - t0) * 1000

            if resp.status_code >= 400:
                error_text = resp.text[:500]
                self.health.record_failure(f"HTTP {resp.status_code}: {error_text}")
                raise ProviderError(self.name, resp.status_code, error_text)

            self.health.record_success(latency)
            google_data = resp.json()

            # Convert Google response → OpenAI format
            return self._google_to_openai(google_data, model, latency)

        except httpx.TimeoutException as e:
            self.health.record_failure(f"Timeout: {e}")
            raise ProviderError(self.name, 0, f"Timeout: {e}") from e

    def _google_to_openai(self, data: dict, model: str, latency: float) -> dict:
        """Convert Google GenAI response to OpenAI chat completion format."""
        candidates = data.get("candidates", [{}])
        content = ""
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            content = "".join(p.get("text", "") for p in parts)

        usage_meta = data.get("usageMetadata", {})
        cached = usage_meta.get("cachedContentTokenCount", 0)

        return {
            "id": f"faigate-google-{int(time.time())}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": usage_meta.get("promptTokenCount", 0),
                "completion_tokens": usage_meta.get("candidatesTokenCount", 0),
                "total_tokens": usage_meta.get("totalTokenCount", 0),
            },
            "_faigate": {
                "provider": self.name,
                "model": model,
                "latency_ms": round(latency, 1),
                "cache_hit_tokens": cached,
                "cache_miss_tokens": max(0, usage_meta.get("promptTokenCount", 0) - cached),
            },
        }


class ProviderError(Exception):
    """Raised when a provider returns an error."""

    def __init__(self, provider: str, status: int, detail: str):
        self.provider = provider
        self.status = status
        self.detail = detail
        super().__init__(f"[{provider}] HTTP {status}: {detail}")
