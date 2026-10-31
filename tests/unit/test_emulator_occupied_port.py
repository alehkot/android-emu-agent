"""Do not report an existing emulator as a newly launched AVD."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from android_emu_agent.cli.commands import emulator
from android_emu_agent.daemon import server
from android_emu_agent.device.manager import DeviceManager
from android_emu_agent.errors import AgentError


@pytest.fixture
def manager(monkeypatch: pytest.MonkeyPatch) -> DeviceManager:
    manager = DeviceManager()
    monkeypatch.setattr(manager, "emulator_list_avds", AsyncMock(return_value=["New_AVD"]))
    monkeypatch.setattr(manager, "_resolve_sdk_tool", lambda _name: Path("/sdk/emulator"))
    monkeypatch.setattr(
        manager, "_list_running_emulator_serials", AsyncMock(return_value={"emulator-5554"})
    )
    monkeypatch.setattr(
        manager, "_spawn_emulator_process", AsyncMock(return_value=MagicMock(pid=42))
    )
    monkeypatch.setattr(
        manager, "_wait_for_new_emulator_serial", AsyncMock(return_value="emulator-5556")
    )
    monkeypatch.setattr(manager, "_wait_for_emulator_ready", AsyncMock())
    monkeypatch.setattr(manager, "_terminate_emulator_process", AsyncMock())
    return manager


@pytest.mark.asyncio
@pytest.mark.parametrize("wait_boot", [True, False])
async def test_occupied_port_is_rejected_without_touching_emulator(
    manager: DeviceManager, wait_boot: bool
) -> None:
    with pytest.raises(AgentError) as exc:
        await manager.emulator_start("New_AVD", port=5554, wait_boot=wait_boot)
    assert exc.value.code == "ERR_EMULATOR_LAUNCH_FAILED"
    assert "5554" in exc.value.message
    assert "choose a free port" in exc.value.message
    manager._spawn_emulator_process.assert_not_awaited()  # type: ignore[attr-defined]
    manager._wait_for_new_emulator_serial.assert_not_awaited()  # type: ignore[attr-defined]
    manager._wait_for_emulator_ready.assert_not_awaited()  # type: ignore[attr-defined]
    manager._terminate_emulator_process.assert_not_awaited()  # type: ignore[attr-defined]


@pytest.mark.asyncio
@pytest.mark.parametrize("port", [None, 5556])
@pytest.mark.parametrize("wait_boot", [True, False])
async def test_free_or_automatic_port_preserves_launch(
    manager: DeviceManager, port: int | None, wait_boot: bool
) -> None:
    result = await manager.emulator_start("New_AVD", port=port, wait_boot=wait_boot)
    assert result["pid"] == 42
    assert result["serial"] == ("emulator-5556" if wait_boot or port else None)
    manager._spawn_emulator_process.assert_awaited_once()  # type: ignore[attr-defined]
    manager._terminate_emulator_process.assert_not_awaited()  # type: ignore[attr-defined]


@pytest.mark.parametrize("json_output", [False, True])
@pytest.mark.parametrize("wait_boot", [True, False])
def test_real_endpoint_failure_reaches_cli(
    manager: DeviceManager,
    monkeypatch: pytest.MonkeyPatch,
    json_output: bool,
    wait_boot: bool,
) -> None:
    core = MagicMock(device_manager=manager, diagnostics=None, trace_manager=None)
    monkeypatch.setattr(server.app.state, "core", core, raising=False)
    client = MagicMock()
    api = TestClient(server.app)  # No lifespan: no real device/daemon startup.
    client.request.side_effect = lambda method, path, **kwargs: api.request(
        method, path, json=kwargs["json_body"]
    )
    monkeypatch.setattr(emulator, "DaemonClient", lambda **_kwargs: client)
    args = ["start", "New_AVD", "--port", "5554"]
    if not wait_boot:
        args.append("--no-wait-boot")
    if json_output:
        args.append("--json")
    try:
        result = CliRunner().invoke(emulator.app, args)
    finally:
        api.close()
    assert result.exit_code == 1
    assert "ERR_EMULATOR_LAUNCH_FAILED" in result.stdout
    if json_output:
        assert json.loads(result.stdout)["error"]["context"]["avd_name"] == "New_AVD"
    manager._spawn_emulator_process.assert_not_awaited()  # type: ignore[attr-defined]
    manager._terminate_emulator_process.assert_not_awaited()  # type: ignore[attr-defined]
    client.close.assert_called_once()
