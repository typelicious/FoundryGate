"""Operator-focused dashboard summaries for fusionAIze Gate."""

# ruff: noqa: E501

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .lane_registry import get_route_add_recommendations
from .metrics import MetricsStore


def _safe_int(value: Any) -> int:
    if value in (None, ""):
        return 0
    return int(value)


def _safe_float(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    return float(value)


def _format_usd(value: float) -> str:
    if value <= 0:
        return "$0.00"
    if value < 0.01:
        return f"${value:.4f}"
    return f"${value:.2f}"


def _format_tokens(value: int) -> str:
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"{value / 1_000:.1f}K"
    return str(value)


def _format_latency_ms(value: float) -> str:
    if value <= 0:
        return "n/a"
    return f"{value:.0f}ms"


def _format_pct(value: float) -> str:
    return f"{value:.1f}%"


def _format_ago(timestamp: float | None) -> str:
    if not timestamp:
        return "never"
    delta = max(0.0, time.time() - timestamp)
    if delta < 60:
        return f"{delta:.0f}s ago"
    if delta < 3600:
        return f"{delta / 60:.0f}m ago"
    if delta < 86400:
        return f"{delta / 3600:.1f}h ago"
    return f"{delta / 86400:.1f}d ago"


def _health_issue_category(last_error: str) -> str:
    lowered = (last_error or "").lower()
    if any(token in lowered for token in ("quota", "insufficient_quota", "billing hard limit")):
        return "quota-exhausted"
    if any(token in lowered for token in ("429", "rate limit", "rate-limit", "too many requests")):
        return "rate-limited"
    if any(token in lowered for token in ("model", "not found", "unsupported")):
        return "model-unavailable"
    return "unhealthy"


def _readiness_category(status: str) -> str:
    normalized = str(status or "").strip().lower()
    if normalized in {"ready", "ready-verified"}:
        return "ready"
    if normalized in {"ready-compat"}:
        return "compat"
    return "degraded"


def _client_highlights(client_totals: list[dict[str, Any]]) -> dict[str, dict[str, Any] | None]:
    if not client_totals:
        return {
            "top_requests": None,
            "top_tokens": None,
            "top_cost": None,
            "highest_failure_rate": None,
            "slowest_client": None,
        }

    rows = list(client_totals)
    failure_rows = [row for row in rows if _safe_int(row.get("failures")) > 0]
    return {
        "top_requests": max(
            rows,
            key=lambda row: (_safe_int(row.get("requests")), _safe_int(row.get("total_tokens"))),
        ),
        "top_tokens": max(
            rows,
            key=lambda row: (_safe_int(row.get("total_tokens")), _safe_int(row.get("requests"))),
        ),
        "top_cost": max(
            rows, key=lambda row: (_safe_float(row.get("cost_usd")), _safe_int(row.get("requests")))
        ),
        "highest_failure_rate": (
            max(
                failure_rows,
                key=lambda row: (
                    -_safe_float(row.get("success_pct") or 0),
                    _safe_int(row.get("failures")),
                    _safe_int(row.get("requests")),
                ),
            )
            if failure_rows
            else None
        ),
        "slowest_client": max(
            rows,
            key=lambda row: (
                _safe_float(row.get("avg_latency_ms")),
                _safe_int(row.get("requests")),
            ),
        ),
    }


def _inventory_provider_map(inventory_payload: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    rows = (inventory_payload or {}).get("providers") or []
    provider_map: dict[str, dict[str, Any]] = {}
    for row in rows:
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        provider_map[name] = row if isinstance(row, dict) else {}
    return provider_map


def _routing_path_summary(routing_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    totals: dict[str, dict[str, Any]] = {}
    for row in routing_rows:
        selection_path = str(row.get("selection_path") or "").strip()
        if not selection_path:
            continue
        bucket = totals.setdefault(
            selection_path,
            {"selection_path": selection_path, "requests": 0, "cost_usd": 0.0},
        )
        bucket["requests"] += _safe_int(row.get("requests"))
        bucket["cost_usd"] += _safe_float(row.get("cost_usd"))
    return sorted(
        totals.values(),
        key=lambda row: (row["requests"], row["cost_usd"]),
        reverse=True,
    )


def _request_readiness_breakdown(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"ready": 0, "compat": 0, "degraded": 0}
    for row in rows:
        request_readiness = row.get("request_readiness") or {}
        category = _readiness_category(str(request_readiness.get("status") or "degraded"))
        counts[category] = counts.get(category, 0) + 1
    return counts


def _lane_family_summary(
    provider_rows: list[dict[str, Any]],
    provider_map: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    metric_rows_by_provider = {
        str(row.get("provider") or ""): row
        for row in provider_rows
        if str(row.get("provider") or "")
    }
    source_rows: list[dict[str, Any]] = []
    if provider_map:
        for provider_name, inventory_row in provider_map.items():
            metrics_row = dict(metric_rows_by_provider.get(provider_name) or {})
            source_rows.append(
                {
                    "provider": provider_name,
                    "requests": _safe_int(metrics_row.get("requests")),
                    "cost_usd": _safe_float(metrics_row.get("cost_usd")),
                    "lane": dict((inventory_row or {}).get("lane") or {}),
                    "request_readiness": dict((inventory_row or {}).get("request_readiness") or {}),
                    "route_runtime_state": dict(
                        (inventory_row or {}).get("route_runtime_state") or {}
                    ),
                }
            )
    else:
        source_rows = list(provider_rows)

    families: dict[str, dict[str, Any]] = {}
    for row in source_rows:
        lane = dict(row.get("lane") or {})
        family = str(lane.get("family") or "unclassified")
        readiness = dict(row.get("request_readiness") or {})
        runtime_state = dict(row.get("route_runtime_state") or {})
        bucket = families.setdefault(
            family,
            {
                "family": family,
                "providers": 0,
                "requests": 0,
                "cost_usd": 0.0,
                "ready": 0,
                "compat": 0,
                "degraded": 0,
                "cooldown": 0,
                "recovered": 0,
            },
        )
        bucket["providers"] += 1
        bucket["requests"] += _safe_int(row.get("requests"))
        bucket["cost_usd"] += _safe_float(row.get("cost_usd"))
        bucket[_readiness_category(str(readiness.get("status") or "degraded"))] += 1
        if str(runtime_state.get("window_state") or "") == "cooldown":
            bucket["cooldown"] += 1
        if bool(runtime_state.get("recovered_recently")):
            bucket["recovered"] += 1
    return sorted(
        families.values(),
        key=lambda row: (row["requests"], row["providers"], row["cost_usd"]),
        reverse=True,
    )


def _lane_family_summary_from_stats(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not rows:
        return []
    normalized: list[dict[str, Any]] = []
    for row in rows:
        normalized.append(
            {
                "family": str(row.get("lane_family") or "unclassified"),
                "providers": _safe_int(row.get("providers")),
                "requests": _safe_int(row.get("requests")),
                "cost_usd": _safe_float(row.get("cost_usd")),
                "cooldown": _safe_int(row.get("cooldown_requests")),
                "degraded": _safe_int(row.get("degraded_requests")),
                "recovered": _safe_int(row.get("recovered_requests")),
                "selection_paths": str(row.get("selection_paths") or ""),
            }
        )
    return normalized


def _selection_path_summary_from_stats(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not rows:
        return []
    normalized: list[dict[str, Any]] = []
    for row in rows:
        normalized.append(
            {
                "selection_path": str(row.get("selection_path") or ""),
                "lane_family": str(row.get("lane_family") or ""),
                "runtime_window_state": str(row.get("runtime_window_state") or ""),
                "recovered_recently": bool(row.get("recovered_recently")),
                "requests": _safe_int(row.get("requests")),
                "cost_usd": _safe_float(row.get("cost_usd")),
                "avg_latency_ms": _safe_float(row.get("avg_latency_ms")),
            }
        )
    return normalized


def _render_lane_family_block(report: dict[str, Any], *, limit: int = 3) -> list[str]:
    rows = report.get("lane_families") or []
    if not rows:
        return []
    lines = ["Lane families"]
    for row in rows[:limit]:
        lines.append(
            f"- {row.get('family')}: {_safe_int(row.get('providers'))} routes | "
            f"{_safe_int(row.get('requests'))} req | cooldown={_safe_int(row.get('cooldown'))} | "
            f"recovery={_safe_int(row.get('recovered'))}"
        )
    return lines


def _render_route_add_block(report: dict[str, Any], *, limit: int = 3) -> list[str]:
    rows = report.get("route_additions") or []
    if not rows:
        return []
    lines = ["Route additions"]
    for row in rows[:limit]:
        lines.append(
            f"- {row.get('family')}: add {row.get('add_provider')} "
            f"({row.get('strategy')}) to strengthen {row.get('canonical_model') or 'the lane'}"
        )
    return lines


def _render_selection_path_block(report: dict[str, Any], *, limit: int = 4) -> list[str]:
    rows = report.get("selection_paths") or []
    if not rows:
        return []
    lines = ["Selection paths"]
    for row in rows[:limit]:
        bits: list[str] = []
        if row.get("lane_family"):
            bits.append(str(row.get("lane_family")))
        if row.get("runtime_window_state"):
            bits.append(str(row.get("runtime_window_state")))
        if row.get("recovered_recently"):
            bits.append("recovery-watch")
        suffix = f" [{' | '.join(bits)}]" if bits else ""
        lines.append(
            f"- {row.get('selection_path')}: {_safe_int(row.get('requests'))} req / "
            f"{_format_usd(_safe_float(row.get('cost_usd')))} / "
            f"{_format_latency_ms(_safe_float(row.get('avg_latency_ms')))}{suffix}"
        )
    return lines


def _enrich_provider_rows_with_lane(
    rows: list[dict[str, Any]],
    provider_map: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    configured_provider_names = set(provider_map.keys()) or {
        str(row.get("provider") or "") for row in rows if str(row.get("provider") or "")
    }
    enriched: list[dict[str, Any]] = []
    for row in rows:
        provider_name = str(row.get("provider") or "")
        provider_inventory = dict(provider_map.get(provider_name) or {})
        lane = dict(provider_inventory.get("lane") or {})
        add_recommendations = get_route_add_recommendations(
            configured_provider_names=configured_provider_names,
            canonical_model=str(lane.get("canonical_model") or ""),
            degrade_to=[str(item) for item in (lane.get("degrade_to") or []) if str(item)],
            family=str(lane.get("family") or ""),
        )
        enriched.append(
            {
                **row,
                "lane": lane,
                "canonical_model": str(lane.get("canonical_model") or ""),
                "lane_family": str(lane.get("family") or ""),
                "lane_name": str(lane.get("name") or ""),
                "route_type": str(lane.get("route_type") or ""),
                "lane_cluster": str(lane.get("cluster") or ""),
                "benchmark_cluster": str(lane.get("benchmark_cluster") or ""),
                "cost_tier": str(
                    ((provider_inventory.get("capabilities") or {}).get("cost_tier"))
                    or lane.get("quality_tier")
                    or ""
                ),
                "transport": dict(provider_inventory.get("transport") or {}),
                "request_readiness": dict(provider_inventory.get("request_readiness") or {}),
                "route_runtime_state": dict(provider_inventory.get("route_runtime_state") or {}),
                "route_add_recommendations": add_recommendations,
                "recommended_add_provider": (
                    str(add_recommendations[0].get("provider_name") or "")
                    if add_recommendations
                    else ""
                ),
                "recommended_add_strategy": (
                    str(add_recommendations[0].get("strategy") or "") if add_recommendations else ""
                ),
            }
        )
    return enriched


def _route_add_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    totals: dict[str, dict[str, Any]] = {}
    for row in rows:
        family = str(row.get("lane_family") or "unclassified")
        add_provider = str(row.get("recommended_add_provider") or "")
        if not add_provider:
            continue
        bucket = totals.setdefault(
            family,
            {
                "family": family,
                "providers": 0,
                "top_provider": str(row.get("provider") or ""),
                "add_provider": add_provider,
                "strategy": str(row.get("recommended_add_strategy") or ""),
                "canonical_model": str(row.get("canonical_model") or ""),
            },
        )
        bucket["providers"] += 1
    return sorted(
        totals.values(),
        key=lambda row: (row["providers"], row["family"]),
        reverse=True,
    )


def _provider_routing_fit(row: dict[str, Any]) -> str:
    benchmark_cluster = str(row.get("benchmark_cluster") or "")
    cost_tier = str(row.get("cost_tier") or "")
    route_type = str(row.get("route_type") or "")
    if benchmark_cluster and cost_tier:
        return f"{benchmark_cluster} with a {cost_tier} cost posture over {route_type or 'default'} routing"
    if benchmark_cluster:
        return f"{benchmark_cluster} over {route_type or 'default'} routing"
    if cost_tier:
        return f"{cost_tier} cost posture over {route_type or 'default'} routing"
    return route_type or "n/a"


def _recommended_scenario_for_client(client_profile: str, *, expensive: bool = False) -> str | None:
    mapping = {
        "opencode": "opencode-eco" if expensive else "opencode-balanced",
        "openclaw": "openclaw-balanced",
        "n8n": "n8n-eco" if expensive else "n8n-reliable",
        "cli": "cli-free" if expensive else "cli-balanced",
    }
    return mapping.get(client_profile)


def _stats_from_db(db_path: str) -> dict[str, Any]:
    path = Path(db_path)
    if not path.exists():
        return {
            "totals": {},
            "providers": [],
            "routing": [],
            "clients": [],
            "client_totals": [],
            "client_highlights": _client_highlights([]),
            "operator_actions": [],
            "hourly": [],
            "daily": [],
        }

    metrics = MetricsStore(str(path))
    metrics.init()
    try:
        client_totals = metrics.get_client_totals()
        return {
            "totals": metrics.get_totals(),
            "providers": metrics.get_provider_summary(),
            "routing": metrics.get_routing_breakdown(),
            "clients": metrics.get_client_breakdown(),
            "client_totals": client_totals,
            "client_highlights": _client_highlights(client_totals),
            "operator_actions": metrics.get_operator_breakdown(),
            "hourly": metrics.get_hourly_series(24),
            "daily": metrics.get_daily_totals(30),
        }
    finally:
        metrics.close()


def build_dashboard_report(
    *,
    db_path: str,
    stats_payload: dict[str, Any] | None = None,
    health_payload: dict[str, Any] | None = None,
    inventory_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one operator-facing dashboard report from live or local metrics."""
    stats = stats_payload or _stats_from_db(db_path)
    source_mode = "live-api" if stats_payload else "db-only"
    if not stats.get("totals"):
        source_mode = "empty"

    totals = stats.get("totals") or {}
    inventory_provider_map = _inventory_provider_map(inventory_payload)
    providers = _enrich_provider_rows_with_lane(
        stats.get("providers") or [], inventory_provider_map
    )
    route_additions = _route_add_summary(providers)
    lane_families = _lane_family_summary_from_stats(stats.get("lane_families") or [])
    if not lane_families:
        lane_families = _lane_family_summary(providers, inventory_provider_map)
    selection_paths = _selection_path_summary_from_stats(stats.get("selection_paths") or [])
    readiness_breakdown = _request_readiness_breakdown(
        list(inventory_provider_map.values()) if inventory_provider_map else providers
    )
    routing = stats.get("routing") or []
    routing_paths = _routing_path_summary(routing)
    client_totals = stats.get("client_totals") or []
    client_highlights = stats.get("client_highlights") or _client_highlights(client_totals)
    daily = stats.get("daily") or []
    hourly = stats.get("hourly") or []
    operator_actions = stats.get("operator_actions") or []

    total_requests = _safe_int(totals.get("total_requests"))
    total_failures = _safe_int(totals.get("total_failures"))
    success_pct = (
        ((total_requests - total_failures) * 100.0 / total_requests) if total_requests else 100.0
    )
    total_prompt_tokens = _safe_int(totals.get("total_prompt_tokens"))
    total_completion_tokens = _safe_int(totals.get("total_compl_tokens"))
    total_cost = _safe_float(totals.get("total_cost_usd"))
    avg_latency_ms = _safe_float(totals.get("avg_latency_ms"))

    fallback_requests = sum(
        _safe_int(item.get("requests"))
        for item in routing
        if str(item.get("layer") or "") == "fallback"
    )
    fallback_pct = (fallback_requests * 100.0 / total_requests) if total_requests else 0.0

    top_provider = max(
        providers,
        key=lambda row: (_safe_int(row.get("requests")), _safe_float(row.get("cost_usd"))),
        default=None,
    )
    top_provider_cost = max(
        providers,
        key=lambda row: (_safe_float(row.get("cost_usd")), _safe_int(row.get("requests"))),
        default=None,
    )

    total_cost_days = [
        _safe_float(day.get("cost_usd"))
        for day in daily
        if any(_safe_int(day.get(key)) for key in ("requests", "tokens", "failures"))
        or _safe_float(day.get("cost_usd"))
    ]
    avg_daily_cost = (sum(total_cost_days) / len(total_cost_days)) if total_cost_days else 0.0
    projected_monthly_cost = avg_daily_cost * 30 if total_cost_days else 0.0

    last_request = totals.get("last_request")
    first_request = totals.get("first_request")
    requests_24h = sum(_safe_int(row.get("requests")) for row in hourly)
    tokens_24h = sum(_safe_int(row.get("tokens")) for row in hourly)
    cost_24h = sum(_safe_float(row.get("cost_usd")) for row in hourly)

    healthy_provider_names: list[str] = []
    healthy_provider_tiers: dict[str, str] = {}
    unhealthy_providers: list[dict[str, str]] = []
    if health_payload:
        health_providers = health_payload.get("providers") or {}
        for provider_name, payload in health_providers.items():
            if payload.get("healthy"):
                healthy_provider_names.append(provider_name)
                healthy_provider_tiers[provider_name] = str(payload.get("tier") or "")
            else:
                unhealthy_providers.append(
                    {
                        "provider": provider_name,
                        "category": _health_issue_category(str(payload.get("last_error") or "")),
                        "detail": str(payload.get("last_error") or "").strip()
                        or "No error detail provided",
                    }
                )

    alerts: list[dict[str, str]] = []
    hints: list[str] = []
    decision_support: list[str] = []

    if health_payload:
        health_summary = health_payload.get("summary") or {}
        unhealthy_count = _safe_int(health_summary.get("providers_unhealthy"))
        total_health_providers = _safe_int(health_summary.get("providers_total"))
        readiness_summary = (health_payload or {}).get("request_readiness") or {}
        providers_request_ready = _safe_int(readiness_summary.get("providers_ready"))
        providers_request_not_ready = _safe_int(readiness_summary.get("providers_not_ready"))
        if unhealthy_count:
            preview = ", ".join(item["provider"] for item in unhealthy_providers[:3])
            suffix = "" if unhealthy_count <= 3 else f" +{unhealthy_count - 3} more"
            alerts.append(
                {
                    "level": "warning",
                    "headline": "One or more live providers are unhealthy",
                    "detail": f"{preview}{suffix} currently look degraded out of {total_health_providers} health-checked providers.",
                    "suggestion": "Run Provider Probe next, then review provider-specific errors before routing more traffic there.",
                }
            )
        if providers_request_not_ready:
            alerts.append(
                {
                    "level": "warning",
                    "headline": "Some provider routes are not request-ready",
                    "detail": (
                        f"{providers_request_ready}/{total_health_providers} provider routes look request-ready "
                        f"while {providers_request_not_ready} still need attention."
                    ),
                    "suggestion": "Run Provider Probe or Doctor next to isolate missing keys, auth failures, endpoint mismatches, or quota pressure before live routing.",
                }
            )
        if readiness_breakdown.get("compat"):
            hints.append(
                f"{readiness_breakdown['compat']} provider routes are request-ready via compatibility profiles rather than native transport profiles."
            )

    if total_requests == 0:
        alerts.append(
            {
                "level": "info",
                "headline": "No request traffic has been recorded yet",
                "detail": "The gateway is up, but the metrics store has not seen any routed client requests yet.",
                "suggestion": "Connect one client and send a small live request to turn the dashboard into an operational view.",
            }
        )
    elif success_pct < 95.0:
        alerts.append(
            {
                "level": "warning",
                "headline": "Failure rate is high enough to watch closely",
                "detail": f"Success is {_format_pct(success_pct)} across {total_requests} requests.",
                "suggestion": "Open Providers and Clients to isolate the unstable path before sending more production traffic.",
            }
        )
    elif total_failures > 0:
        alerts.append(
            {
                "level": "info",
                "headline": "Some requests have failed recently",
                "detail": f"{total_failures} requests have failed so far, even though the overall success rate is {_format_pct(success_pct)}.",
                "suggestion": "Check the top clients and providers before the failure pattern grows.",
            }
        )

    if fallback_pct >= 20.0:
        alerts.append(
            {
                "level": "warning",
                "headline": "Fallback routing is carrying a meaningful share of traffic",
                "detail": f"{fallback_requests} requests ({_format_pct(fallback_pct)}) have gone through fallback routing.",
                "suggestion": "Consider raising budget or priority for primary providers if this should not be the normal steady state.",
            }
        )
    elif fallback_requests:
        hints.append(
            f"Fallback routing has handled {fallback_requests} requests so far ({_format_pct(fallback_pct)} of total traffic)."
        )

    if routing_paths:
        top_path = routing_paths[0]
        hints.append(
            "Actual attempt path most often seen so far: "
            + f"{top_path['selection_path']} ({top_path['requests']} requests)."
        )

    if last_request and (time.time() - float(last_request)) > 12 * 3600:
        alerts.append(
            {
                "level": "info",
                "headline": "Traffic is stale",
                "detail": f"The last recorded request was {_format_ago(float(last_request))}.",
                "suggestion": "Send one real client request before making spend or health decisions from old traffic.",
            }
        )

    if top_provider_cost and total_cost > 0:
        dominant_cost_share = (
            (_safe_float(top_provider_cost.get("cost_usd")) * 100.0 / total_cost)
            if total_cost
            else 0.0
        )
        if dominant_cost_share >= 60.0:
            hints.append(
                f"Most spend currently lands on {top_provider_cost.get('provider')} ({_format_pct(dominant_cost_share)} of total cost)."
            )
            cheaper_healthy = [
                name
                for name, tier in healthy_provider_tiers.items()
                if tier in {"cheap", "default", "fallback"}
                and name != str(top_provider_cost.get("provider") or "")
            ]
            if cheaper_healthy:
                decision_support.append(
                    "Budget hint: consider moving more general traffic toward "
                    + ", ".join(cheaper_healthy[:3])
                    + " before increasing spend on the current top-cost provider."
                )
        top_lane = str(top_provider_cost.get("canonical_model") or "")
        top_route = str(top_provider_cost.get("route_type") or "")
        if top_lane:
            hints.append(
                f"Top-cost lane right now: {top_lane}"
                + (f" via {top_route}" if top_route else "")
                + "."
            )

    rate_limited = [
        item["provider"] for item in unhealthy_providers if item["category"] == "rate-limited"
    ]
    quota_exhausted = [
        item["provider"] for item in unhealthy_providers if item["category"] == "quota-exhausted"
    ]
    if rate_limited:
        decision_support.append(
            "Rate-limit pressure: "
            + ", ".join(rate_limited[:3])
            + " currently look saturated. More budget, lower concurrency, or a stronger secondary path may help."
        )
    if quota_exhausted:
        decision_support.append(
            "Quota pressure: "
            + ", ".join(quota_exhausted[:3])
            + " appear quota-exhausted. Budget or quota changes are likely needed before those paths recover."
        )

    if healthy_provider_names:
        hints.append(
            f"Healthy providers right now: {', '.join(healthy_provider_names[:4])}"
            + (
                ""
                if len(healthy_provider_names) <= 4
                else f" +{len(healthy_provider_names) - 4} more"
            )
        )
    elif health_payload:
        hints.append("No healthy providers are currently reported by /health.")

    top_cost_client = client_highlights.get("top_cost")
    if top_cost_client:
        top_cost_client_name = str(
            top_cost_client.get("client_tag") or top_cost_client.get("client_profile") or "generic"
        )
        top_cost_client_profile = str(top_cost_client.get("client_profile") or "generic")
        cost_per_request = _safe_float(top_cost_client.get("cost_per_request_usd"))
        suggested_scenario = _recommended_scenario_for_client(
            top_cost_client_profile,
            expensive=cost_per_request >= 0.03,
        )
        if suggested_scenario:
            decision_support.append(
                f"Client hint: {top_cost_client_name} is the highest-spend client right now. Review {suggested_scenario} if you want a cheaper default posture."
            )

    hints.append(
        "Provider-specific quota reset windows are not available yet; today the dashboard can only infer quota or rate-limit pressure from live errors."
    )

    if lane_families:
        top_family = lane_families[0]
        hints.append(
            "Top lane family right now: "
            + f"{top_family['family']} ({top_family['providers']} routes, "
            + f"{top_family['requests']} requests)."
        )
        family_cooldowns = sum(_safe_int(item.get("cooldown")) for item in lane_families)
        family_recoveries = sum(_safe_int(item.get("recovered")) for item in lane_families)
        if family_cooldowns:
            decision_support.append(
                f"{family_cooldowns} route(s) are currently in cooldown across all lane families. "
                "Keep primary traffic on healthier siblings until those windows close."
            )
        if family_recoveries:
            hints.append(
                f"{family_recoveries} route(s) are currently under recovery watch across the live lane families."
            )
    if route_additions:
        top_addition = route_additions[0]
        decision_support.append(
            f"Add-provider hint: add {top_addition['add_provider']} "
            f"as a {top_addition['strategy']} for {top_addition['family']} traffic."
        )

    return {
        "source": {
            "mode": source_mode,
            "db_path": db_path,
            "live_health": bool(health_payload),
            "live_stats": bool(stats_payload),
            "live_inventory": bool(inventory_payload),
        },
        "totals": totals,
        "health": health_payload or {},
        "providers": providers,
        "lane_families": lane_families,
        "route_additions": route_additions,
        "clients": client_totals,
        "routing": routing,
        "routing_paths": routing_paths,
        "selection_paths": selection_paths,
        "daily": daily,
        "hourly": hourly,
        "operator_actions": operator_actions,
        "client_highlights": client_highlights,
        "decision_support": decision_support,
        "cards": {
            "traffic": {
                "requests": total_requests,
                "success_pct": round(success_pct, 1),
                "avg_latency_ms": round(avg_latency_ms, 1),
                "last_request_ago": _format_ago(float(last_request)) if last_request else "never",
                "first_request_ago": _format_ago(float(first_request))
                if first_request
                else "never",
            },
            "spend": {
                "total_cost_usd": round(total_cost, 6),
                "projected_monthly_cost_usd": round(projected_monthly_cost, 6),
                "prompt_tokens": total_prompt_tokens,
                "completion_tokens": total_completion_tokens,
            },
            "health": {
                "status": (health_payload or {}).get("status")
                or ("live" if health_payload else "unknown"),
                "providers_healthy": _safe_int(
                    ((health_payload or {}).get("summary") or {}).get("providers_healthy")
                ),
                "providers_total": _safe_int(
                    ((health_payload or {}).get("summary") or {}).get("providers_total")
                ),
                "providers_request_ready": _safe_int(
                    ((health_payload or {}).get("request_readiness") or {}).get("providers_ready")
                ),
                "providers_request_not_ready": _safe_int(
                    ((health_payload or {}).get("request_readiness") or {}).get(
                        "providers_not_ready"
                    )
                ),
                "providers_request_ready_compat": readiness_breakdown.get("compat", 0),
                "unhealthy": unhealthy_providers,
            },
            "lane_families": {
                "cooldown_routes": sum(_safe_int(item.get("cooldown")) for item in lane_families),
                "recovered_routes": sum(_safe_int(item.get("recovered")) for item in lane_families),
                "route_additions": len(route_additions),
            },
            "drivers": {
                "top_provider": top_provider,
                "top_cost_provider": top_provider_cost,
                "top_client": client_highlights.get("top_requests"),
                "fallback_requests": fallback_requests,
                "fallback_pct": round(fallback_pct, 1),
                "requests_24h": requests_24h,
                "tokens_24h": tokens_24h,
                "cost_24h": round(cost_24h, 6),
            },
        },
        "alerts": alerts,
        "hints": hints,
    }


def _render_overview(report: dict[str, Any]) -> str:
    cards = report["cards"]
    top_provider = cards["drivers"]["top_provider"]
    top_client = cards["drivers"]["top_client"]
    lines = [
        "fusionAIze Gate Dashboard",
        "",
        f"Source: {report['source']['mode']} ({'live /health available' if report['source']['live_health'] else 'using local metrics only'})",
        "",
        "Global",
        f"  Requests            {cards['traffic']['requests']}",
        f"  Success             {_format_pct(cards['traffic']['success_pct'])}",
        f"  Avg latency         {_format_latency_ms(cards['traffic']['avg_latency_ms'])}",
        f"  Last request        {cards['traffic']['last_request_ago']}",
        "",
        "Spend + Tokens",
        f"  Cost total          {_format_usd(_safe_float(cards['spend']['total_cost_usd']))}",
        f"  Projected month     {_format_usd(_safe_float(cards['spend']['projected_monthly_cost_usd']))}",
        f"  Prompt tokens       {_format_tokens(_safe_int(cards['spend']['prompt_tokens']))}",
        f"  Completion tokens   {_format_tokens(_safe_int(cards['spend']['completion_tokens']))}",
        "",
        "Confidence",
        f"  Live providers      {cards['health']['providers_healthy']}/{cards['health']['providers_total']} healthy"
        if report["source"]["live_health"]
        else "  Live providers      unavailable (runtime health not reachable)",
        (
            f"  Request-ready       {cards['health']['providers_request_ready']}/{cards['health']['providers_total']} ready"
            if report["source"]["live_health"]
            else "  Request-ready       unavailable (runtime health not reachable)"
        ),
        (
            f"  Compat routes       {cards['health']['providers_request_ready_compat']} compatibility-backed"
            if report["source"]["live_health"]
            else "  Compat routes       unavailable (runtime health not reachable)"
        ),
        f"  Fallback traffic    {cards['drivers']['fallback_requests']} requests ({_format_pct(_safe_float(cards['drivers']['fallback_pct']))})",
        f"  24h activity        {cards['drivers']['requests_24h']} requests / {_format_usd(_safe_float(cards['drivers']['cost_24h']))} / {_format_tokens(_safe_int(cards['drivers']['tokens_24h']))}",
        "",
        "Traffic drivers",
        f"  Top provider        {top_provider.get('provider')} ({top_provider.get('requests')} req, {_format_usd(_safe_float(top_provider.get('cost_usd')))})"
        if top_provider
        else "  Top provider        no traffic yet",
        (
            f"  Route fit           {_provider_routing_fit(top_provider)}"
            if top_provider
            else "  Route fit           n/a"
        ),
        f"  Top client          {top_client.get('client_tag') or top_client.get('client_profile')} ({top_client.get('requests')} req, {_format_usd(_safe_float(top_client.get('cost_usd')))})"
        if top_client
        else "  Top client          no traffic yet",
    ]
    lane_families = report.get("lane_families") or []
    if lane_families:
        top_family = lane_families[0]
        lines.extend(
            [
                "",
                "Lane families",
                f"  Top family         {top_family.get('family')} ({_safe_int(top_family.get('providers'))} routes / {_safe_int(top_family.get('requests'))} req)",
                f"  Cooldown routes    {_safe_int(report['cards']['lane_families']['cooldown_routes'])}",
                f"  Recovery watch     {_safe_int(report['cards']['lane_families']['recovered_routes'])}",
                f"  Add opportunities  {_safe_int(report['cards']['lane_families']['route_additions'])}",
            ]
        )
        route_additions = report.get("route_additions") or []
        if route_additions:
            top_addition = route_additions[0]
            lines.append(
                f"  Next add           {top_addition.get('add_provider')} ({top_addition.get('strategy')})"
            )
    if report["alerts"]:
        alert = report["alerts"][0]
        lines.extend(
            [
                "",
                "Top alert",
                f"  {alert['headline']}",
                f"  {alert['detail']}",
            ]
        )
    elif report["hints"]:
        lines.extend(["", "Operator note", f"  {report['hints'][0]}"])
    if report["decision_support"]:
        lines.extend(["", "Decision support", f"  {report['decision_support'][0]}"])
    return "\n".join(lines) + "\n"


def _render_providers(report: dict[str, Any]) -> str:
    lines = ["fusionAIze Gate Dashboard", "", "Providers"]
    rows = report["providers"][:8]
    unhealthy = {item["provider"]: item for item in report["cards"]["health"]["unhealthy"]}
    if not rows:
        lines.append("  No provider traffic has been recorded yet.")
    for row in rows:
        provider = str(row.get("provider") or "unknown")
        status = "live-healthy"
        if provider in unhealthy:
            status = unhealthy[provider]["category"]
        elif report["source"]["live_health"] and report["cards"]["health"]["providers_total"] == 0:
            status = "health-unavailable"
        lines.extend(
            [
                f"- {provider} [{status}]",
                (
                    "  lane: "
                    + row.get("canonical_model")
                    + (f" | route: {row.get('route_type')}" if row.get("route_type") else "")
                    + (f" | cluster: {row.get('lane_cluster')}" if row.get("lane_cluster") else "")
                )
                if row.get("canonical_model")
                else "  lane: n/a",
                "  request-ready: "
                + (
                    f"{(row.get('request_readiness') or {}).get('status')} | {(row.get('request_readiness') or {}).get('reason')}"
                    if row.get("request_readiness")
                    else "n/a"
                ),
                (
                    "  transport: "
                    + f"{(row.get('transport') or {}).get('profile') or 'n/a'}"
                    + (
                        f" | {(row.get('transport') or {}).get('compatibility')}"
                        if (row.get("transport") or {}).get("compatibility")
                        else ""
                    )
                    + (
                        f" | confidence: {(row.get('transport') or {}).get('probe_confidence')}"
                        if (row.get("transport") or {}).get("probe_confidence")
                        else ""
                    )
                ),
                f"  requests: {_safe_int(row.get('requests'))} | failures: {_safe_int(row.get('failures'))} | success: {_format_pct(100.0 - (_safe_int(row.get('failures')) * 100.0 / max(1, _safe_int(row.get('requests')))))}",
                f"  cost: {_format_usd(_safe_float(row.get('cost_usd')))} | latency: {_format_latency_ms(_safe_float(row.get('avg_latency_ms')))} | tokens: {_format_tokens(_safe_int(row.get('total_tokens')))}",
            ]
        )
        if provider in unhealthy:
            lines.append(f"  live issue: {unhealthy[provider]['detail']}")
        lines.append("")
    if report["hints"]:
        lines.append("Operator hints")
        for hint in report["hints"][:3]:
            lines.append(f"- {hint}")
    family_block = _render_lane_family_block(report)
    if family_block:
        lines.append("")
        lines.extend(family_block)
    route_add_block = _render_route_add_block(report)
    if route_add_block:
        lines.append("")
        lines.extend(route_add_block)
    if report["decision_support"]:
        lines.append("")
        lines.append("Budget + routing hints")
        for hint in report["decision_support"][:3]:
            lines.append(f"- {hint}")
    return "\n".join(lines).rstrip() + "\n"


def _render_clients(report: dict[str, Any]) -> str:
    lines = ["fusionAIze Gate Dashboard", "", "Clients"]
    rows = report["clients"][:8]
    if not rows:
        lines.append("  No client traffic has been recorded yet.")
    for row in rows:
        client_name = str(row.get("client_tag") or row.get("client_profile") or "generic")
        lines.extend(
            [
                f"- {client_name}",
                f"  profile: {row.get('client_profile') or 'generic'} | requests: {_safe_int(row.get('requests'))} | success: {_format_pct(_safe_float(row.get('success_pct') or 0))}",
                f"  cost: {_format_usd(_safe_float(row.get('cost_usd')))} | latency: {_format_latency_ms(_safe_float(row.get('avg_latency_ms')))} | tokens: {_format_tokens(_safe_int(row.get('total_tokens')))}",
                f"  providers: {row.get('providers') or 'n/a'}",
                "",
            ]
        )
    highlights = report["client_highlights"] or {}
    top_cost = highlights.get("top_cost")
    slowest = highlights.get("slowest_client")
    if top_cost or slowest:
        lines.append("Decision support")
        if top_cost:
            lines.append(
                f"- Highest-spend client right now: {(top_cost.get('client_tag') or top_cost.get('client_profile'))} at {_format_usd(_safe_float(top_cost.get('cost_usd')))} total."
            )
        if slowest:
            lines.append(
                f"- Slowest client path right now: {(slowest.get('client_tag') or slowest.get('client_profile'))} at {_format_latency_ms(_safe_float(slowest.get('avg_latency_ms')))} average latency."
            )
    for hint in report["decision_support"][:2]:
        lines.append(f"- {hint}")
    return "\n".join(lines).rstrip() + "\n"


def _render_activity(report: dict[str, Any]) -> str:
    lines = ["fusionAIze Gate Dashboard", "", "Activity"]
    lines.extend(
        [
            f"24h requests: {report['cards']['drivers']['requests_24h']}",
            f"24h tokens: {_format_tokens(_safe_int(report['cards']['drivers']['tokens_24h']))}",
            f"24h cost: {_format_usd(_safe_float(report['cards']['drivers']['cost_24h']))}",
            "",
            "Recent daily trend",
        ]
    )
    daily_rows = report["daily"][-7:]
    if not daily_rows:
        lines.append("  No daily history yet.")
    for row in daily_rows:
        lines.append(
            f"- {row.get('day')}: {_safe_int(row.get('requests'))} req | {_format_usd(_safe_float(row.get('cost_usd')))} | {_format_tokens(_safe_int(row.get('tokens')))} | {_safe_int(row.get('failures'))} fail"
        )
    family_block = _render_lane_family_block(report)
    if family_block:
        lines.append("")
        lines.extend(family_block)
    route_add_block = _render_route_add_block(report)
    if route_add_block:
        lines.append("")
        lines.extend(route_add_block)
    path_block = _render_selection_path_block(report)
    if path_block:
        lines.append("")
        lines.extend(path_block)
    lines.append("")
    lines.append("Operator actions")
    operator_rows = report["operator_actions"][:5]
    if not operator_rows:
        lines.append("  No operator actions have been recorded yet.")
    for row in operator_rows:
        status = row.get("status") or "n/a"
        update_type = row.get("update_type") or "n/a"
        lines.append(
            f"- {row.get('action') or row.get('event_type')}: {row.get('events')} events | status={status} | update_type={update_type}"
        )
    return "\n".join(lines).rstrip() + "\n"


def _render_alerts(report: dict[str, Any]) -> str:
    lines = ["fusionAIze Gate Dashboard", "", "Alerts + Decision Support"]
    if not report["alerts"]:
        lines.append("No active operator alerts right now.")
    for alert in report["alerts"]:
        lines.extend(
            [
                f"- [{alert['level']}] {alert['headline']}",
                f"  detail: {alert['detail']}",
                f"  next: {alert['suggestion']}",
                "",
            ]
        )
    lines.append("Context")
    family_block = _render_lane_family_block(report)
    if family_block:
        lines.extend(family_block)
    route_add_block = _render_route_add_block(report)
    if route_add_block:
        lines.extend(route_add_block)
    for hint in report["hints"][:5]:
        lines.append(f"- {hint}")
    path_block = _render_selection_path_block(report)
    if path_block:
        lines.extend(path_block)
    for hint in report["decision_support"][:5]:
        lines.append(f"- {hint}")
    return "\n".join(lines).rstrip() + "\n"


def _render_provider_detail(report: dict[str, Any], provider_name: str) -> str:
    target = provider_name.strip().lower()
    unhealthy = {item["provider"]: item for item in report["cards"]["health"]["unhealthy"]}
    row = next(
        (item for item in report["providers"] if str(item.get("provider") or "").lower() == target),
        None,
    )
    if not row:
        return (
            "fusionAIze Gate Dashboard\n\n"
            f"Provider detail\n\nNo provider row found for '{provider_name}'.\n"
        )

    provider = str(row.get("provider") or provider_name)
    status = "live-healthy"
    if provider in unhealthy:
        status = unhealthy[provider]["category"]

    requests = _safe_int(row.get("requests"))
    failures = _safe_int(row.get("failures"))
    success_pct = 100.0 - (failures * 100.0 / max(1, requests))
    request_readiness = row.get("request_readiness") or {}
    transport = row.get("transport") or {}
    provider_routing_paths = _routing_path_summary(
        [
            item
            for item in report.get("routing") or []
            if str(item.get("provider") or "").strip().lower() == target
        ]
    )
    lines = [
        "fusionAIze Gate Dashboard",
        "",
        f"Provider detail: {provider}",
        "",
        f"Status            {status}",
        f"Requests          {requests}",
        f"Failures          {failures}",
        f"Success           {_format_pct(success_pct)}",
        f"Latency           {_format_latency_ms(_safe_float(row.get('avg_latency_ms')))}",
        f"Cost              {_format_usd(_safe_float(row.get('cost_usd')))}",
        f"Tokens            {_format_tokens(_safe_int(row.get('total_tokens')))}",
        f"Prompt tokens     {_format_tokens(_safe_int(row.get('prompt_tokens')))}",
        f"Completion tokens {_format_tokens(_safe_int(row.get('completion_tokens')))}",
        f"Canonical lane    {row.get('canonical_model') or 'n/a'}",
        f"Route type        {row.get('route_type') or 'n/a'}",
        f"Lane cluster      {row.get('lane_cluster') or 'n/a'}",
        f"Benchmark focus   {row.get('benchmark_cluster') or 'n/a'}",
        f"Cost tier         {row.get('cost_tier') or 'n/a'}",
        f"Routing fit       {_provider_routing_fit(row)}",
        f"Request-ready     {request_readiness.get('status') or 'n/a'}",
    ]
    if request_readiness.get("reason"):
        lines.append(f"Readiness detail  {request_readiness.get('reason')}")
    if request_readiness.get("verified_via"):
        lines.append(f"Verified via      {request_readiness.get('verified_via')}")
    if request_readiness.get("probe_payload"):
        lines.append(f"Probe payload     {request_readiness.get('probe_payload')}")
    if request_readiness.get("operator_hint"):
        lines.append(f"Operator hint     {request_readiness.get('operator_hint')}")
    if row.get("recommended_add_provider"):
        lines.append(
            f"Add route         {row.get('recommended_add_provider')} ({row.get('recommended_add_strategy')})"
        )
    if transport:
        lines.extend(
            [
                f"Transport profile {transport.get('profile') or 'n/a'}",
                f"Compatibility     {transport.get('compatibility') or 'n/a'}",
                f"Probe confidence  {transport.get('probe_confidence') or 'n/a'}",
                f"Probe strategy    {transport.get('probe_strategy') or 'n/a'}",
                f"Chat path         {transport.get('chat_path') or 'n/a'}",
            ]
        )
        for note in list(transport.get("notes") or [])[:2]:
            lines.append(f"Transport note    {note}")
    runtime_state = row.get("route_runtime_state") or {}
    if runtime_state:
        lines.extend(
            [
                f"Runtime penalty   {_safe_int(runtime_state.get('penalty'))}",
                f"Last issue type   {runtime_state.get('last_issue_type') or 'n/a'}",
            ]
        )
        if runtime_state.get("window_state") and runtime_state.get("window_state") != "clear":
            lines.append(f"Runtime window    {runtime_state.get('window_state')}")
        if runtime_state.get("cooldown_remaining_s"):
            lines.append(
                f"Cooldown left     {_safe_int(runtime_state.get('cooldown_remaining_s'))}s"
            )
        if runtime_state.get("degraded_remaining_s"):
            lines.append(
                f"Degraded left     {_safe_int(runtime_state.get('degraded_remaining_s'))}s"
            )
        if runtime_state.get("recovered_recently"):
            lines.append(
                f"Recovered from    {runtime_state.get('last_recovered_issue_type') or 'n/a'}"
            )
            lines.append(
                f"Recovery watch    {_safe_int(runtime_state.get('recovery_remaining_s'))}s"
            )
    if provider in unhealthy:
        lines.append(f"Live issue        {unhealthy[provider]['detail']}")
    if provider_routing_paths:
        lines.extend(["", "Observed attempt paths"])
        for item in provider_routing_paths[:3]:
            lines.append(
                f"- {item.get('selection_path')}: {_safe_int(item.get('requests'))} requests / {_format_usd(_safe_float(item.get('cost_usd')))}"
            )
    lines.extend(
        [
            "",
            "Operator hints",
            "- Compare this provider against Providers view when latency or failure rate starts drifting.",
            "- If this is expensive and stable, move lighter traffic to cheaper workhorse lanes before adding budget.",
            "- If this is both slow and expensive, keep it for the hard tasks and shift the rest to a balanced scenario.",
        ]
    )
    return "\n".join(lines) + "\n"


def _render_client_detail(report: dict[str, Any], client_name: str) -> str:
    target = client_name.strip().lower()
    row = next(
        (
            item
            for item in report["clients"]
            if str(item.get("client_tag") or item.get("client_profile") or "").lower() == target
        ),
        None,
    )
    if not row:
        return (
            "fusionAIze Gate Dashboard\n\n"
            f"Client detail\n\nNo client row found for '{client_name}'.\n"
        )

    name = str(row.get("client_tag") or row.get("client_profile") or client_name)
    expensive = (
        _safe_float(row.get("cost_usd")) > 0.5 or _safe_float(row.get("avg_latency_ms")) > 4000
    )
    suggested_scenario = _recommended_scenario_for_client(
        str(row.get("client_profile") or name),
        expensive=expensive,
    )
    lines = [
        "fusionAIze Gate Dashboard",
        "",
        f"Client detail: {name}",
        "",
        f"Profile           {row.get('client_profile') or 'generic'}",
        f"Requests          {_safe_int(row.get('requests'))}",
        f"Success           {_format_pct(_safe_float(row.get('success_pct') or 0))}",
        f"Latency           {_format_latency_ms(_safe_float(row.get('avg_latency_ms')))}",
        f"Cost              {_format_usd(_safe_float(row.get('cost_usd')))}",
        f"Tokens            {_format_tokens(_safe_int(row.get('total_tokens')))}",
        f"Providers         {row.get('providers') or 'n/a'}",
    ]
    if suggested_scenario:
        lines.append(f"Suggested scenario {suggested_scenario}")
    lines.extend(
        [
            "",
            "Decision help",
            "- Use the suggested scenario when this client needs a cleaner default without hand-editing the profile.",
            "- If this client is expensive but not mission-critical, trial an eco or free path first.",
            "- If this client is slow on hard tasks, keep premium paths for it and move lighter traffic elsewhere.",
        ]
    )
    return "\n".join(lines) + "\n"


def render_dashboard_text(
    report: dict[str, Any],
    *,
    view: str = "overview",
    target: str | None = None,
) -> str:
    """Render one human-readable dashboard view."""
    renderers = {
        "overview": _render_overview,
        "providers": _render_providers,
        "clients": _render_clients,
        "activity": _render_activity,
        "alerts": _render_alerts,
    }
    if view == "provider-detail":
        return _render_provider_detail(report, target or "")
    if view == "client-detail":
        return _render_client_detail(report, target or "")
    return renderers.get(view, _render_overview)(report)


def report_as_json(report: dict[str, Any]) -> str:
    """Serialize the report for shell helpers and tests."""
    return json.dumps(report, indent=2, sort_keys=True)
