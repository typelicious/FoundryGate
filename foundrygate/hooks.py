"""Optional request hook interfaces for pre-routing extensions."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RequestHookContext:
    """Mutable request context passed through the hook pipeline."""

    body: dict[str, Any]
    headers: dict[str, str]
    model_requested: str


@dataclass
class RequestHookResult:
    """One hook result with optional request and routing adjustments."""

    body_updates: dict[str, Any] = field(default_factory=dict)
    profile_override: str | None = None
    routing_hints: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


@dataclass
class AppliedHooks:
    """Aggregated hook state used by the runtime."""

    body: dict[str, Any]
    profile_override: str | None = None
    routing_hints: dict[str, Any] = field(default_factory=dict)
    applied_hooks: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


RequestHook = Callable[
    [RequestHookContext],
    RequestHookResult | Awaitable[RequestHookResult | None] | None,
]

_REQUEST_HOOKS: dict[str, RequestHook] = {}
_LIST_HINT_KEYS = {
    "allow_providers",
    "deny_providers",
    "prefer_providers",
    "prefer_tiers",
    "require_capabilities",
}


def register_request_hook(name: str, hook: RequestHook) -> None:
    """Register one named request hook."""
    _REQUEST_HOOKS[name] = hook


def get_registered_request_hooks() -> dict[str, RequestHook]:
    """Return the current hook registry."""
    return dict(_REQUEST_HOOKS)


async def apply_request_hooks(config: dict[str, Any], context: RequestHookContext) -> AppliedHooks:
    """Apply configured request hooks in order."""
    applied = AppliedHooks(body=dict(context.body))
    if not config.get("enabled"):
        return applied

    ctx = RequestHookContext(
        body=applied.body,
        headers=dict(context.headers),
        model_requested=context.model_requested,
    )

    for name in config.get("hooks", []):
        hook = _REQUEST_HOOKS.get(name)
        if hook is None:
            continue

        result = hook(ctx)
        if inspect.isawaitable(result):
            result = await result
        if not result:
            continue

        if result.body_updates:
            ctx.body.update(result.body_updates)
        if result.profile_override:
            applied.profile_override = result.profile_override.strip()
        if result.routing_hints:
            _merge_routing_hints(applied.routing_hints, result.routing_hints)
        if result.notes:
            applied.notes.extend(result.notes)

        applied.body = dict(ctx.body)
        applied.applied_hooks.append(name)

    return applied


def _merge_routing_hints(target: dict[str, Any], incoming: dict[str, Any]) -> None:
    """Merge hook-provided routing hints using config-like semantics."""
    for key in _LIST_HINT_KEYS:
        if key not in incoming:
            continue
        target.setdefault(key, [])
        for value in incoming[key]:
            if value not in target[key]:
                target[key].append(value)

    if "capability_values" in incoming:
        target.setdefault("capability_values", {})
        for capability, values in incoming["capability_values"].items():
            target["capability_values"].setdefault(capability, [])
            for value in values:
                if value not in target["capability_values"][capability]:
                    target["capability_values"][capability].append(value)


def _hook_prefer_provider_header(context: RequestHookContext) -> RequestHookResult | None:
    """Respect explicit provider preferences from a request header."""
    raw = context.headers.get("x-foundrygate-prefer-provider", "").strip()
    if not raw:
        return None

    providers = [part.strip() for part in raw.split(",") if part.strip()]
    if not providers:
        return None

    return RequestHookResult(
        routing_hints={"prefer_providers": providers},
        notes=[f"Preferred provider header requested: {', '.join(providers)}"],
    )


def _hook_locality_header(context: RequestHookContext) -> RequestHookResult | None:
    """Request a local-only or cloud-only route from one header."""
    raw = context.headers.get("x-foundrygate-locality", "").strip().lower()
    if raw not in {"local", "local-only", "cloud", "cloud-only"}:
        return None

    if raw in {"local", "local-only"}:
        return RequestHookResult(
            routing_hints={
                "prefer_tiers": ["local"],
                "capability_values": {"local": [True], "cloud": [False]},
            },
            notes=["Locality hook requested local providers only"],
        )

    return RequestHookResult(
        routing_hints={
            "capability_values": {"cloud": [True], "local": [False]},
        },
        notes=["Locality hook requested cloud providers only"],
    )


def _hook_profile_override_header(context: RequestHookContext) -> RequestHookResult | None:
    """Override the resolved client profile for one request."""
    raw = context.headers.get("x-foundrygate-profile", "").strip().lower()
    if not raw:
        return None

    return RequestHookResult(
        profile_override=raw,
        notes=[f"Profile override hook requested profile: {raw}"],
    )


register_request_hook("prefer-provider-header", _hook_prefer_provider_header)
register_request_hook("locality-header", _hook_locality_header)
register_request_hook("profile-override-header", _hook_profile_override_header)
