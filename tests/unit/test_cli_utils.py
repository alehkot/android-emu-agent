"""Tests for shared CLI response handling."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import pytest
import typer

from android_emu_agent.cli.utils import (
    handle_output_response,
    handle_response,
    handle_response_with_pull,
)


class DummyResponse:
    """Minimal HTTP response stub."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def json(self) -> dict[str, Any]:
        return self.payload


@pytest.mark.parametrize("handler", [handle_response, handle_output_response])
def test_json_error_output_exits_nonzero(
    handler: Callable[[Any, bool], None],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Machine-readable errors should remain JSON and return a failure status."""
    payload = {
        "status": "error",
        "error": {
            "code": "ERR_DEVICE_OFFLINE",
            "message": "Device is offline",
            "remediation": "Reconnect the device",
        },
    }

    with pytest.raises(typer.Exit) as exc_info:
        handler(DummyResponse(payload), True)

    assert exc_info.value.exit_code == 1
    assert json.loads(capsys.readouterr().out) == payload


def test_json_pull_error_output_exits_nonzero(capsys: pytest.CaptureFixture[str]) -> None:
    """Artifact response handling should use the same JSON error exit contract."""
    payload = {
        "status": "error",
        "error": {"code": "ERR_NO_SNAPSHOT", "message": "No snapshot available"},
    }

    with pytest.raises(typer.Exit) as exc_info:
        handle_response_with_pull(DummyResponse(payload), json_output=True)

    assert exc_info.value.exit_code == 1
    assert json.loads(capsys.readouterr().out) == payload


def test_json_success_output_keeps_zero_exit(capsys: pytest.CaptureFixture[str]) -> None:
    """Successful machine-readable output should return normally."""
    payload = {"status": "done", "session_id": "s-abc123"}

    handle_response(DummyResponse(payload), json_output=True)

    assert json.loads(capsys.readouterr().out) == payload
