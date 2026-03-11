"""Tests for config safe DB path resolution and env expansion."""

from pathlib import Path

from foundrygate.config import _safe_db_path, load_config

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


def test_metrics_db_path_never_dot_slash(monkeypatch):
    """cfg.metrics['db_path'] must never start with './' regardless of config.yaml content."""
    monkeypatch.delenv("FOUNDRYGATE_DB_PATH", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    cfg = load_config(Path(__file__).parent.parent / "config.yaml")
    db_path = cfg.metrics["db_path"]
    assert not db_path.startswith("./"), f"unsafe db_path in metrics: {db_path}"
    assert db_path.startswith("/"), f"expected absolute path, got: {db_path}"
