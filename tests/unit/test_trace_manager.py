"""Tests for trace archive manager."""

from __future__ import annotations

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
