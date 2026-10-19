"""Task request validation must finish before any device action is dispatched."""

from __future__ import annotations

from typing import Any

import pytest

from android_emu_agent.errors import AgentError
from android_emu_agent.tasks import TaskCall, TaskManager

INVALID_STEPS = [
    pytest.param({"wait": "idle", "timeout_ms": "later"}, "timeout_ms", id="idle-timeout"),
    pytest.param(
        {"wait": "activity", "activity": "Main", "timeout_ms": []},
        "timeout_ms",
        id="activity-timeout",
    ),
    pytest.param(
        {"wait": "text", "text": "Ready", "timeout_ms": {}},
        "timeout_ms",
        id="text-timeout",
    ),
    pytest.param(
        {"wait": "exists", "selector": {"text": 123}},
        "selector.text",
        id="selector-value",
    ),
    pytest.param(
        {"wait": "gone", "ref": "text:Ready", "timeout_ms": 0.5},
        "timeout_ms",
        id="gone-timeout",
    ),
    pytest.param(
        {"action": "swipe", "direction": "up", "distance": "far"},
        "distance",
        id="swipe-distance",
    ),
    pytest.param(
        {"action": "swipe", "direction": "up", "duration": "slow"},
        "duration_ms",
        id="swipe-duration-alias",
    ),
    pytest.param(
        {"action": "swipe", "direction": "up", "container": []},
        "container",
        id="swipe-container",
    ),
    pytest.param(
        {"app": "launch", "package": "com.example.app", "activity": []},
        "activity",
        id="launch-activity",
    ),
    pytest.param(
        {"app": "launch", "package": "com.example.app", "wait_debugger": "maybe"},
        "wait_debugger",
        id="launch-debugger",
    ),
    pytest.param(
        {"app": "deeplink", "uri": "https://example.com", "wait_debugger": {}},
        "wait_debugger",
        id="deeplink-debugger",
    ),
    pytest.param({"ui": "snapshot", "mode": "xml"}, "mode", id="snapshot-mode"),
    pytest.param({"ui": "snapshot", "full": "maybe"}, "full", id="snapshot-full"),
]


@pytest.mark.parametrize(("invalid_step", "field"), INVALID_STEPS)
def test_validate_rejects_invalid_request_fields(invalid_step: dict[str, Any], field: str) -> None:
    manager = TaskManager()
    with pytest.raises(AgentError) as error:
        manager.validate({"steps": [{"action": "home"}, invalid_step]})
    assert error.value.code == "ERR_TASK_INVALID"
    assert f"steps[2].{field}" in error.value.message
    assert error.value.remediation


@pytest.mark.parametrize(("invalid_step", "field"), INVALID_STEPS)
@pytest.mark.parametrize("stop_on_failure", [True, False])
async def test_run_preflights_all_requests_before_dispatch(
    invalid_step: dict[str, Any],
    field: str,
    stop_on_failure: bool,
) -> None:
    calls: list[TaskCall] = []

    async def dispatcher(call: TaskCall) -> dict[str, Any]:
        calls.append(call)
        return {"status": "done"}

    with pytest.raises(AgentError) as error:
        await TaskManager().run(
            {"steps": [{"action": "home"}, invalid_step]},
            session_id="s-test",
            dispatcher=dispatcher,
            stop_on_failure=stop_on_failure,
        )
    assert error.value.code == "ERR_TASK_INVALID"
    assert f"steps[2].{field}" in error.value.message
    assert calls == []


@pytest.mark.parametrize("scope", ["step", "task"])
async def test_invalid_verifiers_prevent_all_dispatch(scope: str) -> None:
    invalid_verifier = {"type": "exists", "selector": {"text": ["Ready"]}}
    spec: dict[str, Any] = {"steps": [{"action": "home"}, {"action": "back"}]}
    if scope == "step":
        spec["steps"][1]["verify"] = [{"type": "idle"}, invalid_verifier]
        location = "steps[2].verify[2].selector.text"
    else:
        spec["verifiers"] = [{"type": "idle"}, invalid_verifier]
        location = "verifiers[2].selector.text"
    calls: list[TaskCall] = []

    async def dispatcher(call: TaskCall) -> dict[str, Any]:
        calls.append(call)
        return {"status": "done"}

    manager = TaskManager()
    with pytest.raises(AgentError, match=location.replace("[", r"\[").replace("]", r"\]")):
        manager.validate(spec)
    with pytest.raises(AgentError) as error:
        await manager.run(spec, session_id="s-test", dispatcher=dispatcher)
    assert location in error.value.message
    assert calls == []


@pytest.mark.parametrize(
    "step",
    [
        {"wait": "idle", "timeout_ms": "1000"},
        {"action": "swipe", "direction": "up", "distance": "0.5", "duration": "100"},
        {"app": "launch", "package": "com.example.app", "wait_debugger": "true"},
        {"app": "deeplink", "uri": "https://example.com", "wait_debugger": "false"},
        {"ui": "snapshot", "full": True},
        {"ui": "snapshot", "mode": "raw"},
        {"wait": "idle", "timeout_ms": None},
        {"wait": "exists", "selector": {"text": "Ready"}},
    ],
)
async def test_preflight_preserves_existing_request_coercions(step: dict[str, Any]) -> None:
    manager = TaskManager()
    calls: list[TaskCall] = []

    async def dispatcher(call: TaskCall) -> dict[str, Any]:
        calls.append(call)
        return {"status": "done"}

    assert manager.validate({"steps": [step]})["status"] == "done"
    result = await manager.run({"steps": [step]}, session_id="s-test", dispatcher=dispatcher)
    assert result["passed"] is True
    assert len(calls) == 1


@pytest.mark.parametrize(
    ("step", "handler_name", "model_name"),
    [
        ({"action": "tap", "ref": "text:OK"}, "action_tap", "ActionRequest"),
        ({"action": "long_tap", "ref": "^a1"}, "action_long_tap", "ActionRequest"),
        (
            {"action": "set_text", "ref": "^a1", "text": "hello"},
            "action_set_text",
            "SetTextRequest",
        ),
        ({"action": "clear", "ref": "^a1"}, "action_clear", "ActionRequest"),
        ({"action": "back"}, "action_back", "SessionRequest"),
        ({"action": "home"}, "action_home", "SessionRequest"),
        ({"action": "recents"}, "action_recents", "SessionRequest"),
        ({"action": "swipe", "direction": "up", "duration": "100"}, "action_swipe", "SwipeRequest"),
        ({"wait": "idle"}, "wait_idle", "WaitIdleRequest"),
        ({"wait": "activity", "activity": "Main"}, "wait_activity", "WaitActivityRequest"),
        ({"wait": "text", "text": "Ready"}, "wait_text", "WaitTextRequest"),
        ({"wait": "exists", "text_contains": "Ready"}, "wait_exists", "WaitSelectorRequest"),
        ({"wait": "gone", "id": "com.example:id/busy"}, "wait_gone", "WaitSelectorRequest"),
        ({"app": "launch", "package": "com.example.app"}, "app_launch", "AppLaunchRequest"),
        (
            {"app": "force_stop", "package": "com.example.app"},
            "app_force_stop",
            "AppForceStopRequest",
        ),
        ({"app": "deeplink", "uri": "https://example.com"}, "app_deeplink", "AppDeeplinkRequest"),
        ({"ui": "snapshot", "full": True}, "ui_snapshot", "SnapshotRequest"),
    ],
)
async def test_preflight_covers_every_supported_dispatch_route(
    step: dict[str, Any],
    handler_name: str,
    model_name: str,
) -> None:
    from unittest.mock import AsyncMock, patch

    from android_emu_agent.daemon import server

    handler = AsyncMock(return_value={"status": "done"})
    with patch.object(server, handler_name, handler):
        result = await TaskManager().run(
            {"steps": [step]},
            session_id="s-test",
            dispatcher=server._dispatch_task_call,
        )
    assert result["passed"] is True
    handler.assert_awaited_once()
    request = handler.call_args.args[0]
    assert type(request).__name__ == model_name
    assert request.session_id == "s-test"
    if model_name == "SwipeRequest":
        assert request.duration_ms == 100
    if model_name == "SnapshotRequest":
        assert request.mode == "full"


def test_request_validation_error_omits_input_values() -> None:
    value = "private-payload-value"
    with pytest.raises(AgentError) as error:
        TaskManager().validate({"steps": [{"wait": "idle", "timeout_ms": value}]})
    assert value not in error.value.message
    assert value not in str(error.value.context)


@pytest.mark.parametrize(
    "distance", [float("nan"), float("inf"), -float("inf"), "NaN", "Infinity", "-inf", "1e999"]
)
@pytest.mark.parametrize("stop_on_failure", [True, False])
async def test_nonfinite_swipe_distance_prevents_all_dispatch(
    distance: object, stop_on_failure: bool
) -> None:
    calls: list[TaskCall] = []

    async def dispatcher(call: TaskCall) -> dict[str, Any]:
        calls.append(call)
        return {"status": "done"}

    spec = {
        "steps": [{"action": "home"}, {"action": "swipe", "direction": "up", "distance": distance}]
    }
    manager = TaskManager()
    for operation in ("validate", "run"):
        with pytest.raises(AgentError) as caught:
            if operation == "validate":
                manager.validate(spec)
            else:
                await manager.run(
                    spec,
                    session_id="s-test",
                    dispatcher=dispatcher,
                    stop_on_failure=stop_on_failure,
                )
        assert caught.value.code == "ERR_TASK_INVALID"
        assert "steps[2].distance" in caught.value.message
        assert "finite" in caught.value.message
    assert calls == []


@pytest.mark.parametrize("distance", [0.8, 1, "0.5", "1e-2", True, False, 0, -1, 1.5, 1e308])
async def test_finite_swipe_distance_preflight_preserves_coercions_and_runtime_ranges(
    distance: object,
) -> None:
    calls: list[TaskCall] = []

    async def dispatcher(call: TaskCall) -> dict[str, Any]:
        calls.append(call)
        return {"status": "done"}

    spec = {"steps": [{"action": "swipe", "direction": "up", "distance": distance}]}
    manager = TaskManager()
    assert manager.validate(spec)["step_count"] == 1
    result = await manager.run(spec, session_id="s-test", dispatcher=dispatcher)
    assert result["passed"] is True
    assert len(calls) == 1
    assert calls[0].payload["distance"] == distance
    assert type(calls[0].payload["distance"]) is type(distance)


@pytest.mark.parametrize("value", [0, 1, 0.0, 1.0, 123])
def test_selector_boolean_support_does_not_coerce_numbers(value: int | float) -> None:
    with pytest.raises(AgentError) as caught:
        TaskManager().validate({"steps": [{"wait": "exists", "selector": {"enabled": value}}]})
    assert caught.value.code == "ERR_TASK_INVALID"
    assert "selector.enabled" in caught.value.message
