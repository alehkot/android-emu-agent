"""Tests for task harness manager."""

from __future__ import annotations

from typing import Any

import pytest

from android_emu_agent.errors import AgentError
from android_emu_agent.tasks import TaskCall, TaskManager


def test_task_script_parses_to_existing_task_spec_shape() -> None:
    """Script format should compile into the JSON task harness shape."""
    manager = TaskManager()

    spec = manager.parse_script(
        """
        name "login script"
        session s-abc123
        launch com.example.app
        wait exists text:"Sign in" timeout_ms=5000
        tap text:"Sign in" || id:com.example:id/login
        verify exists text:"Email"
        set-text id:com.example:id/email "alice@example.com"
        expect activity MainActivity
        """,
        source_name="login.aea",
    )

    assert spec["name"] == "login script"
    assert spec["session_id"] == "s-abc123"
    assert spec["steps"][0] == {"app": "launch", "package": "com.example.app"}
    assert spec["steps"][1] == {
        "wait": "exists",
        "ref": "text:Sign in",
        "timeout_ms": 5000,
    }
    assert spec["steps"][2]["action"] == "tap"
    assert spec["steps"][2]["ref"] == "text:Sign in || id:com.example:id/login"
    assert spec["steps"][2]["verify"] == [{"type": "exists", "ref": "text:Email"}]
    assert spec["verifiers"] == [{"type": "activity", "activity": "MainActivity"}]

    plan = manager.validate(spec)
    assert plan["status"] == "done"
    assert plan["step_count"] == 4


def test_task_script_rejects_unknown_commands() -> None:
    """Invalid script commands should fail with task script-specific errors."""
    manager = TaskManager()

    with pytest.raises(AgentError) as exc_info:
        manager.parse_script("pinch text:Map", source_name="bad.aea")

    assert exc_info.value.code == "ERR_TASK_SCRIPT_INVALID"
    assert "bad.aea:1" in exc_info.value.message


def test_task_validate_normalizes_steps_and_verifiers() -> None:
    """Validation should return a compact execution plan."""
    manager = TaskManager()
    spec = {
        "name": "login smoke",
        "steps": [
            {
                "name": "tap login",
                "action": "tap",
                "ref": 'text:"Log in"',
                "verify": [{"type": "exists", "text": "Email"}],
            }
        ],
        "verifiers": [{"type": "activity", "activity": "MainActivity"}],
    }

    plan = manager.validate(spec)

    assert plan["status"] == "done"
    assert plan["task"]["name"] == "login smoke"
    assert plan["step_count"] == 1
    assert plan["verifier_count"] == 2
    assert plan["steps"][0] == {
        "index": 1,
        "name": "tap login",
        "kind": "action",
        "operation": "tap",
        "verifier_count": 1,
    }


@pytest.mark.asyncio
async def test_task_run_executes_steps_and_verifiers() -> None:
    """Run should dispatch steps, step verifiers, and task verifiers in order."""
    manager = TaskManager()
    calls: list[TaskCall] = []

    async def dispatcher(call: TaskCall) -> dict[str, Any]:
        calls.append(call)
        return {"status": "done", "operation": call.operation}

    result = await manager.run(
        {
            "steps": [
                {
                    "action": "set_text",
                    "ref": "^a1",
                    "text": "alice@example.com",
                    "verify": [{"type": "exists", "text_contains": "alice"}],
                }
            ],
            "verifiers": [{"type": "idle", "timeout_ms": 1000}],
        },
        session_id="s-abc123",
        dispatcher=dispatcher,
    )

    assert result["status"] == "done"
    assert result["passed"] is True
    assert [(call.kind, call.operation) for call in calls] == [
        ("action", "set_text"),
        ("wait", "exists"),
        ("wait", "idle"),
    ]
    assert calls[0].payload == {
        "session_id": "s-abc123",
        "ref": "^a1",
        "text": "alice@example.com",
    }
    assert calls[1].payload["selector"] == {"textContains": "alice"}


@pytest.mark.asyncio
async def test_task_run_stops_on_failed_verifier() -> None:
    """The first failed verifier should fail the task and stop by default."""
    manager = TaskManager()
    calls: list[TaskCall] = []

    async def dispatcher(call: TaskCall) -> dict[str, Any]:
        calls.append(call)
        if call.operation == "exists":
            return {"status": "timeout", "error": {"code": "ERR_TIMEOUT"}}
        return {"status": "done"}

    result = await manager.run(
        {
            "steps": [
                {
                    "action": "tap",
                    "ref": "^a1",
                    "verify": [{"type": "exists", "text": "Checkout"}],
                },
                {"action": "tap", "ref": "^a2"},
            ]
        },
        session_id="s-abc123",
        dispatcher=dispatcher,
    )

    assert result["status"] == "failed"
    assert result["passed"] is False
    assert result["failure"]["kind"] == "step"
    assert result["failure"]["verifier"]["operation"] == "exists"
    assert result["failure"]["verifier"]["response"]["error"]["code"] == "ERR_TIMEOUT"
    assert len(calls) == 2


def test_task_validate_rejects_unsupported_operations() -> None:
    """Unsupported operations should fail with a task-specific AgentError."""
    manager = TaskManager()

    with pytest.raises(AgentError) as exc_info:
        manager.validate({"steps": [{"action": "pinch", "ref": "^a1"}]})

    assert exc_info.value.code == "ERR_TASK_UNSUPPORTED_STEP"
