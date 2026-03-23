"""Tests for config safe DB path resolution and env expansion."""

from pathlib import Path

import pytest

from faigate.config import ConfigError, _safe_db_path, load_config

# ── _safe_db_path unit tests ──────────────────────────────────────────────────


def test_safe_db_path_env_var_wins(monkeypatch):
    """FAIGATE_DB_PATH env var always takes priority."""
    monkeypatch.setenv("FAIGATE_DB_PATH", "/custom/path/faigate.db")
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    assert _safe_db_path() == "/custom/path/faigate.db"


def test_safe_db_path_env_var_over_configured(monkeypatch):
    """Env var wins even when a configured path is provided."""
    monkeypatch.setenv("FAIGATE_DB_PATH", "/env/faigate.db")
    assert _safe_db_path("/configured/faigate.db") == "/env/faigate.db"


def test_safe_db_path_rejects_dot_slash(monkeypatch):
    """./faigate.db must never be returned — it would pollute the repo."""
    monkeypatch.delenv("FAIGATE_DB_PATH", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    result = _safe_db_path("./faigate.db")
    assert not result.startswith("./"), f"unsafe path returned: {result}"
    assert "faigate.db" in result


def test_safe_db_path_rejects_bare_name(monkeypatch):
    """Bare 'faigate.db' (relative) must also be rejected."""
    monkeypatch.delenv("FAIGATE_DB_PATH", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    result = _safe_db_path("faigate.db")
    assert result != "faigate.db"
    assert result.startswith("/")


def test_safe_db_path_accepts_absolute_configured(monkeypatch):
    """An absolute path in config.yaml is used as-is."""
    monkeypatch.delenv("FAIGATE_DB_PATH", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    expected = "/var/lib/faigate/faigate.db"
    assert _safe_db_path(expected) == expected


def test_safe_db_path_xdg(monkeypatch):
    """XDG_DATA_HOME is used when no env/configured path is set."""
    monkeypatch.delenv("FAIGATE_DB_PATH", raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", "/xdg/data")
    result = _safe_db_path()
    assert result == "/xdg/data/faigate/faigate.db"


def test_safe_db_path_home_fallback(monkeypatch):
    """Falls back to ~/.local/share/faigate/faigate.db when nothing else is set."""
    monkeypatch.delenv("FAIGATE_DB_PATH", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    result = _safe_db_path()
    assert result.endswith("/.local/share/faigate/faigate.db")
    assert result.startswith("/")


# ── Config.metrics integration ────────────────────────────────────────────────


def test_metrics_db_path_uses_env_override(monkeypatch):
    """FAIGATE_DB_PATH env var is reflected in cfg.metrics['db_path']."""
    monkeypatch.setenv("FAIGATE_DB_PATH", "/var/lib/faigate/test.db")
    cfg = load_config(Path(__file__).parent.parent / "config.yaml")
    assert cfg.metrics["db_path"] == "/var/lib/faigate/test.db"


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

    monkeypatch.setenv("FAIGATE_CONFIG_FILE", str(path))
    cfg = load_config()
    assert cfg.server["port"] == 9001


def test_metrics_db_path_never_dot_slash(monkeypatch):
    """cfg.metrics['db_path'] must never start with './' regardless of config.yaml content."""
    monkeypatch.delenv("FAIGATE_DB_PATH", raising=False)
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
        "command": "faigate-health",
        "timeout_seconds": 30,
        "rollback_command": "",
    }
    assert cfg.auto_update["maintenance_window"]["enabled"] is False
    assert cfg.auto_update["maintenance_window"]["timezone"] == "UTC"
    assert cfg.auto_update["maintenance_window"]["days"] == ["sat", "sun"]
    assert cfg.auto_update["maintenance_window"]["start_hour"] == 2
    assert cfg.auto_update["maintenance_window"]["end_hour"] == 5
    assert cfg.auto_update["apply_command"] == "faigate-update"


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


def test_provider_lane_metadata_is_normalized(tmp_path):
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
    lane:
      family: custom
      name: workhorse
      canonical_model: custom/chat-model
      route_type: direct
      cluster: balanced-workhorse
      benchmark_cluster: internal-eval
      quality_tier: mid
      reasoning_strength: mid
      context_strength: mid
      tool_strength: low
      same_model_group: custom/chat-model
      degrade_to: [custom/backup-model]
fallback_chain: []
metrics:
  enabled: false
""",
        encoding="utf-8",
    )

    cfg = load_config(path)

    assert cfg.providers["cloud-default"]["lane"]["canonical_model"] == "custom/chat-model"
    assert cfg.providers["cloud-default"]["lane"]["route_type"] == "direct"
    assert cfg.providers["cloud-default"]["lane"]["degrade_to"] == ["custom/backup-model"]


def test_provider_transport_metadata_is_normalized(tmp_path):
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
    transport:
      chat_path: /responses/chat
fallback_chain: []
metrics:
  enabled: false
""",
        encoding="utf-8",
    )

    cfg = load_config(path)

    assert cfg.providers["cloud-default"]["transport"]["auth_mode"] == "bearer"
    assert cfg.providers["cloud-default"]["transport"]["profile"] == "openai-compatible"
    assert cfg.providers["cloud-default"]["transport"]["compatibility"] == "native"
    assert (
        cfg.providers["cloud-default"]["transport"]["probe_payload_kind"] == "openai-chat-minimal"
    )
    assert cfg.providers["cloud-default"]["transport"]["probe_payload_text"] == "ping"
    assert cfg.providers["cloud-default"]["transport"]["probe_payload_max_tokens"] == 1
    assert cfg.providers["cloud-default"]["transport"]["models_path"] == "/models"
    assert cfg.providers["cloud-default"]["transport"]["chat_path"] == "/responses/chat"


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
