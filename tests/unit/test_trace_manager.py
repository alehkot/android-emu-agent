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
