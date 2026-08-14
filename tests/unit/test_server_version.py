"""Tests for daemon package metadata."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from fastapi.testclient import TestClient

from android_emu_agent import __version__
from android_emu_agent.daemon.server import app


def test_daemon_metadata_uses_package_version() -> None:
    """FastAPI and OpenAPI metadata should stay aligned with release artifacts."""
    assert app.version == __version__
    assert app.openapi()["info"]["version"] == __version__


class _HealthOnlyCore:
    """Minimal core stub exposing just what /health reads."""

    trace_manager: Any = None
    diagnostics: Any = None

    def __init__(self) -> None:
        self.health_monitor = self._Monitor()
        self.session_manager = self._Sessions()
        self.diagnostics = None
        self.trace_manager = None
        self._running = False

    class _Monitor:
        def get_status(self) -> dict[str, Any]:
            return {"devices": {}}

    class _Sessions:
        async def list_sessions(self) -> list[object]:
            return []

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running


def test_health_reports_daemon_version() -> None:
    """Health should report which install owns the socket."""
    from android_emu_agent.daemon import server

    with patch.object(server, "DaemonCore", _HealthOnlyCore), TestClient(server.app) as client:
        payload = client.get("/health").json()

    assert payload["version"] == __version__
