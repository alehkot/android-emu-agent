"""Tests for reliability profile daemon endpoint."""

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
    async def get_session(self, session_id: str) -> DummySession | None:
        if session_id != "s-abc123":
            return None
        return DummySession()


class DummyDeviceManager:
    def __init__(self, device: object) -> None:
        self.device = device

    async def get_adb_device(self, serial: str) -> object | None:
        if serial != "emulator-5554":
            return None
        return self.device

    async def get_device(self, serial: str) -> dict[str, str] | None:
        if serial != "emulator-5554":
            return None
        return {"serial": serial}


class DummyReliabilityManager:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def profile(
        self,
        device: object,
        package: str,
        *,
        since: str | None,
        include_raw: bool,
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "device": device,
                "package": package,
                "since": since,
                "include_raw": include_raw,
            }
        )
        return {
            "package": package,
            "since": since,
            "include_raw": include_raw,
            "sections": {"process": {"status": "done", "pid": 123}},
            "output": "PROFILE com.example.app",
        }


class DummyCore:
    session_manager: DummySessionManager
    device_manager: DummyDeviceManager
    reliability_manager: DummyReliabilityManager

    def __init__(self) -> None:
        self.session_manager = self.__class__.session_manager
        self.device_manager = self.__class__.device_manager
        self.reliability_manager = self.__class__.reliability_manager
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

    device = object()
    manager = DummyReliabilityManager()
    DummyCore.session_manager = DummySessionManager()
    DummyCore.device_manager = DummyDeviceManager(device)
    DummyCore.reliability_manager = manager

    with patch.object(server, "DaemonCore", DummyCore), TestClient(server.app) as client:
        yield client, manager, device


def test_reliability_profile_endpoint_calls_manager() -> None:
    """Should resolve target and call profile manager with bounded options."""
    with _client_with_core() as (client, manager, device):
        response = client.post(
            "/reliability/profile",
            json={
                "session_id": "s-abc123",
                "package": "com.example.app",
                "since": "100",
                "include_raw": True,
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "done"
    assert data["serial"] == "emulator-5554"
    assert data["sections"]["process"]["pid"] == 123
    assert manager.calls == [
        {
            "device": device,
            "package": "com.example.app",
            "since": "100",
            "include_raw": True,
        }
    ]


def test_reliability_profile_rejects_invalid_package() -> None:
    """Should reject unsafe package names before invoking diagnostics."""
    with _client_with_core() as (client, manager, _device):
        response = client.post(
            "/reliability/profile",
            json={"serial": "emulator-5554", "package": "com.example.app;id"},
        )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "ERR_INVALID_PACKAGE"
    assert manager.calls == []
