"""Tests for session endpoint resource ownership."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from android_emu_agent.daemon.diagnostics import RequestDiagnostics


@dataclass
class DummySession:
    session_id: str = "s-abc123"
    device_serial: str = "emulator-5554"
    generation: int = 3


class DummyCore:
    session_manager: AsyncMock
    device_manager: AsyncMock
    trace_manager: AsyncMock
    debug_manager: AsyncMock
    ref_resolver: MagicMock
    diagnostics: RequestDiagnostics

    def __init__(self) -> None:
        self.session_manager = self.__class__.session_manager
        self.device_manager = self.__class__.device_manager
        self.trace_manager = self.__class__.trace_manager
        self.debug_manager = self.__class__.debug_manager
        self.ref_resolver = self.__class__.ref_resolver
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

    session = DummySession()
    DummyCore.session_manager = AsyncMock()
    DummyCore.session_manager.get_session.return_value = session
    DummyCore.session_manager.close_session.return_value = True
    DummyCore.device_manager = AsyncMock()
    DummyCore.device_manager.get_adb_device.return_value = MagicMock(name="adb_device")
    DummyCore.trace_manager = AsyncMock()
    DummyCore.trace_manager.stop_if_active.return_value = {
        "status": "stopped",
        "session_id": session.session_id,
        "path": "/tmp/session-trace.aea-trace.zip",
    }
    DummyCore.debug_manager = AsyncMock()
    DummyCore.debug_manager.cleanup_session.return_value = True
    DummyCore.ref_resolver = MagicMock()
    DummyCore.diagnostics = RequestDiagnostics(tmp_path / "diagnostics")

    with patch.object(server, "DaemonCore", DummyCore), TestClient(server.app) as client:
        yield client


def test_session_stop_releases_resources_before_deleting_session(tmp_path: Path) -> None:
    """Stopping a session should finalize every resource owned by that session."""
    with _client_with_core(tmp_path) as client:
        response = client.post("/sessions/stop", json={"session_id": "s-abc123"})

    assert response.status_code == 200
    assert response.json()["debugger_cleaned"] is True
    assert response.json()["trace"]["path"] == "/tmp/session-trace.aea-trace.zip"
    DummyCore.trace_manager.stop_if_active.assert_awaited_once_with("s-abc123")
    DummyCore.device_manager.get_adb_device.assert_awaited_once_with("emulator-5554")
    DummyCore.debug_manager.cleanup_session.assert_awaited_once_with(
        "s-abc123", DummyCore.device_manager.get_adb_device.return_value
    )
    DummyCore.session_manager.close_session.assert_awaited_once_with("s-abc123")
    DummyCore.ref_resolver.clear_session.assert_called_once_with("s-abc123")


def test_session_stop_preserves_session_when_cleanup_fails(tmp_path: Path) -> None:
    """Failed cleanup should remain retryable instead of orphaning resources."""
    with _client_with_core(tmp_path) as client:
        DummyCore.trace_manager.stop_if_active.side_effect = OSError("archive failed")
        response = client.post("/sessions/stop", json={"session_id": "s-abc123"})

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "ERR_SESSION_CLEANUP_FAILED"
    DummyCore.debug_manager.cleanup_session.assert_awaited_once()
    DummyCore.session_manager.close_session.assert_not_awaited()
    DummyCore.ref_resolver.clear_session.assert_not_called()
