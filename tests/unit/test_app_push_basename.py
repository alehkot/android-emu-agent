"""App-private staging must not change the copied source basename."""

from __future__ import annotations

import shlex
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from android_emu_agent.errors import AgentError, adb_command_error
from android_emu_agent.files.manager import FileManager


def _tree(path: Path) -> dict[str, bytes | None]:
    return {
        str(entry.relative_to(path)): None if entry.is_dir() else entry.read_bytes()
        for entry in path.rglob("*")
    }


def _wire_local_transport(
    monkeypatch: pytest.MonkeyPatch, manager: FileManager, stage_root: Path, *, use_root: bool
) -> list[Path]:
    """Execute generated copy commands locally; no device or root access is used."""
    stages: list[Path] = []
    monkeypatch.setattr(manager, "_stage_dir", lambda _package: str(stage_root))

    async def shell(_device: Any, command: str) -> str:
        result = subprocess.run(
            ["sh", "-c", command], capture_output=True, text=True, timeout=5, check=False
        )
        if result.returncode:
            raise adb_command_error(command, result.stderr)
        return result.stdout

    async def optional_root(device: Any, command: str, **kwargs: Any) -> str:
        assert kwargs == {"use_root": use_root}
        # Only the common parent may be root-owned. The unique parent is created
        # through _shell so ordinary shell cleanup can enumerate its contents.
        safe_stage = shlex.quote(str(stage_root))
        assert command == f"mkdir -p {safe_stage} && chmod 0733 {safe_stage}"
        return await shell(device, command)

    async def app_shell(device: Any, _package: str, command: str, **kwargs: Any) -> str:
        assert kwargs == {"use_root": use_root}
        return await shell(device, command)

    async def adb(_serial: str, args: list[str]) -> None:
        assert args[0] == "push"
        stages.append(Path(args[2]))
        # A fresh staging path uses the same directory/file copy semantics as ADB.
        subprocess.run(["cp", "-rL", args[1], args[2]], check=True, timeout=5)

    monkeypatch.setattr(manager, "_shell", shell)
    monkeypatch.setattr(manager, "_shell_with_optional_root", optional_root)
    monkeypatch.setattr(manager, "_shell_app", app_shell)
    monkeypatch.setattr(manager, "_run_adb", adb)
    return stages


@pytest.mark.asyncio
@pytest.mark.parametrize("use_root", [False, True])
@pytest.mark.parametrize("directory", [False, True])
@pytest.mark.parametrize("destination_kind", ["existing-directory", "new-path", "trailing-slash"])
async def test_app_push_matches_source_copy_semantics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    use_root: bool,
    directory: bool,
    destination_kind: str,
) -> None:
    """Repeated pushes preserve native cp nesting/overwrite rules, not staging names."""
    source = tmp_path / "source files; literal" / "payload data"
    source.parent.mkdir()
    if directory:
        source.mkdir()
        (source / "nested").mkdir()
        (source / "empty").mkdir()
        (source / ".hidden").write_text("hidden")
        payload = source / "nested" / "config.json"
    else:
        payload = source
    payload.write_text("first")
    actual = tmp_path / "actual"
    expected = tmp_path / "expected"
    actual.mkdir()
    expected.mkdir()
    actual_target = actual / "chosen"
    expected_target = expected / "chosen"
    if destination_kind != "new-path":
        actual_target.mkdir()
        expected_target.mkdir()
        (actual_target / "unrelated.txt").write_text("preserve")
        (expected_target / "unrelated.txt").write_text("preserve")
    remote = str(actual_target)
    if destination_kind == "trailing-slash":
        remote += "/"
        expected_target /= source.name

    manager = FileManager(tmp_path / "artifacts")
    stage_root = tmp_path / "device stage"
    stages = _wire_local_transport(monkeypatch, manager, stage_root, use_root=use_root)
    for content in ("first", "second"):
        payload.write_text(content)
        subprocess.run(["cp", "-r", str(source), str(expected_target)], check=True, timeout=5)
        result = await manager.app_push(
            MagicMock(), "emulator-5554", "com.example.app", str(source), remote, use_root=use_root
        )
        assert result == manager._resolve_app_dest("com.example.app", remote, source.name)
        assert _tree(actual) == _tree(expected)
        assert list(stage_root.iterdir()) == []
    assert stages[0] != stages[1]


@pytest.mark.asyncio
@pytest.mark.parametrize("use_root", [False, True])
@pytest.mark.parametrize("failure", ["stage-prepare", "adb", "copy"])
async def test_app_push_failure_removes_only_its_staging_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, use_root: bool, failure: str
) -> None:
    manager = FileManager(tmp_path / "artifacts")
    source = tmp_path / "config.json"
    source.write_text("payload")
    stage_root = tmp_path / "stage"
    stage_root.mkdir()
    unrelated = stage_root / "another-transfer"
    unrelated.mkdir()
    (unrelated / "payload").write_text("preserve")
    stages = _wire_local_transport(monkeypatch, manager, stage_root, use_root=use_root)

    async def fail(*_args: Any, **_kwargs: Any) -> None:
        raise adb_command_error("simulated transfer", "failure")

    if failure == "stage-prepare":
        original_shell = manager._shell

        async def partial_prepare(device: Any, command: str) -> str:
            output = await original_shell(device, command)
            if command.startswith("mkdir -p "):
                await fail()
            return output

        monkeypatch.setattr(manager, "_shell", partial_prepare)
    else:
        monkeypatch.setattr(manager, "_run_adb" if failure == "adb" else "_shell_app", fail)
    with pytest.raises(AgentError, match="simulated transfer"):
        await manager.app_push(
            MagicMock(),
            "emulator-5554",
            "com.example.app",
            str(source),
            str(tmp_path / "destination"),
            use_root=use_root,
        )
    assert list(stage_root.iterdir()) == [unrelated]
    assert (unrelated / "payload").read_text() == "preserve"
    assert bool(stages) == (failure == "copy")


@pytest.mark.asyncio
@pytest.mark.parametrize("use_root", [False, True])
@pytest.mark.parametrize("source_kind", ["dot", "parent", "symlink-parent", "symlink"])
async def test_app_push_directory_names_stay_inside_unique_stage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, use_root: bool, source_kind: str
) -> None:
    manager = FileManager(tmp_path / "artifacts")
    source = tmp_path / "original"
    source.mkdir()
    (source / "config.json").write_text("payload")
    child = source / "child"
    child.mkdir()
    caller = tmp_path / "caller"
    caller.mkdir()
    alias = caller / "alias"
    alias.symlink_to(child if source_kind == "symlink-parent" else source, target_is_directory=True)
    if source_kind == "dot":
        monkeypatch.chdir(source)
        path = "."
    elif source_kind == "parent":
        monkeypatch.chdir(child)
        path = ".."
    else:
        monkeypatch.chdir(caller)
        path = "alias/.." if source_kind == "symlink-parent" else "alias"
    basename = "alias" if source_kind == "symlink" else source.name
    remote = tmp_path / "destination"
    remote.mkdir()
    stage_root = tmp_path / "stage"
    stages = _wire_local_transport(monkeypatch, manager, stage_root, use_root=use_root)
    await manager.app_push(
        MagicMock(), "emulator-5554", "com.example.app", path, str(remote), use_root=use_root
    )
    assert stages[0].name == basename
    assert stages[0].parent.parent == stage_root
    assert (remote / basename / "config.json").read_text() == "payload"
    assert list(stage_root.iterdir()) == []


@pytest.mark.asyncio
async def test_app_push_root_rejected_before_device_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager = FileManager(tmp_path / "artifacts")
    calls = MagicMock(side_effect=AssertionError("Device must not be touched"))
    monkeypatch.setattr(manager, "_shell_with_optional_root", calls)
    monkeypatch.setattr(manager, "_run_adb", calls)
    with pytest.raises(AgentError) as caught:
        await manager.app_push(
            MagicMock(), "emulator-5554", "com.example.app", "/", None, use_root=False
        )
    assert caught.value.code == "ERR_INVALID_PATH"
    calls.assert_not_called()
