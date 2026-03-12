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

import foundrygate.hooks as hook_module
import foundrygate.main as main_module
from foundrygate.config import ConfigError, load_config
from foundrygate.hooks import (
    HookExecutionError,
    RequestHookContext,
    RequestHookResult,
    apply_request_hooks,
)
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


class TestRequestHookHardening:
    @pytest.mark.asyncio
    async def test_invalid_hook_outputs_are_sanitized(self, monkeypatch):
        def _unsafe_hook(_context):
            return RequestHookResult(
                body_updates={
                    "model": "local-worker",
                    "max_tokens": "oops",
                    "internal_flag": True,
                },
                profile_override="INVALID PROFILE!",
                routing_hints={
                    "prefer_providers": ["local-worker", "", 42],
                    "capability_values": {"local": [True], "": ["bad"]},
                    "unexpected": "value",
                },
                notes=["unsafe hook ran"],
            )

        monkeypatch.setitem(hook_module._REQUEST_HOOKS, "unsafe-test", _unsafe_hook)
        applied = await apply_request_hooks(
            {"enabled": True, "hooks": ["unsafe-test"], "on_error": "continue"},
            RequestHookContext(
                body={"model": "auto", "messages": [{"role": "user", "content": "hello"}]},
                headers={},
                model_requested="auto",
            ),
        )

        assert applied.body["model"] == "local-worker"
        assert "max_tokens" not in applied.body
        assert applied.profile_override is None
        assert applied.routing_hints["prefer_providers"] == ["local-worker"]
        assert applied.routing_hints["capability_values"]["local"] == [True]
        assert "unsafe-test" in applied.applied_hooks
        assert any(
            "unsupported hook body update field 'internal_flag'" in note for note in applied.notes
        )
        assert any("invalid profile override" in error for error in applied.errors)
        assert any("routing_hints.prefer_providers" in error for error in applied.errors)
        assert any(
            "unsupported routing_hints field 'unexpected'" in error for error in applied.errors
        )

    @pytest.mark.asyncio
    async def test_hook_fail_mode_raises(self, monkeypatch):
        def _failing_hook(_context):
            raise RuntimeError("boom")

        monkeypatch.setitem(hook_module._REQUEST_HOOKS, "failing-test", _failing_hook)

        with pytest.raises(HookExecutionError, match="failing-test"):
            await apply_request_hooks(
                {"enabled": True, "hooks": ["failing-test"], "on_error": "fail"},
                RequestHookContext(
                    body={"model": "auto", "messages": []},
                    headers={},
                    model_requested="auto",
                ),
            )

    @pytest.mark.asyncio
    async def test_hook_continue_mode_records_errors(self, monkeypatch):
        def _failing_hook(_context):
            raise RuntimeError("transient failure")

        monkeypatch.setitem(hook_module._REQUEST_HOOKS, "failing-continue", _failing_hook)
        applied = await apply_request_hooks(
            {"enabled": True, "hooks": ["failing-continue"], "on_error": "continue"},
            RequestHookContext(
                body={"model": "auto", "messages": []},
                headers={},
                model_requested="auto",
            ),
        )

        assert applied.applied_hooks == []
        assert any("failing-continue" in error for error in applied.errors)
