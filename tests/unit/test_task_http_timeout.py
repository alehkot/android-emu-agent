"""Task transport budgets are explicit and separate from device wait deadlines."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import Mock

import httpx
import pytest
from typer.testing import CliRunner

from android_emu_agent.cli import daemon_client
from android_emu_agent.cli.commands import task
from android_emu_agent.tasks.manager import TaskManager


def _file(tmp_path, script):
    path = tmp_path / ("flow.aea" if script else "flow.json")
    if script:
        path.write_text('session s-1\nwait text "Ready" timeout_ms=15000\nexpect activity Home\n')
    else:
        path.write_text(
            json.dumps(
                {
                    "session_id": "s-1",
                    "steps": [{"wait": "text", "text": "Ready", "timeout_ms": 15000}],
                    "verifiers": [{"type": "activity", "activity": "Home"}],
                }
            )
        )
    return path


def _install(monkeypatch, respond):
    controller = Mock()
    monkeypatch.setattr(daemon_client, "DaemonController", lambda *_: controller)
    monkeypatch.setattr(
        daemon_client.httpx, "HTTPTransport", lambda **_: httpx.MockTransport(respond)
    )
    return controller


@pytest.mark.parametrize("script", [False, True])
@pytest.mark.parametrize("budget", [None, "0.5", "60", "120.25"])
@pytest.mark.parametrize("failed", [False, True])
@pytest.mark.parametrize("continue_on_failure", [False, True])
def test_run_timeout_wiring_and_complete_execution_result(
    tmp_path, monkeypatch, script, budget, failed, continue_on_failure
):
    path = _file(tmp_path, script)
    manager = TaskManager()
    requests, calls, results = [], [], []

    async def dispatch(call):
        calls.append(call)
        if failed:
            return {"error": {"code": "ERR_TIMEOUT", "message": "not ready"}}
        return {"status": "done"}

    def respond(request):
        requests.append(request)
        assert request.extensions["timeout"] == {
            "connect": 10.0,
            "read": float(budget) if budget else 10.0,
            "write": 10.0,
            "pool": 10.0,
        }
        payload = json.loads(request.content)
        assert payload["session_id"] == "s-1"
        assert payload["stop_on_failure"] is not continue_on_failure
        assert "timeout" not in payload and "http_timeout_seconds" not in payload
        spec = manager.parse_script(payload["script"]) if script else payload["task"]
        result = asyncio.run(
            manager.run(
                spec,
                session_id="s-1",
                dispatcher=dispatch,
                stop_on_failure=not continue_on_failure,
            )
        )
        results.append(result)
        return httpx.Response(200, json=result)

    _install(monkeypatch, respond)
    args = ["run", str(path), "--json"]
    if budget:
        args += ["--http-timeout-seconds", budget]
    if continue_on_failure:
        args += ["--continue-on-failure"]
    result = CliRunner().invoke(task.app, args)
    assert result.exit_code == int(failed), result.exception
    assert len(requests) == 1
    assert requests[0].url.path == ("/tasks/script/run" if script else "/tasks/run")
    assert json.loads(result.stdout) == results[0]
    assert calls[0].payload["timeout_ms"] == 15000
    assert all("http_timeout_seconds" not in call.payload for call in calls)


@pytest.mark.parametrize("script", [False, True])
@pytest.mark.parametrize("budget", ["0", "-1", "nan", "inf", "-inf", "1e999", "bad"])
def test_invalid_budget_rejected_before_client_creation(tmp_path, monkeypatch, script, budget):
    client = Mock()
    monkeypatch.setattr(task, "DaemonClient", client)
    result = CliRunner().invoke(
        task.app,
        [
            "run",
            str(_file(tmp_path, script)),
            "--http-timeout-seconds",
            budget,
        ],
    )
    assert result.exit_code == 2
    assert "--http-timeout-seconds" in result.output
    client.assert_not_called()


@pytest.mark.parametrize("script", [False, True])
def test_explicit_budget_receives_sequential_wait_result(tmp_path, monkeypatch, script):
    """Model server silence deterministically; MockTransport does not enforce timeouts."""
    path = _file(tmp_path, script)
    requests = []
    manager = TaskManager()

    def respond(request):
        requests.append(request)
        payload = json.loads(request.content)
        spec = manager.parse_script(payload["script"]) if script else payload["task"]
        elapsed = 0.0

        async def dispatch(_call):
            nonlocal elapsed
            elapsed += 8.0
            return {"status": "done"}

        result = asyncio.run(manager.run(spec, session_id="s-1", dispatcher=dispatch))
        if elapsed > request.extensions["timeout"]["read"]:
            raise httpx.ReadTimeout("simulated server silence", request=request)
        return httpx.Response(200, json=result)

    controller = _install(monkeypatch, respond)
    default = CliRunner().invoke(task.app, ["run", str(path), "--json"])
    assert isinstance(default.exception, httpx.ReadTimeout)
    assert len(requests) == 1
    controller.start.assert_not_called()
    extended = CliRunner().invoke(
        task.app,
        [
            "run",
            str(path),
            "--http-timeout-seconds",
            "60",
            "--json",
        ],
    )
    assert extended.exit_code == 0, extended.exception
    assert json.loads(extended.stdout)["passed"] is True
    assert len(requests) == 2


def test_request_override_survives_connect_retry_but_not_health_probe(monkeypatch):
    requests = []

    def respond(request):
        requests.append(request)
        if len(requests) == 1:
            raise httpx.ConnectError("not running", request=request)
        return httpx.Response(200, json={"status": "done"})

    controller = _install(monkeypatch, respond)
    client = daemon_client.DaemonClient()
    try:
        response = client.request("POST", "/tasks/run", timeout=httpx.Timeout(10.0, read=120))
        assert response.status_code == 200
        client.request("POST", "/tasks/validate")
    finally:
        client.close()
    assert [r.url.path for r in requests] == [
        "/tasks/run",
        "/health",
        "/tasks/run",
        "/tasks/validate",
    ]
    assert [r.extensions["timeout"]["read"] for r in requests] == [120, 10, 120, 10]
    for request in requests:
        assert all(request.extensions["timeout"][k] == 10 for k in ("connect", "write", "pool"))
    controller.start.assert_called_once()


@pytest.mark.parametrize("error", [httpx.ReadTimeout, httpx.WriteTimeout, httpx.ReadError])
def test_request_override_does_not_allow_uncertain_mutation_retry(monkeypatch, error):
    requests = []

    def respond(request):
        requests.append(request)
        raise error("uncertain", request=request)

    controller = _install(monkeypatch, respond)
    client = daemon_client.DaemonClient()
    try:
        with pytest.raises(error):
            client.request("POST", "/tasks/run", timeout=httpx.Timeout(10.0, read=120))
    finally:
        client.close()
    assert len(requests) == 1
    controller.start.assert_not_called()
