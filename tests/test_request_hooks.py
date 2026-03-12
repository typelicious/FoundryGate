"""Tests for optional request hook interfaces."""

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

import foundrygate.main as main_module
from foundrygate.config import ConfigError, load_config
from foundrygate.main import _resolve_route_preview
from foundrygate.router import Router


def _write_config(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(body)
    return path


class _ProviderStub:
    def __init__(
        self,
        *,
        name: str,
        model: str,
        tier: str = "default",
        contract: str = "generic",
        capabilities: dict | None = None,
        healthy: bool = True,
    ):
        self.name = name
        self.model = model
        self.backend_type = "openai-compat"
        self.contract = contract
        self.tier = tier
        self.capabilities = capabilities or {}
        self.health = types.SimpleNamespace(
            healthy=healthy,
            last_check=0.0,
            to_dict=lambda: {
                "name": name,
                "healthy": healthy,
                "consecutive_failures": 0,
                "avg_latency_ms": 0.0,
                "last_error": "",
            },
        )


class TestRequestHookConfig:
    def test_rejects_unknown_request_hook_name(self, tmp_path):
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
request_hooks:
  enabled: true
  hooks: ["missing-hook"]
fallback_chain: []
metrics:
  enabled: false
""",
        )

        with pytest.raises(ConfigError, match="unknown hook"):
            load_config(path)


@pytest.fixture
def hook_config(tmp_path, monkeypatch):
    cfg = load_config(
        _write_config(
            tmp_path,
            """
server:
  host: "127.0.0.1"
  port: 8090
providers:
  cloud-default:
    backend: openai-compat
    base_url: "https://api.example.com/v1"
    api_key: "secret"
    model: "cloud-chat"
    tier: default
  local-worker:
    contract: local-worker
    backend: openai-compat
    base_url: "http://127.0.0.1:11434/v1"
    api_key: "local"
    model: "llama3"
    tier: local
request_hooks:
  enabled: true
  hooks:
    - prefer-provider-header
    - locality-header
    - profile-override-header
client_profiles:
  enabled: true
  default: generic
  profiles:
    generic: {}
    local-only:
      capability_values:
        local: true
      prefer_tiers: ["local"]
fallback_chain:
  - cloud-default
metrics:
  enabled: false
""",
        )
    )
    monkeypatch.setattr(main_module, "_config", cfg, raising=False)
    monkeypatch.setattr(main_module, "_router", Router(cfg), raising=False)
    monkeypatch.setattr(
        main_module,
        "_providers",
        {
            "cloud-default": _ProviderStub(
                name="cloud-default",
                model="cloud-chat",
                tier="default",
                capabilities={"local": False, "cloud": True, "network_zone": "public"},
            ),
            "local-worker": _ProviderStub(
                name="local-worker",
                model="llama3",
                contract="local-worker",
                tier="local",
                capabilities={"local": True, "cloud": False, "network_zone": "local"},
            ),
        },
        raising=False,
    )
    return cfg


class TestRequestHookRouting:
    @pytest.mark.asyncio
    async def test_prefer_provider_header_selects_requested_provider(self, hook_config):
        (
            decision,
            profile_name,
            client_tag,
            attempt_order,
            model_requested,
            hook_state,
            effective_body,
        ) = await _resolve_route_preview(
            {
                "model": "auto",
                "messages": [{"role": "user", "content": "inspect the route"}],
            },
            {"x-foundrygate-prefer-provider": "local-worker"},
        )

        assert model_requested == "auto"
        assert profile_name == "generic"
        assert client_tag == "generic"
        assert decision.layer == "hook"
        assert decision.provider_name == "local-worker"
        assert attempt_order == ["local-worker", "cloud-default"]
        assert hook_state.applied_hooks == ["prefer-provider-header"]
        assert effective_body["model"] == "auto"

    @pytest.mark.asyncio
    async def test_locality_and_profile_hooks_shape_one_request(self, hook_config):
        (
            decision,
            profile_name,
            client_tag,
            attempt_order,
            _model_requested,
            hook_state,
            _effective_body,
        ) = await _resolve_route_preview(
            {
                "model": "auto",
                "messages": [{"role": "user", "content": "keep this on the local worker"}],
            },
            {
                "x-foundrygate-locality": "local-only",
                "x-foundrygate-profile": "local-only",
            },
        )

        assert profile_name == "local-only"
        assert client_tag == "local-only"
        assert decision.layer == "hook"
        assert decision.provider_name == "local-worker"
        assert attempt_order == ["local-worker", "cloud-default"]
        assert hook_state.applied_hooks == ["locality-header", "profile-override-header"]
        assert hook_state.profile_override == "local-only"
        assert hook_state.routing_hints["prefer_tiers"] == ["local"]
