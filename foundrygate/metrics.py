"""Metrics store with cost tracking, time-series queries, and aggregations."""

from __future__ import annotations

import json
import logging
import sqlite3
import time

logger = logging.getLogger("foundrygate.metrics")


def calc_cost(
    prompt_tokens: int,
    completion_tokens: int,
    pricing: dict,
    cache_hit: int = 0,
    cache_miss: int = 0,
) -> float:
    """Calculate USD cost. If cache_hit/miss provided, use cache pricing."""
    out = pricing.get("output", 0)
    if cache_hit or cache_miss:
        # Cache-aware pricing: hit tokens at cache_read rate, miss at input rate
        cache_rate = pricing.get("cache_read", pricing.get("input", 0))
        miss_rate = pricing.get("input", 0)
        input_cost = (cache_hit * cache_rate + cache_miss * miss_rate) / 1_000_000
    else:
        input_cost = (prompt_tokens * pricing.get("input", 0)) / 1_000_000
    return input_cost + (completion_tokens * out) / 1_000_000


_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS requests (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   REAL    NOT NULL,
    provider    TEXT    NOT NULL,
    model       TEXT    NOT NULL,
    layer       TEXT    NOT NULL,
    rule_name   TEXT    NOT NULL,
    prompt_tok  INTEGER DEFAULT 0,
    compl_tok   INTEGER DEFAULT 0,
    cache_hit   INTEGER DEFAULT 0,
    cache_miss  INTEGER DEFAULT 0,
    cost_usd    REAL    DEFAULT 0,
    latency_ms  REAL    DEFAULT 0,
    success     INTEGER DEFAULT 1,
    error       TEXT    DEFAULT '',
    requested_model TEXT DEFAULT 'auto',
    client_profile  TEXT DEFAULT 'generic',
    client_tag      TEXT DEFAULT '',
    decision_reason TEXT DEFAULT '',
    confidence      REAL DEFAULT 0,
    attempt_order   TEXT DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS idx_req_ts       ON requests(timestamp);
CREATE INDEX IF NOT EXISTS idx_req_provider ON requests(provider);
CREATE INDEX IF NOT EXISTS idx_req_layer    ON requests(layer);
"""

_OPTIONAL_COLUMNS: dict[str, str] = {
    "requested_model": "TEXT DEFAULT 'auto'",
    "client_profile": "TEXT DEFAULT 'generic'",
    "client_tag": "TEXT DEFAULT ''",
    "decision_reason": "TEXT DEFAULT ''",
    "confidence": "REAL DEFAULT 0",
    "attempt_order": "TEXT DEFAULT '[]'",
}


class MetricsStore:
    """Synchronous SQLite store with cost tracking."""

    def __init__(self, db_path: str = "/var/lib/foundrygate/foundrygate.db"):
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None

    @property
    def db_path(self) -> str:
        return self._db_path

    def init(self) -> None:
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.executescript(_CREATE_SQL)
        self._ensure_optional_columns()
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_req_profile ON requests(client_profile)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_req_client ON requests(client_tag)")
        self._conn.commit()
        logger.info("Metrics DB ready: %s", self._db_path)

    def _ensure_optional_columns(self) -> None:
        """Add newer columns to an existing metrics DB without destroying data."""
        if not self._conn:
            return

        existing = {row[1] for row in self._conn.execute("PRAGMA table_info(requests)").fetchall()}
        for column_name, column_sql in _OPTIONAL_COLUMNS.items():
            if column_name in existing:
                continue
            self._conn.execute(f"ALTER TABLE requests ADD COLUMN {column_name} {column_sql}")

    def log_request(
        self,
        provider: str,
        model: str,
        layer: str,
        rule_name: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        cache_hit: int = 0,
        cache_miss: int = 0,
        cost_usd: float = 0.0,
        latency_ms: float = 0.0,
        success: bool = True,
        error: str = "",
        requested_model: str = "auto",
        client_profile: str = "generic",
        client_tag: str = "",
        decision_reason: str = "",
        confidence: float = 0.0,
        attempt_order: list[str] | None = None,
    ) -> None:
        if not self._conn:
            return
        try:
            self._conn.execute(
                """INSERT INTO requests
                   (timestamp,provider,model,layer,rule_name,
                    prompt_tok,compl_tok,cache_hit,cache_miss,
                    cost_usd,latency_ms,success,error,
                    requested_model,client_profile,client_tag,
                    decision_reason,confidence,attempt_order)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    time.time(),
                    provider,
                    model,
                    layer,
                    rule_name,
                    prompt_tokens,
                    completion_tokens,
                    cache_hit,
                    cache_miss,
                    cost_usd,
                    latency_ms,
                    1 if success else 0,
                    error,
                    requested_model,
                    client_profile,
                    client_tag,
                    decision_reason,
                    confidence,
                    json.dumps(attempt_order or []),
                ),
            )
            self._conn.commit()
        except Exception as e:
            logger.warning("Metrics write failed: %s", e)

    def get_provider_summary(self) -> list[dict]:
        return self._q("""
            SELECT provider,
                COUNT(*)                                        AS requests,
                SUM(CASE WHEN success=0 THEN 1 ELSE 0 END)     AS failures,
                SUM(prompt_tok)                                 AS prompt_tokens,
                SUM(compl_tok)                                  AS compl_tokens,
                SUM(prompt_tok+compl_tok)                       AS total_tokens,
                SUM(cache_hit)                                  AS cache_hit_tokens,
                SUM(cache_miss)                                 AS cache_miss_tokens,
                ROUND(CASE WHEN SUM(cache_hit+cache_miss)>0
                    THEN SUM(cache_hit)*100.0/SUM(cache_hit+cache_miss)
                    ELSE 0 END, 1)                              AS cache_hit_pct,
                ROUND(SUM(cost_usd),6)                          AS cost_usd,
                ROUND(AVG(latency_ms),1)                        AS avg_latency_ms
            FROM requests GROUP BY provider ORDER BY requests DESC
        """)

    def get_routing_breakdown(self) -> list[dict]:
        return self._q("""
            SELECT layer, rule_name, provider,
                COUNT(*)                  AS requests,
                ROUND(SUM(cost_usd),6)    AS cost_usd,
                ROUND(AVG(latency_ms),1)  AS avg_latency_ms
            FROM requests WHERE success=1
            GROUP BY layer, rule_name, provider ORDER BY requests DESC
        """)

    def get_client_breakdown(self) -> list[dict]:
        return self._q("""
            SELECT client_profile,
                client_tag,
                provider,
                layer,
                COUNT(*)                 AS requests,
                ROUND(SUM(cost_usd),6)   AS cost_usd,
                ROUND(AVG(latency_ms),1) AS avg_latency_ms
            FROM requests
            GROUP BY client_profile, client_tag, provider, layer
            ORDER BY requests DESC, client_profile ASC, client_tag ASC
        """)

    def get_hourly_series(self, hours: int = 24) -> list[dict]:
        cutoff = time.time() - hours * 3600
        return self._q(
            """
            SELECT CAST((timestamp-?)/3600 AS INTEGER) AS hour_offset,
                COUNT(*)                    AS requests,
                ROUND(SUM(cost_usd),6)      AS cost_usd,
                SUM(prompt_tok+compl_tok)    AS tokens
            FROM requests WHERE timestamp>=?
            GROUP BY hour_offset ORDER BY hour_offset
        """,
            (cutoff, cutoff),
        )

    def get_daily_totals(self, days: int = 30) -> list[dict]:
        cutoff = time.time() - days * 86400
        return self._q(
            """
            SELECT DATE(timestamp,'unixepoch','localtime') AS day,
                COUNT(*)                                    AS requests,
                ROUND(SUM(cost_usd),6)                      AS cost_usd,
                SUM(prompt_tok+compl_tok)                    AS tokens,
                SUM(CASE WHEN success=0 THEN 1 ELSE 0 END)  AS failures
            FROM requests WHERE timestamp>=?
            GROUP BY day ORDER BY day
        """,
            (cutoff,),
        )

    def get_recent(self, limit: int = 50) -> list[dict]:
        rows = self._q("SELECT * FROM requests ORDER BY timestamp DESC LIMIT ?", (limit,))
        for row in rows:
            attempt_order = row.get("attempt_order")
            if isinstance(attempt_order, str) and attempt_order:
                try:
                    row["attempt_order"] = json.loads(attempt_order)
                except json.JSONDecodeError:
                    row["attempt_order"] = []
        return rows

    def get_totals(self) -> dict:
        rows = self._q("""
            SELECT COUNT(*)                                        AS total_requests,
                SUM(CASE WHEN success=0 THEN 1 ELSE 0 END)        AS total_failures,
                SUM(prompt_tok)                                    AS total_prompt_tokens,
                SUM(compl_tok)                                     AS total_compl_tokens,
                SUM(cache_hit)                                     AS total_cache_hit,
                SUM(cache_miss)                                    AS total_cache_miss,
                ROUND(CASE WHEN SUM(cache_hit+cache_miss)>0
                    THEN SUM(cache_hit)*100.0/SUM(cache_hit+cache_miss)
                    ELSE 0 END, 1)                                 AS cache_hit_pct,
                ROUND(SUM(cost_usd),6)                             AS total_cost_usd,
                ROUND(AVG(latency_ms),1)                           AS avg_latency_ms,
                MIN(timestamp)                                     AS first_request,
                MAX(timestamp)                                     AS last_request
            FROM requests
        """)
        return rows[0] if rows else {}

    def _q(self, sql: str, params: tuple = ()) -> list[dict]:
        if not self._conn:
            return []
        cur = self._conn.execute(sql, params)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def close(self) -> None:
        if self._conn:
            self._conn.close()
