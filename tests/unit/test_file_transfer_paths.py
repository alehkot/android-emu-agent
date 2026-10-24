"""Host transfer paths belong to the CLI caller, not the daemon's working directory."""

from __future__ import annotations

import asyncio
import io
import json
import tarfile
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from typer.testing import CliRunner

from android_emu_agent.cli.commands import file as file_commands
from android_emu_agent.errors import AgentError
from android_emu_agent.files.manager import FileManager


def _wire_daemon(
    monkeypatch: pytest.MonkeyPatch,
    manager: FileManager,
    daemon: Path,
    variant: str,
    direction: str,
) -> list[dict[str, Any]]:
    """Pass real CLI payloads to the real manager under a separate daemon cwd."""
    requests: list[dict[str, Any]] = []
    app_private = variant != "shared"
    timeout = (
        file_commands.FILE_APP_TRANSFER_TIMEOUT
        if app_private
        else file_commands.FILE_TRANSFER_TIMEOUT
    )
    endpoint = f"/files/{'app_' if app_private else ''}{direction}"

    async def transfer(payload: dict[str, Any]) -> str | Path:
        if app_private:
            if direction == "push":
                return await manager.app_push(
                    MagicMock(),
                    "emulator-5554",
                    payload["package"],
                    payload["local_path"],
                    payload["remote_path"],
                    use_root=variant == "app-root",
                )
            return await manager.app_pull(
                MagicMock(),
                "emulator-5554",
                payload["package"],
                payload["remote_path"],
                payload["local_path"],
                use_root=variant == "app-root",
            )
        if direction == "push":
            return await manager.push(
                "emulator-5554", payload["local_path"], payload["remote_path"]
            )
        return await manager.pull("emulator-5554", payload["remote_path"], payload["local_path"])

    class Response:
        def __init__(self, data: dict[str, Any]) -> None:
            self.data = data

        def json(self) -> dict[str, Any]:
            return self.data

    class Client:
        def __init__(self, **kwargs: Any) -> None:
            assert kwargs == {"timeout": timeout}

        def request(self, method: str, path: str, *, json_body: dict[str, Any]) -> Response:
            assert (method, path) == ("POST", endpoint)
            requests.append(json_body)
            with monkeypatch.context() as daemon_context:
                daemon_context.chdir(daemon)
                daemon_context.setenv("HOME", str(daemon))
                try:
                    result = asyncio.run(transfer(json_body))
                except AgentError as exc:
                    return Response({"error": exc.to_dict()})
            return Response({"status": "done", "path": str(result)})

        def close(self) -> None:
            pass

    monkeypatch.setattr(file_commands, "DaemonClient", Client)
    # In production daemon logs are not part of the CLI process's JSON stdout.
    monkeypatch.setattr("android_emu_agent.files.manager.logger", MagicMock())
    monkeypatch.setattr(manager, "_shell_with_optional_root", AsyncMock())
    monkeypatch.setattr(manager, "_shell_app", AsyncMock(return_value="file"))
    monkeypatch.setattr(manager, "_shell", AsyncMock())
    return requests


@pytest.mark.parametrize("variant", ["shared", "app-run-as", "app-root"])
@pytest.mark.parametrize("target", ["--device", "--session"])
@pytest.mark.parametrize("kind", ["file", "directory"])
@pytest.mark.parametrize(
    "path_kind", ["relative", "absolute", "home", "symlink", "symlink-parent", "missing"]
)
def test_push_reads_callers_input(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    variant: str,
    target: str,
    kind: str,
    path_kind: str,
) -> None:
    """Transfer caller bytes, never a same-named file or directory beside the daemon."""
    caller = tmp_path / "caller"
    daemon = tmp_path / "daemon"
    caller.mkdir()
    daemon.mkdir()
    filename = "source data" if kind == "directory" else "config data.json"
    source = caller / filename

    def populate(path: Path, content: bytes) -> None:
        if kind == "directory":
            path.mkdir(parents=True)
            path = path / "config.json"
        path.write_bytes(content)

    if path_kind != "missing":
        populate(source, b"caller data")
    populate(daemon / filename, b"wrong daemon data")
    argument = f"./{filename}"
    expected = source
    if path_kind == "absolute":
        argument = str(source)
    elif path_kind == "home":
        argument = f"~/{filename}"
    elif path_kind == "symlink":
        expected = caller / "alias data"
        expected.symlink_to(source, target_is_directory=kind == "directory")
        argument = expected.name
    elif path_kind == "symlink-parent":
        outside = tmp_path / "outside"
        (outside / "nested").mkdir(parents=True)
        populate(outside / filename, b"caller data")
        (source / "config.json" if kind == "directory" else source).write_bytes(
            b"wrong normalized data"
        )
        (caller / "link").symlink_to(outside / "nested", target_is_directory=True)
        argument = f"link/../{filename}"
        expected = caller / "link" / ".." / filename

    manager = FileManager(output_dir=tmp_path / "artifacts")
    requests = _wire_daemon(monkeypatch, manager, daemon, variant, "push")
    transferred: list[bytes] = []

    async def run_adb(serial: str, args: list[str]) -> None:
        assert serial == "emulator-5554"
        assert args[0] == "push"
        path = Path(args[1])
        transferred.append((path / "config.json" if kind == "directory" else path).read_bytes())

    monkeypatch.setattr(manager, "_run_adb", run_adb)
    monkeypatch.setenv("HOME", str(caller))
    monkeypatch.chdir(caller)
    args = ["push"] if variant == "shared" else ["app", "push", "com.example.app"]
    args.append(argument)
    remote = "files/custom data" if path_kind == "absolute" else None
    if remote is not None:
        args.extend(["--remote", remote])
    target_value = "emulator-5554" if target == "--device" else "s-test"
    result = CliRunner().invoke(file_commands.app, [*args, target, target_value, "--json"])

    data = json.loads(result.stdout)
    if path_kind == "missing":
        assert result.exit_code == 1
        assert data["error"]["code"] == "ERR_FILE_NOT_FOUND"
        assert transferred == []
    else:
        assert result.exit_code == 0, result.output
        assert transferred == [b"caller data"]
        if remote is not None:
            assert data["path"] == (
                remote if variant == "shared" else f"/data/data/com.example.app/{remote}"
            )
        else:
            remote_parent = (
                "/sdcard/Download" if variant == "shared" else "/data/data/com.example.app/files"
            )
            assert data["path"] == f"{remote_parent}/{expected.name}"
    assert requests[0]["local_path"] == str(expected)
    assert requests[0]["remote_path"] == remote
    assert requests[0]["serial" if target == "--device" else "session_id"] == target_value


@pytest.mark.parametrize("variant", ["shared", "app-run-as", "app-root"])
def test_push_current_directory_uses_callers_directory_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, variant: str
) -> None:
    """A dot source names and transfers the caller's directory, not the daemon's."""
    caller = tmp_path / "caller"
    daemon = tmp_path / "daemon"
    caller.mkdir()
    daemon.mkdir()
    (caller / "config.json").write_bytes(b"caller directory data")
    (daemon / "config.json").write_bytes(b"wrong daemon directory data")
    manager = FileManager(output_dir=tmp_path / "artifacts")
    _wire_daemon(monkeypatch, manager, daemon, variant, "push")
    transferred: list[bytes] = []

    async def run_adb(_serial: str, args: list[str]) -> None:
        transferred.append((Path(args[1]) / "config.json").read_bytes())

    monkeypatch.setattr(manager, "_run_adb", run_adb)
    monkeypatch.chdir(caller)
    args = ["push"] if variant == "shared" else ["app", "push", "com.example.app"]
    result = CliRunner().invoke(
        file_commands.app, [*args, ".", "--device", "emulator-5554", "--json"]
    )

    assert result.exit_code == 0, result.output
    assert transferred == [b"caller directory data"]
    remote_parent = (
        "/sdcard/Download" if variant == "shared" else "/data/data/com.example.app/files"
    )
    assert json.loads(result.stdout)["path"] == f"{remote_parent}/{caller.name}"


@pytest.mark.parametrize("variant", ["shared", "app-run-as", "app-root"])
@pytest.mark.parametrize("target", ["--device", "--session"])
@pytest.mark.parametrize(
    "path_kind",
    ["relative", "absolute", "home", "symlink", "symlink-parent", "directory", "omitted", "empty"],
)
def test_pull_writes_callers_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    variant: str,
    target: str,
    path_kind: str,
) -> None:
    """Write through caller paths while preserving automatic output and device paths."""
    caller = tmp_path / "caller"
    daemon = tmp_path / "daemon"
    caller.mkdir()
    daemon.mkdir()
    output_name = "output files/config.json"
    expected = caller / output_name
    argument = output_name
    if path_kind == "absolute":
        argument = str(expected)
    elif path_kind == "home":
        argument = f"~/{output_name}"
    elif path_kind == "symlink":
        actual = caller / "actual.json"
        actual.write_bytes(b"old caller data")
        expected = caller / "linked.json"
        expected.symlink_to(actual)
        argument = expected.name
    elif path_kind == "symlink-parent":
        outside = tmp_path / "outside"
        (outside / "nested").mkdir(parents=True)
        (caller / "link").symlink_to(outside / "nested", target_is_directory=True)
        argument = "link/../config.json"
        expected = caller / "link" / ".." / "config.json"
        (caller / "config.json").write_bytes(b"do not overwrite normalized path")
    elif path_kind == "directory":
        expected = caller / "output directory"
        expected.mkdir()
        argument = expected.name
    elif path_kind == "empty":
        argument = ""
    daemon_decoy = daemon / output_name
    daemon_decoy.parent.mkdir()
    daemon_decoy.write_bytes(b"do not overwrite daemon data")

    manager = FileManager(output_dir=tmp_path / "artifacts")
    requests = _wire_daemon(monkeypatch, manager, daemon, variant, "pull")
    destinations: list[Path] = []
    remote = "files/device data.json"

    async def write_file(destination: Path) -> None:
        destination.write_bytes(b"device data")
        destinations.append(destination)

    async def run_adb(serial: str, args: list[str]) -> None:
        assert serial == "emulator-5554"
        assert args[0] == "pull"
        destination = Path(args[2])
        if destination.is_dir():
            destination /= Path(args[1]).name
        await write_file(destination)

    async def run_adb_to_file(serial: str, _args: list[str], destination: Path) -> None:
        assert serial == "emulator-5554"
        await write_file(destination)

    monkeypatch.setattr(manager, "_run_adb", run_adb)
    monkeypatch.setattr(manager, "_run_adb_to_file", run_adb_to_file)
    monkeypatch.setenv("HOME", str(caller))
    monkeypatch.chdir(caller)
    args = ["pull"] if variant == "shared" else ["app", "pull", "com.example.app"]
    args.append(remote)
    if path_kind != "omitted":
        args.extend(["--local", argument])
    target_value = "emulator-5554" if target == "--device" else "s-test"
    result = CliRunner().invoke(file_commands.app, [*args, target, target_value, "--json"])

    assert result.exit_code == 0, result.output
    assert len(destinations) == 1
    assert destinations[0].read_bytes() == b"device data"
    assert daemon_decoy.read_bytes() == b"do not overwrite daemon data"
    data = json.loads(result.stdout)
    if path_kind in {"omitted", "empty"}:
        assert requests[0]["local_path"] == (None if path_kind == "omitted" else "")
        assert destinations[0].parent == manager.output_dir
        assert data["path"] == str(destinations[0])
    else:
        assert requests[0]["local_path"] == str(expected)
        assert data["path"] == str(expected)
        if path_kind == "directory":
            assert destinations[0].parent == expected
        else:
            assert destinations[0] == expected
            assert expected.read_bytes() == b"device data"
    if path_kind == "symlink":
        assert expected.is_symlink()
        assert (caller / "actual.json").read_bytes() == b"device data"
    elif path_kind == "symlink-parent":
        assert (caller / "config.json").read_bytes() == b"do not overwrite normalized path"
        assert (tmp_path / "outside" / "config.json").read_bytes() == b"device data"
    assert requests[0]["remote_path"] == remote
    assert requests[0]["serial" if target == "--device" else "session_id"] == target_value


@pytest.mark.parametrize("target", ["--device", "--session"])
def test_run_as_directory_pull_extracts_into_callers_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, target: str
) -> None:
    """The archive extraction path must use the caller cwd, not just adb pull paths."""
    caller = tmp_path / "caller"
    daemon = tmp_path / "daemon"
    caller.mkdir()
    daemon.mkdir()
    manager = FileManager(output_dir=tmp_path / "artifacts")
    _wire_daemon(monkeypatch, manager, daemon, "app-run-as", "pull")
    monkeypatch.setattr(manager, "_shell_app", AsyncMock(return_value="dir"))

    async def write_archive(_serial: str, _args: list[str], destination: Path) -> None:
        payload = b"device directory data"
        with tarfile.open(destination, "w") as archive:
            entry = tarfile.TarInfo("nested/config.json")
            entry.size = len(payload)
            archive.addfile(entry, io.BytesIO(payload))

    monkeypatch.setattr(manager, "_run_adb_to_file", write_archive)
    monkeypatch.chdir(caller)
    target_value = "emulator-5554" if target == "--device" else "s-test"
    result = CliRunner().invoke(
        file_commands.app,
        [
            "app",
            "pull",
            "com.example.app",
            "files",
            "--local",
            "pulled directory",
            target,
            target_value,
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    assert (caller / "pulled directory/nested/config.json").read_bytes() == b"device directory data"
    assert not (daemon / "pulled directory").exists()
