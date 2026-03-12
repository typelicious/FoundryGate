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


def allowed_update_types_for_ring(rollout_ring: str, *, allow_major: bool) -> list[str]:
    """Return the allowed update types for one rollout ring."""
    if rollout_ring == "stable":
        allowed = ["patch"]
    elif rollout_ring == "canary":
        allowed = ["patch", "minor"]
    else:
        allowed = ["patch", "minor"]

    if allow_major and rollout_ring == "canary":
        allowed.append("major")
    return allowed


def select_release_payload(payload: Any, *, release_channel: str) -> dict[str, Any]:
    """Select one release object from the GitHub API payload."""
    if release_channel == "preview":
        if not isinstance(payload, list):
            return {}
        for item in payload:
            if isinstance(item, dict) and not item.get("draft"):
                return item
        return {}
    if isinstance(payload, dict):
        return payload
    return {}


def apply_auto_update_guardrails(
    auto_update: dict[str, Any],
    *,
    providers_healthy: int,
    providers_unhealthy: int,
) -> dict[str, Any]:
    """Apply provider-health guardrails to one auto-update eligibility result."""
    result = dict(auto_update or {})
    if not result.get("enabled") or not result.get("eligible"):
        return result

    require_healthy_providers = bool(result.get("require_healthy_providers", True))
    max_unhealthy_providers = int(result.get("max_unhealthy_providers", 0))

    if not require_healthy_providers:
        return result

    if providers_healthy <= 0:
        result["eligible"] = False
        result["blocked_reason"] = "No healthy providers available"
        return result

    if providers_unhealthy > max_unhealthy_providers:
        result["eligible"] = False
        result["blocked_reason"] = (
            f"Too many unhealthy providers ({providers_unhealthy} > {max_unhealthy_providers})"
        )
        return result

    return result


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
    release_channel: str = "stable"
    update_type: str = "current"
    alert_level: str = "disabled"
    recommended_action: str = ""
    auto_update: dict[str, Any] | None = None
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
            "release_channel": self.release_channel,
            "update_type": self.update_type,
            "alert_level": self.alert_level,
            "recommended_action": self.recommended_action,
            "auto_update": self.auto_update or {},
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
        release_channel: str = "stable",
        auto_update: dict[str, Any] | None = None,
    ):
        self.current_version = current_version
        self.enabled = enabled
        self.repository = repository
        self.api_base = api_base.rstrip("/")
        self.check_interval_seconds = check_interval_seconds
        self.timeout_seconds = timeout_seconds
        self.release_channel = release_channel
        self.auto_update = {
            "enabled": bool((auto_update or {}).get("enabled", False)),
            "allow_major": bool((auto_update or {}).get("allow_major", False)),
            "rollout_ring": str((auto_update or {}).get("rollout_ring", "early")),
            "require_healthy_providers": bool(
                (auto_update or {}).get("require_healthy_providers", True)
            ),
            "max_unhealthy_providers": int((auto_update or {}).get("max_unhealthy_providers", 0)),
            "apply_command": str((auto_update or {}).get("apply_command", "foundrygate-update")),
        }
        self._cached = UpdateStatus(
            enabled=enabled,
            current_version=current_version,
            repository=repository,
            release_channel=release_channel,
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

    def _auto_update_status(
        self,
        *,
        status: str,
        update_available: bool,
        update_type: str,
        latest_version: str = "",
    ) -> dict[str, Any]:
        """Return opt-in auto-update eligibility for operator tooling."""
        enabled = bool(self.auto_update.get("enabled", False))
        allow_major = bool(self.auto_update.get("allow_major", False))
        rollout_ring = str(self.auto_update.get("rollout_ring", "early"))
        apply_command = str(self.auto_update.get("apply_command", "foundrygate-update"))
        allowed_types = allowed_update_types_for_ring(rollout_ring, allow_major=allow_major)

        blocked_reason = ""
        eligible = False
        if not enabled:
            blocked_reason = "Auto-update is disabled"
        elif status == "disabled":
            blocked_reason = "Update checks are disabled"
        elif status != "ok":
            blocked_reason = "Release status is unavailable"
        elif not update_available:
            blocked_reason = "Already on the latest release"
        elif update_type not in allowed_types:
            blocked_reason = f"{update_type.capitalize()} updates require manual approval"
        else:
            eligible = True

        return {
            "enabled": enabled,
            "strategy": "script",
            "allowed_update_types": allowed_types,
            "allow_major": allow_major,
            "rollout_ring": rollout_ring,
            "require_healthy_providers": bool(
                self.auto_update.get("require_healthy_providers", True)
            ),
            "max_unhealthy_providers": int(self.auto_update.get("max_unhealthy_providers", 0)),
            "eligible": eligible,
            "blocked_reason": blocked_reason,
            "apply_command": apply_command,
            "target_version": latest_version,
            "requires_operator_trigger": True,
        }

    async def get_status(self, *, force: bool = False) -> UpdateStatus:
        """Return cached or freshly fetched update status."""
        if not self.enabled:
            self._cached = UpdateStatus(
                enabled=False,
                current_version=self.current_version,
                repository=self.repository,
                checked_at=time.time(),
                status="disabled",
                release_channel=self.release_channel,
                update_type="current",
                alert_level="disabled",
                recommended_action="Update checks are disabled",
                auto_update=self._auto_update_status(
                    status="disabled",
                    update_available=False,
                    update_type="current",
                ),
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

        if self.release_channel == "preview":
            url = f"{self.api_base}/repos/{self.repository}/releases?per_page=10"
        else:
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
                    release_channel=self.release_channel,
                    update_type="unknown",
                    alert_level="warning",
                    recommended_action="Inspect release connectivity and retry later",
                    auto_update=self._auto_update_status(
                        status="unavailable",
                        update_available=False,
                        update_type="unknown",
                    ),
                    error=f"Release lookup returned HTTP {response.status_code}",
                )
                return self._cached

            payload = select_release_payload(response.json(), release_channel=self.release_channel)
            latest_version = str(payload.get("tag_name") or "").strip()
            release_url = str(payload.get("html_url") or "").strip()
            if not latest_version:
                self._cached = UpdateStatus(
                    enabled=True,
                    current_version=self.current_version,
                    repository=self.repository,
                    checked_at=now,
                    status="unavailable",
                    release_channel=self.release_channel,
                    update_type="unknown",
                    alert_level="warning",
                    recommended_action="Inspect release connectivity and retry later",
                    auto_update=self._auto_update_status(
                        status="unavailable",
                        update_available=False,
                        update_type="unknown",
                    ),
                    error="No release found for the selected channel",
                )
                return self._cached
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
                release_channel=self.release_channel,
                update_type=update_type,
                alert_level=alert_level,
                recommended_action=(
                    "Upgrade to the latest release" if update_available else "No action needed"
                ),
                auto_update=self._auto_update_status(
                    status="ok",
                    update_available=update_available,
                    update_type=update_type,
                    latest_version=latest_version,
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
                release_channel=self.release_channel,
                update_type="unknown",
                alert_level="warning",
                recommended_action="Inspect release connectivity and retry later",
                auto_update=self._auto_update_status(
                    status="unavailable",
                    update_available=False,
                    update_type="unknown",
                ),
                error=str(exc),
            )
            return self._cached
