"""Tests for stale-ref healing in action and wait endpoints."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from android_emu_agent.actions.executor import ActionExecutor
from android_emu_agent.daemon.diagnostics import RequestDiagnostics
from android_emu_agent.ui.ref_resolver import RefResolver


@dataclass
class DummySession:
    device_serial: str
    generation: int


class DummySessionManager:
    def __init__(self, session: DummySession) -> None:
        self._session = session

    async def get_session(self, session_id: str) -> DummySession | None:
        if session_id != "s-abc123":
            return None
        return self._session

    async def list_sessions(self) -> list[DummySession]:
        return [self._session]


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


class DummyWaitResult:
    def to_dict(self) -> dict[str, Any]:
        return {"status": "done", "elapsed_ms": 1.0}


class DummyWaitEngine:
    def __init__(self) -> None:
        self.exists_calls: list[dict[str, Any]] = []
        self.gone_calls: list[dict[str, Any]] = []

    async def wait_exists(
        self,
        _device: object,
        selector: dict[str, str],
        timeout: float | None = None,
    ) -> DummyWaitResult:
        self.exists_calls.append({"selector": selector, "timeout": timeout})
        return DummyWaitResult()

    async def wait_gone(
        self,
        _device: object,
        selector: dict[str, str],
        timeout: float | None = None,
    ) -> DummyWaitResult:
        self.gone_calls.append({"selector": selector, "timeout": timeout})
        return DummyWaitResult()


class DummyCore:
    session_manager: DummySessionManager
    device_manager: DummyDeviceManager
    action_executor: ActionExecutor
    wait_engine: DummyWaitEngine
    ref_resolver: RefResolver
    database: DummyDatabase
    diagnostics: RequestDiagnostics

    def __init__(self) -> None:
        self.session_manager = self.__class__.session_manager
        self.device_manager = self.__class__.device_manager
        self.action_executor = self.__class__.action_executor
        self.wait_engine = self.__class__.wait_engine
        self.ref_resolver = self.__class__.ref_resolver
        self.database = self.__class__.database
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
def _client_with_core(tmp_path: Path, device: MagicMock, generation: int = 2) -> Any:
    from android_emu_agent.daemon import server

    wait_engine = DummyWaitEngine()
    ref_resolver = RefResolver()
    diagnostics = RequestDiagnostics(tmp_path / "diagnostics")

    DummyCore.session_manager = DummySessionManager(
        DummySession(device_serial="emulator-5554", generation=generation)
    )
    DummyCore.device_manager = DummyDeviceManager(device)
    DummyCore.action_executor = ActionExecutor()
    DummyCore.wait_engine = wait_engine
    DummyCore.ref_resolver = ref_resolver
    DummyCore.database = DummyDatabase()
    DummyCore.diagnostics = diagnostics

    with patch.object(server, "DaemonCore", DummyCore), TestClient(server.app) as client:
        yield client, ref_resolver, wait_engine


def test_action_tap_rebinds_stale_ref_without_forcing_coordinate_fallback(tmp_path: Path) -> None:
    """Stale ref taps should use healed semantics before falling back to raw coordinates."""
    device = MagicMock()

    with _client_with_core(tmp_path, device) as (client, ref_resolver, _wait_engine):
        ref_resolver.store_refs(
            "s-abc123",
            generation=1,
            elements=[
                {
                    "ref": "^a1",
                    "label": "Settings",
                    "class": "android.widget.LinearLayout",
                    "bounds": [0, 0, 40, 40],
                    "index": 0,
                    "ancestry_path": "hierarchy/android.widget.FrameLayout/android.widget.LinearLayout",
                    "element_hash": "settings-row",
                    "selector_chain": [
                        {"kind": "label", "value": "Settings"},
                        {"kind": "class_name", "value": "android.widget.LinearLayout"},
                    ],
                }
            ],
        )
        ref_resolver.store_refs(
            "s-abc123",
            generation=2,
            elements=[
                {
                    "ref": "^a7",
                    "label": "Settings",
                    "class": "android.widget.LinearLayout",
                    "bounds": [100, 100, 220, 220],
                    "index": 0,
                    "ancestry_path": "hierarchy/android.widget.FrameLayout/android.widget.LinearLayout",
                    "element_hash": "settings-row",
                    "selector_chain": [
                        {"kind": "label", "value": "Settings"},
                        {"kind": "class_name", "value": "android.widget.LinearLayout"},
                    ],
                }
            ],
        )

        resp = client.post("/actions/tap", json={"session_id": "s-abc123", "ref": "^a1"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "done"
    assert "warning" in data
    device.click.assert_not_called()
    device.return_value.click.assert_called_once()


def test_wait_exists_rebinds_stale_ref_before_building_selector(tmp_path: Path) -> None:
    """Wait endpoints should heal stale refs instead of returning ERR_STALE_REF."""
    device = MagicMock()

    with _client_with_core(tmp_path, device) as (client, ref_resolver, wait_engine):
        ref_resolver.store_refs(
            "s-abc123",
            generation=1,
            elements=[
                {
                    "ref": "^a1",
                    "label": "Settings",
                    "class": "android.widget.LinearLayout",
                    "bounds": [0, 0, 40, 40],
                    "index": 0,
                    "ancestry_path": "hierarchy/android.widget.FrameLayout/android.widget.LinearLayout",
                    "element_hash": "settings-row",
                    "selector_chain": [
                        {"kind": "label", "value": "Settings"},
                        {"kind": "class_name", "value": "android.widget.LinearLayout"},
                    ],
                }
            ],
        )
        ref_resolver.store_refs(
            "s-abc123",
            generation=2,
            elements=[
                {
                    "ref": "^a7",
                    "resource_id": "com.test:id/settings_row",
                    "label": "Settings",
                    "class": "android.widget.LinearLayout",
                    "bounds": [100, 100, 220, 220],
                    "index": 0,
                    "ancestry_path": "hierarchy/android.widget.FrameLayout/android.widget.LinearLayout",
                    "element_hash": "settings-row",
                    "selector_chain": [
                        {"kind": "resource_id", "value": "com.test:id/settings_row"},
                        {"kind": "label", "value": "Settings"},
                    ],
                }
            ],
        )

        resp = client.post("/wait/exists", json={"session_id": "s-abc123", "ref": "^a1"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "done"
    assert "warning" in data
    assert wait_engine.exists_calls == [
        {"selector": {"resourceId": "com.test:id/settings_row"}, "timeout": None}
    ]
