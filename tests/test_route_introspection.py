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
from foundrygate.main import (
    _extract_image_edit_request_fields,
    _refresh_local_worker_probes,
    _resolve_image_route_preview,
    _resolve_route_preview,
)
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
            last_check=0.0,
            to_dict=lambda: {
                "name": name,
                "healthy": healthy,
                "consecutive_failures": 0,
                "avg_latency_ms": 0.0,
                "last_error": "",
            },
        )
        self.probe_calls = 0

    async def probe_health(self, timeout_seconds: float = 10.0) -> bool:
        self.probe_calls += 1
        self.health.last_check = 1.0
        return self.health.healthy


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
  image-cloud:
    contract: image-provider
    backend: openai-compat
    base_url: "https://api.example.com/v1"
    api_key: "secret"
    model: "gpt-image-1"
    tier: default
    capabilities:
      image_editing: true
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
            "image-cloud": _ProviderStub(
                name="image-cloud",
                model="gpt-image-1",
                contract="image-provider",
                tier="default",
                capabilities={
                    "local": False,
                    "cloud": True,
                    "network_zone": "public",
                    "image_generation": True,
                    "image_editing": True,
                },
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
            hook_state,
            effective_body,
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
        assert hook_state.applied_hooks == []
        assert effective_body["model"] == "auto"

    @pytest.mark.asyncio
    async def test_preview_direct_model_keeps_explicit_provider_first(self, preview_config):
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
        assert hook_state.applied_hooks == []
        assert effective_body["model"] == "cloud-default"

    @pytest.mark.asyncio
    async def test_image_preview_selects_image_provider(self, preview_config):
        (
            decision,
            profile_name,
            client_tag,
            attempt_order,
            model_requested,
            hook_state,
            effective_body,
        ) = await _resolve_image_route_preview(
            {
                "model": "auto",
                "prompt": "Draw a blueprint-style gateway diagram.",
                "size": "1024x1024",
            },
            {},
        )

        assert model_requested == "auto"
        assert profile_name == "generic"
        assert client_tag == "generic"
        assert decision.provider_name == "image-cloud"
        assert decision.details["required_capability"] == "image_generation"
        assert attempt_order == ["image-cloud"]
        assert hook_state.applied_hooks == []
        assert effective_body["prompt"] == "Draw a blueprint-style gateway diagram."

    @pytest.mark.asyncio
    async def test_image_edit_preview_selects_edit_capable_provider(self, preview_config):
        (
            decision,
            profile_name,
            client_tag,
            attempt_order,
            model_requested,
            hook_state,
            effective_body,
        ) = await _resolve_image_route_preview(
            {
                "model": "auto",
                "prompt": "Remove the background and keep the subject.",
            },
            {},
            capability="image_editing",
        )

        assert model_requested == "auto"
        assert profile_name == "generic"
        assert client_tag == "generic"
        assert decision.provider_name == "image-cloud"
        assert decision.details["required_capability"] == "image_editing"
        assert attempt_order == ["image-cloud"]
        assert hook_state.applied_hooks == []
        assert effective_body["prompt"] == "Remove the background and keep the subject."

    def test_extract_image_edit_request_fields_requires_prompt(self):
        with pytest.raises(ValueError, match="non-empty 'prompt'"):
            _extract_image_edit_request_fields({"model": "auto"})

    def test_extract_image_edit_request_fields_parses_scalars(self):
        payload = _extract_image_edit_request_fields(
            {
                "model": "image-cloud",
                "prompt": "Retouch the lighting",
                "n": "2",
                "size": "1024x1024",
                "response_format": "b64_json",
                "user": "tester",
            }
        )

        assert payload["model"] == "image-cloud"
        assert payload["prompt"] == "Retouch the lighting"
        assert payload["n"] == 2
        assert payload["size"] == "1024x1024"
        assert payload["response_format"] == "b64_json"
        assert payload["user"] == "tester"


class TestLocalWorkerProbeRefresh:
    @pytest.mark.asyncio
    async def test_refresh_only_probes_local_worker_contracts(self, preview_config):
        await _refresh_local_worker_probes(force=True)

        local_worker = main_module._providers["local-worker"]
        cloud_default = main_module._providers["cloud-default"]

        assert local_worker.probe_calls == 1
        assert cloud_default.probe_calls == 0
