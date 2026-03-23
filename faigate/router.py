"""Layered routing engine for policy, heuristics, hooks, profiles, and LLM fallback."""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any

from .config import Config
from .lane_registry import get_canonical_model_routes

logger = logging.getLogger("faigate.router")
_BOUNDARY_TEXT_RE = re.compile(r"[a-z0-9]")
_OPENCODE_COMPLEXITY_HINTS = (
    "architecture",
    "tradeoff",
    "trade-off",
    "rollback",
    "idempot",
    "backpressure",
    "migration",
    "failure mode",
    "failure modes",
    "concurrency",
    "refactor",
    "debug",
    "code review",
    "performance bottleneck",
    "race condition",
    "deadlock",
)
_OPENCODE_COMPLEXITY_RULE_KEYWORDS = {
    "refactor",
    "debug",
    "architecture",
    "design pattern",
    "race condition",
    "memory leak",
    "optimize",
    "complexity",
    "security vulnerability",
    "code review",
    "performance bottleneck",
    "type error",
    "deadlock",
    "tradeoff",
    "trade-off",
    "migration",
    "rollback",
    "idempotency",
    "backpressure",
    "failure mode",
    "reliability",
}
_OPENCODE_SIGNAL_GROUPS = {
    "architecture": ("architecture", "tradeoff", "trade-off", "design pattern"),
    "change-risk": (
        "migration",
        "rollback",
        "idempot",
        "failure mode",
        "failure modes",
        "reliability",
    ),
    "concurrency": ("concurrency", "race condition", "deadlock", "backpressure"),
    "debugging": ("debug", "memory leak", "type error", "performance bottleneck"),
    "quality": ("refactor", "code review", "optimize", "security vulnerability"),
}


_QUALITY_TIER_SCORES = {
    "premium": 10,
    "high": 8,
    "mid": 5,
    "budget": 2,
    "free": 1,
    "variable": 4,
    "n/a": 0,
}

_STRENGTH_SCORES = {
    "high": 9,
    "mid": 6,
    "low": 2,
    "variable": 4,
    "n/a": 0,
}

_CLUSTER_POSTURE_SCORES = {
    "quality": {
        "elite-reasoning": 10,
        "quality-workhorse": 8,
        "balanced-workhorse": 5,
        "fast-workhorse": 3,
        "budget-general": 1,
        "aggregator-fallback": 2,
        "image-quality": 8,
    },
    "balanced": {
        "elite-reasoning": 7,
        "quality-workhorse": 8,
        "balanced-workhorse": 9,
        "fast-workhorse": 7,
        "budget-general": 4,
        "aggregator-fallback": 4,
        "image-quality": 5,
    },
    "eco": {
        "elite-reasoning": 2,
        "quality-workhorse": 4,
        "balanced-workhorse": 6,
        "fast-workhorse": 8,
        "budget-general": 10,
        "aggregator-fallback": 6,
        "image-quality": 2,
    },
    "free": {
        "elite-reasoning": 1,
        "quality-workhorse": 2,
        "balanced-workhorse": 3,
        "fast-workhorse": 5,
        "budget-general": 10,
        "aggregator-fallback": 8,
        "image-quality": 1,
    },
}

_ROUTE_POSTURE_SCORES = {
    "quality": {
        "direct": 4,
        "aggregator": 1,
        "wallet-router": 1,
        "local": 3,
    },
    "balanced": {
        "direct": 3,
        "aggregator": 2,
        "wallet-router": 2,
        "local": 3,
    },
    "eco": {
        "direct": 2,
        "aggregator": 4,
        "wallet-router": 4,
        "local": 3,
    },
    "free": {
        "direct": 1,
        "aggregator": 5,
        "wallet-router": 5,
        "local": 2,
    },
}

_BENCHMARK_POSTURE_SCORES = {
    "quality": {
        "quality-coding": 8,
        "reasoning-coding": 9,
        "balanced-coding": 5,
        "fast-general": 2,
        "budget-chat": 1,
        "free-coding": 2,
        "marketplace-general": 3,
        "image-generation": 8,
    },
    "balanced": {
        "quality-coding": 6,
        "reasoning-coding": 7,
        "balanced-coding": 8,
        "fast-general": 6,
        "budget-chat": 4,
        "free-coding": 5,
        "marketplace-general": 5,
        "image-generation": 5,
    },
    "eco": {
        "quality-coding": 2,
        "reasoning-coding": 3,
        "balanced-coding": 6,
        "fast-general": 8,
        "budget-chat": 9,
        "free-coding": 10,
        "marketplace-general": 6,
        "image-generation": 2,
    },
    "free": {
        "quality-coding": 1,
        "reasoning-coding": 2,
        "balanced-coding": 4,
        "fast-general": 6,
        "budget-chat": 9,
        "free-coding": 10,
        "marketplace-general": 7,
        "image-generation": 1,
    },
}

_BENCHMARK_SIGNAL_WEIGHTS = {
    "architecture": {
        "reasoning-coding": 4,
        "quality-coding": 4,
        "balanced-coding": 2,
    },
    "change-risk": {
        "reasoning-coding": 4,
        "quality-coding": 3,
        "balanced-coding": 2,
    },
    "concurrency": {
        "reasoning-coding": 4,
        "quality-coding": 3,
        "balanced-coding": 2,
    },
    "debugging": {
        "reasoning-coding": 4,
        "quality-coding": 3,
        "balanced-coding": 2,
        "fast-general": 1,
    },
    "quality": {
        "quality-coding": 4,
        "reasoning-coding": 3,
        "balanced-coding": 2,
    },
}

_COST_TIER_POSTURE_SCORES = {
    "quality": {
        "premium": 3,
        "standard": 2,
        "cheap": 1,
        "marketplace": 1,
        "budget": 0,
        "free": -1,
        "variable": 0,
    },
    "balanced": {
        "premium": 1,
        "standard": 4,
        "cheap": 5,
        "marketplace": 3,
        "budget": 4,
        "free": 4,
        "variable": 2,
    },
    "eco": {
        "premium": -2,
        "standard": 3,
        "cheap": 7,
        "marketplace": 5,
        "budget": 6,
        "free": 8,
        "variable": 3,
    },
    "free": {
        "premium": -4,
        "standard": 1,
        "cheap": 5,
        "marketplace": 6,
        "budget": 7,
        "free": 10,
        "variable": 4,
    },
}

_ESTIMATED_COST_POSTURE_BANDS = {
    "quality": [
        (0.0008, 3),
        (0.0025, 2),
        (0.0080, 0),
        (0.0200, -1),
    ],
    "balanced": [
        (0.0006, 6),
        (0.0015, 5),
        (0.0040, 3),
        (0.0100, 0),
    ],
    "eco": [
        (0.0004, 10),
        (0.0010, 8),
        (0.0030, 5),
        (0.0080, 1),
    ],
    "free": [
        (0.0002, 12),
        (0.0007, 9),
        (0.0020, 5),
        (0.0060, 0),
    ],
}

_FALLBACK_RELATION_WEIGHTS = {
    "quality": {
        "same_model_route": 40,
        "same_cluster": 16,
        "preferred_degrade": 12,
    },
    "balanced": {
        "same_model_route": 28,
        "same_cluster": 14,
        "preferred_degrade": 10,
    },
    "eco": {
        "same_model_route": 14,
        "same_cluster": 10,
        "preferred_degrade": 8,
    },
    "free": {
        "same_model_route": 10,
        "same_cluster": 8,
        "preferred_degrade": 6,
    },
}


@dataclass
class RoutingDecision:
    """Result of the routing process."""

    provider_name: str
    layer: str  # "policy", "profile", "static", "heuristic", "llm-classify", "fallback"
    rule_name: str  # Which rule matched
    confidence: float  # 0.0–1.0
    reason: str  # Human-readable explanation
    elapsed_ms: float = 0.0
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        payload = {
            "provider": self.provider_name,
            "layer": self.layer,
            "rule": self.rule_name,
            "confidence": self.confidence,
            "reason": self.reason,
            "elapsed_ms": round(self.elapsed_ms, 2),
        }
        if self.details:
            payload["details"] = self.details
        return payload


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token for mixed en/de text."""
    return max(1, len(text) // 4)


def _score_capacity_ratio(ratio: float, *, strong: float = 2.0, ideal: float = 4.0) -> int:
    """Return a bounded score for how comfortably a provider fits one request dimension."""
    if ratio <= 0:
        return 0
    if ratio < 1.0:
        return 0
    if ratio < strong:
        return 4
    if ratio < ideal:
        return 7
    if ratio < ideal * 2:
        return 9
    return 10


def _score_image_fit_ratio(ratio: float) -> int:
    """Return a score for image limits that prefers a close fit over excess headroom."""
    if ratio <= 0 or ratio > 1:
        return 0
    if ratio >= 0.9:
        return 10
    if ratio >= 0.7:
        return 8
    if ratio >= 0.5:
        return 6
    if ratio >= 0.25:
        return 4
    return 2


def _collect_keyword_hits(text: str, keywords: tuple[str, ...] | set[str] | list[str]) -> list[str]:
    """Return de-duplicated keywords that match one text using boundary-aware checks."""
    hits: list[str] = []
    seen: set[str] = set()
    for keyword in keywords:
        normalized = str(keyword).strip().lower()
        if not normalized or normalized in seen:
            continue
        if _keyword_matches_text(normalized, text):
            seen.add(normalized)
            hits.append(normalized)
    return hits


def _request_length_bucket(total_tokens: int) -> str:
    if total_tokens >= 220:
        return "long"
    if total_tokens >= 80:
        return "normal"
    return "brief"


def _estimated_request_cost_usd(provider: dict[str, Any], ctx: _RoutingContext | None) -> float:
    """Estimate one rough request cost from provider pricing and current request shape."""
    if ctx is None:
        return 0.0
    pricing = dict(provider.get("pricing") or {})
    if not pricing:
        return 0.0
    prompt_rate = float(pricing.get("input", 0) or 0)
    output_rate = float(pricing.get("output", 0) or 0)
    cache_rate = float(pricing.get("cache_read", prompt_rate) or 0)
    prompt_tokens = max(1, int(ctx.total_tokens or 0))
    output_tokens = int(ctx.requested_output_tokens or 0)
    if output_tokens <= 0:
        output_tokens = min(1024, max(128, prompt_tokens // 2))

    cache_mode = str((provider.get("cache") or {}).get("mode") or "none")
    if ctx.stable_prefix_tokens >= 64 and cache_mode != "none":
        cached_tokens = min(prompt_tokens, int(ctx.stable_prefix_tokens))
        prompt_cost = (
            (cached_tokens * cache_rate) + ((prompt_tokens - cached_tokens) * prompt_rate)
        ) / 1_000_000
    else:
        prompt_cost = (prompt_tokens * prompt_rate) / 1_000_000

    output_cost = (output_tokens * output_rate) / 1_000_000
    return round(prompt_cost + output_cost, 6)


def _build_request_insights(
    *,
    last_user_message: str,
    client_profile: str,
    has_tools: bool,
    total_tokens: int,
    requested_output_tokens: int,
) -> dict[str, Any]:
    """Summarize request complexity signals for routing and operator surfaces."""
    search_text = (last_user_message or "").lower()
    opencode_hits = _collect_keyword_hits(search_text, _OPENCODE_COMPLEXITY_HINTS)
    signal_groups = [
        group
        for group, keywords in _OPENCODE_SIGNAL_GROUPS.items()
        if _collect_keyword_hits(search_text, keywords)
    ]

    score = 0
    score += min(4, len(opencode_hits))
    score += len(signal_groups)
    if has_tools:
        score += 2
    if total_tokens >= 80:
        score += 1
    if total_tokens >= 180:
        score += 1
    if requested_output_tokens >= 1200:
        score += 1
    if client_profile == "opencode" and opencode_hits:
        score += 1

    if score >= 6:
        complexity_profile = "high"
    elif score >= 3:
        complexity_profile = "medium"
    else:
        complexity_profile = "low"

    return {
        "complexity_profile": complexity_profile,
        "complexity_score": score,
        "signal_groups": signal_groups,
        "matched_signals": opencode_hits,
        "length_bucket": _request_length_bucket(total_tokens),
        "tool_context": bool(has_tools),
        "opencode_bias_eligible": client_profile == "opencode"
        and complexity_profile
        in {
            "medium",
            "high",
        },
    }


def _benchmark_request_score(lane: dict[str, Any], ctx: _RoutingContext | None) -> int:
    """Score one lane against the current request shape, not just the posture."""
    if ctx is None or not lane:
        return 0

    benchmark_cluster = str(lane.get("benchmark_cluster") or "")
    if not benchmark_cluster:
        return 0

    request_insights = dict(getattr(ctx, "request_insights", {}) or {})
    signal_groups = [str(item) for item in (request_insights.get("signal_groups") or []) if item]
    complexity_profile = str(request_insights.get("complexity_profile") or "")
    length_bucket = str(request_insights.get("length_bucket") or "")
    tool_context = bool(request_insights.get("tool_context"))

    score = 0
    for group in signal_groups:
        score += _BENCHMARK_SIGNAL_WEIGHTS.get(group, {}).get(benchmark_cluster, 0)

    if complexity_profile == "high":
        if benchmark_cluster in {"reasoning-coding", "quality-coding"}:
            score += 3
        elif benchmark_cluster == "balanced-coding":
            score += 1
        elif benchmark_cluster in {"budget-chat", "free-coding"}:
            score -= 1
    elif complexity_profile == "medium":
        if benchmark_cluster in {"reasoning-coding", "quality-coding", "balanced-coding"}:
            score += 2
        elif benchmark_cluster in {"budget-chat", "free-coding"}:
            score -= 1
    elif complexity_profile == "low":
        if benchmark_cluster in {"budget-chat", "free-coding", "fast-general"}:
            score += 1

    if tool_context:
        tool_strength = str(lane.get("tool_strength") or "").lower()
        if tool_strength == "high":
            score += 2
        elif tool_strength == "mid":
            score += 1

    if length_bucket == "long":
        context_strength = str(lane.get("context_strength") or "").lower()
        if context_strength == "high":
            score += 2
        elif context_strength == "mid":
            score += 1

    return score


def _cost_posture_score(
    *,
    estimated_cost_usd: float,
    routing_posture: str,
    cost_tier: str,
) -> int:
    """Convert rough cost fit into one posture-aware score."""
    normalized_tier = str(cost_tier or "").lower()
    tier_score = _COST_TIER_POSTURE_SCORES.get(
        routing_posture,
        _COST_TIER_POSTURE_SCORES["balanced"],
    ).get(normalized_tier, 0)

    if estimated_cost_usd <= 0:
        return tier_score

    bands = _ESTIMATED_COST_POSTURE_BANDS.get(
        routing_posture,
        _ESTIMATED_COST_POSTURE_BANDS["balanced"],
    )
    for threshold, score in bands:
        if estimated_cost_usd <= threshold:
            return score + max(0, tier_score // 2)
    return -4 if routing_posture in {"eco", "free"} else -2


def _merge_select_constraints(*selects: dict[str, Any]) -> dict[str, Any]:
    """Merge policy-like select mappings without dropping list/dict constraints."""
    merged: dict[str, Any] = {
        "allow_providers": [],
        "deny_providers": [],
        "prefer_providers": [],
        "prefer_tiers": [],
        "require_capabilities": [],
        "capability_values": {},
    }

    for select in selects:
        if not select:
            continue

        for key in (
            "allow_providers",
            "deny_providers",
            "prefer_providers",
            "prefer_tiers",
            "require_capabilities",
        ):
            values = select.get(key, [])
            if isinstance(values, str):
                values = [values]
            elif not isinstance(values, list):
                continue
            for value in values:
                if value not in merged[key]:
                    merged[key].append(value)

        raw_capability_values = select.get("capability_values", {})
        if not isinstance(raw_capability_values, dict):
            continue
        for capability, values in raw_capability_values.items():
            normalized_values = values if isinstance(values, list) else [values]
            merged["capability_values"].setdefault(capability, [])
            for value in normalized_values:
                if value not in merged["capability_values"][capability]:
                    merged["capability_values"][capability].append(value)

    return merged


def _extract_text(messages: list[dict]) -> tuple[str, str, str]:
    """Extract system prompt, last user message, and full conversation text.

    Handles content=None (valid in OpenAI tool/assistant messages) by treating
    it as an empty string so downstream str operations never receive NoneType.
    """
    system = ""
    last_user = ""
    full = []
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content") or ""  # coerce None → ""
        if isinstance(content, list):
            # Handle multimodal content arrays; parts may also have None text
            content = " ".join(p.get("text") or "" for p in content if isinstance(p, dict))
        if role == "system":
            system = content
        elif role == "user":
            last_user = content
        full.append(content)
    return system, last_user, "\n".join(full)


def _parse_image_size_max_side(value: str) -> int:
    """Return the larger dimension from a WxH image size string."""
    parts = value.lower().split("x", 1)
    if len(parts) != 2:
        return 0
    try:
        width = int(parts[0])
        height = int(parts[1])
    except ValueError:
        return 0
    return max(width, height)


def _normalize_routing_posture(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"premium", "quality"}:
        return "quality"
    if normalized in {"eco", "cheap", "save"}:
        return "eco"
    if normalized in {"free"}:
        return "free"
    return "balanced"


def _keyword_matches_text(keyword: str, search_text: str) -> bool:
    normalized = str(keyword or "").strip().lower()
    if not normalized:
        return False
    if not _BOUNDARY_TEXT_RE.search(normalized):
        return normalized in search_text

    pattern = re.escape(normalized)
    if _BOUNDARY_TEXT_RE.match(normalized[0]):
        pattern = rf"(?<![a-z0-9]){pattern}"
    if _BOUNDARY_TEXT_RE.match(normalized[-1]):
        pattern = rf"{pattern}(?![a-z0-9])"
    return re.search(pattern, search_text) is not None


class Router:
    """Layered routing engine."""

    def __init__(self, config: Config):
        self.config = config

    # ── Public entry point ─────────────────────────────────────

    async def route(
        self,
        messages: list[dict],
        *,
        model_requested: str = "",
        has_tools: bool = False,
        requested_max_tokens: int | None = None,
        client_profile: str = "generic",
        profile_hints: dict[str, Any] | None = None,
        hook_hints: dict[str, Any] | None = None,
        applied_hooks: list[str] | None = None,
        headers: dict[str, str] | None = None,
        provider_health: dict[str, Any] | None = None,
        provider_runtime_state: dict[str, Any] | None = None,
    ) -> RoutingDecision:
        """
        Run through all enabled routing layers in order.
        Returns as soon as a layer makes a decision.
        """
        t0 = time.time()
        system, last_user, full_text = _extract_text(messages)
        total_tokens = _estimate_tokens(full_text)
        stable_prefix_tokens = _estimate_tokens(system) if system else 0
        requested_output_tokens = requested_max_tokens or 0
        total_requested_tokens = total_tokens + requested_output_tokens

        ctx = _RoutingContext(
            system_prompt=system,
            last_user_message=last_user,
            full_text=full_text,
            total_tokens=total_tokens,
            stable_prefix_tokens=stable_prefix_tokens,
            requested_output_tokens=requested_output_tokens,
            total_requested_tokens=total_requested_tokens,
            requested_image_outputs=1,
            requested_image_side_px=0,
            requested_image_size="",
            requested_image_policy="",
            required_capability="",
            cache_preference=(headers or {}).get("x-faigate-cache", "").strip().lower(),
            model_requested=model_requested.lower().strip(),
            has_tools=has_tools,
            client_profile=client_profile,
            profile_hints=profile_hints or {},
            hook_hints=hook_hints or {},
            applied_hooks=applied_hooks or [],
            headers=headers or {},
            provider_health=provider_health or {},
            provider_runtime_state=provider_runtime_state or {},
            providers=self.config.providers,
            request_insights=_build_request_insights(
                last_user_message=last_user,
                client_profile=client_profile,
                has_tools=has_tools,
                total_tokens=total_tokens,
                requested_output_tokens=requested_output_tokens,
            ),
        )

        # Layer 0: Policy rules
        decision = self._layer_policy(ctx)
        if decision:
            decision.elapsed_ms = (time.time() - t0) * 1000
            return self._validate_health(decision, ctx)

        # Layer 1: Static rules
        decision = self._layer_static(ctx)
        if decision:
            decision.elapsed_ms = (time.time() - t0) * 1000
            return self._validate_health(decision, ctx)

        # Layer 2: Heuristic rules
        decision = self._layer_heuristic(ctx)
        if decision:
            decision.elapsed_ms = (time.time() - t0) * 1000
            return self._validate_health(decision, ctx)

        # Layer 3: Request hook hints
        decision = self._layer_hook(ctx)
        if decision:
            decision.elapsed_ms = (time.time() - t0) * 1000
            return self._validate_health(decision, ctx)

        # Layer 4: Client profile hints
        decision = self._layer_profile(ctx)
        if decision:
            decision.elapsed_ms = (time.time() - t0) * 1000
            return self._validate_health(decision, ctx)

        # Layer 5: LLM classifier (if enabled)
        if self.config.llm_classifier.get("enabled"):
            decision = await self._layer_llm_classify(ctx)
            if decision:
                decision.elapsed_ms = (time.time() - t0) * 1000
                return self._validate_health(decision, ctx)

        # Fallback: first healthy provider in the chain
        elapsed = (time.time() - t0) * 1000
        fallback = self.config.fallback_chain[0] if self.config.fallback_chain else "deepseek-chat"
        return self._enrich_decision_details(
            RoutingDecision(
                provider_name=fallback,
                layer="fallback",
                rule_name="no-match",
                confidence=0.3,
                reason="No routing layer matched, using first fallback",
                elapsed_ms=elapsed,
            ),
            ctx,
        )

    def route_capability_request(
        self,
        *,
        capability: str,
        request_text: str = "",
        requested_outputs: int | None = None,
        requested_size: str = "",
        model_requested: str = "",
        client_profile: str = "generic",
        profile_hints: dict[str, Any] | None = None,
        hook_hints: dict[str, Any] | None = None,
        applied_hooks: list[str] | None = None,
        headers: dict[str, str] | None = None,
        provider_health: dict[str, Any] | None = None,
        provider_runtime_state: dict[str, Any] | None = None,
        candidate_names: list[str] | None = None,
    ) -> RoutingDecision | None:
        """Route one non-chat request against providers with a required capability."""
        t0 = time.time()
        total_tokens = _estimate_tokens(request_text) if request_text else 0
        ctx = _RoutingContext(
            system_prompt="",
            last_user_message=request_text,
            full_text=request_text,
            total_tokens=total_tokens,
            stable_prefix_tokens=0,
            requested_output_tokens=0,
            total_requested_tokens=total_tokens,
            requested_image_outputs=requested_outputs or 1,
            requested_image_side_px=_parse_image_size_max_side(requested_size),
            requested_image_size=requested_size.strip().lower() if requested_size else "",
            requested_image_policy=(
                (headers or {}).get("x-faigate-image-policy", "").strip().lower()
            ),
            required_capability=capability,
            cache_preference=(headers or {}).get("x-faigate-cache", "").strip().lower(),
            model_requested=model_requested.lower().strip(),
            has_tools=False,
            client_profile=client_profile,
            profile_hints=profile_hints or {},
            hook_hints=hook_hints or {},
            applied_hooks=applied_hooks or [],
            headers=headers or {},
            provider_health=provider_health or {},
            provider_runtime_state=provider_runtime_state or {},
            providers=self.config.providers,
            request_insights=_build_request_insights(
                last_user_message=request_text,
                client_profile=client_profile,
                has_tools=False,
                total_tokens=total_tokens,
                requested_output_tokens=0,
            ),
        )

        base_select = _merge_select_constraints(
            {
                "require_capabilities": [capability],
                "allow_providers": candidate_names or [],
            }
        )

        policy_decision = self._layer_capability_policy(ctx, capability, base_select)
        if policy_decision:
            policy_decision.elapsed_ms = (time.time() - t0) * 1000
            return self._validate_health(
                policy_decision,
                ctx,
                required_capabilities=[capability],
            )

        for layer_name, selector, confidence, reason in (
            ("hook", ctx.hook_hints, 0.7, "Request hooks selected a preferred provider"),
            (
                "profile",
                ctx.profile_hints,
                0.6,
                f"Client profile '{ctx.client_profile}' selected a preferred provider",
            ),
            (
                "capability-default",
                {},
                0.5,
                f"Selected the best available provider with capability '{capability}'",
            ),
        ):
            provider_name, ranking = self._select_policy_provider(
                _merge_select_constraints(base_select, selector),
                ctx,
            )
            if not provider_name:
                continue
            decision = RoutingDecision(
                provider_name=provider_name,
                layer=layer_name,
                rule_name=f"{capability}-{layer_name}",
                confidence=confidence,
                reason=reason,
                details={
                    "required_capability": capability,
                    "candidate_ranking": ranking,
                },
            )
            decision.elapsed_ms = (time.time() - t0) * 1000
            return self._validate_health(decision, ctx, required_capabilities=[capability])

        return None

    # ── Layer 0: Policy Rules ──────────────────────────────────

    def _layer_policy(self, ctx: _RoutingContext) -> RoutingDecision | None:
        cfg = self.config.routing_policies
        if not cfg.get("enabled"):
            return None

        for rule in cfg.get("rules", []):
            match = rule.get("match", {})
            if not self._match_policy(match, ctx):
                continue

            provider_name, ranking = self._select_policy_provider(rule.get("select", {}), ctx)
            if not provider_name:
                logger.debug("Policy rule matched but no provider was eligible: %s", rule["name"])
                continue

            logger.debug("Policy rule matched: %s → %s", rule["name"], provider_name)
            return RoutingDecision(
                provider_name=provider_name,
                layer="policy",
                rule_name=rule["name"],
                confidence=0.95,
                reason=f"Policy rule '{rule['name']}' matched",
                details={"candidate_ranking": ranking},
            )

        return None

    def _layer_capability_policy(
        self,
        ctx: _RoutingContext,
        capability: str,
        base_select: dict[str, Any],
    ) -> RoutingDecision | None:
        """Apply routing policies while enforcing one required capability."""
        cfg = self.config.routing_policies
        if not cfg.get("enabled"):
            return None

        for rule in cfg.get("rules", []):
            if not self._match_policy(rule.get("match", {}), ctx):
                continue

            provider_name, ranking = self._select_policy_provider(
                _merge_select_constraints(base_select, rule.get("select", {})),
                ctx,
            )
            if not provider_name:
                continue

            return RoutingDecision(
                provider_name=provider_name,
                layer="policy",
                rule_name=rule["name"],
                confidence=0.95,
                reason=(
                    f"Policy rule '{rule['name']}' matched for required capability '{capability}'"
                ),
                details={
                    "required_capability": capability,
                    "candidate_ranking": ranking,
                },
            )

        return None

    def _match_policy(self, match: dict, ctx: _RoutingContext) -> bool:
        """Evaluate a policy match block using the existing static/heuristic primitives."""
        if not match:
            return True

        if "all" in match:
            return all(self._match_policy(sub, ctx) for sub in match["all"])
        if "any" in match:
            return any(self._match_policy(sub, ctx) for sub in match["any"])

        matched_any = False

        if "client_profile" in match:
            matched_any = True
            profiles = match["client_profile"]
            if isinstance(profiles, str):
                profiles = [profiles]
            if ctx.client_profile not in profiles:
                return False

        static_keys = {"model_requested", "system_prompt_contains", "header_contains", "any"}
        heuristic_keys = {"has_tools", "estimated_tokens", "message_keywords", "fallthrough"}

        static_match = {k: match[k] for k in static_keys if k in match}
        heuristic_match = {k: match[k] for k in heuristic_keys if k in match}

        if static_match:
            matched_any = True
            if not self._match_static(static_match, ctx):
                return False
        if heuristic_match:
            matched_any = True
            if not self._match_heuristic(heuristic_match, ctx):
                return False

        return matched_any

    def _select_policy_provider(
        self, select: dict, ctx: _RoutingContext
    ) -> tuple[str | None, list[dict[str, Any]]]:
        """Choose a provider from the current config based on a policy rule."""
        candidates = [
            name
            for name, provider in ctx.providers.items()
            if self._provider_matches_policy(provider, name, select, ctx)
        ]
        if not candidates:
            return None, []

        ranked, ranking = self._rank_policy_candidates(candidates, select, ctx)
        for provider_name in ranked:
            if ctx.provider_health.get(provider_name, {}).get("healthy", True):
                return provider_name, ranking
        return (ranked[0] if ranked else None), ranking

    def _provider_matches_policy(
        self, provider: dict, name: str, select: dict, ctx: _RoutingContext
    ) -> bool:
        """Return whether a provider is eligible for a policy rule."""
        capabilities = provider.get("capabilities", {})
        allow = select.get("allow_providers", [])
        deny = set(select.get("deny_providers", []))

        if allow and name not in allow:
            return False
        if name in deny:
            return False

        for capability in select.get("require_capabilities", []):
            if not capabilities.get(capability):
                return False

        for capability, expected_values in select.get("capability_values", {}).items():
            if capabilities.get(capability) not in expected_values:
                return False

        return self._provider_fits_request_dimensions(name, provider, ctx)

    def _rank_policy_candidates(
        self, candidates: list[str], select: dict, ctx: _RoutingContext
    ) -> tuple[list[str], list[dict[str, Any]]]:
        """Rank eligible policy candidates by explicit preference, then provider order."""
        preferred = []
        prefer_providers = select.get("prefer_providers", [])
        prefer_tiers = set(select.get("prefer_tiers", []))
        locality_preference = self._locality_preference(select)
        routing_posture = self._routing_posture(select, ctx)
        diagnostics = {
            name: self._provider_dimension_details(
                name,
                ctx,
                locality_preference,
                routing_posture,
            )
            for name in candidates
        }
        ranked_candidates = sorted(
            candidates,
            key=lambda name: diagnostics[name]["sort_key"],
            reverse=True,
        )

        def _append(name: str) -> None:
            if name in candidates and name not in preferred:
                preferred.append(name)

        for name in prefer_providers:
            _append(name)

        if prefer_tiers:
            for name in ranked_candidates:
                provider = self.config.provider(name) or {}
                if provider.get("tier") in prefer_tiers:
                    _append(name)

        for name in ranked_candidates:
            _append(name)

        ranking = []
        for idx, name in enumerate(preferred, start=1):
            ranking.append(
                {
                    "rank": idx,
                    "provider": name,
                    **{key: value for key, value in diagnostics[name].items() if key != "sort_key"},
                }
            )

        return preferred, ranking

    def _provider_fits_request_dimensions(
        self, name: str, provider: dict, ctx: _RoutingContext | None
    ) -> bool:
        """Return whether a provider can satisfy the current token and context shape."""
        if ctx is None:
            return True

        limits = provider.get("limits", {})
        max_input = limits.get("max_input_tokens")
        max_output = limits.get("max_output_tokens")
        context_window = provider.get("context_window")

        if max_input and ctx.total_tokens > max_input:
            return False
        if max_output and ctx.requested_output_tokens and ctx.requested_output_tokens > max_output:
            return False
        if context_window and ctx.total_requested_tokens > context_window:
            return False
        if ctx.required_capability in {"image_generation", "image_editing"}:
            image_cfg = provider.get("image", {})
            max_outputs = int(image_cfg.get("max_outputs") or 0)
            max_side_px = int(image_cfg.get("max_side_px") or 0)
            supported_sizes = image_cfg.get("supported_sizes", [])
            if max_outputs and ctx.requested_image_outputs > max_outputs:
                return False
            if (
                max_side_px
                and ctx.requested_image_side_px
                and ctx.requested_image_side_px > max_side_px
            ):
                return False
            if (
                supported_sizes
                and ctx.requested_image_size
                and ctx.requested_image_size not in supported_sizes
            ):
                return False
        return True

    def _provider_dimension_details(
        self,
        name: str,
        ctx: _RoutingContext | None,
        locality_preference: str | None,
        routing_posture: str,
    ) -> dict[str, Any]:
        """Return a multi-dimensional ranking breakdown for one provider."""
        provider = self.config.provider(name) or {}
        limits = provider.get("limits", {})
        cache = provider.get("cache", {})
        image_cfg = provider.get("image", {})
        capabilities = provider.get("capabilities", {})
        lane = self._provider_lane_summary(name)
        health = ctx.provider_health.get(name, {}) if ctx else {}
        runtime_state = ctx.provider_runtime_state.get(name, {}) if ctx else {}

        if ctx is None:
            return {
                "fit": True,
                "score_total": 0,
                "health_score": 0,
                "failure_score": 0,
                "latency_score": 0,
                "locality_score": 0,
                "cache_score": 0,
                "context_score": 0,
                "input_score": 0,
                "output_score": 0,
                "lane_score": 0,
                "route_score": 0,
                "benchmark_score": 0,
                "benchmark_request_score": 0,
                "cost_score": 0,
                "estimated_request_cost_usd": 0.0,
                "cost_tier": "",
                "adaptation_penalty": 0,
                "headroom": 0,
                "sort_key": (0, 0, 0),
            }

        context_window = int(provider.get("context_window") or 0)
        max_input = int(limits.get("max_input_tokens") or 0)
        max_output = int(limits.get("max_output_tokens") or 0)
        headroom = 0
        if context_window:
            headroom = max(0, context_window - ctx.total_requested_tokens)
        elif max_input:
            headroom = max(0, max_input - ctx.total_tokens)

        requested_input = max(ctx.total_tokens, 1)
        requested_total = max(ctx.total_requested_tokens, 1)
        requested_output = max(ctx.requested_output_tokens, 1) if ctx.requested_output_tokens else 0

        context_ratio = (context_window / requested_total) if context_window else 0.0
        input_ratio = (max_input / requested_input) if max_input else context_ratio
        output_ratio = (max_output / requested_output) if max_output and requested_output else 0.0

        prefers_cache = ctx.cache_preference in {"prefer", "prefer-cache"} or (
            not ctx.cache_preference and ctx.stable_prefix_tokens >= 64
        )
        cache_score = 0
        if prefers_cache and cache.get("mode") != "none":
            cache_score = 10 if cache.get("read_discount") else 7
        elif cache.get("mode") != "none":
            cache_score = 2

        context_score = _score_capacity_ratio(context_ratio)
        input_score = _score_capacity_ratio(input_ratio)
        output_score = _score_capacity_ratio(output_ratio) if requested_output else 2

        healthy = bool(health.get("healthy", True))
        consecutive_failures = int(health.get("consecutive_failures", 0) or 0)
        avg_latency_ms = float(health.get("avg_latency_ms", 0) or 0)
        health_score = 25 if healthy else 0
        failure_score = max(0, 12 - (consecutive_failures * 3))
        if avg_latency_ms <= 0:
            latency_score = 6
        elif avg_latency_ms <= 250:
            latency_score = 10
        elif avg_latency_ms <= 750:
            latency_score = 8
        elif avg_latency_ms <= 1500:
            latency_score = 5
        elif avg_latency_ms <= 3000:
            latency_score = 2
        else:
            latency_score = 0

        locality_score = 0
        if locality_preference == "local":
            locality_score = 10 if capabilities.get("local") else 0
        elif locality_preference == "cloud":
            locality_score = 10 if capabilities.get("cloud") else 0
        else:
            locality_score = (
                2 if capabilities.get("local") else 1 if capabilities.get("cloud") else 0
            )

        lane_score = self._lane_posture_score(lane, routing_posture)
        route_score = self._route_posture_score(lane, routing_posture)
        benchmark_score = self._benchmark_posture_score(lane, routing_posture)
        benchmark_request_score = _benchmark_request_score(lane, ctx)
        cost_tier = str(capabilities.get("cost_tier") or lane.get("quality_tier") or "")
        estimated_request_cost_usd = _estimated_request_cost_usd(provider, ctx)
        cost_score = _cost_posture_score(
            estimated_cost_usd=estimated_request_cost_usd,
            routing_posture=routing_posture,
            cost_tier=cost_tier,
        )
        adaptation_penalty = int(runtime_state.get("penalty", 0) or 0)
        recovery_score = self._recovery_posture_score(lane, runtime_state, routing_posture)
        image_score = 0
        image_policy_score = 0
        image_outputs_fit = True
        image_size_fit = True
        image_supported_size = True
        image_policy_match = not bool(ctx.requested_image_policy)
        image_policy_tags = image_cfg.get("policy_tags", [])
        if ctx.required_capability in {"image_generation", "image_editing"}:
            max_outputs = int(image_cfg.get("max_outputs") or 0)
            max_side_px = int(image_cfg.get("max_side_px") or 0)
            supported_sizes = image_cfg.get("supported_sizes", [])
            requested_outputs = max(ctx.requested_image_outputs, 1)
            requested_side = ctx.requested_image_side_px

            if max_outputs:
                image_outputs_fit = requested_outputs <= max_outputs
                ratio = requested_outputs / max_outputs
                image_score += _score_image_fit_ratio(ratio) if image_outputs_fit else 0
            else:
                image_score += 2

            if max_side_px and requested_side:
                image_size_fit = requested_side <= max_side_px
                ratio = requested_side / max_side_px
                image_score += _score_image_fit_ratio(ratio) if image_size_fit else 0
            elif requested_side:
                image_score += 2

            if supported_sizes:
                image_supported_size = (
                    not ctx.requested_image_size or ctx.requested_image_size in supported_sizes
                )
                image_score += 6 if image_supported_size else 0
            elif ctx.requested_image_size:
                image_score += 1

            if ctx.requested_image_policy:
                image_policy_match = ctx.requested_image_policy in image_policy_tags
                image_policy_score = 12 if image_policy_match else 0
            elif image_policy_tags:
                image_policy_score = 1

        fit = self._provider_fits_request_dimensions(name, provider, ctx)
        score_total = (
            health_score
            + failure_score
            + latency_score
            + locality_score
            + cache_score
            + context_score
            + input_score
            + output_score
            + lane_score
            + route_score
            + benchmark_score
            + benchmark_request_score
            + cost_score
            + recovery_score
            + image_score
            + image_policy_score
            - adaptation_penalty
        )
        return {
            "fit": fit,
            "score_total": score_total,
            "health_score": health_score,
            "failure_score": failure_score,
            "latency_score": latency_score,
            "locality_score": locality_score,
            "cache_score": cache_score,
            "context_score": context_score,
            "input_score": input_score,
            "output_score": output_score,
            "lane_score": lane_score,
            "route_score": route_score,
            "benchmark_score": benchmark_score,
            "benchmark_request_score": benchmark_request_score,
            "cost_score": cost_score,
            "estimated_request_cost_usd": estimated_request_cost_usd,
            "cost_tier": cost_tier,
            "adaptation_penalty": adaptation_penalty,
            "recovery_score": recovery_score,
            "image_score": image_score,
            "image_policy_score": image_policy_score,
            "headroom": headroom,
            "context_ratio": round(context_ratio, 3),
            "input_ratio": round(input_ratio, 3),
            "output_ratio": round(output_ratio, 3) if requested_output else 0.0,
            "image_outputs_fit": image_outputs_fit,
            "image_size_fit": image_size_fit,
            "image_supported_size": image_supported_size,
            "image_policy_match": image_policy_match,
            "requested_image_policy": ctx.requested_image_policy,
            "image_policy_tags": image_policy_tags,
            "requested_image_outputs": ctx.requested_image_outputs,
            "requested_image_size": ctx.requested_image_size,
            "max_image_outputs": image_cfg.get("max_outputs"),
            "max_image_side_px": image_cfg.get("max_side_px"),
            "supported_image_sizes": image_cfg.get("supported_sizes", []),
            "avg_latency_ms": avg_latency_ms,
            "consecutive_failures": consecutive_failures,
            "runtime_issue_type": str(runtime_state.get("last_issue_type") or ""),
            "runtime_issue_detail": str(runtime_state.get("last_issue_detail") or ""),
            "runtime_penalty": adaptation_penalty,
            "runtime_recovered_recently": bool(runtime_state.get("recovered_recently")),
            "runtime_recovery_remaining_s": int(runtime_state.get("recovery_remaining_s") or 0),
            "runtime_last_recovered_issue_type": str(
                runtime_state.get("last_recovered_issue_type") or ""
            ),
            "cache_mode": cache.get("mode", "none"),
            "locality_preference": locality_preference or "balanced",
            "routing_posture": routing_posture,
            "lane_family": lane.get("family", ""),
            "lane_name": lane.get("name", ""),
            "canonical_model": lane.get("canonical_model", ""),
            "route_type": lane.get("route_type", ""),
            "lane_cluster": lane.get("cluster", ""),
            "benchmark_cluster": lane.get("benchmark_cluster", ""),
            "quality_tier": lane.get("quality_tier", ""),
            "reasoning_strength": lane.get("reasoning_strength", ""),
            "same_model_group": lane.get("same_model_group", ""),
            "degrade_to": list(lane.get("degrade_to", [])),
            "sort_key": (
                1 if fit else 0,
                score_total,
                headroom,
            ),
        }

    def _provider_lane_summary(self, name: str) -> dict[str, Any]:
        provider = self.config.provider(name) or {}
        lane = provider.get("lane", {})
        if not isinstance(lane, dict):
            return {}
        return {
            "family": str(lane.get("family") or ""),
            "name": str(lane.get("name") or ""),
            "canonical_model": str(lane.get("canonical_model") or ""),
            "route_type": str(lane.get("route_type") or ""),
            "cluster": str(lane.get("cluster") or ""),
            "benchmark_cluster": str(lane.get("benchmark_cluster") or ""),
            "quality_tier": str(lane.get("quality_tier") or ""),
            "reasoning_strength": str(lane.get("reasoning_strength") or ""),
            "context_strength": str(lane.get("context_strength") or ""),
            "tool_strength": str(lane.get("tool_strength") or ""),
            "same_model_group": str(lane.get("same_model_group") or ""),
            "degrade_to": list(lane.get("degrade_to") or []),
        }

    def _routing_posture(self, select: dict[str, Any], ctx: _RoutingContext | None = None) -> str:
        routing_mode = str(select.get("routing_mode", "") or "").strip()
        if not routing_mode and ctx is not None:
            routing_mode = str((ctx.profile_hints or {}).get("routing_mode", "") or "").strip()
        if routing_mode:
            return _normalize_routing_posture(routing_mode)

        prefer_tiers = {str(item).strip().lower() for item in select.get("prefer_tiers", [])}
        if not prefer_tiers and ctx is not None:
            prefer_tiers = {
                str(item).strip().lower()
                for item in (ctx.profile_hints or {}).get("prefer_tiers", [])
            }

        if "premium" in prefer_tiers:
            return "quality"
        if "cheap" in prefer_tiers or "fallback" in prefer_tiers:
            return "eco"
        return "balanced"

    def _lane_posture_score(self, lane: dict[str, Any], routing_posture: str) -> int:
        if not lane:
            return 0
        cluster_scores = _CLUSTER_POSTURE_SCORES.get(
            routing_posture,
            _CLUSTER_POSTURE_SCORES["balanced"],
        )
        quality_score = _QUALITY_TIER_SCORES.get(str(lane.get("quality_tier") or "").lower(), 0)
        reasoning_score = _STRENGTH_SCORES.get(str(lane.get("reasoning_strength") or "").lower(), 0)
        cluster_score = cluster_scores.get(str(lane.get("cluster") or ""), 0)
        return cluster_score + max(0, quality_score // 2) + max(0, reasoning_score // 3)

    def _route_posture_score(self, lane: dict[str, Any], routing_posture: str) -> int:
        if not lane:
            return 0
        route_scores = _ROUTE_POSTURE_SCORES.get(routing_posture, _ROUTE_POSTURE_SCORES["balanced"])
        return route_scores.get(str(lane.get("route_type") or "").lower(), 0)

    def _benchmark_posture_score(self, lane: dict[str, Any], routing_posture: str) -> int:
        if not lane:
            return 0
        benchmark_scores = _BENCHMARK_POSTURE_SCORES.get(
            routing_posture,
            _BENCHMARK_POSTURE_SCORES["balanced"],
        )
        return benchmark_scores.get(str(lane.get("benchmark_cluster") or ""), 0)

    def _recovery_posture_score(
        self,
        lane: dict[str, Any],
        runtime_state: dict[str, Any],
        routing_posture: str,
    ) -> int:
        if not bool(runtime_state.get("recovered_recently")):
            return 0

        recovery_window = max(1, int(runtime_state.get("recovery_window_s") or 0))
        recovery_remaining = max(0, int(runtime_state.get("recovery_remaining_s") or 0))
        freshness = min(1.0, recovery_remaining / recovery_window)

        route_type = str(lane.get("route_type") or "").lower()
        trust_bonus_by_route = {
            "local": 5.0,
            "direct": 4.0,
            "aggregator": 2.0,
        }
        caution_penalty_by_posture = {
            "quality": 5.0,
            "balanced": 3.0,
            "eco": 2.0,
            "free": 1.0,
        }
        trust_bonus = trust_bonus_by_route.get(route_type, 2.0)
        caution_penalty = caution_penalty_by_posture.get(routing_posture, 3.0)
        score = (trust_bonus * (1.0 - freshness)) - (caution_penalty * freshness)
        return int(round(score))

    def _fallback_relation_details(
        self,
        primary_provider: str,
        candidate_provider: str,
        routing_posture: str,
    ) -> dict[str, Any]:
        primary_lane = self._provider_lane_summary(primary_provider)
        candidate_lane = self._provider_lane_summary(candidate_provider)
        same_model_group = bool(
            primary_lane.get("same_model_group")
            and primary_lane.get("same_model_group") == candidate_lane.get("same_model_group")
        )
        same_canonical = bool(
            primary_lane.get("canonical_model")
            and primary_lane.get("canonical_model") == candidate_lane.get("canonical_model")
        )
        same_cluster = bool(
            primary_lane.get("cluster")
            and primary_lane.get("cluster") == candidate_lane.get("cluster")
        )
        same_benchmark_cluster = bool(
            primary_lane.get("benchmark_cluster")
            and primary_lane.get("benchmark_cluster") == candidate_lane.get("benchmark_cluster")
        )
        preferred_degrade = bool(
            candidate_lane.get("canonical_model")
            and candidate_lane.get("canonical_model") in (primary_lane.get("degrade_to") or [])
        )
        weights = _FALLBACK_RELATION_WEIGHTS.get(
            routing_posture,
            _FALLBACK_RELATION_WEIGHTS["balanced"],
        )
        relation_score = 0
        selection_path = "fallback-chain"
        if same_model_group or same_canonical:
            relation_score += weights["same_model_route"]
            selection_path = "same-lane-route"
        elif same_cluster or same_benchmark_cluster:
            relation_score += weights["same_cluster"]
            selection_path = "same-cluster-degrade" if same_cluster else "same-benchmark-degrade"
        elif preferred_degrade:
            relation_score += weights["preferred_degrade"]
            selection_path = "preferred-degrade"
        return {
            "relation_score": relation_score,
            "same_model_route": same_model_group or same_canonical,
            "same_cluster": same_cluster,
            "same_benchmark_cluster": same_benchmark_cluster,
            "preferred_degrade": preferred_degrade,
            "selection_path": selection_path,
        }

    def _rank_fallback_candidates(
        self,
        primary_provider: str,
        candidates: list[str],
        ctx: _RoutingContext,
    ) -> tuple[list[str], list[dict[str, Any]]]:
        routing_posture = self._routing_posture({}, ctx)
        diagnostics = {
            name: self._provider_dimension_details(name, ctx, None, routing_posture)
            for name in candidates
        }
        relations = {
            name: self._fallback_relation_details(primary_provider, name, routing_posture)
            for name in candidates
        }
        ranked = sorted(
            candidates,
            key=lambda name: (
                relations[name]["relation_score"],
                diagnostics[name]["score_total"],
                diagnostics[name]["headroom"],
            ),
            reverse=True,
        )
        ranking = []
        for idx, name in enumerate(ranked, start=1):
            ranking.append(
                {
                    "rank": idx,
                    "provider": name,
                    **relations[name],
                    **{key: value for key, value in diagnostics[name].items() if key != "sort_key"},
                }
            )
        return ranked, ranking

    def _enrich_decision_details(
        self,
        decision: RoutingDecision,
        ctx: _RoutingContext,
        *,
        extra_details: dict[str, Any] | None = None,
    ) -> RoutingDecision:
        details = dict(decision.details)
        lane = self._provider_lane_summary(decision.provider_name)
        request_insights = dict(getattr(ctx, "request_insights", {}) or {})
        if lane:
            details.setdefault("selected_lane", lane)
            details.setdefault("canonical_model", lane.get("canonical_model", ""))
            details.setdefault("lane_family", lane.get("family", ""))
            details.setdefault("lane_name", lane.get("name", ""))
            details.setdefault("route_type", lane.get("route_type", ""))
            details.setdefault("lane_cluster", lane.get("cluster", ""))
            details.setdefault(
                "known_routes",
                get_canonical_model_routes(str(lane.get("canonical_model") or "")),
            )
            details.setdefault(
                "configured_same_lane_routes",
                [
                    provider_name
                    for provider_name, provider in ctx.providers.items()
                    if provider_name != decision.provider_name
                    and str((provider.get("lane") or {}).get("canonical_model") or "")
                    == str(lane.get("canonical_model") or "")
                ],
            )
        if request_insights:
            details.setdefault("request_insights", request_insights)
        details.setdefault("routing_posture", self._routing_posture({}, ctx))
        details.setdefault(
            "route_runtime_state",
            ctx.provider_runtime_state.get(decision.provider_name, {}),
        )
        if "candidate_ranking" not in details and "score_ranking" not in details:
            details.setdefault("score_ranking", self._score_provider_candidates(ctx))
        if extra_details:
            details.update(extra_details)
        decision.details = details
        return decision

    def _score_provider_candidates(
        self, ctx: _RoutingContext, *, limit: int = 3
    ) -> list[dict[str, Any]]:
        routing_posture = self._routing_posture({}, ctx)
        diagnostics = {
            name: self._provider_dimension_details(name, ctx, None, routing_posture)
            for name in ctx.providers
        }
        ranked = [
            name
            for name in sorted(
                ctx.providers,
                key=lambda name: diagnostics[name]["sort_key"],
                reverse=True,
            )
            if diagnostics[name]["fit"]
        ]
        if not ranked:
            ranked = list(
                sorted(
                    ctx.providers,
                    key=lambda name: diagnostics[name]["sort_key"],
                    reverse=True,
                )
            )
        summary: list[dict[str, Any]] = []
        for idx, name in enumerate(ranked[:limit], start=1):
            details = diagnostics[name]
            summary.append(
                {
                    "rank": idx,
                    "provider": name,
                    "score_total": details["score_total"],
                    "routing_posture": details["routing_posture"],
                    "lane_family": details["lane_family"],
                    "canonical_model": details["canonical_model"],
                    "route_type": details["route_type"],
                    "lane_cluster": details["lane_cluster"],
                    "benchmark_cluster": details["benchmark_cluster"],
                    "benchmark_request_score": details["benchmark_request_score"],
                    "cost_score": details["cost_score"],
                    "estimated_request_cost_usd": details["estimated_request_cost_usd"],
                    "cost_tier": details["cost_tier"],
                    "runtime_penalty": details["runtime_penalty"],
                    "runtime_issue_type": details["runtime_issue_type"],
                    "runtime_recovered_recently": details["runtime_recovered_recently"],
                }
            )
        return summary

    def _locality_preference(self, select: dict[str, Any]) -> str | None:
        """Infer one locality preference from the active selector."""
        prefer_tiers = set(select.get("prefer_tiers", []))
        if "local" in prefer_tiers:
            return "local"
        capability_values = select.get("capability_values", {})
        if capability_values.get("local") == [True]:
            return "local"
        if capability_values.get("cloud") == [True]:
            return "cloud"
        return None

    # ── Layer 3: Request Hooks ────────────────────────────────

    def _layer_hook(self, ctx: _RoutingContext) -> RoutingDecision | None:
        """Apply hook-provided routing hints after heuristic routing."""
        if not ctx.hook_hints:
            return None

        provider_name, ranking = self._select_policy_provider(ctx.hook_hints, ctx)
        if not provider_name:
            return None

        hook_list = ", ".join(ctx.applied_hooks) if ctx.applied_hooks else "request hooks"
        return RoutingDecision(
            provider_name=provider_name,
            layer="hook",
            rule_name="request-hooks",
            confidence=0.7,
            reason=f"{hook_list} selected a preferred provider",
            details={"candidate_ranking": ranking},
        )

    # ── Layer 4: Client Profiles ──────────────────────────────

    def _layer_profile(self, ctx: _RoutingContext) -> RoutingDecision | None:
        """Apply default provider preferences for the resolved client profile."""
        if not ctx.profile_hints:
            return None

        provider_name, ranking = self._select_policy_provider(ctx.profile_hints, ctx)
        if not provider_name:
            return None

        return RoutingDecision(
            provider_name=provider_name,
            layer="profile",
            rule_name=f"profile-{ctx.client_profile}",
            confidence=0.6,
            reason=f"Client profile '{ctx.client_profile}' selected a preferred provider",
            details={"candidate_ranking": ranking},
        )

    # ── Layer 1: Static Rules ──────────────────────────────────

    def _layer_static(self, ctx: _RoutingContext) -> RoutingDecision | None:
        cfg = self.config.static_rules
        if not cfg.get("enabled"):
            return None

        for rule in cfg.get("rules", []):
            match = rule.get("match", {})

            if self._match_static(match, ctx):
                logger.debug("Static rule matched: %s → %s", rule["name"], rule["route_to"])
                return RoutingDecision(
                    provider_name=rule["route_to"],
                    layer="static",
                    rule_name=rule["name"],
                    confidence=1.0,
                    reason=f"Static rule '{rule['name']}' matched",
                )

        return None

    def _match_static(self, match: dict, ctx: _RoutingContext) -> bool:
        """Evaluate a static match block."""
        # "any" → at least one sub-condition must match
        if "any" in match:
            return any(self._match_static(sub, ctx) for sub in match["any"])

        matched_any = False

        # model_requested
        if "model_requested" in match:
            matched_any = True
            patterns = match["model_requested"]
            if isinstance(patterns, str):
                patterns = [patterns]
            if not any(p in ctx.model_requested for p in patterns):
                return False

        # system_prompt_contains
        if "system_prompt_contains" in match:
            matched_any = True
            keywords = match["system_prompt_contains"]
            lower_sys = ctx.system_prompt.lower()
            if not any(kw.lower() in lower_sys for kw in keywords):
                return False

        # header_contains
        if "header_contains" in match:
            matched_any = True
            for header_name, patterns in match["header_contains"].items():
                header_val = ctx.headers.get(header_name, "").lower()
                if not any(p.lower() in header_val for p in patterns):
                    return False

        return matched_any

    # ── Layer 2: Heuristic Rules ───────────────────────────────

    def _layer_heuristic(self, ctx: _RoutingContext) -> RoutingDecision | None:
        cfg = self.config.heuristic_rules
        if not cfg.get("enabled"):
            return None

        for rule in cfg.get("rules", []):
            matched, match_details = self._evaluate_heuristic_match(rule, ctx)
            if matched:
                logger.debug("Heuristic rule matched: %s → %s", rule["name"], rule["route_to"])
                return RoutingDecision(
                    provider_name=rule["route_to"],
                    layer="heuristic",
                    rule_name=rule["name"],
                    confidence=0.8,
                    reason=f"Heuristic rule '{rule['name']}' matched",
                    details={"heuristic_match": match_details},
                )

        return None

    def _match_heuristic(self, match: dict[str, Any], ctx: _RoutingContext) -> bool:
        """Backwards-compatible bool-only heuristic matcher used by tests and policy composition."""
        matched, _ = self._evaluate_heuristic_match({"name": "", "match": match}, ctx)
        return matched

    def _evaluate_heuristic_match(
        self, rule: dict[str, Any], ctx: _RoutingContext
    ) -> tuple[bool, dict[str, Any]]:
        """Evaluate a heuristic match block."""
        match = rule.get("match", {})
        rule_name = str(rule.get("name") or "")
        # fallthrough = always matches (used as default)
        if match.get("fallthrough"):
            return True, {"rule_name": rule_name, "fallthrough": True}

        matched_any = False
        details: dict[str, Any] = {"rule_name": rule_name}

        # has_tools
        if "has_tools" in match:
            matched_any = True
            if match["has_tools"] != ctx.has_tools:
                return False, details

        # estimated_tokens
        if "estimated_tokens" in match:
            matched_any = True
            tok_match = match["estimated_tokens"]
            token_ok = True
            if "less_than" in tok_match:
                token_ok = token_ok and ctx.total_tokens < tok_match["less_than"]
            if "greater_than" in tok_match:
                token_ok = token_ok and ctx.total_tokens > tok_match["greater_than"]
            if not token_ok:
                return False, details

        # message_keywords
        if "message_keywords" in match:
            matched_any = True
            kw_cfg = match["message_keywords"]
            keywords = kw_cfg.get("any_of", [])
            original_min_matches = int(kw_cfg.get("min_matches", 1) or 1)
            min_matches = original_min_matches

            # CRITICAL: Score only user messages, NOT the system prompt.
            # ClawRouter insight: OpenClaw's system prompt is keyword-rich
            # and would inflate every request to the reasoning tier.
            search_text = ctx.last_user_message.lower()
            matched_keywords = [
                str(kw).strip().lower()
                for kw in keywords
                if _keyword_matches_text(str(kw), search_text)
            ]
            hit_count = len(matched_keywords)
            request_insights = dict(getattr(ctx, "request_insights", {}) or {})
            complexity_profile = str(request_insights.get("complexity_profile") or "")
            signal_groups = list(request_insights.get("signal_groups") or [])
            opencode_bias_applied = False
            suppressed_for_complexity = False

            if (
                ctx.client_profile == "opencode"
                and any(
                    _keyword_matches_text(term, search_text) for term in _OPENCODE_COMPLEXITY_HINTS
                )
                and any(term in _OPENCODE_COMPLEXITY_RULE_KEYWORDS for term in matched_keywords)
            ):
                min_matches = max(1, int(min_matches) - 1)
                opencode_bias_applied = True

            if (
                ctx.client_profile == "opencode"
                and complexity_profile == "high"
                and any(token in rule_name.lower() for token in ("complex", "reason", "debug"))
                and matched_keywords
            ):
                min_matches = max(1, int(min_matches) - 1)
                opencode_bias_applied = True

            if (
                ctx.client_profile == "opencode"
                and complexity_profile in {"medium", "high"}
                and "simple" in rule_name.lower()
                and matched_keywords
            ):
                suppressed_for_complexity = True

            details.update(
                {
                    "matched_keywords": matched_keywords,
                    "keyword_hit_count": hit_count,
                    "original_min_matches": original_min_matches,
                    "effective_min_matches": min_matches,
                    "opencode_bias_applied": opencode_bias_applied,
                    "suppressed_for_complexity": suppressed_for_complexity,
                    "complexity_profile": complexity_profile,
                    "signal_groups": signal_groups,
                }
            )

            if suppressed_for_complexity:
                return False, details

            if hit_count < min_matches:
                return False, details

        return matched_any, details

    # ── Layer 3: LLM Classifier ────────────────────────────────

    async def _layer_llm_classify(self, ctx: _RoutingContext) -> RoutingDecision | None:
        """Use a cheap LLM to classify the task. Imported lazily to avoid circular deps."""
        cfg = self.config.llm_classifier
        prompt_template = cfg.get("prompt", "")
        category_routing = cfg.get("category_routing", {})

        prompt = prompt_template.replace("{last_user_message}", ctx.last_user_message[:500])

        # We need to call the classifier provider – this is done by the dispatcher
        # which injects a classify callback
        if not hasattr(ctx, "_classify_fn") or ctx._classify_fn is None:
            logger.debug("LLM classifier enabled but no classify function available")
            return None

        try:
            category = await ctx._classify_fn(prompt)
            category = category.strip().upper()

            if category in category_routing:
                return RoutingDecision(
                    provider_name=category_routing[category],
                    layer="llm-classify",
                    rule_name=f"classified-as-{category}",
                    confidence=0.7,
                    reason=f"LLM classified task as {category}",
                    details={"category": category},
                )
        except Exception as e:
            logger.warning("LLM classification failed: %s", e)

        return None

    # ── Health validation ──────────────────────────────────────

    def _validate_health(
        self,
        decision: RoutingDecision,
        ctx: _RoutingContext,
        *,
        required_capabilities: list[str] | None = None,
    ) -> RoutingDecision:
        """If chosen provider is unhealthy or over limits, fall through the chain."""
        health = ctx.provider_health.get(decision.provider_name)
        primary = self.config.provider(decision.provider_name) or {}
        reason_suffix = None
        if health and not health.get("healthy", True):
            reason_suffix = "primary unhealthy"
        elif not self._provider_fits_request_dimensions(decision.provider_name, primary, ctx):
            reason_suffix = "primary exceeded request dimensions"

        if reason_suffix:
            logger.info(
                "Provider %s unsuitable (%s), falling through chain",
                decision.provider_name,
                reason_suffix,
            )
            fallback_candidates = []
            for fallback in self.config.fallback_chain:
                provider = self.config.provider(fallback) or {}
                fb_health = ctx.provider_health.get(fallback, {})
                if not fb_health.get("healthy", True):
                    continue
                if required_capabilities and any(
                    not provider.get("capabilities", {}).get(capability)
                    for capability in required_capabilities
                ):
                    continue
                if not self._provider_fits_request_dimensions(fallback, provider, ctx):
                    continue
                fallback_candidates.append(fallback)

            if fallback_candidates:
                _, fallback_ranking = self._rank_fallback_candidates(
                    decision.provider_name,
                    fallback_candidates,
                    ctx,
                )
                best_fallback = fallback_ranking[0]["provider"]
                return self._enrich_decision_details(
                    RoutingDecision(
                        provider_name=best_fallback,
                        layer=decision.layer,
                        rule_name=f"{decision.rule_name}→fallback",
                        confidence=decision.confidence * 0.8,
                        reason=f"{decision.reason} ({reason_suffix}, fell to {best_fallback})",
                        elapsed_ms=decision.elapsed_ms,
                        details={
                            **decision.details,
                            "fallback_reason": reason_suffix,
                            "fallback_ranking": fallback_ranking,
                        },
                    ),
                    ctx,
                    extra_details={
                        "selection_path": fallback_ranking[0].get(
                            "selection_path",
                            "fallback-chain",
                        ),
                    },
                )
        return self._enrich_decision_details(decision, ctx)


class _RoutingContext:
    """Bundle of extracted request features for routing."""

    __slots__ = (
        "system_prompt",
        "last_user_message",
        "full_text",
        "total_tokens",
        "stable_prefix_tokens",
        "requested_output_tokens",
        "total_requested_tokens",
        "requested_image_outputs",
        "requested_image_side_px",
        "requested_image_size",
        "requested_image_policy",
        "required_capability",
        "cache_preference",
        "model_requested",
        "has_tools",
        "client_profile",
        "profile_hints",
        "hook_hints",
        "applied_hooks",
        "headers",
        "provider_health",
        "provider_runtime_state",
        "providers",
        "request_insights",
        "_classify_fn",
    )

    def __init__(self, **kwargs: Any):
        for k, v in kwargs.items():
            setattr(self, k, v)
        if not hasattr(self, "_classify_fn"):
            self._classify_fn = None
