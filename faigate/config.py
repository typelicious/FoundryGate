"""Configuration loader with environment variable expansion.

DB path resolution
------------------
The metrics database path is resolved in this priority order:

1. FAIGATE_DB_PATH environment variable  (explicit override)
2. metrics.db_path in config.yaml         (if set)
3. XDG_DATA_HOME / faigate / faigate.db (Linux/XDG default)
4. ~/.local/share/faigate/faigate.db    (fallback for non-XDG systems)

The path NEVER defaults to ./faigate.db in the repo working directory.
This ensures no database files are accidentally committed.

On Linux / systemd the recommended path is /var/lib/faigate/faigate.db,
set via FAIGATE_DB_PATH in the service environment.
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
from .lane_registry import get_provider_lane_binding

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
_SUPPORTED_ROUTING_MODE_KEYS = {"aliases", "description", "best_for", "savings", "select"}
_SUPPORTED_MODEL_SHORTCUT_KEYS = {"aliases", "description", "target"}
_CLIENT_PROFILE_MATCH_KEYS = {"header_contains", "header_present", "any", "all"}
_SUPPORTED_CLIENT_PROFILE_PRESETS = {"openclaw", "n8n", "cli"}
_SUPPORTED_REQUEST_HOOKS = set(get_registered_request_hooks())
_SUPPORTED_WINDOW_DAYS = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}
_SUPPORTED_PROVIDER_LANE_KEYS = {
    "family",
    "name",
    "canonical_model",
    "route_type",
    "cluster",
    "benchmark_cluster",
    "quality_tier",
    "reasoning_strength",
    "context_strength",
    "tool_strength",
    "same_model_group",
    "degrade_to",
}
_SUPPORTED_PROVIDER_ROUTE_TYPES = {"direct", "aggregator", "wallet-router", "local"}

_CLIENT_PROFILE_PRESET_SPECS: dict[str, dict[str, Any]] = {
    "openclaw": {
        "profile": {"prefer_tiers": ["default", "reasoning"]},
        "rule": {
            "profile": "openclaw",
            "match": {
                "any": [
                    {"header_present": ["x-openclaw-source"]},
                    {"header_contains": {"x-faigate-client": ["openclaw"]}},
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
                    "x-faigate-client": ["n8n"],
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
                    "x-faigate-client": ["cli", "codex", "claude", "kilocode", "deepseek"],
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
      1. FAIGATE_DB_PATH env var
      2. configured value from config.yaml (if not empty / not a relative ./)
      3. XDG_DATA_HOME/faigate/faigate.db
      4. ~/.local/share/faigate/faigate.db
    """
    # 1. Env var always wins
    env_path = os.environ.get("FAIGATE_DB_PATH", "").strip()
    if env_path:
        return env_path

    # 2. Explicit config value – but reject ./faigate.db* to prevent repo pollution
    if configured:
        p = configured.strip()
        if p and not p.startswith("./faigate.db") and p != "faigate.db":
            return p

    # 3. XDG_DATA_HOME
    xdg = os.environ.get("XDG_DATA_HOME", "").strip()
    if xdg:
        return str(Path(xdg) / "faigate" / "faigate.db")

    # 4. ~/.local/share/faigate/faigate.db
    return str(Path.home() / ".local" / "share" / "faigate" / "faigate.db")


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


def _validate_provider_base_url(name: str, base_url: str) -> str:
    """Validate provider base URLs against the current trust-boundary baseline."""
    parsed = urlparse(base_url)
    scheme = (parsed.scheme or "").strip().lower()
    if scheme not in {"http", "https"}:
        raise ConfigError(
            "Provider "
            f"'{name}' base_url must use http or https "
            f"(got '{parsed.scheme or 'missing'}')"
        )

    if not parsed.netloc:
        raise ConfigError(f"Provider '{name}' base_url must include a host")

    if scheme == "http" and not _looks_local_base_url(base_url):
        raise ConfigError(
            "Provider "
            f"'{name}' base_url must use https unless it points "
            "to local/private network space"
        )

    return base_url


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


def _normalize_provider_lane(name: str, cfg: dict[str, Any]) -> dict[str, Any]:
    """Validate optional lane metadata used by adaptive routing."""
    defaults = get_provider_lane_binding(name)
    raw = cfg.get("lane", {})
    if raw in (None, ""):
        raw = {}
    if not isinstance(raw, dict):
        raise ConfigError(f"Provider '{name}' field 'lane' must be a mapping")

    lane = {**defaults, **raw}
    if not lane:
        return {}

    unknown = sorted(set(lane) - _SUPPORTED_PROVIDER_LANE_KEYS)
    if unknown:
        unknown_list = ", ".join(unknown)
        raise ConfigError(f"Provider '{name}' lane has unknown keys: {unknown_list}")

    required = ("family", "name", "canonical_model", "route_type")
    normalized: dict[str, Any] = {}
    for field_name in required:
        value = lane.get(field_name, "")
        if not isinstance(value, str) or not value.strip():
            raise ConfigError(f"Provider '{name}' lane.{field_name} must be a non-empty string")
        normalized[field_name] = value.strip()

    if normalized["route_type"] not in _SUPPORTED_PROVIDER_ROUTE_TYPES:
        supported = ", ".join(sorted(_SUPPORTED_PROVIDER_ROUTE_TYPES))
        raise ConfigError(
            f"Provider '{name}' lane.route_type uses unsupported value "
            f"'{normalized['route_type']}' (supported: {supported})"
        )

    for field_name in (
        "cluster",
        "benchmark_cluster",
        "quality_tier",
        "reasoning_strength",
        "context_strength",
        "tool_strength",
        "same_model_group",
    ):
        value = lane.get(field_name, "")
        if value in (None, ""):
            normalized[field_name] = ""
            continue
        if not isinstance(value, str) or not value.strip():
            raise ConfigError(f"Provider '{name}' lane.{field_name} must be a non-empty string")
        normalized[field_name] = value.strip()

    degrade_to = lane.get("degrade_to", [])
    if degrade_to in (None, ""):
        degrade_to = []
    if isinstance(degrade_to, str):
        degrade_to = [degrade_to]
    if not isinstance(degrade_to, list):
        raise ConfigError(f"Provider '{name}' lane.degrade_to must be a list")
    normalized["degrade_to"] = []
    for item in degrade_to:
        if not isinstance(item, str) or not item.strip():
            raise ConfigError(
                f"Provider '{name}' lane.degrade_to must contain non-empty strings"
            )
        normalized["degrade_to"].append(item.strip())

    return normalized


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
    normalized["base_url"] = _validate_provider_base_url(name, str(normalized["base_url"]).strip())

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
    normalized["lane"] = _normalize_provider_lane(name, normalized)
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


def _normalize_policy_select(
    name: str,
    select: Any,
    providers: dict[str, Any],
    *,
    extra_keys: set[str] | None = None,
) -> dict[str, Any]:
    """Validate a policy select block."""
    if not isinstance(select, dict):
        raise ConfigError(f"Policy '{name}' select must be a mapping")

    supported_keys = set(_POLICY_SELECT_KEYS)
    if extra_keys:
        supported_keys |= set(extra_keys)

    unknown = sorted(set(select) - supported_keys)
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

    if extra_keys and "routing_mode" in extra_keys:
        routing_mode = normalized.get("routing_mode", "")
        if routing_mode in (None, ""):
            normalized["routing_mode"] = ""
        elif not isinstance(routing_mode, str) or not routing_mode.strip():
            raise ConfigError(f"Policy '{name}' field 'routing_mode' must be a non-empty string")
        else:
            normalized["routing_mode"] = routing_mode.strip()

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
            extra_keys={"routing_mode"},
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
            extra_keys={"routing_mode"},
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


def _normalize_routing_modes(data: dict[str, Any]) -> dict[str, Any]:
    """Validate optional virtual routing modes."""
    raw = data.get("routing_modes", {"enabled": False, "default": "auto", "modes": {}})
    if raw in (None, ""):
        raw = {"enabled": False, "default": "auto", "modes": {}}
    if not isinstance(raw, dict):
        raise ConfigError("'routing_modes' must be a mapping")

    enabled = raw.get("enabled", False)
    if not isinstance(enabled, bool):
        raise ConfigError("'routing_modes.enabled' must be a boolean")

    default_mode = raw.get("default", "auto")
    if not isinstance(default_mode, str) or not default_mode.strip():
        raise ConfigError("'routing_modes.default' must be a non-empty string")
    default_mode = default_mode.strip()

    raw_modes = raw.get("modes", {})
    if raw_modes is None:
        raw_modes = {}
    if not isinstance(raw_modes, dict):
        raise ConfigError("'routing_modes.modes' must be a mapping")

    normalized_modes: dict[str, dict[str, Any]] = {}
    seen_aliases: dict[str, str] = {}
    provider_names = data.get("providers", {})

    for mode_name, spec in raw_modes.items():
        if not isinstance(mode_name, str) or not mode_name.strip():
            raise ConfigError("Routing mode names must be non-empty strings")
        if not isinstance(spec, dict):
            raise ConfigError(f"Routing mode '{mode_name}' must be a mapping")

        normalized_name = mode_name.strip()
        unknown = sorted(set(spec) - _SUPPORTED_ROUTING_MODE_KEYS)
        if unknown:
            unknown_list = ", ".join(unknown)
            raise ConfigError(f"Routing mode '{normalized_name}' has unknown keys: {unknown_list}")

        aliases = _normalize_string_list(
            spec.get("aliases", []),
            field_name="aliases",
            rule_name=f"routing mode '{normalized_name}'",
            allow_empty=True,
        )
        for alias in [normalized_name, *aliases]:
            owner = seen_aliases.get(alias)
            if owner and owner != normalized_name:
                raise ConfigError(
                    f"Routing mode alias '{alias}' is already used by routing mode '{owner}'"
                )
            seen_aliases[alias] = normalized_name

        normalized_modes[normalized_name] = {
            "aliases": aliases,
            "description": str(spec.get("description", "") or "").strip(),
            "best_for": str(spec.get("best_for", "") or "").strip(),
            "savings": str(spec.get("savings", "") or "").strip(),
            "select": _normalize_policy_select(
                f"routing mode '{normalized_name}'",
                dict(spec.get("select", {}) or {}),
                provider_names,
            ),
        }

    if default_mode != "auto" and default_mode not in normalized_modes:
        raise ConfigError(f"'routing_modes.default' references unknown mode '{default_mode}'")

    normalized = dict(data)
    normalized["routing_modes"] = {
        "enabled": enabled,
        "default": default_mode,
        "modes": normalized_modes,
    }
    return normalized


def _normalize_model_shortcuts(data: dict[str, Any]) -> dict[str, Any]:
    """Validate explicit shortcut names that map to concrete providers."""
    raw = data.get("model_shortcuts", {"enabled": False, "shortcuts": {}})
    if raw in (None, ""):
        raw = {"enabled": False, "shortcuts": {}}
    if not isinstance(raw, dict):
        raise ConfigError("'model_shortcuts' must be a mapping")

    enabled = raw.get("enabled", False)
    if not isinstance(enabled, bool):
        raise ConfigError("'model_shortcuts.enabled' must be a boolean")

    raw_shortcuts = raw.get("shortcuts", {})
    if raw_shortcuts is None:
        raw_shortcuts = {}
    if not isinstance(raw_shortcuts, dict):
        raise ConfigError("'model_shortcuts.shortcuts' must be a mapping")

    provider_names = set(data.get("providers", {}))
    mode_names = set((data.get("routing_modes") or {}).get("modes", {}))
    normalized_shortcuts: dict[str, dict[str, Any]] = {}
    seen_aliases: dict[str, str] = {}

    for shortcut_name, spec in raw_shortcuts.items():
        if not isinstance(shortcut_name, str) or not shortcut_name.strip():
            raise ConfigError("Model shortcut names must be non-empty strings")
        if not isinstance(spec, dict):
            raise ConfigError(f"Model shortcut '{shortcut_name}' must be a mapping")

        normalized_name = shortcut_name.strip()
        unknown = sorted(set(spec) - _SUPPORTED_MODEL_SHORTCUT_KEYS)
        if unknown:
            unknown_list = ", ".join(unknown)
            raise ConfigError(
                f"Model shortcut '{normalized_name}' has unknown keys: {unknown_list}"
            )

        target = spec.get("target", "")
        if not isinstance(target, str) or not target.strip():
            raise ConfigError(f"Model shortcut '{normalized_name}' must define a non-empty target")
        target = target.strip()
        if target not in provider_names:
            raise ConfigError(
                f"Model shortcut '{normalized_name}' references unknown provider '{target}'"
            )
        if normalized_name in mode_names:
            raise ConfigError(
                "Model shortcut "
                f"'{normalized_name}' conflicts with routing mode '{normalized_name}'"
            )

        aliases = _normalize_string_list(
            spec.get("aliases", []),
            field_name="aliases",
            rule_name=f"model shortcut '{normalized_name}'",
            allow_empty=True,
        )
        for alias in [normalized_name, *aliases]:
            owner = seen_aliases.get(alias)
            if owner and owner != normalized_name:
                raise ConfigError(
                    f"Model shortcut alias '{alias}' is already used by model shortcut '{owner}'"
                )
            if alias in mode_names:
                raise ConfigError(
                    f"Model shortcut alias '{alias}' conflicts with routing mode '{alias}'"
                )
            seen_aliases[alias] = normalized_name

        normalized_shortcuts[normalized_name] = {
            "aliases": aliases,
            "description": str(spec.get("description", "") or "").strip(),
            "target": target,
        }

    normalized = dict(data)
    normalized["model_shortcuts"] = {
        "enabled": enabled,
        "shortcuts": normalized_shortcuts,
    }
    return normalized


def _validate_routing_mode_references(data: dict[str, Any]) -> dict[str, Any]:
    """Ensure profile-level routing_mode references existing routing modes."""
    mode_names = set((data.get("routing_modes") or {}).get("modes", {}))
    for profile_name, hints in (data.get("client_profiles") or {}).get("profiles", {}).items():
        routing_mode = str((hints or {}).get("routing_mode", "") or "").strip()
        if routing_mode and routing_mode not in mode_names:
            raise ConfigError(
                f"Client profile '{profile_name}' references unknown routing_mode '{routing_mode}'"
            )
    return data


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

    repository = raw.get("repository", "fusionAIze/faigate")
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

    min_release_age_hours = raw.get("min_release_age_hours", 0)
    if isinstance(min_release_age_hours, bool) or not isinstance(min_release_age_hours, int):
        raise ConfigError("'auto_update.min_release_age_hours' must be a non-negative integer")
    if min_release_age_hours < 0:
        raise ConfigError("'auto_update.min_release_age_hours' must be non-negative")

    provider_scope = raw.get("provider_scope", {})
    if provider_scope is None:
        provider_scope = {}
    if not isinstance(provider_scope, dict):
        raise ConfigError("'auto_update.provider_scope' must be a mapping")

    provider_names = set((data.get("providers") or {}).keys())
    allow_providers = _normalize_string_list(
        provider_scope.get("allow_providers", []),
        field_name="allow_providers",
        rule_name="auto_update.provider_scope",
        allow_empty=True,
    )
    deny_providers = _normalize_string_list(
        provider_scope.get("deny_providers", []),
        field_name="deny_providers",
        rule_name="auto_update.provider_scope",
        allow_empty=True,
    )
    unknown_allowed = sorted(name for name in allow_providers if name not in provider_names)
    if unknown_allowed:
        raise ConfigError(
            "'auto_update.provider_scope.allow_providers' references unknown providers: "
            + ", ".join(unknown_allowed)
        )
    unknown_denied = sorted(name for name in deny_providers if name not in provider_names)
    if unknown_denied:
        raise ConfigError(
            "'auto_update.provider_scope.deny_providers' references unknown providers: "
            + ", ".join(unknown_denied)
        )
    overlap = sorted(set(allow_providers) & set(deny_providers))
    if overlap:
        raise ConfigError(
            "'auto_update.provider_scope' cannot allow and deny the same providers: "
            + ", ".join(overlap)
        )

    verification = raw.get("verification", {})
    if verification is None:
        verification = {}
    if not isinstance(verification, dict):
        raise ConfigError("'auto_update.verification' must be a mapping")

    verification_enabled = verification.get("enabled", False)
    if not isinstance(verification_enabled, bool):
        raise ConfigError("'auto_update.verification.enabled' must be a boolean")

    verification_command = verification.get("command", "faigate-health")
    if not isinstance(verification_command, str) or not verification_command.strip():
        raise ConfigError("'auto_update.verification.command' must be a non-empty string")

    verification_timeout_seconds = verification.get("timeout_seconds", 30)
    if isinstance(verification_timeout_seconds, bool) or not isinstance(
        verification_timeout_seconds, int
    ):
        raise ConfigError("'auto_update.verification.timeout_seconds' must be an integer")
    if verification_timeout_seconds <= 0:
        raise ConfigError("'auto_update.verification.timeout_seconds' must be positive")

    rollback_command = verification.get("rollback_command", "")
    if not isinstance(rollback_command, str):
        raise ConfigError("'auto_update.verification.rollback_command' must be a string")

    maintenance_window = raw.get("maintenance_window", {})
    if maintenance_window is None:
        maintenance_window = {}
    if not isinstance(maintenance_window, dict):
        raise ConfigError("'auto_update.maintenance_window' must be a mapping")

    window_enabled = maintenance_window.get("enabled", False)
    if not isinstance(window_enabled, bool):
        raise ConfigError("'auto_update.maintenance_window.enabled' must be a boolean")

    timezone = maintenance_window.get("timezone", "UTC")
    if not isinstance(timezone, str) or not timezone.strip():
        raise ConfigError("'auto_update.maintenance_window.timezone' must be a non-empty string")

    days = _normalize_string_list(
        maintenance_window.get("days", []),
        field_name="days",
        rule_name="auto_update.maintenance_window",
        allow_empty=True,
    )
    unknown_days = sorted(set(days) - _SUPPORTED_WINDOW_DAYS)
    if unknown_days:
        raise ConfigError(
            "'auto_update.maintenance_window.days' has unknown weekday values: "
            + ", ".join(unknown_days)
        )

    start_hour = maintenance_window.get("start_hour", 0)
    end_hour = maintenance_window.get("end_hour", 24)
    for key, value in {"start_hour": start_hour, "end_hour": end_hour}.items():
        if isinstance(value, bool) or not isinstance(value, int):
            raise ConfigError(f"'auto_update.maintenance_window.{key}' must be an integer")
    if not 0 <= start_hour <= 23:
        raise ConfigError("'auto_update.maintenance_window.start_hour' must be between 0 and 23")
    if not 1 <= end_hour <= 24:
        raise ConfigError("'auto_update.maintenance_window.end_hour' must be between 1 and 24")
    if start_hour == end_hour:
        raise ConfigError("'auto_update.maintenance_window' must not use the same start/end hour")

    apply_command = raw.get("apply_command", "faigate-update")
    if not isinstance(apply_command, str) or not apply_command.strip():
        raise ConfigError("'auto_update.apply_command' must be a non-empty string")

    normalized = dict(data)
    normalized["auto_update"] = {
        "enabled": enabled,
        "allow_major": allow_major,
        "rollout_ring": rollout_ring,
        "require_healthy_providers": require_healthy_providers,
        "max_unhealthy_providers": max_unhealthy_providers,
        "min_release_age_hours": min_release_age_hours,
        "provider_scope": {
            "allow_providers": allow_providers,
            "deny_providers": deny_providers,
        },
        "verification": {
            "enabled": verification_enabled,
            "command": verification_command.strip(),
            "timeout_seconds": verification_timeout_seconds,
            "rollback_command": rollback_command.strip(),
        },
        "maintenance_window": {
            "enabled": window_enabled,
            "timezone": timezone.strip(),
            "days": days,
            "start_hour": start_hour,
            "end_hour": end_hour,
        },
        "apply_command": apply_command.strip(),
    }
    return normalized


def _normalize_security(data: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize runtime security settings."""
    raw = data.get("security") or {}
    if raw in (None, ""):
        raw = {}
    if not isinstance(raw, dict):
        raise ConfigError("'security' must be a mapping")

    normalized = dict(data)
    normalized["security"] = {
        "response_headers": bool(raw.get("response_headers", True)),
        "cache_control": str(raw.get("cache_control", "no-store")).strip() or "no-store",
        "max_json_body_bytes": _normalize_positive_int(
            raw.get("max_json_body_bytes", 1_048_576),
            field_name="security.max_json_body_bytes",
            provider_name="runtime",
        )
        or 1_048_576,
        "max_upload_bytes": _normalize_positive_int(
            raw.get("max_upload_bytes", 10_485_760),
            field_name="security.max_upload_bytes",
            provider_name="runtime",
        )
        or 10_485_760,
        "max_header_value_chars": _normalize_positive_int(
            raw.get("max_header_value_chars", 160),
            field_name="security.max_header_value_chars",
            provider_name="runtime",
        )
        or 160,
    }
    return normalized


def _normalize_provider_catalog_check(data: dict[str, Any]) -> dict[str, Any]:
    """Validate provider-catalog drift/freshness checks."""
    raw = data.get("provider_catalog_check") or {}
    if raw in (None, ""):
        raw = {}
    if not isinstance(raw, dict):
        raise ConfigError("'provider_catalog_check' must be a mapping")

    max_catalog_age_days = raw.get("max_catalog_age_days", 30)
    if isinstance(max_catalog_age_days, bool) or not isinstance(max_catalog_age_days, int):
        raise ConfigError("'provider_catalog_check.max_catalog_age_days' must be an integer")
    if max_catalog_age_days < 0:
        raise ConfigError("'provider_catalog_check.max_catalog_age_days' must be non-negative")

    normalized = dict(data)
    normalized["provider_catalog_check"] = {
        "enabled": bool(raw.get("enabled", True)),
        "warn_on_untracked": bool(raw.get("warn_on_untracked", True)),
        "warn_on_model_drift": bool(raw.get("warn_on_model_drift", True)),
        "warn_on_unofficial_sources": bool(raw.get("warn_on_unofficial_sources", True)),
        "warn_on_volatile_offers": bool(raw.get("warn_on_volatile_offers", True)),
        "max_catalog_age_days": max_catalog_age_days,
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
    def routing_modes(self) -> dict:
        return self._data.get(
            "routing_modes",
            {"enabled": False, "default": "auto", "modes": {}},
        )

    @property
    def model_shortcuts(self) -> dict:
        return self._data.get(
            "model_shortcuts",
            {"enabled": False, "shortcuts": {}},
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
        # Patch in a safe DB path so callers never see ./faigate.db
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
                "repository": "fusionAIze/faigate",
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
                "min_release_age_hours": 0,
                "provider_scope": {
                    "allow_providers": [],
                    "deny_providers": [],
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
                    "days": [],
                    "start_hour": 0,
                    "end_hour": 24,
                },
                "apply_command": "faigate-update",
            },
        )

    @property
    def security(self) -> dict:
        return self._data.get(
            "security",
            {
                "response_headers": True,
                "cache_control": "no-store",
                "max_json_body_bytes": 1_048_576,
                "max_upload_bytes": 10_485_760,
                "max_header_value_chars": 160,
            },
        )

    @property
    def provider_catalog_check(self) -> dict:
        return self._data.get(
            "provider_catalog_check",
            {
                "enabled": True,
                "warn_on_untracked": True,
                "warn_on_model_drift": True,
                "max_catalog_age_days": 30,
            },
        )

    def provider(self, name: str) -> dict | None:
        return self.providers.get(name)


def load_config(path: str | Path | None = None) -> Config:
    """Load config.yaml, expand env vars, return Config object."""
    load_dotenv()

    if path is None:
        env_path = os.environ.get("FAIGATE_CONFIG_FILE") or os.environ.get("FAIGATE_CONFIG_PATH")
        if env_path:
            path = env_path

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

    expanded = _normalize_provider_catalog_check(
        _normalize_security(
            _normalize_auto_update(
                _normalize_update_check(
                    _normalize_request_hooks(
                        _validate_routing_mode_references(
                            _normalize_model_shortcuts(
                                _normalize_routing_modes(
                                    _normalize_client_profiles(
                                        _normalize_routing_policies(
                                            _normalize_providers(_walk_expand(raw))
                                        )
                                    )
                                )
                            )
                        )
                    )
                )
            )
        )
    )
    return Config(expanded)
