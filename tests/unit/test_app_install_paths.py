"""APK installation paths belong to the invoking CLI, not the daemon's cwd."""

from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest
from typer.testing import CliRunner

from android_emu_agent.cli.commands import app_cmd
from android_emu_agent.device.manager import DeviceManager
from android_emu_agent.errors import AgentError


@pytest.mark.parametrize("target", ["--device", "--session"])
@pytest.mark.parametrize(
    "path_kind", ["relative", "absolute", "home", "symlink", "symlink-parent", "missing"]
)
def test_install_uses_callers_apk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, target: str, path_kind: str
) -> None:
    """Exercise CLI payload and real manager path validation across distinct cwd values."""
    caller = tmp_path / "caller"
    daemon = tmp_path / "daemon"
    caller.mkdir()
    daemon.mkdir()
    filename = "app debug.apk"
    apk = caller / filename
    if path_kind != "missing":
        apk.write_bytes(b"caller APK")
    (daemon / filename).write_bytes(b"wrong daemon APK")
    monkeypatch.setenv("HOME", str(caller))
    monkeypatch.chdir(caller)
    argument = f"./{filename}"
    if path_kind == "absolute":
        argument = str(apk)
    elif path_kind == "home":
        argument = f"~/{filename}"
    elif path_kind == "symlink":
        (caller / "linked.apk").symlink_to(apk)
        argument = "linked.apk"

    elif path_kind == "symlink-parent":
        outside = tmp_path / "outside"
        (outside / "nested").mkdir(parents=True)
        (outside / filename).write_bytes(b"caller APK")
        apk.write_bytes(b"wrong normalized APK")
        (caller / "link").symlink_to(outside / "nested", target_is_directory=True)
        argument = f"link/../{filename}"

    manager = DeviceManager()
    monkeypatch.setattr(manager, "get_adb_device", AsyncMock(return_value=object()))
    installed: list[bytes] = []
    requests: list[dict[str, Any]] = []
    closed: list[bool] = []

    async def run_adb(serial: str, args: list[str]) -> subprocess.CompletedProcess[str]:
        assert serial == "emulator-5554"
        assert args[:-1] == ["install", "-g", "-d"]
        installed.append(Path(args[-1]).read_bytes())
        return subprocess.CompletedProcess(args, 0, stdout="Success", stderr="")

    monkeypatch.setattr(manager, "_run_adb", run_adb)

    class Response:
        def __init__(self, data: dict[str, Any]) -> None:
            self.data = data

        def json(self) -> dict[str, Any]:
            return self.data

    class Client:
        def __init__(self, *, timeout: float) -> None:
            assert timeout == app_cmd.APP_INSTALL_TIMEOUT

        def request(self, method: str, path: str, *, json_body: dict[str, Any]) -> Response:
            assert (method, path) == ("POST", "/app/install")
            requests.append(json_body)
            # Simulate an already-running daemon launched in a different directory.
            with monkeypatch.context() as daemon_context:
                daemon_context.chdir(daemon)
                try:
                    output = asyncio.run(
                        manager.app_install(
                            "emulator-5554",
                            json_body["apk_path"],
                            replace=json_body["replace"],
                            grant_permissions=json_body["grant_permissions"],
                            allow_downgrade=json_body["allow_downgrade"],
                        )
                    )
                except AgentError as exc:
                    return Response({"error": exc.to_dict()})
            return Response({"status": "done", "output": output})

        def close(self) -> None:
            closed.append(True)

    monkeypatch.setattr(app_cmd, "DaemonClient", Client)
    target_value = "emulator-5554" if target == "--device" else "s-test"
    result = CliRunner().invoke(
        app_cmd.app,
        [
            "install",
            argument,
            target,
            target_value,
            "--no-replace",
            "--grant-permissions",
            "--allow-downgrade",
            "--json",
        ],
    )
    assert closed == [True]
    assert requests[0].get("serial" if target == "--device" else "session_id") == target_value
    expected_path = caller / ("linked.apk" if path_kind == "symlink" else filename)
    if path_kind == "symlink-parent":
        expected_path = caller / "link" / ".." / filename
    assert requests[0]["apk_path"] == str(expected_path)
    data = json.loads(result.stdout)
    if path_kind == "missing":
        assert result.exit_code == 1
        assert data["error"]["code"] == "ERR_FILE_NOT_FOUND"
        assert installed == []
    else:
        assert result.exit_code == 0, result.output
        assert data == {"status": "done", "output": "Success"}
        assert installed == [b"caller APK"]
