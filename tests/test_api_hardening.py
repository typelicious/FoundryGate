"""Functional API tests for v0.9 hardening surfaces."""

from __future__ import annotations

import importlib
import sys
import types
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

sys.modules.pop("httpx", None)
import httpx  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

sys.modules["httpx"] = httpx

sys.modules.pop("foundrygate.providers", None)
sys.modules.pop("foundrygate.updates", None)
sys.modules.pop("foundrygate.main", None)

import foundrygate.main as main_module  # noqa: E402
from foundrygate.config import load_config  # noqa: E402
from foundrygate.router import Router  # noqa: E402

importlib.reload(main_module)


def _write_config(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(body)
    return path


class _ProviderStub:
    def __init__(self):
        self.name = "cloud-default"
        self.model = "chat-model"
        self.backend_type = "openai-compat"
        self.contract = "generic"
        self.tier = "default"
        self.capabilities = {"chat": True, "local": False, "cloud": True, "network_zone": "public"}
        self.context_window = 128000
        self.limits = {"max_input_tokens": 128000, "max_output_tokens": 4096}
        self.cache = {"mode": "none", "read_discount": False}
        self.image = {}
        self.health = types.SimpleNamespace(
            healthy=True,
            last_check=1.0,
            avg_latency_ms=12.0,
            last_error="",
            to_dict=lambda: {
                "name": "cloud-default",
                "healthy": True,
                "consecutive_failures": 0,
                "avg_latency_ms": 12.0,
                "last_error": "",
            },
        )

    async def close(self):
        return None

    async def complete(self, *_args, **_kwargs):
        return {
            "id": "chatcmpl-123",
            "object": "chat.completion",
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": "ok"},
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            "_foundrygate": {"latency_ms": 12},
        }


class _FailingProviderStub(_ProviderStub):
    async def complete(self, *_args, **_kwargs):
        raise main_module.ProviderError(
            "cloud-default",
            502,
            "upstream trace: token=secret should not leak",
        )


class _MetricsStub:
    def log_request(self, **_kwargs):
        return None

    def get_totals(self, **_kwargs):
        return {}

    def get_provider_summary(self, **_kwargs):
        return []

    def get_modality_breakdown(self, **_kwargs):
        return []

    def get_routing_breakdown(self, **_kwargs):
        return []

    def get_client_breakdown(self, **_kwargs):
        return []

    def get_client_totals(self, **_kwargs):
        return [
            {
                "client_profile": "openclaw",
                "client_tag": "agent-alpha",
                "requests": 12,
                "failures": 1,
                "success_pct": 91.7,
                "prompt_tokens": 1500,
                "compl_tokens": 450,
                "total_tokens": 1950,
                "cost_usd": 0.1642,
                "cost_per_request_usd": 0.0137,
                "avg_latency_ms": 620.0,
                "modalities": "chat",
                "providers": "cloud-default",
            },
            {
                "client_profile": "cli",
                "client_tag": "batch-jobs",
                "requests": 5,
                "failures": 2,
                "success_pct": 60.0,
                "prompt_tokens": 4200,
                "compl_tokens": 1200,
                "total_tokens": 5400,
                "cost_usd": 0.441,
                "cost_per_request_usd": 0.0882,
                "avg_latency_ms": 980.0,
                "modalities": "chat,image_generation",
                "providers": "cloud-default",
            },
        ]

    def get_operator_breakdown(self, **_kwargs):
        return []

    def get_hourly_series(self, *_args, **_kwargs):
        return []

    def get_daily_totals(self, *_args, **_kwargs):
        return []

    def get_recent(self, *_args, **_kwargs):
        return []

    def get_operator_events(self, *_args, **_kwargs):
        return []


@pytest.fixture
def api_client(tmp_path, monkeypatch):
    cfg = load_config(
        _write_config(
            tmp_path,
            """
server:
  host: "127.0.0.1"
  port: 8090
  log_level: "info"
security:
  max_json_body_bytes: 256
  max_upload_bytes: 8
  max_header_value_chars: 12
providers:
  cloud-default:
    backend: openai-compat
    base_url: "https://api.example.com/v1"
    api_key: "secret"
    model: "chat-model"
fallback_chain:
  - cloud-default
metrics:
  enabled: false
""",
        )
    )

    @asynccontextmanager
    async def _noop_lifespan(_app):
        yield

    monkeypatch.setattr(main_module, "_config", cfg, raising=False)
    monkeypatch.setattr(main_module, "_router", Router(cfg), raising=False)
    monkeypatch.setattr(
        main_module,
        "_providers",
        {"cloud-default": _ProviderStub()},
        raising=False,
    )
    monkeypatch.setattr(main_module, "_metrics", _MetricsStub(), raising=False)
    monkeypatch.setattr(main_module.app.router, "lifespan_context", _noop_lifespan, raising=False)

    with TestClient(main_module.app) as client:
        yield client


def test_dashboard_sets_security_headers(api_client):
    response = api_client.get("/dashboard")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    csp = response.headers["content-security-policy"]
    assert "frame-ancestors 'none'" in csp
    assert "'unsafe-inline'" not in csp
    assert "sha256-" in csp


def test_stats_includes_client_highlights(api_client):
    response = api_client.get("/api/stats")

    assert response.status_code == 200
    body = response.json()
    assert body["client_highlights"]["top_requests"]["client_tag"] == "agent-alpha"
    assert body["client_highlights"]["top_tokens"]["client_tag"] == "batch-jobs"
    assert body["client_highlights"]["top_cost"]["client_tag"] == "batch-jobs"
    assert body["client_highlights"]["highest_failure_rate"]["client_tag"] == "batch-jobs"
    assert body["client_highlights"]["slowest_client"]["client_tag"] == "batch-jobs"


def test_route_preview_rejects_large_json_payload(api_client):
    response = api_client.post(
        "/api/route",
        json={
            "model": "auto",
            "messages": [{"role": "user", "content": "x" * 400}],
        },
    )

    assert response.status_code == 413
    assert response.json()["type"] == "payload_too_large"


def test_route_preview_sanitizes_header_values(api_client):
    response = api_client.post(
        "/api/route",
        headers={"X-FoundryGate-Client": "CLI-AGENT-WITH-VERY-LONG-NAME"},
        json={
            "model": "auto",
            "messages": [{"role": "user", "content": "route this safely"}],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["routing_headers"]["x-foundrygate-client"] == "CLI-AGENT-WI"
    assert body["client_tag"] == "cli-agent-wi"


def test_image_edit_rejects_large_upload(api_client):
    response = api_client.post(
        "/v1/images/edits",
        data={"model": "auto", "prompt": "remove background"},
        files={"image": ("input.png", b"0123456789", "image/png")},
    )

    assert response.status_code == 413
    assert response.json()["type"] == "payload_too_large"


def test_chat_completions_returns_security_headers(api_client):
    response = api_client.post(
        "/v1/chat/completions",
        json={
            "model": "auto",
            "messages": [{"role": "user", "content": "say hi"}],
        },
    )

    assert response.status_code == 200
    assert response.headers["x-foundrygate-provider"] == "cloud-default"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_chat_completions_hides_upstream_provider_details(api_client, monkeypatch):
    monkeypatch.setattr(
        main_module,
        "_providers",
        {"cloud-default": _FailingProviderStub()},
        raising=False,
    )

    response = api_client.post(
        "/v1/chat/completions",
        json={
            "model": "auto",
            "messages": [{"role": "user", "content": "cause failure"}],
        },
    )

    assert response.status_code == 502
    body = response.json()
    assert body["error"]["message"] == "All providers failed"
    assert "secret" not in response.text
    assert body["error"]["attempts"] == [
        {"provider": "cloud-default", "status": 502, "category": "upstream_server_error"}
    ]
