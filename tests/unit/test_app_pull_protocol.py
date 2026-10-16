"""App-private pull transport wiring; no live ADB/device is required."""

from __future__ import annotations

import io
import shlex
import subprocess
import tarfile
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from android_emu_agent.errors import AgentError
from android_emu_agent.files.manager import FileManager


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["file", "dir"])
@pytest.mark.parametrize("suffix", ["space name", "it's;$(id)\nquoted", "binary.bin"])
async def test_app_pull_uses_quoted_status_aware_shell(
    tmp_path: Path, kind: str, suffix: str
) -> None:
    """Both stream commands preserve literal shell metacharacters in remote paths."""
    manager = FileManager(output_dir=tmp_path)
    remote = f"/data/data/com.example.app/files/{suffix}"

    async def stream(_serial: str, args: list[str], destination: Path) -> None:
        assert args[:3] == ["shell", "-T", "-n"]
        assert len(args) == 4
        expected = ["run-as", "com.example.app"]
        expected += ["cat", remote] if kind == "file" else ["tar", "-C", remote, "-cf", "-", "."]
        assert shlex.split(args[3]) == expected
        if kind == "dir":
            with tarfile.open(destination, "w"):
                pass

    with (
        patch.object(manager, "_shell_app", new=AsyncMock(return_value=kind)),
        patch.object(manager, "_run_adb_to_file", new=AsyncMock(side_effect=stream)) as transfer,
    ):
        await manager.app_pull(
            MagicMock(),
            "emulator-5554",
            "com.example.app",
            f"files/{suffix}",
            str(tmp_path / "result"),
            use_root=False,
        )
    transfer.assert_awaited_once()


@pytest.mark.asyncio
async def test_app_pull_writes_binary_stdout_without_stderr(tmp_path: Path) -> None:
    """The subprocess receives a binary file handle and a separate stderr pipe."""
    manager = FileManager(output_dir=tmp_path)
    destination = tmp_path / "result.bin"
    payload = b"\x00\xff\xfe\r\n\n\r\x00"

    def run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        assert command == [
            "/test/adb",
            "-s",
            "emulator-5554",
            "shell",
            "-T",
            "-n",
            "run-as com.example.app cat /data/data/com.example.app/files/source.bin",
        ]
        assert kwargs["check"] is True
        assert kwargs["stderr"] == subprocess.PIPE
        assert kwargs["timeout"] == 600
        kwargs["stdout"].write(payload)
        return subprocess.CompletedProcess(command, 0, stderr=b"diagnostic only\n")

    with (
        patch.object(manager, "_shell_app", new=AsyncMock(return_value="file")),
        patch("android_emu_agent.files.manager.shutil.which", return_value="/test/adb"),
        patch("android_emu_agent.files.manager.subprocess.run", side_effect=run),
    ):
        await manager.app_pull(
            MagicMock(),
            "emulator-5554",
            "com.example.app",
            "files/source.bin",
            str(destination),
            use_root=False,
        )
    assert destination.read_bytes() == payload


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["file", "dir"])
@pytest.mark.parametrize("reason", [b"run-as: denied\xff", b"device does not support shell v2"])
async def test_app_pull_propagates_remote_failure_without_fallback(
    tmp_path: Path, kind: str, reason: bytes
) -> None:
    """Nonzero ADB status aborts both pulls, even with a readable tar on stdout."""
    manager = FileManager(output_dir=tmp_path)
    destination = tmp_path / "result"
    if kind == "dir":
        destination.mkdir()
        (destination / "existing.txt").write_bytes(b"keep")

    def run(command: list[str], **kwargs: Any) -> None:
        assert command[3:6] == ["shell", "-T", "-n"]
        assert kwargs["check"] is True
        if kind == "dir":
            with tarfile.open(fileobj=kwargs["stdout"], mode="w") as archive:
                member = tarfile.TarInfo("existing.txt")
                member.size = 7
                archive.addfile(member, io.BytesIO(b"replace"))
        else:
            kwargs["stdout"].write(b"partial")
        raise subprocess.CalledProcessError(1, command, stderr=reason)

    with (
        patch.object(manager, "_shell_app", new=AsyncMock(return_value=kind)),
        patch("android_emu_agent.files.manager.shutil.which", return_value="/test/adb"),
        patch("android_emu_agent.files.manager.subprocess.run", side_effect=run) as process,
        patch("android_emu_agent.files.manager.tarfile.open", wraps=tarfile.open) as archive_open,
        pytest.raises(AgentError) as error,
    ):
        await manager.app_pull(
            MagicMock(),
            "emulator-5554",
            "com.example.app",
            "files/source",
            str(destination),
            use_root=False,
        )
    assert error.value.code == "ERR_ADB_COMMAND"
    assert error.value.context["reason"] == reason.decode("utf-8", errors="replace")
    process.assert_called_once()
    # Only the fake process's write is allowed; extraction must never begin.
    assert archive_open.call_count == (1 if kind == "dir" else 0)
    if kind == "dir":
        assert (destination / "existing.txt").read_bytes() == b"keep"
        assert list(destination.iterdir()) == [destination / "existing.txt"]


@pytest.mark.asyncio
async def test_app_pull_stream_preserves_timeout_error(tmp_path: Path) -> None:
    manager = FileManager(output_dir=tmp_path)
    with (
        patch("android_emu_agent.files.manager.shutil.which", return_value="/test/adb"),
        patch(
            "android_emu_agent.files.manager.subprocess.run",
            side_effect=subprocess.TimeoutExpired("adb", 0.1),
        ) as process,
        pytest.raises(AgentError) as error,
    ):
        await manager._run_adb_to_file(
            "emulator-5554",
            ["shell", "-T", "-n", "cat /source"],
            tmp_path / "result",
            timeout_s=0.1,
        )
    assert error.value.code == "ERR_TIMEOUT"
    assert process.call_args.kwargs["timeout"] == 0.1
