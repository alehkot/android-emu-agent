"""Tests for artifact-related daemon endpoints."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import patch

from fastapi.testclient import TestClient

from android_emu_agent.errors import AgentError


@dataclass
class DummySession:
    """Simple session payload returned by session manager."""

    device_serial: str


class DummySessionManager:
    async def get_session(self, session_id: str) -> DummySession | None:
        if session_id != "s-abc123":
            return None
        return DummySession(device_serial="emulator-5554")


class DummyDeviceManager:
    async def get_u2_device(self, serial: str) -> object | None:
        if serial != "emulator-5554":
            return None
        return object()


class DummyArtifactManager:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.error: AgentError | None = None

    async def pull_logs(
        self,
        device: object,
        session_id: str,
        package: str | None = None,
        level: str | None = None,
        since: str | int | None = None,
        follow: bool = False,
        filename: str | None = None,
    ) -> Path:
        self.calls.append(
            {
                "device": device,
                "session_id": session_id,
                "package": package,
                "level": level,
                "since": since,
                "follow": follow,
                "filename": filename,
            }
        )
        if self.error:
            raise self.error
        return Path("/tmp/logcat.txt")


class DummyCore:
    device_manager: DummyDeviceManager
    session_manager: DummySessionManager
    artifact_manager: DummyArtifactManager

    def __init__(self) -> None:
        self.device_manager = self.__class__.device_manager
        self.session_manager = self.__class__.session_manager
        self.artifact_manager = self.__class__.artifact_manager
        self._running = False

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running


@contextmanager
def _client_with_core() -> Any:
    from android_emu_agent.daemon import server

    artifact_manager = DummyArtifactManager()
    DummyCore.device_manager = DummyDeviceManager()
    DummyCore.session_manager = DummySessionManager()
    DummyCore.artifact_manager = artifact_manager

    with patch.object(server, "DaemonCore", DummyCore), TestClient(server.app) as client:
        yield client, artifact_manager


def test_artifact_logs_type_normalizes_to_priority() -> None:
    """Should map friendly log type aliases to logcat priorities."""
    with _client_with_core() as (client, artifact_manager):
        resp = client.post(
            "/artifacts/logs",
            json={
                "session_id": "s-abc123",
                "log_type": "errors",
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "done"
    assert data["path"] == "/tmp/logcat.txt"
    assert len(artifact_manager.calls) == 1
    assert artifact_manager.calls[0]["level"] == "E"


def test_artifact_logs_rejects_invalid_log_type() -> None:
    """Should reject unknown log type aliases."""
    with _client_with_core() as (client, _artifact_manager):
        resp = client.post(
            "/artifacts/logs",
            json={
                "session_id": "s-abc123",
                "log_type": "critical-only",
            },
        )

    assert resp.status_code == 400
    data = resp.json()
    assert data["status"] == "error"
    assert data["error"]["code"] == "ERR_INVALID_LOG_TYPE"


def test_artifact_logs_rejects_conflicting_filters() -> None:
    """Should reject mixed level/type filters resolving to different priorities."""
    with _client_with_core() as (client, _artifact_manager):
        resp = client.post(
            "/artifacts/logs",
            json={
                "session_id": "s-abc123",
                "level": "warn",
                "log_type": "errors",
            },
        )

    assert resp.status_code == 400
    data = resp.json()
    assert data["status"] == "error"
    assert data["error"]["code"] == "ERR_CONFLICTING_LOG_FILTERS"


def test_artifact_logs_surfaces_manager_errors() -> None:
    """Should map manager AgentError responses to structured 400 payloads."""
    with _client_with_core() as (client, artifact_manager):
        artifact_manager.error = AgentError(
            code="ERR_INVALID_LOGCAT_SINCE",
            message="bad",
            remediation="Use valid --since",
        )
        resp = client.post(
            "/artifacts/logs",
            json={
                "session_id": "s-abc123",
                "since": "yesterday-ish",
            },
        )

    assert resp.status_code == 400
    data = resp.json()
    assert data["status"] == "error"
    assert data["error"]["code"] == "ERR_INVALID_LOGCAT_SINCE"
