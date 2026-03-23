"""Canonical model-lane and provider-route metadata for adaptive orchestration."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

_CANONICAL_MODEL_LANES: dict[str, dict[str, Any]] = {
    "anthropic/opus-4.6": {
        "family": "anthropic",
        "name": "quality",
        "cluster": "elite-reasoning",
        "benchmark_cluster": "quality-coding",
        "quality_tier": "premium",
        "reasoning_strength": "high",
        "context_strength": "high",
        "tool_strength": "medium",
        "preferred_degrades": ["anthropic/sonnet-4.6", "openai/gpt-4o", "deepseek/reasoner"],
        "last_reviewed": "2026-03-22",
    },
    "anthropic/sonnet-4.6": {
        "family": "anthropic",
        "name": "workhorse",
        "cluster": "quality-workhorse",
        "benchmark_cluster": "quality-coding",
        "quality_tier": "high",
        "reasoning_strength": "high",
        "context_strength": "high",
        "tool_strength": "medium",
        "preferred_degrades": ["openai/gpt-4o", "google/gemini-pro-high"],
        "last_reviewed": "2026-03-22",
    },
    "anthropic/haiku-4.5": {
        "family": "anthropic",
        "name": "fast",
        "cluster": "fast-workhorse",
        "benchmark_cluster": "fast-general",
        "quality_tier": "mid",
        "reasoning_strength": "mid",
        "context_strength": "mid",
        "tool_strength": "medium",
        "preferred_degrades": ["google/gemini-flash", "openai/gpt-4o-mini"],
        "last_reviewed": "2026-03-22",
    },
    "google/gemini-pro-high": {
        "family": "google",
        "name": "quality",
        "cluster": "quality-workhorse",
        "benchmark_cluster": "quality-coding",
        "quality_tier": "high",
        "reasoning_strength": "high",
        "context_strength": "high",
        "tool_strength": "medium",
        "preferred_degrades": ["google/gemini-pro-low", "google/gemini-flash"],
        "last_reviewed": "2026-03-22",
    },
    "google/gemini-pro-low": {
        "family": "google",
        "name": "balanced",
        "cluster": "balanced-workhorse",
        "benchmark_cluster": "balanced-coding",
        "quality_tier": "mid",
        "reasoning_strength": "mid",
        "context_strength": "high",
        "tool_strength": "medium",
        "preferred_degrades": ["google/gemini-flash", "deepseek/chat"],
        "last_reviewed": "2026-03-22",
    },
    "google/gemini-flash": {
        "family": "google",
        "name": "fast",
        "cluster": "fast-workhorse",
        "benchmark_cluster": "fast-general",
        "quality_tier": "mid",
        "reasoning_strength": "mid",
        "context_strength": "mid",
        "tool_strength": "medium",
        "preferred_degrades": ["google/gemini-flash-lite", "deepseek/chat"],
        "last_reviewed": "2026-03-22",
    },
    "google/gemini-flash-lite": {
        "family": "google",
        "name": "cheap",
        "cluster": "budget-general",
        "benchmark_cluster": "budget-chat",
        "quality_tier": "budget",
        "reasoning_strength": "low",
        "context_strength": "mid",
        "tool_strength": "low",
        "preferred_degrades": ["aggregator/kilo-glm5-free", "aggregator/blackbox-grok-code-fast"],
        "last_reviewed": "2026-03-22",
    },
    "openai/gpt-4o": {
        "family": "openai",
        "name": "balanced",
        "cluster": "quality-workhorse",
        "benchmark_cluster": "quality-coding",
        "quality_tier": "high",
        "reasoning_strength": "high",
        "context_strength": "high",
        "tool_strength": "high",
        "preferred_degrades": ["openai/gpt-4o-mini", "google/gemini-pro-high"],
        "last_reviewed": "2026-03-22",
    },
    "openai/gpt-4o-mini": {
        "family": "openai",
        "name": "fast",
        "cluster": "fast-workhorse",
        "benchmark_cluster": "fast-general",
        "quality_tier": "mid",
        "reasoning_strength": "mid",
        "context_strength": "mid",
        "tool_strength": "mid",
        "preferred_degrades": ["google/gemini-flash", "deepseek/chat"],
        "last_reviewed": "2026-03-22",
    },
    "openai/gpt-image-1": {
        "family": "openai",
        "name": "image",
        "cluster": "image-quality",
        "benchmark_cluster": "image-generation",
        "quality_tier": "premium",
        "reasoning_strength": "n/a",
        "context_strength": "n/a",
        "tool_strength": "n/a",
        "preferred_degrades": [],
        "last_reviewed": "2026-03-22",
    },
    "deepseek/reasoner": {
        "family": "deepseek",
        "name": "reasoning",
        "cluster": "elite-reasoning",
        "benchmark_cluster": "reasoning-coding",
        "quality_tier": "high",
        "reasoning_strength": "high",
        "context_strength": "mid",
        "tool_strength": "medium",
        "preferred_degrades": ["deepseek/chat", "google/gemini-pro-high"],
        "last_reviewed": "2026-03-22",
    },
    "deepseek/chat": {
        "family": "deepseek",
        "name": "workhorse",
        "cluster": "balanced-workhorse",
        "benchmark_cluster": "balanced-coding",
        "quality_tier": "mid",
        "reasoning_strength": "mid",
        "context_strength": "mid",
        "tool_strength": "medium",
        "preferred_degrades": ["google/gemini-flash", "aggregator/openrouter-auto"],
        "last_reviewed": "2026-03-22",
    },
    "aggregator/openrouter-auto": {
        "family": "openrouter",
        "name": "router",
        "cluster": "aggregator-fallback",
        "benchmark_cluster": "marketplace-general",
        "quality_tier": "variable",
        "reasoning_strength": "variable",
        "context_strength": "variable",
        "tool_strength": "variable",
        "preferred_degrades": ["aggregator/kilo-glm5-free", "aggregator/blackbox-grok-code-fast"],
        "last_reviewed": "2026-03-22",
    },
    "aggregator/kilo-glm5-free": {
        "family": "kilo",
        "name": "free",
        "cluster": "budget-general",
        "benchmark_cluster": "free-coding",
        "quality_tier": "free",
        "reasoning_strength": "mid",
        "context_strength": "mid",
        "tool_strength": "low",
        "preferred_degrades": ["aggregator/blackbox-grok-code-fast", "google/gemini-flash-lite"],
        "last_reviewed": "2026-03-22",
    },
    "aggregator/blackbox-grok-code-fast": {
        "family": "blackbox",
        "name": "free-burst",
        "cluster": "budget-general",
        "benchmark_cluster": "free-coding",
        "quality_tier": "free",
        "reasoning_strength": "mid",
        "context_strength": "mid",
        "tool_strength": "mid",
        "preferred_degrades": ["aggregator/kilo-glm5-free", "google/gemini-flash-lite"],
        "last_reviewed": "2026-03-22",
    },
}

_PROVIDER_LANE_BINDINGS: dict[str, dict[str, Any]] = {
    "anthropic-claude": {
        "family": "anthropic",
        "name": "quality",
        "canonical_model": "anthropic/opus-4.6",
        "route_type": "direct",
        "cluster": "elite-reasoning",
        "benchmark_cluster": "quality-coding",
        "quality_tier": "premium",
        "reasoning_strength": "high",
        "context_strength": "high",
        "tool_strength": "medium",
        "same_model_group": "anthropic/opus-4.6",
        "degrade_to": ["anthropic/sonnet-4.6", "openai/gpt-4o", "deepseek/reasoner"],
    },
    "deepseek-chat": {
        "family": "deepseek",
        "name": "workhorse",
        "canonical_model": "deepseek/chat",
        "route_type": "direct",
        "cluster": "balanced-workhorse",
        "benchmark_cluster": "balanced-coding",
        "quality_tier": "mid",
        "reasoning_strength": "mid",
        "context_strength": "mid",
        "tool_strength": "medium",
        "same_model_group": "deepseek/chat",
        "degrade_to": ["google/gemini-flash", "aggregator/openrouter-auto"],
    },
    "deepseek-reasoner": {
        "family": "deepseek",
        "name": "reasoning",
        "canonical_model": "deepseek/reasoner",
        "route_type": "direct",
        "cluster": "elite-reasoning",
        "benchmark_cluster": "reasoning-coding",
        "quality_tier": "high",
        "reasoning_strength": "high",
        "context_strength": "mid",
        "tool_strength": "medium",
        "same_model_group": "deepseek/reasoner",
        "degrade_to": ["deepseek/chat", "google/gemini-pro-high"],
    },
    "gemini-flash": {
        "family": "google",
        "name": "fast",
        "canonical_model": "google/gemini-flash",
        "route_type": "direct",
        "cluster": "fast-workhorse",
        "benchmark_cluster": "fast-general",
        "quality_tier": "mid",
        "reasoning_strength": "mid",
        "context_strength": "mid",
        "tool_strength": "medium",
        "same_model_group": "google/gemini-flash",
        "degrade_to": ["google/gemini-flash-lite", "deepseek/chat"],
    },
    "gemini-flash-lite": {
        "family": "google",
        "name": "cheap",
        "canonical_model": "google/gemini-flash-lite",
        "route_type": "direct",
        "cluster": "budget-general",
        "benchmark_cluster": "budget-chat",
        "quality_tier": "budget",
        "reasoning_strength": "low",
        "context_strength": "mid",
        "tool_strength": "low",
        "same_model_group": "google/gemini-flash-lite",
        "degrade_to": ["aggregator/kilo-glm5-free", "aggregator/blackbox-grok-code-fast"],
    },
    "openai-gpt4o": {
        "family": "openai",
        "name": "balanced",
        "canonical_model": "openai/gpt-4o",
        "route_type": "direct",
        "cluster": "quality-workhorse",
        "benchmark_cluster": "quality-coding",
        "quality_tier": "high",
        "reasoning_strength": "high",
        "context_strength": "high",
        "tool_strength": "high",
        "same_model_group": "openai/gpt-4o",
        "degrade_to": ["openai/gpt-4o-mini", "google/gemini-pro-high"],
    },
    "openai-images": {
        "family": "openai",
        "name": "image",
        "canonical_model": "openai/gpt-image-1",
        "route_type": "direct",
        "cluster": "image-quality",
        "benchmark_cluster": "image-generation",
        "quality_tier": "premium",
        "reasoning_strength": "n/a",
        "context_strength": "n/a",
        "tool_strength": "n/a",
        "same_model_group": "openai/gpt-image-1",
        "degrade_to": [],
    },
    "openrouter-fallback": {
        "family": "openrouter",
        "name": "router",
        "canonical_model": "aggregator/openrouter-auto",
        "route_type": "aggregator",
        "cluster": "aggregator-fallback",
        "benchmark_cluster": "marketplace-general",
        "quality_tier": "variable",
        "reasoning_strength": "variable",
        "context_strength": "variable",
        "tool_strength": "variable",
        "same_model_group": "aggregator/openrouter-auto",
        "degrade_to": ["aggregator/kilo-glm5-free", "aggregator/blackbox-grok-code-fast"],
    },
    "kilocode": {
        "family": "kilo",
        "name": "free",
        "canonical_model": "aggregator/kilo-glm5-free",
        "route_type": "aggregator",
        "cluster": "budget-general",
        "benchmark_cluster": "free-coding",
        "quality_tier": "free",
        "reasoning_strength": "mid",
        "context_strength": "mid",
        "tool_strength": "low",
        "same_model_group": "aggregator/kilo-glm5-free",
        "degrade_to": ["aggregator/blackbox-grok-code-fast", "google/gemini-flash-lite"],
    },
    "blackbox-free": {
        "family": "blackbox",
        "name": "free-burst",
        "canonical_model": "aggregator/blackbox-grok-code-fast",
        "route_type": "aggregator",
        "cluster": "budget-general",
        "benchmark_cluster": "free-coding",
        "quality_tier": "free",
        "reasoning_strength": "mid",
        "context_strength": "mid",
        "tool_strength": "mid",
        "same_model_group": "aggregator/blackbox-grok-code-fast",
        "degrade_to": ["aggregator/kilo-glm5-free", "google/gemini-flash-lite"],
    },
    "clawrouter": {
        "family": "blockrun",
        "name": "wallet-router",
        "canonical_model": "aggregator/openrouter-auto",
        "route_type": "wallet-router",
        "cluster": "aggregator-fallback",
        "benchmark_cluster": "marketplace-general",
        "quality_tier": "variable",
        "reasoning_strength": "variable",
        "context_strength": "variable",
        "tool_strength": "variable",
        "same_model_group": "aggregator/openrouter-auto",
        "degrade_to": ["aggregator/kilo-glm5-free", "aggregator/blackbox-grok-code-fast"],
    },
}

_DEFAULT_TRANSPORT_BY_BACKEND: dict[str, dict[str, Any]] = {
    "openai-compat": {
        "profile": "openai-compatible",
        "compatibility": "native",
        "probe_confidence": "high",
        "auth_mode": "bearer",
        "probe_strategy": "models",
        "probe_payload_kind": "openai-chat-minimal",
        "probe_payload_text": "ping",
        "probe_payload_max_tokens": 1,
        "models_path": "/models",
        "chat_path": "/chat/completions",
        "image_generation_path": "/images/generations",
        "image_edit_path": "/images/edits",
        "requires_api_key": True,
        "supports_models_probe": True,
        "notes": [],
    },
    "anthropic-compat": {
        "profile": "anthropic-compatible",
        "compatibility": "native",
        "probe_confidence": "high",
        "auth_mode": "bearer",
        "probe_strategy": "models",
        "probe_payload_kind": "anthropic-chat-minimal",
        "probe_payload_text": "ping",
        "probe_payload_max_tokens": 1,
        "models_path": "/models",
        "chat_path": "/chat/completions",
        "image_generation_path": "/images/generations",
        "image_edit_path": "/images/edits",
        "requires_api_key": True,
        "supports_models_probe": True,
        "notes": [],
    },
    "google-genai": {
        "profile": "google-genai",
        "compatibility": "native",
        "probe_confidence": "medium",
        "auth_mode": "query",
        "probe_strategy": "none",
        "probe_payload_kind": "google-generate-content",
        "probe_payload_text": "ping",
        "probe_payload_max_tokens": 1,
        "models_path": "",
        "chat_path": "",
        "image_generation_path": "",
        "image_edit_path": "",
        "requires_api_key": True,
        "supports_models_probe": False,
        "notes": ["genai backend uses generateContent instead of OpenAI-compatible chat paths"],
    },
}

_PROVIDER_TRANSPORT_BINDINGS: dict[str, dict[str, Any]] = {
    "openrouter-fallback": {
        "profile": "openrouter-openai-compat",
        "compatibility": "aggregator",
        "probe_confidence": "high",
        "auth_mode": "bearer",
        "probe_strategy": "models_or_chat",
        "probe_payload_kind": "openrouter-chat-minimal",
        "probe_payload_text": "ping",
        "probe_payload_max_tokens": 1,
        "models_path": "/models",
        "chat_path": "/chat/completions",
        "notes": [
            "requires HTTP-Referer and X-Title headers for best marketplace attribution",
            "route remains OpenAI-compatible but upstream model selection is marketplace-managed",
            "falls back to a shallow chat probe when the models route is not reliable enough",
        ],
    },
    "kilocode": {
        "profile": "kilo-openai-compat",
        "compatibility": "aggregator",
        "probe_confidence": "medium",
        "auth_mode": "bearer",
        "probe_strategy": "chat",
        "probe_payload_kind": "kilo-chat-minimal",
        "probe_payload_text": "ping",
        "probe_payload_max_tokens": 1,
        "models_path": "",
        "chat_path": "/chat/completions",
        "supports_models_probe": False,
        "notes": [
            "aggregator route uses a shallow chat probe instead of assuming /models support",
            "free-tier model availability and path behavior should be revalidated regularly",
        ],
    },
    "blackbox-free": {
        "profile": "blackbox-openai-compat",
        "compatibility": "aggregator",
        "probe_confidence": "medium",
        "auth_mode": "bearer",
        "probe_strategy": "chat",
        "probe_payload_kind": "blackbox-chat-minimal",
        "probe_payload_text": "ping",
        "probe_payload_max_tokens": 1,
        "models_path": "",
        "chat_path": "/chat/completions",
        "supports_models_probe": False,
        "notes": [
            "aggregator route uses a shallow chat probe instead of assuming /models support",
            "free-tier route volatility is high; auth and model availability can shift quickly",
        ],
    },
}

_CANONICAL_MODEL_ROUTE_REGISTRY: dict[str, list[dict[str, Any]]] = {
    "anthropic/opus-4.6": [
        {
            "route_id": "anthropic-direct/opus-4.6",
            "provider_name": "anthropic-claude",
            "provider_family": "anthropic",
            "route_type": "direct",
            "availability": "configured",
            "route_group": "same-lane",
        },
        {
            "route_id": "openrouter/anthropic-opus-4.6",
            "provider_name": "openrouter-anthropic-opus",
            "provider_family": "openrouter",
            "route_type": "aggregator",
            "availability": "catalog",
            "route_group": "same-lane",
        },
        {
            "route_id": "kilocode/anthropic-opus-4.6",
            "provider_name": "kilocode-anthropic-opus",
            "provider_family": "kilo",
            "route_type": "aggregator",
            "availability": "catalog",
            "route_group": "same-lane",
        },
        {
            "route_id": "blackbox/anthropic-opus-4.6",
            "provider_name": "blackbox-anthropic-opus",
            "provider_family": "blackbox",
            "route_type": "aggregator",
            "availability": "catalog",
            "route_group": "same-lane",
        },
    ],
    "openai/gpt-4o": [
        {
            "route_id": "openai-direct/gpt-4o",
            "provider_name": "openai-gpt4o",
            "provider_family": "openai",
            "route_type": "direct",
            "availability": "configured",
            "route_group": "same-lane",
        },
        {
            "route_id": "openrouter/openai-gpt-4o",
            "provider_name": "openrouter-openai-gpt4o",
            "provider_family": "openrouter",
            "route_type": "aggregator",
            "availability": "catalog",
            "route_group": "same-lane",
        },
    ],
    "deepseek/reasoner": [
        {
            "route_id": "deepseek-direct/reasoner",
            "provider_name": "deepseek-reasoner",
            "provider_family": "deepseek",
            "route_type": "direct",
            "availability": "configured",
            "route_group": "same-lane",
        },
        {
            "route_id": "openrouter/deepseek-reasoner",
            "provider_name": "openrouter-deepseek-reasoner",
            "provider_family": "openrouter",
            "route_type": "aggregator",
            "availability": "catalog",
            "route_group": "same-lane",
        },
    ],
    "deepseek/chat": [
        {
            "route_id": "deepseek-direct/chat",
            "provider_name": "deepseek-chat",
            "provider_family": "deepseek",
            "route_type": "direct",
            "availability": "configured",
            "route_group": "same-lane",
        },
        {
            "route_id": "openrouter/deepseek-chat",
            "provider_name": "openrouter-fallback",
            "provider_family": "openrouter",
            "route_type": "aggregator",
            "availability": "configured",
            "route_group": "same-lane",
        },
    ],
    "google/gemini-flash": [
        {
            "route_id": "google-direct/gemini-flash",
            "provider_name": "gemini-flash",
            "provider_family": "google",
            "route_type": "direct",
            "availability": "configured",
            "route_group": "same-lane",
        },
        {
            "route_id": "openrouter/gemini-flash",
            "provider_name": "openrouter-gemini-flash",
            "provider_family": "openrouter",
            "route_type": "aggregator",
            "availability": "catalog",
            "route_group": "same-lane",
        },
    ],
    "google/gemini-flash-lite": [
        {
            "route_id": "google-direct/gemini-flash-lite",
            "provider_name": "gemini-flash-lite",
            "provider_family": "google",
            "route_type": "direct",
            "availability": "configured",
            "route_group": "same-lane",
        },
        {
            "route_id": "kilocode/glm-5-free",
            "provider_name": "kilocode",
            "provider_family": "kilo",
            "route_type": "aggregator",
            "availability": "configured",
            "route_group": "cluster-alternative",
        },
        {
            "route_id": "blackbox/grok-code-fast",
            "provider_name": "blackbox-free",
            "provider_family": "blackbox",
            "route_type": "aggregator",
            "availability": "configured",
            "route_group": "cluster-alternative",
        },
    ],
}


def get_canonical_model_catalog() -> dict[str, dict[str, Any]]:
    """Return the canonical model-lane catalog."""
    return deepcopy(_CANONICAL_MODEL_LANES)


def get_provider_lane_binding(provider_name: str) -> dict[str, Any]:
    """Return lane metadata for one configured provider or route."""
    binding = _PROVIDER_LANE_BINDINGS.get(provider_name, {})
    return deepcopy(binding)


def get_provider_transport_binding(
    provider_name: str,
    *,
    backend: str = "openai-compat",
    contract: str = "generic",
) -> dict[str, Any]:
    """Return normalized transport defaults for one provider backend/route."""
    binding = deepcopy(_DEFAULT_TRANSPORT_BY_BACKEND.get(backend, {}))
    if contract == "local-worker":
        binding["requires_api_key"] = False
    binding.update(deepcopy(_PROVIDER_TRANSPORT_BINDINGS.get(provider_name, {})))
    return binding


def get_canonical_model_routes(canonical_model: str) -> list[dict[str, Any]]:
    """Return known direct and aggregator execution routes for one canonical model."""
    routes = _CANONICAL_MODEL_ROUTE_REGISTRY.get(canonical_model, [])
    return deepcopy(routes)


def _route_setup_provider_name(provider_name: str, provider_family: str) -> str:
    if provider_name in _PROVIDER_LANE_BINDINGS:
        return provider_name
    family = str(provider_family or "").strip().lower()
    if family == "openrouter":
        return "openrouter-fallback"
    if family == "kilo":
        return "kilocode"
    if family == "blackbox":
        return "blackbox-free"
    return provider_name


def get_route_add_recommendations(
    *,
    configured_provider_names: set[str] | list[str] | tuple[str, ...],
    canonical_model: str = "",
    degrade_to: list[str] | tuple[str, ...] | None = None,
    family: str = "",
) -> list[dict[str, Any]]:
    """Return concrete provider additions that would improve route resilience.

    Recommendations are ordered by usefulness:
    1. same-lane mirrors for the exact canonical model
    2. next-cluster providers from the configured degrade chain
    3. remaining family siblings that are known in the catalog
    """

    configured = {str(name) for name in configured_provider_names if str(name)}
    seen = set(configured)
    recommendations: list[dict[str, Any]] = []

    def add_route_candidates(target_model: str, strategy: str) -> None:
        for route in get_canonical_model_routes(target_model):
            provider_name = str(route.get("provider_name") or "")
            if not provider_name or provider_name in seen:
                continue
            if strategy == "same-lane-add":
                reason = f"adds a same-lane mirror for {target_model}"
            else:
                reason = f"adds a cluster fallback for {target_model}"
            recommendations.append(
                {
                    "provider_name": provider_name,
                    "setup_provider_name": _route_setup_provider_name(
                        provider_name,
                        str(route.get("provider_family") or ""),
                    ),
                    "strategy": strategy,
                    "strategy_label": {
                        "same-lane-add": "same lane",
                        "cluster-add": "next cluster lane",
                        "family-add": "family lane",
                    }.get(strategy, "route addition"),
                    "canonical_model": target_model,
                    "provider_family": str(route.get("provider_family") or ""),
                    "route_type": str(route.get("route_type") or ""),
                    "route_group": str(route.get("route_group") or ""),
                    "reason": reason,
                }
            )
            seen.add(provider_name)

    if canonical_model:
        add_route_candidates(canonical_model, "same-lane-add")

    for target_model in degrade_to or []:
        if str(target_model):
            add_route_candidates(str(target_model), "cluster-add")

    if family:
        for provider_name, binding in sorted(_PROVIDER_LANE_BINDINGS.items()):
            if provider_name in seen:
                continue
            if str(binding.get("family") or "") != family:
                continue
            recommendations.append(
                {
                    "provider_name": provider_name,
                    "setup_provider_name": provider_name,
                    "strategy": "family-add",
                    "strategy_label": "family lane",
                    "canonical_model": str(binding.get("canonical_model") or ""),
                    "provider_family": family,
                    "route_type": str(binding.get("route_type") or ""),
                    "route_group": "family-lane",
                    "reason": (
                        f"adds another {family} family lane for recovery and routing flexibility"
                    ),
                }
            )
            seen.add(provider_name)

    return recommendations
