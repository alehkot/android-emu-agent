"""Repeated and concurrent captures must preserve earlier diagnostic evidence."""

from __future__ import annotations

import asyncio
import threading
import zipfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from android_emu_agent.artifacts.manager import ArtifactManager


@pytest.fixture(autouse=True)
def frozen_artifact_clock():
    """Exercise collisions without depending on machine speed or wall-clock rollover."""
    with patch("android_emu_agent.artifacts.manager.datetime") as clock:
        clock.now.return_value = datetime(2026, 10, 14, 7, 50)
        yield


def device_with_content(content: str) -> MagicMock:
    device = MagicMock()
    image = MagicMock()
    image.save.side_effect = lambda path: Path(path).write_text(content)
    device.screenshot.return_value = image
    device.shell.return_value = content
    return device


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["screenshot", "logs", "snapshot"])
async def test_same_second_captures_preserve_both_results(tmp_path, kind) -> None:
    manager = ArtifactManager(output_dir=tmp_path)
    paths = []
    for content in ("first", "second"):
        if kind == "screenshot":
            path = await manager.screenshot(device_with_content(content), "s-one")
        elif kind == "logs":
            path = await manager.pull_logs(device_with_content(content), "s-one")
        else:
            path = await manager.save_snapshot(content, "s-one", 3)
        paths.append(path)
    assert paths[0] != paths[1]
    assert [path.read_text() for path in paths] == ["first", "second"]
    assert all(path.name.startswith("s-one_") for path in paths)
    assert all(path.stat().st_mode & 0o777 == 0o600 for path in paths)


@pytest.mark.asyncio
async def test_bundle_does_not_delete_standalone_captures(tmp_path) -> None:
    manager = ArtifactManager(output_dir=tmp_path)
    device = device_with_content("standalone")
    screenshot = await manager.screenshot(device, "s-one")
    logs = await manager.pull_logs(device, "s-one")
    bundle = await manager.create_debug_bundle(device_with_content("bundle"), "s-one")
    assert screenshot.read_text() == "standalone"
    assert logs.read_text() == "standalone"
    with zipfile.ZipFile(bundle) as archive:
        assert sorted(
            archive.read(name).decode() for name in archive.namelist() if name != "metadata.txt"
        ) == ["bundle", "bundle"]
    assert set(tmp_path.iterdir()) == {screenshot, logs, bundle}


@pytest.mark.asyncio
async def test_repeated_bundles_keep_their_own_evidence(tmp_path) -> None:
    manager = ArtifactManager(output_dir=tmp_path)
    paths = [
        await manager.create_debug_bundle(device_with_content(value), "s-one")
        for value in ("first", "second")
    ]
    assert paths[0] != paths[1]
    for path, value in zip(paths, ("first", "second"), strict=True):
        with zipfile.ZipFile(path) as archive:
            contents = [
                archive.read(name).decode() for name in archive.namelist() if name != "metadata.txt"
            ]
            assert contents == [value, value]
    assert set(tmp_path.iterdir()) == set(paths)


@pytest.mark.asyncio
async def test_concurrent_bundles_from_separate_managers_do_not_share_paths(tmp_path) -> None:
    managers = [ArtifactManager(output_dir=tmp_path) for _ in range(2)]
    devices = [device_with_content(value) for value in ("first", "second")]
    saving = threading.Barrier(2)

    def overlapping_save(path, *, content):
        # Both bundle captures must be in flight before either writes its image.
        saving.wait(timeout=5)
        Path(path).write_text(content)

    for device, value in zip(devices, ("first", "second"), strict=True):
        device.screenshot.return_value.save.side_effect = (
            lambda path, content=value: overlapping_save(path, content=content)
        )
    paths = await asyncio.gather(
        *(
            manager.create_debug_bundle(device, "s-one", value)
            for manager, device, value in zip(managers, devices, ("first", "second"), strict=True)
        )
    )
    assert paths[0] != paths[1]
    for path, value in zip(paths, ("first", "second"), strict=True):
        with zipfile.ZipFile(path) as archive:
            assert archive.read("snapshot.json").decode() == value
            contents = [
                archive.read(name).decode()
                for name in archive.namelist()
                if name not in {"metadata.txt", "snapshot.json"}
            ]
            assert contents == [value, value]
    assert set(tmp_path.iterdir()) == set(paths)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["screenshot", "logs"])
async def test_explicit_filename_keeps_replacement_behavior(tmp_path, kind) -> None:
    manager = ArtifactManager(output_dir=tmp_path)
    filename = "chosen.png" if kind == "screenshot" else "chosen.txt"
    for content in ("first", "second"):
        if kind == "screenshot":
            path = await manager.screenshot(device_with_content(content), "s-one", filename)
        else:
            path = await manager.pull_logs(device_with_content(content), "s-one", filename=filename)
        assert path == tmp_path / filename
        assert path.read_text() == content
