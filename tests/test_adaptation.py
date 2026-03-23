from faigate.adaptation import AdaptiveRouteState, RoutePressure


def test_route_pressure_sets_hard_cooldown_for_auth_invalid() -> None:
    route = RoutePressure(provider_name="anthropic-direct")

    route.record_failure("401 invalid api key")
    snapshot = route.to_dict()

    assert snapshot["last_issue_type"] == "auth-invalid"
    assert snapshot["window_state"] == "cooldown"
    assert snapshot["request_blocked"] is True
    assert snapshot["cooldown_remaining_s"] > 0
    assert snapshot["degraded_remaining_s"] == 0


def test_route_pressure_sets_soft_degrade_window_for_timeout() -> None:
    route = RoutePressure(provider_name="deepseek-chat")

    route.record_failure("Timeout: upstream timed out")
    snapshot = route.to_dict()

    assert snapshot["last_issue_type"] == "timeout"
    assert snapshot["window_state"] == "degraded"
    assert snapshot["request_blocked"] is False
    assert snapshot["degraded_remaining_s"] > 0
    assert snapshot["cooldown_remaining_s"] == 0


def test_adaptive_route_state_provider_snapshot_exposes_window_metadata() -> None:
    state = AdaptiveRouteState()

    state.record_failure("openrouter-fallback", error="unsupported path /models")
    snapshot = state.provider_snapshot("openrouter-fallback")

    assert snapshot["last_issue_type"] == "endpoint-mismatch"
    assert snapshot["window_state"] == "cooldown"
    assert snapshot["cooldown_until"] > 0
