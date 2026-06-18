"""Tests for action daemon endpoints."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from android_emu_agent.actions.executor import ActionExecutor
from android_emu_agent.ui.ref_resolver import RefResolver


@dataclass
class DummySession:
    """Minimal session payload for action endpoint tests."""

    device_serial: str
    generation: int


class DummySessionManager:
    def __init__(self, session: DummySession) -> None:
        self._session = session

    async def get_session(self, session_id: str) -> DummySession | None:
        if session_id != "s-abc123":
            return None
        return self._session


class DummyDeviceManager:
    def __init__(self, device: MagicMock) -> None:
        self._device = device

    async def get_u2_device(self, serial: str) -> MagicMock | None:
        if serial != "emulator-5554":
            return None
        return self._device


class DummyDatabase:
    async def get_ref_any_generation(
        self,
        _session_id: str,
        _ref: str,
    ) -> tuple[int, dict[str, Any]] | None:
        return None

    async def get_refs_for_generation(
        self,
        _session_id: str,
        _generation: int,
    ) -> list[dict[str, Any]]:
        return []


class DummyCore:
    session_manager: DummySessionManager
    device_manager: DummyDeviceManager
    action_executor: ActionExecutor
    ref_resolver: RefResolver
    database: DummyDatabase

    def __init__(self) -> None:
        self.session_manager = self.__class__.session_manager
        self.device_manager = self.__class__.device_manager
        self.action_executor = self.__class__.action_executor
        self.ref_resolver = self.__class__.ref_resolver
        self.database = self.__class__.database
        self._running = False

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running


@contextmanager
def _client_with_core(device: MagicMock, generation: int = 2) -> Any:
    from android_emu_agent.daemon import server

    ref_resolver = RefResolver()
    DummyCore.session_manager = DummySessionManager(
        DummySession(device_serial="emulator-5554", generation=generation)
    )
    DummyCore.device_manager = DummyDeviceManager(device)
    DummyCore.action_executor = ActionExecutor()
    DummyCore.ref_resolver = ref_resolver
    DummyCore.database = DummyDatabase()

    with patch.object(server, "DaemonCore", DummyCore), TestClient(server.app) as client:
        yield client, ref_resolver


def test_swipe_uses_ref_container_bounds() -> None:
    """Swipe should use container ref bounds instead of full-screen bounds."""
    device = MagicMock()

    with _client_with_core(device) as (client, ref_resolver):
        ref_resolver.store_refs(
            "s-abc123",
            generation=2,
            elements=[
                {
                    "ref": "^a1",
                    "label": "Scrollable list",
                    "class": "androidx.recyclerview.widget.RecyclerView",
                    "bounds": [100, 100, 300, 500],
                    "index": 0,
                    "ancestry_path": "hierarchy/android.widget.FrameLayout/RecyclerView",
                }
            ],
        )

        resp = client.post(
            "/actions/swipe",
            json={
                "session_id": "s-abc123",
                "direction": "up",
                "container": "^a1",
                "distance": 0.5,
                "duration_ms": 400,
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "done"
    assert data["bounds"] == [100, 100, 300, 500]
    device.swipe.assert_called_once_with(200, 400, 200, 200, 0.4)


def test_tap_tries_fallback_selectors_in_order() -> None:
    """Tap should try selector alternatives separated by ||."""
    device = MagicMock()
    missing = MagicMock()
    missing.exists.return_value = False
    found = MagicMock()
    found.exists.return_value = True
    device.side_effect = [missing, found]

    with _client_with_core(device) as (client, _ref_resolver):
        resp = client.post(
            "/actions/tap",
            json={
                "session_id": "s-abc123",
                "ref": 'text:"Missing" || id:com.example:id/login',
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "done"
    assert data["matched_selector"] == "resourceId:com.example:id/login"
    assert device.call_args_list[0].kwargs == {"text": "Missing"}
    assert device.call_args_list[1].kwargs == {"resourceId": "com.example:id/login"}
    found.click.assert_called_once_with()


def test_swipe_rejects_invalid_distance() -> None:
    """Swipe should reject distances outside the supported range."""
    device = MagicMock()

    with _client_with_core(device) as (client, _ref_resolver):
        resp = client.post(
            "/actions/swipe",
            json={
                "session_id": "s-abc123",
                "direction": "up",
                "distance": 1.5,
            },
        )

    assert resp.status_code == 400
    data = resp.json()
    assert data["status"] == "error"
    assert data["error"]["code"] == "ERR_INVALID_DISTANCE"
    device.swipe.assert_not_called()


def test_swipe_rejects_coordinate_container() -> None:
    """Swipe containers need bounds, so coords selectors are invalid."""
    device = MagicMock()

    with _client_with_core(device) as (client, _ref_resolver):
        resp = client.post(
            "/actions/swipe",
            json={
                "session_id": "s-abc123",
                "direction": "up",
                "container": "coords:10,20",
            },
        )

    assert resp.status_code == 400
    data = resp.json()
    assert data["status"] == "error"
    assert data["error"]["code"] == "ERR_INVALID_CONTAINER"
    device.swipe.assert_not_called()
