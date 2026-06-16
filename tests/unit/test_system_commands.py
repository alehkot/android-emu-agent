"""Tests for system surface CLI commands."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch


class DummyResponse:
    """Simple response stub for CLI handlers."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def json(self) -> dict[str, Any]:
        return self._payload


def test_system_notifications_open_builds_payload() -> None:
    """Should send notification-open payload to the daemon."""
    from android_emu_agent.cli.commands import system

    calls: list[tuple[str, str, dict[str, Any] | None]] = []

    class DummyClient:
        def __init__(self, *_: Any, **__: Any) -> None:
            pass

        def request(self, method: str, path: str, json_body: dict[str, Any] | None = None):
            calls.append((method, path, json_body))
            return DummyResponse({"status": "done"})

        def close(self) -> None:
            return None

    with patch.object(system, "DaemonClient", DummyClient):
        system.system_notifications_open(
            device=None,
            session_id="s-abc123",
            json_output=False,
        )

    assert calls[0] == ("POST", "/system/notifications/open", {"session_id": "s-abc123"})


def test_system_quick_settings_open_builds_payload() -> None:
    """Should send Quick Settings payload to the daemon."""
    from android_emu_agent.cli.commands import system

    calls: list[tuple[str, str, dict[str, Any] | None]] = []

    class DummyClient:
        def __init__(self, *_: Any, **__: Any) -> None:
            pass

        def request(self, method: str, path: str, json_body: dict[str, Any] | None = None):
            calls.append((method, path, json_body))
            return DummyResponse({"status": "done"})

        def close(self) -> None:
            return None

    with patch.object(system, "DaemonClient", DummyClient):
        system.system_quick_settings_open(
            device="emulator-5554",
            session_id=None,
            json_output=False,
        )

    assert calls[0] == ("POST", "/system/quick_settings/open", {"serial": "emulator-5554"})


def test_system_permissions_grant_builds_payload() -> None:
    """Should send permission grant payload to the daemon."""
    from android_emu_agent.cli.commands import system

    calls: list[tuple[str, str, dict[str, Any] | None]] = []

    class DummyClient:
        def __init__(self, *_: Any, **__: Any) -> None:
            pass

        def request(self, method: str, path: str, json_body: dict[str, Any] | None = None):
            calls.append((method, path, json_body))
            return DummyResponse({"status": "done"})

        def close(self) -> None:
            return None

    with patch.object(system, "DaemonClient", DummyClient):
        system.system_permissions_grant(
            "com.example.app",
            "android.permission.POST_NOTIFICATIONS",
            device=None,
            session_id="s-abc123",
            json_output=False,
        )

    assert calls[0] == (
        "POST",
        "/system/permissions/grant",
        {
            "session_id": "s-abc123",
            "package": "com.example.app",
            "permission": "android.permission.POST_NOTIFICATIONS",
        },
    )


def test_system_permissions_list_builds_payload() -> None:
    """Should send permission list payload to the daemon."""
    from android_emu_agent.cli.commands import system

    calls: list[tuple[str, str, dict[str, Any] | None]] = []

    class DummyClient:
        def __init__(self, *_: Any, **__: Any) -> None:
            pass

        def request(self, method: str, path: str, json_body: dict[str, Any] | None = None):
            calls.append((method, path, json_body))
            return DummyResponse({"status": "done", "output": "ok"})

        def close(self) -> None:
            return None

    with patch.object(system, "DaemonClient", DummyClient):
        system.system_permissions_list(
            "com.example.app",
            device="emulator-5554",
            session_id=None,
            json_output=False,
        )

    assert calls[0] == (
        "POST",
        "/system/permissions/list",
        {"serial": "emulator-5554", "package": "com.example.app"},
    )
