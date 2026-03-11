"""Tests for policy-based provider selection."""

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
from foundrygate.router import Router


def _write_config(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(body)
    return path


class TestRoutingPolicies:
    @pytest.mark.asyncio
    async def test_policy_prefers_local_provider_for_matching_profile(self, tmp_path):
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
    backend: openai-compat
    base_url: "http://127.0.0.1:11434/v1"
    api_key: "local"
    model: "llama3"
    tier: local
routing_policies:
  enabled: true
  rules:
    - name: local-only-profile
      match:
        header_contains:
          x-foundrygate-profile: ["local-only"]
      select:
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
        router = Router(cfg)

        decision = await router.route(
            [{"role": "user", "content": "hello"}],
            model_requested="auto",
            headers={"x-foundrygate-profile": "local-only"},
        )

        assert decision.layer == "policy"
        assert decision.rule_name == "local-only-profile"
        assert decision.provider_name == "local-worker"

    @pytest.mark.asyncio
    async def test_policy_falls_to_next_healthy_preferred_candidate(self, tmp_path):
        cfg = load_config(
            _write_config(
                tmp_path,
                """
server:
  host: "127.0.0.1"
  port: 8090
providers:
  tool-primary:
    backend: openai-compat
    base_url: "https://api.example.com/v1"
    api_key: "secret"
    model: "tool-primary"
    tier: default
    capabilities:
      tools: true
  tool-secondary:
    backend: openai-compat
    base_url: "https://api.example.com/v1"
    api_key: "secret"
    model: "tool-secondary"
    tier: default
    capabilities:
      tools: true
  cheap-chat:
    backend: openai-compat
    base_url: "https://api.example.com/v1"
    api_key: "secret"
    model: "cheap-chat"
    tier: cheap
routing_policies:
  enabled: true
  rules:
    - name: tool-traffic
      match:
        has_tools: true
      select:
        require_capabilities: ["tools"]
        prefer_providers: ["tool-primary", "tool-secondary"]
fallback_chain:
  - cheap-chat
metrics:
  enabled: false
""",
            )
        )
        router = Router(cfg)

        decision = await router.route(
            [{"role": "user", "content": "search files"}],
            model_requested="auto",
            has_tools=True,
            provider_health={
                "tool-primary": {"healthy": False},
                "tool-secondary": {"healthy": True},
            },
        )

        assert decision.layer == "policy"
        assert decision.provider_name == "tool-secondary"


class TestPolicyValidation:
    def test_policy_rejects_unknown_provider_reference(self, tmp_path):
        path = _write_config(
            tmp_path,
            """
server:
  host: "127.0.0.1"
  port: 8090
providers:
  primary:
    backend: openai-compat
    base_url: "https://api.example.com/v1"
    api_key: "secret"
    model: "chat-model"
routing_policies:
  enabled: true
  rules:
    - name: invalid-provider
      match: {}
      select:
        allow_providers: ["missing-provider"]
fallback_chain: []
metrics:
  enabled: false
""",
        )

        with pytest.raises(ConfigError, match="unknown providers"):
            load_config(path)

    def test_policy_rejects_unknown_capability_reference(self, tmp_path):
        path = _write_config(
            tmp_path,
            """
server:
  host: "127.0.0.1"
  port: 8090
providers:
  primary:
    backend: openai-compat
    base_url: "https://api.example.com/v1"
    api_key: "secret"
    model: "chat-model"
routing_policies:
  enabled: true
  rules:
    - name: invalid-capability
      match: {}
      select:
        capability_values:
          not_real: true
fallback_chain: []
metrics:
  enabled: false
""",
        )

        with pytest.raises(ConfigError, match="unknown capability"):
            load_config(path)
