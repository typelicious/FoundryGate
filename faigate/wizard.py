"""Initial configuration wizard helpers for local fusionAIze Gate installs."""

from __future__ import annotations

import os
import shutil
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
            if row["notes"]:
                lines.append("  " + f"why: {row['notes']}")
        lines.append("")

    lines.append("Tip: Press Enter in the wizard to use the recommended ready providers.")
    lines.append(
        "Tip: Use --json or --yaml with --list-candidates when you want the full metadata dump."
    )
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
