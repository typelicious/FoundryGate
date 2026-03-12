"""3-layer routing engine: static → heuristic → LLM classifier."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
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

    def to_dict(self) -> dict:
        return {
            "provider": self.provider_name,
            "layer": self.layer,
            "rule": self.rule_name,
            "confidence": self.confidence,
            "reason": self.reason,
            "elapsed_ms": round(self.elapsed_ms, 2),
        }


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token for mixed en/de text."""
    return max(1, len(text) // 4)


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

        ctx = _RoutingContext(
            system_prompt=system,
            last_user_message=last_user,
            full_text=full_text,
            total_tokens=total_tokens,
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

    # ── Layer 0: Policy Rules ──────────────────────────────────

    def _layer_policy(self, ctx: _RoutingContext) -> RoutingDecision | None:
        cfg = self.config.routing_policies
        if not cfg.get("enabled"):
            return None

        for rule in cfg.get("rules", []):
            match = rule.get("match", {})
            if not self._match_policy(match, ctx):
                continue

            provider_name = self._select_policy_provider(rule.get("select", {}), ctx)
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

    def _select_policy_provider(self, select: dict, ctx: _RoutingContext) -> str | None:
        """Choose a provider from the current config based on a policy rule."""
        candidates = [
            name
            for name, provider in ctx.providers.items()
            if self._provider_matches_policy(provider, name, select)
        ]
        if not candidates:
            return None

        ranked = self._rank_policy_candidates(candidates, select)
        for provider_name in ranked:
            if ctx.provider_health.get(provider_name, {}).get("healthy", True):
                return provider_name
        return ranked[0] if ranked else None

    def _provider_matches_policy(self, provider: dict, name: str, select: dict) -> bool:
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

        return True

    def _rank_policy_candidates(self, candidates: list[str], select: dict) -> list[str]:
        """Rank eligible policy candidates by explicit preference, then provider order."""
        preferred = []
        prefer_providers = select.get("prefer_providers", [])
        prefer_tiers = set(select.get("prefer_tiers", []))

        def _append(name: str) -> None:
            if name in candidates and name not in preferred:
                preferred.append(name)

        for name in prefer_providers:
            _append(name)

        if prefer_tiers:
            for name in candidates:
                provider = self.config.provider(name) or {}
                if provider.get("tier") in prefer_tiers:
                    _append(name)

        for name in candidates:
            _append(name)

        return preferred

    # ── Layer 3: Request Hooks ────────────────────────────────

    def _layer_hook(self, ctx: _RoutingContext) -> RoutingDecision | None:
        """Apply hook-provided routing hints after heuristic routing."""
        if not ctx.hook_hints:
            return None

        provider_name = self._select_policy_provider(ctx.hook_hints, ctx)
        if not provider_name:
            return None

        hook_list = ", ".join(ctx.applied_hooks) if ctx.applied_hooks else "request hooks"
        return RoutingDecision(
            provider_name=provider_name,
            layer="hook",
            rule_name="request-hooks",
            confidence=0.7,
            reason=f"{hook_list} selected a preferred provider",
        )

    # ── Layer 4: Client Profiles ──────────────────────────────

    def _layer_profile(self, ctx: _RoutingContext) -> RoutingDecision | None:
        """Apply default provider preferences for the resolved client profile."""
        if not ctx.profile_hints:
            return None

        provider_name = self._select_policy_provider(ctx.profile_hints, ctx)
        if not provider_name:
            return None

        return RoutingDecision(
            provider_name=provider_name,
            layer="profile",
            rule_name=f"profile-{ctx.client_profile}",
            confidence=0.6,
            reason=f"Client profile '{ctx.client_profile}' selected a preferred provider",
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
                )
        except Exception as e:
            logger.warning("LLM classification failed: %s", e)

        return None

    # ── Health validation ──────────────────────────────────────

    def _validate_health(self, decision: RoutingDecision, ctx: _RoutingContext) -> RoutingDecision:
        """If chosen provider is unhealthy, fall through the chain."""
        health = ctx.provider_health.get(decision.provider_name)
        if health and not health.get("healthy", True):
            logger.info("Provider %s unhealthy, falling through chain", decision.provider_name)
            for fallback in self.config.fallback_chain:
                fb_health = ctx.provider_health.get(fallback, {})
                if fb_health.get("healthy", True) and fallback != decision.provider_name:
                    return RoutingDecision(
                        provider_name=fallback,
                        layer=decision.layer,
                        rule_name=f"{decision.rule_name}→fallback",
                        confidence=decision.confidence * 0.8,
                        reason=f"{decision.reason} (primary unhealthy, fell to {fallback})",
                        elapsed_ms=decision.elapsed_ms,
                    )
        return decision


class _RoutingContext:
    """Bundle of extracted request features for routing."""

    __slots__ = (
        "system_prompt",
        "last_user_message",
        "full_text",
        "total_tokens",
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
