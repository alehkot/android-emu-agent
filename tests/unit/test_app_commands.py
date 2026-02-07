"""Tests for app-related CLI commands."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch


class DummyResponse:
    """Simple response stub for CLI handlers."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def json(self) -> dict[str, Any]:
        return self._payload


def test_app_install_builds_payload() -> None:
    """Should send install payload to the daemon."""
    from android_emu_agent.cli.commands import app_cmd

    calls: list[tuple[str, str, dict[str, Any] | None]] = []

    class DummyClient:
        def __init__(self, *_: Any, **__: Any) -> None:
            pass

        def request(self, method: str, path: str, json_body: dict[str, Any] | None = None):
            calls.append((method, path, json_body))
            return DummyResponse({"status": "done", "output": "Success"})

        def close(self) -> None:
            return None

    with patch.object(app_cmd, "DaemonClient", DummyClient):
        app_cmd.app_install(
            "/tmp/app-debug.apk",
            device="emulator-5554",
            session_id=None,
            replace=True,
            grant_permissions=False,
            allow_downgrade=False,
            json_output=False,
        )

    method, path, payload = calls[0]
    assert method == "POST"
    assert path == "/app/install"
    assert payload == {
        "serial": "emulator-5554",
        "apk_path": "/tmp/app-debug.apk",
        "replace": True,
        "grant_permissions": False,
        "allow_downgrade": False,
    }


def test_app_launch_wait_debugger_builds_payload() -> None:
    """Should include wait_debugger for app launch."""
    from android_emu_agent.cli.commands import app_cmd

    calls: list[tuple[str, str, dict[str, Any] | None]] = []

    class DummyClient:
        def __init__(self, *_: Any, **__: Any) -> None:
            pass

        def request(self, method: str, path: str, json_body: dict[str, Any] | None = None):
            calls.append((method, path, json_body))
            return DummyResponse({"status": "done"})

        def close(self) -> None:
            return None

    with patch.object(app_cmd, "DaemonClient", DummyClient):
        app_cmd.app_launch(
            "s-abc123",
            "com.example.app",
            activity=".MainActivity",
            wait_debugger=True,
            json_output=False,
        )

    method, path, payload = calls[0]
    assert method == "POST"
    assert path == "/app/launch"
    assert payload == {
        "session_id": "s-abc123",
        "package": "com.example.app",
        "activity": ".MainActivity",
        "wait_debugger": True,
    }


def test_app_deeplink_wait_debugger_builds_payload() -> None:
    """Should include wait_debugger for deeplink launch."""
    from android_emu_agent.cli.commands import app_cmd

    calls: list[tuple[str, str, dict[str, Any] | None]] = []

    class DummyClient:
        def __init__(self, *_: Any, **__: Any) -> None:
            pass

        def request(self, method: str, path: str, json_body: dict[str, Any] | None = None):
            calls.append((method, path, json_body))
            return DummyResponse({"status": "done"})

        def close(self) -> None:
            return None

    with patch.object(app_cmd, "DaemonClient", DummyClient):
        app_cmd.app_deeplink(
            "s-abc123",
            "https://example.com/deep",
            wait_debugger=True,
            json_output=False,
        )

    method, path, payload = calls[0]
    assert method == "POST"
    assert path == "/app/deeplink"
    assert payload == {
        "session_id": "s-abc123",
        "uri": "https://example.com/deep",
        "wait_debugger": True,
    }


def test_app_intent_builds_payload() -> None:
    """Should send intent payload to the daemon."""
    from android_emu_agent.cli.commands import app_cmd

    calls: list[tuple[str, str, dict[str, Any] | None]] = []

    class DummyClient:
        def __init__(self, *_: Any, **__: Any) -> None:
            pass

        def request(self, method: str, path: str, json_body: dict[str, Any] | None = None):
            calls.append((method, path, json_body))
            return DummyResponse({"status": "done"})

        def close(self) -> None:
            return None

    with patch.object(app_cmd, "DaemonClient", DummyClient):
        app_cmd.app_intent(
            "s-abc123",
            action="android.intent.action.MAIN",
            data_uri=None,
            component="com.example.app/.MainActivity",
            package="com.example.app",
            wait_debugger=True,
            json_output=False,
        )

    method, path, payload = calls[0]
    assert method == "POST"
    assert path == "/app/intent"
    assert payload == {
        "session_id": "s-abc123",
        "action": "android.intent.action.MAIN",
        "data_uri": None,
        "component": "com.example.app/.MainActivity",
        "package": "com.example.app",
        "wait_debugger": True,
    }
