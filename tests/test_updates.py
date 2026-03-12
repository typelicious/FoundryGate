"""Tests for release update checking."""

from __future__ import annotations

import pytest

from foundrygate.updates import (
    UpdateChecker,
    alert_level_for_update,
    classify_update,
    is_update_available,
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


@pytest.mark.asyncio
async def test_update_checker_reports_latest_release():
    checker = UpdateChecker(
        current_version="0.4.0",
        enabled=True,
        repository="typelicious/FoundryGate",
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
    assert "network unavailable" in status.error
