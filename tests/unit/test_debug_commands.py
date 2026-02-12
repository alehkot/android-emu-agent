"""Tests for debug CLI command payload wiring."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch


class DummyResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def json(self) -> dict[str, Any]:
        return self._payload


def test_debug_ping_builds_payload() -> None:
    from android_emu_agent.cli.commands import debug

    calls: list[tuple[str, str, dict[str, Any] | None]] = []

    class DummyClient:
        def __init__(self, *_: Any, **__: Any) -> None:
            pass

        def request(self, method: str, path: str, json_body: dict[str, Any] | None = None):
            calls.append((method, path, json_body))
            return DummyResponse({"status": "done"})

        def close(self) -> None:
            return None

    with patch.object(debug, "DaemonClient", DummyClient):
        debug.debug_ping("s-abc123", json_output=False)

    assert calls[0] == ("POST", "/debug/ping", {"session_id": "s-abc123"})


def test_debug_attach_builds_payload_with_process() -> None:
    from android_emu_agent.cli.commands import debug

    calls: list[tuple[str, str, dict[str, Any] | None]] = []

    class DummyClient:
        def __init__(self, *_: Any, **__: Any) -> None:
            pass

        def request(self, method: str, path: str, json_body: dict[str, Any] | None = None):
            calls.append((method, path, json_body))
            return DummyResponse({"status": "done"})

        def close(self) -> None:
            return None

    with patch.object(debug, "DaemonClient", DummyClient):
        debug.debug_attach(
            session_id="s-abc123",
            package="com.example.app",
            process="com.example.app:remote",
            json_output=False,
        )

    assert calls[0] == (
        "POST",
        "/debug/attach",
        {
            "session_id": "s-abc123",
            "package": "com.example.app",
            "process": "com.example.app:remote",
        },
    )


def test_debug_detach_builds_payload() -> None:
    from android_emu_agent.cli.commands import debug

    calls: list[tuple[str, str, dict[str, Any] | None]] = []

    class DummyClient:
        def __init__(self, *_: Any, **__: Any) -> None:
            pass

        def request(self, method: str, path: str, json_body: dict[str, Any] | None = None):
            calls.append((method, path, json_body))
            return DummyResponse({"status": "done"})

        def close(self) -> None:
            return None

    with patch.object(debug, "DaemonClient", DummyClient):
        debug.debug_detach(session_id="s-abc123", json_output=False)

    assert calls[0] == ("POST", "/debug/detach", {"session_id": "s-abc123"})


def test_debug_status_calls_status_endpoint() -> None:
    from android_emu_agent.cli.commands import debug

    calls: list[tuple[str, str, dict[str, Any] | None]] = []

    class DummyClient:
        def __init__(self, *_: Any, **__: Any) -> None:
            pass

        def request(self, method: str, path: str, json_body: dict[str, Any] | None = None):
            calls.append((method, path, json_body))
            return DummyResponse({"status": "done"})

        def close(self) -> None:
            return None

    with patch.object(debug, "DaemonClient", DummyClient):
        debug.debug_status(session_id="s-abc123", json_output=False)

    assert calls[0] == ("GET", "/debug/status/s-abc123", None)
