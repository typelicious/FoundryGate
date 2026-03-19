"""Initial configuration wizard helpers for local FoundryGate installs."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import dotenv_values

from .provider_catalog import get_provider_catalog

ProviderFactory = dict[str, Any]


_PURPOSES = {"general", "coding", "quality", "free"}
_CLIENTS = {"generic", "openclaw", "n8n", "cli", "opencode"}


_PROVIDER_FACTORIES: dict[str, ProviderFactory] = {
    "deepseek-chat": {
        "env": "DEEPSEEK_API_KEY",
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


def detect_wizard_providers(*, env_file: str | Path | None = None) -> list[str]:
    """Return provider names that can be configured from the current env file."""
    env_values = _load_env_values(env_file)
    detected = []
    for name, spec in _PROVIDER_FACTORIES.items():
        if env_values.get(spec["env"]):
            detected.append(name)
    return detected


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

    catalog = get_provider_catalog()
    detected = detect_wizard_providers(env_file=env_file)
    existing = _load_existing_provider_names(config_path)
    preferred = set(_preferred_provider_set(detected, purpose=purpose, client=client))

    rows: list[dict[str, Any]] = []
    for name in detected:
        factory = _PROVIDER_FACTORIES[name]
        provider = factory["provider"]
        catalog_entry = catalog.get(name, {})
        rows.append(
            {
                "provider": name,
                "env": factory["env"],
                "configured": name in existing,
                "selected_by_default": name in preferred,
                "model": provider.get("model", ""),
                "tier": provider.get("tier", "default"),
                "contract": provider.get("contract", "generic"),
                "provider_type": catalog_entry.get("provider_type", "direct"),
                "auth_modes": list(catalog_entry.get("auth_modes", ["api_key"])),
                "offer_track": catalog_entry.get("offer_track", "direct"),
                "volatility": catalog_entry.get("volatility", "low"),
                "evidence_level": catalog_entry.get("evidence_level", "official"),
                "official_source_url": catalog_entry.get("official_source_url", ""),
                "notes": catalog_entry.get("notes", ""),
            }
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
        merged[section] = _merge_mapping(merged.get(section, {}), suggestion.get(section, {}))

    merged["providers"] = dict(merged.get("providers", {}))
    merged["providers"].update(_clone(suggestion.get("providers", {})))

    merged["fallback_chain"] = _unique_preserve_order(
        list(merged.get("fallback_chain", [])) + list(suggestion.get("fallback_chain", []))
    )

    existing_modes = merged.get("routing_modes", {})
    suggested_modes = suggestion.get("routing_modes", {})
    existing_modes["enabled"] = bool(
        existing_modes.get("enabled", suggested_modes.get("enabled", True))
    )
    existing_modes["default"] = existing_modes.get(
        "default",
        suggested_modes.get("default", "auto"),
    )
    existing_modes["modes"] = _merge_mapping(
        existing_modes.get("modes", {}),
        suggested_modes.get("modes", {}),
    )
    merged["routing_modes"] = existing_modes

    existing_shortcuts = merged.get("model_shortcuts", {})
    suggested_shortcuts = suggestion.get("model_shortcuts", {})
    existing_shortcuts["enabled"] = bool(
        existing_shortcuts.get("enabled", suggested_shortcuts.get("enabled", True))
    )
    existing_shortcuts["shortcuts"] = _merge_mapping(
        existing_shortcuts.get("shortcuts", {}),
        suggested_shortcuts.get("shortcuts", {}),
    )
    merged["model_shortcuts"] = existing_shortcuts

    existing_profiles = merged.get("client_profiles", {})
    suggested_profiles = suggestion.get("client_profiles", {})
    existing_profiles["enabled"] = bool(
        existing_profiles.get("enabled", suggested_profiles.get("enabled", True))
    )
    existing_profiles["default"] = existing_profiles.get(
        "default", suggested_profiles.get("default", "generic")
    )
    existing_profiles["presets"] = _unique_preserve_order(
        list(existing_profiles.get("presets", [])) + list(suggested_profiles.get("presets", []))
    )
    profiles = dict(existing_profiles.get("profiles", {}))
    for name, profile in suggested_profiles.get("profiles", {}).items():
        profiles[name] = _merge_mapping(profiles.get(name, {}), profile)
    existing_profiles["profiles"] = profiles
    rules_by_profile = {rule.get("profile"): rule for rule in existing_profiles.get("rules", [])}
    for rule in suggested_profiles.get("rules", []):
        rules_by_profile.setdefault(rule.get("profile"), _clone(rule))
    existing_profiles["rules"] = list(rules_by_profile.values())
    merged["client_profiles"] = existing_profiles

    existing_policies = merged.get("routing_policies", {})
    suggested_policies = suggestion.get("routing_policies", {})
    existing_policies["enabled"] = bool(
        existing_policies.get("enabled", suggested_policies.get("enabled", True))
    )
    rules_by_name = {rule.get("name"): rule for rule in existing_policies.get("rules", [])}
    for rule in suggested_policies.get("rules", []):
        rules_by_name.setdefault(rule.get("name"), _clone(rule))
    existing_policies["rules"] = list(rules_by_name.values())
    merged["routing_policies"] = existing_policies

    existing_hooks = merged.get("request_hooks", {})
    suggested_hooks = suggestion.get("request_hooks", {})
    existing_hooks["enabled"] = bool(
        existing_hooks.get("enabled", suggested_hooks.get("enabled", True))
    )
    existing_hooks["on_error"] = existing_hooks.get(
        "on_error", suggested_hooks.get("on_error", "continue")
    )
    existing_hooks["hooks"] = _unique_preserve_order(
        list(existing_hooks.get("hooks", [])) + list(suggested_hooks.get("hooks", []))
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
    providers = {name: _clone(_PROVIDER_FACTORIES[name]["provider"]) for name in selected}
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
                            {"header_contains": {"x-foundrygate-client": ["n8n"]}},
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
                            {"header_contains": {"x-foundrygate-client": ["opencode"]}},
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
                            {"header_contains": {"x-foundrygate-client": ["opencode"]}},
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
            "repository": "typelicious/FoundryGate",
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
                "command": "foundrygate-health",
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
            "apply_command": "foundrygate-update",
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
