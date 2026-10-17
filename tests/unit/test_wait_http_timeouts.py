"""CLI transport budgets must allow the daemon to return its wait result."""

from __future__ import annotations

import json
from unittest.mock import Mock

import httpx
import pytest
from typer.testing import CliRunner

from android_emu_agent.cli import daemon_client
from android_emu_agent.cli.commands import expect, wait

COMMANDS = [
    ["idle", "s-1"],
    ["activity", "s-1", "MainActivity"],
    ["text", "s-1", "Welcome"],
    ["exists", "s-1", "--text", "Welcome"],
    ["gone", "s-1", "--text", "Loading"],
]


@pytest.mark.parametrize("module", [wait, expect], ids=["wait", "expect"])
@pytest.mark.parametrize("command", COMMANDS, ids=lambda args: args[0])
@pytest.mark.parametrize("timeout_ms", [None, 0, 500, 15000, 60000])
def test_wait_cli_budget_reaches_http_transport(monkeypatch, module, command, timeout_ms) -> None:
    """Exercise real CLI and HTTPX wiring with a deterministic delayed-response model.

    MockTransport itself does not enforce timeouts; inspect the actual HTTPX request
    extension and simulate a timeout if the daemon result exceeds that read budget.
    No wall-clock sleeps or live device/socket are needed for this regression.
    """
    requests: list[httpx.Request] = []
    effective_wait = (timeout_ms or 10000) / 1000
    response_at = effective_wait + 0.1

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        read_timeout = request.extensions["timeout"]["read"]
        assert read_timeout is not None, "wait transport must remain bounded"
        if read_timeout < response_at:
            raise httpx.ReadTimeout("daemon has not finished waiting", request=request)
        return httpx.Response(200, json={"status": "done"})

    monkeypatch.setattr(daemon_client, "DaemonController", Mock())
    monkeypatch.setattr(
        daemon_client.httpx, "HTTPTransport", lambda **_: httpx.MockTransport(respond)
    )
    args = [*command, "--json"]
    if timeout_ms is not None:
        args += ["--timeout-ms", str(timeout_ms)]
    result = CliRunner().invoke(module.app, args)
    assert result.exit_code == 0, str(result.exception)
    assert json.loads(result.stdout) == {"status": "done"}
    assert len(requests) == 1
    request = requests[0]
    assert request.extensions["timeout"]["read"] == max(10.0, effective_wait + 10.0)
    assert json.loads(request.content)["timeout_ms"] == timeout_ms
    assert request.url.path == f"/{module.__name__.rsplit('.', 1)[-1]}/{command[0]}"


@pytest.mark.parametrize("module,code", [(wait, "ERR_TIMEOUT"), (expect, "ERR_EXPECTATION_FAILED")])
def test_default_wait_failure_returns_structured_result(monkeypatch, module, code) -> None:
    """A result just after the default wait deadline remains a daemon error, not HTTP timeout."""
    requests: list[httpx.Request] = []
    payload = {"error": {"code": code, "message": "condition not reached"}}

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.extensions["timeout"]["read"] < 10.1:
            raise httpx.ReadTimeout("default daemon wait still completing", request=request)
        return httpx.Response(408, json=payload)

    monkeypatch.setattr(daemon_client, "DaemonController", Mock())
    monkeypatch.setattr(
        daemon_client.httpx, "HTTPTransport", lambda **_: httpx.MockTransport(respond)
    )
    result = CliRunner().invoke(module.app, ["text", "s-1", "Welcome", "--json"])
    assert result.exit_code == 1
    assert json.loads(result.stdout) == payload
    assert len(requests) == 1


def test_current_app_retains_regular_transport_budget(monkeypatch) -> None:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"status": "done"})

    monkeypatch.setattr(daemon_client, "DaemonController", Mock())
    monkeypatch.setattr(
        daemon_client.httpx, "HTTPTransport", lambda **_: httpx.MockTransport(respond)
    )
    result = CliRunner().invoke(expect.app, ["current-app", "s-1", "--package", "com.example"])
    assert result.exit_code == 0
    assert requests[0].extensions["timeout"]["read"] == 10.0
