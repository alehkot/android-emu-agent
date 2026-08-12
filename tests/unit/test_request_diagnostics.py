"""Tests for request diagnostics middleware."""

from __future__ import annotations

import json
import stat
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from android_emu_agent.daemon.diagnostics import RequestDiagnostics


class DummyDeviceManager:
    async def list_devices(self) -> list[dict[str, str]]:
        return []


class DummySessionManager:
    async def get_session(self, _session_id: str) -> None:
        return None

    async def list_sessions(self) -> list[object]:
        return []


class DummyHealthMonitor:
    def get_status(self) -> dict[str, Any]:
        return {"devices": {}}


class DummyCore:
    diagnostics: RequestDiagnostics
    trace_manager: Any = None

    def __init__(self) -> None:
        self.device_manager = DummyDeviceManager()
        self.session_manager = DummySessionManager()
        self.health_monitor = DummyHealthMonitor()
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
    DummyCore.trace_manager = None
    with patch.object(server, "DaemonCore", DummyCore), TestClient(server.app) as client:
        yield client, DummyCore.diagnostics


def _read_events(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_success_response_includes_diagnostic_id_and_logs_event(tmp_path: Path) -> None:
    """Successful JSON responses should expose and persist diagnostic IDs."""
    with _client_with_core(tmp_path) as (client, diagnostics):
        resp = client.get("/devices")

    assert resp.status_code == 200
    data = resp.json()
    assert data["diagnostic_id"] == resp.headers["x-diagnostic-id"]

    events = _read_events(diagnostics.path)
    assert len(events) == 1
    assert events[0]["path"] == "/devices"
    assert events[0]["status_code"] == 200
    assert events[0]["diagnostic_id"] == data["diagnostic_id"]
    assert stat.S_IMODE(diagnostics.output_dir.stat().st_mode) == 0o700
    assert stat.S_IMODE(diagnostics.path.stat().st_mode) == 0o600


def test_error_response_logs_redacted_request_payload(tmp_path: Path) -> None:
    """Diagnostics should attach IDs to errors and redact sensitive request fields."""
    with _client_with_core(tmp_path) as (client, diagnostics):
        resp = client.post(
            "/actions/set_text",
            json={"session_id": "missing", "ref": "^g1a1", "text": "top-secret"},
        )

    assert resp.status_code == 404
    data = resp.json()
    assert data["diagnostic_id"] == resp.headers["x-diagnostic-id"]
    assert data["error"]["code"] == "ERR_SESSION_EXPIRED"

    events = _read_events(diagnostics.path)
    assert len(events) == 1
    assert events[0]["session_id"] == "missing"
    assert events[0]["request"]["text"] == "***REDACTED***"
    assert events[0]["error"]["code"] == "ERR_SESSION_EXPIRED"


@pytest.mark.asyncio
async def test_set_text_payload_is_not_persisted(tmp_path: Path) -> None:
    """Typed input should be redacted even though its key is only 'text'."""
    diagnostics = RequestDiagnostics(tmp_path / "diagnostics")

    event = {
        "path": "/actions/set_text",
        "request": {"session_id": "s-123", "ref": "^a1", "text": "audit-secret"},
    }
    await diagnostics.record(event)

    raw_event = diagnostics.path.read_text(encoding="utf-8")
    assert "audit-secret" not in raw_event
    assert _read_events(diagnostics.path)[0]["request"]["text"] == "***REDACTED***"


def test_diagnostics_failure_does_not_replace_endpoint_response(tmp_path: Path) -> None:
    """A completed endpoint response should survive diagnostics storage failure."""
    diagnostics = RequestDiagnostics(tmp_path / "diagnostics")

    async def fail_record(_event: dict[str, Any]) -> None:
        raise OSError("synthetic diagnostics failure")

    with patch.object(diagnostics, "record", side_effect=fail_record):
        from android_emu_agent.daemon import server

        DummyCore.diagnostics = diagnostics
        DummyCore.trace_manager = None
        with patch.object(server, "DaemonCore", DummyCore), TestClient(server.app) as client:
            response = client.get("/devices")

    assert response.status_code == 200
    assert response.json()["devices"] == []


def test_trace_failure_does_not_replace_endpoint_response(tmp_path: Path) -> None:
    """A completed endpoint response should survive trace storage failure."""
    trace_manager = AsyncMock()
    trace_manager.record_daemon_exchange.side_effect = OSError("synthetic trace failure")

    from android_emu_agent.daemon import server

    DummyCore.diagnostics = RequestDiagnostics(tmp_path / "diagnostics")
    DummyCore.trace_manager = trace_manager
    with patch.object(server, "DaemonCore", DummyCore), TestClient(server.app) as client:
        response = client.get("/devices")

    assert response.status_code == 200
    assert response.json()["devices"] == []


class TestDiagnosticsRotation:
    """Tests for bounded diagnostics log growth."""

    @pytest.mark.asyncio
    async def test_rotates_when_size_budget_exceeded(self, tmp_path) -> None:
        """The active log must roll over instead of growing without bound."""
        from android_emu_agent.daemon.diagnostics import RequestDiagnostics

        diagnostics = RequestDiagnostics(tmp_path, max_bytes=400, backup_count=2)
        for index in range(40):
            await diagnostics.record({"diagnostic_id": f"{index:04d}", "path": "/x" * 20})

        assert diagnostics.path.exists()
        assert diagnostics.path.stat().st_size <= 400
        assert diagnostics.path.with_name("requests.ndjson.1").exists()
        # Only backup_count generations are retained.
        assert not diagnostics.path.with_name("requests.ndjson.3").exists()

    @pytest.mark.asyncio
    async def test_rotated_files_stay_owner_only(self, tmp_path) -> None:
        """Rotation must not widen permissions on historical diagnostics."""
        from android_emu_agent.daemon.diagnostics import RequestDiagnostics

        diagnostics = RequestDiagnostics(tmp_path, max_bytes=200, backup_count=1)
        for index in range(20):
            await diagnostics.record({"diagnostic_id": f"{index:04d}", "path": "/y" * 20})

        rotated = diagnostics.path.with_name("requests.ndjson.1")
        assert rotated.exists()
        assert rotated.stat().st_mode & 0o077 == 0

    @pytest.mark.asyncio
    async def test_records_are_not_lost_below_the_budget(self, tmp_path) -> None:
        """A log under the budget keeps every line."""
        from android_emu_agent.daemon.diagnostics import RequestDiagnostics

        diagnostics = RequestDiagnostics(tmp_path, max_bytes=1_000_000)
        for index in range(5):
            await diagnostics.record({"diagnostic_id": f"{index}"})

        assert len(diagnostics.path.read_text().strip().splitlines()) == 5
