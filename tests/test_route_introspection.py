"""Tests for route introspection and dry-run previews."""

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
from foundrygate.config import load_config
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
        backend_type: str = "openai-compat",
        contract: str = "generic",
        tier: str = "default",
        healthy: bool = True,
        capabilities: dict | None = None,
    ):
        self.name = name
        self.model = model
        self.backend_type = backend_type
        self.contract = contract
        self.tier = tier
        self.capabilities = capabilities or {}
        self.health = types.SimpleNamespace(
            healthy=healthy,
            to_dict=lambda: {
                "name": name,
                "healthy": healthy,
                "consecutive_failures": 0,
                "avg_latency_ms": 0.0,
                "last_error": "",
            },
        )


@pytest.fixture
def preview_config(tmp_path, monkeypatch):
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
client_profiles:
  enabled: true
  default: generic
  profiles:
    generic: {}
    local-only:
      capability_values:
        local: true
      prefer_tiers: ["local"]
  rules:
    - profile: local-only
      match:
        header_contains:
          x-foundrygate-profile: ["local-only"]
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


class TestRoutePreview:
    @pytest.mark.asyncio
    async def test_preview_resolves_profile_and_attempt_order(self, preview_config):
        (
            decision,
            profile_name,
            client_tag,
            attempt_order,
            model_requested,
        ) = await _resolve_route_preview(
            {
                "model": "auto",
                "messages": [{"role": "user", "content": "hello from local-only traffic"}],
            },
            {"x-foundrygate-profile": "local-only"},
        )

        assert model_requested == "auto"
        assert profile_name == "local-only"
        assert client_tag == "local-only"
        assert decision.layer == "profile"
        assert decision.provider_name == "local-worker"
        assert attempt_order == ["local-worker", "cloud-default"]

    @pytest.mark.asyncio
    async def test_preview_direct_model_keeps_explicit_provider_first(self, preview_config):
        (
            decision,
            profile_name,
            client_tag,
            attempt_order,
            model_requested,
        ) = await _resolve_route_preview(
            {
                "model": "cloud-default",
                "messages": [{"role": "user", "content": "use the explicit provider"}],
            },
            {},
        )

        assert model_requested == "cloud-default"
        assert profile_name == "generic"
        assert client_tag == "generic"
        assert decision.layer == "direct"
        assert decision.provider_name == "cloud-default"
        assert attempt_order == ["cloud-default"]
