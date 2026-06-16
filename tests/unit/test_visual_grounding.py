"""Tests for visual grounding artifacts."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from android_emu_agent.errors import AgentError
from android_emu_agent.visual import VisualGroundingManager


def _snapshot() -> dict[str, Any]:
    return {
        "session_id": "s-abc123",
        "generation": 7,
        "elements": [
            {
                "ref": "^a1",
                "label": "Checkout",
                "text": "Checkout",
                "content_desc": None,
                "resource_id": "com.example:id/checkout",
                "class": "android.widget.Button",
                "role": "button",
                "bounds": [10, 20, 110, 70],
                "state": {"enabled": True},
            },
            {
                "ref": "^a2",
                "label": "Cancel",
                "bounds": [120, 20, 220, 70],
            },
        ],
    }


def test_visual_grounding_manager_writes_ref_metadata(tmp_path: Path) -> None:
    """Grounding artifact should link refs to screenshot-space bounds."""
    manager = VisualGroundingManager(tmp_path / "visual")

    result = manager.create_grounding(
        session_id="s-abc123",
        snapshot=_snapshot(),
        screenshot_path=tmp_path / "screen.png",
        refs=["^a1"],
    )

    assert result["status"] == "done"
    assert result["vision_required"] is False
    assert result["elements"][0]["ref"] == "^a1"
    assert result["elements"][0]["center"] == {"x": 60, "y": 45}
    assert Path(result["path"]).exists()


def test_visual_grounding_manager_rejects_missing_refs(tmp_path: Path) -> None:
    """Unknown refs should produce a grounding-specific AgentError."""
    manager = VisualGroundingManager(tmp_path / "visual")

    with pytest.raises(AgentError) as exc_info:
        manager.create_grounding(
            session_id="s-abc123",
            snapshot=_snapshot(),
            screenshot_path=None,
            refs=["^missing"],
        )

    assert exc_info.value.code == "ERR_VISUAL_REF_NOT_FOUND"


@dataclass
class DummySession:
    """Minimal session payload for visual grounding endpoint tests."""

    session_id: str = "s-abc123"
    device_serial: str = "emulator-5554"
    generation: int = 7


class DummySessionManager:
    snapshot: dict[str, Any] | None

    async def get_session(self, session_id: str) -> DummySession | None:
        if session_id != "s-abc123":
            return None
        return DummySession()

    async def get_last_snapshot(self, session_id: str) -> dict[str, Any] | None:
        if session_id != "s-abc123":
            return None
        return self.__class__.snapshot


class DummyDeviceManager:
    async def get_u2_device(self, serial: str) -> MagicMock | None:
        if serial != "emulator-5554":
            return None
        return MagicMock()


class DummyArtifactManager:
    screenshot_path: Path

    async def screenshot(self, _device: MagicMock, _session_id: str) -> Path:
        return self.__class__.screenshot_path


class DummyCore:
    snapshot: dict[str, Any] | None
    tmp_path: Path

    def __init__(self) -> None:
        DummySessionManager.snapshot = self.__class__.snapshot
        DummyArtifactManager.screenshot_path = self.__class__.tmp_path / "screen.png"
        self.session_manager = DummySessionManager()
        self.device_manager = DummyDeviceManager()
        self.artifact_manager = DummyArtifactManager()
        self.visual_grounding_manager = VisualGroundingManager(self.__class__.tmp_path / "visual")
        self._running = False

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running


@contextmanager
def _client_with_core(tmp_path: Path, snapshot: dict[str, Any] | None) -> Any:
    from android_emu_agent.daemon import server

    DummyCore.tmp_path = tmp_path
    DummyCore.snapshot = snapshot
    with patch.object(server, "DaemonCore", DummyCore), TestClient(server.app) as client:
        yield client


def test_ui_ground_endpoint_creates_grounding_artifact(tmp_path: Path) -> None:
    """Endpoint should create grounding metadata from latest snapshot."""
    with _client_with_core(tmp_path, _snapshot()) as client:
        response = client.post(
            "/ui/ground",
            json={"session_id": "s-abc123", "refs": ["^a1"], "screenshot": True},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["screenshot_path"].endswith("screen.png")
    assert data["elements"][0]["ref"] == "^a1"
    assert Path(data["path"]).exists()


def test_ui_ground_requires_latest_snapshot(tmp_path: Path) -> None:
    """Grounding should ask for a UI snapshot first."""
    with _client_with_core(tmp_path, None) as client:
        response = client.post("/ui/ground", json={"session_id": "s-abc123"})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ERR_SNAPSHOT_REQUIRED"


def test_ui_ground_cli_builds_payload() -> None:
    """CLI command should send refs and screenshot flag."""
    from android_emu_agent.cli.commands import ui

    calls: list[tuple[str, str, dict[str, Any] | None]] = []

    class DummyResponse:
        def json(self) -> dict[str, Any]:
            return {"status": "done", "path": "/tmp/grounding.json"}

    class DummyClient:
        def __init__(self, *_: Any, **__: Any) -> None:
            pass

        def request(self, method: str, path: str, json_body: dict[str, Any] | None = None):
            calls.append((method, path, json_body))
            return DummyResponse()

        def close(self) -> None:
            return None

    with patch.object(ui, "DaemonClient", DummyClient):
        ui.ui_ground(
            "s-abc123",
            refs=["^a1", "^a2"],
            screenshot=False,
            pull=False,
            output=None,
            json_output=False,
        )

    assert calls[0] == (
        "POST",
        "/ui/ground",
        {"session_id": "s-abc123", "refs": ["^a1", "^a2"], "screenshot": False},
    )
