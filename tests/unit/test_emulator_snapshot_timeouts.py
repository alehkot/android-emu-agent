"""Snapshot CLI reads must outlast the daemon's bounded console operation."""

from __future__ import annotations

import json
from unittest.mock import Mock

import httpx
import pytest
from typer.testing import CliRunner

from android_emu_agent.cli import daemon_client
from android_emu_agent.cli.commands import emulator


@pytest.mark.parametrize(
    ("command", "endpoint", "timeout", "restart"),
    [
        (["save"], "snapshot_save", 60.0, None),
        (["restore", "--no-restart"], "snapshot_restore", 60.0, False),
        (["restore"], "snapshot_restore", 180.0, True),
    ],
    ids=["save", "live-restore", "restart-restore"],
)
@pytest.mark.parametrize("json_output", [False, True], ids=["human", "json"])
@pytest.mark.parametrize("failed", [False, True], ids=["success", "console-rejection"])
def test_snapshot_result_survives_slow_console_response(
    monkeypatch: pytest.MonkeyPatch,
    command: list[str],
    endpoint: str,
    timeout: float,
    restart: bool | None,
    json_output: bool,
    failed: bool,
) -> None:
    """Exercise real CLI/DaemonClient/HTTPX wiring, not real emulator speed.

    The daemon permits 30 seconds for the console command after its handshake.
    Model a response at 15 seconds, within that budget but beyond the old HTTP
    read limit. MockTransport does not enforce timeouts itself, so explicitly
    compare the timeout HTTPX passes to the transport. No wall-clock sleep,
    socket, device operation or mutation replay is involved.
    """
    payload = (
        {
            "error": {
                "code": "ERR_SNAPSHOT_FAILED",
                "message": "Console rejected snapshot baseline",
                "remediation": "Check the emulator snapshot and retry deliberately",
            }
        }
        if failed
        else {"status": "done"}
    )
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        read_timeout = request.extensions["timeout"]["read"]
        assert read_timeout is not None, "snapshot requests must remain bounded"
        if read_timeout < 15.0:
            raise httpx.ReadTimeout("console operation still completing", request=request)
        return httpx.Response(400 if failed else 200, json=payload)

    controller = Mock()
    monkeypatch.setattr(daemon_client, "DaemonController", controller)
    monkeypatch.setattr(
        daemon_client.httpx, "HTTPTransport", lambda **_: httpx.MockTransport(respond)
    )
    args = ["snapshot", *command, "emulator-5554", "baseline"]
    if json_output:
        args.append("--json")
    result = CliRunner().invoke(emulator.app, args)

    assert result.exit_code == (1 if failed else 0), str(result.exception)
    if json_output:
        assert json.loads(result.stdout) == payload
    elif failed:
        assert "ERR_SNAPSHOT_FAILED: Console rejected snapshot baseline" in result.stdout
        assert "Hint: Check the emulator snapshot and retry deliberately" in result.stdout
        assert "Done" not in result.stdout
    else:
        assert "✓ Done" in result.stdout
    assert len(requests) == 1
    request = requests[0]
    assert request.method == "POST"
    assert request.url.path == f"/emulator/{endpoint}"
    expected: dict[str, str | bool] = {"serial": "emulator-5554", "name": "baseline"}
    if restart is not None:
        expected["restart"] = restart
    assert json.loads(request.content) == expected
    assert request.extensions["timeout"]["read"] == timeout
    controller.return_value.start.assert_not_called()
