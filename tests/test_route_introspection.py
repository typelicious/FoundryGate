"""Tests for route introspection and dry-run previews."""

# ruff: noqa: E402

import json
import sys
import types
from pathlib import Path

import pytest
from starlette.requests import Request

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
    _normalize_image_request_body,
    _refresh_local_worker_probes,
    _resolve_image_route_preview,
    _resolve_route_preview,
    health,
    preview_image_route,
    provider_inventory,
)
from foundrygate.router import Router


def _write_config(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(body)
    return path


def _json_request(
    path: str,
    payload: dict[str, object],
    headers: dict[str, str] | None = None,
) -> Request:
    body = json.dumps(payload).encode("utf-8")
    header_items = [(b"content-type", b"application/json")]
    for key, value in (headers or {}).items():
        header_items.append((key.lower().encode("utf-8"), value.encode("utf-8")))

    received = False

    async def receive():
        nonlocal received
        if received:
            return {"type": "http.disconnect"}
        received = True
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": path,
            "headers": header_items,
        },
        receive,
    )


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
        image: dict | None = None,
    ):
        self.name = name
        self.model = model
        self.backend_type = backend_type
        self.contract = contract
        self.tier = tier
        self.capabilities = capabilities or {}
        self.context_window = 0
        self.limits = {}
        self.cache = {"mode": "none", "read_discount": False}
        self.image = image or {}
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
    image:
      max_outputs: 1
      max_side_px: 1024
      supported_sizes: ["1024x1024"]
  image-large:
    contract: image-provider
    backend: openai-compat
    base_url: "https://api.example.com/v1"
    api_key: "secret"
    model: "gpt-image-1-hd"
    tier: default
    capabilities:
      image_editing: true
    image:
      max_outputs: 4
      max_side_px: 2048
      supported_sizes: ["1024x1024", "2048x2048"]
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
                image={
                    "max_outputs": 1,
                    "max_side_px": 1024,
                    "supported_sizes": ["1024x1024"],
                },
            ),
            "image-large": _ProviderStub(
                name="image-large",
                model="gpt-image-1-hd",
                contract="image-provider",
                tier="default",
                capabilities={
                    "local": False,
                    "cloud": True,
                    "network_zone": "public",
                    "image_generation": True,
                    "image_editing": True,
                },
                image={
                    "max_outputs": 4,
                    "max_side_px": 2048,
                    "supported_sizes": ["1024x1024", "2048x2048"],
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

    @pytest.mark.asyncio
    async def test_image_route_preview_endpoint_reports_modality(self, preview_config):
        response = await preview_image_route(
            _json_request(
                "/api/route/image",
                {
                    "model": "auto",
                    "capability": "image_editing",
                    "prompt": "Remove the background.",
                },
            )
        )

        assert response["effective_request"]["modality"] == "image_editing"
        assert response["decision"]["provider"] == "image-cloud"
        assert response["selected_provider"]["contract"] == "image-provider"

    @pytest.mark.asyncio
    async def test_image_route_preview_prefers_provider_that_fits_size_and_count(
        self, preview_config
    ):
        response = await preview_image_route(
            _json_request(
                "/api/route/image",
                {
                    "model": "auto",
                    "capability": "image_generation",
                    "prompt": "Create a high-resolution architectural render.",
                    "size": "2048x2048",
                    "n": 2,
                },
            )
        )

        assert response["decision"]["provider"] == "image-large"
        ranking = response["decision"]["details"]["candidate_ranking"]
        assert len(ranking) == 1
        assert ranking[0]["provider"] == "image-large"
        assert ranking[0]["image_size_fit"] is True
        assert ranking[0]["image_outputs_fit"] is True

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

    def test_normalize_image_request_body_validates_size_and_n(self):
        payload = _normalize_image_request_body(
            {
                "model": "auto",
                "prompt": " Render a scene ",
                "n": 2,
                "size": " 2048x2048 ",
                "quality": " high ",
            },
            capability="image_generation",
        )

        assert payload["prompt"] == "Render a scene"
        assert payload["model"] == "auto"
        assert payload["n"] == 2
        assert payload["size"] == "2048x2048"
        assert payload["quality"] == "high"

    def test_normalize_image_request_body_rejects_invalid_size(self):
        with pytest.raises(ValueError, match="must use the form <width>x<height>"):
            _normalize_image_request_body(
                {
                    "model": "auto",
                    "prompt": "Render a scene",
                    "size": "wide",
                },
                capability="image_generation",
            )

    @pytest.mark.asyncio
    async def test_image_route_preview_rejects_invalid_size(self, preview_config):
        response = await preview_image_route(
            _json_request(
                "/api/route/image",
                {
                    "model": "auto",
                    "capability": "image_generation",
                    "prompt": "Draw a gateway diagram.",
                    "size": "invalid",
                },
            )
        )

        assert response.status_code == 400


class TestLocalWorkerProbeRefresh:
    @pytest.mark.asyncio
    async def test_refresh_only_probes_local_worker_contracts(self, preview_config):
        await _refresh_local_worker_probes(force=True)

        local_worker = main_module._providers["local-worker"]
        cloud_default = main_module._providers["cloud-default"]

        assert local_worker.probe_calls == 1
        assert cloud_default.probe_calls == 0


class TestProviderCoverage:
    @pytest.mark.asyncio
    async def test_health_reports_capability_coverage(self, preview_config):
        response = await health()

        assert response["summary"]["providers_total"] == 4
        assert response["summary"]["providers_healthy"] == 4
        assert response["coverage"]["image_generation"]["total"] == 2
        assert response["coverage"]["image_generation"]["healthy"] == 2
        assert response["coverage"]["image_editing"]["providers"] == [
            "image-cloud",
            "image-large",
        ]
        assert response["providers"]["image-cloud"]["image"]["max_outputs"] == 1

    @pytest.mark.asyncio
    async def test_provider_inventory_filters_by_capability(self, preview_config):
        response = await provider_inventory(capability="image_editing")

        provider_names = [provider["name"] for provider in response["providers"]]
        assert provider_names == ["image-cloud", "image-large"]
        assert response["coverage"]["image_editing"]["total"] == 2
        assert response["providers"][0]["contract"] == "image-provider"
