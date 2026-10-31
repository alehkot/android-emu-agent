"""Reset must not report a clean slate when Android rejects pm clear."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from android_emu_agent.cli.commands import app_cmd
from android_emu_agent.cli.main import app as cli_app
from android_emu_agent.daemon import server
from android_emu_agent.device.manager import DeviceManager
from android_emu_agent.errors import AgentError


@pytest.mark.parametrize(
    ("returncode", "output"),
    [(1, "Failed\n"), (1, "Security exception: permission denied\n"), (2, ""), (1, "Success\n")],
)
@pytest.mark.asyncio
async def test_reset_rejects_remote_failure(returncode: int, output: str) -> None:
    manager = DeviceManager()
    device = MagicMock()
    device.shell.return_value = output
    device.shell2.return_value = SimpleNamespace(returncode=returncode, output=output)
    manager.get_adb_device = AsyncMock(return_value=device)

    with pytest.raises(AgentError) as exc:
        await manager.app_reset("emulator-5554", "com.example.app")

    assert exc.value.code == "ERR_ADB_COMMAND"
    assert exc.value.context["command"] == "pm clear com.example.app"
    assert exc.value.context["reason"] == (output.strip() or f"Exit status {returncode}")
    device.shell2.assert_called_once_with("pm clear com.example.app")
    device.shell.assert_not_called()


@pytest.mark.parametrize("output", ["Success\n", "Success\r\n", "warning\nSuccess\n", ""])
@pytest.mark.asyncio
async def test_reset_preserves_success(output: str) -> None:
    manager = DeviceManager()
    device = MagicMock()
    device.shell2.return_value = SimpleNamespace(returncode=0, output=output)
    manager.get_adb_device = AsyncMock(return_value=device)
    assert await manager.app_reset("emulator-5554", "com.example.app") is None


@pytest.mark.parametrize("json_output", [False, True])
@pytest.mark.parametrize("returncode", [0, 1])
def test_reset_cli_endpoint_manager_round_trip(
    monkeypatch: pytest.MonkeyPatch, returncode: int, json_output: bool
) -> None:
    manager = DeviceManager()
    device = MagicMock()
    output = "Success\n" if returncode == 0 else "Failed\n"
    device.shell.return_value = output
    device.shell2.return_value = SimpleNamespace(returncode=returncode, output=output)
    manager.get_adb_device = AsyncMock(return_value=device)
    core = SimpleNamespace(
        device_manager=manager,
        session_manager=SimpleNamespace(
            get_session=AsyncMock(return_value=SimpleNamespace(device_serial="emulator-5554"))
        ),
    )
    monkeypatch.setattr(server.app.state, "core", core, raising=False)
    api = TestClient(server.app)

    class Client:
        def request(self, method: str, path: str, *, json_body: dict[str, str]):
            return api.request(method, path, json=json_body)

        def close(self) -> None:
            api.close()

    monkeypatch.setattr(app_cmd, "DaemonClient", Client)
    args = ["app", "reset", "s-test", "com.example.app"]
    if json_output:
        args.append("--json")
    result = CliRunner().invoke(cli_app, args)
    assert result.exit_code == (0 if returncode == 0 else 1), result.output
    if returncode:
        assert "ERR_ADB_COMMAND" in result.output
        assert "ERR_DEVICE_OFFLINE" not in result.output
        assert "Done" not in result.output
    else:
        assert ("done" if json_output else "Done") in result.output


@pytest.mark.parametrize(("status", "output"), [(0, "Success\n"), (1, "Failed\n"), (1, "")])
@pytest.mark.asyncio
async def test_reset_uses_real_adbutils_exit_status(
    monkeypatch: pytest.MonkeyPatch, status: int, output: str
) -> None:
    from adbutils import AdbClient, AdbDevice

    device = AdbDevice(AdbClient(), serial="emulator-5554")
    shell = MagicMock(return_value=f"{output}X4EXIT:{status}\n".encode())
    monkeypatch.setattr(device, "shell", shell)
    manager = DeviceManager()
    manager.get_adb_device = AsyncMock(return_value=device)
    if status:
        with pytest.raises(AgentError, match="adb command failed"):
            await manager.app_reset("emulator-5554", "com.example.app")
    else:
        assert await manager.app_reset("emulator-5554", "com.example.app") is None
    assert shell.call_args.args[0] == "pm clear com.example.app; echo X4EXIT:$?"


@pytest.mark.parametrize(
    "failure", [RuntimeError("device disconnected"), OSError("transport failed")]
)
@pytest.mark.asyncio
async def test_reset_preserves_transport_failure(failure: Exception) -> None:
    manager = DeviceManager()
    device = MagicMock()
    device.shell2.side_effect = failure
    manager.get_adb_device = AsyncMock(return_value=device)
    with pytest.raises(type(failure), match=str(failure)):
        await manager.app_reset("emulator-5554", "com.example.app")


@pytest.mark.asyncio
async def test_reset_preserves_missing_device_failure() -> None:
    manager = DeviceManager()
    manager.get_adb_device = AsyncMock(return_value=None)
    with pytest.raises(RuntimeError, match="Device not found"):
        await manager.app_reset("emulator-5554", "com.example.app")


def test_reset_endpoint_preserves_offline_error(monkeypatch: pytest.MonkeyPatch) -> None:
    core = SimpleNamespace(
        device_manager=SimpleNamespace(
            app_reset=AsyncMock(side_effect=OSError("transport failed"))
        ),
        session_manager=SimpleNamespace(
            get_session=AsyncMock(return_value=SimpleNamespace(device_serial="emulator-5554"))
        ),
    )
    monkeypatch.setattr(server.app.state, "core", core, raising=False)
    api = TestClient(server.app)
    try:
        response = api.post(
            "/app/reset", json={"session_id": "s-test", "package": "com.example.app"}
        )
    finally:
        api.close()
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ERR_DEVICE_OFFLINE"
