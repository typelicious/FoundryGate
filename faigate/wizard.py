"""Initial configuration wizard helpers for local fusionAIze Gate installs."""

from __future__ import annotations

import asyncio
import os
import re
import shutil
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml
from dotenv import dotenv_values

from .lane_registry import (
    get_canonical_model_routes,
    get_provider_lane_binding,
    get_provider_transport_binding,
)
from .provider_catalog import get_provider_catalog
from .providers import ProviderBackend

ProviderFactory = dict[str, Any]


_PURPOSES = {"general", "coding", "quality", "free"}
_CLIENTS = {"generic", "openclaw", "n8n", "cli", "opencode"}

_LOCAL_WORKER_PRESETS: dict[str, dict[str, str]] = {
    "lmstudio": {
        "name": "LM Studio",
        "base_url": "http://127.0.0.1:1234/v1",
    },
    "ollama": {
        "name": "Ollama (OpenAI-compatible bridge)",
        "base_url": "http://127.0.0.1:11434/v1",
    },
    "custom": {
        "name": "Custom local worker",
        "base_url": "http://127.0.0.1:8080/v1",
    },
}

_CLIENT_SCENARIOS: dict[str, dict[str, str]] = {
    "opencode-eco": {
        "client": "opencode",
        "purpose": "coding",
        "routing_mode": "eco",
        "title": "opencode / eco",
        "summary": "Lower-cost coding path with cheaper defaults and fallback coverage.",
        "best_for": "High-volume coding and refactors where cost matters more than premium polish.",
        "tradeoff": "May route fewer tasks into the strongest reasoning paths.",
        "budget_posture": "save",
    },
    "opencode-balanced": {
        "client": "opencode",
        "purpose": "coding",
        "routing_mode": "auto",
        "title": "opencode / balanced",
        "summary": "Balanced coding path that keeps quality and cost in the middle.",
        "best_for": "Day-to-day coding where you want a stable default without over-optimizing.",
        "tradeoff": "Not the cheapest and not the strongest quality-first path either.",
        "budget_posture": "balanced",
    },
    "opencode-quality": {
        "client": "opencode",
        "purpose": "quality",
        "routing_mode": "premium",
        "title": "opencode / quality",
        "summary": "Higher-quality coding defaults for harder reasoning and review tasks.",
        "best_for": "Harder debugging, architecture work, and review-heavy coding sessions.",
        "tradeoff": "Usually slower and more expensive than eco or balanced.",
        "budget_posture": "invest",
    },
    "opencode-free": {
        "client": "opencode",
        "purpose": "free",
        "routing_mode": "free",
        "title": "opencode / free",
        "summary": "Free-tier-first coding path when zero-cost routing matters most.",
        "best_for": "Experiments and background coding where budget wins over consistency.",
        "tradeoff": "Free-tier availability can move quickly and reliability is less predictable.",
        "budget_posture": "free",
    },
    "openclaw-balanced": {
        "client": "openclaw",
        "purpose": "general",
        "routing_mode": "auto",
        "title": "openclaw / balanced",
        "summary": "Balanced delegated-agent traffic with stable defaults.",
        "best_for": "Default OpenClaw agent work when you want a safe everyday posture.",
        "tradeoff": "Not tuned for either ultra-low-cost or premium-heavy workflows.",
        "budget_posture": "balanced",
    },
    "openclaw-quality": {
        "client": "openclaw",
        "purpose": "quality",
        "routing_mode": "premium",
        "title": "openclaw / quality",
        "summary": "Quality-first path for heavier agent reasoning and review loops.",
        "best_for": "Longer reasoning loops and agent tasks where quality matters most.",
        "tradeoff": "More premium usage and higher latency are both more likely.",
        "budget_posture": "invest",
    },
    "n8n-eco": {
        "client": "n8n",
        "purpose": "free",
        "routing_mode": "eco",
        "title": "n8n / eco",
        "summary": "Automation-first path that keeps cost and churn low.",
        "best_for": "High-volume workflow automation where low unit cost matters most.",
        "tradeoff": "Can sacrifice some resilience and premium quality headroom.",
        "budget_posture": "save",
    },
    "n8n-reliable": {
        "client": "n8n",
        "purpose": "general",
        "routing_mode": "auto",
        "title": "n8n / reliable",
        "summary": "Balanced workflow routing with steadier fallbacks than the eco path.",
        "best_for": "Important automations where retries and fallback posture matter.",
        "tradeoff": "Usually a little more expensive than the eco path.",
        "budget_posture": "balanced",
    },
    "cli-balanced": {
        "client": "cli",
        "purpose": "general",
        "routing_mode": "auto",
        "title": "cli / balanced",
        "summary": "General shell and coding assistant path with balanced defaults.",
        "best_for": "Daily CLI work where you want one sensible default and fewer decisions.",
        "tradeoff": "Not specialized for ultra-cheap or premium-only work.",
        "budget_posture": "balanced",
    },
    "cli-free": {
        "client": "cli",
        "purpose": "free",
        "routing_mode": "free",
        "title": "cli / free",
        "summary": "Free-tier-first shell path for low-cost experimentation.",
        "best_for": "Lightweight experimentation and background CLI tasks.",
        "tradeoff": "Free providers can rotate, saturate, or disappear faster.",
        "budget_posture": "free",
    },
}

_PROVIDER_ROLE_TAXONOMY: dict[str, dict[str, str]] = {
    "anthropic-claude": {
        "family": "Anthropic",
        "slot": "quality",
        "role": "architecture / deep review",
    },
    "openai-gpt4o": {
        "family": "OpenAI",
        "slot": "balanced",
        "role": "general premium workhorse",
    },
    "deepseek-reasoner": {
        "family": "DeepSeek",
        "slot": "reasoning",
        "role": "hard reasoning / debugging",
    },
    "deepseek-chat": {
        "family": "DeepSeek",
        "slot": "balanced",
        "role": "day-to-day coding workhorse",
    },
    "gemini-flash": {
        "family": "Gemini",
        "slot": "balanced",
        "role": "fast general coding",
    },
    "gemini-flash-lite": {
        "family": "Gemini",
        "slot": "cheap",
        "role": "cheap burst traffic",
    },
    "kilocode": {
        "family": "Kilo",
        "slot": "free",
        "role": "free coding coverage",
    },
    "blackbox-free": {
        "family": "BLACKBOX",
        "slot": "free",
        "role": "free coding burst lane",
    },
    "openrouter-fallback": {
        "family": "OpenRouter",
        "slot": "fallback",
        "role": "marketplace safety net",
    },
}


_PROVIDER_FACTORIES: dict[str, ProviderFactory] = {
    "deepseek-chat": {
        "env": "DEEPSEEK_API_KEY",
        "base_url_env": "DEEPSEEK_BASE_URL",
        "provider": {
            "backend": "openai-compat",
            "base_url": "${DEEPSEEK_BASE_URL:-https://api.deepseek.com/v1}",
            "api_key": "${DEEPSEEK_API_KEY}",
            "model": "deepseek-chat",
            "max_tokens": 8000,
            "tier": "default",
            "timeout": {"connect_s": 10, "read_s": 60},
            "capabilities": {
                "streaming": True,
                "cost_tier": "standard",
                "latency_tier": "fast",
            },
        },
        "shortcut": {
            "description": "DeepSeek Chat",
            "aliases": ["chat", "ds"],
        },
    },
    "deepseek-reasoner": {
        "env": "DEEPSEEK_API_KEY",
        "base_url_env": "DEEPSEEK_BASE_URL",
        "provider": {
            "backend": "openai-compat",
            "base_url": "${DEEPSEEK_BASE_URL:-https://api.deepseek.com/v1}",
            "api_key": "${DEEPSEEK_API_KEY}",
            "model": "deepseek-reasoner",
            "max_tokens": 8000,
            "tier": "reasoning",
            "timeout": {"connect_s": 10, "read_s": 120},
            "capabilities": {
                "reasoning": True,
                "streaming": True,
                "cost_tier": "standard",
                "latency_tier": "balanced",
            },
        },
        "shortcut": {
            "description": "DeepSeek reasoning path",
            "aliases": ["reasoner", "r1", "think"],
        },
    },
    "gemini-flash-lite": {
        "env": "GEMINI_API_KEY",
        "base_url_env": "GEMINI_BASE_URL",
        "provider": {
            "backend": "google-genai",
            "base_url": "${GEMINI_BASE_URL:-https://generativelanguage.googleapis.com/v1beta}",
            "api_key": "${GEMINI_API_KEY}",
            "model": "gemini-2.5-flash-lite",
            "max_tokens": 8000,
            "tier": "cheap",
            "timeout": {"connect_s": 10, "read_s": 45},
            "capabilities": {
                "cost_tier": "cheap",
                "latency_tier": "fast",
            },
        },
        "shortcut": {
            "description": "Gemini Flash-Lite",
            "aliases": ["lite", "flash-lite"],
        },
    },
    "gemini-flash": {
        "env": "GEMINI_API_KEY",
        "base_url_env": "GEMINI_BASE_URL",
        "provider": {
            "backend": "google-genai",
            "base_url": "${GEMINI_BASE_URL:-https://generativelanguage.googleapis.com/v1beta}",
            "api_key": "${GEMINI_API_KEY}",
            "model": "gemini-2.5-flash",
            "max_tokens": 8000,
            "tier": "mid",
            "timeout": {"connect_s": 10, "read_s": 60},
            "capabilities": {
                "cost_tier": "cheap",
                "latency_tier": "fast",
            },
        },
        "shortcut": {
            "description": "Gemini Flash",
            "aliases": ["flash", "gemini"],
        },
    },
    "openrouter-fallback": {
        "env": "OPENROUTER_API_KEY",
        "base_url_env": "OPENROUTER_BASE_URL",
        "provider": {
            "backend": "openai-compat",
            "base_url": "${OPENROUTER_BASE_URL:-https://openrouter.ai/api/v1}",
            "api_key": "${OPENROUTER_API_KEY}",
            "model": "openrouter/auto",
            "max_tokens": 8000,
            "tier": "fallback",
            "timeout": {"connect_s": 10, "read_s": 90},
            "capabilities": {
                "streaming": True,
                "cost_tier": "marketplace",
                "latency_tier": "balanced",
            },
        },
    },
    "kilocode": {
        "env": "KILOCODE_API_KEY",
        "base_url_env": "KILOCODE_BASE_URL",
        "provider": {
            "backend": "openai-compat",
            "base_url": "${KILOCODE_BASE_URL:-https://api.kilo.ai/api/gateway/v1}",
            "api_key": "${KILOCODE_API_KEY}",
            "model": "z-ai/glm-5:free",
            "max_tokens": 8000,
            "tier": "fallback",
            "timeout": {"connect_s": 10, "read_s": 60},
            "capabilities": {
                "cost_tier": "free",
                "latency_tier": "balanced",
            },
        },
        "shortcut": {
            "description": "Kilo free-tier gateway path",
            "aliases": ["kilo", "glm5"],
        },
    },
    "blackbox-free": {
        "env": "BLACKBOX_API_KEY",
        "base_url_env": "BLACKBOX_BASE_URL",
        "provider": {
            "backend": "openai-compat",
            "base_url": "${BLACKBOX_BASE_URL:-https://api.blackbox.ai}",
            "api_key": "${BLACKBOX_API_KEY}",
            "model": "blackboxai/x-ai/grok-code-fast-1:free",
            "max_tokens": 8000,
            "tier": "fallback",
            "timeout": {"connect_s": 10, "read_s": 60},
            "capabilities": {
                "cost_tier": "free",
                "latency_tier": "fast",
            },
        },
        "shortcut": {
            "description": "BLACKBOX free-tier route",
            "aliases": ["blackbox", "bb"],
        },
    },
    "openai-gpt4o": {
        "env": "OPENAI_API_KEY",
        "base_url_env": "OPENAI_BASE_URL",
        "provider": {
            "backend": "openai-compat",
            "base_url": "${OPENAI_BASE_URL:-https://api.openai.com/v1}",
            "api_key": "${OPENAI_API_KEY}",
            "model": "gpt-4o",
            "max_tokens": 8192,
            "tier": "mid",
            "timeout": {"connect_s": 10, "read_s": 60},
            "capabilities": {
                "cost_tier": "premium",
                "latency_tier": "balanced",
            },
        },
        "shortcut": {
            "description": "OpenAI GPT-4o",
            "aliases": ["gpt4o", "gpt-4o"],
        },
    },
    "openai-images": {
        "env": "OPENAI_API_KEY",
        "base_url_env": "OPENAI_BASE_URL",
        "provider": {
            "contract": "image-provider",
            "backend": "openai-compat",
            "base_url": "${OPENAI_BASE_URL:-https://api.openai.com/v1}",
            "api_key": "${OPENAI_API_KEY}",
            "model": "gpt-image-1",
            "tier": "specialty",
            "capabilities": {
                "image_editing": True,
                "cost_tier": "premium",
            },
            "image": {
                "max_outputs": 4,
                "max_side_px": 2048,
                "supported_sizes": ["1024x1024", "1536x1024", "1024x1536"],
                "policy_tags": ["quality", "editing", "batch"],
            },
        },
        "shortcut": {
            "description": "OpenAI image generation and editing",
            "aliases": ["img", "image", "gpt-image"],
        },
    },
    "anthropic-claude": {
        "env": "ANTHROPIC_API_KEY",
        "base_url_env": "ANTHROPIC_BASE_URL",
        "provider": {
            "backend": "anthropic-compat",
            "base_url": "${ANTHROPIC_BASE_URL:-https://api.anthropic.com/v1}",
            "api_key": "${ANTHROPIC_API_KEY}",
            "model": "claude-opus-4-6",
            "max_tokens": 64000,
            "tier": "mid",
            "timeout": {"connect_s": 10, "read_s": 120},
            "capabilities": {
                "reasoning": True,
                "cost_tier": "premium",
                "latency_tier": "quality",
            },
        },
        "shortcut": {
            "description": "Anthropic Claude Opus",
            "aliases": ["opus", "claude", "br-sonnet"],
        },
    },
}


def _clone(value: Any) -> Any:
    return yaml.safe_load(yaml.safe_dump(value))


def _load_env_values(env_file: str | Path | None = None) -> dict[str, str]:
    """Return environment values from one env file, ignoring empty entries."""
    values = {
        key: value for key, value in os.environ.items() if isinstance(value, str) and value.strip()
    }
    path = Path(env_file) if env_file is not None else Path.cwd() / ".env"
    if path.exists():
        values.update(
            {k: v for k, v in dotenv_values(path).items() if isinstance(v, str) and v.strip()}
        )
    return values


def _load_existing_provider_names(config_path: str | Path | None = None) -> set[str]:
    if config_path is None:
        return set()
    path = Path(config_path)
    if not path.exists():
        return set()
    with path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    providers = raw.get("providers") or {}
    if not isinstance(providers, dict):
        return set()
    return set(providers.keys())


def _load_existing_provider_configs(
    config_path: str | Path | None = None,
) -> dict[str, dict[str, Any]]:
    if config_path is None:
        return {}
    path = Path(config_path)
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    providers = raw.get("providers") or {}
    if not isinstance(providers, dict):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for name, provider in providers.items():
        if isinstance(provider, dict):
            result[str(name)] = dict(provider)
    return result


def _extract_env_reference(value: str) -> str:
    stripped = value.strip()
    if stripped.startswith("${") and stripped.endswith("}"):
        return stripped[2:-1].split(":-", 1)[0].split(":", 1)[0]
    return ""


_ENV_REF_RE = re.compile(r"\$\{([^}]+)}")


def _expand_env_with_values(value: Any, env_values: dict[str, str]) -> Any:
    if isinstance(value, str):
        def _replace(match: re.Match[str]) -> str:
            token = match.group(1)
            if ":-" in token:
                name, default = token.split(":-", 1)
                return env_values.get(name, default)
            return env_values.get(token, match.group(0))

        return _ENV_REF_RE.sub(_replace, value)
    if isinstance(value, dict):
        return {key: _expand_env_with_values(val, env_values) for key, val in value.items()}
    if isinstance(value, list):
        return [_expand_env_with_values(item, env_values) for item in value]
    return value


async def _probe_providers_live(
    configured: dict[str, dict[str, Any]],
    *,
    env_values: dict[str, str],
    timeout_seconds: float,
) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    for name, provider in configured.items():
        runtime_cfg = _expand_env_with_values(deepcopy(provider), env_values)
        if not isinstance(runtime_cfg, dict):
            continue
        backend = ProviderBackend(name, runtime_cfg)
        try:
            ok = await backend.probe_health(timeout_seconds=timeout_seconds)
            results[name] = {
                "healthy": ok,
                "avg_latency_ms": backend.health.avg_latency_ms,
                "last_error": backend.health.last_error,
                "request_readiness": backend.request_readiness(),
            }
        finally:
            await backend.close()
    return results


def _load_existing_provider_models(config_path: str | Path | None = None) -> dict[str, str]:
    if config_path is None:
        return {}
    path = Path(config_path)
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    providers = raw.get("providers") or {}
    if not isinstance(providers, dict):
        return {}
    result: dict[str, str] = {}
    for name, provider in providers.items():
        if isinstance(provider, dict):
            result[str(name)] = str(provider.get("model", "") or "").strip()
    return result


def _load_existing_profile_modes(config_path: str | Path | None = None) -> dict[str, str]:
    if config_path is None:
        return {}
    path = Path(config_path)
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    client_profiles = raw.get("client_profiles") or {}
    if not isinstance(client_profiles, dict):
        return {}
    profiles = client_profiles.get("profiles") or {}
    if not isinstance(profiles, dict):
        return {}
    result: dict[str, str] = {}
    for name, profile in profiles.items():
        if isinstance(profile, dict) and profile.get("routing_mode"):
            result[str(name)] = str(profile.get("routing_mode"))
    return result


def _load_existing_config(config_path: str | Path) -> dict[str, Any]:
    path = Path(config_path)
    with path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    if not isinstance(raw, dict):
        raise ValueError("Existing config must be a YAML mapping")
    return raw


def detect_wizard_providers(*, env_file: str | Path | None = None) -> list[str]:
    """Return provider names that can be configured from the current env file."""
    env_values = _load_env_values(env_file)
    detected = []
    for name, spec in _PROVIDER_FACTORIES.items():
        if env_values.get(spec["env"]):
            detected.append(name)
    return detected


def _candidate_row(
    name: str,
    *,
    env_values: dict[str, str],
    existing: set[str],
    preferred: set[str],
    catalog: dict[str, Any],
) -> dict[str, Any]:
    factory = _PROVIDER_FACTORIES[name]
    provider = factory["provider"]
    catalog_entry = catalog.get(name, {})
    lane = dict(provider.get("lane") or get_provider_lane_binding(name))
    ready_now = bool(env_values.get(factory["env"]))
    already_configured = name in existing
    recommended_now = name in preferred
    return {
        "provider": name,
        "env": factory["env"],
        "configured": already_configured,
        "already_configured": already_configured,
        "ready_now": ready_now,
        "selected_by_default": recommended_now,
        "recommended_now": recommended_now,
        "model": provider.get("model", ""),
        "tier": provider.get("tier", "default"),
        "contract": provider.get("contract", "generic"),
        "provider_type": catalog_entry.get("provider_type", "direct"),
        "auth_modes": list(catalog_entry.get("auth_modes", ["api_key"])),
        "offer_track": catalog_entry.get("offer_track", "direct"),
        "volatility": catalog_entry.get("volatility", "low"),
        "evidence_level": catalog_entry.get("evidence_level", "official"),
        "official_source_url": catalog_entry.get("official_source_url", ""),
        "signup_url": (catalog_entry.get("discovery") or {}).get("signup_url", ""),
        "discovery_url": (catalog_entry.get("discovery") or {}).get("resolved_url", ""),
        "discovery_link_source": (
            (catalog_entry.get("discovery") or {}).get("link_source", "official")
        ),
        "discovery_disclosure": ((catalog_entry.get("discovery") or {}).get("disclosure", "")),
        "discovery_disclosure_required": bool(
            (catalog_entry.get("discovery") or {}).get("disclosure_required", False)
        ),
        "discovery_env_var": ((catalog_entry.get("discovery") or {}).get("operator_env_var", "")),
        "notes": catalog_entry.get("notes", ""),
        "canonical_model": lane.get("canonical_model", ""),
        "lane_family": lane.get("family", ""),
        "lane_name": lane.get("name", ""),
        "route_type": lane.get("route_type", ""),
        "lane_cluster": lane.get("cluster", ""),
    }


def build_interactive_candidate_sections(
    *,
    env_file: str | Path | None = None,
    purpose: str = "general",
    client: str = "generic",
    config_path: str | Path | None = None,
) -> dict[str, Any]:
    """Return compact candidate groups for interactive shell flows."""
    if purpose not in _PURPOSES:
        supported = ", ".join(sorted(_PURPOSES))
        raise ValueError(f"Unsupported purpose '{purpose}'. Choose one of: {supported}")
    if client not in _CLIENTS:
        supported = ", ".join(sorted(_CLIENTS))
        raise ValueError(f"Unsupported client '{client}'. Choose one of: {supported}")

    env_values = _load_env_values(env_file)
    catalog = get_provider_catalog()
    existing = _load_existing_provider_names(config_path)
    detected = detect_wizard_providers(env_file=env_file)
    preferred_all = _preferred_provider_set(
        list(_PROVIDER_FACTORIES),
        purpose=purpose,
        client=client,
    )
    preferred_set = set(preferred_all)

    ready_now: list[dict[str, Any]] = []
    available_with_key: list[dict[str, Any]] = []
    optional_add_ons: list[dict[str, Any]] = []

    for name in preferred_all:
        row = _candidate_row(
            name,
            env_values=env_values,
            existing=existing,
            preferred=preferred_set,
            catalog=catalog,
        )
        if row["contract"] != "generic":
            optional_add_ons.append(row)
        elif row["ready_now"]:
            ready_now.append(row)
        else:
            available_with_key.append(row)

    seen = set(preferred_all)
    extra_ready = [
        _candidate_row(
            name,
            env_values=env_values,
            existing=existing,
            preferred=preferred_set,
            catalog=catalog,
        )
        for name in detected
        if name not in seen
        and _PROVIDER_FACTORIES[name]["provider"].get("contract", "generic") == "generic"
    ]
    extra_ready.sort(key=lambda row: row["provider"])
    ready_now.extend(extra_ready)

    return {
        "purpose": purpose,
        "client": client,
        "ready_now": ready_now,
        "available_with_key": available_with_key,
        "optional_add_ons": optional_add_ons,
    }


def render_candidate_cards_text(
    *,
    env_file: str | Path | None = None,
    purpose: str = "general",
    client: str = "generic",
    config_path: str | Path | None = None,
) -> str:
    """Render a compact operator-friendly candidate view."""
    sections = build_interactive_candidate_sections(
        env_file=env_file,
        purpose=purpose,
        client=client,
        config_path=config_path,
    )
    lines = [
        f"purpose: {sections['purpose']}",
        f"client: {sections['client']}",
        "",
    ]

    ready_now = sections["ready_now"]
    if ready_now:
        lines.append("Ready now")
        for row in ready_now:
            badges = ["recommended"]
            if row["already_configured"]:
                badges.append("already in config")
            lines.append(f"- {row['provider']}  ({' · '.join(badges)})")
            lines.append(
                "  "
                + f"model: {row['model']} | tier: {row['tier']} | source: {row['provider_type']}"
            )
            if row["canonical_model"]:
                lines.append(
                    "  "
                    + "lane: "
                    + f"{row['canonical_model']} | route: {row['route_type'] or 'n/a'}"
                    + (f" | cluster: {row['lane_cluster']}" if row["lane_cluster"] else "")
                )
            if row["notes"]:
                lines.append("  " + f"why: {row['notes']}")
        lines.append("")
    else:
        lines.extend(
            [
                "Ready now",
                "- none yet",
                "  why: no recommended providers are currently backed by a detected API key.",
                "",
            ]
        )

    available_with_key = sections["available_with_key"]
    if available_with_key:
        lines.append("More options if you add keys")
        for row in available_with_key:
            lines.append(f"- {row['provider']}  (needs {row['env']})")
            lines.append(
                "  "
                + f"model: {row['model']} | tier: {row['tier']} | source: {row['provider_type']}"
            )
            if row["canonical_model"]:
                lines.append(
                    "  "
                    + "lane: "
                    + f"{row['canonical_model']} | route: {row['route_type'] or 'n/a'}"
                    + (f" | cluster: {row['lane_cluster']}" if row["lane_cluster"] else "")
                )
            if row["notes"]:
                lines.append("  " + f"why: {row['notes']}")
        lines.append("")

    optional_add_ons = sections["optional_add_ons"]
    if optional_add_ons:
        lines.append("Optional specialty add-ons")
        for row in optional_add_ons:
            availability = "ready now" if row["ready_now"] else f"needs {row['env']}"
            lines.append(f"- {row['provider']}  ({availability})")
            lines.append("  " + f"model: {row['model']} | tier: {row['tier']}")
            if row["canonical_model"]:
                lines.append(
                    "  "
                    + "lane: "
                    + f"{row['canonical_model']} | route: {row['route_type'] or 'n/a'}"
                    + (f" | cluster: {row['lane_cluster']}" if row["lane_cluster"] else "")
                )
            if row["notes"]:
                lines.append("  " + f"why: {row['notes']}")
        lines.append("")

    lines.append("Tip: Press Enter in the wizard to use the recommended ready providers.")
    lines.append(
        "Tip: Use --json or --yaml with --list-candidates when you want the full metadata dump."
    )
    return "\n".join(lines) + "\n"


def list_known_provider_sources(
    *,
    env_file: str | Path | None = None,
    config_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Return one compact setup-oriented view over known provider sources."""
    env_values = _load_env_values(env_file)
    catalog = get_provider_catalog()
    configured = _load_existing_provider_configs(config_path)
    rows: list[dict[str, Any]] = []
    for name, factory in _PROVIDER_FACTORIES.items():
        provider = factory["provider"]
        catalog_entry = catalog.get(name, {})
        env_key = str(factory["env"])
        base_url_env = str(factory.get("base_url_env", "") or "")
        rows.append(
            {
                "provider": name,
                "env": env_key,
                "base_url_env": base_url_env,
                "key_present": bool(env_values.get(env_key)),
                "configured": name in configured,
                "contract": provider.get("contract", "generic"),
                "provider_type": catalog_entry.get("provider_type", "direct"),
                "offer_track": catalog_entry.get("offer_track", "direct"),
                "model": provider.get("model", ""),
                "tier": provider.get("tier", "default"),
                "notes": catalog_entry.get("notes", ""),
                "signup_url": (catalog_entry.get("discovery") or {}).get("resolved_url", ""),
            }
        )
    return rows


def render_known_provider_sources_text(
    *,
    env_file: str | Path | None = None,
    config_path: str | Path | None = None,
) -> str:
    rows = list_known_provider_sources(env_file=env_file, config_path=config_path)
    lines = [
        "Known providers",
        "",
    ]
    for row in rows:
        status_bits = []
        status_bits.append("key ready" if row["key_present"] else f"needs {row['env']}")
        if row["configured"]:
            status_bits.append("already in config")
        lines.append(f"- {row['provider']}  ({' · '.join(status_bits)})")
        lines.append(
            "  " + f"model: {row['model']} | tier: {row['tier']} | source: {row['provider_type']}"
        )
        if row["notes"]:
            lines.append("  " + f"why: {row['notes']}")
    lines.append("")
    lines.append("Tip: Select one or more provider IDs in Provider Setup to add or update them.")
    return "\n".join(lines) + "\n"


def render_current_provider_sources_text(
    *,
    env_file: str | Path | None = None,
    config_path: str | Path | None = None,
) -> str:
    env_values = _load_env_values(env_file)
    configured = _load_existing_provider_configs(config_path)
    if not configured:
        return (
            "Current provider sources\n\n"
            "- none yet\n"
            "  why: config.yaml does not contain any provider blocks yet.\n"
        )

    lines = ["Current provider sources", ""]
    for name in sorted(configured):
        provider = configured[name]
        api_key = str(provider.get("api_key", "") or "").strip()
        env_name = ""
        match = None
        if api_key.startswith("${") and api_key.endswith("}"):
            match = api_key[2:-1].split(":-", 1)[0].split(":", 1)[0]
        if match:
            env_name = match
        status = (
            "ready"
            if (env_name and env_values.get(env_name)) or (api_key and not env_name)
            else "missing key"
        )
        contract = str(provider.get("contract", "generic") or "generic")
        tier = str(provider.get("tier", "default") or "default")
        lines.append(f"- {name}  ({status} · {contract})")
        lines.append(
            "  "
            + "model: "
            + f"{provider.get('model', '')} | tier: {tier} | base_url: "
            + f"{provider.get('base_url', '')}"
        )
    return "\n".join(lines) + "\n"


def apply_provider_setup(
    *,
    config_path: str | Path | None,
    env_file: str | Path | None,
    known_providers: list[dict[str, Any]] | None = None,
    custom_provider: dict[str, Any] | None = None,
    local_worker: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Apply one provider-setup mutation to config and env payloads."""
    if config_path is None:
        raise ValueError("config_path is required")

    existing_config = (
        _load_existing_config(config_path) if Path(config_path).exists() else {"providers": {}}
    )
    providers = dict(existing_config.get("providers") or {})
    env_updates: dict[str, str] = {}
    added_providers: list[str] = []
    updated_env_vars: list[str] = []

    def track_env_var(name: str, value: str) -> None:
        env_updates[name] = value
        updated_env_vars.append(name)

    for provider_item in known_providers or []:
        provider_name = str(provider_item["provider"])
        if provider_name not in _PROVIDER_FACTORIES:
            raise ValueError(f"Unsupported known provider '{provider_name}'")
        factory = _PROVIDER_FACTORIES[provider_name]
        providers[provider_name] = _provider_payload_with_lane(provider_name)
        added_providers.append(provider_name)
        key_value = str(provider_item.get("env_value", "") or "")
        if key_value:
            track_env_var(str(factory["env"]), key_value)
        base_url_env = str(factory.get("base_url_env", "") or "")
        base_url_value = str(provider_item.get("base_url_value", "") or "")
        if base_url_env and base_url_value:
            track_env_var(base_url_env, base_url_value)

    if custom_provider:
        name = str(custom_provider["name"])
        api_env = str(custom_provider["api_env"])
        provider_payload = {
            "backend": "openai-compat",
            "base_url": f"${{{custom_provider['base_url_env']}}}",
            "api_key": f"${{{api_env}}}",
            "model": str(custom_provider["model"]),
            "max_tokens": int(custom_provider.get("max_tokens", 8000)),
            "tier": str(custom_provider.get("tier", "default") or "default"),
            "timeout": {"connect_s": 10, "read_s": 90},
            "capabilities": {
                "cost_tier": str(custom_provider.get("cost_tier", "custom") or "custom"),
                "latency_tier": str(custom_provider.get("latency_tier", "balanced") or "balanced"),
            },
            "lane": {
                "family": str(custom_provider.get("family", "custom") or "custom"),
                "name": str(custom_provider.get("lane_name", "custom") or "custom"),
                "canonical_model": str(custom_provider.get("canonical_model", name) or name),
                "route_type": "direct",
                "cluster": str(custom_provider.get("cluster", "custom") or "custom"),
                "benchmark_cluster": str(
                    custom_provider.get("benchmark_cluster", "custom") or "custom"
                ),
                "quality_tier": str(custom_provider.get("quality_tier", "custom") or "custom"),
                "reasoning_strength": str(
                    custom_provider.get("reasoning_strength", "custom") or "custom"
                ),
                "context_strength": str(
                    custom_provider.get("context_strength", "custom") or "custom"
                ),
                "tool_strength": str(custom_provider.get("tool_strength", "custom") or "custom"),
                "same_model_group": str(custom_provider.get("same_model_group", name) or name),
                "degrade_to": list(custom_provider.get("degrade_to", []) or []),
            },
        }
        providers[name] = provider_payload
        added_providers.append(name)
        track_env_var(str(custom_provider["base_url_env"]), str(custom_provider["base_url"]))
        track_env_var(api_env, str(custom_provider.get("api_key_value", "") or ""))

    if local_worker:
        name = str(local_worker["name"])
        provider_payload = {
            "contract": "local-worker",
            "backend": "openai-compat",
            "base_url": str(local_worker["base_url"]),
            "model": str(local_worker["model"]),
            "max_tokens": int(local_worker.get("max_tokens", 8000)),
            "tier": "local",
            "timeout": {"connect_s": 5, "read_s": 120},
            "capabilities": {
                "chat": True,
                "streaming": True,
                "local": True,
                "cloud": False,
                "network_zone": "local",
                "cost_tier": "local",
                "latency_tier": "local",
            },
            "lane": {
                "family": "local",
                "name": "local",
                "canonical_model": str(local_worker.get("canonical_model", name) or name),
                "route_type": "local",
                "cluster": "local-worker",
                "benchmark_cluster": "local-worker",
                "quality_tier": "local",
                "reasoning_strength": str(
                    local_worker.get("reasoning_strength", "custom") or "custom"
                ),
                "context_strength": str(local_worker.get("context_strength", "custom") or "custom"),
                "tool_strength": str(local_worker.get("tool_strength", "custom") or "custom"),
                "same_model_group": str(local_worker.get("same_model_group", name) or name),
                "degrade_to": list(local_worker.get("degrade_to", []) or []),
            },
        }
        api_env = str(local_worker.get("api_env", "") or "")
        if api_env:
            provider_payload["api_key"] = f"${{{api_env}}}"
            track_env_var(api_env, str(local_worker.get("api_key_value", "") or ""))
        providers[name] = provider_payload
        added_providers.append(name)

    existing_config["providers"] = providers
    if "fallback_chain" not in existing_config:
        existing_config["fallback_chain"] = []

    return {
        "config": existing_config,
        "env_updates": env_updates,
        "added_providers": added_providers,
        "updated_env_vars": _unique_preserve_order(updated_env_vars),
    }


def render_provider_setup_summary(payload: dict[str, Any]) -> str:
    lines = ["Provider setup summary", ""]
    added = list(payload.get("added_providers", []) or [])
    if added:
        lines.append("Providers to add/update")
        for name in added:
            lines.append(f"- {name}")
        lines.append("")
    env_updates = dict(payload.get("env_updates", {}) or {})
    if env_updates:
        lines.append("Env updates")
        for key, value in env_updates.items():
            status = "set" if value else "left blank"
            lines.append(f"- {key}  ({status})")
        lines.append("")
    provider_count = len((payload.get("config") or {}).get("providers") or {})
    lines.append(f"Resulting configured providers: {provider_count}")
    return "\n".join(lines) + "\n"


def render_provider_setup_yaml(payload: dict[str, Any]) -> str:
    return yaml.safe_dump(payload.get("config") or {}, sort_keys=False, allow_unicode=False)


def write_env_updates(
    *,
    env_path: str | Path,
    env_updates: dict[str, str],
) -> dict[str, Any]:
    path = Path(env_path)
    existing_lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    preserved: list[str] = []
    remaining = dict(env_updates)
    for line in existing_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            preserved.append(line)
            continue
        key = line.split("=", 1)[0].strip()
        if key in remaining:
            preserved.append(f"{key}={remaining.pop(key)}")
        else:
            preserved.append(line)
    for key, value in remaining.items():
        preserved.append(f"{key}={value}")
    payload = "\n".join(preserved).rstrip() + "\n"
    path.write_text(payload, encoding="utf-8")
    return {"output_path": str(path), "updated_keys": sorted(env_updates)}


def build_provider_probe_report(
    *,
    config_path: str | Path | None = None,
    env_file: str | Path | None = None,
    health_payload: dict[str, Any] | None = None,
    live_probe: bool = False,
    timeout_seconds: float = 2.0,
) -> dict[str, Any]:
    configured = _load_existing_provider_configs(config_path)
    env_values = _load_env_values(env_file)
    provider_health = ((health_payload or {}).get("providers")) or {}
    if live_probe and configured:
        provider_health = {
            **provider_health,
            **asyncio.run(
                _probe_providers_live(
                    configured,
                    env_values=env_values,
                    timeout_seconds=timeout_seconds,
                )
            ),
        }
    rows: list[dict[str, Any]] = []
    ready_count = 0
    action_counts = {
        "fix-now": 0,
        "hold": 0,
        "watch": 0,
        "route": 0,
        "inspect": 0,
    }

    for name, provider in sorted(configured.items()):
        transport_defaults = get_provider_transport_binding(
            name,
            backend=str(provider.get("backend", "openai-compat") or "openai-compat"),
            contract=str(provider.get("contract", "generic") or "generic"),
        )
        lane_binding = get_provider_lane_binding(name)
        api_key = str(provider.get("api_key", "") or "").strip()
        env_name = _extract_env_reference(api_key)
        missing_key = bool(env_name) and not bool(env_values.get(env_name))
        health = provider_health.get(name) or {}
        healthy = bool(health.get("healthy"))
        last_error = str(health.get("last_error", "") or "").strip()
        request_readiness = health.get("request_readiness") or {}
        contract = str(provider.get("contract", "generic") or "generic")
        if missing_key:
            status = "missing-key"
            status_reason = f"needs {env_name}"
        elif request_readiness and not bool(request_readiness.get("ready")):
            status = str(request_readiness.get("status") or "unhealthy")
            status_reason = str(request_readiness.get("reason") or "route is not request-ready")
        elif request_readiness and bool(request_readiness.get("ready")):
            status = str(request_readiness.get("status") or "ready")
            status_reason = str(
                request_readiness.get("reason") or "route looks request-ready from runtime state"
            )
            ready_count += 1
        elif health_payload is None:
            status = "configured"
            status_reason = "health endpoint unavailable; config and env look present"
        elif healthy:
            status = "ready"
            status_reason = "responding through /health"
            ready_count += 1
        elif contract == "local-worker":
            status = "unhealthy"
            status_reason = last_error or "local worker configured but not healthy yet"
        else:
            lowered = last_error.lower()
            if "quota" in lowered or "insufficient_quota" in lowered:
                status = "quota-exhausted"
            elif "rate limit" in lowered or "429" in lowered:
                status = "rate-limited"
            elif "model" in lowered and ("unavailable" in lowered or "not found" in lowered):
                status = "model-unavailable"
            elif last_error:
                status = "unhealthy"
            else:
                status = "configured"
            status_reason = last_error or "configured but not reporting healthy yet"
        runtime_window_state = str(request_readiness.get("runtime_window_state") or "clear")
        runtime_cooldown_active = bool(request_readiness.get("runtime_cooldown_active"))
        runtime_recovered_recently = bool(request_readiness.get("runtime_recovered_recently"))
        action_group = _classify_probe_action(
            status=status,
            missing_key=missing_key,
            ready=bool(request_readiness.get("ready")),
            runtime_window_state=runtime_window_state,
            runtime_cooldown_active=runtime_cooldown_active,
            runtime_recovered_recently=runtime_recovered_recently,
        )
        action_counts[action_group] += 1
        operator_hint = str(request_readiness.get("operator_hint") or "")
        next_action = operator_hint or _default_probe_action_hint(
            action_group=action_group,
            provider_name=name,
            family=str(
                (provider.get("lane") or {}).get("family")
                or lane_binding.get("family")
                or ""
            ),
        )
        lane = dict(provider.get("lane") or lane_binding or {})
        rows.append(
            {
                "provider": name,
                "status": status,
                "reason": status_reason,
                "contract": contract,
                "tier": str(provider.get("tier", "default") or "default"),
                "model": str(provider.get("model", "") or ""),
                "base_url": str(provider.get("base_url", "") or ""),
                "env": env_name,
                "healthy": healthy,
                "avg_latency_ms": float(health.get("avg_latency_ms", 0.0) or 0.0),
                "canonical_model": str(lane.get("canonical_model") or ""),
                "lane_family": str(
                    lane.get("family") or ""
                ),
                "lane_cluster": str(lane.get("cluster") or ""),
                "degrade_to": [str(item) for item in (lane.get("degrade_to") or []) if str(item)],
                "transport_profile": str(
                    request_readiness.get("profile")
                    or (provider.get("transport") or {}).get("profile")
                    or transport_defaults.get("profile")
                    or ""
                ),
                "transport_compatibility": str(
                    request_readiness.get("compatibility")
                    or (provider.get("transport") or {}).get("compatibility")
                    or transport_defaults.get("compatibility")
                    or ""
                ),
                "transport_confidence": str(
                    request_readiness.get("probe_confidence")
                    or (provider.get("transport") or {}).get("probe_confidence")
                    or transport_defaults.get("probe_confidence")
                    or ""
                ),
                "probe_strategy": str(
                    request_readiness.get("probe_strategy")
                    or (provider.get("transport") or {}).get("probe_strategy")
                    or transport_defaults.get("probe_strategy")
                    or ""
                ),
                "probe_payload": str(request_readiness.get("probe_payload") or ""),
                "verified_via": str(request_readiness.get("verified_via") or ""),
                "operator_hint": operator_hint,
                "action_group": action_group,
                "next_action": next_action,
            }
        )

    recommendation_counts = {
        "same-lane-route": 0,
        "cluster-degrade": 0,
        "family-route": 0,
        "none": 0,
    }
    for row in rows:
        recommendation = _pick_probe_recommendation(row=row, rows=rows)
        row["recommended_route"] = recommendation["provider"]
        row["recommended_strategy"] = recommendation["strategy"]
        recommendation_counts[recommendation["strategy"]] = (
            recommendation_counts.get(recommendation["strategy"], 0) + 1
        )
        row["next_action"] = _combine_probe_next_action(
            current_hint=str(row.get("next_action") or ""),
            action_group=str(row.get("action_group") or "inspect"),
            family=str(row.get("lane_family") or ""),
            preferred_route=str(recommendation["provider"] or ""),
            strategy=str(recommendation["strategy"] or "none"),
        )

    return {
        "providers": rows,
        "summary": {
            "configured": len(rows),
            "ready": ready_count,
            "health_live": health_payload is not None,
            "live_probe": live_probe,
            "actions": action_counts,
            "recommendations": recommendation_counts,
        },
    }


def render_provider_probe_text(report: dict[str, Any]) -> str:
    lines = ["Provider probe", ""]
    summary = report.get("summary") or {}
    lines.append(
        f"Configured: {summary.get('configured', 0)} | Ready now: {summary.get('ready', 0)}"
    )
    lines.append(
        "Live health: "
        + ("available" if summary.get("health_live") else "not available; config/env only")
    )
    if summary.get("live_probe"):
        lines.append("Live probe: enabled (using transport-specific shallow request probes)")
    actions = summary.get("actions") or {}
    action_bits = [
        f"fix-now={actions.get('fix-now', 0)}",
        f"hold={actions.get('hold', 0)}",
        f"watch={actions.get('watch', 0)}",
        f"route={actions.get('route', 0)}",
        f"inspect={actions.get('inspect', 0)}",
    ]
    lines.append("Action summary: " + " | ".join(action_bits))
    recommendations = summary.get("recommendations") or {}
    lines.append(
        "Fallback guidance: "
        + " | ".join(
            [
                f"same-lane={recommendations.get('same-lane-route', 0)}",
                f"cluster={recommendations.get('cluster-degrade', 0)}",
                f"family={recommendations.get('family-route', 0)}",
            ]
        )
    )
    lines.append("")
    for row in report.get("providers", []):
        lines.append(f"- {row['provider']}  ({row['status']})")
        lines.append(
            "  " + f"model: {row['model']} | tier: {row['tier']} | contract: {row['contract']}"
        )
        if row.get("lane_family") or row.get("action_group"):
            family = row.get("lane_family") or "unclassified"
            action = row.get("action_group") or "inspect"
            bits = [f"family: {family}", f"action: {action}"]
            if row.get("canonical_model"):
                bits.append(f"canonical: {row['canonical_model']}")
            if row.get("lane_cluster"):
                bits.append(f"cluster: {row['lane_cluster']}")
            lines.append("  " + " | ".join(bits))
        if row.get("transport_profile"):
            lines.append(
                "  "
                + "transport: "
                + f"{row['transport_profile']} | {row.get('transport_compatibility') or 'n/a'}"
                + (
                    f" | confidence: {row.get('transport_confidence')}"
                    if row.get("transport_confidence")
                    else ""
                )
                + (
                    f" | strategy: {row.get('probe_strategy')}"
                    if row.get("probe_strategy")
                    else ""
                )
            )
        if row.get("verified_via"):
            lines.append("  " + f"verified via: {row['verified_via']}")
        if row.get("probe_payload"):
            lines.append("  " + f"probe payload: {row['probe_payload']}")
        if row.get("avg_latency_ms"):
            lines.append("  " + f"latency: {row['avg_latency_ms']:.1f} ms")
        lines.append("  " + f"why: {row['reason']}")
        if row.get("recommended_route"):
            lines.append(
                "  "
                + "prefer: "
                + f"{row['recommended_route']} "
                + f"({row.get('recommended_strategy') or 'fallback'})"
            )
        if row.get("next_action"):
            lines.append("  " + f"next: {row['next_action']}")
    lines.append("")
    lines.append(
        "Tip: Ready means config, env, and the current /health "
        "request-readiness payload all line up."
    )
    lines.append(
        "Tip: Missing-key or model-unavailable states should be fixed before client rollout."
    )
    return "\n".join(lines) + "\n"


def _classify_probe_action(
    *,
    status: str,
    missing_key: bool,
    ready: bool,
    runtime_window_state: str,
    runtime_cooldown_active: bool,
    runtime_recovered_recently: bool,
) -> str:
    if missing_key or status in {
        "missing-key",
        "unresolved-key",
        "auth-invalid",
        "endpoint-mismatch",
        "model-unavailable",
    }:
        return "fix-now"
    if (
        runtime_cooldown_active
        or runtime_window_state == "cooldown"
        or status in {"quota-exhausted", "rate-limited"}
    ):
        return "hold"
    if (
        runtime_recovered_recently
        or runtime_window_state == "degraded"
        or status == "ready-recovered"
    ):
        return "watch"
    if ready or status in {"ready", "ready-verified", "ready-compat"}:
        return "route"
    return "inspect"


def _default_probe_action_hint(*, action_group: str, provider_name: str, family: str) -> str:
    family_label = family or "this route"
    if action_group == "fix-now":
        return (
            "fix credentials, model mapping, or endpoint settings "
            f"before routing {provider_name}"
        )
    if action_group == "hold":
        return f"hold {provider_name} out of primary traffic until the cooldown pressure clears"
    if action_group == "watch":
        return (
            f"keep {provider_name} in light traffic while the {family_label} "
            "recovery window stays open"
        )
    if action_group == "route":
        return f"route can carry live traffic for the {family_label} lane"
    return f"inspect runtime hints for {provider_name} before making it a primary lane"


def _pick_probe_recommendation(
    *, row: dict[str, Any], rows: list[dict[str, Any]]
) -> dict[str, str]:
    action_group = str(row.get("action_group") or "inspect")
    if action_group == "route":
        return {"provider": "", "strategy": "none"}

    def candidate_pool(*, matcher) -> list[dict[str, Any]]:
        candidates = [
            candidate
            for candidate in rows
            if candidate.get("provider") != row.get("provider")
            and str(candidate.get("action_group") or "inspect") in {"route", "watch"}
            and matcher(candidate)
        ]
        candidates.sort(
            key=lambda candidate: (
                0 if str(candidate.get("action_group") or "") == "route" else 1,
                float(candidate.get("avg_latency_ms") or 0.0),
                str(candidate.get("provider") or ""),
            )
        )
        return candidates

    canonical_model = str(row.get("canonical_model") or "")
    if canonical_model:
        candidates = candidate_pool(
            matcher=lambda candidate: str(candidate.get("canonical_model") or "") == canonical_model
        )
        if candidates:
            return {
                "provider": str(candidates[0].get("provider") or ""),
                "strategy": "same-lane-route",
            }

    degrade_to = [str(item) for item in (row.get("degrade_to") or []) if str(item)]
    if degrade_to:
        candidates = candidate_pool(
            matcher=lambda candidate: str(candidate.get("canonical_model") or "") in degrade_to
        )
        if candidates:
            return {
                "provider": str(candidates[0].get("provider") or ""),
                "strategy": "cluster-degrade",
            }

    family = str(row.get("lane_family") or "")
    if family:
        candidates = candidate_pool(
            matcher=lambda candidate: str(candidate.get("lane_family") or "") == family
        )
        if candidates:
            return {
                "provider": str(candidates[0].get("provider") or ""),
                "strategy": "family-route",
            }

    return {"provider": "", "strategy": "none"}


def _combine_probe_next_action(
    *,
    current_hint: str,
    action_group: str,
    family: str,
    preferred_route: str,
    strategy: str,
) -> str:
    if not preferred_route:
        return current_hint
    strategy_label = {
        "same-lane-route": "same lane",
        "cluster-degrade": "next cluster lane",
        "family-route": "family route",
    }.get(strategy, "fallback route")
    traffic_label = family or "this"
    if action_group == "hold":
        return (
            f"{current_hint}; prefer {preferred_route} as the {strategy_label} "
            f"for {traffic_label} traffic meanwhile"
        )
    if action_group == "watch":
        return (
            f"{current_hint}; favor {preferred_route} as the {strategy_label} "
            f"for steady {traffic_label} traffic"
        )
    if action_group in {"fix-now", "inspect"}:
        return (
            f"{current_hint}; route {traffic_label} traffic through {preferred_route} "
            f"as the {strategy_label} until fixed"
        )
    return current_hint


def _scenario_provider_selection(*, purpose: str, client: str) -> list[str]:
    preferred = _preferred_provider_set(list(_PROVIDER_FACTORIES), purpose=purpose, client=client)
    return [
        name
        for name in preferred
        if _PROVIDER_FACTORIES[name]["provider"].get("contract", "generic") == "generic"
    ]


def _scenario_provider_selection_for_spec(spec: dict[str, Any]) -> list[str]:
    purpose = str(spec["purpose"])
    client = str(spec["client"])
    routing_mode = str(spec.get("routing_mode") or "auto")

    if client == "opencode":
        by_mode = {
            "eco": [
                "gemini-flash-lite",
                "kilocode",
                "blackbox-free",
                "deepseek-chat",
                "deepseek-reasoner",
                "openrouter-fallback",
            ],
            "auto": [
                "deepseek-reasoner",
                "deepseek-chat",
                "anthropic-claude",
                "openai-gpt4o",
                "gemini-flash",
                "kilocode",
                "blackbox-free",
                "openrouter-fallback",
            ],
            "premium": [
                "anthropic-claude",
                "openai-gpt4o",
                "deepseek-reasoner",
                "deepseek-chat",
                "gemini-flash",
                "openrouter-fallback",
            ],
            "free": [
                "kilocode",
                "blackbox-free",
                "gemini-flash-lite",
                "deepseek-chat",
                "openrouter-fallback",
            ],
        }
        preferred = by_mode.get(routing_mode, by_mode["auto"])
        return [name for name in preferred if name in _PROVIDER_FACTORIES]

    return _scenario_provider_selection(purpose=purpose, client=client)


def _scenario_provider_lanes(provider_names: list[str]) -> list[tuple[str, list[str]]]:
    lane_order = [
        ("quality-first", ["anthropic-claude", "openai-gpt4o"]),
        ("reasoning", ["deepseek-reasoner"]),
        ("balanced workhorses", ["deepseek-chat", "gemini-flash"]),
        ("budget / free", ["gemini-flash-lite", "kilocode", "blackbox-free"]),
        ("fallback safety", ["openrouter-fallback"]),
    ]
    lanes: list[tuple[str, list[str]]] = []
    for lane_name, lane_candidates in lane_order:
        lane_members = [name for name in lane_candidates if name in provider_names]
        if lane_members:
            lanes.append((lane_name, lane_members))
    return lanes


def _scenario_provider_role(provider_name: str) -> str:
    taxonomy = _PROVIDER_ROLE_TAXONOMY.get(provider_name) or {}
    return str(taxonomy.get("role") or "")


def _provider_route_registry_summary(provider_name: str) -> dict[str, Any]:
    lane = get_provider_lane_binding(provider_name)
    canonical_model = str(lane.get("canonical_model") or "")
    if not canonical_model:
        return {"canonical_model": "", "known_routes": [], "mirror_providers": []}
    routes = get_canonical_model_routes(canonical_model)
    mirror_providers = [
        str(route.get("provider_name") or "")
        for route in routes
        if str(route.get("provider_name") or "")
        and str(route.get("provider_name") or "") != provider_name
    ]
    return {
        "canonical_model": canonical_model,
        "known_routes": routes,
        "mirror_providers": mirror_providers,
    }


def _scenario_lane_descriptions(provider_names: list[str]) -> list[tuple[str, list[str]]]:
    detailed_lanes: list[tuple[str, list[str]]] = []
    for lane_name, lane_members in _scenario_provider_lanes(provider_names):
        enriched = []
        for provider_name in lane_members:
            role = _scenario_provider_role(provider_name)
            if role:
                enriched.append(f"{provider_name} ({role})")
            else:
                enriched.append(provider_name)
        detailed_lanes.append((lane_name, enriched))
    return detailed_lanes


def _scenario_route_mirrors(provider_names: list[str]) -> list[str]:
    summaries: list[str] = []
    seen: set[str] = set()
    for provider_name in provider_names:
        route_info = _provider_route_registry_summary(provider_name)
        canonical_model = route_info["canonical_model"]
        mirror_providers = route_info["mirror_providers"]
        if not canonical_model or not mirror_providers or canonical_model in seen:
            continue
        seen.add(canonical_model)
        previews = ", ".join(mirror_providers[:3])
        suffix = "" if len(mirror_providers) <= 3 else f" +{len(mirror_providers) - 3} more"
        summaries.append(f"{canonical_model}: {previews}{suffix}")
    return summaries


def _scenario_degrade_chains(provider_names: list[str]) -> list[str]:
    lines: list[str] = []
    seen: set[str] = set()
    for provider_name in provider_names:
        lane = get_provider_lane_binding(provider_name)
        canonical_model = str(lane.get("canonical_model") or "")
        degrade_to = [str(item) for item in (lane.get("degrade_to") or []) if str(item)]
        if not canonical_model or not degrade_to or canonical_model in seen:
            continue
        seen.add(canonical_model)
        lines.append(f"{canonical_model} -> " + " -> ".join(degrade_to[:3]))
    return lines


def _scenario_family_coverage(provider_names: list[str]) -> list[str]:
    provider_set = set(provider_names)
    coverage: list[str] = []
    if "anthropic-claude" in provider_set:
        coverage.append("Anthropic: quality lane active; workhorse/fast lane not configured yet")
    if "openai-gpt4o" in provider_set:
        coverage.append(
            "OpenAI: balanced lane active; faster or cheaper family split not configured yet"
        )
    if "deepseek-reasoner" in provider_set and "deepseek-chat" in provider_set:
        coverage.append("DeepSeek: reasoning + workhorse lanes active")
    if {"kilocode", "blackbox-free"} & provider_set:
        coverage.append("Free lane: aggregator-backed budget coverage is active")
    return coverage


def _scenario_family_hint(provider_names: list[str]) -> str | None:
    hints: list[str] = []
    provider_set = set(provider_names)
    if "anthropic-claude" in provider_set:
        hints.append(
            "Anthropic is currently represented by one quality lane. "
            "Add separate Sonnet or Haiku-style providers if you want "
            "dedicated workhorse or fast Anthropic slots."
        )
    if "openai-gpt4o" in provider_set:
        hints.append(
            "OpenAI is currently represented by one balanced multimodal "
            "lane. Add more OpenAI family variants if you want sharper "
            "quality vs speed splits there too."
        )
    if hints:
        return " ".join(hints)
    return None


def _scenario_deemphasized_providers(provider_names: list[str]) -> list[str]:
    scenario_set = set(provider_names)
    return [
        name
        for name in (
            "anthropic-claude",
            "openai-gpt4o",
            "deepseek-reasoner",
            "deepseek-chat",
            "gemini-flash",
            "gemini-flash-lite",
            "kilocode",
            "blackbox-free",
            "openrouter-fallback",
        )
        if name in _PROVIDER_FACTORIES and name not in scenario_set
    ]


def list_client_scenarios(
    *,
    env_file: str | Path | None = None,
    config_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    configured = _load_existing_provider_names(config_path)
    detected = set(detect_wizard_providers(env_file=env_file))
    scenarios: list[dict[str, Any]] = []
    for scenario_id, spec in _CLIENT_SCENARIOS.items():
        preferred = _scenario_provider_selection_for_spec(spec)
        ready = [name for name in preferred if name in detected]
        configured_hits = [name for name in preferred if name in configured]
        scenarios.append(
            {
                "id": scenario_id,
                "title": spec["title"],
                "client": spec["client"],
                "purpose": spec["purpose"],
                "routing_mode": spec["routing_mode"],
                "summary": spec["summary"],
                "best_for": spec.get("best_for", ""),
                "tradeoff": spec.get("tradeoff", ""),
                "budget_posture": spec.get("budget_posture", "balanced"),
                "recommended_providers": preferred,
                "ready_providers": ready,
                "configured_providers": configured_hits,
                "provider_lanes": _scenario_provider_lanes(preferred),
                "lane_descriptions": _scenario_lane_descriptions(preferred),
                "family_coverage": _scenario_family_coverage(preferred),
                "deemphasized_providers": _scenario_deemphasized_providers(preferred),
                "family_hint": _scenario_family_hint(preferred),
                "route_mirrors": _scenario_route_mirrors(preferred),
                "degrade_chains": _scenario_degrade_chains(preferred),
            }
        )
    return scenarios


def render_client_scenarios_text(
    *,
    env_file: str | Path | None = None,
    config_path: str | Path | None = None,
) -> str:
    lines = ["Client scenarios", ""]
    for item in list_client_scenarios(env_file=env_file, config_path=config_path):
        lines.append(f"- {item['title']}  ({item['id']})")
        lines.append(
            "  "
            + f"client: {item['client']} | purpose: {item['purpose']} | "
            + f"mode: {item['routing_mode']} | budget: {item['budget_posture']}"
        )
        lines.append("  " + f"why: {item['summary']}")
        if item["best_for"]:
            lines.append("  " + f"best when: {item['best_for']}")
        if item["tradeoff"]:
            lines.append("  " + f"tradeoff: {item['tradeoff']}")
        if item["lane_descriptions"]:
            for lane_name, lane_members in item["lane_descriptions"]:
                lines.append("  " + f"{lane_name}: " + ", ".join(lane_members))
        if item.get("route_mirrors"):
            for mirror_line in item["route_mirrors"]:
                lines.append("  " + f"known route mirrors: {mirror_line}")
        if item.get("degrade_chains"):
            for degrade_line in item["degrade_chains"]:
                lines.append("  " + f"degrade chain: {degrade_line}")
        if item["ready_providers"]:
            lines.append("  " + "ready now: " + ", ".join(item["ready_providers"]))
        elif item["recommended_providers"]:
            lines.append(
                "  "
                + "needs keys for: "
                + ", ".join(item["recommended_providers"][:4])
                + (" ..." if len(item["recommended_providers"]) > 4 else "")
            )
        if item["deemphasized_providers"]:
            lines.append(
                "  "
                + "de-emphasized now: "
                + ", ".join(item["deemphasized_providers"][:4])
                + (" ..." if len(item["deemphasized_providers"]) > 4 else "")
            )
        if item.get("family_hint"):
            lines.append("  " + f"family note: {item['family_hint']}")
        if item["family_coverage"]:
            for coverage_line in item["family_coverage"]:
                lines.append("  " + f"family coverage: {coverage_line}")
    lines.append("")
    lines.append(
        "Tip: Apply one scenario when you want a client-specific default "
        "without hand-editing profile modes."
    )
    lines.append(
        "Tip: Scenario lanes describe the current configured provider inventory. "
        "If you want separate Opus / Sonnet / Haiku or similar family lanes, "
        "add them as distinct providers first."
    )
    return "\n".join(lines) + "\n"


def apply_client_scenario(
    *,
    scenario_id: str,
    config_path: str | Path,
    env_file: str | Path | None = None,
) -> dict[str, Any]:
    if scenario_id not in _CLIENT_SCENARIOS:
        raise ValueError(f"Unsupported client scenario '{scenario_id}'")
    spec = _CLIENT_SCENARIOS[scenario_id]
    available = detect_wizard_providers(env_file=env_file)
    selected = [
        name for name in _scenario_provider_selection_for_spec(spec) if name in set(available)
    ]
    suggestion = build_initial_config(
        env_file=env_file,
        purpose=spec["purpose"],
        client=spec["client"],
        selected_providers=selected,
    )
    merged = merge_initial_config(config_path=config_path, suggestion=suggestion)
    profiles = merged.setdefault("client_profiles", {}).setdefault("profiles", {})
    profile = dict(profiles.get(spec["client"], {}))
    profile["routing_mode"] = spec["routing_mode"]
    profiles[spec["client"]] = profile
    return {
        "scenario": {
            "id": scenario_id,
            "title": spec["title"],
            "client": spec["client"],
            "purpose": spec["purpose"],
            "routing_mode": spec["routing_mode"],
        },
        "config": merged,
        "summary": build_config_change_summary(config_path=config_path, updated_config=merged),
    }


def render_client_scenario_summary(payload: dict[str, Any]) -> str:
    scenario = payload.get("scenario") or {}
    summary = payload.get("summary") or {}
    scenario_spec = _CLIENT_SCENARIOS.get(str(scenario.get("id", "")), {})
    lines = [
        "Client scenario summary",
        "",
        f"Scenario: {scenario.get('title', scenario.get('id', 'unknown'))}",
        f"Client  : {scenario.get('client', 'unknown')}",
        f"Purpose : {scenario.get('purpose', 'unknown')}",
        f"Mode    : {scenario.get('routing_mode', 'unknown')}",
        "",
        "Operator guidance",
        "- best when: " + str(scenario_spec.get("best_for", "n/a")),
        "- tradeoff : " + str(scenario_spec.get("tradeoff", "n/a")),
        "",
        "Change preview",
    ]
    if summary.get("added_providers"):
        lines.append("- add providers: " + ", ".join(summary["added_providers"]))
    if summary.get("replaced_models"):
        for item in summary["replaced_models"]:
            lines.append(
                "- replace model: "
                + f"{item['provider']} {item['from_model']} -> {item['to_model']}"
            )
    if summary.get("fallback_additions"):
        lines.append("- fallback additions: " + ", ".join(summary["fallback_additions"]))
    if summary.get("changed_profile_modes"):
        for item in summary["changed_profile_modes"]:
            lines.append(
                "- profile mode: " + f"{item['profile']} {item['from_mode']} -> {item['to_mode']}"
            )
    if lines[-1] == "Change preview":
        lines.append("- no config changes beyond confirming the current scenario")
    return "\n".join(lines) + "\n"


def _preferred_fallback_chain(available: list[str], *, purpose: str) -> list[str]:
    """Return a purpose-aware fallback chain over available providers."""
    by_purpose = {
        "general": [
            "deepseek-chat",
            "deepseek-reasoner",
            "gemini-flash",
            "openai-gpt4o",
            "anthropic-claude",
            "openrouter-fallback",
            "kilocode",
            "blackbox-free",
        ],
        "coding": [
            "deepseek-reasoner",
            "deepseek-chat",
            "anthropic-claude",
            "openai-gpt4o",
            "gemini-flash",
            "openrouter-fallback",
            "kilocode",
            "blackbox-free",
        ],
        "quality": [
            "anthropic-claude",
            "openai-gpt4o",
            "deepseek-reasoner",
            "deepseek-chat",
            "gemini-flash",
            "openrouter-fallback",
            "kilocode",
            "blackbox-free",
        ],
        "free": [
            "kilocode",
            "blackbox-free",
            "gemini-flash-lite",
            "deepseek-chat",
            "openrouter-fallback",
        ],
    }
    return [name for name in by_purpose[purpose] if name in available]


def _preferred_provider_set(available: list[str], *, purpose: str, client: str) -> list[str]:
    chain = _preferred_fallback_chain(available, purpose=purpose)
    if client == "n8n":
        preferred = [
            name
            for name in (
                "gemini-flash-lite",
                "kilocode",
                "blackbox-free",
                "deepseek-chat",
            )
            if name in available
        ]
    elif client == "openclaw":
        preferred = [
            name
            for name in (
                "deepseek-chat",
                "deepseek-reasoner",
                "gemini-flash",
                "openai-gpt4o",
            )
            if name in available
        ]
    elif client == "opencode":
        preferred = [
            name
            for name in (
                "deepseek-reasoner",
                "deepseek-chat",
                "anthropic-claude",
                "openai-gpt4o",
            )
            if name in available
        ]
    else:
        preferred = chain

    selected = preferred or chain
    if "openai-images" in available and "openai-images" not in selected:
        selected.append("openai-images")
    return selected


def _suggested_profile_modes(*, purpose: str) -> dict[str, str]:
    default_mode = {
        "general": "auto",
        "coding": "auto",
        "quality": "premium",
        "free": "free",
    }[purpose]
    return {
        "generic": default_mode,
        "openclaw": "auto",
        "cli": "auto",
        "opencode": "auto",
        "n8n": "eco" if purpose != "quality" else "auto",
    }


def list_provider_candidates(
    *,
    env_file: str | Path | None = None,
    purpose: str = "general",
    client: str = "generic",
    config_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Return detected provider candidates enriched with provider-catalog metadata."""
    if purpose not in _PURPOSES:
        supported = ", ".join(sorted(_PURPOSES))
        raise ValueError(f"Unsupported purpose '{purpose}'. Choose one of: {supported}")
    if client not in _CLIENTS:
        supported = ", ".join(sorted(_CLIENTS))
        raise ValueError(f"Unsupported client '{client}'. Choose one of: {supported}")

    env_values = _load_env_values(env_file)
    catalog = get_provider_catalog()
    detected = detect_wizard_providers(env_file=env_file)
    existing = _load_existing_provider_names(config_path)
    preferred = set(_preferred_provider_set(detected, purpose=purpose, client=client))

    rows: list[dict[str, Any]] = []
    for name in detected:
        rows.append(
            _candidate_row(
                name,
                env_values=env_values,
                existing=existing,
                preferred=preferred,
                catalog=catalog,
            )
        )
    return rows


def build_update_suggestions(
    *,
    env_file: str | Path | None = None,
    purpose: str = "general",
    client: str = "generic",
    config_path: str | Path | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Return config-aware provider suggestions grouped by add/replace/keep."""
    candidates = list_provider_candidates(
        env_file=env_file,
        purpose=purpose,
        client=client,
        config_path=config_path,
    )
    existing_models = _load_existing_provider_models(config_path)
    existing_profile_modes = _load_existing_profile_modes(config_path)
    recommended_add: list[dict[str, Any]] = []
    recommended_replace: list[dict[str, Any]] = []
    recommended_keep: list[dict[str, Any]] = []
    recommended_mode_changes: list[dict[str, Any]] = []

    for candidate in candidates:
        provider = candidate["provider"]
        entry = dict(candidate)
        if not candidate["configured"]:
            if candidate["selected_by_default"]:
                entry["reason"] = "preferred by current purpose/client recommendation"
                recommended_add.append(entry)
            continue

        configured_model = existing_models.get(provider, "")
        if configured_model and configured_model != candidate["model"]:
            entry["configured_model"] = configured_model
            entry["reason"] = "configured model differs from the current curated default"
            recommended_replace.append(entry)
        else:
            entry["reason"] = "already configured and aligned with the current recommendation"
            recommended_keep.append(entry)

    for profile, suggested_mode in _suggested_profile_modes(purpose=purpose).items():
        current_mode = existing_profile_modes.get(profile)
        if current_mode and current_mode != suggested_mode:
            recommended_mode_changes.append(
                {
                    "profile": profile,
                    "configured_mode": current_mode,
                    "suggested_mode": suggested_mode,
                    "reason": "profile mode differs from the current purpose-aware wizard default",
                }
            )

    return {
        "recommended_add": recommended_add,
        "recommended_replace": recommended_replace,
        "recommended_keep": recommended_keep,
        "recommended_mode_changes": recommended_mode_changes,
    }


def apply_update_suggestions(
    *,
    env_file: str | Path | None = None,
    purpose: str = "general",
    client: str = "generic",
    config_path: str | Path,
    apply_groups: list[str] | None = None,
    selected_providers: list[str] | None = None,
    selected_profiles: list[str] | None = None,
) -> dict[str, Any]:
    """Apply selected suggestion groups onto one existing config."""
    groups = set(apply_groups or ["recommended_add", "recommended_replace"])
    supported = {
        "recommended_add",
        "recommended_replace",
        "recommended_keep",
        "recommended_mode_changes",
    }
    unknown = groups - supported
    if unknown:
        raise ValueError("Unsupported suggestion groups: " + ", ".join(sorted(unknown)))

    suggestions = build_update_suggestions(
        env_file=env_file,
        purpose=purpose,
        client=client,
        config_path=config_path,
    )

    provider_names: list[str] = []
    for group_name in ("recommended_add", "recommended_replace", "recommended_keep"):
        if group_name not in groups:
            continue
        provider_names.extend(item["provider"] for item in suggestions[group_name])

    if selected_providers:
        wanted = set(selected_providers)
        provider_names = [name for name in provider_names if name in wanted]

    suggestion = build_initial_config(
        env_file=env_file,
        purpose=purpose,
        client=client,
        selected_providers=_unique_preserve_order(provider_names) or None,
    )
    merged = merge_initial_config(config_path=config_path, suggestion=suggestion)

    if "recommended_mode_changes" in groups:
        profile_names = selected_profiles or [
            item["profile"] for item in suggestions["recommended_mode_changes"]
        ]
        profiles = merged.setdefault("client_profiles", {}).setdefault("profiles", {})
        for item in suggestions["recommended_mode_changes"]:
            if item["profile"] not in profile_names:
                continue
            profile = dict(profiles.get(item["profile"], {}))
            profile["routing_mode"] = item["suggested_mode"]
            profiles[item["profile"]] = profile

    return merged


def build_config_change_summary(
    *,
    config_path: str | Path,
    updated_config: dict[str, Any],
) -> dict[str, Any]:
    """Return one compact summary of config changes."""
    existing = _load_existing_config(config_path)
    existing_providers = existing.get("providers") or {}
    updated_providers = updated_config.get("providers") or {}

    added_providers = sorted(name for name in updated_providers if name not in existing_providers)
    replaced_models: list[dict[str, str]] = []
    for name, provider in updated_providers.items():
        if name not in existing_providers:
            continue
        current = existing_providers.get(name) or {}
        if not isinstance(provider, dict) or not isinstance(current, dict):
            continue
        from_model = str(current.get("model", "") or "").strip()
        to_model = str(provider.get("model", "") or "").strip()
        if from_model and to_model and from_model != to_model:
            replaced_models.append(
                {"provider": name, "from_model": from_model, "to_model": to_model}
            )

    existing_profiles = ((existing.get("client_profiles") or {}).get("profiles")) or {}
    updated_profiles = ((updated_config.get("client_profiles") or {}).get("profiles")) or {}
    changed_profile_modes: list[dict[str, str]] = []
    for name, profile in updated_profiles.items():
        current = existing_profiles.get(name) or {}
        if not isinstance(profile, dict) or not isinstance(current, dict):
            continue
        from_mode = str(current.get("routing_mode", "") or "").strip()
        to_mode = str(profile.get("routing_mode", "") or "").strip()
        if from_mode and to_mode and from_mode != to_mode:
            changed_profile_modes.append(
                {"profile": name, "from_mode": from_mode, "to_mode": to_mode}
            )

    existing_fallback = list(existing.get("fallback_chain", []) or [])
    updated_fallback = list(updated_config.get("fallback_chain", []) or [])
    fallback_additions = [name for name in updated_fallback if name not in existing_fallback]

    return {
        "added_providers": added_providers,
        "replaced_models": replaced_models,
        "changed_profile_modes": changed_profile_modes,
        "fallback_additions": fallback_additions,
    }


def write_output_file(
    *,
    output_path: str | Path,
    rendered: str,
    write_backup: bool = False,
    backup_suffix: str = ".bak",
) -> dict[str, str | bool]:
    """Write one rendered payload to disk, optionally snapshotting the previous file."""
    path = Path(output_path)
    backup_path = ""

    if write_backup and path.exists():
        if not backup_suffix:
            raise ValueError("backup_suffix must not be empty when write_backup is enabled")
        backup_path = str(path.parent / f"{path.name}{backup_suffix}")
        shutil.copy2(path, backup_path)

    payload = rendered if rendered.endswith("\n") else rendered + "\n"
    path.write_text(payload, encoding="utf-8")
    return {
        "output_path": str(path),
        "backup_created": bool(backup_path),
        "backup_path": backup_path,
    }


def _resolve_selected_providers(
    available: list[str],
    *,
    purpose: str,
    client: str,
    selected_providers: list[str] | None,
) -> list[str]:
    if selected_providers:
        unknown = [name for name in selected_providers if name not in available]
        if unknown:
            raise ValueError(
                "Unsupported or unavailable wizard provider selection: "
                + ", ".join(sorted(unknown))
            )
        return list(dict.fromkeys(selected_providers))
    return _preferred_provider_set(available, purpose=purpose, client=client)


def _available_shortcuts(available: list[str]) -> dict[str, dict[str, Any]]:
    """Return shortcut mappings for available providers only."""
    shortcuts: dict[str, dict[str, Any]] = {}
    for name in available:
        shortcut = _PROVIDER_FACTORIES[name].get("shortcut")
        if not shortcut:
            continue
        shortcuts[name] = {
            "target": name,
            "aliases": list(shortcut.get("aliases", [])),
            "description": str(shortcut.get("description", "") or "").strip(),
        }
    return shortcuts


def _provider_payload_with_lane(name: str) -> dict[str, Any]:
    provider = _clone(_PROVIDER_FACTORIES[name]["provider"])
    lane = get_provider_lane_binding(name)
    if lane:
        provider["lane"] = lane
    return provider


def _premium_targets(available: list[str]) -> list[str]:
    return [
        name
        for name in ("anthropic-claude", "openai-gpt4o", "deepseek-reasoner", "gemini-flash")
        if name in available
    ]


def _free_targets(available: list[str]) -> list[str]:
    return [name for name in ("kilocode", "blackbox-free") if name in available]


def _build_modes(available: list[str], *, purpose: str) -> dict[str, Any]:
    premium_targets = _premium_targets(available)
    free_targets = _free_targets(available)
    default_mode = {
        "general": "auto",
        "coding": "auto",
        "quality": "premium",
        "free": "free",
    }[purpose]

    modes = {
        "auto": {
            "description": "Balanced (default)",
            "best_for": "General use",
            "savings": "Balanced",
            "aliases": [],
            "select": {
                "prefer_tiers": ["default", "reasoning", "mid"],
            },
        },
        "eco": {
            "description": "Cheapest possible",
            "best_for": "Maximum savings",
            "savings": "Aggressive savings",
            "aliases": [],
            "select": {
                "prefer_tiers": ["cheap", "fallback", "default", "mid"],
                "capability_values": {
                    "cost_tier": ["free", "cheap", "standard"],
                },
            },
        },
        "premium": {
            "description": "Best quality",
            "best_for": "Mission-critical work",
            "savings": "Lowest savings",
            "aliases": [],
            "select": {
                "prefer_providers": premium_targets,
                "prefer_tiers": ["mid", "reasoning", "default"],
            },
        },
    }
    if free_targets:
        modes["free"] = {
            "description": "Free tier only",
            "best_for": "Zero-cost routing",
            "savings": "100%",
            "aliases": [],
            "select": {
                "allow_providers": free_targets,
                "prefer_providers": free_targets,
                "capability_values": {
                    "cost_tier": ["free"],
                },
            },
        }

    return {
        "enabled": True,
        "default": default_mode if default_mode in modes else "auto",
        "modes": modes,
    }


def _unique_preserve_order(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


def _merge_mapping(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = dict(existing)
    for key, value in incoming.items():
        if key not in merged:
            merged[key] = _clone(value)
        elif isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _merge_mapping(merged[key], value)
    return merged


def _mapping_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list_or_empty(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def merge_initial_config(
    *,
    config_path: str | Path,
    suggestion: dict[str, Any],
) -> dict[str, Any]:
    """Merge one wizard suggestion into an existing config with conservative defaults."""
    path = Path(config_path)
    with path.open(encoding="utf-8") as handle:
        existing = yaml.safe_load(handle) or {}
    if not isinstance(existing, dict):
        raise ValueError("Existing config must be a YAML mapping")

    merged = _clone(existing)
    for section in ("server", "security", "provider_catalog_check", "update_check", "auto_update"):
        merged[section] = _merge_mapping(
            _mapping_or_empty(merged.get(section)),
            _mapping_or_empty(suggestion.get(section)),
        )

    merged["providers"] = dict(_mapping_or_empty(merged.get("providers")))
    merged["providers"].update(_clone(_mapping_or_empty(suggestion.get("providers"))))

    merged["fallback_chain"] = _unique_preserve_order(
        list(_list_or_empty(merged.get("fallback_chain")))
        + list(_list_or_empty(suggestion.get("fallback_chain")))
    )

    existing_modes = _mapping_or_empty(merged.get("routing_modes"))
    suggested_modes = _mapping_or_empty(suggestion.get("routing_modes"))
    existing_modes["enabled"] = bool(
        existing_modes.get("enabled", suggested_modes.get("enabled", True))
    )
    existing_modes["default"] = existing_modes.get(
        "default",
        suggested_modes.get("default", "auto"),
    )
    existing_modes["modes"] = _merge_mapping(
        _mapping_or_empty(existing_modes.get("modes")),
        _mapping_or_empty(suggested_modes.get("modes")),
    )
    merged["routing_modes"] = existing_modes

    existing_shortcuts = _mapping_or_empty(merged.get("model_shortcuts"))
    suggested_shortcuts = _mapping_or_empty(suggestion.get("model_shortcuts"))
    existing_shortcuts["enabled"] = bool(
        existing_shortcuts.get("enabled", suggested_shortcuts.get("enabled", True))
    )
    existing_shortcuts["shortcuts"] = _merge_mapping(
        _mapping_or_empty(existing_shortcuts.get("shortcuts")),
        _mapping_or_empty(suggested_shortcuts.get("shortcuts")),
    )
    merged["model_shortcuts"] = existing_shortcuts

    existing_profiles = _mapping_or_empty(merged.get("client_profiles"))
    suggested_profiles = _mapping_or_empty(suggestion.get("client_profiles"))
    existing_profiles["enabled"] = bool(
        existing_profiles.get("enabled", suggested_profiles.get("enabled", True))
    )
    existing_profiles["default"] = existing_profiles.get(
        "default", suggested_profiles.get("default", "generic")
    )
    existing_profiles["presets"] = _unique_preserve_order(
        list(_list_or_empty(existing_profiles.get("presets")))
        + list(_list_or_empty(suggested_profiles.get("presets")))
    )
    profiles = dict(_mapping_or_empty(existing_profiles.get("profiles")))
    for name, profile in _mapping_or_empty(suggested_profiles.get("profiles")).items():
        profiles[name] = _merge_mapping(
            _mapping_or_empty(profiles.get(name)),
            _mapping_or_empty(profile),
        )
    existing_profiles["profiles"] = profiles
    rules_by_profile = {
        rule.get("profile"): rule
        for rule in _list_or_empty(existing_profiles.get("rules"))
        if isinstance(rule, dict)
    }
    for rule in _list_or_empty(suggested_profiles.get("rules")):
        if not isinstance(rule, dict):
            continue
        rules_by_profile.setdefault(rule.get("profile"), _clone(rule))
    existing_profiles["rules"] = list(rules_by_profile.values())
    merged["client_profiles"] = existing_profiles

    existing_policies = _mapping_or_empty(merged.get("routing_policies"))
    suggested_policies = _mapping_or_empty(suggestion.get("routing_policies"))
    existing_policies["enabled"] = bool(
        existing_policies.get("enabled", suggested_policies.get("enabled", True))
    )
    rules_by_name = {
        rule.get("name"): rule
        for rule in _list_or_empty(existing_policies.get("rules"))
        if isinstance(rule, dict)
    }
    for rule in _list_or_empty(suggested_policies.get("rules")):
        if not isinstance(rule, dict):
            continue
        rules_by_name.setdefault(rule.get("name"), _clone(rule))
    existing_policies["rules"] = list(rules_by_name.values())
    merged["routing_policies"] = existing_policies

    existing_hooks = _mapping_or_empty(merged.get("request_hooks"))
    suggested_hooks = _mapping_or_empty(suggestion.get("request_hooks"))
    existing_hooks["enabled"] = bool(
        existing_hooks.get("enabled", suggested_hooks.get("enabled", True))
    )
    existing_hooks["on_error"] = existing_hooks.get(
        "on_error", suggested_hooks.get("on_error", "continue")
    )
    existing_hooks["hooks"] = _unique_preserve_order(
        list(_list_or_empty(existing_hooks.get("hooks")))
        + list(_list_or_empty(suggested_hooks.get("hooks")))
    )
    merged["request_hooks"] = existing_hooks
    return merged


def build_initial_config(
    *,
    env_file: str | Path | None = None,
    purpose: str = "general",
    client: str = "generic",
    selected_providers: list[str] | None = None,
) -> dict[str, Any]:
    """Build a suggested initial config from detected API keys and one purpose."""
    if purpose not in _PURPOSES:
        supported = ", ".join(sorted(_PURPOSES))
        raise ValueError(f"Unsupported purpose '{purpose}'. Choose one of: {supported}")
    if client not in _CLIENTS:
        supported = ", ".join(sorted(_CLIENTS))
        raise ValueError(f"Unsupported client '{client}'. Choose one of: {supported}")

    available = detect_wizard_providers(env_file=env_file)
    selected = _resolve_selected_providers(
        available,
        purpose=purpose,
        client=client,
        selected_providers=selected_providers,
    )
    providers = {name: _provider_payload_with_lane(name) for name in selected}
    shortcuts = _available_shortcuts(selected)
    fallback_chain = _preferred_fallback_chain(selected, purpose=purpose)

    config: dict[str, Any] = {
        "server": {
            "host": "127.0.0.1",
            "port": 8090,
            "log_level": "info",
        },
        "security": {
            "response_headers": True,
            "cache_control": "no-store",
            "max_json_body_bytes": 1048576,
            "max_upload_bytes": 10485760,
            "max_header_value_chars": 160,
        },
        "provider_catalog_check": {
            "enabled": True,
            "warn_on_untracked": True,
            "warn_on_model_drift": True,
            "warn_on_unofficial_sources": True,
            "warn_on_volatile_offers": True,
            "max_catalog_age_days": 30,
        },
        "providers": providers,
        "fallback_chain": fallback_chain,
        "routing_modes": _build_modes(selected, purpose=purpose),
        "model_shortcuts": {
            "enabled": bool(shortcuts),
            "shortcuts": shortcuts,
        },
        "routing_policies": {
            "enabled": True,
            "rules": [
                {
                    "name": "n8n-cheap-default",
                    "match": {
                        "any": [
                            {"header_contains": {"x-faigate-client": ["n8n"]}},
                            {"client_profile": ["n8n"]},
                        ]
                    },
                    "select": {
                        "prefer_tiers": ["cheap", "default", "mid"],
                    },
                },
                {
                    "name": "opencode-general",
                    "match": {
                        "any": [
                            {"header_contains": {"x-faigate-client": ["opencode"]}},
                            {"client_profile": ["opencode"]},
                        ]
                    },
                    "select": {
                        "prefer_tiers": ["default", "mid", "reasoning"],
                    },
                },
            ],
        },
        "client_profiles": {
            "enabled": True,
            "default": "generic",
            "presets": ["openclaw", "n8n", "cli"],
            "profiles": {
                "generic": {},
                "n8n": {
                    "routing_mode": "eco",
                },
                "openclaw": {
                    "routing_mode": "auto",
                },
                "cli": {
                    "routing_mode": "auto",
                },
                "opencode": {
                    "routing_mode": "auto",
                    "prefer_tiers": ["default", "mid", "reasoning"],
                },
            },
            "rules": [
                {
                    "profile": "opencode",
                    "match": {
                        "any": [
                            {"header_contains": {"x-faigate-client": ["opencode"]}},
                        ]
                    },
                }
            ],
        },
        "request_hooks": {
            "enabled": True,
            "on_error": "continue",
            "hooks": [
                "prefer-provider-header",
                "locality-header",
                "profile-override-header",
            ],
        },
        "update_check": {
            "enabled": True,
            "repository": "fusionAIze/faigate",
            "api_base": "https://api.github.com",
            "timeout_seconds": 5.0,
            "check_interval_seconds": 21600,
            "release_channel": "stable",
        },
        "auto_update": {
            "enabled": False,
            "allow_major": False,
            "rollout_ring": "stable",
            "require_healthy_providers": True,
            "max_unhealthy_providers": 0,
            "min_release_age_hours": 24,
            "provider_scope": {
                "allow_providers": [],
                "deny_providers": ["openrouter-fallback"],
            },
            "verification": {
                "enabled": False,
                "command": "faigate-health",
                "timeout_seconds": 30,
                "rollback_command": "",
            },
            "maintenance_window": {
                "enabled": False,
                "timezone": "UTC",
                "days": ["sat", "sun"],
                "start_hour": 2,
                "end_hour": 5,
            },
            "apply_command": "faigate-update",
        },
    }
    return config


def render_initial_config_yaml(
    *,
    env_file: str | Path | None = None,
    purpose: str = "general",
    client: str = "generic",
    selected_providers: list[str] | None = None,
    config_path: str | Path | None = None,
    merge_existing: bool = False,
) -> str:
    """Render the suggested config as YAML."""
    suggestion = build_initial_config(
        env_file=env_file,
        purpose=purpose,
        client=client,
        selected_providers=selected_providers,
    )
    payload = (
        merge_initial_config(config_path=config_path, suggestion=suggestion)
        if merge_existing and config_path is not None
        else suggestion
    )
    return yaml.safe_dump(payload, sort_keys=False, allow_unicode=False)
