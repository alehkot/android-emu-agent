"""Tests for trace CLI command payload wiring."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch


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
