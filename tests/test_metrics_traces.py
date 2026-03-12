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
        modality="chat",
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
    assert recent[0]["modality"] == "chat"
    assert recent[0]["client_profile"] == "local-only"
    assert recent[0]["client_tag"] == "n8n"
    assert recent[0]["decision_reason"].startswith("Client profile")
    assert recent[0]["confidence"] == 0.6
    assert recent[0]["attempt_order"] == ["local-worker", "cloud-default"]

    client_rows = metrics.get_client_breakdown()
    assert client_rows[0]["modality"] == "chat"
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
    assert "modality" in columns
    assert "attempt_order" in columns
    reopened.close()


def test_metrics_store_filters_recent_and_breakdowns(tmp_path):
    db_path = tmp_path / "filtered.db"
    metrics = MetricsStore(str(db_path))
    metrics.init()

    metrics.log_request(
        provider="local-worker",
        model="llama3",
        modality="image_generation",
        layer="hook",
        rule_name="request-hooks",
        cost_usd=0.0,
        latency_ms=25.0,
        client_profile="local-only",
        client_tag="codex",
        success=True,
    )
    metrics.log_request(
        provider="cloud-default",
        model="cloud-chat",
        modality="chat",
        layer="policy",
        rule_name="prefer-cloud",
        cost_usd=0.01,
        latency_ms=140.0,
        client_profile="generic",
        client_tag="n8n",
        success=False,
    )

    local_recent = metrics.get_recent(10, provider="local-worker")
    assert len(local_recent) == 1
    assert local_recent[0]["provider"] == "local-worker"

    failed_recent = metrics.get_recent(10, success=False)
    assert len(failed_recent) == 1
    assert failed_recent[0]["provider"] == "cloud-default"

    client_rows = metrics.get_client_breakdown(client_tag="codex")
    assert len(client_rows) == 1
    assert client_rows[0]["modality"] == "image_generation"
    assert client_rows[0]["client_tag"] == "codex"
    assert client_rows[0]["provider"] == "local-worker"

    modality_rows = metrics.get_modality_breakdown(modality="image_generation")
    assert len(modality_rows) == 1
    assert modality_rows[0]["modality"] == "image_generation"
    assert modality_rows[0]["provider"] == "local-worker"

    routing_rows = metrics.get_routing_breakdown(layer="hook")
    assert len(routing_rows) == 1
    assert routing_rows[0]["layer"] == "hook"

    totals = metrics.get_totals(provider="cloud-default")
    assert totals["total_requests"] == 1
    assert totals["total_failures"] == 1

    metrics.close()
