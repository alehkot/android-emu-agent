"""Tests for FileManager utilities."""

from __future__ import annotations

import io
import tarfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def test_parse_find_output_parses_matches() -> None:
    """Should parse stat output into file metadata."""
    from android_emu_agent.files.manager import FileManager

    manager = FileManager(output_dir=Path("/tmp"))
    output = "\n".join(
        [
            "/data/data/app/db.sqlite|regular file|2048|1000|1000|644|1700000000",
            "/data/data/app/cache|directory|4096|1000|1000|755|1700000100",
        ]
    )

    matches = manager._parse_find_output(output)

    assert matches == [
        {
            "path": "/data/data/app/db.sqlite",
            "name": "db.sqlite",
            "kind": "file",
            "type_raw": "regular file",
            "size_bytes": 2048,
            "uid": 1000,
            "gid": 1000,
            "mode": "644",
            "mtime_epoch": 1700000000,
        },
        {
            "path": "/data/data/app/cache",
            "name": "cache",
            "kind": "dir",
            "type_raw": "directory",
            "size_bytes": 4096,
            "uid": 1000,
            "gid": 1000,
            "mode": "755",
            "mtime_epoch": 1700000100,
        },
    ]


@pytest.mark.asyncio
async def test_find_metadata_builds_command() -> None:
    """Should include filters for find command."""
    from android_emu_agent.files.manager import FileManager

    manager = FileManager(output_dir=Path("/tmp"))
    calls: list[str] = []

    async def fake_shell(_device: MagicMock, command: str) -> str:
        calls.append(command)
        return "/data/data/app/db.sqlite|regular file|1|0|0|644|1700000000"

    with patch.object(manager, "_shell", new=AsyncMock(side_effect=fake_shell)):
        matches = await manager.find_metadata(MagicMock(), "/data/data", "*.db", "file", 2)

    assert len(matches) == 1
    command = calls[0]
    assert "find -H /data/data" in command
    assert "-maxdepth 2" in command
    assert "-type f" in command
    assert "-name" in command


@pytest.mark.asyncio
async def test_find_metadata_any_kind_skips_type() -> None:
    """Should omit type flag for any-kind searches."""
    from android_emu_agent.files.manager import FileManager

    manager = FileManager(output_dir=Path("/tmp"))
    calls: list[str] = []

    async def fake_shell(_device: MagicMock, command: str) -> str:
        calls.append(command)
        return ""

    with patch.object(manager, "_shell", new=AsyncMock(side_effect=fake_shell)):
        matches = await manager.find_metadata(MagicMock(), "/data/data", "*.db", "any", 1)

    assert matches == []
    assert "-type" not in calls[0]


@pytest.mark.asyncio
async def test_find_metadata_rejects_negative_depth() -> None:
    """Should error on invalid max depth."""
    from android_emu_agent.errors import AgentError
    from android_emu_agent.files.manager import FileManager

    manager = FileManager(output_dir=Path("/tmp"))

    with pytest.raises(AgentError) as excinfo:
        await manager.find_metadata(MagicMock(), "/data/data", "*.db", "file", -1)

    assert excinfo.value.code == "ERR_INVALID_DEPTH"


@pytest.mark.asyncio
async def test_list_metadata_builds_command() -> None:
    """Should list only immediate entries."""
    from android_emu_agent.files.manager import FileManager

    manager = FileManager(output_dir=Path("/tmp"))
    calls: list[str] = []

    async def fake_shell(_device: MagicMock, command: str) -> str:
        calls.append(command)
        return "/sdcard/Download|directory|4096|1000|1000|755|1700000200"

    with patch.object(manager, "_shell", new=AsyncMock(side_effect=fake_shell)):
        matches = await manager.list_metadata(MagicMock(), "/sdcard", "dir")

    assert len(matches) == 1
    command = calls[0]
    assert "find -H /sdcard" in command
    assert "-mindepth 1" in command
    assert "-maxdepth 1" in command
    assert "-type d" in command


@pytest.mark.asyncio
async def test_app_pull_quotes_remote_paths(tmp_path: Path) -> None:
    """Should quote app-private paths before running commands as the app user."""
    from android_emu_agent.files.manager import FileManager

    manager = FileManager(output_dir=tmp_path)
    calls: list[str] = []

    async def fake_shell_app(
        _device: MagicMock,
        _package: str,
        command: str,
        *,
        use_root: bool,
    ) -> str:
        assert use_root is True
        calls.append(command)
        return ""

    with (
        patch.object(manager, "_shell", new=AsyncMock(return_value="")),
        patch.object(manager, "_shell_app", new=AsyncMock(side_effect=fake_shell_app)),
        patch.object(manager, "_run_adb", new=AsyncMock()),
    ):
        await manager.app_pull(
            MagicMock(),
            "emulator-5554",
            "com.example.app",
            "files/config;id.json",
            None,
            use_root=True,
        )

    assert calls
    assert "cp -r '/data/data/com.example.app/files/config;id.json'" in calls[0]


@pytest.mark.asyncio
async def test_app_pull_streams_file_via_run_as_without_root(tmp_path: Path) -> None:
    """Non-root pulls should stream files instead of copying across SELinux domains."""
    from android_emu_agent.files.manager import FileManager

    manager = FileManager(output_dir=tmp_path)

    with (
        patch.object(manager, "_shell_app", new=AsyncMock(return_value="file")) as shell_app,
        patch.object(manager, "_run_adb_to_file", new=AsyncMock()) as run_adb_to_file,
    ):
        local = await manager.app_pull(
            MagicMock(),
            "emulator-5554",
            "com.example.app",
            "files/config.json",
            str(tmp_path / "config.json"),
            use_root=False,
        )

    shell_app.assert_awaited_once()
    run_adb_to_file.assert_awaited_once_with(
        "emulator-5554",
        [
            "shell",
            "-T",
            "-n",
            "run-as com.example.app cat /data/data/com.example.app/files/config.json",
        ],
        tmp_path / "config.json",
    )
    assert local == tmp_path / "config.json"


@pytest.mark.asyncio
async def test_app_pull_extracts_streamed_directory_safely(tmp_path: Path) -> None:
    """Directory pulls should extract regular archive members into the requested path."""
    from android_emu_agent.files.manager import FileManager

    manager = FileManager(output_dir=tmp_path)

    async def write_archive(_serial: str, _args: list[str], destination: Path) -> None:
        payload = b"run-as-ok\n"
        with tarfile.open(destination, mode="w") as archive:
            member = tarfile.TarInfo("./nested/smoke.txt")
            member.size = len(payload)
            archive.addfile(member, io.BytesIO(payload))

    local = tmp_path / "pulled"
    with patch.object(manager, "_run_adb_to_file", new=AsyncMock(side_effect=write_archive)):
        await manager._pull_app_directory(
            "emulator-5554",
            "com.example.app",
            "/data/data/com.example.app/files",
            local,
        )

    assert (local / "nested" / "smoke.txt").read_text() == "run-as-ok\n"


@pytest.mark.asyncio
async def test_app_pull_rejects_unsafe_archive_members(tmp_path: Path) -> None:
    """Streamed app archives must not escape their extraction directory."""
    from android_emu_agent.errors import AgentError
    from android_emu_agent.files.manager import FileManager

    manager = FileManager(output_dir=tmp_path)

    async def write_archive(_serial: str, _args: list[str], destination: Path) -> None:
        payload = b"unsafe"
        with tarfile.open(destination, mode="w") as archive:
            member = tarfile.TarInfo("../escape.txt")
            member.size = len(payload)
            archive.addfile(member, io.BytesIO(payload))

    with (
        patch.object(manager, "_run_adb_to_file", new=AsyncMock(side_effect=write_archive)),
        pytest.raises(AgentError) as exc_info,
    ):
        await manager._pull_app_directory(
            "emulator-5554",
            "com.example.app",
            "/data/data/com.example.app/files",
            tmp_path / "pulled",
        )

    assert exc_info.value.code == "ERR_UNSAFE_ARCHIVE"
    assert not (tmp_path / "escape.txt").exists()


@pytest.mark.asyncio
async def test_find_metadata_uses_root_only_when_available() -> None:
    """Protected searches should retain the root path when the target supports it."""
    from android_emu_agent.files.manager import FileManager

    manager = FileManager(output_dir=Path("/tmp"))

    with patch.object(manager, "_shell_su", new=AsyncMock(return_value="")) as shell_su:
        await manager.find_metadata(
            MagicMock(),
            "/data/data",
            "*.db",
            "file",
            2,
            use_root=True,
        )

    shell_su.assert_awaited_once()


@pytest.mark.asyncio
async def test_shell_app_uses_run_as_without_root() -> None:
    """Debuggable app storage should be accessed with run-as on non-root devices."""
    from android_emu_agent.files.manager import FileManager

    manager = FileManager(output_dir=Path("/tmp"))
    device = MagicMock()
    device.shell.return_value = "\n__AEA_EXIT_CODE__:0"

    await manager._shell_app(
        device,
        "com.example.app",
        "ls files",
        use_root=False,
    )

    command = device.shell.call_args.args[0]
    assert command.startswith("run-as com.example.app sh -c 'ls files'")
    assert "__AEA_EXIT_CODE__" in command


@pytest.mark.asyncio
async def test_shell_raises_when_device_command_fails() -> None:
    """File operations must not treat a non-zero device shell exit as success."""
    from android_emu_agent.errors import AgentError
    from android_emu_agent.files.manager import FileManager

    manager = FileManager(output_dir=Path("/tmp"))
    device = MagicMock()
    device.shell.return_value = "run-as: package not debuggable\n__AEA_EXIT_CODE__:1"

    with pytest.raises(AgentError) as exc_info:
        await manager._shell(device, "run-as com.example.app pwd")

    assert exc_info.value.code == "ERR_ADB_COMMAND"
    assert exc_info.value.context["reason"] == "run-as: package not debuggable"
