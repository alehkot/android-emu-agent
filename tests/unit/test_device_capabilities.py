"""Tests for device capability introspection."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from android_emu_agent.device.manager import DeviceInfo, DeviceManager


class DummySession:
    """Minimal session payload for capability endpoint tests."""

    device_serial = "emulator-5554"


class DummySessionManager:
    async def get_session(self, session_id: str) -> DummySession | None:
        if session_id != "s-abc123":
            return None
        return DummySession()


class DummyDeviceManager(DeviceManager):
    def __init__(self) -> None:
        super().__init__()
        self.info = DeviceInfo(
            serial="emulator-5554",
            model="Pixel",
            sdk_version=35,
            is_rooted=True,
            is_emulator=True,
        )

    async def get_adb_device(self, serial: str) -> MagicMock | None:
        if serial != "emulator-5554":
            return None
        return MagicMock()

    async def get_device(self, serial: str) -> DeviceInfo | None:
        if serial != "emulator-5554":
            return None
        return self.info


class DummyCore:
    def __init__(self) -> None:
        self.session_manager = DummySessionManager()
        self.device_manager = DummyDeviceManager()
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

    with patch.object(server, "DaemonCore", DummyCore), TestClient(server.app) as client:
        yield client


def test_device_manager_capability_report_lists_selector_features() -> None:
    """Capability report should expose selector and subsystem support."""
    manager = DeviceManager()
    info = DeviceInfo(
        serial="emulator-5554",
        model="Pixel",
        sdk_version=35,
        is_rooted=True,
        is_emulator=True,
    )

    report = manager.capability_report(serial="emulator-5554", info=info, session_id="s-abc123")

    assert report["status"] == "done"
    assert "text-contains:<value>" in report["selectors"]["target_syntax"]
    assert "resourceIdMatches" in report["selectors"]["selector_keys"]
    assert report["automation"]["task_harness"] is True
    assert report["automation"]["visual_grounding"] is True
    assert report["automation"]["system_surfaces"] is True
    assert report["automation"]["debugger_fusion"] is True
    assert report["device_features"]["emulator_controls_available"] is True
    assert report["device_features"]["runtime_permissions"] is True


def test_device_capabilities_endpoint_accepts_session_target() -> None:
    """Capability endpoint should resolve session targets."""
    with _client_with_core() as client:
        response = client.post("/devices/capabilities", json={"session_id": "s-abc123"})

    assert response.status_code == 200
    data = response.json()
    assert data["target"]["serial"] == "emulator-5554"
    assert data["target"]["session_id"] == "s-abc123"
    assert data["target"]["is_rooted"] is True


def test_device_capabilities_cli_builds_payload() -> None:
    """CLI command should send target payload to daemon."""
    from android_emu_agent.cli.commands import device

    calls: list[tuple[str, str, dict[str, Any] | None]] = []

    class DummyResponse:
        def json(self) -> dict[str, Any]:
            return {"status": "done"}

    class DummyClient:
        def __init__(self, *_: Any, **__: Any) -> None:
            pass

        def request(self, method: str, path: str, json_body: dict[str, Any] | None = None):
            calls.append((method, path, json_body))
            return DummyResponse()

        def close(self) -> None:
            return None

    with patch.object(device, "DaemonClient", DummyClient):
        device.device_capabilities(device=None, session_id="s-abc123", json_output=False)

    assert calls[0] == ("POST", "/devices/capabilities", {"session_id": "s-abc123"})
