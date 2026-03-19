"""Tests for config safe DB path resolution and env expansion."""

from pathlib import Path

import pytest

from foundrygate.config import ConfigError, _safe_db_path, load_config

# ── _safe_db_path unit tests ──────────────────────────────────────────────────


def test_safe_db_path_env_var_wins(monkeypatch):
    """FOUNDRYGATE_DB_PATH env var always takes priority."""
    monkeypatch.setenv("FOUNDRYGATE_DB_PATH", "/custom/path/foundrygate.db")
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    assert _safe_db_path() == "/custom/path/foundrygate.db"


def test_safe_db_path_env_var_over_configured(monkeypatch):
    """Env var wins even when a configured path is provided."""
    monkeypatch.setenv("FOUNDRYGATE_DB_PATH", "/env/foundrygate.db")
    assert _safe_db_path("/configured/foundrygate.db") == "/env/foundrygate.db"


def test_safe_db_path_rejects_dot_slash(monkeypatch):
    """./foundrygate.db must never be returned — it would pollute the repo."""
    monkeypatch.delenv("FOUNDRYGATE_DB_PATH", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    result = _safe_db_path("./foundrygate.db")
    assert not result.startswith("./"), f"unsafe path returned: {result}"
    assert "foundrygate.db" in result


def test_safe_db_path_rejects_bare_name(monkeypatch):
    """Bare 'foundrygate.db' (relative) must also be rejected."""
    monkeypatch.delenv("FOUNDRYGATE_DB_PATH", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    result = _safe_db_path("foundrygate.db")
    assert result != "foundrygate.db"
    assert result.startswith("/")


def test_safe_db_path_accepts_absolute_configured(monkeypatch):
    """An absolute path in config.yaml is used as-is."""
    monkeypatch.delenv("FOUNDRYGATE_DB_PATH", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    expected = "/var/lib/foundrygate/foundrygate.db"
    assert _safe_db_path(expected) == expected


def test_safe_db_path_xdg(monkeypatch):
    """XDG_DATA_HOME is used when no env/configured path is set."""
    monkeypatch.delenv("FOUNDRYGATE_DB_PATH", raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", "/xdg/data")
    result = _safe_db_path()
    assert result == "/xdg/data/foundrygate/foundrygate.db"


def test_safe_db_path_home_fallback(monkeypatch):
    """Falls back to ~/.local/share/foundrygate/foundrygate.db when nothing else is set."""
    monkeypatch.delenv("FOUNDRYGATE_DB_PATH", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    result = _safe_db_path()
    assert result.endswith("/.local/share/foundrygate/foundrygate.db")
    assert result.startswith("/")


# ── Config.metrics integration ────────────────────────────────────────────────


def test_metrics_db_path_uses_env_override(monkeypatch):
    """FOUNDRYGATE_DB_PATH env var is reflected in cfg.metrics['db_path']."""
    monkeypatch.setenv("FOUNDRYGATE_DB_PATH", "/var/lib/foundrygate/test.db")
    cfg = load_config(Path(__file__).parent.parent / "config.yaml")
    assert cfg.metrics["db_path"] == "/var/lib/foundrygate/test.db"


def test_load_config_uses_explicit_config_env_file(tmp_path, monkeypatch):
    path = tmp_path / "custom-config.yaml"
    path.write_text(
        """
server:
  host: "127.0.0.1"
  port: 9001
providers:
  cloud-default:
    backend: openai-compat
    base_url: "https://api.example.com/v1"
    api_key: "secret"
    model: "chat-model"
fallback_chain: []
metrics:
  enabled: false
"""
    )

    monkeypatch.setenv("FOUNDRYGATE_CONFIG_FILE", str(path))
    cfg = load_config()
    assert cfg.server["port"] == 9001


def test_metrics_db_path_never_dot_slash(monkeypatch):
    """cfg.metrics['db_path'] must never start with './' regardless of config.yaml content."""
    monkeypatch.delenv("FOUNDRYGATE_DB_PATH", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    cfg = load_config(Path(__file__).parent.parent / "config.yaml")
    db_path = cfg.metrics["db_path"]
    assert not db_path.startswith("./"), f"unsafe db_path in metrics: {db_path}"
    assert db_path.startswith("/"), f"expected absolute path, got: {db_path}"


def test_auto_update_defaults_are_exposed():
    cfg = load_config(Path(__file__).parent.parent / "config.yaml")
    assert cfg.auto_update["enabled"] is False
    assert cfg.auto_update["allow_major"] is False
    assert cfg.auto_update["rollout_ring"] == "early"
    assert cfg.auto_update["require_healthy_providers"] is True
    assert cfg.auto_update["max_unhealthy_providers"] == 0
    assert cfg.auto_update["min_release_age_hours"] == 0
    assert cfg.auto_update["provider_scope"] == {
        "allow_providers": [],
        "deny_providers": ["openrouter-fallback"],
    }
    assert cfg.auto_update["verification"] == {
        "enabled": False,
        "command": "foundrygate-health",
        "timeout_seconds": 30,
        "rollback_command": "",
    }
    assert cfg.auto_update["maintenance_window"]["enabled"] is False
    assert cfg.auto_update["maintenance_window"]["timezone"] == "UTC"
    assert cfg.auto_update["maintenance_window"]["days"] == ["sat", "sun"]
    assert cfg.auto_update["maintenance_window"]["start_hour"] == 2
    assert cfg.auto_update["maintenance_window"]["end_hour"] == 5
    assert cfg.auto_update["apply_command"] == "foundrygate-update"


def test_update_check_defaults_include_stable_release_channel():
    cfg = load_config(Path(__file__).parent.parent / "config.yaml")
    assert cfg.update_check["release_channel"] == "stable"


def test_routing_modes_and_model_shortcuts_are_exposed(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        """
server:
  host: "127.0.0.1"
  port: 8090
providers:
  cloud-default:
    backend: openai-compat
    base_url: "https://api.example.com/v1"
    api_key: "secret"
    model: "chat-model"
routing_modes:
  enabled: true
  default: premium
  modes:
    premium:
      aliases: ["quality"]
      description: "Best quality"
      select:
        prefer_providers: ["cloud-default"]
model_shortcuts:
  enabled: true
  shortcuts:
    fast:
      target: cloud-default
      aliases: ["chat"]
client_profiles:
  enabled: true
  default: generic
  profiles:
    generic: {}
    app:
      routing_mode: premium
  rules: []
fallback_chain: []
metrics:
  enabled: false
"""
    )

    cfg = load_config(path)
    assert cfg.routing_modes["enabled"] is True
    assert cfg.routing_modes["default"] == "premium"
    assert cfg.routing_modes["modes"]["premium"]["aliases"] == ["quality"]
    assert cfg.model_shortcuts["shortcuts"]["fast"]["target"] == "cloud-default"
    assert cfg.client_profiles["profiles"]["app"]["routing_mode"] == "premium"


def test_client_profile_rejects_unknown_routing_mode(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        """
server:
  host: "127.0.0.1"
  port: 8090
providers:
  cloud-default:
    backend: openai-compat
    base_url: "https://api.example.com/v1"
    api_key: "secret"
    model: "chat-model"
routing_modes:
  enabled: true
  default: auto
  modes:
    premium:
      select:
        prefer_providers: ["cloud-default"]
client_profiles:
  enabled: true
  default: generic
  profiles:
    generic: {}
    app:
      routing_mode: missing
  rules: []
fallback_chain: []
metrics:
  enabled: false
"""
    )

    with pytest.raises(ConfigError, match="unknown routing_mode 'missing'"):
        load_config(path)


def test_security_defaults_are_exposed():
    cfg = load_config(Path(__file__).parent.parent / "config.yaml")
    assert cfg.security == {
        "response_headers": True,
        "cache_control": "no-store",
        "max_json_body_bytes": 1048576,
        "max_upload_bytes": 10485760,
        "max_header_value_chars": 160,
    }


def test_provider_catalog_check_defaults_are_exposed():
    cfg = load_config(Path(__file__).parent.parent / "config.yaml")
    assert cfg.provider_catalog_check == {
        "enabled": True,
        "warn_on_untracked": True,
        "warn_on_model_drift": True,
        "warn_on_unofficial_sources": True,
        "warn_on_volatile_offers": True,
        "max_catalog_age_days": 30,
    }


def test_security_rejects_invalid_limit_values(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        """
server:
  host: "127.0.0.1"
  port: 8090
providers:
  cloud-default:
    backend: openai-compat
    base_url: "https://api.example.com/v1"
    api_key: "secret"
    model: "chat-model"
security:
  max_json_body_bytes: 0
fallback_chain: []
metrics:
  enabled: false
"""
    )

    with pytest.raises(ConfigError, match="security.max_json_body_bytes"):
        load_config(path)


def test_provider_rejects_public_http_base_url(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        """
server:
  host: "127.0.0.1"
  port: 8090
providers:
  cloud-default:
    backend: openai-compat
    base_url: "http://api.example.com/v1"
    api_key: "secret"
    model: "chat-model"
fallback_chain: []
metrics:
  enabled: false
"""
    )

    with pytest.raises(ConfigError, match="must use https"):
        load_config(path)


def test_provider_allows_local_http_base_url(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        """
server:
  host: "127.0.0.1"
  port: 8090
providers:
  local-worker:
    backend: openai-compat
    base_url: "http://127.0.0.1:11434/v1"
    api_key: "local"
    model: "llama3"
fallback_chain: []
metrics:
  enabled: false
"""
    )

    cfg = load_config(path)
    assert cfg.providers["local-worker"]["base_url"] == "http://127.0.0.1:11434/v1"
