"""Tests for action daemon endpoints."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock, call, patch

import pytest
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
    missing.count = 0
    found = MagicMock()
    found.count = 1
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


def test_tap_rejects_ambiguous_selector() -> None:
    """A single-target action must not click uiautomator2's arbitrary first match."""
    device = MagicMock()
    element = MagicMock()
    element.count = 2
    device.return_value = element

    with _client_with_core(device) as (client, _ref_resolver):
        resp = client.post(
            "/actions/tap",
            json={
                "session_id": "s-abc123",
                "ref": 'text:"Delete"',
            },
        )

    assert resp.status_code == 409
    data = resp.json()
    assert data["error"]["code"] == "ERR_AMBIGUOUS_SELECTOR"
    assert data["error"]["context"]["match_count"] == 2
    element.click.assert_not_called()


def test_tap_fallback_does_not_skip_ambiguous_match() -> None:
    """Fallbacks should advance only on zero matches, not hide an ambiguous alternative."""
    device = MagicMock()
    ambiguous = MagicMock()
    ambiguous.count = 2
    unique = MagicMock()
    unique.count = 1
    device.side_effect = [ambiguous, unique]

    with _client_with_core(device) as (client, _ref_resolver):
        resp = client.post(
            "/actions/tap",
            json={
                "session_id": "s-abc123",
                "ref": 'text:"Delete" || id:com.example:id/delete',
            },
        )

    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "ERR_AMBIGUOUS_SELECTOR"
    assert device.call_count == 1
    ambiguous.click.assert_not_called()
    unique.click.assert_not_called()


def test_tap_fallback_executes_preferred_ref_branch() -> None:
    """A valid ref in a fallback chain must not be silently skipped."""
    device = MagicMock()
    ref_element = MagicMock()
    ref_element.count = 1
    fallback_element = MagicMock()
    fallback_element.count = 1

    def _select(**kwargs: str) -> MagicMock:
        if kwargs == {"resourceId": "com.example:id/preferred"}:
            return ref_element
        return fallback_element

    device.side_effect = _select

    with _client_with_core(device) as (client, ref_resolver):
        ref_resolver.store_refs(
            "s-abc123",
            generation=2,
            elements=[
                {
                    "ref": "^g2a1",
                    "resource_id": "com.example:id/preferred",
                    "class": "android.widget.Button",
                    "bounds": [100, 100, 300, 200],
                }
            ],
        )
        resp = client.post(
            "/actions/tap",
            json={
                "session_id": "s-abc123",
                "ref": "^g2a1 || id:com.example:id/fallback",
            },
        )

    assert resp.status_code == 200
    assert resp.json()["matched_selector"] == "^g2a1"
    ref_element.click.assert_called_once_with()
    fallback_element.click.assert_not_called()


def test_clear_fallback_executes_preferred_ref_branch() -> None:
    """Ref branches should work for non-tap element actions too."""
    device = MagicMock()
    ref_element = MagicMock()
    ref_element.count = 1
    fallback_element = MagicMock()
    fallback_element.count = 1

    def _select(**kwargs: str) -> MagicMock:
        if kwargs == {"resourceId": "com.example:id/preferred"}:
            return ref_element
        return fallback_element

    device.side_effect = _select

    with _client_with_core(device) as (client, ref_resolver):
        ref_resolver.store_refs(
            "s-abc123",
            generation=2,
            elements=[
                {
                    "ref": "^g2a1",
                    "resource_id": "com.example:id/preferred",
                    "class": "android.widget.EditText",
                    "bounds": [100, 100, 500, 200],
                }
            ],
        )
        resp = client.post(
            "/actions/clear",
            json={
                "session_id": "s-abc123",
                "ref": "^g2a1 || id:com.example:id/fallback",
            },
        )

    assert resp.status_code == 200
    assert resp.json()["matched_selector"] == "^g2a1"
    ref_element.clear_text.assert_called_once_with()
    fallback_element.clear_text.assert_not_called()


def test_set_text_accepts_unique_selector() -> None:
    """Set-text should honor the selector targets documented for task scripts."""
    device = MagicMock()
    element = MagicMock()
    element.count = 1
    device.return_value = element

    with _client_with_core(device) as (client, _ref_resolver):
        resp = client.post(
            "/actions/set_text",
            json={
                "session_id": "s-abc123",
                "ref": "id:com.example:id/email",
                "text": "agent@example.com",
            },
        )

    assert resp.status_code == 200
    assert resp.json()["status"] == "done"
    device.assert_called_once_with(resourceId="com.example:id/email")
    element.set_text.assert_called_once_with("agent@example.com")


def test_clear_tries_fallback_selectors_in_order() -> None:
    """Clear should advance through selector fallbacks only when a target is absent."""
    device = MagicMock()
    missing = MagicMock()
    missing.count = 0
    found = MagicMock()
    found.count = 1
    device.side_effect = [missing, found]

    with _client_with_core(device) as (client, _ref_resolver):
        resp = client.post(
            "/actions/clear",
            json={
                "session_id": "s-abc123",
                "ref": 'text:"Missing" || id:com.example:id/search',
            },
        )

    assert resp.status_code == 200
    assert resp.json()["matched_selector"] == "resourceId:com.example:id/search"
    found.clear_text.assert_called_once_with()


def test_long_tap_accepts_coordinate_selector() -> None:
    """Long-tap should execute non-ref coordinate targets consistently with tap."""
    device = MagicMock()

    with _client_with_core(device) as (client, _ref_resolver):
        resp = client.post(
            "/actions/long_tap",
            json={"session_id": "s-abc123", "ref": "coords:120,340"},
        )

    assert resp.status_code == 200
    assert resp.json()["status"] == "done"
    device.long_click.assert_called_once_with(120, 340)


def test_coordinate_tap_returns_structured_action_failure() -> None:
    """Coordinate transport failures should not escape as unhandled server exceptions."""
    device = MagicMock()
    device.click.side_effect = RuntimeError("device connection lost")

    with _client_with_core(device) as (client, _ref_resolver):
        resp = client.post(
            "/actions/tap",
            json={"session_id": "s-abc123", "ref": "coords:120,340"},
        )

    assert resp.status_code == 500
    error = resp.json()["error"]
    assert error["code"] == "ERR_ACTION_FAILED"
    assert error["context"] == {"action": "tap", "target": "coords:120,340"}


def test_selector_set_text_returns_structured_action_failure() -> None:
    """Selector mutation failures should preserve the action error contract."""
    device = MagicMock()
    element = MagicMock()
    element.count = 1
    element.set_text.side_effect = RuntimeError("uiautomator service stopped")
    device.return_value = element

    with _client_with_core(device) as (client, _ref_resolver):
        resp = client.post(
            "/actions/set_text",
            json={
                "session_id": "s-abc123",
                "ref": "id:com.example:id/email",
                "text": "agent@example.com",
            },
        )

    assert resp.status_code == 500
    error = resp.json()["error"]
    assert error["code"] == "ERR_ACTION_FAILED"
    assert error["context"] == {
        "action": "set_text",
        "target": "id:com.example:id/email",
    }


def test_swipe_rejects_ambiguous_container_selector() -> None:
    """Container bounds cannot come from an arbitrary first match."""
    device = MagicMock()
    element = MagicMock()
    element.count = 2
    device.return_value = element

    with _client_with_core(device) as (client, _ref_resolver):
        resp = client.post(
            "/actions/swipe",
            json={
                "session_id": "s-abc123",
                "direction": "up",
                "container": "class:android.widget.ScrollView",
            },
        )

    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "ERR_AMBIGUOUS_SELECTOR"
    device.swipe.assert_not_called()


def test_swipe_tries_fallback_container_selectors_in_order() -> None:
    """Swipe containers should use the first fallback selector with one match."""
    device = MagicMock()
    missing = MagicMock()
    missing.count = 0
    found = MagicMock()
    found.count = 1
    found.info = {"bounds": {"left": 100, "top": 200, "right": 500, "bottom": 1000}}
    device.side_effect = [missing, found]

    with _client_with_core(device) as (client, _ref_resolver):
        resp = client.post(
            "/actions/swipe",
            json={
                "session_id": "s-abc123",
                "direction": "up",
                "container": 'text:"Missing" || id:com.example:id/list',
            },
        )

    assert resp.status_code == 200
    assert resp.json()["bounds"] == [100, 200, 500, 1000]
    assert device.call_args_list[0].kwargs == {"text": "Missing"}
    assert device.call_args_list[1].kwargs == {"resourceId": "com.example:id/list"}
    device.swipe.assert_called_once()


def test_swipe_fallback_does_not_skip_ambiguous_container() -> None:
    """Swipe fallbacks must not hide an ambiguous earlier container selector."""
    device = MagicMock()
    ambiguous = MagicMock()
    ambiguous.count = 2
    unique = MagicMock()
    unique.count = 1
    device.side_effect = [ambiguous, unique]

    with _client_with_core(device) as (client, _ref_resolver):
        resp = client.post(
            "/actions/swipe",
            json={
                "session_id": "s-abc123",
                "direction": "up",
                "container": 'text:"List" || id:com.example:id/list',
            },
        )

    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "ERR_AMBIGUOUS_SELECTOR"
    assert device.call_count == 1
    device.swipe.assert_not_called()


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


def test_tap_and_long_tap_agree_on_coordinate_response_shape() -> None:
    """Tap must echo the caller's selector like every other action does."""
    device = MagicMock()

    with _client_with_core(device) as (client, _ref_resolver):
        tap = client.post(
            "/actions/tap",
            json={"session_id": "s-abc123", "ref": "coords:120,340"},
        )
        long_tap = client.post(
            "/actions/long_tap",
            json={"session_id": "s-abc123", "ref": "coords:120,340"},
        )

    assert tap.status_code == 200
    assert long_tap.status_code == 200
    assert tap.json()["selector"] == long_tap.json()["selector"] == "coords:120,340"
    device.click.assert_called_once_with(120, 340)
    device.long_click.assert_called_once_with(120, 340)


@pytest.mark.parametrize("target", ["coords:300,150", "^g2a1", 'text:"Missing" || coords:300,150'])
@pytest.mark.parametrize("text", ["replacement", "Привет 👋", ""])
def test_coordinate_set_text_replaces_existing_content(target: str, text: str) -> None:
    """Direct coordinates and ref fallbacks must replace, including repeated and empty sets."""
    device = MagicMock()
    device.return_value.count = 0
    content = "existing content"

    def send_keys(value: str, clear: bool = False) -> None:
        nonlocal content
        content = value if clear else content + value

    def clear_text() -> None:
        nonlocal content
        content = ""

    device.send_keys.side_effect = send_keys
    device.clear_text.side_effect = clear_text
    with _client_with_core(device) as (client, resolver):
        resolver.store_refs(
            "s-abc123",
            generation=2,
            elements=[
                {
                    "ref": "^g2a1",
                    "resource_id": "missing:id/input",
                    "class": "android.widget.EditText",
                    "bounds": [100, 100, 500, 200],
                }
            ],
        )
        for _ in range(2):
            response = client.post(
                "/actions/set_text",
                json={
                    "session_id": "s-abc123",
                    "ref": target,
                    "text": text,
                },
            )
            assert response.status_code == 200
            assert response.json()["status"] == "done"
            assert content == text
    assert device.click.call_count == 2
    device.click.assert_called_with(300, 150)
    if text:
        device.send_keys.assert_called_with(text, clear=True)
    else:
        assert device.clear_text.call_count == 2
        device.send_keys.assert_not_called()
    device.send_action.assert_not_called()
    mutation = call.send_keys(text, clear=True) if text else call.clear_text()
    mutations = [
        item for item in device.mock_calls if item[0] in {"click", "send_keys", "clear_text"}
    ]
    assert mutations == [call.click(300, 150), mutation] * 2


@pytest.mark.parametrize("target", ["coords:300,150", "^g2a1", 'text:"Missing" || coords:300,150'])
def test_coordinate_clear_uses_supported_clear_api(target: str) -> None:
    """Clearing must empty the field without an unsupported IME editor action."""
    device = MagicMock()
    device.return_value.count = 0
    content = "existing content"

    def clear_text() -> None:
        nonlocal content
        content = ""

    device.clear_text.side_effect = clear_text
    device.send_action.side_effect = ValueError("unsupported editor action")
    with _client_with_core(device) as (client, resolver):
        resolver.store_refs(
            "s-abc123",
            generation=2,
            elements=[
                {
                    "ref": "^g2a1",
                    "resource_id": "missing:id/input",
                    "class": "android.widget.EditText",
                    "bounds": [100, 100, 500, 200],
                }
            ],
        )
        response = client.post("/actions/clear", json={"session_id": "s-abc123", "ref": target})
    assert response.status_code == 200
    assert response.json()["status"] == "done"
    assert content == ""
    device.click.assert_called_once_with(300, 150)
    device.clear_text.assert_called_once_with()
    device.send_action.assert_not_called()
    device.send_keys.assert_not_called()


@pytest.mark.parametrize("target", ["coords:300,150", "^g2a1"])
@pytest.mark.parametrize("action", ["set_text", "clear"])
@pytest.mark.parametrize("failed_step", ["click", "mutation"])
def test_coordinate_text_failures_are_not_reported_as_success(
    target: str, action: str, failed_step: str
) -> None:
    """Never mutate after a failed focus, and surface driver failures through both paths."""
    device = MagicMock()
    device.return_value.count = 0
    mutation = device.send_keys if action == "set_text" else device.clear_text
    failing_call = device.click if failed_step == "click" else mutation
    failing_call.side_effect = RuntimeError("device input failed")
    with _client_with_core(device) as (client, resolver):
        resolver.store_refs(
            "s-abc123",
            generation=2,
            elements=[
                {
                    "ref": "^g2a1",
                    "resource_id": "missing:id/input",
                    "class": "android.widget.EditText",
                    "bounds": [100, 100, 500, 200],
                }
            ],
        )
        payload = {"session_id": "s-abc123", "ref": target}
        if action == "set_text":
            payload["text"] = "replacement"
        response = client.post(f"/actions/{action}", json=payload)
    assert response.json()["error"]["code"] == "ERR_ACTION_FAILED"
    assert response.json()["status"] != "done"
    device.click.assert_called_once_with(300, 150)
    if failed_step == "click":
        device.send_keys.assert_not_called()
        device.clear_text.assert_not_called()
    else:
        assert mutation.call_count == 1
