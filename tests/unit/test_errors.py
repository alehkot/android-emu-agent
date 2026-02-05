"""Tests for error model."""

from __future__ import annotations

from android_emu_agent.errors import (
    AgentError,
    blocked_input_error,
    device_offline_error,
    not_found_error,
    stale_ref_error,
    timeout_error,
)


class TestAgentError:
    """Tests for AgentError."""

    def test_error_str(self) -> None:
        """Should format error as string."""
        error = AgentError(
            code="ERR_TEST",
            message="Test error",
            context={},
            remediation="Fix it",
        )
        assert str(error) == "[ERR_TEST] Test error"

    def test_error_to_dict(self) -> None:
        """Should convert to dict."""
        error = AgentError(
            code="ERR_TEST",
            message="Test error",
            context={"key": "value"},
            remediation="Fix it",
        )
        result = error.to_dict()

        assert result["code"] == "ERR_TEST"
        assert result["message"] == "Test error"
        assert result["context"] == {"key": "value"}
        assert result["remediation"] == "Fix it"


class TestErrorConstructors:
    """Tests for error constructor functions."""

    def test_stale_ref_error(self) -> None:
        """Should create stale ref error."""
        error = stale_ref_error("@a1", ref_generation=1, current_generation=5)

        assert error.code == "ERR_STALE_REF"
        assert "@a1" in error.message
        assert error.context["ref"] == "@a1"
        assert "snapshot" in error.remediation.lower()

    def test_not_found_error(self) -> None:
        """Should create not found error."""
        error = not_found_error("@a5")

        assert error.code == "ERR_NOT_FOUND"
        assert "@a5" in error.message

    def test_blocked_input_error(self) -> None:
        """Should create blocked input error."""
        error = blocked_input_error("system dialog visible")

        assert error.code == "ERR_BLOCKED_INPUT"
        assert "system dialog" in error.message

    def test_timeout_error(self) -> None:
        """Should create timeout error."""
        error = timeout_error("wait_for_text", timeout_ms=5000)

        assert error.code == "ERR_TIMEOUT"
        assert error.context["timeout_ms"] == 5000

    def test_device_offline_error(self) -> None:
        """Should create device offline error."""
        error = device_offline_error("emulator-5554")

        assert error.code == "ERR_DEVICE_OFFLINE"
        assert "emulator-5554" in error.message
        assert "devices list" in error.remediation

    def test_not_emulator_error(self) -> None:
        """Should create not-emulator error."""
        from android_emu_agent.errors import not_emulator_error

        error = not_emulator_error("device-123")
        assert error.code == "ERR_NOT_EMULATOR"
        assert "device-123" in error.message
        assert "emulator" in error.remediation.lower()

    def test_console_connect_error(self) -> None:
        """Should create console connect error."""
        from android_emu_agent.errors import console_connect_error

        error = console_connect_error(5554)
        assert error.code == "ERR_CONSOLE_CONNECT"
        assert "5554" in error.message

    def test_snapshot_failed_error(self) -> None:
        """Should create snapshot failed error."""
        from android_emu_agent.errors import snapshot_failed_error

        error = snapshot_failed_error("baseline", "not found")
        assert error.code == "ERR_SNAPSHOT_FAILED"
        assert "baseline" in error.message

    def test_invalid_package_error(self) -> None:
        """Should create invalid package error."""
        from android_emu_agent.errors import invalid_package_error

        error = invalid_package_error("bad package!")
        assert error.code == "ERR_INVALID_PACKAGE"
        assert "bad package!" in error.message

    def test_package_not_found_error(self) -> None:
        """Should create package not found error."""
        from android_emu_agent.errors import package_not_found_error

        error = package_not_found_error("com.missing.app")
        assert error.code == "ERR_PACKAGE_NOT_FOUND"
        assert "com.missing.app" in error.message

    def test_launch_failed_error(self) -> None:
        """Should create launch failed error."""
        from android_emu_agent.errors import launch_failed_error

        error = launch_failed_error("com.test.app", "Activity not found")
        assert error.code == "ERR_LAUNCH_FAILED"
        assert "com.test.app" in error.message

    def test_invalid_uri_error(self) -> None:
        """Should create invalid URI error."""
        from android_emu_agent.errors import invalid_uri_error

        error = invalid_uri_error("not-a-uri")
        assert error.code == "ERR_INVALID_URI"
        assert "not-a-uri" in error.message

    def test_invalid_selector_error(self) -> None:
        """Should create invalid selector error."""
        from android_emu_agent.errors import invalid_selector_error

        error = invalid_selector_error("bad:selector")
        assert error.code == "ERR_INVALID_SELECTOR"
        assert "bad:selector" in error.message
