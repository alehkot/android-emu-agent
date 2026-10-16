"""Regression tests for independent files and staging during overlapping transfers."""

from __future__ import annotations

import asyncio
import shlex
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from android_emu_agent.files.manager import FileManager


@pytest.mark.asyncio
@pytest.mark.parametrize("app_private", [False, True])
@pytest.mark.parametrize("concurrent", [False, True])
@pytest.mark.parametrize("independent_managers", [False, True])
async def test_automatic_pull_destinations_preserve_each_transfer(
    tmp_path: Path, *, app_private: bool, concurrent: bool, independent_managers: bool
) -> None:
    """Same-second pulls must retain both payloads even for identical basenames."""
    manager = FileManager(output_dir=tmp_path)
    both_started = asyncio.Event()
    started = 0

    async def write_payload(remote: str, destination: Path) -> None:
        nonlocal started
        started += 1
        if started == 2:
            both_started.set()
        if concurrent:
            await both_started.wait()
        destination.write_text(remote, encoding="utf-8")

    async def adb(_serial: str, args: list[str]) -> None:
        await write_payload(args[1], Path(args[2]))

    async def adb_to_file(_serial: str, args: list[str], destination: Path) -> None:
        await write_payload(shlex.split(args[-1])[-1], destination)

    async def pull(remote: str) -> Path:
        transfer_manager = FileManager(output_dir=tmp_path) if independent_managers else manager
        if app_private:
            return await transfer_manager.app_pull(
                MagicMock(), "emulator-5554", "com.example.app", remote, None, use_root=False
            )
        return await transfer_manager.pull("emulator-5554", remote, None)

    remotes = [
        "/data/data/com.example.app/files/first/config.json",
        "/data/data/com.example.app/files/second/config.json",
    ]
    with (
        patch.object(FileManager, "_timestamp", return_value="20261016_005400"),
        patch.object(FileManager, "_shell_app", new=AsyncMock(return_value="file")),
        patch.object(FileManager, "_run_adb", new=AsyncMock(side_effect=adb)),
        patch.object(FileManager, "_run_adb_to_file", new=AsyncMock(side_effect=adb_to_file)),
    ):
        if concurrent:
            paths = await asyncio.wait_for(asyncio.gather(*(pull(remote) for remote in remotes)), 5)
        else:
            paths = [await pull(remote) for remote in remotes]

    assert paths[0] != paths[1]
    assert [path.read_text(encoding="utf-8") for path in paths] == remotes
    assert all(path.parent == tmp_path for path in paths)


@pytest.mark.asyncio
@pytest.mark.parametrize("fail_first", [False, True])
async def test_overlapping_root_app_pulls_do_not_delete_each_others_stage(
    tmp_path: Path, *, fail_first: bool
) -> None:
    """Finishing one root pull must leave another transfer's staged payload intact."""
    manager = FileManager(output_dir=tmp_path)
    stage_files: dict[str, str] = {}
    both_staged = asyncio.Event()
    first_cleaned = asyncio.Event()
    pull_count = 0
    cleanup_count = 0

    async def stage(_device: MagicMock, _package: str, command: str, *, use_root: bool) -> str:
        assert use_root
        args = shlex.split(command.split(" && ")[0])
        assert args[:2] == ["cp", "-r"]
        stage_files[args[3]] = args[2]
        return ""

    async def adb(_serial: str, args: list[str]) -> None:
        nonlocal pull_count
        pull_count += 1
        first = pull_count == 1
        if pull_count == 2:
            both_staged.set()
        await both_staged.wait()
        if not first:
            await first_cleaned.wait()
        if first and fail_first:
            raise RuntimeError("Simulated transfer failure")
        Path(args[2]).write_text(stage_files.get(args[1], "STAGE MISSING"), encoding="utf-8")

    async def cleanup(_device: MagicMock, command: str) -> str:
        nonlocal cleanup_count
        stage_files.pop(shlex.split(command)[2], None)
        cleanup_count += 1
        if cleanup_count == 1:
            first_cleaned.set()
        return ""

    remotes = ["files/first.json", "files/second.json"]
    with (
        patch.object(manager, "_timestamp", return_value="20261016_005400"),
        patch.object(manager, "_shell_with_optional_root", new=AsyncMock()),
        patch.object(manager, "_shell_app", new=AsyncMock(side_effect=stage)),
        patch.object(manager, "_run_adb", new=AsyncMock(side_effect=adb)),
        patch.object(manager, "_shell", new=AsyncMock(side_effect=cleanup)),
    ):
        paths = await asyncio.wait_for(
            asyncio.gather(
                *(
                    manager.app_pull(
                        MagicMock(),
                        "emulator-5554",
                        "com.example.app",
                        remote,
                        str(tmp_path / f"output-{index}.json"),
                        use_root=True,
                    )
                    for index, remote in enumerate(remotes)
                ),
                return_exceptions=True,
            ),
            5,
        )

    if fail_first:
        assert isinstance(paths[0], RuntimeError)
        assert str(paths[0]) == "Simulated transfer failure"
    else:
        assert isinstance(paths[0], Path)
        assert paths[0].read_text(encoding="utf-8") == f"/data/data/com.example.app/{remotes[0]}"
    assert isinstance(paths[1], Path)
    assert paths[1].read_text(encoding="utf-8") == f"/data/data/com.example.app/{remotes[1]}"
    assert not stage_files
    assert cleanup_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("use_root", [False, True])
async def test_overlapping_app_pushes_preserve_same_basename_payloads(
    tmp_path: Path, *, use_root: bool
) -> None:
    """Same-named source files need separate staging even when destinations differ."""
    manager = FileManager(output_dir=tmp_path)
    sources = [tmp_path / "first" / "config.json", tmp_path / "second" / "config.json"]
    for index, source in enumerate(sources):
        source.parent.mkdir()
        source.write_text(f"payload-{index}", encoding="utf-8")
    stage_files: dict[str, str] = {}
    destinations: dict[str, str] = {}
    both_staged = asyncio.Event()
    first_cleaned = asyncio.Event()
    push_count = 0
    cleanup_count = 0

    async def adb(_serial: str, args: list[str]) -> None:
        nonlocal push_count
        push_count += 1
        first = push_count == 1
        stage_files[args[2]] = Path(args[1]).read_text(encoding="utf-8")
        if push_count == 2:
            both_staged.set()
        await both_staged.wait()
        if not first:
            await first_cleaned.wait()

    async def copy(_device: MagicMock, _package: str, command: str, *, use_root: bool) -> str:
        del use_root
        args = shlex.split(command.split(" && ")[1])
        assert args[:2] == ["cp", "-r"]
        destinations[args[3]] = stage_files.get(args[2], "STAGE MISSING")
        return ""

    async def cleanup(_device: MagicMock, command: str) -> str:
        nonlocal cleanup_count
        stage_files.pop(shlex.split(command)[2], None)
        cleanup_count += 1
        if cleanup_count == 1:
            first_cleaned.set()
        return ""

    with (
        patch.object(manager, "_timestamp", return_value="20261016_005400"),
        patch.object(manager, "_shell_with_optional_root", new=AsyncMock()),
        patch.object(manager, "_shell_app", new=AsyncMock(side_effect=copy)),
        patch.object(manager, "_run_adb", new=AsyncMock(side_effect=adb)),
        patch.object(manager, "_shell", new=AsyncMock(side_effect=cleanup)),
    ):
        results = await asyncio.wait_for(
            asyncio.gather(
                *(
                    manager.app_push(
                        MagicMock(),
                        "emulator-5554",
                        "com.example.app",
                        str(source),
                        f"files/output-{index}.json",
                        use_root=use_root,
                    )
                    for index, source in enumerate(sources)
                )
            ),
            5,
        )

    assert [destinations[result] for result in results] == ["payload-0", "payload-1"]
    assert not stage_files
    assert cleanup_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("app_private", [False, True])
async def test_explicit_pull_destination_is_unchanged(tmp_path: Path, *, app_private: bool) -> None:
    """An explicit destination remains caller-controlled instead of gaining a suffix."""
    manager = FileManager(output_dir=tmp_path)
    destination = tmp_path / "chosen.json"
    with (
        patch.object(manager, "_shell_app", new=AsyncMock(return_value="file")),
        patch.object(manager, "_run_adb", new=AsyncMock()) as adb,
        patch.object(manager, "_run_adb_to_file", new=AsyncMock()) as adb_to_file,
    ):
        if app_private:
            result = await manager.app_pull(
                MagicMock(),
                "emulator-5554",
                "com.example.app",
                "files/config.json",
                str(destination),
                use_root=False,
            )
            assert adb_to_file.await_args is not None
            assert adb_to_file.await_args.args[-1] == destination
        else:
            result = await manager.pull("emulator-5554", "/sdcard/config.json", str(destination))
            assert adb.await_args is not None
            assert adb.await_args.args[-1][-1] == str(destination)
    assert result == destination


@pytest.mark.asyncio
@pytest.mark.parametrize("basename", ["x" * 200, "界" * 70], ids=["ascii", "multibyte"])
@pytest.mark.parametrize("long_context", [False, True])
@pytest.mark.parametrize("app_private", [False, True])
async def test_automatic_pull_names_fit_filesystem_limit(
    tmp_path: Path, basename: str, *, long_context: bool, app_private: bool
) -> None:
    """Valid source names remain writable after adding transfer identity and context."""
    manager = FileManager(output_dir=tmp_path)
    serial = "emulator-" + "5" * 180 if long_context else "emulator-5554"
    package = "com." + "x" * 180 + ".app" if long_context else "com.example.app"
    writes = 0

    async def write_payload(destination: Path) -> None:
        nonlocal writes
        writes += 1
        destination.write_text(f"payload-{writes}", encoding="utf-8")

    async def adb(_serial: str, args: list[str]) -> None:
        await write_payload(Path(args[2]))

    async def adb_to_file(_serial: str, _args: list[str], destination: Path) -> None:
        await write_payload(destination)

    with (
        patch.object(manager, "_timestamp", return_value="20261016_005400"),
        patch.object(manager, "_shell_app", new=AsyncMock(return_value="file")),
        patch.object(manager, "_run_adb", new=AsyncMock(side_effect=adb)),
        patch.object(manager, "_run_adb_to_file", new=AsyncMock(side_effect=adb_to_file)),
    ):
        paths = []
        for _ in range(2):
            if app_private:
                paths.append(
                    await manager.app_pull(
                        MagicMock(), serial, package, f"files/{basename}", None, use_root=False
                    )
                )
            else:
                paths.append(await manager.pull(serial, f"/sdcard/{basename}", None))

    assert paths[0] != paths[1]
    assert [path.read_text(encoding="utf-8") for path in paths] == ["payload-1", "payload-2"]
    assert all(len(path.name.encode("utf-8")) <= 255 for path in paths)
    assert all("\ufffd" not in path.name for path in paths)


@pytest.mark.asyncio
@pytest.mark.parametrize("basename", ["x" * 200, "界" * 70], ids=["ascii", "multibyte"])
@pytest.mark.parametrize("long_package", [False, True])
async def test_app_push_stage_names_fit_filesystem_limit(
    tmp_path: Path, basename: str, *, long_package: bool
) -> None:
    """Staging long source names must fit Android's per-component byte limit."""
    manager = FileManager(output_dir=tmp_path)
    package = "com." + "x" * 180 + ".app" if long_package else "com.example.app"
    source = tmp_path / basename
    source.write_text("source", encoding="utf-8")
    stages = tmp_path / "stages"
    stages.mkdir()
    staged_paths: list[Path] = []

    async def adb(_serial: str, args: list[str]) -> None:
        local_stage = stages / Path(args[2]).name
        local_stage.write_bytes(Path(args[1]).read_bytes())
        staged_paths.append(local_stage)

    with (
        patch.object(manager, "_timestamp", return_value="20261016_005400"),
        patch.object(manager, "_shell_with_optional_root", new=AsyncMock()),
        patch.object(manager, "_shell_app", new=AsyncMock()),
        patch.object(manager, "_shell", new=AsyncMock()),
        patch.object(manager, "_run_adb", new=AsyncMock(side_effect=adb)),
    ):
        for _ in range(2):
            await manager.app_push(
                MagicMock(), "emulator-5554", package, str(source), None, use_root=False
            )

    assert staged_paths[0] != staged_paths[1]
    assert all(path.read_text(encoding="utf-8") == "source" for path in staged_paths)
    assert all(len(path.name.encode("utf-8")) <= 255 for path in staged_paths)
    assert all("\ufffd" not in path.name for path in staged_paths)


@pytest.mark.asyncio
async def test_app_directory_pulls_preserve_separate_same_second_outputs(tmp_path: Path) -> None:
    """Automatic directory destinations must not silently merge separate pulls."""
    import io
    import tarfile

    manager = FileManager(output_dir=tmp_path)
    transfers = 0

    async def archive(_serial: str, _args: list[str], destination: Path) -> None:
        nonlocal transfers
        transfers += 1
        payload = f"payload-{transfers}".encode()
        with tarfile.open(destination, "w") as output:
            entry = tarfile.TarInfo("nested/config.json")
            entry.size = len(payload)
            output.addfile(entry, io.BytesIO(payload))

    with (
        patch.object(manager, "_timestamp", return_value="20261016_005400"),
        patch.object(manager, "_shell_app", new=AsyncMock(return_value="dir")),
        patch.object(manager, "_run_adb_to_file", new=AsyncMock(side_effect=archive)),
    ):
        paths = [
            await manager.app_pull(
                MagicMock(), "emulator-5554", "com.example.app", "files", None, use_root=False
            )
            for _ in range(2)
        ]

    assert paths[0] != paths[1]
    assert [(path / "nested/config.json").read_text(encoding="utf-8") for path in paths] == [
        "payload-1",
        "payload-2",
    ]
