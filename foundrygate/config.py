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

_SUPPORTED_BACKENDS = {"openai-compat", "google-genai", "anthropic-compat"}
_BOOL_CAPABILITY_FIELDS = {
    "chat",
    "reasoning",
    "vision",
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

    normalized: dict[str, Any] = {
        "chat": True,
        "reasoning": tier == "reasoning" or "reasoner" in model,
        "vision": False,
        "tools": False,
        "long_context": False,
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

    expanded = _normalize_routing_policies(_normalize_providers(_walk_expand(raw)))
    return Config(expanded)
