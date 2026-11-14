"""Tests for trace CLI command payload wiring."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

import pytest


class DummyResponse:
    """Simple response stub for CLI handlers."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def json(self) -> dict[str, Any]:
        return self._payload


def test_trace_start_builds_payload() -> None:
    """Should send trace start payload to the daemon."""
    from android_emu_agent.cli.commands import trace

    calls: list[tuple[str, str, dict[str, Any] | None]] = []

    class DummyClient:
        def __init__(self, *_: Any, **__: Any) -> None:
            pass

        def request(self, method: str, path: str, json_body: dict[str, Any] | None = None):
            calls.append((method, path, json_body))
            return DummyResponse({"status": "done"})

        def close(self) -> None:
            return None

    with patch.object(trace, "DaemonClient", DummyClient):
        trace.trace_start("s-abc123", label="checkout", json_output=False)

    assert calls[0] == (
        "POST",
        "/trace/start",
        {"session_id": "s-abc123", "label": "checkout"},
    )


def test_trace_stop_builds_output_payload() -> None:
    """Should send trace stop output path to the daemon."""
    from android_emu_agent.cli.commands import trace

    calls: list[tuple[str, str, dict[str, Any] | None]] = []

    class DummyClient:
        def __init__(self, *_: Any, **__: Any) -> None:
            pass

        def request(self, method: str, path: str, json_body: dict[str, Any] | None = None):
            calls.append((method, path, json_body))
            return DummyResponse({"status": "done", "path": "/tmp/run.aea-trace.zip"})

        def close(self) -> None:
            return None

    with patch.object(trace, "DaemonClient", DummyClient):
        trace.trace_stop("s-abc123", output="/tmp/run.aea-trace.zip", json_output=False)

    assert calls[0] == (
        "POST",
        "/trace/stop",
        {"session_id": "s-abc123", "output_path": "/tmp/run.aea-trace.zip"},
    )


def test_trace_status_prints_the_traces_without_json(capsys: pytest.CaptureFixture[str]) -> None:
    """Text output should list the traces, not only "✓ Done"."""
    from android_emu_agent.cli.commands import trace

    payload = {"status": "done", "traces": [{"trace_id": "tr-abc", "trace_status": "active"}]}

    class DummyClient:
        def __init__(self, *_: Any, **__: Any) -> None:
            pass

        def request(self, *_: Any, **__: Any) -> DummyResponse:
            return DummyResponse(payload)

        def close(self) -> None:
            return None

    with patch.object(trace, "DaemonClient", DummyClient):
        trace.trace_status(session_id=None, json_output=False)

    assert json.loads(capsys.readouterr().out) == payload


@pytest.mark.parametrize(
    ("output", "expected"),
    [(None, "# Trace report\n\n"), ("/tmp/run.md", "✓ Done -> /tmp/run.md\n")],
    ids=["no-output", "output"],
)
def test_trace_export_text_output_shows_the_report_or_its_path(
    output: str | None, expected: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """Text output shouldn't name the source archive as if the report were written there."""
    from android_emu_agent.cli.commands import trace

    payload = {"status": "done", "path": "/tmp/run.aea-trace.zip", "markdown": "# Trace report\n"}
    if output:
        payload["output_path"] = output

    class DummyClient:
        def __init__(self, *_: Any, **__: Any) -> None:
            pass

        def request(self, *_: Any, **__: Any) -> DummyResponse:
            return DummyResponse(payload)

        def close(self) -> None:
            return None

    with patch.object(trace, "DaemonClient", DummyClient):
        trace.trace_export("/tmp/run.aea-trace.zip", output=output, json_output=False)

    assert capsys.readouterr().out == expected


def test_trace_replay_builds_payload() -> None:
    """Should send dry replay options to the daemon."""
    from android_emu_agent.cli.commands import trace

    calls: list[tuple[str, str, dict[str, Any] | None]] = []

    class DummyClient:
        def __init__(self, *_: Any, **__: Any) -> None:
            pass

        def request(self, method: str, path: str, json_body: dict[str, Any] | None = None):
            calls.append((method, path, json_body))
            return DummyResponse({"status": "done"})

        def close(self) -> None:
            return None

    with patch.object(trace, "DaemonClient", DummyClient):
        trace.trace_replay("/tmp/run.aea-trace.zip", until_failure=True, json_output=False)

    assert calls[0] == (
        "POST",
        "/trace/replay",
        {"path": "/tmp/run.aea-trace.zip", "until_failure": True},
    )


def test_trace_export_builds_payload() -> None:
    """Should request Markdown export from the daemon."""
    from android_emu_agent.cli.commands import trace

    calls: list[tuple[str, str, dict[str, Any] | None]] = []

    class DummyClient:
        def __init__(self, *_: Any, **__: Any) -> None:
            pass

        def request(self, method: str, path: str, json_body: dict[str, Any] | None = None):
            calls.append((method, path, json_body))
            return DummyResponse({"status": "done"})

        def close(self) -> None:
            return None

    with patch.object(trace, "DaemonClient", DummyClient):
        trace.trace_export(
            "/tmp/run.aea-trace.zip",
            output="/tmp/run.md",
            json_output=False,
        )

    assert calls[0] == (
        "POST",
        "/trace/export",
        {
            "path": "/tmp/run.aea-trace.zip",
            "output_path": "/tmp/run.md",
            "format": "markdown",
        },
    )
