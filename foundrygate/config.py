"""Configuration loader with environment variable expansion.

DB path resolution
------------------
The metrics database path is resolved in this priority order:

1. FOUNDRYGATE_DB_PATH environment variable  (explicit override)
2. metrics.db_path in config.yaml         (if set)
3. XDG_DATA_HOME / foundrygate / foundrygate.db (Linux/XDG default)
4. ~/.local/share/foundrygate/foundrygate.db    (fallback for non-XDG systems)

The path NEVER defaults to ./foundrygate.db in the repo working directory.
This ensures no database files are accidentally committed.

On Linux / systemd the recommended path is /var/lib/foundrygate/foundrygate.db,
set via FOUNDRYGATE_DB_PATH in the service environment.
"""

from __future__ import annotations

import ipaddress
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml
from dotenv import load_dotenv

from .hooks import get_registered_request_hooks

_SUPPORTED_BACKENDS = {"openai-compat", "google-genai", "anthropic-compat"}
_SUPPORTED_PROVIDER_CONTRACTS = {"generic", "local-worker", "image-provider"}
_SUPPORTED_CACHE_MODES = {"none", "implicit", "explicit"}
_BOOL_CAPABILITY_FIELDS = {
    "chat",
    "reasoning",
    "vision",
    "image_generation",
    "image_editing",
    "tools",
    "long_context",
    "streaming",
    "local",
    "cloud",
}
_STRING_CAPABILITY_FIELDS = {
    "cost_tier",
    "latency_tier",
    "network_zone",
    "compliance_scope",
}
_ALL_CAPABILITY_FIELDS = _BOOL_CAPABILITY_FIELDS | _STRING_CAPABILITY_FIELDS
_POLICY_SELECT_KEYS = {
    "allow_providers",
    "deny_providers",
    "prefer_providers",
    "prefer_tiers",
    "require_capabilities",
    "capability_values",
}
_CLIENT_PROFILE_MATCH_KEYS = {"header_contains", "header_present", "any", "all"}
_SUPPORTED_CLIENT_PROFILE_PRESETS = {"openclaw", "n8n", "cli"}
_SUPPORTED_REQUEST_HOOKS = set(get_registered_request_hooks())

_CLIENT_PROFILE_PRESET_SPECS: dict[str, dict[str, Any]] = {
    "openclaw": {
        "profile": {"prefer_tiers": ["default", "reasoning"]},
        "rule": {
            "profile": "openclaw",
            "match": {
                "any": [
                    {"header_present": ["x-openclaw-source"]},
                    {"header_contains": {"x-foundrygate-client": ["openclaw"]}},
                ]
            },
        },
    },
    "n8n": {
        "profile": {"prefer_tiers": ["cheap", "default"]},
        "rule": {
            "profile": "n8n",
            "match": {
                "header_contains": {
                    "x-foundrygate-client": ["n8n"],
                }
            },
        },
    },
    "cli": {
        "profile": {"prefer_tiers": ["default", "reasoning"]},
        "rule": {
            "profile": "cli",
            "match": {
                "header_contains": {
                    "x-foundrygate-client": ["cli", "codex", "claude", "kilocode", "deepseek"],
                }
            },
        },
    },
}


class ConfigError(ValueError):
    """Raised when config.yaml contains an invalid runtime configuration."""


def _expand_env(value: str) -> str:
    """Expand ${VAR} and ${VAR:-default} patterns in a string."""

    def _replace(m: re.Match) -> str:
        var = m.group(1)
        if ":-" in var:
            name, default = var.split(":-", 1)
            return os.environ.get(name, default)
        return os.environ.get(var, m.group(0))

    return re.sub(r"\$\{([^}]+)}", _replace, value)


def _walk_expand(obj: Any) -> Any:
    """Recursively expand env vars in all string values."""
    if isinstance(obj, str):
        return _expand_env(obj)
    if isinstance(obj, dict):
        return {k: _walk_expand(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_walk_expand(v) for v in obj]
    return obj


def _safe_db_path(configured: str | None = None) -> str:
    """Return a safe, out-of-repo default DB path.

    Priority:
      1. FOUNDRYGATE_DB_PATH env var
      2. configured value from config.yaml (if not empty / not a relative ./)
      3. XDG_DATA_HOME/foundrygate/foundrygate.db
      4. ~/.local/share/foundrygate/foundrygate.db
    """
    # 1. Env var always wins
    env_path = os.environ.get("FOUNDRYGATE_DB_PATH", "").strip()
    if env_path:
        return env_path

    # 2. Explicit config value – but reject ./foundrygate.db* to prevent repo pollution
    if configured:
        p = configured.strip()
        if p and not p.startswith("./foundrygate.db") and p != "foundrygate.db":
            return p

    # 3. XDG_DATA_HOME
    xdg = os.environ.get("XDG_DATA_HOME", "").strip()
    if xdg:
        return str(Path(xdg) / "foundrygate" / "foundrygate.db")

    # 4. ~/.local/share/foundrygate/foundrygate.db
    return str(Path.home() / ".local" / "share" / "foundrygate" / "foundrygate.db")


def _looks_local_base_url(base_url: str) -> bool:
    """Return whether a provider URL points to localhost or private network space."""
    parsed = urlparse(base_url)
    host = (parsed.hostname or "").strip().lower()
    if not host:
        return False

    if host in {"localhost", "::1"} or host.endswith(".local"):
        return True

    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False

    return ip.is_loopback or ip.is_private or ip.is_link_local


def _normalize_provider_capabilities(name: str, cfg: dict[str, Any]) -> dict[str, Any]:
    """Normalize and validate provider capability metadata."""
    raw = cfg.get("capabilities") or {}
    if not isinstance(raw, dict):
        raise ConfigError(f"Provider '{name}' capabilities must be a mapping")

    unknown = sorted(set(raw) - _ALL_CAPABILITY_FIELDS)
    if unknown:
        unknown_list = ", ".join(unknown)
        raise ConfigError(f"Provider '{name}' has unknown capability keys: {unknown_list}")

    backend = cfg.get("backend", "openai-compat")
    model = str(cfg.get("model", "")).lower()
    tier = str(cfg.get("tier", "")).lower()
    is_local = _looks_local_base_url(str(cfg.get("base_url", "")))
    context_window = int(cfg.get("context_window") or 0)
    max_input_tokens = int((cfg.get("limits") or {}).get("max_input_tokens") or 0)

    normalized: dict[str, Any] = {
        "chat": True,
        "reasoning": tier == "reasoning" or "reasoner" in model,
        "vision": False,
        "image_generation": False,
        "image_editing": False,
        "tools": False,
        "long_context": context_window >= 128_000 or max_input_tokens >= 128_000,
        "streaming": backend != "google-genai",
        "local": is_local,
        "cloud": not is_local,
    }

    for key in _BOOL_CAPABILITY_FIELDS:
        if key not in raw:
            continue
        value = raw[key]
        if not isinstance(value, bool):
            raise ConfigError(f"Provider '{name}' capability '{key}' must be a boolean")
        normalized[key] = value

    if "local" in raw and "cloud" not in raw:
        normalized["cloud"] = not normalized["local"]
    if "cloud" in raw and "local" not in raw:
        normalized["local"] = not normalized["cloud"]

    normalized["network_zone"] = "local" if normalized["local"] else "public"

    for key in _STRING_CAPABILITY_FIELDS:
        if key not in raw:
            continue
        value = raw[key]
        if not isinstance(value, str) or not value.strip():
            raise ConfigError(f"Provider '{name}' capability '{key}' must be a non-empty string")
        normalized[key] = value.strip()

    if not normalized["chat"]:
        raise ConfigError(f"Provider '{name}' must support chat=true in the current runtime")
    if normalized["local"] and normalized["cloud"]:
        raise ConfigError(f"Provider '{name}' cannot be both local and cloud")
    if backend == "google-genai" and normalized["streaming"]:
        raise ConfigError(f"Provider '{name}' cannot enable streaming for backend google-genai yet")
    if backend == "google-genai" and normalized["tools"]:
        raise ConfigError(f"Provider '{name}' cannot enable tools for backend google-genai yet")

    return normalized


def _normalize_positive_int(value: Any, *, field_name: str, provider_name: str) -> int | None:
    """Validate one optional positive integer provider field."""
    if value in (None, ""):
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ConfigError(
            f"Provider '{provider_name}' field '{field_name}' must be a positive integer"
        )
    return value


def _normalize_provider_limits(name: str, cfg: dict[str, Any]) -> dict[str, int]:
    """Validate optional provider token limit metadata."""
    raw = cfg.get("limits") or {}
    if not isinstance(raw, dict):
        raise ConfigError(f"Provider '{name}' field 'limits' must be a mapping")

    limits: dict[str, int] = {}
    max_input = _normalize_positive_int(
        raw.get("max_input_tokens"),
        field_name="limits.max_input_tokens",
        provider_name=name,
    )
    max_output = _normalize_positive_int(
        raw.get("max_output_tokens"),
        field_name="limits.max_output_tokens",
        provider_name=name,
    )
    if max_input is not None:
        limits["max_input_tokens"] = max_input
    if max_output is not None:
        limits["max_output_tokens"] = max_output
    return limits


def _normalize_provider_cache(name: str, cfg: dict[str, Any]) -> dict[str, Any]:
    """Validate optional provider cache metadata."""
    raw = cfg.get("cache") or {}
    if not isinstance(raw, dict):
        raise ConfigError(f"Provider '{name}' field 'cache' must be a mapping")

    pricing = cfg.get("pricing") or {}
    has_cache_read_price = bool(pricing.get("cache_read", 0))
    default_mode = "implicit" if has_cache_read_price else "none"
    mode = str(raw.get("mode", default_mode)).strip().lower()
    if mode not in _SUPPORTED_CACHE_MODES:
        supported = ", ".join(sorted(_SUPPORTED_CACHE_MODES))
        raise ConfigError(
            f"Provider '{name}' field 'cache.mode' uses unsupported value '{mode}'"
            f" (supported: {supported})"
        )

    read_discount = raw.get("read_discount")
    if read_discount is None:
        input_price = float(pricing.get("input", 0) or 0)
        cache_price = float(pricing.get("cache_read", input_price) or input_price)
        read_discount = mode != "none" and cache_price < input_price
    elif not isinstance(read_discount, bool):
        raise ConfigError(f"Provider '{name}' field 'cache.read_discount' must be a boolean")

    return {"mode": mode, "read_discount": read_discount}


def _normalize_provider_image(name: str, cfg: dict[str, Any]) -> dict[str, Any]:
    """Validate optional provider image metadata."""
    raw = cfg.get("image") or {}
    if not isinstance(raw, dict):
        raise ConfigError(f"Provider '{name}' field 'image' must be a mapping")

    image: dict[str, Any] = {}
    max_outputs = _normalize_positive_int(
        raw.get("max_outputs"),
        field_name="image.max_outputs",
        provider_name=name,
    )
    if max_outputs is not None:
        image["max_outputs"] = max_outputs

    max_side_px = _normalize_positive_int(
        raw.get("max_side_px"),
        field_name="image.max_side_px",
        provider_name=name,
    )
    if max_side_px is not None:
        image["max_side_px"] = max_side_px

    supported_sizes = raw.get("supported_sizes", [])
    if supported_sizes in (None, ""):
        supported_sizes = []
    if isinstance(supported_sizes, str):
        supported_sizes = [supported_sizes]
    if not isinstance(supported_sizes, list):
        raise ConfigError(f"Provider '{name}' field 'image.supported_sizes' must be a list")

    normalized_sizes = []
    for value in supported_sizes:
        if not isinstance(value, str) or not value.strip():
            raise ConfigError(
                f"Provider '{name}' field 'image.supported_sizes' must contain non-empty strings"
            )
        normalized_sizes.append(value.strip())
    if normalized_sizes:
        image["supported_sizes"] = normalized_sizes

    policy_tags = raw.get("policy_tags", [])
    if policy_tags in (None, ""):
        policy_tags = []
    if isinstance(policy_tags, str):
        policy_tags = [policy_tags]
    if not isinstance(policy_tags, list):
        raise ConfigError(f"Provider '{name}' field 'image.policy_tags' must be a list")

    normalized_tags = []
    for value in policy_tags:
        if not isinstance(value, str) or not value.strip():
            raise ConfigError(
                f"Provider '{name}' field 'image.policy_tags' must contain non-empty strings"
            )
        normalized_tags.append(value.strip().lower())
    if normalized_tags:
        image["policy_tags"] = normalized_tags

    return image


def _normalize_provider(name: str, cfg: Any) -> dict[str, Any]:
    """Validate a provider definition and attach normalized capability metadata."""
    if not isinstance(cfg, dict):
        raise ConfigError(f"Provider '{name}' must be a mapping")

    normalized = dict(cfg)
    backend = normalized.get("backend", "openai-compat")
    if backend not in _SUPPORTED_BACKENDS:
        supported = ", ".join(sorted(_SUPPORTED_BACKENDS))
        raise ConfigError(
            f"Provider '{name}' uses unsupported backend '{backend}' (supported: {supported})"
        )

    for field in ("base_url", "model"):
        value = normalized.get(field, "")
        if not isinstance(value, str) or not value.strip():
            raise ConfigError(f"Provider '{name}' must define a non-empty '{field}'")

    context_window = _normalize_positive_int(
        normalized.get("context_window"),
        field_name="context_window",
        provider_name=name,
    )
    if context_window is not None:
        normalized["context_window"] = context_window

    contract = normalized.get("contract", "generic")
    if not isinstance(contract, str) or not contract.strip():
        raise ConfigError(f"Provider '{name}' contract must be a non-empty string")
    contract = contract.strip()
    if contract not in _SUPPORTED_PROVIDER_CONTRACTS:
        supported = ", ".join(sorted(_SUPPORTED_PROVIDER_CONTRACTS))
        raise ConfigError(
            f"Provider '{name}' uses unsupported contract '{contract}' (supported: {supported})"
        )
    normalized["contract"] = contract

    if contract == "local-worker":
        if backend != "openai-compat":
            raise ConfigError(
                f"Provider '{name}' contract 'local-worker' requires backend 'openai-compat'"
            )
        if not _looks_local_base_url(str(normalized.get("base_url", ""))):
            raise ConfigError(
                f"Provider '{name}' contract 'local-worker' requires a local/private base_url"
            )
        normalized.setdefault("tier", "local")

        raw_capabilities = normalized.get("capabilities")
        if raw_capabilities is None:
            raw_capabilities = {}
        if not isinstance(raw_capabilities, dict):
            raise ConfigError(f"Provider '{name}' capabilities must be a mapping")
        normalized["capabilities"] = {
            **raw_capabilities,
            "local": True,
            "cloud": False,
            "network_zone": "local",
        }
    elif contract == "image-provider":
        if backend != "openai-compat":
            raise ConfigError(
                f"Provider '{name}' contract 'image-provider' requires backend 'openai-compat'"
            )
        raw_capabilities = normalized.get("capabilities")
        if raw_capabilities is None:
            raw_capabilities = {}
        if not isinstance(raw_capabilities, dict):
            raise ConfigError(f"Provider '{name}' capabilities must be a mapping")
        normalized["capabilities"] = {
            **raw_capabilities,
            "image_generation": True,
        }

    normalized["limits"] = _normalize_provider_limits(name, normalized)
    if "max_tokens" in normalized and "max_output_tokens" not in normalized["limits"]:
        max_tokens = _normalize_positive_int(
            normalized.get("max_tokens"),
            field_name="max_tokens",
            provider_name=name,
        )
        if max_tokens is not None:
            normalized["max_tokens"] = max_tokens
            normalized["limits"]["max_output_tokens"] = max_tokens

    normalized["cache"] = _normalize_provider_cache(name, normalized)
    normalized["image"] = _normalize_provider_image(name, normalized)
    normalized["capabilities"] = _normalize_provider_capabilities(name, normalized)
    return normalized


def _normalize_providers(data: dict[str, Any]) -> dict[str, Any]:
    """Normalize every provider block before the Config object is created."""
    providers = data.get("providers", {})
    if not isinstance(providers, dict):
        raise ConfigError("'providers' must be a mapping")

    normalized = dict(data)
    normalized["providers"] = {
        name: _normalize_provider(name, cfg) for name, cfg in providers.items()
    }
    return normalized


def _normalize_string_list(
    value: Any, *, field_name: str, rule_name: str, allow_empty: bool = False
) -> list[str]:
    """Normalize a config field to a list of non-empty strings."""
    if value is None:
        return []
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, list):
        items = value
    else:
        raise ConfigError(f"Policy '{rule_name}' field '{field_name}' must be a string or list")

    normalized = []
    for item in items:
        if not isinstance(item, str) or not item.strip():
            raise ConfigError(
                f"Policy '{rule_name}' field '{field_name}' must contain non-empty strings"
            )
        normalized.append(item.strip())

    if not allow_empty and not normalized:
        raise ConfigError(f"Policy '{rule_name}' field '{field_name}' must not be empty")
    return normalized


def _normalize_policy_match(name: str, match: Any) -> dict[str, Any]:
    """Validate a policy match block."""
    if not isinstance(match, dict):
        raise ConfigError(f"Policy '{name}' match must be a mapping")
    return match


def _normalize_policy_select(name: str, select: Any, providers: dict[str, Any]) -> dict[str, Any]:
    """Validate a policy select block."""
    if not isinstance(select, dict):
        raise ConfigError(f"Policy '{name}' select must be a mapping")

    unknown = sorted(set(select) - _POLICY_SELECT_KEYS)
    if unknown:
        unknown_list = ", ".join(unknown)
        raise ConfigError(f"Policy '{name}' has unknown select keys: {unknown_list}")

    normalized = dict(select)
    provider_names = set(providers)

    for field_name in ("allow_providers", "deny_providers", "prefer_providers"):
        values = _normalize_string_list(
            normalized.get(field_name, []),
            field_name=field_name,
            rule_name=name,
            allow_empty=True,
        )
        unknown_providers = sorted(value for value in values if value not in provider_names)
        if unknown_providers:
            unknown_list = ", ".join(unknown_providers)
            raise ConfigError(
                f"Policy '{name}' field '{field_name}' references unknown providers: {unknown_list}"
            )
        normalized[field_name] = values

    normalized["prefer_tiers"] = _normalize_string_list(
        normalized.get("prefer_tiers", []),
        field_name="prefer_tiers",
        rule_name=name,
        allow_empty=True,
    )

    required_caps = _normalize_string_list(
        normalized.get("require_capabilities", []),
        field_name="require_capabilities",
        rule_name=name,
        allow_empty=True,
    )
    unknown_caps = sorted(cap for cap in required_caps if cap not in _ALL_CAPABILITY_FIELDS)
    if unknown_caps:
        unknown_list = ", ".join(unknown_caps)
        raise ConfigError(
            f"Policy '{name}' require_capabilities has unknown capability names: {unknown_list}"
        )
    normalized["require_capabilities"] = required_caps

    cap_values = normalized.get("capability_values", {})
    if cap_values is None:
        cap_values = {}
    if not isinstance(cap_values, dict):
        raise ConfigError(f"Policy '{name}' capability_values must be a mapping")

    normalized_cap_values: dict[str, list[Any]] = {}
    for cap_name, raw_values in cap_values.items():
        if cap_name not in _ALL_CAPABILITY_FIELDS:
            raise ConfigError(
                f"Policy '{name}' capability_values references unknown capability '{cap_name}'"
            )
        values = raw_values if isinstance(raw_values, list) else [raw_values]
        if not values:
            raise ConfigError(
                f"Policy '{name}' capability_values '{cap_name}' must not be an empty list"
            )
        normalized_values = []
        for value in values:
            if cap_name in _BOOL_CAPABILITY_FIELDS and not isinstance(value, bool):
                raise ConfigError(
                    f"Policy '{name}' capability_values '{cap_name}' must use boolean values"
                )
            if cap_name in _STRING_CAPABILITY_FIELDS:
                if not isinstance(value, str) or not value.strip():
                    raise ConfigError(
                        f"Policy '{name}' capability_values '{cap_name}' must use non-empty strings"
                    )
                value = value.strip()
            normalized_values.append(value)
        normalized_cap_values[cap_name] = normalized_values
    normalized["capability_values"] = normalized_cap_values

    if normalized["allow_providers"] and normalized["deny_providers"]:
        overlap = sorted(set(normalized["allow_providers"]) & set(normalized["deny_providers"]))
        if overlap:
            overlap_list = ", ".join(overlap)
            raise ConfigError(
                f"Policy '{name}' cannot allow and deny the same provider(s): {overlap_list}"
            )

    return normalized


def _normalize_routing_policies(data: dict[str, Any]) -> dict[str, Any]:
    """Validate the optional routing policy layer."""
    raw = data.get("routing_policies", {"enabled": False, "rules": []})
    if not isinstance(raw, dict):
        raise ConfigError("'routing_policies' must be a mapping")

    enabled = raw.get("enabled", False)
    if not isinstance(enabled, bool):
        raise ConfigError("'routing_policies.enabled' must be a boolean")

    rules = raw.get("rules", [])
    if rules is None:
        rules = []
    if not isinstance(rules, list):
        raise ConfigError("'routing_policies.rules' must be a list")

    providers = data.get("providers", {})
    normalized_rules = []
    for idx, rule in enumerate(rules, start=1):
        if not isinstance(rule, dict):
            raise ConfigError(f"Policy rule #{idx} must be a mapping")
        name = rule.get("name", "").strip()
        if not name:
            raise ConfigError(f"Policy rule #{idx} must define a non-empty 'name'")
        normalized_rules.append(
            {
                "name": name,
                "match": _normalize_policy_match(name, rule.get("match", {})),
                "select": _normalize_policy_select(name, rule.get("select", {}), providers),
            }
        )

    normalized = dict(data)
    normalized["routing_policies"] = {"enabled": enabled, "rules": normalized_rules}
    return normalized


def _normalize_client_profile_match(name: str, match: Any) -> dict[str, Any]:
    """Validate a client profile match block."""
    if not isinstance(match, dict):
        raise ConfigError(f"Client profile rule '{name}' match must be a mapping")
    unknown = sorted(set(match) - _CLIENT_PROFILE_MATCH_KEYS)
    if unknown:
        unknown_list = ", ".join(unknown)
        raise ConfigError(f"Client profile rule '{name}' has unknown match keys: {unknown_list}")

    if "header_present" in match:
        match["header_present"] = _normalize_string_list(
            match["header_present"],
            field_name="header_present",
            rule_name=f"client profile rule '{name}'",
            allow_empty=False,
        )

    if "header_contains" in match:
        if not isinstance(match["header_contains"], dict):
            raise ConfigError(
                f"Client profile rule '{name}' field 'header_contains' must be a mapping"
            )
        normalized_header_contains = {}
        for header_name, values in match["header_contains"].items():
            if not isinstance(header_name, str) or not header_name.strip():
                raise ConfigError(
                    f"Client profile rule '{name}' field 'header_contains' "
                    "must use non-empty header names"
                )
            normalized_header_contains[header_name.strip().lower()] = _normalize_string_list(
                values,
                field_name="header_contains",
                rule_name=f"client profile rule '{name}'",
                allow_empty=False,
            )
        match["header_contains"] = normalized_header_contains

    for compound in ("any", "all"):
        if compound in match:
            values = match[compound]
            if not isinstance(values, list) or not values:
                raise ConfigError(
                    f"Client profile rule '{name}' field '{compound}' must be a non-empty list"
                )
            match[compound] = [_normalize_client_profile_match(name, item) for item in values]

    return match


def _normalize_client_profiles(data: dict[str, Any]) -> dict[str, Any]:
    """Validate the optional client profile layer."""
    raw = data.get(
        "client_profiles",
        {"enabled": False, "default": "generic", "profiles": {"generic": {}}, "rules": []},
    )
    if not isinstance(raw, dict):
        raise ConfigError("'client_profiles' must be a mapping")

    enabled = raw.get("enabled", False)
    if not isinstance(enabled, bool):
        raise ConfigError("'client_profiles.enabled' must be a boolean")

    default_profile = raw.get("default", "generic")
    if not isinstance(default_profile, str) or not default_profile.strip():
        raise ConfigError("'client_profiles.default' must be a non-empty string")
    default_profile = default_profile.strip()

    profiles = raw.get("profiles", {})
    if profiles is None:
        profiles = {}
    if not isinstance(profiles, dict):
        raise ConfigError("'client_profiles.profiles' must be a mapping")

    presets = raw.get("presets", [])
    if presets is None:
        presets = []
    presets = _normalize_string_list(
        presets,
        field_name="presets",
        rule_name="client_profiles",
        allow_empty=True,
    )
    unknown_presets = sorted(set(presets) - _SUPPORTED_CLIENT_PROFILE_PRESETS)
    if unknown_presets:
        unknown_list = ", ".join(unknown_presets)
        raise ConfigError(f"'client_profiles.presets' has unknown preset names: {unknown_list}")

    normalized_profiles = {}
    for preset_name in presets:
        preset = _CLIENT_PROFILE_PRESET_SPECS[preset_name]
        normalized_profiles[preset_name] = _normalize_policy_select(
            f"client profile '{preset_name}'",
            dict(preset["profile"]),
            data.get("providers", {}),
        )

    for profile_name, hints in profiles.items():
        if not isinstance(profile_name, str) or not profile_name.strip():
            raise ConfigError("Client profile names must be non-empty strings")
        if hints is None:
            hints = {}
        normalized_profiles[profile_name.strip()] = _normalize_policy_select(
            f"client profile '{profile_name.strip()}'",
            hints,
            data.get("providers", {}),
        )

    if default_profile not in normalized_profiles:
        normalized_profiles.setdefault(
            default_profile,
            _normalize_policy_select(
                f"client profile '{default_profile}'", {}, data.get("providers", {})
            ),
        )

    rules = raw.get("rules", [])
    if rules is None:
        rules = []
    if not isinstance(rules, list):
        raise ConfigError("'client_profiles.rules' must be a list")

    normalized_rules = []
    seen_rule_profiles = set()
    for preset_name in presets:
        preset_rule = _CLIENT_PROFILE_PRESET_SPECS[preset_name]["rule"]
        normalized_rules.append(
            {
                "profile": preset_name,
                "match": _normalize_client_profile_match(preset_name, dict(preset_rule["match"])),
            }
        )
        seen_rule_profiles.add(preset_name)

    for idx, rule in enumerate(rules, start=1):
        if not isinstance(rule, dict):
            raise ConfigError(f"Client profile rule #{idx} must be a mapping")
        profile_name = rule.get("profile", "")
        if not isinstance(profile_name, str) or not profile_name.strip():
            raise ConfigError(f"Client profile rule #{idx} must define a non-empty 'profile'")
        profile_name = profile_name.strip()
        if profile_name not in normalized_profiles:
            raise ConfigError(
                f"Client profile rule #{idx} references unknown profile '{profile_name}'"
            )
        if profile_name in seen_rule_profiles:
            normalized_rules = [r for r in normalized_rules if r["profile"] != profile_name]
        normalized_rules.append(
            {
                "profile": profile_name,
                "match": _normalize_client_profile_match(profile_name, rule.get("match", {})),
            }
        )
        seen_rule_profiles.add(profile_name)

    normalized = dict(data)
    normalized["client_profiles"] = {
        "enabled": enabled,
        "default": default_profile,
        "presets": presets,
        "profiles": normalized_profiles,
        "rules": normalized_rules,
    }
    return normalized


def _normalize_request_hooks(data: dict[str, Any]) -> dict[str, Any]:
    """Validate the optional request hook pipeline."""
    raw = data.get("request_hooks", {"enabled": False, "hooks": []})
    if not isinstance(raw, dict):
        raise ConfigError("'request_hooks' must be a mapping")

    enabled = raw.get("enabled", False)
    if not isinstance(enabled, bool):
        raise ConfigError("'request_hooks.enabled' must be a boolean")
    on_error = raw.get("on_error", "continue")
    if on_error not in {"continue", "fail"}:
        raise ConfigError("'request_hooks.on_error' must be 'continue' or 'fail'")

    hooks = _normalize_string_list(
        raw.get("hooks", []),
        field_name="hooks",
        rule_name="request_hooks",
        allow_empty=True,
    )
    unknown_hooks = sorted(set(hooks) - _SUPPORTED_REQUEST_HOOKS)
    if unknown_hooks:
        unknown_list = ", ".join(unknown_hooks)
        raise ConfigError(f"'request_hooks.hooks' has unknown hook names: {unknown_list}")

    normalized = dict(data)
    normalized["request_hooks"] = {
        "enabled": enabled,
        "hooks": hooks,
        "on_error": on_error,
    }
    return normalized


def _normalize_update_check(data: dict[str, Any]) -> dict[str, Any]:
    """Validate optional update-check configuration."""
    raw = data.get("update_check", {})
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ConfigError("'update_check' must be a mapping")

    enabled = raw.get("enabled", True)
    if not isinstance(enabled, bool):
        raise ConfigError("'update_check.enabled' must be a boolean")

    repository = raw.get("repository", "typelicious/FoundryGate")
    if not isinstance(repository, str) or "/" not in repository or not repository.strip():
        raise ConfigError("'update_check.repository' must be an owner/repo string")

    api_base = raw.get("api_base", "https://api.github.com")
    if not isinstance(api_base, str) or not api_base.strip():
        raise ConfigError("'update_check.api_base' must be a non-empty string")

    timeout_seconds = raw.get("timeout_seconds", 5)
    if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float)):
        raise ConfigError("'update_check.timeout_seconds' must be a positive number")
    if timeout_seconds <= 0:
        raise ConfigError("'update_check.timeout_seconds' must be positive")

    check_interval_seconds = raw.get("check_interval_seconds", 21600)
    if isinstance(check_interval_seconds, bool) or not isinstance(check_interval_seconds, int):
        raise ConfigError("'update_check.check_interval_seconds' must be a positive integer")
    if check_interval_seconds <= 0:
        raise ConfigError("'update_check.check_interval_seconds' must be positive")

    release_channel = raw.get("release_channel", "stable")
    if release_channel not in {"stable", "preview"}:
        raise ConfigError("'update_check.release_channel' must be 'stable' or 'preview'")

    normalized = dict(data)
    normalized["update_check"] = {
        "enabled": enabled,
        "repository": repository.strip(),
        "api_base": api_base.strip().rstrip("/"),
        "timeout_seconds": float(timeout_seconds),
        "check_interval_seconds": check_interval_seconds,
        "release_channel": release_channel,
    }
    return normalized


def _normalize_auto_update(data: dict[str, Any]) -> dict[str, Any]:
    """Validate optional auto-update helper configuration."""
    raw = data.get("auto_update", {})
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ConfigError("'auto_update' must be a mapping")

    enabled = raw.get("enabled", False)
    if not isinstance(enabled, bool):
        raise ConfigError("'auto_update.enabled' must be a boolean")

    allow_major = raw.get("allow_major", False)
    if not isinstance(allow_major, bool):
        raise ConfigError("'auto_update.allow_major' must be a boolean")

    rollout_ring = raw.get("rollout_ring", "early")
    if rollout_ring not in {"stable", "early", "canary"}:
        raise ConfigError("'auto_update.rollout_ring' must be 'stable', 'early', or 'canary'")

    require_healthy_providers = raw.get("require_healthy_providers", True)
    if not isinstance(require_healthy_providers, bool):
        raise ConfigError("'auto_update.require_healthy_providers' must be a boolean")

    max_unhealthy_providers = raw.get("max_unhealthy_providers", 0)
    if isinstance(max_unhealthy_providers, bool) or not isinstance(max_unhealthy_providers, int):
        raise ConfigError("'auto_update.max_unhealthy_providers' must be a non-negative integer")
    if max_unhealthy_providers < 0:
        raise ConfigError("'auto_update.max_unhealthy_providers' must be non-negative")

    apply_command = raw.get("apply_command", "foundrygate-update")
    if not isinstance(apply_command, str) or not apply_command.strip():
        raise ConfigError("'auto_update.apply_command' must be a non-empty string")

    normalized = dict(data)
    normalized["auto_update"] = {
        "enabled": enabled,
        "allow_major": allow_major,
        "rollout_ring": rollout_ring,
        "require_healthy_providers": require_healthy_providers,
        "max_unhealthy_providers": max_unhealthy_providers,
        "apply_command": apply_command.strip(),
    }
    return normalized


class Config:
    """Holds the parsed and expanded configuration."""

    def __init__(self, data: dict):
        self._data = data

    # ── Accessors ──────────────────────────────────────────────────────────

    @property
    def server(self) -> dict:
        return self._data.get("server", {})

    @property
    def providers(self) -> dict:
        return self._data.get("providers", {})

    @property
    def fallback_chain(self) -> list[str]:
        return self._data.get("fallback_chain", [])

    @property
    def static_rules(self) -> dict:
        return self._data.get("static_rules", {"enabled": False, "rules": []})

    @property
    def heuristic_rules(self) -> dict:
        return self._data.get("heuristic_rules", {"enabled": False, "rules": []})

    @property
    def routing_policies(self) -> dict:
        return self._data.get("routing_policies", {"enabled": False, "rules": []})

    @property
    def client_profiles(self) -> dict:
        return self._data.get(
            "client_profiles",
            {"enabled": False, "default": "generic", "profiles": {"generic": {}}, "rules": []},
        )

    @property
    def request_hooks(self) -> dict:
        return self._data.get(
            "request_hooks",
            {"enabled": False, "hooks": [], "on_error": "continue"},
        )

    @property
    def llm_classifier(self) -> dict:
        return self._data.get("llm_classifier", {"enabled": False})

    @property
    def health(self) -> dict:
        return self._data.get("health", {})

    @property
    def metrics(self) -> dict:
        raw = self._data.get("metrics", {"enabled": False})
        # Patch in a safe DB path so callers never see ./foundrygate.db
        configured = raw.get("db_path") if isinstance(raw, dict) else None
        safe = _safe_db_path(configured)
        if isinstance(raw, dict):
            return {**raw, "db_path": safe}
        return {"enabled": False, "db_path": safe}

    @property
    def update_check(self) -> dict:
        return self._data.get(
            "update_check",
            {
                "enabled": True,
                "repository": "typelicious/FoundryGate",
                "api_base": "https://api.github.com",
                "timeout_seconds": 5.0,
                "check_interval_seconds": 21600,
                "release_channel": "stable",
            },
        )

    @property
    def auto_update(self) -> dict:
        return self._data.get(
            "auto_update",
            {
                "enabled": False,
                "allow_major": False,
                "rollout_ring": "early",
                "require_healthy_providers": True,
                "max_unhealthy_providers": 0,
                "apply_command": "foundrygate-update",
            },
        )

    def provider(self, name: str) -> dict | None:
        return self.providers.get(name)


def load_config(path: str | Path | None = None) -> Config:
    """Load config.yaml, expand env vars, return Config object."""
    load_dotenv()

    if path is None:
        # Look next to the package, then cwd
        candidates = [
            Path(__file__).resolve().parent.parent / "config.yaml",
            Path.cwd() / "config.yaml",
        ]
        for c in candidates:
            if c.exists():
                path = c
                break
        else:
            raise FileNotFoundError("config.yaml not found")

    path = Path(path)
    with path.open() as f:
        raw = yaml.safe_load(f)

    expanded = _normalize_auto_update(
        _normalize_update_check(
            _normalize_request_hooks(
                _normalize_client_profiles(
                    _normalize_routing_policies(_normalize_providers(_walk_expand(raw)))
                )
            )
        )
    )
    return Config(expanded)
