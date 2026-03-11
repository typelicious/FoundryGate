"""Tests for client profile resolution and profile-based routing."""

# ruff: noqa: E402

import sys
import types
from pathlib import Path

import pytest

# Mock httpx before importing our modules
_httpx = types.ModuleType("httpx")


class _Timeout:
    def __init__(self, *a, **kw):
        pass


class _Limits:
    def __init__(self, *a, **kw):
        pass


class _AsyncClient:
    def __init__(self, *a, **kw):
        pass

    async def aclose(self):
        pass


_httpx.Timeout = _Timeout
_httpx.Limits = _Limits
_httpx.AsyncClient = _AsyncClient
_httpx.TimeoutException = Exception
_httpx.ConnectError = Exception
sys.modules["httpx"] = _httpx

from foundrygate.config import ConfigError, load_config
from foundrygate.main import _resolve_client_profile
from foundrygate.router import Router


def _write_config(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(body)
    return path


class TestClientProfileResolution:
    def test_resolve_n8n_profile_from_headers(self, tmp_path):
        cfg = load_config(
            _write_config(
                tmp_path,
                """
server:
  host: "127.0.0.1"
  port: 8090
providers:
  default-provider:
    backend: openai-compat
    base_url: "https://api.example.com/v1"
    api_key: "secret"
    model: "chat-model"
client_profiles:
  enabled: true
  default: generic
  profiles:
    generic: {}
    n8n:
      prefer_tiers: ["cheap", "default"]
  rules:
    - profile: n8n
      match:
        header_contains:
          x-foundrygate-client: ["n8n"]
fallback_chain: []
metrics:
  enabled: false
""",
            )
        )

        profile_name, hints = _resolve_client_profile(
            cfg,
            {"x-foundrygate-client": "n8n-workflow"},
        )

        assert profile_name == "n8n"
        assert hints["prefer_tiers"] == ["cheap", "default"]

    def test_rejects_unknown_profile_reference(self, tmp_path):
        path = _write_config(
            tmp_path,
            """
server:
  host: "127.0.0.1"
  port: 8090
providers:
  default-provider:
    backend: openai-compat
    base_url: "https://api.example.com/v1"
    api_key: "secret"
    model: "chat-model"
client_profiles:
  enabled: true
  default: generic
  profiles:
    generic: {}
  rules:
    - profile: missing
      match:
        header_present: ["x-foundrygate-client"]
fallback_chain: []
metrics:
  enabled: false
""",
        )

        with pytest.raises(ConfigError, match="unknown profile"):
            load_config(path)

    def test_preset_profiles_are_added_and_resolved(self, tmp_path):
        cfg = load_config(
            _write_config(
                tmp_path,
                """
server:
  host: "127.0.0.1"
  port: 8090
providers:
  cheap-worker:
    backend: openai-compat
    base_url: "https://api.example.com/v1"
    api_key: "secret"
    model: "cheap-model"
    tier: cheap
  default-worker:
    backend: openai-compat
    base_url: "https://api.example.com/v1"
    api_key: "secret"
    model: "default-model"
    tier: default
client_profiles:
  enabled: true
  default: generic
  presets: ["openclaw", "n8n", "cli"]
  profiles:
    generic: {}
fallback_chain:
  - default-worker
metrics:
  enabled: false
""",
            )
        )

        assert cfg.client_profiles["presets"] == ["openclaw", "n8n", "cli"]
        assert cfg.client_profiles["profiles"]["openclaw"]["prefer_tiers"] == [
            "default",
            "reasoning",
        ]
        assert cfg.client_profiles["profiles"]["n8n"]["prefer_tiers"] == ["cheap", "default"]
        assert cfg.client_profiles["profiles"]["cli"]["prefer_tiers"] == ["default", "reasoning"]

        profile_name, hints = _resolve_client_profile(cfg, {"x-openclaw-source": "subagent-42"})
        assert profile_name == "openclaw"
        assert hints["prefer_tiers"] == ["default", "reasoning"]

    def test_rejects_unknown_profile_preset(self, tmp_path):
        path = _write_config(
            tmp_path,
            """
server:
  host: "127.0.0.1"
  port: 8090
providers:
  default-provider:
    backend: openai-compat
    base_url: "https://api.example.com/v1"
    api_key: "secret"
    model: "chat-model"
client_profiles:
  enabled: true
  default: generic
  presets: ["missing"]
  profiles:
    generic: {}
fallback_chain: []
metrics:
  enabled: false
""",
        )

        with pytest.raises(ConfigError, match="unknown preset"):
            load_config(path)


class TestClientProfileRouting:
    @pytest.mark.asyncio
    async def test_profile_prefers_cheaper_provider_when_no_semantic_rule_matches(self, tmp_path):
        cfg = load_config(
            _write_config(
                tmp_path,
                """
server:
  host: "127.0.0.1"
  port: 8090
providers:
  cheap-worker:
    backend: openai-compat
    base_url: "https://api.example.com/v1"
    api_key: "secret"
    model: "cheap-model"
    tier: cheap
  default-worker:
    backend: openai-compat
    base_url: "https://api.example.com/v1"
    api_key: "secret"
    model: "default-model"
    tier: default
client_profiles:
  enabled: true
  default: generic
  profiles:
    generic: {}
    n8n:
      prefer_tiers: ["cheap", "default"]
  rules:
    - profile: n8n
      match:
        header_contains:
          x-foundrygate-client: ["n8n"]
static_rules:
  enabled: false
  rules: []
heuristic_rules:
  enabled: false
  rules: []
fallback_chain:
  - default-worker
metrics:
  enabled: false
""",
            )
        )
        router = Router(cfg)
        profile_name, hints = _resolve_client_profile(
            cfg,
            {"x-foundrygate-client": "n8n"},
        )

        decision = await router.route(
            [{"role": "user", "content": "hello there"}],
            model_requested="auto",
            client_profile=profile_name,
            profile_hints=hints,
            headers={"x-foundrygate-client": "n8n"},
        )

        assert decision.layer == "profile"
        assert decision.rule_name == "profile-n8n"
        assert decision.provider_name == "cheap-worker"

    @pytest.mark.asyncio
    async def test_cli_preset_prefers_default_tier(self, tmp_path):
        cfg = load_config(
            _write_config(
                tmp_path,
                """
server:
  host: "127.0.0.1"
  port: 8090
providers:
  cheap-worker:
    backend: openai-compat
    base_url: "https://api.example.com/v1"
    api_key: "secret"
    model: "cheap-model"
    tier: cheap
  default-worker:
    backend: openai-compat
    base_url: "https://api.example.com/v1"
    api_key: "secret"
    model: "default-model"
    tier: default
client_profiles:
  enabled: true
  default: generic
  presets: ["cli"]
  profiles:
    generic: {}
static_rules:
  enabled: false
  rules: []
heuristic_rules:
  enabled: false
  rules: []
fallback_chain:
  - cheap-worker
metrics:
  enabled: false
""",
            )
        )
        router = Router(cfg)
        profile_name, hints = _resolve_client_profile(
            cfg,
            {"x-foundrygate-client": "codex-cli"},
        )

        decision = await router.route(
            [{"role": "user", "content": "inspect the repository"}],
            model_requested="auto",
            client_profile=profile_name,
            profile_hints=hints,
            headers={"x-foundrygate-client": "codex-cli"},
        )

        assert profile_name == "cli"
        assert decision.layer == "profile"
        assert decision.provider_name == "default-worker"
