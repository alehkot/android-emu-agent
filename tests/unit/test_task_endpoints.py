"""Tests for task daemon endpoints."""

from __future__ import annotations

import asyncio
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from starlette.responses import Response

from android_emu_agent.actions.executor import ActionExecutor
from android_emu_agent.actions.wait import WaitEngine
from android_emu_agent.device.io import shutdown_device_io
from android_emu_agent.tasks import TaskCall, TaskManager
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


def test_task_verifier_times_out_before_stalled_observation_finishes() -> None:
    """A blocked verifier must fail the task without dispatching later verifiers."""
    release = threading.Event()
    finished = threading.Event()
    device = MagicMock()
    device.serial = "task-deadline-device"

    def blocked_exists() -> bool:
        release.wait(timeout=5)
        finished.set()
        return True

    device.return_value.exists.side_effect = blocked_exists

    try:
        with _client_with_core(device) as client:
            response = client.post(
                "/tasks/run",
                json={
                    "session_id": "s-abc123",
                    "task": {
                        "verifiers": [
                            {"type": "exists", "text": "Ready", "timeout_ms": 50},
                            {"type": "text", "text": "Next"},
                        ]
                    },
                },
            )

        assert not finished.is_set()
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "failed"
        assert data["passed"] is False
        assert len(data["verifiers"]) == 1
        assert data["verifiers"][0]["response"]["error"]["code"] == "ERR_TIMEOUT"
        device.assert_called_once_with(text="Ready")
    finally:
        release.set()
        try:
            assert finished.wait(timeout=2)
        finally:
            shutdown_device_io(device.serial)


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


def test_task_script_set_text_selector_executes() -> None:
    """A documented set-text selector should execute instead of being treated as a ref."""
    device = MagicMock()
    element = MagicMock()
    element.count = 1
    device.return_value = element

    with _client_with_core(device) as client:
        response = client.post(
            "/tasks/script/run",
            json={
                "session_id": "s-abc123",
                "script": 'set-text id:com.example:id/email "agent@example.com"\n',
                "source_name": "login.aea",
            },
        )

    assert response.status_code == 200
    assert response.json()["passed"] is True
    device.assert_called_once_with(resourceId="com.example:id/email")
    element.set_text.assert_called_once_with("agent@example.com")


@pytest.mark.parametrize("text", ["x=y", "timeout_ms=5000", "first x=y last"])
def test_task_script_set_text_literal_equals_executes(text: str) -> None:
    device = MagicMock()
    element = MagicMock()
    element.count = 1
    device.return_value = element

    with _client_with_core(device) as client:
        response = client.post(
            "/tasks/script/run",
            json={
                "session_id": "s-abc123",
                "script": f'set-text id:com.example:id/input "{text}"',
            },
        )

    assert response.status_code == 200
    assert response.json()["passed"] is True
    device.assert_called_once_with(resourceId="com.example:id/input")
    element.set_text.assert_called_once_with(text)


def test_task_script_query_link_and_literal_verifiers_dispatch() -> None:
    from android_emu_agent.daemon import server

    script = (
        'deeplink "https://example.com/search?q=android&sort=date"\n'
        'verify text "Total=5" timeout_ms=1000\n'
        'expect text "timeout_ms=5000" timeout_ms=1000\n'
    )
    dispatch = AsyncMock(return_value={"status": "done", "passed": True})
    with (
        _client_with_core(MagicMock()) as client,
        patch.object(server, "_dispatch_task_call", dispatch),
    ):
        validated = client.post("/tasks/script/validate", json={"script": script})
        assert validated.status_code == 200
        dispatch.assert_not_called()
        response = client.post(
            "/tasks/script/run", json={"session_id": "s-abc123", "script": script}
        )

    assert response.status_code == 200
    assert response.json()["passed"] is True
    calls = [call.args[0] for call in dispatch.await_args_list]
    assert len(calls) == 3
    assert calls[0].operation == "deeplink"
    assert calls[0].payload["uri"] == "https://example.com/search?q=android&sort=date"
    assert [call.payload["text"] for call in calls[1:]] == ["Total=5", "timeout_ms=5000"]
    assert [call.payload["timeout_ms"] for call in calls[1:]] == [1000, 1000]


def test_task_dispatcher_wraps_raw_snapshot_response() -> None:
    """Raw snapshot task steps should return JSON task evidence instead of failing to decode XML."""
    from android_emu_agent.daemon import server

    response = Response(content="<hierarchy />", media_type="application/xml")
    call = TaskCall(
        kind="ui",
        operation="snapshot",
        payload={"session_id": "s-abc123", "mode": "raw"},
        label="ui:snapshot",
    )

    with patch.object(server, "ui_snapshot", AsyncMock(return_value=response)):
        result = asyncio.run(server._dispatch_task_call(call))

    assert result == {"status": "done", "mode": "raw", "xml": "<hierarchy />"}


@pytest.mark.parametrize("route", ["validate", "run"])
@pytest.mark.parametrize("scope", ["step", "attached-verifier", "final-verifier"])
@pytest.mark.parametrize("stop_on_failure", [True, False])
def test_invalid_task_request_returns_400_without_device_actions(
    route: str,
    scope: str,
    stop_on_failure: bool,
) -> None:
    device = MagicMock()
    task: dict[str, Any] = {"steps": [{"action": "home"}]}
    invalid_wait = {"type": "idle", "timeout_ms": "later"}
    if scope == "step":
        task["steps"].append({"wait": "idle", "timeout_ms": "later"})
    elif scope == "attached-verifier":
        task["steps"][0]["verify"] = [invalid_wait]
    else:
        task["verifiers"] = [invalid_wait]
    body: dict[str, Any] = {"task": task}
    if route == "run":
        body.update(session_id="s-abc123", stop_on_failure=stop_on_failure)

    with _client_with_core(device) as client:
        response = client.post(f"/tasks/{route}", json=body)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "ERR_TASK_INVALID"
    assert "timeout_ms" in response.json()["error"]["message"]
    assert device.mock_calls == []


@pytest.mark.parametrize("route", ["validate", "run"])
@pytest.mark.parametrize(
    "script",
    ["home\nsnapshot mode=xml\n", "home\nlaunch com.example.app wait_debugger=maybe\n"],
)
def test_invalid_compiled_request_returns_400_without_device_actions(
    route: str, script: str
) -> None:
    device = MagicMock()
    body: dict[str, Any] = {"script": script, "source_name": "invalid.aea"}
    if route == "run":
        body["session_id"] = "s-abc123"
    with _client_with_core(device) as client:
        response = client.post(f"/tasks/script/{route}", json=body)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "ERR_TASK_INVALID"
    assert "steps[2]" in response.json()["error"]["message"]
    assert device.mock_calls == []


@pytest.mark.parametrize("route", ["validate", "run"])
@pytest.mark.parametrize(
    "line",
    [
        "wait idle timeout_ms=later",
        "swipe up duration_ms=slow",
        "swipe up duration=1.5",
        "swipe up distance=far",
        "verify idle timeout_ms=",
        "expect idle timeout_ms=bad",
        "swipe up distance=nan",
        "swipe up distance=Infinity",
        "swipe up distance=1e999",
    ],
)
def test_invalid_script_number_returns_400_without_actions(route: str, line: str) -> None:
    device = MagicMock()
    body: dict[str, Any] = {"script": f"# heading\nhome\n{line}\n", "source_name": "bad.aea"}
    if route == "run":
        body.update(session_id="s-abc123", stop_on_failure=False)
    with _client_with_core(device) as client:
        response = client.post(f"/tasks/script/{route}", json=body)
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "ERR_TASK_SCRIPT_INVALID"
    assert error["context"] == {"source": "bad.aea", "line": 3}
    assert "task validate" in error["remediation"]
    assert device.mock_calls == []


@pytest.mark.parametrize("route", ["validate", "run"])
@pytest.mark.parametrize(
    "distance_json",
    ['"NaN"', '"Infinity"', '"-inf"', '"1e999"', "NaN", "Infinity", "-Infinity", "1e999"],
)
def test_json_task_nonfinite_swipe_distance_is_rejected_before_actions(
    route: str, distance_json: str
) -> None:
    device = MagicMock()
    task_json = (
        '{"steps":[{"action":"home"},{"action":"swipe","direction":"up","distance":'
        + distance_json
        + "}]}"
    )
    body = '{"task":' + task_json
    if route == "run":
        body += ',"session_id":"s-abc123","stop_on_failure":false'
    body += "}"
    with _client_with_core(device) as client:
        response = client.post(
            f"/tasks/{route}", content=body, headers={"Content-Type": "application/json"}
        )
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "ERR_TASK_INVALID"
    assert "steps[2].distance" in error["message"]
    assert "finite" in error["message"]
    assert device.mock_calls == []
