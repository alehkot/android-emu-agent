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

    @pytest.mark.parametrize(
        "uri",
        [
            "mailto:user@example.com",
            "tel:+15551234567",
            "content:com.example.provider/items/1",
            "market:details?id=com.example.app",
        ],
    )
    def test_valid_opaque_android_uri(self, uri: str) -> None:
        """Should accept Android intent URIs that do not use a double-slash authority."""
        from android_emu_agent.validation import validate_uri

        validate_uri(uri)

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

    @pytest.mark.parametrize("uri", ["mailto:", "1app:value", "my app:value", "tel:+1 555"])
    def test_invalid_uri_syntax(self, uri: str) -> None:
        """Should reject missing values, invalid schemes, and raw whitespace."""
        from android_emu_agent.validation import validate_uri

        with pytest.raises(AgentError) as exc_info:
            validate_uri(uri)

        assert exc_info.value.code == "ERR_INVALID_URI"


class TestValidateSnapshotName:
    @pytest.mark.parametrize("name", ["baseline", "clean.boot-1", "_quick_boot"])
    def test_valid_snapshot_name(self, name: str) -> None:
        from android_emu_agent.validation import validate_snapshot_name

        validate_snapshot_name(name)

    @pytest.mark.parametrize("name", ["", "has space", "baseline\navd kill", "x" * 129])
    def test_invalid_snapshot_name(self, name: str) -> None:
        from android_emu_agent.validation import validate_snapshot_name

        with pytest.raises(AgentError) as exc_info:
            validate_snapshot_name(name)

        assert exc_info.value.code == "ERR_INVALID_SNAPSHOT_NAME"


class TestValidateEmulatorPort:
    @pytest.mark.parametrize("port", [5554, 5556, 5584])
    def test_valid_emulator_port(self, port: int) -> None:
        from android_emu_agent.validation import validate_emulator_port

        validate_emulator_port(port)

    @pytest.mark.parametrize("port", [0, 5553, 5555, 5585])
    def test_invalid_emulator_port(self, port: int) -> None:
        from android_emu_agent.validation import validate_emulator_port

        with pytest.raises(AgentError) as exc_info:
            validate_emulator_port(port)

        assert exc_info.value.code == "ERR_INVALID_EMULATOR_PORT"


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

    @pytest.mark.parametrize(
        "serial",
        ["emulator-abc", "emulator-5554-extra", "emulator-5554 ", "emulator-"],
    )
    def test_invalid_format(self, serial: str) -> None:
        """Should raise for malformed serial."""
        from android_emu_agent.validation import get_console_port

        with pytest.raises(AgentError) as exc_info:
            get_console_port(serial)

        assert exc_info.value.code == "ERR_NOT_EMULATOR"
