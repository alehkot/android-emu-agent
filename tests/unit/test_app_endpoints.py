"""Tests for app daemon endpoints."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any
from unittest.mock import patch

from fastapi.testclient import TestClient


@dataclass
class DummySession:
    """Minimal session payload for app endpoint tests."""

    device_serial: str


class DummySessionManager:
    async def get_session(self, session_id: str) -> DummySession | None:
        if session_id != "s-abc123":
            return None
        return DummySession(device_serial="emulator-5554")


class DummyDeviceManager:
    def __init__(self) -> None:
        self.reset_calls: list[tuple[str, str]] = []
        self.intent_calls: list[dict[str, Any]] = []

    async def app_reset(self, serial: str, package: str) -> None:
        self.reset_calls.append((serial, package))

    async def app_start_intent(
        self,
        serial: str,
        *,
        action: str | None = None,
        data_uri: str | None = None,
        component: str | None = None,
        package: str | None = None,
        wait_for_debugger: bool = False,
    ) -> None:
        self.intent_calls.append(
            {
                "serial": serial,
                "action": action,
                "data_uri": data_uri,
                "component": component,
                "package": package,
                "wait_for_debugger": wait_for_debugger,
            }
        )


class DummyCore:
    device_manager: DummyDeviceManager
    session_manager: DummySessionManager

    def __init__(self) -> None:
        self.device_manager = self.__class__.device_manager
        self.session_manager = self.__class__.session_manager
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

    device_manager = DummyDeviceManager()
    DummyCore.device_manager = device_manager
    DummyCore.session_manager = DummySessionManager()

    with patch.object(server, "DaemonCore", DummyCore), TestClient(server.app) as client:
        yield client, device_manager


def test_app_reset_rejects_invalid_package() -> None:
    """Should reject reset packages before invoking the device manager."""
    with _client_with_core() as (client, device_manager):
        resp = client.post(
            "/app/reset",
            json={"session_id": "s-abc123", "package": "com.example.app;id"},
        )

    assert resp.status_code == 400
    data = resp.json()
    assert data["status"] == "error"
    assert data["error"]["code"] == "ERR_INVALID_PACKAGE"
    assert device_manager.reset_calls == []


def test_app_intent_rejects_invalid_package() -> None:
    """Should reject optional package fields before building an intent command."""
    with _client_with_core() as (client, device_manager):
        resp = client.post(
            "/app/intent",
            json={
                "session_id": "s-abc123",
                "action": "android.intent.action.VIEW",
                "package": "com.example.app;id",
            },
        )

    assert resp.status_code == 400
    data = resp.json()
    assert data["status"] == "error"
    assert data["error"]["code"] == "ERR_INVALID_PACKAGE"
    assert device_manager.intent_calls == []
