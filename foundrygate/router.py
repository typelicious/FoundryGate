"""Layered routing engine for policy, heuristics, hooks, profiles, and LLM fallback."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from .config import Config

logger = logging.getLogger("foundrygate.router")


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
            cache_preference=(headers or {}).get("x-foundrygate-cache", "").strip().lower(),
            model_requested=model_requested.lower().strip(),
            has_tools=has_tools,
            client_profile=client_profile,
            profile_hints=profile_hints or {},
            hook_hints=hook_hints or {},
            applied_hooks=applied_hooks or [],
            headers=headers or {},
            provider_health=provider_health or {},
            providers=self.config.providers,
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
        return RoutingDecision(
            provider_name=fallback,
            layer="fallback",
            rule_name="no-match",
            confidence=0.3,
            reason="No routing layer matched, using first fallback",
            elapsed_ms=elapsed,
        )

    def route_capability_request(
        self,
        *,
        capability: str,
        request_text: str = "",
        model_requested: str = "",
        client_profile: str = "generic",
        profile_hints: dict[str, Any] | None = None,
        hook_hints: dict[str, Any] | None = None,
        applied_hooks: list[str] | None = None,
        headers: dict[str, str] | None = None,
        provider_health: dict[str, Any] | None = None,
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
            cache_preference=(headers or {}).get("x-foundrygate-cache", "").strip().lower(),
            model_requested=model_requested.lower().strip(),
            has_tools=False,
            client_profile=client_profile,
            profile_hints=profile_hints or {},
            hook_hints=hook_hints or {},
            applied_hooks=applied_hooks or [],
            headers=headers or {},
            provider_health=provider_health or {},
            providers=self.config.providers,
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
        if "client_profile" in match:
            profiles = match["client_profile"]
            if isinstance(profiles, str):
                profiles = [profiles]
            return ctx.client_profile in profiles

        static_keys = {"model_requested", "system_prompt_contains", "header_contains", "any"}
        heuristic_keys = {"has_tools", "estimated_tokens", "message_keywords", "fallthrough"}

        static_match = {k: match[k] for k in static_keys if k in match}
        heuristic_match = {k: match[k] for k in heuristic_keys if k in match}

        if static_match and not self._match_static(static_match, ctx):
            return False
        if heuristic_match and not self._match_heuristic(heuristic_match, ctx):
            return False

        return bool(static_match or heuristic_match)

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
        diagnostics = {
            name: self._provider_dimension_details(name, ctx, locality_preference)
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
        return True

    def _provider_dimension_details(
        self, name: str, ctx: _RoutingContext | None, locality_preference: str | None
    ) -> dict[str, Any]:
        """Return a multi-dimensional ranking breakdown for one provider."""
        provider = self.config.provider(name) or {}
        limits = provider.get("limits", {})
        cache = provider.get("cache", {})
        capabilities = provider.get("capabilities", {})
        health = ctx.provider_health.get(name, {}) if ctx else {}

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
            "headroom": headroom,
            "context_ratio": round(context_ratio, 3),
            "input_ratio": round(input_ratio, 3),
            "output_ratio": round(output_ratio, 3) if requested_output else 0.0,
            "avg_latency_ms": avg_latency_ms,
            "consecutive_failures": consecutive_failures,
            "cache_mode": cache.get("mode", "none"),
            "locality_preference": locality_preference or "balanced",
            "sort_key": (
                1 if fit else 0,
                score_total,
                headroom,
            ),
        }

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

        # model_requested
        if "model_requested" in match:
            patterns = match["model_requested"]
            if isinstance(patterns, str):
                patterns = [patterns]
            if any(p in ctx.model_requested for p in patterns):
                return True
            if match.keys() == {"model_requested"}:
                return False

        # system_prompt_contains
        if "system_prompt_contains" in match:
            keywords = match["system_prompt_contains"]
            lower_sys = ctx.system_prompt.lower()
            if any(kw.lower() in lower_sys for kw in keywords):
                return True
            if match.keys() == {"system_prompt_contains"}:
                return False

        # header_contains
        if "header_contains" in match:
            for header_name, patterns in match["header_contains"].items():
                header_val = ctx.headers.get(header_name, "").lower()
                if any(p.lower() in header_val for p in patterns):
                    return True

        return False

    # ── Layer 2: Heuristic Rules ───────────────────────────────

    def _layer_heuristic(self, ctx: _RoutingContext) -> RoutingDecision | None:
        cfg = self.config.heuristic_rules
        if not cfg.get("enabled"):
            return None

        for rule in cfg.get("rules", []):
            match = rule.get("match", {})

            if self._match_heuristic(match, ctx):
                logger.debug("Heuristic rule matched: %s → %s", rule["name"], rule["route_to"])
                return RoutingDecision(
                    provider_name=rule["route_to"],
                    layer="heuristic",
                    rule_name=rule["name"],
                    confidence=0.8,
                    reason=f"Heuristic rule '{rule['name']}' matched",
                )

        return None

    def _match_heuristic(self, match: dict, ctx: _RoutingContext) -> bool:
        """Evaluate a heuristic match block."""
        # fallthrough = always matches (used as default)
        if match.get("fallthrough"):
            return True

        # has_tools
        if "has_tools" in match:
            if match["has_tools"] == ctx.has_tools:
                return True
            return False

        # estimated_tokens
        if "estimated_tokens" in match:
            tok_match = match["estimated_tokens"]
            if "less_than" in tok_match and ctx.total_tokens < tok_match["less_than"]:
                return True
            if "greater_than" in tok_match and ctx.total_tokens > tok_match["greater_than"]:
                return True
            return False

        # message_keywords
        if "message_keywords" in match:
            kw_cfg = match["message_keywords"]
            keywords = kw_cfg.get("any_of", [])
            min_matches = kw_cfg.get("min_matches", 1)

            # CRITICAL: Score only user messages, NOT the system prompt.
            # ClawRouter insight: OpenClaw's system prompt is keyword-rich
            # and would inflate every request to the reasoning tier.
            search_text = ctx.last_user_message.lower()
            hit_count = sum(1 for kw in keywords if kw.lower() in search_text)

            return hit_count >= min_matches

        return False

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
                _, fallback_ranking = self._rank_policy_candidates(fallback_candidates, {}, ctx)
                best_fallback = fallback_ranking[0]["provider"]
                return RoutingDecision(
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
                )
        return decision


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
        "cache_preference",
        "model_requested",
        "has_tools",
        "client_profile",
        "profile_hints",
        "hook_hints",
        "applied_hooks",
        "headers",
        "provider_health",
        "providers",
        "_classify_fn",
    )

    def __init__(self, **kwargs: Any):
        for k, v in kwargs.items():
            setattr(self, k, v)
        if not hasattr(self, "_classify_fn"):
            self._classify_fn = None
