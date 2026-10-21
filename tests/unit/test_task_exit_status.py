"""Task CLI exit status must reflect the complete daemon execution result."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import Mock

import httpx
import pytest
from typer.testing import CliRunner

from android_emu_agent.cli import daemon_client
from android_emu_agent.cli.commands import task
from android_emu_agent.tasks.manager import TaskManager


def _task_file(tmp_path: Path, script: bool, failure_scope: str) -> Path:
    path = tmp_path / ("flow.aea" if script else "flow.json")
    if script:
        lines = ["session s-1", "home"]
        if failure_scope == "step-verifier":
            lines.append('verify text "Ready"')
        lines.append("back")
        if failure_scope == "final-verifier":
            lines.append('expect text "Ready"')
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    else:
        spec = {"session_id": "s-1", "steps": [{"action": "home"}, {"action": "back"}]}
        if failure_scope == "step-verifier":
            spec["steps"][0]["verify"] = [{"type": "text", "text": "Ready"}]
        if failure_scope == "final-verifier":
            spec["verifiers"] = [{"type": "text", "text": "Ready"}]
        path.write_text(json.dumps(spec), encoding="utf-8")
    return path


def _transport(monkeypatch, respond) -> None:
    monkeypatch.setattr(daemon_client, "DaemonController", Mock())
    monkeypatch.setattr(
        daemon_client.httpx, "HTTPTransport", lambda **_: httpx.MockTransport(respond)
    )


@pytest.mark.parametrize("script", [False, True], ids=["json-task", "aea-script"])
@pytest.mark.parametrize("json_output", [False, True], ids=["human", "json-output"])
@pytest.mark.parametrize("continue_on_failure", [False, True], ids=["stop", "continue"])
@pytest.mark.parametrize("failure_scope", ["action", "step-verifier", "final-verifier"])
def test_failed_execution_returns_nonzero_with_complete_result(
    tmp_path, monkeypatch, script, json_output, continue_on_failure, failure_scope
) -> None:
    """Use the real task planner/executor, HTTP client, and Typer command."""
    path = _task_file(tmp_path, script, failure_scope)
    dispatched = []
    responses = []
    requests = []
    manager = TaskManager()

    async def dispatch(call):
        dispatched.append(call.operation)
        fail_operation = "home" if failure_scope == "action" else "text"
        if call.operation == fail_operation:
            return {"error": {"code": "ERR_TIMEOUT", "message": "condition not reached"}}
        return {"status": "done"}

    def respond(request):
        requests.append(request)
        payload = json.loads(request.content)
        assert payload["stop_on_failure"] is not continue_on_failure
        spec = manager.parse_script(payload["script"]) if script else payload["task"]
        result = asyncio.run(
            manager.run(
                spec,
                session_id=payload["session_id"],
                dispatcher=dispatch,
                stop_on_failure=payload["stop_on_failure"],
            )
        )
        if script:
            result = {"source_name": payload["source_name"], "compiled_task": spec, **result}
        responses.append(result)
        return httpx.Response(200, json=result)

    _transport(monkeypatch, respond)
    args = ["run", str(path)]
    if json_output:
        args.append("--json")
    if continue_on_failure:
        args.append("--continue-on-failure")
    result = CliRunner().invoke(task.app, args)

    assert result.exit_code == 1, result.stdout
    assert len(requests) == 1, "a failed task must not be automatically replayed"
    assert requests[0].url.path == ("/tasks/script/run" if script else "/tasks/run")
    assert json.loads(result.stdout) == responses[0], "retain the entire failure report"
    assert responses[0]["status"] == "failed"
    assert responses[0]["passed"] is False
    assert responses[0]["failure"] is not None
    assert ("back" in dispatched) is (continue_on_failure or failure_scope == "final-verifier")


@pytest.mark.parametrize("script", [False, True], ids=["json-task", "aea-script"])
@pytest.mark.parametrize("json_output", [False, True], ids=["human", "json-output"])
@pytest.mark.parametrize("continue_on_failure", [False, True], ids=["stop", "continue"])
def test_successful_execution_keeps_zero_exit_status(
    tmp_path, monkeypatch, script, json_output, continue_on_failure
) -> None:
    path = _task_file(tmp_path, script, "final-verifier")
    responses = []
    manager = TaskManager()

    async def dispatch(_call):
        return {"status": "done"}

    def respond(request):
        payload = json.loads(request.content)
        spec = manager.parse_script(payload["script"]) if script else payload["task"]
        result = asyncio.run(
            manager.run(
                spec,
                session_id=payload["session_id"],
                dispatcher=dispatch,
                stop_on_failure=payload["stop_on_failure"],
            )
        )
        responses.append(result)
        return httpx.Response(200, json=result)

    _transport(monkeypatch, respond)
    args = ["run", str(path)]
    if json_output:
        args.append("--json")
    if continue_on_failure:
        args.append("--continue-on-failure")
    result = CliRunner().invoke(task.app, args)
    assert result.exit_code == 0, result.exception
    assert len(responses) == 1
    assert responses[0]["passed"] is True
    if json_output:
        assert json.loads(result.stdout) == responses[0]
    else:
        assert "Done" in result.stdout


@pytest.mark.parametrize("command", ["run", "validate"])
@pytest.mark.parametrize("script", [False, True], ids=["json-task", "aea-script"])
@pytest.mark.parametrize("json_output", [False, True], ids=["human", "json-output"])
def test_top_level_errors_keep_nonzero_exit_status(
    tmp_path, monkeypatch, command, script, json_output
) -> None:
    path = _task_file(tmp_path, script, "action")
    payload = {"error": {"code": "ERR_TASK_INVALID", "message": "invalid task"}}
    _transport(monkeypatch, lambda _request: httpx.Response(400, json=payload))
    args = [command, str(path), *(["--json"] if json_output else [])]
    result = CliRunner().invoke(task.app, args)
    assert result.exit_code == 1
    if json_output:
        assert json.loads(result.stdout) == payload
    else:
        assert "ERR_TASK_INVALID: invalid task" in result.stdout


@pytest.mark.parametrize("script", [False, True], ids=["json-task", "aea-script"])
@pytest.mark.parametrize("json_output", [False, True], ids=["human", "json-output"])
def test_validation_keeps_zero_exit_status(tmp_path, monkeypatch, script, json_output) -> None:
    path = _task_file(tmp_path, script, "final-verifier")
    responses = []
    manager = TaskManager()

    def respond(request):
        payload = json.loads(request.content)
        spec = manager.parse_script(payload["script"]) if script else payload["task"]
        result = manager.validate(spec)
        responses.append(result)
        return httpx.Response(200, json=result)

    _transport(monkeypatch, respond)
    args = ["validate", str(path), *(["--json"] if json_output else [])]
    result = CliRunner().invoke(task.app, args)
    assert result.exit_code == 0, result.exception
    if json_output:
        assert json.loads(result.stdout) == responses[0]
    else:
        assert "Done" in result.stdout
