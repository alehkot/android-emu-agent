"""Tests for request diagnostics middleware."""

from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import patch

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

    def __init__(self) -> None:
        self.device_manager = DummyDeviceManager()
        self.session_manager = DummySessionManager()
        self.health_monitor = DummyHealthMonitor()
        self.diagnostics = self.__class__.diagnostics
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


def test_error_response_logs_redacted_request_payload(tmp_path: Path) -> None:
    """Diagnostics should attach IDs to errors and redact sensitive request fields."""
    with _client_with_core(tmp_path) as (client, diagnostics):
        resp = client.post(
            "/actions/back",
            json={"session_id": "missing", "api_key": "top-secret"},
        )

    assert resp.status_code == 404
    data = resp.json()
    assert data["diagnostic_id"] == resp.headers["x-diagnostic-id"]
    assert data["error"]["code"] == "ERR_SESSION_EXPIRED"

    events = _read_events(diagnostics.path)
    assert len(events) == 1
    assert events[0]["session_id"] == "missing"
    assert events[0]["request"]["api_key"] == "***REDACTED***"
    assert events[0]["error"]["code"] == "ERR_SESSION_EXPIRED"
