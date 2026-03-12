"""Tests for release update checking."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from foundrygate.updates import (
    UpdateChecker,
    alert_level_for_update,
    allowed_update_types_for_ring,
    apply_auto_update_guardrails,
    apply_maintenance_window_guardrail,
    apply_release_age_guardrail,
    classify_update,
    is_update_available,
    release_age_hours,
    select_release_payload,
)


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, response: _FakeResponse | Exception):
        self._response = response
        self.calls = 0

    async def get(self, url):
        self.calls += 1
        if isinstance(self._response, Exception):
            raise self._response
        return self._response

    async def aclose(self):
        return None


def test_version_comparison_detects_newer_release():
    assert is_update_available("0.4.0", "v0.5.0") is True
    assert is_update_available("0.5.0", "v0.5.0") is False
    assert is_update_available("0.5.1", "v0.5.0") is False


def test_classify_update_distinguishes_patch_minor_and_major():
    assert classify_update("0.6.0", "v0.6.1") == "patch"
    assert classify_update("0.6.0", "v0.7.0") == "minor"
    assert classify_update("0.6.0", "v1.0.0") == "major"
    assert classify_update("0.6.0", "v0.6.0") == "current"


def test_alert_level_maps_update_type_and_status():
    assert alert_level_for_update("patch", available=True, status="ok") == "info"
    assert alert_level_for_update("minor", available=True, status="ok") == "warning"
    assert alert_level_for_update("major", available=True, status="ok") == "critical"
    assert alert_level_for_update("current", available=False, status="ok") == "ok"
    assert alert_level_for_update("unknown", available=False, status="unavailable") == "warning"


def test_allowed_update_types_follow_rollout_ring():
    assert allowed_update_types_for_ring("stable", allow_major=False) == ["patch"]
    assert allowed_update_types_for_ring("early", allow_major=False) == ["patch", "minor"]
    assert allowed_update_types_for_ring("canary", allow_major=False) == ["patch", "minor"]
    assert allowed_update_types_for_ring("canary", allow_major=True) == [
        "patch",
        "minor",
        "major",
    ]


def test_select_release_payload_uses_first_preview_release():
    payload = [
        {"tag_name": "v0.8.0-rc1", "draft": False, "html_url": "https://example.test/rc1"},
        {"tag_name": "v0.7.0", "draft": False, "html_url": "https://example.test/stable"},
    ]
    chosen = select_release_payload(payload, release_channel="preview")
    assert chosen["tag_name"] == "v0.8.0-rc1"


def test_release_age_hours_reports_elapsed_time():
    now = datetime(2026, 3, 12, 18, 0, tzinfo=timezone.utc)
    published = (now - timedelta(hours=6)).isoformat().replace("+00:00", "Z")
    assert release_age_hours(published, now=now) == 6.0


def test_release_age_guardrail_blocks_new_releases():
    guarded = apply_release_age_guardrail(
        {
            "enabled": True,
            "eligible": True,
            "min_release_age_hours": 24,
            "blocked_reason": "",
        },
        published_at=(datetime.now(timezone.utc) - timedelta(hours=2))
        .isoformat()
        .replace("+00:00", "Z"),
    )
    assert guarded["eligible"] is False
    assert guarded["blocked_reason"].startswith("Release is too new")


def test_auto_update_guardrails_block_when_too_many_providers_are_unhealthy():
    guarded = apply_auto_update_guardrails(
        {
            "enabled": True,
            "eligible": True,
            "require_healthy_providers": True,
            "max_unhealthy_providers": 0,
            "blocked_reason": "",
        },
        providers_total=2,
        providers_healthy=1,
        providers_unhealthy=1,
    )

    assert guarded["eligible"] is False
    assert guarded["blocked_reason"] == "Too many unhealthy providers (1 > 0)"


def test_auto_update_guardrails_allow_updates_when_health_budget_is_met():
    guarded = apply_auto_update_guardrails(
        {
            "enabled": True,
            "eligible": True,
            "require_healthy_providers": True,
            "max_unhealthy_providers": 1,
            "blocked_reason": "",
        },
        providers_total=3,
        providers_healthy=2,
        providers_unhealthy=1,
    )

    assert guarded["eligible"] is True


def test_auto_update_guardrails_block_when_no_provider_is_healthy():
    guarded = apply_auto_update_guardrails(
        {
            "enabled": True,
            "eligible": True,
            "require_healthy_providers": True,
            "max_unhealthy_providers": 2,
            "blocked_reason": "",
        },
        providers_total=2,
        providers_healthy=0,
        providers_unhealthy=2,
    )

    assert guarded["eligible"] is False
    assert guarded["blocked_reason"] == "No healthy providers available"


def test_auto_update_guardrails_block_when_provider_scope_matches_nothing():
    guarded = apply_auto_update_guardrails(
        {
            "enabled": True,
            "eligible": True,
            "require_healthy_providers": True,
            "max_unhealthy_providers": 0,
            "blocked_reason": "",
        },
        providers_total=0,
        providers_healthy=0,
        providers_unhealthy=0,
    )

    assert guarded["eligible"] is False
    assert guarded["blocked_reason"] == "No providers match rollout provider scope"


def test_maintenance_window_guardrail_allows_updates_when_window_is_disabled():
    guarded = apply_maintenance_window_guardrail(
        {
            "enabled": True,
            "eligible": True,
            "blocked_reason": "",
            "maintenance_window": {
                "enabled": False,
                "timezone": "UTC",
                "days": [],
                "start_hour": 0,
                "end_hour": 24,
            },
        },
        now=datetime(2026, 3, 12, 12, 0, tzinfo=timezone.utc),
    )

    assert guarded["eligible"] is True
    assert guarded["maintenance_window"]["open"] is True


def test_maintenance_window_guardrail_blocks_outside_allowed_days():
    guarded = apply_maintenance_window_guardrail(
        {
            "enabled": True,
            "eligible": True,
            "blocked_reason": "",
            "maintenance_window": {
                "enabled": True,
                "timezone": "UTC",
                "days": ["sat", "sun"],
                "start_hour": 0,
                "end_hour": 24,
            },
        },
        now=datetime(2026, 3, 12, 12, 0, tzinfo=timezone.utc),
    )

    assert guarded["eligible"] is False
    assert guarded["maintenance_window"]["open"] is False
    assert guarded["blocked_reason"] == "Outside maintenance days (thu)"


def test_maintenance_window_guardrail_blocks_outside_allowed_hours():
    guarded = apply_maintenance_window_guardrail(
        {
            "enabled": True,
            "eligible": True,
            "blocked_reason": "",
            "maintenance_window": {
                "enabled": True,
                "timezone": "UTC",
                "days": [],
                "start_hour": 2,
                "end_hour": 5,
            },
        },
        now=datetime(2026, 3, 12, 12, 0, tzinfo=timezone.utc),
    )

    assert guarded["eligible"] is False
    assert guarded["maintenance_window"]["open"] is False
    assert guarded["blocked_reason"] == "Outside maintenance window (02:00-05:00 UTC)"


def test_maintenance_window_guardrail_allows_inside_matching_window():
    guarded = apply_maintenance_window_guardrail(
        {
            "enabled": True,
            "eligible": True,
            "blocked_reason": "",
            "maintenance_window": {
                "enabled": True,
                "timezone": "UTC",
                "days": ["thu"],
                "start_hour": 10,
                "end_hour": 14,
            },
        },
        now=datetime(2026, 3, 12, 12, 0, tzinfo=timezone.utc),
    )

    assert guarded["eligible"] is True
    assert guarded["maintenance_window"]["open"] is True
    assert guarded["maintenance_window"]["current_day"] == "thu"
    assert guarded["maintenance_window"]["current_hour"] == 12


def test_maintenance_window_guardrail_blocks_unknown_timezone():
    guarded = apply_maintenance_window_guardrail(
        {
            "enabled": True,
            "eligible": True,
            "blocked_reason": "",
            "maintenance_window": {
                "enabled": True,
                "timezone": "Mars/Olympus",
                "days": [],
                "start_hour": 0,
                "end_hour": 24,
            },
        },
        now=datetime(2026, 3, 12, 12, 0, tzinfo=timezone.utc),
    )

    assert guarded["eligible"] is False
    assert guarded["maintenance_window"]["open"] is False
    assert guarded["blocked_reason"] == "Unknown maintenance-window timezone 'Mars/Olympus'"


@pytest.mark.asyncio
async def test_update_checker_reports_latest_release():
    checker = UpdateChecker(
        current_version="0.4.0",
        enabled=True,
        repository="typelicious/FoundryGate",
        auto_update={
            "enabled": True,
            "allow_major": False,
            "provider_scope": {"allow_providers": ["deepseek-chat"], "deny_providers": []},
        },
    )
    checker._client = _FakeClient(
        _FakeResponse(
            200,
            {
                "tag_name": "v0.5.0",
                "html_url": "https://github.com/typelicious/FoundryGate/releases/tag/v0.5.0",
            },
        )
    )

    status = await checker.get_status(force=True)

    assert status.status == "ok"
    assert status.latest_version == "v0.5.0"
    assert status.update_available is True
    assert status.update_type == "minor"
    assert status.alert_level == "warning"
    assert status.recommended_action == "Upgrade to the latest release"
    assert status.auto_update["enabled"] is True
    assert status.auto_update["eligible"] is True
    assert status.release_channel == "stable"
    assert status.auto_update["allowed_update_types"] == ["patch", "minor"]
    assert status.auto_update["provider_scope"] == {
        "allow_providers": ["deepseek-chat"],
        "deny_providers": [],
    }
    assert status.release_url.endswith("/v0.5.0")


@pytest.mark.asyncio
async def test_update_checker_uses_cache_until_forced():
    checker = UpdateChecker(
        current_version="0.4.0",
        enabled=True,
        repository="typelicious/FoundryGate",
        check_interval_seconds=3600,
    )
    fake_client = _FakeClient(
        _FakeResponse(
            200,
            {
                "tag_name": "v0.4.0",
                "html_url": "https://github.com/typelicious/FoundryGate/releases/tag/v0.4.0",
            },
        )
    )
    checker._client = fake_client

    first = await checker.get_status(force=True)
    second = await checker.get_status(force=False)

    assert first.status == "ok"
    assert second.status == "ok"
    assert second.alert_level == "ok"
    assert fake_client.calls == 1


@pytest.mark.asyncio
async def test_update_checker_handles_remote_errors():
    checker = UpdateChecker(
        current_version="0.4.0",
        enabled=True,
        repository="typelicious/FoundryGate",
    )
    checker._client = _FakeClient(RuntimeError("network unavailable"))

    status = await checker.get_status(force=True)

    assert status.status == "unavailable"
    assert status.update_available is False
    assert status.alert_level == "warning"
    assert status.recommended_action == "Inspect release connectivity and retry later"
    assert status.auto_update["eligible"] is False
    assert status.auto_update["blocked_reason"] == "Auto-update is disabled"
    assert "network unavailable" in status.error


@pytest.mark.asyncio
async def test_major_updates_are_blocked_when_auto_update_disallows_them():
    checker = UpdateChecker(
        current_version="0.6.0",
        enabled=True,
        repository="typelicious/FoundryGate",
        auto_update={"enabled": True, "allow_major": False},
    )
    checker._client = _FakeClient(
        _FakeResponse(
            200,
            {
                "tag_name": "v1.0.0",
                "html_url": "https://github.com/typelicious/FoundryGate/releases/tag/v1.0.0",
            },
        )
    )

    status = await checker.get_status(force=True)

    assert status.update_type == "major"
    assert status.auto_update["enabled"] is True
    assert status.auto_update["eligible"] is False
    assert status.auto_update["blocked_reason"] == "Major updates require manual approval"


@pytest.mark.asyncio
async def test_stable_rollout_ring_blocks_minor_updates():
    checker = UpdateChecker(
        current_version="0.6.0",
        enabled=True,
        repository="typelicious/FoundryGate",
        auto_update={"enabled": True, "rollout_ring": "stable", "allow_major": False},
    )
    checker._client = _FakeClient(
        _FakeResponse(
            200,
            {
                "tag_name": "v0.7.0",
                "html_url": "https://github.com/typelicious/FoundryGate/releases/tag/v0.7.0",
            },
        )
    )

    status = await checker.get_status(force=True)

    assert status.update_type == "minor"
    assert status.auto_update["rollout_ring"] == "stable"
    assert status.auto_update["eligible"] is False
    assert status.auto_update["blocked_reason"] == "Minor updates require manual approval"


@pytest.mark.asyncio
async def test_preview_release_channel_reads_latest_preview_release():
    checker = UpdateChecker(
        current_version="0.6.0",
        enabled=True,
        repository="typelicious/FoundryGate",
        release_channel="preview",
        auto_update={"enabled": True, "rollout_ring": "canary", "allow_major": False},
    )
    checker._client = _FakeClient(
        _FakeResponse(
            200,
            [
                {
                    "tag_name": "v0.7.0-rc1",
                    "draft": False,
                    "html_url": "https://github.com/typelicious/FoundryGate/releases/tag/v0.7.0-rc1",
                },
                {
                    "tag_name": "v0.6.2",
                    "draft": False,
                    "html_url": "https://github.com/typelicious/FoundryGate/releases/tag/v0.6.2",
                },
            ],
        )
    )

    status = await checker.get_status(force=True)

    assert status.release_channel == "preview"
    assert status.latest_version == "v0.7.0-rc1"


@pytest.mark.asyncio
async def test_min_release_age_blocks_auto_update_until_release_has_aged():
    checker = UpdateChecker(
        current_version="0.6.0",
        enabled=True,
        repository="typelicious/FoundryGate",
        auto_update={
            "enabled": True,
            "rollout_ring": "early",
            "allow_major": False,
            "min_release_age_hours": 24,
        },
    )
    checker._client = _FakeClient(
        _FakeResponse(
            200,
            {
                "tag_name": "v0.6.1",
                "html_url": "https://github.com/typelicious/FoundryGate/releases/tag/v0.6.1",
                "published_at": (datetime.now(timezone.utc) - timedelta(hours=1))
                .isoformat()
                .replace("+00:00", "Z"),
            },
        )
    )

    status = await checker.get_status(force=True)

    assert status.update_type == "patch"
    assert status.auto_update["eligible"] is False
    assert status.auto_update["min_release_age_hours"] == 24
    assert status.auto_update["blocked_reason"].startswith("Release is too new")


@pytest.mark.asyncio
async def test_auto_update_disabled_status_is_reported_cleanly():
    checker = UpdateChecker(
        current_version="0.6.0",
        enabled=False,
        repository="typelicious/FoundryGate",
        auto_update={"enabled": False},
    )

    status = await checker.get_status(force=False)

    assert status.status == "disabled"
    assert status.auto_update["enabled"] is False
    assert status.auto_update["eligible"] is False
    assert status.auto_update["blocked_reason"] == "Auto-update is disabled"
