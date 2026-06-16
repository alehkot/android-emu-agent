"""Tests for system surface daemon endpoints."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any
from unittest.mock import patch

from fastapi.testclient import TestClient

from android_emu_agent.system import SystemManager


@dataclass
class ShellResult:
    output: str = ""


class FakeDevice:
    def __init__(self) -> None:
        self.commands: list[str] = []

    def shell(self, command: str) -> ShellResult:
        self.commands.append(command)
        return ShellResult("ok")


@dataclass
class DummySession:
    device_serial: str


class DummySessionManager:
    async def get_session(self, session_id: str) -> DummySession | None:
        if session_id != "s-abc123":
            return None
        return DummySession(device_serial="emulator-5554")


class DummyDeviceManager:
    def __init__(self, device: FakeDevice) -> None:
        self.device = device

    async def get_adb_device(self, serial: str) -> FakeDevice | None:
        if serial != "emulator-5554":
            return None
        return self.device

    async def get_device(self, serial: str) -> dict[str, Any] | None:
        if serial != "emulator-5554":
            return None
        return {"serial": serial}


class DummyCore:
    device_manager: DummyDeviceManager
    session_manager: DummySessionManager
    system_manager: SystemManager

    def __init__(self) -> None:
        self.device_manager = self.__class__.device_manager
        self.session_manager = self.__class__.session_manager
        self.system_manager = self.__class__.system_manager
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

    device = FakeDevice()
    DummyCore.device_manager = DummyDeviceManager(device)
    DummyCore.session_manager = DummySessionManager()
    DummyCore.system_manager = SystemManager()

    with patch.object(server, "DaemonCore", DummyCore), TestClient(server.app) as client:
        yield client, device


def test_system_notifications_open_calls_statusbar_command() -> None:
    """Should open notification shade via shell-backed system manager."""
    with _client_with_core() as (client, device):
        response = client.post(
            "/system/notifications/open",
            json={"serial": "emulator-5554"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "done"
    assert data["surface"] == "notifications"
    assert data["state"] == "open"
    assert device.commands == ["cmd statusbar expand-notifications"]


def test_system_permissions_grant_validates_and_calls_pm() -> None:
    """Should validate package names and grant runtime permissions."""
    with _client_with_core() as (client, device):
        response = client.post(
            "/system/permissions/grant",
            json={
                "session_id": "s-abc123",
                "package": "com.example.app",
                "permission": "android.permission.POST_NOTIFICATIONS",
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "done"
    assert data["serial"] == "emulator-5554"
    assert data["granted"] is True
    assert device.commands == ["pm grant com.example.app android.permission.POST_NOTIFICATIONS"]


def test_system_permissions_grant_rejects_invalid_permission() -> None:
    """Should reject unsafe permission names before invoking pm grant."""
    with _client_with_core() as (client, device):
        response = client.post(
            "/system/permissions/grant",
            json={
                "serial": "emulator-5554",
                "package": "com.example.app",
                "permission": "android.permission.CAMERA;id",
            },
        )

    assert response.status_code == 400
    data = response.json()
    assert data["status"] == "error"
    assert data["error"]["code"] == "ERR_INVALID_PERMISSION"
    assert device.commands == []


def test_system_permissions_list_rejects_invalid_package() -> None:
    """Should validate package names before running dumpsys."""
    with _client_with_core() as (client, device):
        response = client.post(
            "/system/permissions/list",
            json={"serial": "emulator-5554", "package": "com.example.app;id"},
        )

    assert response.status_code == 400
    data = response.json()
    assert data["error"]["code"] == "ERR_INVALID_PACKAGE"
    assert device.commands == []
