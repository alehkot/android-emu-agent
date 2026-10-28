"""Android permission rejections must not be reported as successful changes."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from adbutils import ShellReturn
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from android_emu_agent.cli.commands import system
from android_emu_agent.daemon import server
from android_emu_agent.system.manager import SystemManager


@pytest.mark.parametrize("operation", ["grant", "revoke"])
@pytest.mark.parametrize("json_output", [False, True], ids=["human", "json"])
@pytest.mark.parametrize("returncode", [0, 1, 255], ids=["success", "rejected", "empty-rejection"])
def test_permission_exit_status_reaches_cli(
    operation: str,
    json_output: bool,
    returncode: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Use real CLI/API/manager; emulate only the ADB boundary, without changing a device."""
    output = (
        "Security exception: Package com.example.app has not requested permission "
        "android.permission.CAMERA\n"
        if returncode == 1
        else ""
    )
    device = MagicMock()
    device.shell.return_value = output  # Old adbutils shell API discards the exit status.
    device.shell2.return_value = ShellReturn("pm", returncode, output)
    core = MagicMock(diagnostics=None, trace_manager=None)
    core.device_manager.get_adb_device = AsyncMock(return_value=device)
    core.device_manager.get_device = AsyncMock(return_value=None)
    core.system_manager = SystemManager()
    monkeypatch.setattr(server.app.state, "core", core, raising=False)
    api = TestClient(server.app)  # No lifespan: no daemon, ADB, or device is started.
    responses: list[httpx.Response] = []

    def request(method: str, path: str, **kwargs: Any) -> httpx.Response:
        assert method == "POST"
        assert path == f"/system/permissions/{operation}"
        response = api.request(method, path, json=kwargs["json_body"])
        responses.append(response)
        return response

    client = MagicMock()
    client.request.side_effect = request
    monkeypatch.setattr(system, "DaemonClient", lambda: client)
    result = CliRunner().invoke(
        system.app,
        [
            "permissions",
            operation,
            "com.example.app",
            "android.permission.CAMERA",
            "--device",
            "emulator-5554",
            *(["--json"] if json_output else []),
        ],
    )
    api.close()
    assert len(responses) == 1
    payload = responses[0].json()
    assert result.exit_code == (1 if returncode else 0)
    if returncode:
        assert responses[0].status_code == 400
        assert payload["error"]["code"] == "ERR_PERMISSION_CHANGE_FAILED"
        assert payload["error"]["context"]["exit_code"] == returncode
        assert payload["error"]["context"]["output"] == output.strip()
        assert "granted" not in payload
        assert "✓ Done" not in result.stdout
        assert ("has not requested permission" if output else "Exit status 255") in result.stdout
    else:
        assert responses[0].status_code == 200
        assert payload["status"] == "done"
        assert payload["granted"] is (operation == "grant")
        assert payload["output"] == ""
        if not json_output:
            assert result.stdout == "✓ Done\n"
    if json_output:
        assert json.loads(result.stdout) == payload
    client.close.assert_called_once_with()
    calls = device.shell.call_args_list + device.shell2.call_args_list
    assert len(calls) == 1  # Never retry a mutation after a returned rejection.
    assert calls[0].args == (f"pm {operation} com.example.app android.permission.CAMERA",)
