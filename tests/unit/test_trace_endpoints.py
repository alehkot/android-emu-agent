"""Tests for trace daemon endpoints and middleware recording."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch

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


def test_trace_export_rejects_unsupported_format_with_agent_error(tmp_path: Path) -> None:
    """Unsupported trace export formats should use the project error shape."""
    with _client_with_core(tmp_path) as (client, _trace_manager):
        response = client.post(
            "/trace/export",
            json={"path": "/tmp/run.aea-trace.zip", "format": "html"},
        )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "ERR_UNSUPPORTED_TRACE_FORMAT"
