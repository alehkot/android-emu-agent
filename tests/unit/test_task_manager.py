"""Tests for task harness manager."""

from __future__ import annotations

from typing import Any

import pytest

from android_emu_agent.errors import AgentError
from android_emu_agent.tasks import TaskCall, TaskManager


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
                    "verify": [{"type": "text", "text": "alice@example.com"}],
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
        ("wait", "text"),
        ("wait", "idle"),
    ]
    assert calls[0].payload == {
        "session_id": "s-abc123",
        "ref": "^a1",
        "text": "alice@example.com",
    }


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
