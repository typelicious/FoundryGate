"""Tests for FoundryGate routing engine and cost calculation."""

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

from foundrygate.config import load_config
from foundrygate.metrics import calc_cost
from foundrygate.router import Router


@pytest.fixture
def config():
    return load_config(Path(__file__).parent.parent / "config.yaml")


@pytest.fixture
def router(config):
    return Router(config)


# ── Cost calculation ───────────────────────────────────────────


class TestCostCalculation:
    def test_basic_cost(self):
        cost = calc_cost(1_000_000, 1_000_000, {"input": 0.27, "output": 1.10})
        assert abs(cost - 1.37) < 0.01

    def test_cache_aware_cost(self):
        # 80% cache hit should be cheaper
        no_cache = calc_cost(1000, 1000, {"input": 0.27, "output": 1.10})
        with_cache = calc_cost(
            1000,
            1000,
            {"input": 0.27, "output": 1.10, "cache_read": 0.07},
            cache_hit=800,
            cache_miss=200,
        )
        assert with_cache < no_cache

    def test_100pct_cache_hit(self):
        cost = calc_cost(
            1000,
            0,
            {"input": 0.27, "output": 1.10, "cache_read": 0.07},
            cache_hit=1000,
            cache_miss=0,
        )
        # Should use cache_read rate: 1000 * 0.07 / 1M
        assert abs(cost - 0.00007) < 0.000001

    def test_zero_tokens(self):
        cost = calc_cost(0, 0, {"input": 0.27, "output": 1.10})
        assert cost == 0.0

    def test_flash_lite_cheapest(self):
        ds = calc_cost(1_000_000, 1_000_000, {"input": 0.27, "output": 1.10})
        fl = calc_cost(1_000_000, 1_000_000, {"input": 0.075, "output": 0.30})
        assert fl < ds
        assert fl / ds < 0.3  # Flash-Lite should be >70% cheaper


# ── Static routing ─────────────────────────────────────────────


class TestStaticRouting:
    @pytest.mark.asyncio
    async def test_heartbeat(self, router):
        d = await router.route(
            [{"role": "system", "content": "heartbeat check"}, {"role": "user", "content": "ok"}],
            model_requested="auto",
        )
        assert d.provider_name == "gemini-flash-lite"
        assert d.layer == "static"
        assert d.rule_name == "heartbeat"

    @pytest.mark.asyncio
    async def test_explicit_reasoner(self, router):
        d = await router.route(
            [{"role": "user", "content": "hello"}],
            model_requested="r1",
        )
        assert d.provider_name == "deepseek-reasoner"
        assert d.layer == "static"

    @pytest.mark.asyncio
    async def test_explicit_flash(self, router):
        d = await router.route(
            [{"role": "user", "content": "hello"}],
            model_requested="flash",
        )
        assert d.provider_name == "gemini-flash"

    @pytest.mark.asyncio
    async def test_subagent_header(self, router):
        d = await router.route(
            [{"role": "user", "content": "process file"}],
            model_requested="auto",
            headers={"x-openclaw-source": "subagent-42"},
        )
        assert d.provider_name == "deepseek-chat"
        assert d.rule_name == "subagent"

    def test_static_match_requires_all_fields_by_default(self, router):
        ctx = types.SimpleNamespace(
            model_requested="auto",
            system_prompt="delegated task planner",
            headers={"x-openclaw-source": "primary-agent"},
        )
        assert (
            router._match_static(  # noqa: SLF001
                {
                    "system_prompt_contains": ["delegated task"],
                    "header_contains": {"x-openclaw-source": ["subagent"]},
                },
                ctx,
            )
            is False
        )
        assert (
            router._match_static(  # noqa: SLF001
                {
                    "system_prompt_contains": ["delegated task"],
                    "header_contains": {"x-openclaw-source": ["primary-agent"]},
                },
                ctx,
            )
            is True
        )


# ── Heuristic routing ─────────────────────────────────────────


class TestHeuristicRouting:
    @pytest.mark.asyncio
    async def test_math_reasoning(self, router):
        d = await router.route(
            [{"role": "user", "content": "Prove the theorem step by step using induction"}],
            model_requested="auto",
        )
        assert d.provider_name == "deepseek-reasoner"
        assert "math" in d.rule_name or "reasoning" in d.rule_name

    @pytest.mark.asyncio
    async def test_complex_code(self, router):
        d = await router.route(
            [
                {
                    "role": "user",
                    "content": "debug this race condition and refactor the architecture",
                }
            ],
            model_requested="auto",
        )
        assert d.provider_name == "deepseek-reasoner"

    @pytest.mark.asyncio
    async def test_tool_use(self, router):
        d = await router.route(
            [{"role": "user", "content": "search files"}],
            model_requested="auto",
            has_tools=True,
        )
        assert d.provider_name == "deepseek-chat"
        assert d.rule_name == "tool-use"

    @pytest.mark.asyncio
    async def test_simple_query_de(self, router):
        d = await router.route(
            [{"role": "user", "content": "Was ist ein Monad?"}],
            model_requested="auto",
        )
        assert d.provider_name == "gemini-flash-lite"
        assert d.rule_name == "simple-query"

    @pytest.mark.asyncio
    async def test_simple_query_zh(self, router):
        d = await router.route(
            [{"role": "user", "content": "你好"}],
            model_requested="auto",
        )
        assert d.provider_name == "gemini-flash-lite"

    @pytest.mark.asyncio
    async def test_short_message_fallback(self, router):
        d = await router.route(
            [{"role": "user", "content": "ok"}],
            model_requested="auto",
        )
        assert d.provider_name == "deepseek-chat"

    @pytest.mark.asyncio
    async def test_system_prompt_not_scored(self, router):
        """Critical: system prompt keywords must NOT trigger reasoning tier."""
        d = await router.route(
            [
                {
                    "role": "system",
                    "content": (
                        "You are expert at proving theorems step by step with "
                        "complex reasoning and debugging race conditions"
                    ),
                },
                {"role": "user", "content": "find my file"},
            ],
            model_requested="auto",
        )
        # Should NOT be deepseek-reasoner despite system prompt keywords
        assert d.provider_name != "deepseek-reasoner"

    def test_heuristic_match_requires_all_fields_by_default(self, router):
        ctx = types.SimpleNamespace(
            has_tools=True,
            total_tokens=90,
            last_user_message="search files and summarize the result",
        )
        assert (
            router._match_heuristic(  # noqa: SLF001
                {
                    "has_tools": True,
                    "estimated_tokens": {"greater_than": 100},
                },
                ctx,
            )
            is False
        )
        assert (
            router._match_heuristic(  # noqa: SLF001
                {
                    "has_tools": True,
                    "estimated_tokens": {"less_than": 100},
                },
                ctx,
            )
            is True
        )


# ── Health fallback ────────────────────────────────────────────


class TestHealthFallback:
    @pytest.mark.asyncio
    async def test_unhealthy_primary_falls_through(self, router):
        d = await router.route(
            [{"role": "user", "content": "hello"}],
            model_requested="r1",
            provider_health={
                "deepseek-reasoner": {"healthy": False},
                "deepseek-chat": {"healthy": True},
            },
        )
        # Should fall through to next healthy provider
        assert d.provider_name != "deepseek-reasoner"
        assert "fallback" in d.rule_name


# ── Regression: content=None handling (GitHub: fix/runtime-bugs) ──────────────


class TestNoneContentHandling:
    """Regression tests for TypeError: sequence item N: expected str, NoneType.

    The OpenAI spec allows content=null on tool/assistant messages.
    FoundryGate must not crash when these arrive in the messages array.
    """

    @pytest.mark.asyncio
    async def test_null_system_content(self, router):
        """content=null on a system message must not raise TypeError."""
        d = await router.route(
            [
                {"role": "system", "content": None},
                {"role": "user", "content": "ping"},
            ],
            model_requested="auto",
        )
        assert d.provider_name  # any provider is fine — just must not crash

    @pytest.mark.asyncio
    async def test_null_assistant_content(self, router):
        """content=null on an assistant message (tool-call turn) must not raise TypeError."""
        d = await router.route(
            [
                {"role": "user", "content": "call the tool"},
                {"role": "assistant", "content": None, "tool_calls": [{"id": "x"}]},
                {"role": "tool", "content": "result", "tool_call_id": "x"},
                {"role": "user", "content": "ok now answer"},
            ],
            model_requested="auto",
        )
        assert d.provider_name

    @pytest.mark.asyncio
    async def test_null_user_content(self, router):
        """content=null on the user message itself must not raise TypeError."""
        d = await router.route(
            [{"role": "user", "content": None}],
            model_requested="auto",
        )
        assert d.provider_name

    @pytest.mark.asyncio
    async def test_mixed_null_and_real_content(self, router):
        """Mixed None and real content in the same messages list."""
        d = await router.route(
            [
                {"role": "system", "content": None},
                {"role": "user", "content": "Prove this theorem step by step"},
                {"role": "assistant", "content": None},
                {"role": "user", "content": "continue"},
            ],
            model_requested="auto",
        )
        assert d.provider_name
