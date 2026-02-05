"""Tests for file-related CLI commands."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch


class DummyResponse:
    """Simple response stub for CLI handlers."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def json(self) -> dict[str, Any]:
        return self._payload


def test_file_find_builds_payload() -> None:
    """Should send find payload to the daemon."""
    from android_emu_agent.cli.commands import file as file_commands

    calls: list[tuple[str, str, dict[str, Any] | None]] = []

    class DummyClient:
        def __init__(self, *_: Any, **__: Any) -> None:
            pass

        def request(self, method: str, path: str, json_body: dict[str, Any] | None = None):
            calls.append((method, path, json_body))
            return DummyResponse({"status": "done"})

        def close(self) -> None:
            return None

    with patch.object(file_commands, "DaemonClient", DummyClient):
        file_commands.file_find(
            "/data/data",
            name="*.db",
            kind="file",
            max_depth=3,
            device="emulator-5554",
            session_id=None,
            json_output=False,
        )

    method, path, payload = calls[0]
    assert method == "POST"
    assert path == "/files/find"
    assert payload == {
        "serial": "emulator-5554",
        "path": "/data/data",
        "name": "*.db",
        "kind": "file",
        "max_depth": 3,
    }


def test_file_list_builds_payload() -> None:
    """Should send list payload to the daemon."""
    from android_emu_agent.cli.commands import file as file_commands

    calls: list[tuple[str, str, dict[str, Any] | None]] = []

    class DummyClient:
        def __init__(self, *_: Any, **__: Any) -> None:
            pass

        def request(self, method: str, path: str, json_body: dict[str, Any] | None = None):
            calls.append((method, path, json_body))
            return DummyResponse({"status": "done"})

        def close(self) -> None:
            return None

    with patch.object(file_commands, "DaemonClient", DummyClient):
        file_commands.file_list(
            "/sdcard",
            kind="dir",
            device="emulator-5554",
            session_id=None,
            json_output=False,
        )

    method, path, payload = calls[0]
    assert method == "POST"
    assert path == "/files/list"
    assert payload == {
        "serial": "emulator-5554",
        "path": "/sdcard",
        "kind": "dir",
    }


def test_file_push_builds_payload() -> None:
    """Should send push payload to the daemon."""
    from android_emu_agent.cli.commands import file as file_commands

    calls: list[tuple[str, str, dict[str, Any] | None]] = []

    class DummyClient:
        def __init__(self, *_: Any, **__: Any) -> None:
            pass

        def request(self, method: str, path: str, json_body: dict[str, Any] | None = None):
            calls.append((method, path, json_body))
            return DummyResponse({"status": "done"})

        def close(self) -> None:
            return None

    with patch.object(file_commands, "DaemonClient", DummyClient):
        file_commands.file_push(
            "./local.txt",
            remote_path="/sdcard/Download/local.txt",
            device="emulator-5554",
            session_id=None,
            json_output=False,
        )

    method, path, payload = calls[0]
    assert method == "POST"
    assert path == "/files/push"
    assert payload == {
        "serial": "emulator-5554",
        "local_path": "./local.txt",
        "remote_path": "/sdcard/Download/local.txt",
    }


def test_file_app_pull_builds_payload() -> None:
    """Should send app pull payload to the daemon."""
    from android_emu_agent.cli.commands import file as file_commands

    calls: list[tuple[str, str, dict[str, Any] | None]] = []

    class DummyClient:
        def __init__(self, *_: Any, **__: Any) -> None:
            pass

        def request(self, method: str, path: str, json_body: dict[str, Any] | None = None):
            calls.append((method, path, json_body))
            return DummyResponse({"status": "done"})

        def close(self) -> None:
            return None

    with patch.object(file_commands, "DaemonClient", DummyClient):
        file_commands.file_app_pull(
            "com.example.app",
            "files/config.json",
            local_path="/tmp/config.json",
            device="emulator-5554",
            session_id=None,
            json_output=False,
        )

    method, path, payload = calls[0]
    assert method == "POST"
    assert path == "/files/app_pull"
    assert payload == {
        "serial": "emulator-5554",
        "package": "com.example.app",
        "remote_path": "files/config.json",
        "local_path": "/tmp/config.json",
    }
