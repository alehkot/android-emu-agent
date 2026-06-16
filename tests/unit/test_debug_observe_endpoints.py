"""Tests for fused debug observation endpoint."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any
from unittest.mock import patch

from fastapi.testclient import TestClient


@dataclass
class DummySession:
    device_serial: str = "emulator-5554"


class DummySessionManager:
    def __init__(self, snapshot: dict[str, Any] | None) -> None:
        self.snapshot = snapshot

    async def get_session(self, session_id: str) -> DummySession | None:
        if session_id != "s-abc123":
            return None
        return DummySession()

    async def get_last_snapshot(self, session_id: str) -> dict[str, Any] | None:
        if session_id != "s-abc123":
            return None
        return self.snapshot


class DummyDeviceManager:
    async def app_current(self, serial: str) -> dict[str, str | None]:
        assert serial == "emulator-5554"
        return {
            "package": "com.example.app",
            "activity": ".MainActivity",
            "component": "com.example.app/.MainActivity",
            "line": "ACTIVITY com.example.app/.MainActivity",
        }


class DummyDebugManager:
    def __init__(self, status_payload: dict[str, Any]) -> None:
        self.status_payload = status_payload
        self.peek_calls: list[dict[str, Any]] = []
        self.logpoint_calls: list[dict[str, Any]] = []
        self.stack_calls: list[dict[str, Any]] = []

    async def status(self, session_id: str) -> dict[str, Any]:
        assert session_id == "s-abc123"
        return self.status_payload

    async def peek_events(
        self,
        session_id: str,
        *,
        drain: bool,
        limit: int,
    ) -> dict[str, Any]:
        self.peek_calls.append({"session_id": session_id, "drain": drain, "limit": limit})
        return {
            "status": "attached",
            "session_id": session_id,
            "count": 1,
            "buffer_count": 2,
            "drained": drain,
            "events": [{"type": "breakpoint_hit", "breakpoint_id": 7}],
        }

    async def list_logpoint_hits(
        self,
        session_id: str,
        *,
        limit: int,
    ) -> dict[str, Any]:
        self.logpoint_calls.append({"session_id": session_id, "limit": limit})
        return {
            "status": "attached",
            "session_id": session_id,
            "count": 1,
            "buffer_count": 3,
            "hits": [{"type": "logpoint_hit", "breakpoint_id": 9, "message": "x=1"}],
        }

    async def stack_trace(
        self,
        *,
        session_id: str,
        thread_name: str,
        max_frames: int,
    ) -> dict[str, Any]:
        self.stack_calls.append(
            {"session_id": session_id, "thread_name": thread_name, "max_frames": max_frames}
        )
        return {
            "status": "suspended",
            "thread": thread_name,
            "frames": [{"index": 0, "location": "com.example.MainActivity:42"}],
        }


class DummyCore:
    session_manager: DummySessionManager
    device_manager: DummyDeviceManager
    debug_manager: DummyDebugManager

    def __init__(self) -> None:
        self.session_manager = self.__class__.session_manager
        self.device_manager = self.__class__.device_manager
        self.debug_manager = self.__class__.debug_manager
        self._running = False

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running


@contextmanager
def _client_with_core(
    *,
    status_payload: dict[str, Any],
    snapshot: dict[str, Any] | None,
) -> Any:
    from android_emu_agent.daemon import server

    debug_manager = DummyDebugManager(status_payload)
    DummyCore.session_manager = DummySessionManager(snapshot)
    DummyCore.device_manager = DummyDeviceManager()
    DummyCore.debug_manager = debug_manager

    with patch.object(server, "DaemonCore", DummyCore), TestClient(server.app) as client:
        yield client, debug_manager


def test_debug_observe_fuses_app_snapshot_and_debug_context() -> None:
    """Should return bounded app, UI, event, logpoint, and stack context."""
    snapshot = {
        "generation": 12,
        "context": {"package": "com.example.app", "activity": ".MainActivity"},
        "elements": [
            {
                "ref": "^a1",
                "role": "button",
                "label": "Submit",
                "resource_id": "com.example:id/submit",
                "bounds": [1, 2, 3, 4],
            },
            {"ref": "^a2", "role": "text", "label": "Ignored by ref limit"},
        ],
    }
    with _client_with_core(
        status_payload={"status": "attached", "suspended": True},
        snapshot=snapshot,
    ) as (client, debug_manager):
        response = client.post(
            "/debug/observe",
            json={
                "session_id": "s-abc123",
                "thread": "main",
                "max_frames": 4,
                "event_limit": 1,
                "logpoint_limit": 1,
                "ref_limit": 1,
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "done"
    assert data["app"]["package"] == "com.example.app"
    assert data["snapshot"]["generation"] == 12
    assert data["snapshot"]["element_count"] == 2
    assert data["snapshot"]["refs"] == [
        {
            "ref": "^a1",
            "role": "button",
            "label": "Submit",
            "resource_id": "com.example:id/submit",
            "bounds": [1, 2, 3, 4],
        }
    ]
    assert data["debug"]["status"] == "attached"
    assert data["events"]["events"][0]["type"] == "breakpoint_hit"
    assert data["logpoints"]["hits"][0]["message"] == "x=1"
    assert data["stack"]["frames"][0]["location"] == "com.example.MainActivity:42"
    assert debug_manager.peek_calls == [
        {"session_id": "s-abc123", "drain": False, "limit": 1}
    ]
    assert debug_manager.logpoint_calls == [{"session_id": "s-abc123", "limit": 1}]
    assert debug_manager.stack_calls == [
        {"session_id": "s-abc123", "thread_name": "main", "max_frames": 4}
    ]


def test_debug_observe_skips_debug_sections_when_not_attached() -> None:
    """Should still return app/snapshot context when debugger is not attached."""
    with _client_with_core(
        status_payload={"status": "not_attached", "session_id": "s-abc123"},
        snapshot=None,
    ) as (client, debug_manager):
        response = client.post("/debug/observe", json={"session_id": "s-abc123"})

    assert response.status_code == 200
    data = response.json()
    assert data["debug"]["status"] == "not_attached"
    assert data["snapshot"] == {"status": "missing", "available": False}
    assert data["events"]["status"] == "skipped"
    assert data["logpoints"]["status"] == "skipped"
    assert data["stack"]["status"] == "skipped"
    assert debug_manager.peek_calls == []
    assert debug_manager.logpoint_calls == []
    assert debug_manager.stack_calls == []
