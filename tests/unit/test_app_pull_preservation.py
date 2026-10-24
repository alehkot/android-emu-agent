"""Non-root app pulls preserve host files until the ADB transfer succeeds."""

from __future__ import annotations

import stat
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from android_emu_agent.errors import AgentError
from android_emu_agent.files.manager import FileManager

OLD_PAYLOAD = b"previous complete backup\x00\xff"


def _destination(tmp_path: Path, kind: str) -> tuple[Path, Path, Path | None]:
    target = tmp_path / "backup.bin"
    alias = None
    if kind != "absent":
        target.write_bytes(OLD_PAYLOAD)
        target.chmod(0o640)
    local = target
    if kind == "symlink":
        local = tmp_path / "link.bin"
        local.symlink_to(target.name)
    elif kind == "hardlink":
        alias = tmp_path / "alias.bin"
        alias.hardlink_to(target)
    elif kind == "directory":
        local = tmp_path / "output"
        local.mkdir()
        target.rename(local / "source.bin")
        target = local / "source.bin"
    return local, target, alias


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["existing", "absent", "symlink", "hardlink", "directory"])
@pytest.mark.parametrize("failure", ["remote", "timeout", "launch", "spool_write"])
async def test_failed_app_pull_preserves_destination(
    tmp_path: Path, kind: str, failure: str
) -> None:
    manager = FileManager(output_dir=tmp_path)
    local, target, alias = _destination(tmp_path, kind)
    inode = target.stat().st_ino if target.exists() else None
    stream: Any = None

    def run(command: list[str], **kwargs: Any) -> None:
        nonlocal stream
        stream = kwargs["stdout"]
        if failure == "launch":
            raise FileNotFoundError("adb disappeared")
        stream.write(b"partial")
        stream.flush()
        if failure == "remote":
            raise subprocess.CalledProcessError(1, command, stderr=b"connection lost")
        if failure == "timeout":
            raise subprocess.TimeoutExpired(command, kwargs["timeout"])
        raise OSError("temporary storage full")

    expected = OSError if failure == "spool_write" else AgentError
    with (
        patch.object(manager, "_shell_app", new=AsyncMock(return_value="file")),
        patch("android_emu_agent.files.manager.shutil.which", return_value="/test/adb"),
        patch("android_emu_agent.files.manager.subprocess.run", side_effect=run) as process,
        pytest.raises(expected) as error,
    ):
        await manager.app_pull(
            MagicMock(),
            "emulator-5554",
            "com.example.app",
            "files/source.bin",
            str(local),
            use_root=False,
        )

    if isinstance(error.value, AgentError):
        assert (
            error.value.code
            == {
                "remote": "ERR_ADB_COMMAND",
                "timeout": "ERR_TIMEOUT",
                "launch": "ERR_ADB_NOT_FOUND",
            }[failure]
        )
    process.assert_called_once()
    assert stream.closed
    if kind == "absent":
        assert not target.exists()
    else:
        assert target.read_bytes() == OLD_PAYLOAD
        assert target.stat().st_ino == inode
        assert stat.S_IMODE(target.stat().st_mode) == 0o640
    if kind == "symlink":
        assert local.is_symlink()
    if alias is not None:
        assert alias.read_bytes() == OLD_PAYLOAD
        assert alias.stat().st_ino == inode


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["existing", "absent", "symlink", "hardlink", "directory"])
@pytest.mark.parametrize("payload", [b"", b"new\x00\xff\xfe\r\n\x00"])
async def test_successful_app_pull_publishes_only_after_transfer(
    tmp_path: Path, kind: str, payload: bytes
) -> None:
    manager = FileManager(output_dir=tmp_path)
    local, target, alias = _destination(tmp_path, kind)
    inode = target.stat().st_ino if target.exists() else None
    stream: Any = None

    def run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        nonlocal stream
        stream = kwargs["stdout"]
        stream.write(payload)
        stream.flush()
        # Even a successful transfer must not expose incomplete bytes mid-stream.
        if kind == "absent":
            assert not target.exists()
        else:
            assert target.read_bytes() == OLD_PAYLOAD
        assert command[3:6] == ["shell", "-T", "-n"]
        assert kwargs["check"] is True
        assert kwargs["stderr"] == subprocess.PIPE
        assert kwargs["timeout"] == 600
        return subprocess.CompletedProcess(command, 0, stderr=b"not payload")

    with (
        patch.object(manager, "_shell_app", new=AsyncMock(return_value="file")),
        patch("android_emu_agent.files.manager.shutil.which", return_value="/test/adb"),
        patch("android_emu_agent.files.manager.subprocess.run", side_effect=run) as process,
    ):
        result = await manager.app_pull(
            MagicMock(),
            "emulator-5554",
            "com.example.app",
            "files/source.bin",
            str(local),
            use_root=False,
        )

    process.assert_called_once()
    assert result == local
    assert stream.closed
    assert target.read_bytes() == payload
    if inode is not None:
        assert target.stat().st_ino == inode
        assert stat.S_IMODE(target.stat().st_mode) == 0o640
    if kind == "symlink":
        assert local.is_symlink()
    if alias is not None:
        assert alias.read_bytes() == payload
        assert alias.stat().st_ino == inode
