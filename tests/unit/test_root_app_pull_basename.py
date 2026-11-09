"""Root pulls retain ADB basename semantics without sharing staging payloads."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from android_emu_agent.files.manager import FileManager


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["file", "directory"])
@pytest.mark.parametrize("name", ["config.json", "app data;quoted's"])
async def test_root_pull_retains_basename_in_existing_directory(
    tmp_path: Path, kind: str, name: str
) -> None:
    manager = FileManager(output_dir=tmp_path / "artifacts")
    destination = tmp_path / "backup"
    destination.mkdir()
    expected = destination / name
    if kind == "directory":
        expected.mkdir()
        (expected / "keep.txt").write_text("keep")
        expected = expected / "payload.txt"
    expected.write_text("old")
    stages: list[Path] = []

    async def pull(_serial: str, args: list[str]) -> None:
        # ADB appends the source basename for a file or directory pulled into
        # an already-existing local directory. Model that public ADB contract.
        stages.append(Path(args[1]))
        target = Path(args[2]) / Path(args[1]).name
        if kind == "directory":
            target.mkdir(exist_ok=True)
            target /= "payload.txt"
        target.write_text("new")

    with (
        patch.object(manager, "_shell_with_optional_root", new=AsyncMock()) as shell,
        patch.object(manager, "_shell_app", new=AsyncMock()),
        patch.object(manager, "_run_adb", new=AsyncMock(side_effect=pull)),
    ):
        result = await manager.app_pull(
            MagicMock(),
            "emulator-5554",
            "com.example.app",
            f"files/{name}",
            str(destination),
            use_root=True,
        )
    assert result == destination
    assert expected.read_text() == "new"
    assert list(destination.iterdir()) == [destination / name]
    assert stages[0].name == name
    if kind == "directory":
        assert (destination / name / "keep.txt").read_text() == "keep"
    assert shell.await_args_list[-1].args[1] == f"rm -rf {stages[0].parent}"
    assert shell.await_args_list[-1].kwargs == {"use_root": True}


@pytest.mark.asyncio
@pytest.mark.parametrize("remote", ["/", "..", "files/.."])
async def test_special_root_paths_cannot_escape_transfer_directory(
    tmp_path: Path, remote: str
) -> None:
    manager = FileManager(output_dir=tmp_path)
    with (
        patch.object(manager, "_shell_with_optional_root", new=AsyncMock()) as shell,
        patch.object(manager, "_shell_app", new=AsyncMock()),
        patch.object(manager, "_run_adb", new=AsyncMock()) as adb,
    ):
        await manager.app_pull(
            MagicMock(),
            "emulator-5554",
            "com.example.app",
            remote,
            str(tmp_path / "output"),
            use_root=True,
        )
    assert adb.await_args is not None
    staged = Path(adb.await_args.args[1][1])
    assert staged.name == "artifact"
    assert staged.parent.parent == Path(manager._stage_dir("com.example.app"))
    assert shell.await_args_list[-1].args[1] == f"rm -rf {staged.parent}"
