"""Tests for trace daemon endpoints and middleware recording."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from android_emu_agent.daemon.diagnostics import RequestDiagnostics
from android_emu_agent.tracing.manager import TraceManager


@dataclass
class DummySession:
    """Session object with the fields used by session endpoints."""

    session_id: str = "s-abc123"
    device_serial: str = "emulator-5554"
    generation: int = 4
    created_at: datetime = field(default_factory=datetime.now)


class DummySessionManager:
    def __init__(self) -> None:
        self.session = DummySession()

    async def get_session(self, session_id: str) -> DummySession | None:
        if session_id != self.session.session_id:
            return None
        return self.session

    async def list_sessions(self) -> list[DummySession]:
        return [self.session]


class DummyCore:
    diagnostics: RequestDiagnostics
    trace_manager: TraceManager

    def __init__(self) -> None:
        self.session_manager = DummySessionManager()
        self.diagnostics = self.__class__.diagnostics
        self.trace_manager = self.__class__.trace_manager
        self._running = False

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running


@contextmanager
def _client_with_core(tmp_path: Path) -> Any:
    from android_emu_agent.daemon import server

    DummyCore.diagnostics = RequestDiagnostics(tmp_path / "diagnostics")
    DummyCore.trace_manager = TraceManager(tmp_path / "traces")

    with patch.object(server, "DaemonCore", DummyCore), TestClient(server.app) as client:
        yield client, DummyCore.trace_manager


def test_trace_start_records_session_exchange_and_stop_archives(tmp_path: Path) -> None:
    """Trace endpoints should record session-scoped daemon exchanges into an archive."""
    with _client_with_core(tmp_path) as (client, trace_manager):
        start_resp = client.post(
            "/trace/start",
            json={"session_id": "s-abc123", "label": "smoke"},
        )
        session_resp = client.get("/sessions/s-abc123")
        stop_resp = client.post("/trace/stop", json={"session_id": "s-abc123"})

    assert start_resp.status_code == 200
    assert start_resp.json()["status"] == "done"
    assert start_resp.json()["trace_status"] == "active"
    assert session_resp.status_code == 200
    assert stop_resp.status_code == 200

    archive_path = Path(stop_resp.json()["path"])
    events = trace_manager.load_events(archive_path)
    exchange_events = [event for event in events if event["kind"] == "daemon_exchange"]
    assert len(exchange_events) == 1
    assert exchange_events[0]["path"] == "/sessions/s-abc123"
    assert exchange_events[0]["response"]["session_id"] == "s-abc123"


def test_trace_start_rejects_duplicate_active_trace(tmp_path: Path) -> None:
    """Only one active trace should be allowed per session."""
    with _client_with_core(tmp_path) as (client, _trace_manager):
        first = client.post("/trace/start", json={"session_id": "s-abc123"})
        second = client.post("/trace/start", json={"session_id": "s-abc123"})

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "ERR_TRACE_ACTIVE"


def test_trace_start_response_survives_diagnostics_failure(tmp_path: Path) -> None:
    """A completed state mutation should not fail because observability storage failed."""
    with _client_with_core(tmp_path) as (client, _trace_manager):
        failure = AsyncMock(side_effect=OSError("synthetic diagnostics failure"))
        with patch.object(DummyCore.diagnostics, "record", failure):
            response = client.post("/trace/start", json={"session_id": "s-abc123"})

    assert response.status_code == 200
    assert response.json()["trace_status"] == "active"
    failure.assert_awaited_once()


def test_trace_export_rejects_unsupported_format_with_agent_error(tmp_path: Path) -> None:
    """Unsupported trace export formats should use the project error shape."""
    with _client_with_core(tmp_path) as (client, _trace_manager):
        response = client.post(
            "/trace/export",
            json={"path": "/tmp/run.aea-trace.zip", "format": "html"},
        )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "ERR_UNSUPPORTED_TRACE_FORMAT"


def test_trace_stop_rejects_source_output_and_can_retry(tmp_path: Path) -> None:
    """Invalid archive destinations return an actionable 400 without ending the trace."""
    with _client_with_core(tmp_path) as (client, trace_manager):
        started = client.post("/trace/start", json={"session_id": "s-abc123"}).json()
        response = client.post(
            "/trace/stop",
            json={"session_id": "s-abc123", "output_path": started["directory"]},
        )
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "ERR_TRACE_OUTPUT_PATH"
        assert "outside" in response.json()["error"]["remediation"]
        stopped = client.post("/trace/stop", json={"session_id": "s-abc123"})
        assert stopped.status_code == 200
        events = trace_manager.load_events(stopped.json()["path"])
        assert [event["kind"] for event in events] == ["trace_started", "trace_stopped"]


@pytest.mark.parametrize("script", [False, True], ids=["json-task", "aea-script"])
@pytest.mark.parametrize("failure_scope", ["action", "step-verifier", "final-verifier"])
@pytest.mark.parametrize("stop_on_failure", [False, True], ids=["continue", "stop"])
def test_trace_replay_stops_at_failed_task_response(
    tmp_path: Path, script: bool, failure_scope: str, stop_on_failure: bool
) -> None:
    """Actual task results and middleware archives must retain the failure boundary."""
    from android_emu_agent.daemon import server
    from android_emu_agent.tasks.manager import TaskManager

    manager = TaskManager()
    lines = ["home"]
    if failure_scope == "step-verifier":
        lines.append('verify text "Ready"')
    lines.append("back")
    if failure_scope == "final-verifier":
        lines.append('expect text "Ready"')
    source = "\n".join(lines)
    dispatched = []

    async def dispatch(call):
        dispatched.append(call.operation)
        fail_operation = "home" if failure_scope == "action" else "text"
        if call.operation == fail_operation:
            return {"error": {"code": "ERR_TIMEOUT", "message": "condition not reached"}}
        return {"status": "done"}

    with _client_with_core(tmp_path) as (client, trace_manager):
        server.app.state.core.task_manager = manager
        started = client.post("/trace/start", json={"session_id": "s-abc123"}).json()
        assert client.get("/sessions/s-abc123").status_code == 200
        task_path = "/tasks/script/run" if script else "/tasks/run"
        payload = {"session_id": "s-abc123", "stop_on_failure": stop_on_failure}
        if script:
            payload["script"] = source
        else:
            payload["task"] = manager.parse_script(source)
        with patch.object(server, "_dispatch_task_call", dispatch):
            task_response = client.post(task_path, json=payload)
        assert task_response.status_code == 200
        assert task_response.json()["status"] == "failed"
        assert task_response.json()["passed"] is False
        assert not task_response.json().get("error")
        assert client.get("/sessions/s-abc123").status_code == 200
        stopped = client.post("/trace/stop", json={"session_id": "s-abc123"}).json()
        calls_before_replay = list(dispatched)
        for archive_path in (stopped["path"], started["directory"]):
            full = client.post("/trace/replay", json={"path": archive_path}).json()
            limited = client.post(
                "/trace/replay", json={"path": archive_path, "until_failure": True}
            ).json()
            assert full["step_count"] == 3
            assert full["stopped_at_failure"] is False
            assert limited["stopped_at_failure"] is True
            assert limited["step_count"] == 2
            assert limited["steps"] == full["steps"][:2]
            assert limited["steps"][-1]["path"] == task_path
            assert limited["steps"][-1]["status_code"] == 200
            assert limited["steps"][-1]["error"] is None
            assert "response" not in limited["steps"][-1], "keep the replay step schema"
        assert dispatched == calls_before_replay, "replay remains a dry-run"
        exchanges = [
            event
            for event in trace_manager.load_events(stopped["path"])
            if event["kind"] == "daemon_exchange"
        ]
        assert exchanges[1]["response"] == task_response.json()
