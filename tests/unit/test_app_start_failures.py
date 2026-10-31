"""Activity-manager rejections must reach API and CLI callers as failures."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from adbutils import AdbClient, AdbDevice, ShellReturn
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from android_emu_agent.cli.commands import app_cmd
from android_emu_agent.daemon import server
from android_emu_agent.daemon.models import TaskRunRequest
from android_emu_agent.device import io as device_io
from android_emu_agent.device.manager import DeviceManager
from android_emu_agent.errors import AgentError
from android_emu_agent.tasks import TaskManager


async def start(manager: DeviceManager, operation: str) -> str | None:
    if operation == "launch":
        return await manager.app_launch("emulator-5554", "com.example.app", ".MissingActivity")
    if operation == "deeplink":
        return await manager.app_deeplink("emulator-5554", "example://missing")
    return await manager.app_start_intent(
        "emulator-5554", component="com.example.app/.MissingActivity"
    )


@pytest.mark.parametrize("operation", ["launch", "deeplink", "intent"])
@pytest.mark.parametrize(
    ("returncode", "output"),
    [
        (0, "Starting: Intent { ... }\nError type 3\nError: Activity class does not exist.\n"),
        (0, "Starting: Intent { ... }\nError: Activity not started, unable to resolve Intent\n"),
        (0, " \tError: Activity not started, permission denied\r\n"),
        (0, "Error type 3\n"),
        (1, "Error: Activity class does not exist.\n"),
        (255, ""),
    ],
)
@pytest.mark.asyncio
async def test_android_rejection_is_not_success(
    operation: str, returncode: int, output: str
) -> None:
    manager = DeviceManager()
    device = MagicMock()
    device.shell.return_value = output  # Baseline shell discards both status and diagnostics.
    device.shell2.return_value = ShellReturn("am start", returncode, output)
    manager.get_adb_device = AsyncMock(return_value=device)
    with pytest.raises(AgentError) as exc:
        await start(manager, operation)
    assert exc.value.code == "ERR_LAUNCH_FAILED"
    assert exc.value.remediation
    device.shell2.assert_called_once()
    device.shell.assert_not_called()  # Never retry an already rejected start.


@pytest.mark.parametrize("operation", ["launch", "deeplink", "intent"])
@pytest.mark.parametrize("json_output", [False, True], ids=["human", "json"])
@pytest.mark.parametrize("rejected", [False, True])
def test_cli_api_manager_round_trip(
    monkeypatch: pytest.MonkeyPatch, operation: str, json_output: bool, rejected: bool
) -> None:
    # The real daemon logs elsewhere; keep its in-process test logs out of CLI stdout.
    monkeypatch.setattr(device_io, "logger", MagicMock())
    output = (
        "Error: Activity not started, unable to resolve Intent\n"
        if rejected
        else "Starting: Intent { ... }\nWarning: Activity not started, its task is in front\n"
    )
    device = MagicMock()
    device.shell.return_value = output
    device.shell2.return_value = ShellReturn("am start", 0, output)
    manager = DeviceManager()
    manager.get_adb_device = AsyncMock(return_value=device)
    core = SimpleNamespace(
        device_manager=manager,
        session_manager=SimpleNamespace(
            get_session=AsyncMock(return_value=SimpleNamespace(device_serial="emulator-5554"))
        ),
    )
    monkeypatch.setattr(server.app.state, "core", core, raising=False)
    api = TestClient(server.app)  # No lifespan, daemon socket, emulator, or ADB connection.
    responses: list[httpx.Response] = []

    def request(method: str, path: str, **kwargs: Any) -> httpx.Response:
        response = api.request(method, path, json=kwargs["json_body"])
        responses.append(response)
        return response

    client = MagicMock()
    client.request.side_effect = request
    monkeypatch.setattr(app_cmd, "DaemonClient", lambda: client)
    args = [operation, "s-test"]
    if operation == "launch":
        args.extend(["com.example.app", "--activity", ".MissingActivity"])
    elif operation == "deeplink":
        args.append("example://missing")
    else:
        args.extend(["--component", "com.example.app/.MissingActivity"])
    if json_output:
        args.append("--json")
    try:
        result = CliRunner().invoke(app_cmd.app, args)
    finally:
        api.close()
    assert len(responses) == 1
    payload = responses[0].json()
    assert result.exit_code == (1 if rejected else 0), result.output
    if rejected:
        assert responses[0].status_code == (500 if operation == "launch" else 400)
        assert payload["error"]["code"] == "ERR_LAUNCH_FAILED"
        assert "ERR_DEVICE_OFFLINE" not in result.output
        assert "Done" not in result.output
    else:
        assert responses[0].status_code == 200
        assert payload["status"] == "done"
        if not json_output:
            assert result.stdout == "✓ Done\n"
    if json_output:
        assert json.loads(result.stdout) == payload
    client.close.assert_called_once_with()


@pytest.mark.parametrize(
    "output",
    [
        "Starting: Intent { ... }\n",
        "Warning: Activity not started, intent has been delivered to currently running top-most instance.\n",
        "Warning: Activity not started, its current task has been brought to the front\n",
        "Starting: Intent { dat=example://Error:detail cmp=com.example/.ErrorActivity }\n",
        "Starting: Intent { dat=example://Error%20type%203 }\n",
    ],
)
@pytest.mark.asyncio
async def test_success_warnings_and_embedded_error_text_are_not_failures(output: str) -> None:
    manager = DeviceManager()
    device = MagicMock()
    device.shell2.return_value = ShellReturn("am start", 0, output)
    manager.get_adb_device = AsyncMock(return_value=device)
    assert await start(manager, "launch") == ".MissingActivity"


@pytest.mark.parametrize(
    ("status", "output"), [(0, "Starting: Intent\n"), (0, "Error type 3\n"), (1, "")]
)
@pytest.mark.asyncio
async def test_actual_adbutils_shell2_status_and_output(
    monkeypatch: pytest.MonkeyPatch, status: int, output: str
) -> None:
    device = AdbDevice(AdbClient(), serial="emulator-5554")
    shell = MagicMock(return_value=f"{output}X4EXIT:{status}\n".encode())
    monkeypatch.setattr(device, "shell", shell)
    manager = DeviceManager()
    manager.get_adb_device = AsyncMock(return_value=device)
    if status or output.startswith("Error"):
        with pytest.raises(AgentError) as exc:
            await start(manager, "launch")
        assert exc.value.code == "ERR_LAUNCH_FAILED"
    else:
        assert await start(manager, "launch") == ".MissingActivity"
    assert shell.call_args.args[0] == (
        "am start -n com.example.app/.MissingActivity; echo X4EXIT:$?"
    )


@pytest.mark.parametrize("operation", ["launch", "deeplink", "intent"])
@pytest.mark.asyncio
async def test_transport_errors_are_not_android_rejections(operation: str) -> None:
    manager = DeviceManager()
    device = MagicMock()
    device.shell2.side_effect = OSError("transport disconnected")
    manager.get_adb_device = AsyncMock(return_value=device)
    with pytest.raises(OSError, match="transport disconnected"):
        await start(manager, operation)


@pytest.mark.asyncio
async def test_checked_intent_preserves_quoting_and_debugger_flag() -> None:
    manager = DeviceManager()
    device = MagicMock()
    device.shell2.return_value = ShellReturn("am start", 0, "Starting: Intent\n")
    manager.get_adb_device = AsyncMock(return_value=device)
    await manager.app_start_intent(
        "emulator-5554",
        action="android.intent.action.VIEW",
        data_uri="example://path?a=1&b=2",
        component="com.example.app/.MainActivity",
        wait_for_debugger=True,
    )
    device.shell2.assert_called_once_with(
        "am start -D -a android.intent.action.VIEW -d 'example://path?a=1&b=2' "
        "-n com.example.app/.MainActivity"
    )


@pytest.mark.parametrize("operation", ["launch", "deeplink", "intent"])
def test_endpoint_preserves_transport_error_contract(
    monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    manager = DeviceManager()
    device = MagicMock()
    device.shell2.side_effect = OSError("transport disconnected")
    manager.get_adb_device = AsyncMock(return_value=device)
    core = SimpleNamespace(
        device_manager=manager,
        session_manager=SimpleNamespace(
            get_session=AsyncMock(return_value=SimpleNamespace(device_serial="emulator-5554"))
        ),
    )
    monkeypatch.setattr(server.app.state, "core", core, raising=False)
    body = {"session_id": "s-test"}
    if operation == "launch":
        body.update(package="com.example.app", activity=".MainActivity")
    elif operation == "deeplink":
        body["uri"] = "example://path"
    else:
        body["component"] = "com.example.app/.MainActivity"
    api = TestClient(server.app)
    try:
        response = api.post(f"/app/{operation}", json=body)
    finally:
        api.close()
    assert response.status_code == (500 if operation == "launch" else 404)
    assert response.json()["error"]["code"] == (
        "ERR_LAUNCH_FAILED" if operation == "launch" else "ERR_DEVICE_OFFLINE"
    )


@pytest.mark.parametrize("operation", ["launch", "deeplink"])
@pytest.mark.asyncio
async def test_rejected_start_fails_task_and_stops_later_steps(
    monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    # Intent is not a supported task operation; exercise the two public task paths.
    manager = DeviceManager()
    device = MagicMock()
    device.shell.return_value = "Error: Activity not started, unable to resolve Intent\n"
    device.shell2.return_value = ShellReturn("am start", 0, device.shell.return_value)
    manager.get_adb_device = AsyncMock(return_value=device)
    core = SimpleNamespace(
        device_manager=manager,
        session_manager=SimpleNamespace(
            get_session=AsyncMock(return_value=SimpleNamespace(device_serial="emulator-5554"))
        ),
        task_manager=TaskManager(),
    )
    monkeypatch.setattr(server.app.state, "core", core, raising=False)
    step = (
        {"app": "launch", "package": "com.example.app", "activity": ".MissingActivity"}
        if operation == "launch"
        else {"app": "deeplink", "uri": "example://missing"}
    )
    result = await server.task_run(
        TaskRunRequest(session_id="s-test", task={"steps": [step, step]})
    )
    assert isinstance(result, dict)
    assert result["status"] == "failed"
    assert result["passed"] is False
    assert len(result["steps"]) == 1
    assert result["steps"][0]["response"]["error"]["code"] == "ERR_LAUNCH_FAILED"
    device.shell2.assert_called_once()
