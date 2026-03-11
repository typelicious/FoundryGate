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

import os
import re
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv


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

    expanded = _walk_expand(raw)
    return Config(expanded)
