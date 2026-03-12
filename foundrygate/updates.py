"""Release update checks for operators."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx


def _normalize_version(value: str) -> tuple[int, ...]:
    """Normalize a tag or version string like v0.5.0 into a comparable tuple."""
    cleaned = (value or "").strip().lower()
    if cleaned.startswith("v"):
        cleaned = cleaned[1:]
    parts = []
    for chunk in cleaned.split("."):
        digits = []
        for char in chunk:
            if char.isdigit():
                digits.append(char)
            else:
                break
        parts.append(int("".join(digits) or "0"))
    return tuple(parts)


def is_update_available(current_version: str, latest_version: str) -> bool:
    """Return whether the latest release is newer than the current runtime version."""
    current = _normalize_version(current_version)
    latest = _normalize_version(latest_version)
    if not current or not latest:
        return False
    width = max(len(current), len(latest))
    current += (0,) * (width - len(current))
    latest += (0,) * (width - len(latest))
    return latest > current


def classify_update(current_version: str, latest_version: str) -> str:
    """Classify a newer release as patch, minor, major, or current."""
    current = _normalize_version(current_version)
    latest = _normalize_version(latest_version)
    if not current or not latest:
        return "unknown"

    width = max(3, len(current), len(latest))
    current += (0,) * (width - len(current))
    latest += (0,) * (width - len(latest))
    if latest <= current:
        return "current"
    if latest[0] > current[0]:
        return "major"
    if latest[1] > current[1]:
        return "minor"
    return "patch"


def alert_level_for_update(update_type: str, *, available: bool, status: str) -> str:
    """Return an operator-facing alert level for one update status."""
    if status in {"unavailable"}:
        return "warning"
    if status in {"disabled"}:
        return "disabled"
    if not available:
        return "ok"
    if update_type == "major":
        return "critical"
    if update_type == "minor":
        return "warning"
    if update_type == "patch":
        return "info"
    return "warning"


@dataclass
class UpdateStatus:
    """Structured update-check result."""

    enabled: bool
    current_version: str
    latest_version: str = ""
    update_available: bool = False
    repository: str = ""
    release_url: str = ""
    checked_at: float = 0.0
    status: str = "disabled"
    update_type: str = "current"
    alert_level: str = "disabled"
    recommended_action: str = ""
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "current_version": self.current_version,
            "latest_version": self.latest_version,
            "update_available": self.update_available,
            "repository": self.repository,
            "release_url": self.release_url,
            "checked_at": self.checked_at,
            "status": self.status,
            "update_type": self.update_type,
            "alert_level": self.alert_level,
            "recommended_action": self.recommended_action,
            "error": self.error,
        }


class UpdateChecker:
    """Fetch and cache release update metadata for the running gateway."""

    def __init__(
        self,
        *,
        current_version: str,
        enabled: bool,
        repository: str,
        api_base: str = "https://api.github.com",
        check_interval_seconds: int = 21600,
        timeout_seconds: float = 5.0,
    ):
        self.current_version = current_version
        self.enabled = enabled
        self.repository = repository
        self.api_base = api_base.rstrip("/")
        self.check_interval_seconds = check_interval_seconds
        self.timeout_seconds = timeout_seconds
        self._cached = UpdateStatus(
            enabled=enabled,
            current_version=current_version,
            repository=repository,
        )
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds, connect=min(timeout_seconds, 5.0)),
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": f"FoundryGate/{current_version}",
            },
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def get_status(self, *, force: bool = False) -> UpdateStatus:
        """Return cached or freshly fetched update status."""
        if not self.enabled:
            self._cached = UpdateStatus(
                enabled=False,
                current_version=self.current_version,
                repository=self.repository,
                checked_at=time.time(),
                status="disabled",
                update_type="current",
                alert_level="disabled",
                recommended_action="Update checks are disabled",
            )
            return self._cached

        now = time.time()
        if (
            not force
            and self._cached.checked_at
            and (now - self._cached.checked_at) < self.check_interval_seconds
            and self._cached.status in {"ok", "unavailable"}
        ):
            return self._cached

        url = f"{self.api_base}/repos/{self.repository}/releases/latest"
        try:
            response = await self._client.get(url)
            if response.status_code >= 400:
                self._cached = UpdateStatus(
                    enabled=True,
                    current_version=self.current_version,
                    repository=self.repository,
                    checked_at=now,
                    status="unavailable",
                    update_type="unknown",
                    alert_level="warning",
                    recommended_action="Inspect release connectivity and retry later",
                    error=f"Release lookup returned HTTP {response.status_code}",
                )
                return self._cached

            payload = response.json()
            latest_version = str(payload.get("tag_name") or "").strip()
            release_url = str(payload.get("html_url") or "").strip()
            update_available = is_update_available(self.current_version, latest_version)
            update_type = classify_update(self.current_version, latest_version)
            alert_level = alert_level_for_update(
                update_type,
                available=update_available,
                status="ok",
            )
            self._cached = UpdateStatus(
                enabled=True,
                current_version=self.current_version,
                latest_version=latest_version,
                update_available=update_available,
                repository=self.repository,
                release_url=release_url,
                checked_at=now,
                status="ok",
                update_type=update_type,
                alert_level=alert_level,
                recommended_action=(
                    "Upgrade to the latest release" if update_available else "No action needed"
                ),
            )
            return self._cached
        except Exception as exc:
            self._cached = UpdateStatus(
                enabled=True,
                current_version=self.current_version,
                repository=self.repository,
                checked_at=now,
                status="unavailable",
                update_type="unknown",
                alert_level="warning",
                recommended_action="Inspect release connectivity and retry later",
                error=str(exc),
            )
            return self._cached
