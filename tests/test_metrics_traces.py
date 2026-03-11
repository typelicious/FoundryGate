"""Tests for enriched routing metrics and trace queries."""

import sqlite3
from pathlib import Path

from foundrygate.metrics import MetricsStore


def test_metrics_store_persists_trace_fields(tmp_path):
    db_path = tmp_path / "foundrygate.db"
    metrics = MetricsStore(str(db_path))
    metrics.init()

    metrics.log_request(
        provider="local-worker",
        model="llama3",
        layer="profile",
        rule_name="profile-local-only",
        prompt_tokens=120,
        completion_tokens=24,
        cost_usd=0.0,
        latency_ms=43.0,
        requested_model="auto",
        client_profile="local-only",
        client_tag="n8n",
        decision_reason="Client profile 'local-only' selected a preferred provider",
        confidence=0.6,
        attempt_order=["local-worker", "cloud-default"],
    )

    recent = metrics.get_recent(1)
    assert recent[0]["requested_model"] == "auto"
    assert recent[0]["client_profile"] == "local-only"
    assert recent[0]["client_tag"] == "n8n"
    assert recent[0]["decision_reason"].startswith("Client profile")
    assert recent[0]["confidence"] == 0.6
    assert recent[0]["attempt_order"] == ["local-worker", "cloud-default"]

    client_rows = metrics.get_client_breakdown()
    assert client_rows[0]["client_profile"] == "local-only"
    assert client_rows[0]["client_tag"] == "n8n"
    assert client_rows[0]["provider"] == "local-worker"
    assert client_rows[0]["layer"] == "profile"
    assert client_rows[0]["requests"] == 1

    metrics.close()


def test_metrics_store_migrates_existing_db(tmp_path):
    db_path = Path(tmp_path) / "legacy.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE requests (
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
            error       TEXT    DEFAULT ''
        );
        """
    )
    conn.commit()
    conn.close()

    reopened = MetricsStore(str(db_path))
    reopened.init()
    columns = {
        row["name"]
        for row in reopened._q("PRAGMA table_info(requests)")  # noqa: SLF001
    }

    assert "client_profile" in columns
    assert "client_tag" in columns
    assert "attempt_order" in columns
    reopened.close()
