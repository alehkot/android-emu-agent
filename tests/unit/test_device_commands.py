"""Tests for device CLI commands."""

from __future__ import annotations

from collections.abc import Callable
from unittest.mock import MagicMock, patch

import pytest
import typer
from typer.testing import CliRunner

from android_emu_agent.cli.commands import device

runner = CliRunner()


@pytest.mark.parametrize(
    "command",
    [
        device.device_set_animations,
        device.device_set_stay_awake,
        device.device_set_wifi,
        device.device_set_mobile,
        device.device_set_doze,
    ],
)
def test_binary_device_settings_reject_unknown_state(
    command: Callable[[str, str, bool], None],
) -> None:
    """Unknown state strings must not silently disable a device setting."""
    with (
        patch.object(device, "DaemonClient") as client,
        pytest.raises(typer.BadParameter) as exc_info,
    ):
        command("banana", "emulator-5554", False)

    assert "Expected 'on' or 'off'" in str(exc_info.value)
    client.assert_not_called()


def test_wifi_invalid_state_exits_before_daemon_request() -> None:
    """The rendered CLI should reject an invalid state with usage status 2."""
    with patch.object(device, "DaemonClient") as client:
        result = runner.invoke(
            device.app,
            ["set", "wifi", "banana", "--device", "emulator-5554"],
        )

    assert result.exit_code == 2
    assert "Expected 'on' or 'off'" in result.output
    client.assert_not_called()


@pytest.mark.parametrize(
    ("command", "path"),
    [
        (device.device_set_wifi, "/devices/wifi"),
        (device.device_set_mobile, "/devices/mobile"),
        (device.device_set_doze, "/devices/doze"),
    ],
)
def test_boolean_device_settings_normalize_valid_state(
    command: Callable[[str, str, bool], None],
    path: str,
) -> None:
    """Valid state strings should map to an explicit boolean payload."""
    response = MagicMock()
    response.json.return_value = {"status": "done"}
    client = MagicMock()
    client.request.return_value = response

    with patch.object(device, "DaemonClient", return_value=client):
        command("ON", "emulator-5554", False)

    client.request.assert_called_once_with(
        "POST",
        path,
        json_body={"serial": "emulator-5554", "enabled": True},
    )


def test_string_device_settings_normalize_valid_state() -> None:
    """String-backed daemon settings should receive the canonical lowercase value."""
    response = MagicMock()
    response.json.return_value = {"status": "done"}
    client = MagicMock()
    client.request.return_value = response

    with patch.object(device, "DaemonClient", return_value=client):
        device.device_set_animations("OFF", "emulator-5554", False)

    client.request.assert_called_once_with(
        "POST",
        "/devices/animations",
        json_body={"serial": "emulator-5554", "state": "off"},
    )
