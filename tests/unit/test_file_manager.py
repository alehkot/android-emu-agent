"""Tests for FileManager utilities."""

from __future__ import annotations

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

    with patch.object(manager, "_shell_su", new=AsyncMock(side_effect=fake_shell)):
        matches = await manager.find_metadata(MagicMock(), "/data/data", "*.db", "file", 2)

    assert len(matches) == 1
    command = calls[0]
    assert "find /data/data" in command
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

    with patch.object(manager, "_shell_su", new=AsyncMock(side_effect=fake_shell)):
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

    with patch.object(manager, "_shell_su", new=AsyncMock(side_effect=fake_shell)):
        matches = await manager.list_metadata(MagicMock(), "/sdcard", "dir")

    assert len(matches) == 1
    command = calls[0]
    assert "find /sdcard" in command
    assert "-mindepth 1" in command
    assert "-maxdepth 1" in command
    assert "-type d" in command
