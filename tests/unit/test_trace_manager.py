"""Tests for trace archive manager."""

from __future__ import annotations

import stat
import zipfile
from pathlib import Path

import pytest

from android_emu_agent.tracing.manager import TraceManager


@pytest.mark.asyncio
async def test_trace_manager_archives_redacted_daemon_events(tmp_path: Path) -> None:
    """Trace archives should contain redacted request/response events."""
    manager = TraceManager(tmp_path / "traces")

    started = await manager.start("s-abc123", label="login")
    await manager.record_daemon_exchange(
        session_id="s-abc123",
        diagnostic_id="diag-1",
        method="POST",
        path="/actions/tap",
        status_code=200,
        elapsed_ms=12.5,
        request_payload={"session_id": "s-abc123", "api_key": "secret", "ref": "^a1"},
        response_payload={"status": "done", "path": "/tmp/screen.png"},
    )
    stopped = await manager.stop("s-abc123")

    archive_path = Path(stopped["path"])
    assert archive_path.exists()
    assert archive_path.suffixes[-2:] == [".aea-trace", ".zip"]
    assert stat.S_IMODE(manager.output_dir.stat().st_mode) == 0o700
    assert stat.S_IMODE(archive_path.stat().st_mode) == 0o600

    with zipfile.ZipFile(archive_path) as zf:
        names = set(zf.namelist())
    assert {"manifest.json", "events.ndjson"}.issubset(names)

    events = manager.load_events(archive_path)
    assert [event["kind"] for event in events] == [
        "trace_started",
        "daemon_exchange",
        "trace_stopped",
    ]
    exchange = events[1]
    assert exchange["trace_id"] == started["trace_id"]
    assert exchange["request"]["api_key"] == "***REDACTED***"
    assert exchange["response"]["path"] == "/tmp/screen.png"

    replay = manager.replay_archive(archive_path)
    assert replay["step_count"] == 1
    assert replay["steps"][0]["path"] == "/actions/tap"

    exported = manager.export_markdown(archive_path)
    assert "# Android Emu Agent Trace" in exported["markdown"]
    assert "POST /actions/tap" in exported["markdown"]


@pytest.mark.asyncio
async def test_trace_replay_can_stop_at_first_failure(tmp_path: Path) -> None:
    """Dry replay should optionally truncate at the first failed exchange."""
    manager = TraceManager(tmp_path / "traces")

    await manager.start("s-abc123")
    await manager.record_daemon_exchange(
        session_id="s-abc123",
        diagnostic_id="diag-1",
        method="POST",
        path="/actions/tap",
        status_code=404,
        elapsed_ms=1.0,
        request_payload={"session_id": "s-abc123", "ref": "^a9"},
        response_payload={"status": "error", "error": {"code": "ERR_NOT_FOUND"}},
    )
    await manager.record_daemon_exchange(
        session_id="s-abc123",
        diagnostic_id="diag-2",
        method="POST",
        path="/ui/snapshot",
        status_code=200,
        elapsed_ms=1.0,
        request_payload={"session_id": "s-abc123"},
        response_payload={"status": "done"},
    )
    stopped = await manager.stop("s-abc123")

    replay = manager.replay_archive(stopped["path"], until_failure=True)

    assert replay["stopped_at_failure"] is True
    assert replay["step_count"] == 1
    assert replay["steps"][0]["error"]["code"] == "ERR_NOT_FOUND"


@pytest.mark.asyncio
async def test_trace_manager_does_not_archive_typed_input(tmp_path: Path) -> None:
    """Trace archives should redact set-text values from daemon exchanges."""
    manager = TraceManager(tmp_path / "traces")
    await manager.start("s-abc123")
    await manager.record_daemon_exchange(
        session_id="s-abc123",
        diagnostic_id="diag-1",
        method="POST",
        path="/actions/set_text",
        status_code=200,
        elapsed_ms=1.0,
        request_payload={"session_id": "s-abc123", "ref": "^a1", "text": "audit-secret"},
        response_payload={"status": "done"},
    )
    stopped = await manager.stop("s-abc123")

    archive_path = Path(stopped["path"])
    assert b"audit-secret" not in archive_path.read_bytes()
    exchange = manager.load_events(archive_path)[1]
    assert exchange["request"]["text"] == "***REDACTED***"


@pytest.mark.asyncio
async def test_stop_if_active_archives_trace_once(tmp_path: Path) -> None:
    """Session cleanup should finalize an active trace without requiring a separate command."""
    manager = TraceManager(tmp_path / "traces")
    await manager.start("s-abc123")

    stopped = await manager.stop_if_active("s-abc123")

    assert stopped is not None
    assert Path(stopped["path"]).exists()
    assert await manager.stop_if_active("s-abc123") is None


@pytest.mark.asyncio
async def test_stop_all_archives_every_active_trace(tmp_path: Path) -> None:
    """Daemon shutdown should preserve every in-progress trace as an archive."""
    manager = TraceManager(tmp_path / "traces")
    await manager.start("s-one")
    await manager.start("s-two")

    stopped = await manager.stop_all()

    assert {result["session_id"] for result in stopped} == {"s-one", "s-two"}
    assert all(Path(result["path"]).exists() for result in stopped)
    assert (await manager.status())["traces"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "destination", ["manifest.json", "events.ndjson", "nested/result.zip", "."]
)
async def test_trace_stop_rejects_output_inside_source_without_changing_trace(
    tmp_path: Path, destination: str
) -> None:
    """An output path must never replace or become part of its own trace input."""
    from android_emu_agent.errors import AgentError

    manager = TraceManager(tmp_path / "traces")
    started = await manager.start("s-one")
    directory = Path(started["directory"])
    before = {path.name: path.read_bytes() for path in directory.iterdir()}

    with pytest.raises(AgentError, match="outside"):
        await manager.stop("s-one", str(directory / destination))

    assert {path.name: path.read_bytes() for path in directory.iterdir()} == before
    assert len((await manager.status())["traces"]) == 1
    stopped = await manager.stop("s-one")
    assert [event["kind"] for event in manager.load_events(stopped["path"])] == [
        "trace_started",
        "trace_stopped",
    ]


@pytest.mark.asyncio
async def test_trace_stop_rejects_symlinked_source_directory(tmp_path: Path) -> None:
    """The safety check must resolve aliases of the source directory."""
    from android_emu_agent.errors import AgentError

    manager = TraceManager(tmp_path / "traces")
    started = await manager.start("s-one")
    alias = tmp_path / "alias"
    alias.symlink_to(started["directory"], target_is_directory=True)
    with pytest.raises(AgentError, match="outside"):
        await manager.stop("s-one", str(alias / "result.zip"))
    assert len(manager.load_events(started["directory"])) == 1


@pytest.mark.parametrize("existing", [False, True])
def test_trace_archive_write_failure_preserves_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, existing: bool
) -> None:
    """A partial ZIP must not replace an earlier archive or appear as a completed one."""
    directory = tmp_path / "source"
    directory.mkdir()
    (directory / "events.ndjson").write_text("{}\n")
    output = tmp_path / "archive.zip"
    previous = b"previous good archive"
    if existing:
        output.write_bytes(previous)

    def fail_write(*_args: object, **_kwargs: object) -> None:
        raise OSError("simulated disk full")

    monkeypatch.setattr(zipfile.ZipFile, "write", fail_write)
    with pytest.raises(OSError, match="disk full"):
        TraceManager._zip_trace(directory, output)

    if existing:
        assert output.read_bytes() == previous
    else:
        assert not output.exists()
    assert set(tmp_path.iterdir()) == ({directory, output} if existing else {directory})


def test_trace_archive_replaces_destination_only_after_zip_closes(tmp_path: Path) -> None:
    """Successful replacement produces a private, readable archive without temp leftovers."""
    directory = tmp_path / "source"
    directory.mkdir()
    (directory / "events.ndjson").write_text("{}\n")
    output = tmp_path / "archive.zip"
    output.write_bytes(b"previous archive")
    TraceManager._zip_trace(directory, output)
    with zipfile.ZipFile(output) as archive:
        assert archive.testzip() is None
        assert archive.read("events.ndjson") == b"{}\n"
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert set(tmp_path.iterdir()) == {directory, output}


def test_trace_archive_replace_failure_preserves_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = tmp_path / "source"
    directory.mkdir()
    (directory / "events.ndjson").write_text("{}\n")
    output = tmp_path / "archive.zip"
    output.write_bytes(b"previous archive")

    def fail_replace(_source: Path, _target: Path) -> None:
        raise OSError("simulated rename failure")

    monkeypatch.setattr(Path, "replace", fail_replace)
    with pytest.raises(OSError, match="rename failure"):
        TraceManager._zip_trace(directory, output)
    assert output.read_bytes() == b"previous archive"
    assert set(tmp_path.iterdir()) == {directory, output}


@pytest.mark.asyncio
async def test_trace_stop_accepts_external_directory(tmp_path: Path) -> None:
    manager = TraceManager(tmp_path / "traces")
    started = await manager.start("s-one")
    output = tmp_path / "exports"
    output.mkdir()
    stopped = await manager.stop("s-one", str(output))
    assert Path(stopped["path"]) == output / f"{started['trace_id']}.aea-trace.zip"
    assert manager.load_manifest(stopped["path"])["status"] == "stopped"


@pytest.mark.asyncio
async def test_trace_stop_rejects_output_symlink_to_source_file(tmp_path: Path) -> None:
    from android_emu_agent.errors import AgentError

    manager = TraceManager(tmp_path / "traces")
    started = await manager.start("s-one")
    manifest = Path(started["directory"]) / "manifest.json"
    original = manifest.read_bytes()
    output = tmp_path / "archive.zip"
    output.symlink_to(manifest)
    with pytest.raises(AgentError, match="outside"):
        await manager.stop("s-one", str(output))
    assert output.is_symlink()
    assert manifest.read_bytes() == original


@pytest.mark.asyncio
async def test_trace_stop_rejects_source_symlink_pointing_outside(tmp_path: Path) -> None:
    """A final symlink must not hide that the temp file and output entry are inside source."""
    from android_emu_agent.errors import AgentError

    manager = TraceManager(tmp_path / "traces")
    started = await manager.start("s-one")
    directory = Path(started["directory"])
    external = tmp_path / "external.zip"
    external.write_bytes(b"previous archive")
    output = directory / "link.zip"
    output.symlink_to(external)
    manifest = (directory / "manifest.json").read_bytes()
    with pytest.raises(AgentError, match="outside"):
        await manager.stop("s-one", str(output))
    assert output.is_symlink()
    assert external.read_bytes() == b"previous archive"
    assert (directory / "manifest.json").read_bytes() == manifest
    assert len(manager.load_events(directory)) == 1
    assert {path.name for path in directory.iterdir()} == {
        "events.ndjson",
        "manifest.json",
        "link.zip",
    }
