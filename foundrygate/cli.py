#!/usr/bin/env python3
"""foundrygate-stats – CLI dashboard for FoundryGate metrics.

Usage:
    python -m foundrygate.cli              # Full overview
    python -m foundrygate.cli --recent 20  # Last 20 requests
    python -m foundrygate.cli --daily      # Daily cost breakdown
    python -m foundrygate.cli --json       # JSON output (pipe-friendly)
"""

# ruff: noqa: I001

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from .config import _safe_db_path, load_config
from .metrics import MetricsStore


# ── Formatting helpers ─────────────────────────────────────────

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
MAGENTA = "\033[35m"
CYAN = "\033[36m"
RED = "\033[31m"
WHITE = "\033[37m"


def _c(text: str, color: str) -> str:
    return f"{color}{text}{RESET}"


def _usd(n: float | None) -> str:
    if n is None or n == 0:
        return _c("$0.0000", DIM)
    return _c(f"${n:.4f}", GREEN)


def _tok(n: int | None) -> str:
    if not n:
        return _c("0", DIM)
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def _ms(n: float | None) -> str:
    if not n:
        return _c("—", DIM)
    return f"{n:.0f}ms"


def _ago(ts: float | None) -> str:
    if not ts:
        return "—"
    delta = time.time() - ts
    if delta < 60:
        return f"{delta:.0f}s ago"
    if delta < 3600:
        return f"{delta / 60:.0f}m ago"
    if delta < 86400:
        return f"{delta / 3600:.1f}h ago"
    return f"{delta / 86400:.1f}d ago"


def _bar(ratio: float, width: int = 20, char: str = "█") -> str:
    filled = int(ratio * width)
    return _c(char * filled, CYAN) + _c("░" * (width - filled), DIM)


def _table(headers: list[str], rows: list[list[str]], col_widths: list[int] | None = None):
    """Print a simple aligned table."""
    if not col_widths:
        col_widths = [
            max(len(h), max((len(str(r[i])) for r in rows), default=0)) + 2
            for i, h in enumerate(headers)
        ]

    # Header
    hdr = ""
    for i, h in enumerate(headers):
        hdr += _c(h.upper().ljust(col_widths[i]), DIM)
    print(hdr)
    print(_c("─" * sum(col_widths), DIM))

    # Rows
    for row in rows:
        line = ""
        for i, cell in enumerate(row):
            line += str(cell).ljust(col_widths[i])
        print(line)


# ── Commands ───────────────────────────────────────────────────


def cmd_overview(metrics: MetricsStore):
    totals = metrics.get_totals()
    providers = metrics.get_provider_summary()
    routing = metrics.get_routing_breakdown()

    print()
    print(_c("  ╔══════════════════════════════════════╗", BLUE))
    print(_c("  ║", BLUE) + _c("  FOUNDRYGATE STATS", BOLD) + _c("          ║", BLUE))
    print(_c("  ╚══════════════════════════════════════╝", BLUE))
    print()

    # Totals
    tr = totals.get("total_requests", 0) or 0
    tc = totals.get("total_cost_usd", 0) or 0
    pt = totals.get("total_prompt_tokens", 0) or 0
    ct = totals.get("total_compl_tokens", 0) or 0
    fl = totals.get("total_failures", 0) or 0
    al = totals.get("avg_latency_ms", 0) or 0

    print(
        f"  {_c('Requests:', DIM)}  {_c(str(tr), BOLD)}     "
        f"{_c('Cost:', DIM)}  {_usd(tc)}     "
        f"{_c('Tokens:', DIM)}  {_tok(pt)} in / {_tok(ct)} out     "
        f"{_c('Failures:', DIM)}  {_c(str(fl), RED if fl else DIM)}"
    )
    print(
        f"  {_c('Avg latency:', DIM)}  {_ms(al)}     "
        f"{_c('First:', DIM)}  {_ago(totals.get('first_request'))}     "
        f"{_c('Last:', DIM)}  {_ago(totals.get('last_request'))}"
    )
    print()

    # Provider breakdown
    if providers:
        print(_c("  ── Providers ──────────────────────────", DIM))
        max_req = max(p["requests"] for p in providers) if providers else 1
        rows = []
        for p in providers:
            ratio = p["requests"] / max_req if max_req else 0
            rows.append(
                [
                    _c(p["provider"], BOLD),
                    str(p["requests"]),
                    _tok(p.get("total_tokens", 0)),
                    _usd(p.get("cost_usd", 0)),
                    str(p.get("failures", 0)),
                    _ms(p.get("avg_latency_ms", 0)),
                    _bar(ratio, 15),
                ]
            )
        _table(
            ["Provider", "Reqs", "Tokens", "Cost", "Fail", "Latency", "Share"],
            rows,
            [22, 8, 10, 12, 6, 10, 18],
        )
        print()

    # Routing breakdown
    if routing:
        print(_c("  ── Routing Rules ─────────────────────", DIM))
        rows = []
        for r in routing[:12]:
            layer_color = {
                "static": MAGENTA,
                "heuristic": GREEN,
                "direct": YELLOW,
                "llm-classify": CYAN,
                "fallback": RED,
            }.get(r["layer"], WHITE)
            rows.append(
                [
                    _c(r["layer"], layer_color),
                    r["rule_name"],
                    r["provider"],
                    str(r["requests"]),
                    _usd(r.get("cost_usd", 0)),
                ]
            )
        _table(["Layer", "Rule", "Provider", "Reqs", "Cost"], rows, [14, 24, 22, 8, 12])
        print()


def cmd_recent(metrics: MetricsStore, limit: int):
    recent = metrics.get_recent(limit)
    if not recent:
        print(_c("  No requests recorded yet.", DIM))
        return

    print()
    print(_c(f"  ── Last {limit} Requests ──", DIM))
    rows = []
    for r in recent:
        ok = "✓" if r.get("success") else _c("✗", RED)
        rows.append(
            [
                _ago(r.get("timestamp")),
                r.get("provider", ""),
                r.get("layer", ""),
                r.get("rule_name", ""),
                _tok((r.get("prompt_tok", 0) or 0) + (r.get("compl_tok", 0) or 0)),
                _usd(r.get("cost_usd", 0)),
                _ms(r.get("latency_ms", 0)),
                ok,
            ]
        )
    _table(
        ["When", "Provider", "Layer", "Rule", "Tokens", "Cost", "Latency", "OK"],
        rows,
        [12, 20, 12, 20, 8, 12, 10, 4],
    )
    print()


def cmd_daily(metrics: MetricsStore, days: int):
    daily = metrics.get_daily_totals(days)
    if not daily:
        print(_c("  No data for the selected period.", DIM))
        return

    print()
    print(_c(f"  ── Daily Breakdown (last {days}d) ──", DIM))
    max_cost = max((d.get("cost_usd", 0) or 0) for d in daily) if daily else 1
    rows = []
    for d in daily:
        cost = d.get("cost_usd", 0) or 0
        ratio = cost / max_cost if max_cost else 0
        rows.append(
            [
                d.get("day", ""),
                str(d.get("requests", 0)),
                _tok(d.get("tokens", 0)),
                _usd(cost),
                str(d.get("failures", 0)),
                _bar(ratio, 20),
            ]
        )
    _table(["Day", "Reqs", "Tokens", "Cost", "Fail", "Cost Bar"], rows, [14, 8, 10, 12, 6, 24])

    total_cost = sum((d.get("cost_usd", 0) or 0) for d in daily)
    avg_daily = total_cost / len(daily) if daily else 0
    print()
    print(
        f"  {_c('Total:', DIM)} {_usd(total_cost)}   "
        f"{_c('Avg/day:', DIM)} {_usd(avg_daily)}   "
        f"{_c('Projected/month:', DIM)} {_usd(avg_daily * 30)}"
    )
    print()


# ── Main ───────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        prog="foundrygate-stats",
        description="CLI dashboard for FoundryGate metrics",
    )
    parser.add_argument("--db", help="Path to metrics DB (default: from config)")
    parser.add_argument("--recent", type=int, metavar="N", help="Show last N requests")
    parser.add_argument("--daily", action="store_true", help="Show daily cost breakdown")
    parser.add_argument("--days", type=int, default=30, help="Days for --daily (default: 30)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    # Find DB
    db_path = args.db
    if not db_path:
        try:
            cfg = load_config()
            db_path = cfg.metrics.get("db_path", _safe_db_path())
        except FileNotFoundError:
            db_path = _safe_db_path()

    if not Path(db_path).exists():
        print(f"Database not found: {db_path}", file=sys.stderr)
        print("Run the dispatcher first to create the database.", file=sys.stderr)
        sys.exit(1)

    metrics = MetricsStore(db_path)
    metrics.init()

    if args.json:
        data = {
            "totals": metrics.get_totals(),
            "providers": metrics.get_provider_summary(),
            "routing": metrics.get_routing_breakdown(),
            "daily": metrics.get_daily_totals(args.days),
            "recent": metrics.get_recent(args.recent or 20),
        }
        print(json.dumps(data, indent=2, default=str))
        metrics.close()
        return

    if args.recent:
        cmd_recent(metrics, args.recent)
    elif args.daily:
        cmd_daily(metrics, args.days)
    else:
        cmd_overview(metrics)

    metrics.close()


if __name__ == "__main__":
    main()
