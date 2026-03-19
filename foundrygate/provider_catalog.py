"""Curated provider catalog and drift/freshness reporting."""

from __future__ import annotations

import os
import re
from datetime import date
from typing import Any

from .config import Config

_COMMUNITY_WATCHLIST = {
    "label": "free-llm-api-resources",
    "url": "https://github.com/cheahjs/free-llm-api-resources",
}

_DISCOVERY_DISCLOSURE = (
    "Provider recommendations stay performance-led. Signup or discovery links may include "
    "operator-configured affiliate attribution, but payout never affects ranking."
)

_CATALOG: dict[str, dict[str, Any]] = {
    "deepseek-chat": {
        "recommended_model": "deepseek-chat",
        "aliases": ["deepseek-chat"],
        "track": "stable",
        "offer_track": "direct",
        "provider_type": "direct",
        "auth_modes": ["api_key"],
        "volatility": "low",
        "evidence_level": "official",
        "official_source_url": "https://api-docs.deepseek.com/",
        "signup_url": "https://platform.deepseek.com/",
        "watch_sources": [],
        "notes": "Balanced DeepSeek chat default",
        "last_reviewed": "2026-03-19",
    },
    "deepseek-reasoner": {
        "recommended_model": "deepseek-reasoner",
        "aliases": ["deepseek-reasoner"],
        "track": "stable",
        "offer_track": "direct",
        "provider_type": "direct",
        "auth_modes": ["api_key"],
        "volatility": "low",
        "evidence_level": "official",
        "official_source_url": "https://api-docs.deepseek.com/",
        "signup_url": "https://platform.deepseek.com/",
        "watch_sources": [],
        "notes": "Reasoning-heavy DeepSeek path",
        "last_reviewed": "2026-03-19",
    },
    "gemini-flash-lite": {
        "recommended_model": "gemini-2.5-flash-lite",
        "aliases": ["gemini-2.5-flash-lite"],
        "track": "stable",
        "offer_track": "direct",
        "provider_type": "direct",
        "auth_modes": ["api_key"],
        "volatility": "low",
        "evidence_level": "official",
        "official_source_url": "https://ai.google.dev/gemini-api/docs/models",
        "signup_url": "https://aistudio.google.com/",
        "watch_sources": [],
        "notes": "Cheap Gemini default",
        "last_reviewed": "2026-03-19",
    },
    "gemini-flash": {
        "recommended_model": "gemini-2.5-flash",
        "aliases": ["gemini-2.5-flash"],
        "track": "stable",
        "offer_track": "direct",
        "provider_type": "direct",
        "auth_modes": ["api_key"],
        "volatility": "low",
        "evidence_level": "official",
        "official_source_url": "https://ai.google.dev/gemini-api/docs/models",
        "signup_url": "https://aistudio.google.com/",
        "watch_sources": [],
        "notes": "Balanced Gemini default",
        "last_reviewed": "2026-03-19",
    },
    "openrouter-fallback": {
        "recommended_model": "openrouter/auto",
        "aliases": ["openrouter/auto"],
        "track": "stable",
        "offer_track": "byok",
        "provider_type": "aggregator",
        "auth_modes": ["api_key", "byok"],
        "volatility": "medium",
        "evidence_level": "official",
        "official_source_url": "https://openrouter.ai/docs/features/provider-routing",
        "signup_url": "https://openrouter.ai/",
        "watch_sources": [],
        "notes": "Marketplace fallback path with official provider routing and BYOK support",
        "last_reviewed": "2026-03-19",
    },
    "kilocode": {
        "recommended_model": "z-ai/glm-5:free",
        "aliases": ["z-ai/glm-5:free"],
        "track": "free",
        "offer_track": "free",
        "provider_type": "aggregator",
        "auth_modes": ["api_key", "byok"],
        "volatility": "high",
        "evidence_level": "official",
        "official_source_url": "https://kilo.ai/docs/gateway/models-and-providers",
        "signup_url": "https://kilo.ai/",
        "watch_sources": [_COMMUNITY_WATCHLIST],
        "notes": "Current curated Kilo free-tier model; free and budget tracks can move quickly",
        "last_reviewed": "2026-03-19",
    },
    "blackbox-free": {
        "recommended_model": "blackboxai/x-ai/grok-code-fast-1:free",
        "aliases": ["blackboxai/x-ai/grok-code-fast-1:free"],
        "track": "free",
        "offer_track": "free",
        "provider_type": "aggregator",
        "auth_modes": ["api_key"],
        "volatility": "high",
        "evidence_level": "mixed",
        "official_source_url": "https://docs.blackbox.ai/api-reference/authentication",
        "signup_url": "https://cloud.blackbox.ai/",
        "watch_sources": [_COMMUNITY_WATCHLIST],
        "notes": (
            "Current curated BLACKBOX free-tier path; verify often because free "
            "offerings can rotate"
        ),
        "last_reviewed": "2026-03-19",
    },
    "openai-gpt4o": {
        "recommended_model": "gpt-4o",
        "aliases": ["gpt-4o"],
        "track": "stable",
        "offer_track": "direct",
        "provider_type": "direct",
        "auth_modes": ["api_key"],
        "volatility": "low",
        "evidence_level": "official",
        "official_source_url": "https://platform.openai.com/docs/models",
        "signup_url": "https://platform.openai.com/",
        "watch_sources": [],
        "notes": "Balanced OpenAI multimodal path",
        "last_reviewed": "2026-03-19",
    },
    "openai-images": {
        "recommended_model": "gpt-image-1",
        "aliases": ["gpt-image-1"],
        "track": "stable",
        "offer_track": "direct",
        "provider_type": "direct",
        "auth_modes": ["api_key"],
        "volatility": "low",
        "evidence_level": "official",
        "official_source_url": "https://platform.openai.com/docs/models",
        "signup_url": "https://platform.openai.com/",
        "watch_sources": [],
        "notes": "OpenAI image generation and editing",
        "last_reviewed": "2026-03-19",
    },
    "anthropic-claude": {
        "recommended_model": "claude-opus-4-6",
        "aliases": ["claude-opus-4-6"],
        "track": "stable",
        "offer_track": "direct",
        "provider_type": "direct",
        "auth_modes": ["api_key"],
        "volatility": "low",
        "evidence_level": "official",
        "official_source_url": "https://docs.anthropic.com/en/docs/about-claude/models",
        "signup_url": "https://console.anthropic.com/",
        "watch_sources": [],
        "notes": "Quality-first Anthropic default",
        "last_reviewed": "2026-03-19",
    },
    "clawrouter": {
        "recommended_model": "auto",
        "aliases": ["auto", "eco", "premium", "free"],
        "track": "stable",
        "offer_track": "marketplace",
        "provider_type": "wallet-router",
        "auth_modes": ["wallet_x402"],
        "volatility": "medium",
        "evidence_level": "official",
        "official_source_url": "https://blockrun.ai/docs/products/routing/clawrouter",
        "signup_url": "https://blockrun.ai/",
        "watch_sources": [],
        "notes": "BlockRun ClawRouter uses wallet/x402 routing modes rather than a classic API key",
        "last_reviewed": "2026-03-19",
    },
}


def _slugify_provider_name(provider_name: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", provider_name.upper()).strip("_")


def _discovery_env_var(provider_name: str) -> str:
    token = _slugify_provider_name(provider_name)
    return f"FOUNDRYGATE_PROVIDER_LINK_{token}_URL"


def _build_discovery_metadata(provider_name: str, catalog_entry: dict[str, Any]) -> dict[str, Any]:
    env_var = _discovery_env_var(provider_name)
    operator_url = str(os.environ.get(env_var, "") or "").strip()
    signup_url = str(catalog_entry.get("signup_url", "") or "").strip()
    discovery_url = (
        operator_url or signup_url or str(catalog_entry.get("official_source_url", "") or "")
    )

    return {
        "signup_url": signup_url,
        "resolved_url": discovery_url,
        "link_source": "operator_override" if operator_url else "official",
        "operator_env_var": env_var,
        "disclosure": _DISCOVERY_DISCLOSURE,
        "disclosure_required": bool(operator_url),
    }


def get_provider_catalog() -> dict[str, dict[str, Any]]:
    """Return a shallow copy of the curated provider catalog."""
    payload: dict[str, dict[str, Any]] = {}
    for name, entry in _CATALOG.items():
        item = dict(entry)
        item["discovery"] = _build_discovery_metadata(name, entry)
        payload[name] = item
    return payload


def _alert(
    *,
    provider: str,
    severity: str,
    code: str,
    message: str,
    **extra: Any,
) -> dict[str, Any]:
    payload = {
        "provider": provider,
        "severity": severity,
        "code": code,
        "message": message,
    }
    payload.update(extra)
    return payload


def _tracked_item(
    provider_name: str,
    provider: dict[str, Any],
    catalog_entry: dict[str, Any],
    *,
    today: date,
) -> dict[str, Any]:
    model = str(provider.get("model", "") or "").strip()
    recommended_model = str(catalog_entry["recommended_model"])
    aliases = list(catalog_entry.get("aliases", []))
    reviewed_on = date.fromisoformat(catalog_entry["last_reviewed"])
    age_days = (today - reviewed_on).days
    return {
        "provider": provider_name,
        "configured_model": model,
        "tracked": True,
        "status": "tracked",
        "recommended_model": recommended_model,
        "track": catalog_entry.get("track", "stable"),
        "offer_track": catalog_entry.get("offer_track", "direct"),
        "provider_type": catalog_entry.get("provider_type", "direct"),
        "auth_modes": list(catalog_entry.get("auth_modes", ["api_key"])),
        "volatility": catalog_entry.get("volatility", "low"),
        "evidence_level": catalog_entry.get("evidence_level", "official"),
        "official_source_url": catalog_entry.get("official_source_url", ""),
        "signup_url": catalog_entry.get("signup_url", ""),
        "discovery": _build_discovery_metadata(provider_name, catalog_entry),
        "watch_sources": list(catalog_entry.get("watch_sources", [])),
        "notes": catalog_entry.get("notes", ""),
        "last_reviewed": catalog_entry["last_reviewed"],
        "catalog_age_days": age_days,
        "model_matches_recommendation": model == recommended_model or model in aliases,
    }


def build_provider_catalog_report(config: Config) -> dict[str, Any]:
    """Compare configured providers against the curated provider catalog."""
    check_cfg = config.provider_catalog_check
    today = date.today()

    tracked = 0
    alerts: list[dict[str, Any]] = []
    items: list[dict[str, Any]] = []

    for provider_name, provider in sorted(config.providers.items()):
        model = str(provider.get("model", "") or "").strip()
        catalog_entry = _CATALOG.get(provider_name)
        item: dict[str, Any] = {
            "provider": provider_name,
            "configured_model": model,
            "tracked": catalog_entry is not None,
        }

        if not catalog_entry:
            item["status"] = "untracked"
            items.append(item)
            if check_cfg.get("enabled") and check_cfg.get("warn_on_untracked"):
                alerts.append(
                    _alert(
                        provider=provider_name,
                        severity="warning",
                        code="untracked-provider",
                        message=(
                            f"Provider '{provider_name}' is not in the curated provider "
                            "catalog yet."
                        ),
                    )
                )
            continue

        tracked += 1
        item = _tracked_item(provider_name, provider, catalog_entry, today=today)
        items.append(item)

        if (
            check_cfg.get("enabled")
            and check_cfg.get("warn_on_model_drift")
            and not item["model_matches_recommendation"]
        ):
            alerts.append(
                _alert(
                    provider=provider_name,
                    severity="warning",
                    code="model-drift",
                    message=(
                        f"Provider '{provider_name}' uses model '{model}', while the curated "
                        f"catalog recommends '{item['recommended_model']}'."
                    ),
                    recommended_model=item["recommended_model"],
                )
            )

        if (
            check_cfg.get("enabled")
            and check_cfg.get("warn_on_unofficial_sources")
            and item["evidence_level"] != "official"
        ):
            alerts.append(
                _alert(
                    provider=provider_name,
                    severity="notice",
                    code="catalog-source-unofficial",
                    message=(
                        f"Catalog guidance for provider '{provider_name}' is backed by "
                        f"{item['evidence_level']} evidence; review the configured "
                        "model more often."
                    ),
                    official_source_url=item["official_source_url"],
                )
            )

        if (
            check_cfg.get("enabled")
            and check_cfg.get("warn_on_volatile_offers")
            and item["volatility"] in {"medium", "high"}
            and item["offer_track"] in {"free", "credit", "byok", "marketplace"}
        ):
            alerts.append(
                _alert(
                    provider=provider_name,
                    severity="notice",
                    code="volatile-offer-configured",
                    message=(
                        f"Provider '{provider_name}' is on the '{item['offer_track']}' track "
                        f"with {item['volatility']} volatility; limits, models, or "
                        "pricing may change quickly."
                    ),
                    offer_track=item["offer_track"],
                )
            )

        max_age_days = int(check_cfg.get("max_catalog_age_days", 30))
        if check_cfg.get("enabled") and item["catalog_age_days"] > max_age_days:
            alerts.append(
                _alert(
                    provider=provider_name,
                    severity="notice",
                    code="catalog-stale",
                    message=(
                        f"Catalog guidance for provider '{provider_name}' is "
                        f"{item['catalog_age_days']} days old."
                    ),
                    last_reviewed=item["last_reviewed"],
                )
            )

    return {
        "enabled": bool(check_cfg.get("enabled")),
        "tracked_providers": tracked,
        "total_providers": len(config.providers),
        "alert_count": len(alerts),
        "recommendation_policy": {
            "affiliate_payout_affects_ranking": False,
            "ranking_basis": [
                "fit",
                "quality",
                "health",
                "capability",
                "cost_behavior",
            ],
            "disclosure": _DISCOVERY_DISCLOSURE,
        },
        "alerts": alerts,
        "items": items,
    }
