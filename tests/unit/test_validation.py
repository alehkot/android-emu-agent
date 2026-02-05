"""Tests for validation helpers."""

from __future__ import annotations

import pytest

from android_emu_agent.errors import AgentError


class TestValidatePackage:
    """Tests for validate_package."""

    def test_valid_package(self) -> None:
        """Should accept valid package names."""
        from android_emu_agent.validation import validate_package

        # Should not raise
        validate_package("com.example.app")
        validate_package("com.example.my_app")
        validate_package("org.test.App123")

    def test_invalid_package_spaces(self) -> None:
        """Should reject package with spaces."""
        from android_emu_agent.validation import validate_package

        with pytest.raises(AgentError) as exc_info:
            validate_package("com.example app")

        assert exc_info.value.code == "ERR_INVALID_PACKAGE"

    def test_invalid_package_special_chars(self) -> None:
        """Should reject package with special characters."""
        from android_emu_agent.validation import validate_package

        with pytest.raises(AgentError) as exc_info:
            validate_package("com.example!app")

        assert exc_info.value.code == "ERR_INVALID_PACKAGE"

    def test_invalid_package_single_segment(self) -> None:
        """Should reject single-segment package."""
        from android_emu_agent.validation import validate_package

        with pytest.raises(AgentError) as exc_info:
            validate_package("myapp")

        assert exc_info.value.code == "ERR_INVALID_PACKAGE"


class TestValidateUri:
    """Tests for validate_uri."""

    def test_valid_https_uri(self) -> None:
        """Should accept https URI."""
        from android_emu_agent.validation import validate_uri

        validate_uri("https://example.com/path")

    def test_valid_custom_scheme(self) -> None:
        """Should accept custom scheme URI."""
        from android_emu_agent.validation import validate_uri

        validate_uri("myapp://deep/link")

    def test_invalid_no_scheme(self) -> None:
        """Should reject URI without scheme."""
        from android_emu_agent.validation import validate_uri

        with pytest.raises(AgentError) as exc_info:
            validate_uri("example.com/path")

        assert exc_info.value.code == "ERR_INVALID_URI"

    def test_invalid_empty(self) -> None:
        """Should reject empty URI."""
        from android_emu_agent.validation import validate_uri

        with pytest.raises(AgentError) as exc_info:
            validate_uri("")

        assert exc_info.value.code == "ERR_INVALID_URI"


class TestGetConsolePort:
    """Tests for get_console_port."""

    def test_valid_emulator_serial(self) -> None:
        """Should extract port from emulator serial."""
        from android_emu_agent.validation import get_console_port

        assert get_console_port("emulator-5554") == 5554
        assert get_console_port("emulator-5556") == 5556

    def test_invalid_not_emulator(self) -> None:
        """Should raise for non-emulator serial."""
        from android_emu_agent.validation import get_console_port

        with pytest.raises(AgentError) as exc_info:
            get_console_port("device-123")

        assert exc_info.value.code == "ERR_NOT_EMULATOR"

    def test_invalid_format(self) -> None:
        """Should raise for malformed serial."""
        from android_emu_agent.validation import get_console_port

        with pytest.raises(AgentError) as exc_info:
            get_console_port("emulator-abc")

        assert exc_info.value.code == "ERR_NOT_EMULATOR"
