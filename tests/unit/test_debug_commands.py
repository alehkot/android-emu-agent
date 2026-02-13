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


def test_debug_break_set_builds_payload() -> None:
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
        debug.debug_break_set(
            class_pattern="com.example.MainActivity",
            line=25,
            session_id="s-abc123",
            json_output=False,
        )

    assert calls[0] == (
        "POST",
        "/debug/breakpoint/set",
        {
            "session_id": "s-abc123",
            "class_pattern": "com.example.MainActivity",
            "line": 25,
        },
    )


def test_debug_break_remove_builds_payload() -> None:
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
        debug.debug_break_remove(
            breakpoint_id=7,
            session_id="s-abc123",
            json_output=False,
        )

    assert calls[0] == (
        "POST",
        "/debug/breakpoint/remove",
        {"session_id": "s-abc123", "breakpoint_id": 7},
    )


def test_debug_break_list_calls_endpoint() -> None:
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
        debug.debug_break_list(session_id="s-abc123", json_output=False)

    assert calls[0] == ("GET", "/debug/breakpoints?session_id=s-abc123", None)


def test_debug_threads_default_calls_endpoint() -> None:
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
        debug.debug_threads(session_id="s-abc123", include_all=False, json_output=False)

    assert calls[0] == (
        "GET",
        "/debug/threads?session_id=s-abc123&include_daemon=false&max_threads=20",
        None,
    )


def test_debug_threads_all_calls_endpoint() -> None:
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
        debug.debug_threads(session_id="s-abc123", include_all=True, json_output=False)

    assert calls[0] == (
        "GET",
        "/debug/threads?session_id=s-abc123&include_daemon=true&max_threads=100",
        None,
    )


def test_debug_events_calls_endpoint() -> None:
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
        debug.debug_events(session_id="s-abc123", json_output=False)

    assert calls[0] == ("GET", "/debug/events?session_id=s-abc123", None)


def test_debug_stack_calls_endpoint() -> None:
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
        debug.debug_stack(
            session_id="s-abc123",
            thread="main",
            max_frames=10,
            json_output=False,
        )

    assert calls[0] == (
        "POST",
        "/debug/stack",
        {"session_id": "s-abc123", "thread": "main", "max_frames": 10},
    )


def test_debug_inspect_calls_endpoint() -> None:
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
        debug.debug_inspect(
            variable_path="user.profile.name",
            session_id="s-abc123",
            thread="main",
            frame=0,
            depth=2,
            json_output=False,
        )

    assert calls[0] == (
        "POST",
        "/debug/inspect",
        {
            "session_id": "s-abc123",
            "variable_path": "user.profile.name",
            "thread": "main",
            "frame": 0,
            "depth": 2,
        },
    )


def test_debug_eval_calls_endpoint() -> None:
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
        debug.debug_eval(
            expression="savedInstanceState.toString()",
            session_id="s-abc123",
            thread="main",
            frame=0,
            json_output=False,
        )

    assert calls[0] == (
        "POST",
        "/debug/eval",
        {
            "session_id": "s-abc123",
            "expression": "savedInstanceState.toString()",
            "thread": "main",
            "frame": 0,
        },
    )


def test_debug_step_over_calls_endpoint() -> None:
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
        debug.debug_step_over(
            session_id="s-abc123",
            thread="main",
            timeout_seconds=10.0,
            json_output=False,
        )

    assert calls[0] == (
        "POST",
        "/debug/step_over",
        {"session_id": "s-abc123", "thread": "main", "timeout_seconds": 10.0},
    )


def test_debug_step_into_calls_endpoint() -> None:
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
        debug.debug_step_into(
            session_id="s-abc123",
            thread="main",
            timeout_seconds=10.0,
            json_output=False,
        )

    assert calls[0] == (
        "POST",
        "/debug/step_into",
        {"session_id": "s-abc123", "thread": "main", "timeout_seconds": 10.0},
    )


def test_debug_step_out_calls_endpoint() -> None:
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
        debug.debug_step_out(
            session_id="s-abc123",
            thread="main",
            timeout_seconds=10.0,
            json_output=False,
        )

    assert calls[0] == (
        "POST",
        "/debug/step_out",
        {"session_id": "s-abc123", "thread": "main", "timeout_seconds": 10.0},
    )


def test_debug_resume_calls_endpoint_for_all_threads() -> None:
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
        debug.debug_resume(session_id="s-abc123", thread=None, json_output=False)

    assert calls[0] == ("POST", "/debug/resume", {"session_id": "s-abc123"})


def test_debug_resume_calls_endpoint_for_specific_thread() -> None:
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
        debug.debug_resume(session_id="s-abc123", thread="main", json_output=False)

    assert calls[0] == ("POST", "/debug/resume", {"session_id": "s-abc123", "thread": "main"})
