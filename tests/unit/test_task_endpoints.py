"""Tests for task daemon endpoints."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from android_emu_agent.actions.executor import ActionExecutor
from android_emu_agent.actions.wait import WaitEngine
from android_emu_agent.tasks import TaskManager
from android_emu_agent.ui.ref_resolver import RefResolver


@dataclass
class DummySession:
    """Minimal session payload for task endpoint tests."""

    session_id: str = "s-abc123"
    device_serial: str = "emulator-5554"
    generation: int = 1


class DummySessionManager:
    async def get_session(self, session_id: str) -> DummySession | None:
        if session_id != "s-abc123":
            return None
        return DummySession()


class DummyDeviceManager:
    def __init__(self, device: MagicMock) -> None:
        self._device = device

    async def get_u2_device(self, serial: str) -> MagicMock | None:
        if serial != "emulator-5554":
            return None
        return self._device


class DummyCore:
    device: MagicMock

    def __init__(self) -> None:
        self.session_manager = DummySessionManager()
        self.device_manager = DummyDeviceManager(self.__class__.device)
        self.action_executor = ActionExecutor()
        self.wait_engine = WaitEngine(default_timeout=0.01, poll_interval=0.001)
        self.ref_resolver = RefResolver()
        self.task_manager = TaskManager()
        self._running = False

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running


@contextmanager
def _client_with_core(device: MagicMock) -> Any:
    from android_emu_agent.daemon import server

    DummyCore.device = device
    with patch.object(server, "DaemonCore", DummyCore), TestClient(server.app) as client:
        yield client


def test_task_validate_endpoint_rejects_bad_spec() -> None:
    """Validation endpoint should return AgentError payloads for bad specs."""
    device = MagicMock()

    with _client_with_core(device) as client:
        response = client.post("/tasks/validate", json={"task": {"steps": [{"action": "pinch"}]}})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "ERR_TASK_UNSUPPORTED_STEP"


def test_task_script_validate_endpoint_parses_and_validates() -> None:
    """Script validation endpoint should return compiled task and plan."""
    device = MagicMock()

    with _client_with_core(device) as client:
        response = client.post(
            "/tasks/script/validate",
            json={"script": 'name "script smoke"\nwait idle\n', "source_name": "smoke.aea"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "done"
    assert data["source_name"] == "smoke.aea"
    assert data["task"]["name"] == "script smoke"
    assert data["plan"]["step_count"] == 1


def test_task_run_endpoint_dispatches_wait_verifier() -> None:
    """Run endpoint should execute verifier calls through existing wait handlers."""
    device = MagicMock()
    element = MagicMock()
    element.exists.return_value = True
    device.return_value = element

    with _client_with_core(device) as client:
        response = client.post(
            "/tasks/run",
            json={
                "session_id": "s-abc123",
                "task": {
                    "name": "wait smoke",
                    "verifiers": [{"type": "exists", "text": "Ready"}],
                },
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "done"
    assert data["passed"] is True
    assert data["verifiers"][0]["operation"] == "exists"
    device.assert_called_with(text="Ready")


def test_task_script_run_endpoint_dispatches_compiled_script() -> None:
    """Script run endpoint should parse then execute through existing task dispatcher."""
    device = MagicMock()

    with _client_with_core(device) as client:
        response = client.post(
            "/tasks/script/run",
            json={"session_id": "s-abc123", "script": "wait idle\n", "source_name": "smoke.aea"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["source_name"] == "smoke.aea"
    assert data["compiled_task"]["steps"] == [{"wait": "idle"}]
    assert data["passed"] is True
