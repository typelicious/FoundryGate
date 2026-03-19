"""Curated provider catalog and drift/freshness reporting."""

from __future__ import annotations

from datetime import date
from typing import Any

from .config import Config

_CATALOG: dict[str, dict[str, Any]] = {
    "deepseek-chat": {
        "recommended_model": "deepseek-chat",
        "aliases": ["deepseek-chat"],
        "track": "stable",
        "notes": "Balanced DeepSeek chat default",
        "last_reviewed": "2026-03-19",
    },
    "deepseek-reasoner": {
        "recommended_model": "deepseek-reasoner",
        "aliases": ["deepseek-reasoner"],
        "track": "stable",
        "notes": "Reasoning-heavy DeepSeek path",
        "last_reviewed": "2026-03-19",
    },
    "gemini-flash-lite": {
        "recommended_model": "gemini-2.5-flash-lite",
        "aliases": ["gemini-2.5-flash-lite"],
        "track": "stable",
        "notes": "Cheap Gemini default",
        "last_reviewed": "2026-03-19",
    },
    "gemini-flash": {
        "recommended_model": "gemini-2.5-flash",
        "aliases": ["gemini-2.5-flash"],
        "track": "stable",
        "notes": "Balanced Gemini default",
        "last_reviewed": "2026-03-19",
    },
    "openrouter-fallback": {
        "recommended_model": "openrouter/auto",
        "aliases": ["openrouter/auto"],
        "track": "stable",
        "notes": "Marketplace fallback path",
        "last_reviewed": "2026-03-19",
    },
    "kilocode": {
        "recommended_model": "z-ai/glm-5:free",
        "aliases": ["z-ai/glm-5:free"],
        "track": "free",
        "notes": "Current curated free-tier Kilo model",
        "last_reviewed": "2026-03-19",
    },
    "blackbox-free": {
        "recommended_model": "blackboxai/x-ai/grok-code-fast-1:free",
        "aliases": ["blackboxai/x-ai/grok-code-fast-1:free"],
        "track": "free",
        "notes": "Current curated BLACKBOX free-tier model",
        "last_reviewed": "2026-03-19",
    },
    "openai-gpt4o": {
        "recommended_model": "gpt-4o",
        "aliases": ["gpt-4o"],
        "track": "stable",
        "notes": "Balanced OpenAI multimodal path",
        "last_reviewed": "2026-03-19",
    },
    "openai-images": {
        "recommended_model": "gpt-image-1",
        "aliases": ["gpt-image-1"],
        "track": "stable",
        "notes": "OpenAI image generation and editing",
        "last_reviewed": "2026-03-19",
    },
    "anthropic-claude": {
        "recommended_model": "claude-opus-4-6",
        "aliases": ["claude-opus-4-6"],
        "track": "stable",
        "notes": "Quality-first Anthropic default",
        "last_reviewed": "2026-03-19",
    },
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
                    {
                        "provider": provider_name,
                        "severity": "warning",
                        "code": "untracked-provider",
                        "message": (
                            f"Provider '{provider_name}' is not in the curated provider "
                            "catalog yet."
                        ),
                    }
                )
            continue

        tracked += 1
        recommended_model = str(catalog_entry["recommended_model"])
        aliases = list(catalog_entry.get("aliases", []))
        reviewed_on = date.fromisoformat(catalog_entry["last_reviewed"])
        age_days = (today - reviewed_on).days

        item.update(
            {
                "status": "tracked",
                "recommended_model": recommended_model,
                "track": catalog_entry.get("track", "stable"),
                "notes": catalog_entry.get("notes", ""),
                "last_reviewed": catalog_entry["last_reviewed"],
                "catalog_age_days": age_days,
                "model_matches_recommendation": model == recommended_model or model in aliases,
            }
        )
        items.append(item)

        if (
            check_cfg.get("enabled")
            and check_cfg.get("warn_on_model_drift")
            and not item["model_matches_recommendation"]
        ):
            alerts.append(
                {
                    "provider": provider_name,
                    "severity": "warning",
                    "code": "model-drift",
                    "message": (
                        f"Provider '{provider_name}' uses model '{model}',"
                        f" while the curated catalog recommends '{recommended_model}'."
                    ),
                    "recommended_model": recommended_model,
                }
            )

        max_age_days = int(check_cfg.get("max_catalog_age_days", 30))
        if check_cfg.get("enabled") and age_days > max_age_days:
            alerts.append(
                {
                    "provider": provider_name,
                    "severity": "notice",
                    "code": "catalog-stale",
                    "message": (
                        f"Catalog guidance for provider '{provider_name}' is {age_days} days old."
                    ),
                    "last_reviewed": catalog_entry["last_reviewed"],
                }
            )

    return {
        "enabled": bool(check_cfg.get("enabled")),
        "tracked_providers": tracked,
        "total_providers": len(config.providers),
        "alert_count": len(alerts),
        "alerts": alerts,
        "items": items,
    }
