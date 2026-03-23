"""Tests for context-window, provider-limit, and cache-aware routing."""

from datetime import date, timedelta
from pathlib import Path

import pytest

from faigate.config import ConfigError, load_config
from faigate.router import Router


def _write_config(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(body)
    return path


@pytest.mark.asyncio
async def test_profile_prefers_cache_and_context_fit(tmp_path):
    cfg = load_config(
        _write_config(
            tmp_path,
            """
server:
  host: "127.0.0.1"
  port: 8090
providers:
  cheap-small:
    backend: openai-compat
    base_url: "https://api.example.com/v1"
    api_key: "secret"
    model: "cheap-chat"
    tier: default
    context_window: 4096
    limits:
      max_input_tokens: 2048
    cache:
      mode: none
  cached-large:
    backend: openai-compat
    base_url: "https://api.example.com/v1"
    api_key: "secret"
    model: "cached-chat"
    tier: default
    context_window: 131072
    limits:
      max_input_tokens: 65536
    cache:
      mode: implicit
      read_discount: true
client_profiles:
  enabled: true
  default: generic
  profiles:
    generic:
      prefer_tiers: ["default"]
static_rules:
  enabled: false
  rules: []
heuristic_rules:
  enabled: false
  rules: []
fallback_chain:
  - cached-large
metrics:
  enabled: false
""",
        )
    )
    router = Router(cfg)
    long_system = "stable prefix " * 80

    decision = await router.route(
        [
            {"role": "system", "content": long_system},
            {"role": "user", "content": "Summarize this long request."},
        ],
        model_requested="auto",
        requested_max_tokens=512,
        client_profile="generic",
        profile_hints=cfg.client_profiles["profiles"]["generic"],
        headers={"x-faigate-cache": "prefer-cache"},
    )

    assert decision.layer == "profile"
    assert decision.provider_name == "cached-large"


@pytest.mark.asyncio
async def test_unfit_provider_falls_back_to_context_fit_provider(tmp_path):
    cfg = load_config(
        _write_config(
            tmp_path,
            """
server:
  host: "127.0.0.1"
  port: 8090
providers:
  tiny-reasoner:
    backend: openai-compat
    base_url: "https://api.example.com/v1"
    api_key: "secret"
    model: "tiny-reasoner"
    tier: reasoning
    context_window: 4096
    limits:
      max_input_tokens: 1024
  roomy-default:
    backend: openai-compat
    base_url: "https://api.example.com/v1"
    api_key: "secret"
    model: "roomy-chat"
    tier: default
    context_window: 65536
    limits:
      max_input_tokens: 32768
static_rules:
  enabled: false
  rules: []
heuristic_rules:
  enabled: true
  rules:
    - name: default-route
      match:
        fallthrough: true
      route_to: tiny-reasoner
fallback_chain:
  - roomy-default
metrics:
  enabled: false
""",
        )
    )
    router = Router(cfg)
    huge_user = "context " * 700

    decision = await router.route(
        [{"role": "user", "content": huge_user}],
        model_requested="auto",
        requested_max_tokens=256,
        client_profile="generic",
        headers={},
        provider_health={
            "tiny-reasoner": {"healthy": True},
            "roomy-default": {"healthy": True},
        },
    )

    assert decision.provider_name == "roomy-default"
    assert decision.rule_name.endswith("fallback")
    assert "request dimensions" in decision.reason


def test_provider_rejects_invalid_cache_mode(tmp_path):
    path = _write_config(
        tmp_path,
        """
server:
  host: "127.0.0.1"
  port: 8090
providers:
  invalid:
    backend: openai-compat
    base_url: "https://api.example.com/v1"
    api_key: "secret"
    model: "chat"
    cache:
      mode: strange
fallback_chain: []
metrics:
  enabled: false
""",
    )

    with pytest.raises(ConfigError, match="cache.mode"):
        load_config(path)


@pytest.mark.asyncio
async def test_profile_ranking_prefers_lower_latency_and_fewer_failures(tmp_path):
    cfg = load_config(
        _write_config(
            tmp_path,
            """
server:
  host: "127.0.0.1"
  port: 8090
providers:
  fast-local:
    contract: local-worker
    backend: openai-compat
    base_url: "http://127.0.0.1:11434/v1"
    api_key: "local"
    model: "llama3"
    tier: local
    context_window: 32768
    capabilities:
      local: true
      cloud: false
  slow-local:
    contract: local-worker
    backend: openai-compat
    base_url: "http://127.0.0.1:22434/v1"
    api_key: "local"
    model: "qwen"
    tier: local
    context_window: 32768
    capabilities:
      local: true
      cloud: false
client_profiles:
  enabled: true
  default: generic
  profiles:
    generic:
      prefer_tiers: ["local"]
fallback_chain:
  - fast-local
metrics:
  enabled: false
""",
        )
    )
    router = Router(cfg)

    decision = await router.route(
        [{"role": "user", "content": "pick the best local model"}],
        model_requested="auto",
        client_profile="generic",
        profile_hints=cfg.client_profiles["profiles"]["generic"],
        provider_health={
            "fast-local": {
                "healthy": True,
                "avg_latency_ms": 90,
                "consecutive_failures": 0,
            },
            "slow-local": {
                "healthy": True,
                "avg_latency_ms": 1400,
                "consecutive_failures": 3,
            },
        },
    )

    assert decision.layer == "profile"
    assert decision.provider_name == "fast-local"
    ranking = decision.details["candidate_ranking"]
    assert ranking[0]["provider"] == "fast-local"
    assert ranking[0]["score_total"] > ranking[1]["score_total"]
    assert ranking[0]["latency_score"] > ranking[1]["latency_score"]
    assert ranking[0]["failure_score"] > ranking[1]["failure_score"]


@pytest.mark.asyncio
async def test_locality_preference_and_context_scores_appear_in_ranking(tmp_path):
    cfg = load_config(
        _write_config(
            tmp_path,
            """
server:
  host: "127.0.0.1"
  port: 8090
providers:
  local-fit:
    contract: local-worker
    backend: openai-compat
    base_url: "http://127.0.0.1:11434/v1"
    api_key: "local"
    model: "llama3"
    tier: local
    context_window: 65536
    limits:
      max_input_tokens: 32000
      max_output_tokens: 2048
    capabilities:
      local: true
      cloud: false
    cache:
      mode: implicit
      read_discount: true
  cloud-roomy:
    backend: openai-compat
    base_url: "https://api.example.com/v1"
    api_key: "secret"
    model: "cloud-roomy"
    tier: default
    context_window: 131072
    limits:
      max_input_tokens: 64000
      max_output_tokens: 4096
    capabilities:
      local: false
      cloud: true
client_profiles:
  enabled: true
  default: generic
  profiles:
    generic:
      prefer_tiers: ["local"]
      capability_values:
        local: true
fallback_chain:
  - cloud-roomy
metrics:
  enabled: false
""",
        )
    )
    router = Router(cfg)
    long_system = "stable prefix " * 80

    decision = await router.route(
        [
            {"role": "system", "content": long_system},
            {"role": "user", "content": "stay local if it fits"},
        ],
        model_requested="auto",
        requested_max_tokens=512,
        client_profile="generic",
        profile_hints=cfg.client_profiles["profiles"]["generic"],
        headers={"x-faigate-cache": "prefer-cache"},
        provider_health={
            "local-fit": {"healthy": True, "avg_latency_ms": 120, "consecutive_failures": 0},
            "cloud-roomy": {"healthy": True, "avg_latency_ms": 110, "consecutive_failures": 0},
        },
    )

    assert decision.provider_name == "local-fit"
    ranking = decision.details["candidate_ranking"]
    assert ranking[0]["provider"] == "local-fit"
    assert ranking[0]["locality_preference"] == "local"
    assert ranking[0]["cache_score"] >= 7
    assert ranking[0]["context_score"] >= 4
    assert ranking[0]["input_score"] >= 4
    assert ranking[0]["output_score"] >= 2


@pytest.mark.asyncio
async def test_quality_posture_prefers_same_lane_route_before_cluster_degrade(tmp_path):
    cfg = load_config(
        _write_config(
            tmp_path,
            """
server:
  host: "127.0.0.1"
  port: 8090
providers:
  anthropic-direct:
    backend: openai-compat
    base_url: "https://api.example.com/v1"
    api_key: "secret"
    model: "claude-opus-4-6"
    tier: mid
    lane:
      family: anthropic
      name: quality
      canonical_model: anthropic/opus-4.6
      route_type: direct
      cluster: elite-reasoning
      benchmark_cluster: quality-coding
      quality_tier: premium
      reasoning_strength: high
      same_model_group: anthropic/opus-4.6
      degrade_to: ["anthropic/sonnet-4.6", "openai/gpt-4o"]
  anthropic-marketplace:
    backend: openai-compat
    base_url: "https://router.example.com/v1"
    api_key: "secret"
    model: "claude-opus-4-6"
    tier: fallback
    lane:
      family: anthropic
      name: quality
      canonical_model: anthropic/opus-4.6
      route_type: aggregator
      cluster: elite-reasoning
      benchmark_cluster: quality-coding
      quality_tier: premium
      reasoning_strength: high
      same_model_group: anthropic/opus-4.6
      degrade_to: ["anthropic/sonnet-4.6", "openai/gpt-4o"]
  openai-alt:
    backend: openai-compat
    base_url: "https://api.openai.example/v1"
    api_key: "secret"
    model: "gpt-4o"
    tier: mid
    lane:
      family: openai
      name: balanced
      canonical_model: openai/gpt-4o
      route_type: direct
      cluster: quality-workhorse
      benchmark_cluster: quality-coding
      quality_tier: high
      reasoning_strength: high
      same_model_group: openai/gpt-4o
      degrade_to: ["openai/gpt-4o-mini"]
client_profiles:
  enabled: true
  default: generic
  profiles:
    generic:
      routing_mode: premium
      prefer_tiers: ["mid", "fallback"]
routing_modes:
  enabled: true
  default: auto
  modes:
    premium:
      select:
        prefer_tiers: ["mid", "reasoning", "fallback"]
static_rules:
  enabled: false
  rules: []
heuristic_rules:
  enabled: true
  rules:
    - name: quality-default
      match:
        fallthrough: true
      route_to: anthropic-direct
fallback_chain:
  - openai-alt
  - anthropic-marketplace
metrics:
  enabled: false
""",
        )
    )
    router = Router(cfg)

    decision = await router.route(
        [{"role": "user", "content": "Review this architecture decision in depth."}],
        model_requested="auto",
        client_profile="generic",
        profile_hints=cfg.client_profiles["profiles"]["generic"],
        provider_health={
            "anthropic-direct": {"healthy": False, "last_error": "quota exhausted"},
            "anthropic-marketplace": {"healthy": True, "avg_latency_ms": 600},
            "openai-alt": {"healthy": True, "avg_latency_ms": 180},
        },
    )

    assert decision.provider_name == "anthropic-marketplace"
    assert decision.details["selection_path"] == "same-lane-route"
    assert decision.details["canonical_model"] == "anthropic/opus-4.6"
    ranking = decision.details["fallback_ranking"]
    assert ranking[0]["provider"] == "anthropic-marketplace"
    assert ranking[0]["same_model_route"] is True
    assert ranking[0]["selection_path"] == "same-lane-route"


@pytest.mark.asyncio
async def test_quality_posture_tempers_freshly_recovered_route(tmp_path):
    cfg = load_config(
        _write_config(
            tmp_path,
            """
server:
  host: "127.0.0.1"
  port: 8090
providers:
  stable-direct:
    backend: openai-compat
    base_url: "https://stable.example.com/v1"
    api_key: "secret"
    model: "claude-sonnet-4-6"
    tier: mid
    lane:
      family: anthropic
      name: workhorse
      canonical_model: anthropic/sonnet-4.6
      route_type: direct
      cluster: quality-workhorse
      benchmark_cluster: quality-coding
      quality_tier: high
      reasoning_strength: high
      same_model_group: anthropic/sonnet-4.6
  recovered-direct:
    backend: openai-compat
    base_url: "https://recovered.example.com/v1"
    api_key: "secret"
    model: "claude-sonnet-4-6"
    tier: mid
    lane:
      family: anthropic
      name: workhorse
      canonical_model: anthropic/sonnet-4.6
      route_type: direct
      cluster: quality-workhorse
      benchmark_cluster: quality-coding
      quality_tier: high
      reasoning_strength: high
      same_model_group: anthropic/sonnet-4.6
client_profiles:
  enabled: true
  default: generic
  profiles:
    generic:
      routing_mode: premium
      prefer_tiers: ["mid"]
routing_modes:
  enabled: true
  default: auto
  modes:
    premium:
      select:
        prefer_tiers: ["mid"]
heuristic_rules:
  enabled: false
  rules: []
fallback_chain: []
metrics:
  enabled: false
""",
        )
    )
    router = Router(cfg)

    decision = await router.route(
        [{"role": "user", "content": "Review this architecture decision in depth."}],
        model_requested="auto",
        client_profile="generic",
        profile_hints=cfg.client_profiles["profiles"]["generic"],
        provider_health={
            "stable-direct": {"healthy": True, "avg_latency_ms": 110, "consecutive_failures": 0},
            "recovered-direct": {"healthy": True, "avg_latency_ms": 95, "consecutive_failures": 0},
        },
        provider_runtime_state={
            "recovered-direct": {
                "penalty": 0,
                "window_state": "clear",
                "recovered_recently": True,
                "recovery_window_s": 300,
                "recovery_remaining_s": 280,
                "last_recovered_issue_type": "rate-limited",
            }
        },
    )

    assert decision.provider_name == "stable-direct"
    ranking = decision.details["candidate_ranking"]
    assert ranking[0]["provider"] == "stable-direct"
    recovered_row = next(row for row in ranking if row["provider"] == "recovered-direct")
    assert recovered_row["recovery_score"] < 0
    assert recovered_row["runtime_recovered_recently"] is True


@pytest.mark.asyncio
async def test_balanced_posture_allows_older_recovered_route_back_to_top(tmp_path):
    cfg = load_config(
        _write_config(
            tmp_path,
            """
server:
  host: "127.0.0.1"
  port: 8090
providers:
  stable-direct:
    backend: openai-compat
    base_url: "https://stable.example.com/v1"
    api_key: "secret"
    model: "deepseek-chat"
    tier: default
    lane:
      family: deepseek
      name: workhorse
      canonical_model: deepseek/chat
      route_type: direct
      cluster: balanced-workhorse
      benchmark_cluster: balanced-coding
      quality_tier: mid
      reasoning_strength: mid
      same_model_group: deepseek/chat
  recovered-direct:
    backend: openai-compat
    base_url: "https://recovered.example.com/v1"
    api_key: "secret"
    model: "deepseek-chat"
    tier: default
    lane:
      family: deepseek
      name: workhorse
      canonical_model: deepseek/chat
      route_type: direct
      cluster: balanced-workhorse
      benchmark_cluster: balanced-coding
      quality_tier: mid
      reasoning_strength: mid
      same_model_group: deepseek/chat
client_profiles:
  enabled: true
  default: generic
  profiles:
    generic:
      routing_mode: auto
      prefer_tiers: ["default"]
routing_modes:
  enabled: true
  default: auto
  modes:
    auto:
      select:
        prefer_tiers: ["default"]
heuristic_rules:
  enabled: false
  rules: []
fallback_chain: []
metrics:
  enabled: false
""",
        )
    )
    router = Router(cfg)

    decision = await router.route(
        [{"role": "user", "content": "Keep this coding answer pragmatic and concise."}],
        model_requested="auto",
        client_profile="generic",
        profile_hints=cfg.client_profiles["profiles"]["generic"],
        provider_health={
            "stable-direct": {"healthy": True, "avg_latency_ms": 180, "consecutive_failures": 0},
            "recovered-direct": {"healthy": True, "avg_latency_ms": 90, "consecutive_failures": 0},
        },
        provider_runtime_state={
            "recovered-direct": {
                "penalty": 0,
                "window_state": "clear",
                "recovered_recently": True,
                "recovery_window_s": 300,
                "recovery_remaining_s": 40,
                "last_recovered_issue_type": "timeout",
            }
        },
    )

    assert decision.provider_name == "recovered-direct"
    ranking = decision.details["candidate_ranking"]
    recovered_row = next(row for row in ranking if row["provider"] == "recovered-direct")
    assert recovered_row["recovery_score"] > 0
    assert recovered_row["runtime_last_recovered_issue_type"] == "timeout"


@pytest.mark.asyncio
async def test_eco_posture_prefers_budget_lane_over_premium_direct_provider(tmp_path):
    cfg = load_config(
        _write_config(
            tmp_path,
            """
server:
  host: "127.0.0.1"
  port: 8090
providers:
  premium-direct:
    backend: openai-compat
    base_url: "https://premium.example.com/v1"
    api_key: "secret"
    model: "claude-opus-4-6"
    tier: default
    lane:
      family: anthropic
      name: quality
      canonical_model: anthropic/opus-4.6
      route_type: direct
      cluster: elite-reasoning
      benchmark_cluster: quality-coding
      quality_tier: premium
      reasoning_strength: high
      same_model_group: anthropic/opus-4.6
  budget-aggregator:
    backend: openai-compat
    base_url: "https://budget.example.com/v1"
    api_key: "secret"
    model: "glm-5-free"
    tier: fallback
    lane:
      family: kilo
      name: free
      canonical_model: aggregator/kilo-glm5-free
      route_type: aggregator
      cluster: budget-general
      benchmark_cluster: free-coding
      quality_tier: free
      reasoning_strength: mid
      same_model_group: aggregator/kilo-glm5-free
client_profiles:
  enabled: true
  default: generic
  profiles:
    generic:
      routing_mode: eco
      prefer_tiers: ["default", "fallback"]
routing_modes:
  enabled: true
  default: auto
  modes:
    eco:
      select:
        prefer_tiers: ["default", "fallback"]
fallback_chain:
  - budget-aggregator
metrics:
  enabled: false
""",
        )
    )
    router = Router(cfg)

    decision = await router.route(
        [{"role": "user", "content": "Refactor this script but keep the answer compact."}],
        model_requested="auto",
        client_profile="generic",
        profile_hints=cfg.client_profiles["profiles"]["generic"],
        provider_health={
            "premium-direct": {"healthy": True, "avg_latency_ms": 140},
            "budget-aggregator": {"healthy": True, "avg_latency_ms": 220},
        },
    )

    assert decision.provider_name == "budget-aggregator"
    ranking = decision.details["candidate_ranking"]
    assert ranking[0]["provider"] == "budget-aggregator"
    assert ranking[0]["routing_posture"] == "eco"
    assert ranking[0]["route_type"] == "aggregator"
    assert ranking[0]["canonical_model"] == "aggregator/kilo-glm5-free"
    assert ranking[0]["benchmark_score"] > ranking[1]["benchmark_score"]


@pytest.mark.asyncio
async def test_eco_posture_prefers_cheaper_same_cluster_route(tmp_path):
    cfg = load_config(
        _write_config(
            tmp_path,
            """
server:
  host: "127.0.0.1"
  port: 8090
providers:
  standard-workhorse:
    backend: openai-compat
    base_url: "https://standard.example.com/v1"
    api_key: "secret"
    model: "deepseek-chat"
    tier: default
    pricing:
      input: 1.20
      output: 4.80
      cache_read: 0.60
    lane:
      family: deepseek
      name: workhorse
      canonical_model: deepseek/chat
      route_type: direct
      cluster: balanced-workhorse
      benchmark_cluster: balanced-coding
      quality_tier: mid
      reasoning_strength: mid
      context_strength: mid
      tool_strength: medium
      same_model_group: deepseek/chat
  cheap-workhorse:
    backend: openai-compat
    base_url: "https://cheap.example.com/v1"
    api_key: "secret"
    model: "deepseek-chat"
    tier: default
    pricing:
      input: 0.08
      output: 0.32
      cache_read: 0.02
    lane:
      family: deepseek
      name: workhorse
      canonical_model: deepseek/chat
      route_type: direct
      cluster: balanced-workhorse
      benchmark_cluster: balanced-coding
      quality_tier: mid
      reasoning_strength: mid
      context_strength: mid
      tool_strength: medium
      same_model_group: deepseek/chat
client_profiles:
  enabled: true
  default: generic
  profiles:
    generic:
      routing_mode: eco
      prefer_tiers: ["default"]
routing_modes:
  enabled: true
  default: eco
  modes:
    eco:
      select:
        prefer_tiers: ["default"]
heuristic_rules:
  enabled: false
  rules: []
fallback_chain: []
metrics:
  enabled: false
""",
        )
    )
    router = Router(cfg)

    decision = await router.route(
        [{"role": "user", "content": "Summarize this coding diff briefly and pragmatically."}],
        model_requested="auto",
        client_profile="generic",
        profile_hints=cfg.client_profiles["profiles"]["generic"],
        provider_health={
            "standard-workhorse": {
                "healthy": True,
                "avg_latency_ms": 120,
                "consecutive_failures": 0,
            },
            "cheap-workhorse": {
                "healthy": True,
                "avg_latency_ms": 120,
                "consecutive_failures": 0,
            },
        },
    )

    assert decision.provider_name == "cheap-workhorse"
    ranking = decision.details["candidate_ranking"]
    assert ranking[0]["provider"] == "cheap-workhorse"
    assert ranking[0]["cost_score"] > ranking[1]["cost_score"]
    assert ranking[0]["estimated_request_cost_usd"] < ranking[1]["estimated_request_cost_usd"]


@pytest.mark.asyncio
async def test_quality_posture_prefers_fresh_benchmark_assumptions(tmp_path):
    fresh_date = date.today().isoformat()
    stale_date = (date.today() - timedelta(days=45)).isoformat()
    cfg = load_config(
        _write_config(
            tmp_path,
            f"""
server:
  host: "127.0.0.1"
  port: 8090
providers:
  fresh-quality:
    backend: openai-compat
    base_url: "https://fresh.example.com/v1"
    api_key: "secret"
    model: "quality-a"
    tier: mid
    capabilities:
      cost_tier: premium
    lane:
      family: custom
      name: quality
      canonical_model: custom/quality-a
      route_type: direct
      cluster: quality-workhorse
      benchmark_cluster: quality-coding
      quality_tier: high
      reasoning_strength: high
      context_strength: high
      tool_strength: high
      same_model_group: custom/quality-a
      last_reviewed: "{fresh_date}"
      review_age_days: 0
      freshness_status: fresh
      freshness_hint: benchmark and cost assumptions were reviewed recently
  stale-quality:
    backend: openai-compat
    base_url: "https://stale.example.com/v1"
    api_key: "secret"
    model: "quality-b"
    tier: mid
    capabilities:
      cost_tier: premium
    lane:
      family: custom
      name: quality
      canonical_model: custom/quality-b
      route_type: direct
      cluster: quality-workhorse
      benchmark_cluster: quality-coding
      quality_tier: high
      reasoning_strength: high
      context_strength: high
      tool_strength: high
      same_model_group: custom/quality-b
      last_reviewed: "{stale_date}"
      review_age_days: 45
      freshness_status: stale
      freshness_hint: benchmark and cost assumptions are stale; review before trusting them heavily
client_profiles:
  enabled: true
  default: generic
  profiles:
    generic:
      routing_mode: premium
      prefer_tiers: ["mid"]
routing_modes:
  enabled: true
  default: premium
  modes:
    premium:
      select:
        prefer_tiers: ["mid"]
heuristic_rules:
  enabled: false
  rules: []
fallback_chain: []
metrics:
  enabled: false
""",
        )
    )
    router = Router(cfg)

    decision = await router.route(
        [{"role": "user", "content": "Review this architecture plan carefully."}],
        model_requested="auto",
        client_profile="generic",
        profile_hints=cfg.client_profiles["profiles"]["generic"],
        provider_health={
            "fresh-quality": {"healthy": True, "avg_latency_ms": 110, "consecutive_failures": 0},
            "stale-quality": {"healthy": True, "avg_latency_ms": 110, "consecutive_failures": 0},
        },
    )

    assert decision.provider_name == "fresh-quality"
    ranking = decision.details["candidate_ranking"]
    assert ranking[0]["provider"] == "fresh-quality"
    assert ranking[0]["freshness_score"] > ranking[1]["freshness_score"]
    assert ranking[0]["freshness_status"] == "fresh"
    assert ranking[1]["freshness_status"] == "stale"


@pytest.mark.asyncio
async def test_runtime_route_pressure_penalty_demotes_hot_provider(tmp_path):
    cfg = load_config(
        _write_config(
            tmp_path,
            """
server:
  host: "127.0.0.1"
  port: 8090
providers:
  direct-workhorse:
    backend: openai-compat
    base_url: "https://direct.example.com/v1"
    api_key: "secret"
    model: "workhorse"
    tier: default
    lane:
      family: custom
      name: balanced
      canonical_model: custom/workhorse
      route_type: direct
      cluster: balanced-workhorse
      benchmark_cluster: balanced-coding
      quality_tier: mid
      reasoning_strength: mid
      same_model_group: custom/workhorse
  stable-alt:
    backend: openai-compat
    base_url: "https://alt.example.com/v1"
    api_key: "secret"
    model: "workhorse-alt"
    tier: default
    lane:
      family: custom
      name: balanced
      canonical_model: custom/workhorse-alt
      route_type: direct
      cluster: balanced-workhorse
      benchmark_cluster: balanced-coding
      quality_tier: mid
      reasoning_strength: mid
      same_model_group: custom/workhorse-alt
client_profiles:
  enabled: true
  default: generic
  profiles:
    generic:
      prefer_tiers: ["default"]
fallback_chain:
  - stable-alt
metrics:
  enabled: false
""",
        )
    )
    router = Router(cfg)

    decision = await router.route(
        [{"role": "user", "content": "Pick the steadier route."}],
        model_requested="auto",
        client_profile="generic",
        profile_hints=cfg.client_profiles["profiles"]["generic"],
        provider_health={
            "direct-workhorse": {"healthy": True, "avg_latency_ms": 90, "consecutive_failures": 0},
            "stable-alt": {"healthy": True, "avg_latency_ms": 160, "consecutive_failures": 0},
        },
        provider_runtime_state={
            "direct-workhorse": {
                "penalty": 28,
                "last_issue_type": "rate-limited",
                "last_issue_detail": "429 too many requests",
            },
            "stable-alt": {"penalty": 0},
        },
    )

    assert decision.provider_name == "stable-alt"
    ranking = decision.details["candidate_ranking"]
    assert ranking[0]["provider"] == "stable-alt"
    assert ranking[1]["provider"] == "direct-workhorse"
    assert ranking[1]["adaptation_penalty"] == 28


@pytest.mark.asyncio
async def test_simple_query_keyword_matching_does_not_trigger_on_substrings(tmp_path):
    cfg = load_config(
        _write_config(
            tmp_path,
            """
server:
  host: "127.0.0.1"
  port: 8090
providers:
  deepseek-reasoner:
    backend: openai-compat
    base_url: "https://reasoner.example.com/v1"
    api_key: "secret"
    model: "reasoner"
    tier: reasoning
  gemini-flash-lite:
    backend: google-genai
    base_url: "https://google.example.com/v1beta"
    api_key: "secret"
    model: "gemini-2.5-flash-lite"
    tier: cheap
static_rules:
  enabled: false
  rules: []
heuristic_rules:
  enabled: true
  rules:
    - name: simple-query
      match:
        message_keywords:
          any_of: ["hi"]
          min_matches: 1
      route_to: gemini-flash-lite
fallback_chain:
  - deepseek-reasoner
metrics:
  enabled: false
""",
        )
    )
    router = Router(cfg)

    decision = await router.route(
        [{"role": "user", "content": "Should this architecture hold under load?"}],
        model_requested="auto",
        client_profile="generic",
        profile_hints={},
        provider_health={
            "deepseek-reasoner": {"healthy": True},
            "gemini-flash-lite": {"healthy": True},
        },
    )

    assert decision.provider_name == "deepseek-reasoner"


@pytest.mark.asyncio
async def test_opencode_medium_complexity_suppresses_simple_query_and_promotes_complex_rule(
    tmp_path,
):
    cfg = load_config(
        _write_config(
            tmp_path,
            """
server:
  host: "127.0.0.1"
  port: 8090
providers:
  deepseek-reasoner:
    backend: openai-compat
    base_url: "https://reasoner.example.com/v1"
    api_key: "secret"
    model: "reasoner"
    tier: reasoning
  gemini-flash-lite:
    backend: google-genai
    base_url: "https://google.example.com/v1beta"
    api_key: "secret"
    model: "gemini-2.5-flash-lite"
    tier: cheap
heuristic_rules:
  enabled: true
  rules:
    - name: complex-code
      match:
        message_keywords:
          any_of: ["architecture", "rollback", "refactor"]
          min_matches: 4
      route_to: deepseek-reasoner
    - name: simple-query
      match:
        message_keywords:
          any_of: ["hello", "hi"]
          min_matches: 1
      route_to: gemini-flash-lite
fallback_chain:
  - deepseek-reasoner
metrics:
  enabled: false
""",
        )
    )
    router = Router(cfg)
    messages = [
        {
            "role": "user",
            "content": "hi, need a rollback-safe architecture plan for this refactor",
        }
    ]

    generic_decision = await router.route(
        messages,
        model_requested="auto",
        client_profile="generic",
        profile_hints={},
        provider_health={
            "deepseek-reasoner": {"healthy": True},
            "gemini-flash-lite": {"healthy": True},
        },
    )
    opencode_decision = await router.route(
        messages,
        model_requested="auto",
        client_profile="opencode",
        profile_hints={"routing_mode": "auto"},
        provider_health={
            "deepseek-reasoner": {"healthy": True},
            "gemini-flash-lite": {"healthy": True},
        },
    )

    assert generic_decision.provider_name == "gemini-flash-lite"
    assert opencode_decision.provider_name == "deepseek-reasoner"
    assert opencode_decision.details["request_insights"]["complexity_profile"] in {
        "medium",
        "high",
    }
    assert opencode_decision.details["heuristic_match"]["opencode_bias_applied"] is True


@pytest.mark.asyncio
async def test_opencode_complexity_bias_promotes_single_strong_architecture_hit(tmp_path):
    cfg = load_config(
        _write_config(
            tmp_path,
            """
server:
  host: "127.0.0.1"
  port: 8090
providers:
  deepseek-reasoner:
    backend: openai-compat
    base_url: "https://reasoner.example.com/v1"
    api_key: "secret"
    model: "reasoner"
    tier: reasoning
  gemini-flash-lite:
    backend: google-genai
    base_url: "https://google.example.com/v1beta"
    api_key: "secret"
    model: "gemini-2.5-flash-lite"
    tier: cheap
heuristic_rules:
  enabled: true
  rules:
    - name: complex-code
      match:
        message_keywords:
          any_of: ["architecture", "debug", "refactor"]
          min_matches: 2
      route_to: deepseek-reasoner
    - name: simple-query
      match:
        message_keywords:
          any_of: ["hello", "hi"]
          min_matches: 1
      route_to: gemini-flash-lite
fallback_chain:
  - deepseek-reasoner
metrics:
  enabled: false
""",
        )
    )
    router = Router(cfg)

    decision = await router.route(
        [
            {
                "role": "user",
                "content": "Need an architecture plan for rollback-safe event processing.",
            }
        ],
        model_requested="auto",
        client_profile="opencode",
        profile_hints={"routing_mode": "auto"},
        provider_health={
            "deepseek-reasoner": {"healthy": True},
            "gemini-flash-lite": {"healthy": True},
        },
    )

    assert decision.provider_name == "deepseek-reasoner"
