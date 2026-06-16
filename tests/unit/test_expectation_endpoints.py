"""Tests for expectation daemon endpoints."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from android_emu_agent.actions.wait import WaitEngine
from android_emu_agent.expectations import ExpectationManager


@dataclass
class DummySession:
    """Minimal session payload for expectation endpoint tests."""

    session_id: str = "s-abc123"
    device_serial: str = "emulator-5554"
    generation: int = 1


class DummySessionManager:
    async def get_session(self, session_id: str) -> DummySession | None:
        if session_id != "s-abc123":
            return None
        return DummySession()


class DummyDeviceManager:
    def __init__(self, device: MagicMock, current_app: dict[str, str | None]) -> None:
        self._device = device
        self._current_app = current_app

    async def get_u2_device(self, serial: str) -> MagicMock | None:
        if serial != "emulator-5554":
            return None
        return self._device

    async def app_current(self, serial: str) -> dict[str, str | None]:
        if serial != "emulator-5554":
            raise RuntimeError("device not found")
        return self._current_app


class DummyCore:
    device: MagicMock
    current_app: dict[str, str | None]

    def __init__(self) -> None:
        self.session_manager = DummySessionManager()
        self.device_manager = DummyDeviceManager(self.__class__.device, self.__class__.current_app)
        self.wait_engine = WaitEngine(default_timeout=0.01, poll_interval=0.001)
        self.expectation_manager = ExpectationManager()
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
    device: MagicMock,
    current_app: dict[str, str | None] | None = None,
) -> Any:
    from android_emu_agent.daemon import server

    DummyCore.device = device
    DummyCore.current_app = current_app or {
        "package": "com.example",
        "activity": ".MainActivity",
        "component": "com.example/.MainActivity",
        "line": "ActivityRecord com.example/.MainActivity",
    }
    with patch.object(server, "DaemonCore", DummyCore), TestClient(server.app) as client:
        yield client


def test_expect_text_passes_when_wait_succeeds() -> None:
    """Text expectations should pass through successful wait results."""
    device = MagicMock()
    element = MagicMock()
    element.exists.return_value = True
    device.return_value = element

    with _client_with_core(device) as client:
        response = client.post(
            "/expect/text",
            json={"session_id": "s-abc123", "text": "Ready", "timeout_ms": 1},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "done"
    assert data["passed"] is True
    assert data["assertion"] == "text"


def test_expect_exists_fails_with_expectation_error() -> None:
    """Selector expectation failures should use ERR_EXPECTATION_FAILED."""
    device = MagicMock()
    element = MagicMock()
    element.exists.return_value = False
    device.return_value = element

    with _client_with_core(device) as client:
        response = client.post(
            "/expect/exists",
            json={
                "session_id": "s-abc123",
                "selector": {"text": "Missing"},
                "timeout_ms": 1,
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "error"
    assert data["passed"] is False
    assert data["error"]["code"] == "ERR_EXPECTATION_FAILED"
    assert data["actual"]["error"]["code"] == "ERR_TIMEOUT"


def test_expect_text_preserves_session_errors() -> None:
    """Expectation endpoints should not hide expired-session failures."""
    device = MagicMock()

    with _client_with_core(device) as client:
        response = client.post(
            "/expect/text",
            json={"session_id": "s-missing", "text": "Ready", "timeout_ms": 1},
        )

    assert response.status_code == 404
    data = response.json()
    assert data["status"] == "error"
    assert data["error"]["code"] == "ERR_SESSION_EXPIRED"


def test_expect_current_app_checks_package_and_activity() -> None:
    """Current-app expectation should compare package and activity."""
    device = MagicMock()

    with _client_with_core(device) as client:
        response = client.post(
            "/expect/current_app",
            json={
                "session_id": "s-abc123",
                "package": "com.example",
                "activity": "MainActivity",
            },
        )

    assert response.status_code == 200
    assert response.json()["status"] == "done"


def test_expect_current_app_requires_expected_state() -> None:
    """Current-app expectation should reject empty expectations with AgentError."""
    device = MagicMock()

    with _client_with_core(device) as client:
        response = client.post("/expect/current_app", json={"session_id": "s-abc123"})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "ERR_EXPECTATION_REQUIRED"
