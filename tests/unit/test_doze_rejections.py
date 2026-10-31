"""Doze precondition rejections must reach the caller instead of reporting success."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from android_emu_agent.cli.commands import device as device_cli
from android_emu_agent.daemon import server
from android_emu_agent.device import io as device_io
from android_emu_agent.device.manager import DeviceManager


@pytest.mark.parametrize("json_output", [False, True], ids=["human", "json"])
@pytest.mark.parametrize(
    ("state", "output", "rejected"),
    [
        ("on", "Now forced in to deep idle mode\n", False),
        ("off", "Light state: ACTIVE, deep state: ACTIVE\n", False),
        ("on", "Unable to go deep idle; not enabled\n", True),
        ("on", "Unable to go deep idle; stopped at INACTIVE\n", True),
        ("on", "Unable to go idle; not enabled\n", True),
    ],
    ids=["enabled", "unforced", "disabled", "stalled", "legacy-disabled"],
)
def test_doze_result_reaches_cli(
    state: str,
    output: str,
    rejected: bool,
    json_output: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exercise the real CLI, endpoint and manager, faking only device I/O and HTTP transport."""
    # In production daemon logs do not share the invoking CLI's stdout.
    monkeypatch.setattr(device_io, "logger", MagicMock())
    device = MagicMock()
    device.serial = "emulator-5554"
    device.shell.return_value = output
    manager = DeviceManager()
    monkeypatch.setattr(manager, "get_adb_device", AsyncMock(return_value=device))
    core = MagicMock(diagnostics=None, trace_manager=None)
    core.device_manager = manager
    monkeypatch.setattr(server.app.state, "core", core, raising=False)
    responses: list[httpx.Response] = []
    # No lifespan: no daemon, emulator, ADB connection or socket is started.
    api = TestClient(server.app)

    def request(method: str, path: str, **kwargs: Any) -> httpx.Response:
        assert (method, path) == ("POST", "/devices/doze")
        response = api.request(method, path, json=kwargs["json_body"])
        responses.append(response)
        return response

    client = MagicMock()
    client.request.side_effect = request
    monkeypatch.setattr(device_cli, "DaemonClient", lambda: client)
    try:
        result = CliRunner().invoke(
            device_cli.app,
            [
                "set",
                "doze",
                state,
                "--device",
                "emulator-5554",
                *(["--json"] if json_output else []),
            ],
        )
    finally:
        api.close()
    assert len(responses) == 1
    payload = responses[0].json()
    assert result.exit_code == (1 if rejected else 0)
    if rejected:
        assert responses[0].status_code == 400
        assert payload["error"]["code"] == "ERR_DOZE_CHANGE_FAILED"
        assert payload["error"]["context"]["output"] == output.strip()
        assert output.strip() in result.stdout
        assert "doze" not in payload
        assert "✓ Done" not in result.stdout
    else:
        assert responses[0].status_code == 200
        assert payload["status"] == "done"
        assert payload["serial"] == "emulator-5554"
        assert payload["doze"] == state
        if not json_output:
            assert result.stdout == "✓ Done\n"
    if json_output:
        assert json.loads(result.stdout) == payload
    command = "force-idle" if state == "on" else "unforce"
    device.shell.assert_called_once_with(f"dumpsys deviceidle {command}")
    device.shell2.assert_not_called()
    client.close.assert_called_once_with()
