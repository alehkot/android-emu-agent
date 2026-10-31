"""HTTP failures must not become successful CLI exits or artifact copies."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest
import typer
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from android_emu_agent.cli import utils
from android_emu_agent.cli.commands import app_cmd, emulator, reliability
from android_emu_agent.daemon import server

HANDLERS = [utils.handle_response, utils.handle_output_response, utils.handle_response_with_pull]


@pytest.mark.parametrize("json_output", [False, True], ids=["human", "json"])
@pytest.mark.parametrize(
    ("module", "args", "endpoint"),
    [
        (
            reliability,
            ["compile", "com.example", "--device", "emulator-5554", "--mode", "speeed"],
            "/reliability/compile",
        ),
        (
            emulator,
            ["start", "Pixel_8", "--snapshot", "saved", "--cold-boot"],
            "/emulator/start",
        ),
        (app_cmd, ["intent", "s-example"], "/app/intent"),
    ],
    ids=["invalid-compile-mode", "conflicting-boot-options", "missing-intent-target"],
)
def test_real_validation_rejection_exits_nonzero(
    module: Any,
    args: list[str],
    endpoint: str,
    json_output: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exercise CLI payload wiring and real FastAPI validation without a daemon/device."""
    core = MagicMock(diagnostics=None, trace_manager=None)
    monkeypatch.setattr(server.app.state, "core", core, raising=False)
    api = TestClient(server.app)  # Deliberately do not enter lifespan/start device services.
    responses: list[httpx.Response] = []

    def request(method: str, path: str, **kwargs: Any) -> httpx.Response:
        assert method == "POST"
        assert path == endpoint
        response = api.request(method, path, json=kwargs["json_body"])
        responses.append(response)
        return response

    client = MagicMock()
    client.request.side_effect = request
    monkeypatch.setattr(module, "DaemonClient", lambda **_kwargs: client)
    result = CliRunner().invoke(module.app, [*args, *(["--json"] if json_output else [])])
    api.close()

    assert len(responses) == 1
    response = responses[0]
    assert response.status_code == 422
    assert response.json()["detail"]
    assert response.json()["diagnostic_id"]
    assert result.exit_code == 1
    assert json.loads(result.stdout) == response.json()
    client.close.assert_called_once_with()
    assert core.mock_calls == []  # Validation rejected the payload before any device operation.


@pytest.mark.parametrize("handler", HANDLERS, ids=["response", "output", "pull"])
@pytest.mark.parametrize("json_output", [False, True], ids=["human", "json"])
@pytest.mark.parametrize("status_code", [400, 404, 422, 500])
def test_http_error_details_are_preserved_and_fail(
    handler: Callable[..., None],
    json_output: bool,
    status_code: int,
    capsys: pytest.CaptureFixture[str],
) -> None:
    payload = {"detail": "Request was rejected", "diagnostic_id": "test-diagnostic"}
    response = httpx.Response(status_code, json=payload)

    with pytest.raises(typer.Exit) as exc_info:
        handler(response, json_output=json_output)

    assert exc_info.value.exit_code == 1
    assert json.loads(capsys.readouterr().out) == payload


@pytest.mark.parametrize("handler", HANDLERS, ids=["response", "output", "pull"])
@pytest.mark.parametrize("json_output", [False, True], ids=["human", "json"])
def test_http_error_cannot_render_success_or_copy_artifact(
    handler: Callable[..., None],
    json_output: bool,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "source.png"
    source.write_bytes(b"source artifact")
    destination = tmp_path / "destination.png"
    destination.write_bytes(b"keep existing artifact")
    payload = {"status": "done", "output": "misleading success", "path": str(source)}
    response = httpx.Response(500, json=payload)
    kwargs: dict[str, Any] = {"json_output": json_output}
    if handler is utils.handle_response_with_pull:
        kwargs.update(pull=True, output=str(destination))

    with pytest.raises(typer.Exit) as exc_info:
        handler(response, **kwargs)

    assert exc_info.value.exit_code == 1
    assert json.loads(capsys.readouterr().out) == payload
    assert destination.read_bytes() == b"keep existing artifact"
    assert source.read_bytes() == b"source artifact"


@pytest.mark.parametrize("handler", HANDLERS, ids=["response", "output", "pull"])
@pytest.mark.parametrize("json_output", [False, True], ids=["human", "json"])
def test_success_response_and_artifact_copy_still_work(
    handler: Callable[..., None],
    json_output: bool,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "source.png"
    source.write_bytes(b"source artifact")
    destination = tmp_path / "destination.png"
    payload = {"status": "done", "path": str(source), "elapsed_ms": 12}
    kwargs: dict[str, Any] = {"json_output": json_output}
    if handler is utils.handle_response_with_pull:
        kwargs.update(pull=True, output=str(destination))

    handler(httpx.Response(200, json=payload), **kwargs)

    output = capsys.readouterr().out
    if handler is utils.handle_response_with_pull:
        assert destination.read_bytes() == b"source artifact"
        payload["pulled_path"] = str(destination)
    if json_output:
        assert json.loads(output) == payload
    else:
        assert "✓ Done (12 ms)" in output
        assert str(source) in output


@pytest.mark.parametrize("handler", HANDLERS, ids=["response", "output", "pull"])
@pytest.mark.parametrize("json_output", [False, True], ids=["human", "json"])
def test_structured_agent_error_contract_is_unchanged(
    handler: Callable[..., None],
    json_output: bool,
    capsys: pytest.CaptureFixture[str],
) -> None:
    payload = {
        "error": {
            "code": "ERR_DEVICE_OFFLINE",
            "message": "Device is offline",
            "remediation": "Reconnect the device",
        },
        "diagnostic_id": "test-diagnostic",
    }
    with pytest.raises(typer.Exit) as exc_info:
        handler(httpx.Response(400, json=payload), json_output=json_output)

    assert exc_info.value.exit_code == 1
    output = capsys.readouterr().out
    if json_output:
        assert json.loads(output) == payload
    else:
        assert output == "ERR_DEVICE_OFFLINE: Device is offline\nHint: Reconnect the device\n"
