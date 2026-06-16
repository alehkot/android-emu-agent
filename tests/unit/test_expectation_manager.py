"""Tests for expectation result shaping."""

from __future__ import annotations

from android_emu_agent.expectations import ExpectationManager


def test_wait_response_success_passes_expectation() -> None:
    """Successful wait responses should become passed expectations."""
    manager = ExpectationManager()

    result = manager.from_wait_response(
        assertion="text",
        session_id="s-abc123",
        expected={"text": "Ready"},
        response={"status": "done", "elapsed_ms": 1.5},
    )

    assert result["status"] == "done"
    assert result["passed"] is True
    assert result["expected"] == {"text": "Ready"}


def test_wait_response_timeout_fails_expectation() -> None:
    """Timed-out wait responses should become assertion failures."""
    manager = ExpectationManager()

    result = manager.from_wait_response(
        assertion="exists",
        session_id="s-abc123",
        expected={"text": "Checkout"},
        response={"status": "timeout", "error": {"code": "ERR_TIMEOUT"}},
    )

    assert result["status"] == "error"
    assert result["passed"] is False
    assert result["error"]["code"] == "ERR_EXPECTATION_FAILED"
    assert result["actual"]["error"]["code"] == "ERR_TIMEOUT"


def test_wait_response_infrastructure_error_is_preserved() -> None:
    """Non-condition errors should not be hidden as expectation failures."""
    manager = ExpectationManager()

    result = manager.from_wait_response(
        assertion="text",
        session_id="s-missing",
        expected={"text": "Ready"},
        response={
            "status": "error",
            "error": {"code": "ERR_SESSION_EXPIRED", "message": "Session expired"},
        },
    )

    assert result["status"] == "error"
    assert result["error"]["code"] == "ERR_SESSION_EXPIRED"


def test_current_app_matches_package_and_activity_substring() -> None:
    """Current-app assertions should accept activity substrings."""
    manager = ExpectationManager()

    result = manager.current_app(
        session_id="s-abc123",
        expected_package="com.example",
        expected_activity="MainActivity",
        response={
            "status": "done",
            "package": "com.example",
            "activity": ".MainActivity",
            "component": "com.example/.MainActivity",
        },
    )

    assert result["status"] == "done"
    assert result["passed"] is True


def test_current_app_mismatch_fails_expectation() -> None:
    """Mismatched foreground app should fail with expectation context."""
    manager = ExpectationManager()

    result = manager.current_app(
        session_id="s-abc123",
        expected_package="com.other",
        expected_activity=None,
        response={
            "status": "done",
            "package": "com.example",
            "activity": ".MainActivity",
        },
    )

    assert result["status"] == "error"
    assert result["expected"]["package"] == "com.other"
    assert result["actual"]["package"] == "com.example"


def test_current_app_infrastructure_error_is_preserved() -> None:
    """Current-app assertion should preserve upstream app/current errors."""
    manager = ExpectationManager()

    result = manager.current_app(
        session_id="s-missing",
        expected_package="com.example",
        expected_activity=None,
        response={
            "status": "error",
            "error": {"code": "ERR_SESSION_EXPIRED", "message": "Session expired"},
        },
    )

    assert result["status"] == "error"
    assert result["error"]["code"] == "ERR_SESSION_EXPIRED"
