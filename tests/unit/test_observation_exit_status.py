"""Session/snapshot CLI errors retain their payload but fail shell automation."""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager, redirect_stdout
from io import StringIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from fastapi import Response
from typer.testing import CliRunner

from android_emu_agent.cli import daemon_client
from android_emu_agent.cli.main import app
from android_emu_agent.daemon import server
from android_emu_agent.daemon.models import SessionStartRequest, SnapshotRequest


@asynccontextmanager
async def _snapshot_lock(_session_id):
    yield


def _transport(monkeypatch, respond):
    transports = []

    def make_transport(**_kwargs):
        transport = httpx.MockTransport(respond)
        transport.close = Mock(wraps=transport.close)
        transports.append(transport)
        return transport

    monkeypatch.setattr(daemon_client, "DaemonController", Mock())
    monkeypatch.setattr(daemon_client.httpx, "HTTPTransport", make_transport)
    return transports


def _response(result):
    if isinstance(result, Response):
        return httpx.Response(
            result.status_code, content=bytes(result.body), headers=result.headers
        )
    return httpx.Response(200, json=result)


@pytest.mark.parametrize("json_output", [False, True], ids=["human", "json"])
@pytest.mark.parametrize("online", [False, True], ids=["offline", "online"])
def test_session_start_endpoint_exit_status(monkeypatch, json_output, online):
    core = SimpleNamespace(device_manager=AsyncMock(), session_manager=AsyncMock())
    core.device_manager.get_device.return_value = {"serial": "emulator-5554"} if online else None
    core.session_manager.create_session.return_value = SimpleNamespace(
        session_id="s-new", device_serial="emulator-5554", generation=0
    )
    monkeypatch.setattr(server.app.state, "core", core, raising=False)
    responses = []

    def respond(request):
        assert request.method == "POST"
        assert request.url.path == "/sessions/start"
        assert json.loads(request.content) == {"device_serial": "emulator-5554"}
        response = _response(
            asyncio.run(
                server.session_start(SessionStartRequest.model_validate_json(request.content))
            )
        )
        responses.append(response.json())
        return response

    transports = _transport(monkeypatch, respond)
    args = ["session", "start", "--device", "emulator-5554"]
    result = CliRunner().invoke(app, args + (["--json"] if json_output else []))
    assert result.exit_code == (0 if online else 1), result.output
    assert len(responses) == 1
    transports[0].close.assert_called_once()
    if json_output:
        assert json.loads(result.stdout) == responses[0]
    elif online:
        assert result.stdout == "s-new\n"
    else:
        assert "ERR_DEVICE_OFFLINE" in result.stdout
        assert "Hint:" in result.stdout
    if not online:
        core.session_manager.create_session.assert_not_awaited()


@pytest.mark.parametrize("mode", ["compact", "full", "raw"])
@pytest.mark.parametrize("format_", ["json", "text"])
@pytest.mark.parametrize("failure", ["expired", "offline", "capture"])
def test_snapshot_endpoint_errors_exit_nonzero(monkeypatch, mode, format_, failure):
    session = SimpleNamespace(session_id="s-test", device_serial="emulator-5554", generation=2)
    core = SimpleNamespace(session_manager=AsyncMock(), device_manager=AsyncMock())
    core.session_manager.get_session.return_value = None if failure == "expired" else session
    core.session_manager.snapshot_lock = _snapshot_lock
    device = Mock()
    device.dump_hierarchy.side_effect = RuntimeError("hierarchy capture unavailable")
    core.device_manager.get_u2_device.return_value = None if failure == "offline" else device
    core.device_manager.get_adb_device.return_value = Mock()
    monkeypatch.setattr(server.app.state, "core", core, raising=False)
    responses = []

    def respond(request):
        assert request.method == "POST"
        assert request.url.path == "/ui/snapshot"
        assert json.loads(request.content) == {"session_id": "s-test", "mode": mode}
        # In production daemon logs are not part of the CLI stdout stream.
        with redirect_stdout(StringIO()):
            response = _response(
                asyncio.run(
                    server.ui_snapshot(SnapshotRequest.model_validate_json(request.content))
                )
            )
        responses.append(response.json())
        return response

    transports = _transport(monkeypatch, respond)
    args = ["ui", "snapshot", "s-test", "--format", format_]
    if mode != "compact":
        args.append("--" + mode)
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 1, result.output
    assert len(responses) == 1
    assert json.loads(result.stdout) == responses[0]
    assert (
        responses[0]["error"]["code"]
        == {
            "expired": "ERR_SESSION_EXPIRED",
            "offline": "ERR_DEVICE_OFFLINE",
            "capture": "ERR_SNAPSHOT_FAILED",
        }[failure]
    )
    assert responses[0]["error"]["remediation"]
    transports[0].close.assert_called_once()


@pytest.mark.parametrize("mode", ["compact", "full", "raw"])
@pytest.mark.parametrize("format_", ["json", "text"])
@pytest.mark.parametrize("empty", [False, True], ids=["elements", "empty"])
def test_snapshot_success_output_is_unchanged(monkeypatch, mode, format_, empty):
    payload = {
        "session_id": "s-test",
        "generation": 3,
        "elements": []
        if empty
        else [{"ref": "^g3a1", "label": "Continue", "role": "button", "bounds": [0, 0, 10, 10]}],
    }
    xml = '<hierarchy><node text="Continue" /></hierarchy>'

    def respond(request):
        assert json.loads(request.content) == {"session_id": "s-test", "mode": mode}
        if mode == "raw":
            return httpx.Response(200, text=xml, headers={"content-type": "application/xml"})
        return httpx.Response(200, json=payload)

    transports = _transport(monkeypatch, respond)
    args = ["ui", "snapshot", "s-test", "--format", format_]
    if mode != "compact":
        args.append("--" + mode)
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 0, result.exception
    transports[0].close.assert_called_once()
    if mode == "raw":
        assert result.stdout == xml + "\n"
    elif format_ == "json":
        assert json.loads(result.stdout) == payload
    else:
        expected = f"session=s-test generation=3 elements={len(payload['elements'])}\n"
        if not empty:
            expected += "^g3a1 button 'Continue' id=- bounds=[0, 0, 10, 10]\n"
        assert result.stdout == expected
