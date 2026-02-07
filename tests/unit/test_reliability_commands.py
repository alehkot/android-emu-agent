"""Tests for reliability-related CLI commands."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch


class DummyResponse:
    """Simple response stub for CLI handlers."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def json(self) -> dict[str, Any]:
        return self._payload


def test_reliability_process_builds_payload() -> None:
    """Should send process payload to the daemon."""
    from android_emu_agent.cli.commands import reliability

    calls: list[tuple[str, str, dict[str, Any] | None]] = []

    class DummyClient:
        def __init__(self, *_: Any, **__: Any) -> None:
            pass

        def request(self, method: str, path: str, json_body: dict[str, Any] | None = None):
            calls.append((method, path, json_body))
            return DummyResponse({"status": "done", "output": "ok"})

        def close(self) -> None:
            return None

    with patch.object(reliability, "DaemonClient", DummyClient):
        reliability.reliability_process(
            "com.example.app",
            device="emulator-5554",
            session_id=None,
            json_output=False,
        )

    method, path, payload = calls[0]
    assert method == "POST"
    assert path == "/reliability/process"
    assert payload == {"serial": "emulator-5554", "package": "com.example.app"}


def test_reliability_meminfo_builds_payload() -> None:
    """Should send meminfo payload to the daemon."""
    from android_emu_agent.cli.commands import reliability

    calls: list[tuple[str, str, dict[str, Any] | None]] = []

    class DummyClient:
        def __init__(self, *_: Any, **__: Any) -> None:
            pass

        def request(self, method: str, path: str, json_body: dict[str, Any] | None = None):
            calls.append((method, path, json_body))
            return DummyResponse({"status": "done", "output": "ok"})

        def close(self) -> None:
            return None

    with patch.object(reliability, "DaemonClient", DummyClient):
        reliability.reliability_meminfo(
            "com.example.app",
            device="emulator-5554",
            session_id=None,
            json_output=False,
        )

    method, path, payload = calls[0]
    assert method == "POST"
    assert path == "/reliability/meminfo"
    assert payload == {"serial": "emulator-5554", "package": "com.example.app"}


def test_reliability_gfxinfo_builds_payload() -> None:
    """Should send gfxinfo payload to the daemon."""
    from android_emu_agent.cli.commands import reliability

    calls: list[tuple[str, str, dict[str, Any] | None]] = []

    class DummyClient:
        def __init__(self, *_: Any, **__: Any) -> None:
            pass

        def request(self, method: str, path: str, json_body: dict[str, Any] | None = None):
            calls.append((method, path, json_body))
            return DummyResponse({"status": "done", "output": "ok"})

        def close(self) -> None:
            return None

    with patch.object(reliability, "DaemonClient", DummyClient):
        reliability.reliability_gfxinfo(
            "com.example.app",
            device="emulator-5554",
            session_id=None,
            json_output=False,
        )

    method, path, payload = calls[0]
    assert method == "POST"
    assert path == "/reliability/gfxinfo"
    assert payload == {"serial": "emulator-5554", "package": "com.example.app"}

