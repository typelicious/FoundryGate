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

import faigate.main as main_module
from faigate.adaptation import AdaptiveRouteState
from faigate.config import load_config
from faigate.main import (
    _attempt_metric_fields,
    _extract_image_edit_request_fields,
    _normalize_image_request_body,
    _refresh_local_worker_probes,
    _resolve_image_route_preview,
    _resolve_route_preview,
    health,
    list_models,
    preview_image_route,
    provider_catalog,
    provider_inventory,
)
from faigate.router import Router


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
        lane: dict | None = None,
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
        self.lane = lane or {}
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
    lane:
      family: custom
      name: balanced
      canonical_model: custom/cloud-chat
      route_type: direct
      cluster: balanced-workhorse
      benchmark_cluster: balanced-coding
      quality_tier: mid
      reasoning_strength: mid
  local-worker:
    contract: local-worker
    backend: openai-compat
    base_url: "http://127.0.0.1:11434/v1"
    api_key: "local"
    model: "llama3"
    tier: local
    lane:
      family: local
      name: workhorse
      canonical_model: local/llama3
      route_type: local
      cluster: balanced-workhorse
      benchmark_cluster: local-general
      quality_tier: mid
      reasoning_strength: mid
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
      policy_tags: ["balanced", "cost", "editing"]
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
      policy_tags: ["quality", "batch"]
client_profiles:
  enabled: true
  default: generic
  profiles:
    generic:
      routing_mode: auto
    local-only:
      routing_mode: eco
      capability_values:
        local: true
      prefer_tiers: ["local"]
  rules:
    - profile: local-only
      match:
        header_contains:
          x-faigate-profile: ["local-only"]
routing_modes:
  enabled: true
  default: auto
  modes:
    auto:
      description: "Balanced"
      select:
        prefer_tiers: ["default", "local"]
    eco:
      aliases: ["cheap"]
      description: "Cheapest possible"
      select:
        prefer_providers: ["local-worker", "cloud-default"]
        prefer_tiers: ["local", "default"]
    premium:
      aliases: ["quality"]
      description: "Best quality"
      select:
        prefer_providers: ["cloud-default"]
model_shortcuts:
  enabled: true
  shortcuts:
    local:
      target: local-worker
      aliases: ["llama"]
    img:
      target: image-large
      aliases: ["image"]
fallback_chain:
  - cloud-default
metrics:
  enabled: false
""",
        )
    )
    monkeypatch.setattr(main_module, "_config", cfg, raising=False)
    monkeypatch.setattr(main_module, "_router", Router(cfg), raising=False)
    monkeypatch.setattr(main_module, "_adaptive_state", AdaptiveRouteState(), raising=False)
    monkeypatch.setattr(
        main_module,
        "_providers",
        {
            "cloud-default": _ProviderStub(
                name="cloud-default",
                model="cloud-chat",
                tier="default",
                lane={
                    "family": "custom",
                    "name": "balanced",
                    "canonical_model": "custom/cloud-chat",
                    "route_type": "direct",
                    "cluster": "balanced-workhorse",
                },
            ),
            "local-worker": _ProviderStub(
                name="local-worker",
                model="llama3",
                contract="local-worker",
                tier="local",
                capabilities={"local": True, "cloud": False, "network_zone": "local"},
                lane={
                    "family": "local",
                    "name": "workhorse",
                    "canonical_model": "local/llama3",
                    "route_type": "local",
                    "cluster": "balanced-workhorse",
                },
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
                    "policy_tags": ["balanced", "cost", "editing"],
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
                    "policy_tags": ["quality", "batch"],
                },
            ),
        },
        raising=False,
    )
    return cfg


@pytest.mark.asyncio
async def test_preview_resolves_explicit_routing_mode(preview_config):
    (
        decision,
        profile_name,
        client_tag,
        attempt_order,
        model_requested,
        resolved_mode,
        resolved_shortcut,
        _hook_state,
        payload,
    ) = await _resolve_route_preview(
        {"model": "premium", "messages": [{"role": "user", "content": "hello"}]},
        {},
    )

    assert model_requested == "premium"
    assert resolved_mode == "premium"
    assert resolved_shortcut is None
    assert profile_name == "generic"
    assert client_tag == "generic"
    assert decision.provider_name == "cloud-default"
    assert decision.details["canonical_model"] == "custom/cloud-chat"
    assert isinstance(decision.details["known_routes"], list)
    assert payload["model"] == "auto"
    assert attempt_order[0] == "cloud-default"


@pytest.mark.asyncio
async def test_preview_uses_client_profile_default_mode_on_auto(preview_config):
    (
        decision,
        profile_name,
        _client_tag,
        _attempt_order,
        model_requested,
        resolved_mode,
        resolved_shortcut,
        _hook_state,
        payload,
    ) = await _resolve_route_preview(
        {"model": "auto", "messages": [{"role": "user", "content": "hello"}]},
        {"x-faigate-profile": "local-only"},
    )

    assert model_requested == "auto"
    assert profile_name == "local-only"
    assert resolved_mode == "eco"
    assert resolved_shortcut is None
    assert decision.provider_name == "local-worker"
    assert payload["model"] == "auto"


@pytest.mark.asyncio
async def test_preview_resolves_model_shortcut(preview_config):
    (
        decision,
        _profile_name,
        _client_tag,
        _attempt_order,
        model_requested,
        resolved_mode,
        resolved_shortcut,
        _hook_state,
        payload,
    ) = await _resolve_route_preview(
        {"model": "local", "messages": [{"role": "user", "content": "hello"}]},
        {},
    )

    assert model_requested == "local"
    assert resolved_mode is None
    assert resolved_shortcut == "local"
    assert decision.provider_name == "local-worker"
    assert payload["model"] == "local-worker"


@pytest.mark.asyncio
async def test_image_preview_resolves_shortcut(preview_config):
    (
        decision,
        _profile_name,
        _client_tag,
        _attempt_order,
        model_requested,
        resolved_mode,
        resolved_shortcut,
        _hook_state,
        payload,
    ) = await _resolve_image_route_preview(
        {"model": "img", "prompt": "make a cat", "size": "1024x1024"},
        {},
        capability="image_generation",
    )

    assert model_requested == "img"
    assert resolved_mode is None
    assert resolved_shortcut == "img"
    assert decision.provider_name == "image-large"
    assert payload["model"] == "image-large"


@pytest.mark.asyncio
async def test_list_models_includes_modes_and_shortcuts(preview_config):
    payload = await list_models()
    model_ids = {row["id"] for row in payload["data"]}

    assert "auto" in model_ids
    assert "eco" in model_ids
    assert "premium" in model_ids
    assert "local" in model_ids
    assert "img" in model_ids


@pytest.mark.asyncio
async def test_provider_catalog_endpoint_reports_alerts(preview_config):
    payload = await provider_catalog()

    assert payload["total_providers"] >= 1
    assert payload["alert_count"] >= 1
    assert "alerts" in payload
    assert "items" in payload


class TestRoutePreview:
    @pytest.mark.asyncio
    async def test_preview_resolves_profile_and_attempt_order(self, preview_config):
        (
            decision,
            profile_name,
            client_tag,
            attempt_order,
            model_requested,
            _resolved_mode,
            _resolved_shortcut,
            hook_state,
            effective_body,
        ) = await _resolve_route_preview(
            {
                "model": "auto",
                "messages": [{"role": "user", "content": "hello from local-only traffic"}],
            },
            {"x-faigate-profile": "local-only"},
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
            _resolved_mode,
            _resolved_shortcut,
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
        assert decision.details["canonical_model"] == "custom/cloud-chat"
        assert decision.details["route_type"] == "direct"
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
            _resolved_mode,
            _resolved_shortcut,
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
            _resolved_mode,
            _resolved_shortcut,
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

    @pytest.mark.asyncio
    async def test_image_route_preview_prefers_matching_policy_tag(self, preview_config):
        response = await preview_image_route(
            _json_request(
                "/api/route/image",
                {
                    "model": "auto",
                    "capability": "image_generation",
                    "prompt": "Create a polished product render.",
                    "size": "1024x1024",
                    "metadata": {"image_policy": "quality"},
                },
            )
        )

        assert response["effective_request"]["image_policy"] == "quality"
        assert response["decision"]["provider"] == "image-large"
        ranking = response["decision"]["details"]["candidate_ranking"]
        assert ranking[0]["provider"] == "image-large"
        assert ranking[0]["image_policy_match"] is True
        assert ranking[0]["requested_image_policy"] == "quality"

    @pytest.mark.asyncio
    async def test_image_route_preview_header_policy_overrides_metadata(self, preview_config):
        response = await preview_image_route(
            _json_request(
                "/api/route/image",
                {
                    "model": "auto",
                    "capability": "image_generation",
                    "prompt": "Create a cheap concept sketch.",
                    "size": "1024x1024",
                    "metadata": {"image_policy": "quality"},
                },
                headers={"x-faigate-image-policy": "cost"},
            )
        )

        assert response["routing_headers"]["x-faigate-image-policy"] == "cost"
        assert response["decision"]["provider"] == "image-cloud"

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
                "image_policy": "editing",
            }
        )

        assert payload["model"] == "image-cloud"
        assert payload["prompt"] == "Retouch the lighting"
        assert payload["n"] == 2
        assert payload["size"] == "1024x1024"
        assert payload["response_format"] == "b64_json"
        assert payload["user"] == "tester"
        assert payload["image_policy"] == "editing"
        assert payload["metadata"]["image_policy"] == "editing"

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
        assert response["summary"]["providers_request_ready"] == 4
        assert response["providers"]["cloud-default"]["request_readiness"]["status"] == "ready"
        assert response["coverage"]["image_generation"]["total"] == 2
        assert response["coverage"]["image_generation"]["healthy"] == 2
        assert response["coverage"]["image_editing"]["providers"] == [
            "image-cloud",
            "image-large",
        ]
        assert response["providers"]["image-cloud"]["image"]["max_outputs"] == 1

    @pytest.mark.asyncio
    async def test_health_request_readiness_enters_cooldown_under_runtime_pressure(
        self, preview_config
    ):
        main_module._adaptive_state.record_failure("cloud-default", error="429 rate limit")
        main_module._adaptive_state.record_failure("cloud-default", error="429 rate limit")

        response = await health()

        readiness = response["providers"]["cloud-default"]["request_readiness"]
        assert readiness["ready"] is False
        assert readiness["status"] == "rate-limited"
        assert readiness["runtime_penalty"] >= 20
        assert readiness["runtime_cooldown_active"] is True
        assert readiness["runtime_window_state"] == "cooldown"
        assert readiness["runtime_cooldown_remaining_s"] > 0
        assert readiness["operator_hint"] == (
            "keep this route out of primary traffic until the cooldown pressure drops"
        )

    @pytest.mark.asyncio
    async def test_health_request_readiness_marks_timeout_routes_as_degraded(self, preview_config):
        main_module._adaptive_state.record_failure(
            "cloud-default",
            error="Timeout: upstream timed out",
        )

        response = await health()

        readiness = response["providers"]["cloud-default"]["request_readiness"]
        assert readiness["ready"] is True
        assert readiness["status"] == "ready-degraded"
        assert readiness["runtime_window_state"] == "degraded"
        assert readiness["runtime_degraded_remaining_s"] > 0
        assert (
            readiness["operator_hint"] == "prefer lower-pressure siblings while this route recovers"
        )

    @pytest.mark.asyncio
    async def test_health_request_readiness_blocks_auth_invalid_routes_immediately(
        self, preview_config
    ):
        main_module._adaptive_state.record_failure("cloud-default", error="401 invalid api key")

        response = await health()

        readiness = response["providers"]["cloud-default"]["request_readiness"]
        assert readiness["ready"] is False
        assert readiness["status"] == "auth-invalid"
        assert readiness["runtime_window_state"] == "cooldown"
        assert readiness["runtime_cooldown_active"] is True

    @pytest.mark.asyncio
    async def test_health_request_readiness_marks_recently_recovered_routes(self, preview_config):
        main_module._adaptive_state.record_failure("cloud-default", error="429 rate limit")
        main_module._adaptive_state.record_success("cloud-default", latency_ms=110.0)

        response = await health()

        readiness = response["providers"]["cloud-default"]["request_readiness"]
        assert readiness["ready"] is True
        assert readiness["status"] == "ready-recovered"
        assert readiness["runtime_recovered_recently"] is True
        assert readiness["runtime_last_recovered_issue_type"] == "rate-limited"
        assert readiness["runtime_recovery_remaining_s"] > 0

    @pytest.mark.asyncio
    async def test_provider_inventory_filters_by_capability(self, preview_config):
        response = await provider_inventory(capability="image_editing")

        provider_names = [provider["name"] for provider in response["providers"]]
        assert provider_names == ["image-cloud", "image-large"]
        assert response["coverage"]["image_editing"]["total"] == 2
        assert response["providers"][0]["contract"] == "image-provider"
        assert "request_readiness" in response
        assert "transport" in response["providers"][0]


@pytest.mark.asyncio
async def test_attempt_metric_fields_capture_same_lane_fallback(monkeypatch):
    monkeypatch.setattr(
        main_module,
        "_providers",
        {
            "anthropic-direct": _ProviderStub(
                name="anthropic-direct",
                model="claude-opus-4-6",
                lane={
                    "family": "anthropic",
                    "name": "quality",
                    "canonical_model": "anthropic/opus-4.6",
                    "route_type": "direct",
                    "cluster": "elite-reasoning",
                    "benchmark_cluster": "quality-coding",
                    "same_model_group": "anthropic/opus-4.6",
                    "degrade_to": ["anthropic/sonnet-4.6"],
                },
            ),
            "anthropic-marketplace": _ProviderStub(
                name="anthropic-marketplace",
                model="claude-opus-4-6",
                lane={
                    "family": "openrouter",
                    "name": "quality",
                    "canonical_model": "anthropic/opus-4.6",
                    "route_type": "aggregator",
                    "cluster": "elite-reasoning",
                    "benchmark_cluster": "quality-coding",
                    "same_model_group": "anthropic/opus-4.6",
                    "degrade_to": ["anthropic/sonnet-4.6"],
                },
            ),
        },
        raising=False,
    )

    metric_fields = _attempt_metric_fields(
        main_module.RoutingDecision(
            provider_name="anthropic-direct",
            layer="heuristic",
            rule_name="complex-code",
            confidence=0.8,
            reason="Heuristic matched",
        ),
        "anthropic-marketplace",
        attempt_order=["anthropic-direct", "anthropic-marketplace"],
    )

    assert metric_fields["canonical_model"] == "anthropic/opus-4.6"
    assert metric_fields["route_type"] == "aggregator"
    assert metric_fields["selection_path"] == "same-lane-route"
    assert metric_fields["decision_details"]["same_model_route"] is True


@pytest.mark.asyncio
async def test_attempt_metric_fields_capture_runtime_recovery_state(monkeypatch):
    monkeypatch.setattr(
        main_module,
        "_providers",
        {
            "deepseek-chat": _ProviderStub(
                name="deepseek-chat",
                model="deepseek-chat",
                lane={
                    "family": "deepseek",
                    "name": "workhorse",
                    "canonical_model": "deepseek/chat",
                    "route_type": "direct",
                    "cluster": "balanced-workhorse",
                },
            ),
        },
        raising=False,
    )
    main_module._adaptive_state.record_failure("deepseek-chat", error="429 rate limit")
    main_module._adaptive_state.record_success("deepseek-chat", latency_ms=95.0)

    metric_fields = _attempt_metric_fields(
        main_module.RoutingDecision(
            provider_name="deepseek-chat",
            layer="heuristic",
            rule_name="general-chat",
            confidence=0.7,
            reason="Heuristic matched",
        ),
        "deepseek-chat",
        attempt_order=["deepseek-chat"],
    )

    runtime_state = metric_fields["decision_details"]["attempt_runtime_state"]
    assert runtime_state["recovered_recently"] is True
    assert runtime_state["last_recovered_issue_type"] == "rate-limited"
