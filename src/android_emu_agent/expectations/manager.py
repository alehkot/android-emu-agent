"""Expectation result shaping for assertion-style commands."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class ExpectationManager:
    """Converts daemon observations into explicit assertion results."""

    def passed(
        self,
        *,
        assertion: str,
        session_id: str,
        expected: Mapping[str, Any],
        actual: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Return a successful expectation payload."""
        return {
            "status": "done",
            "passed": True,
            "assertion": assertion,
            "session_id": session_id,
            "expected": dict(expected),
            "actual": dict(actual),
        }

    def from_wait_response(
        self,
        *,
        assertion: str,
        session_id: str,
        expected: Mapping[str, Any],
        response: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Convert an existing wait response into an expectation result."""
        if response.get("status") == "done":
            return self.passed(
                assertion=assertion,
                session_id=session_id,
                expected=expected,
                actual=response,
            )
        if not self._is_unmet_condition(response):
            return dict(response)
        return self.failed(
            assertion=assertion,
            session_id=session_id,
            expected=expected,
            actual=response,
            remediation="Verify the screen state, adjust the selector, or increase --timeout-ms.",
        )

    def current_app(
        self,
        *,
        session_id: str,
        expected_package: str | None,
        expected_activity: str | None,
        response: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Assert the current foreground app/activity matches expectations."""
        expected = {
            "package": expected_package,
            "activity": expected_activity,
        }
        if response.get("status") != "done":
            return dict(response)

        actual_package = response.get("package")
        actual_activity = response.get("activity")
        actual_component = response.get("component")
        package_matches = expected_package is None or actual_package == expected_package
        activity_matches = expected_activity is None or self._activity_matches(
            expected_activity,
            actual_activity,
            actual_component,
        )
        if package_matches and activity_matches:
            return self.passed(
                assertion="current_app",
                session_id=session_id,
                expected=expected,
                actual=response,
            )

        return self.failed(
            assertion="current_app",
            session_id=session_id,
            expected=expected,
            actual=response,
            remediation="Launch or navigate to the expected app/activity, then retry.",
        )

    def failed(
        self,
        *,
        assertion: str,
        session_id: str,
        expected: Mapping[str, Any],
        actual: Mapping[str, Any],
        remediation: str,
    ) -> dict[str, Any]:
        """Return a failed expectation payload."""
        return {
            "status": "error",
            "passed": False,
            "assertion": assertion,
            "session_id": session_id,
            "expected": dict(expected),
            "actual": dict(actual),
            "error": {
                "code": "ERR_EXPECTATION_FAILED",
                "message": f"Expectation failed: {assertion}",
                "context": {
                    "expected": dict(expected),
                    "actual": dict(actual),
                },
                "remediation": remediation,
            },
        }

    @staticmethod
    def _activity_matches(
        expected_activity: str,
        actual_activity: Any,
        actual_component: Any,
    ) -> bool:
        for value in (actual_activity, actual_component):
            if isinstance(value, str) and expected_activity in value:
                return True
        return False

    @staticmethod
    def _is_unmet_condition(response: Mapping[str, Any]) -> bool:
        if response.get("status") == "timeout":
            return True
        error = response.get("error")
        return isinstance(error, Mapping) and error.get("code") == "ERR_TIMEOUT"
