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


def test_reliability_profile_builds_payload() -> None:
    """Should send profile payload to the daemon."""
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
        reliability.reliability_profile(
            "com.example.app",
            device=None,
            session_id="s-abc123",
            since="100",
            include_raw=True,
            json_output=False,
        )

    method, path, payload = calls[0]
    assert method == "POST"
    assert path == "/reliability/profile"
    assert payload == {
        "session_id": "s-abc123",
        "package": "com.example.app",
        "since": "100",
        "include_raw": True,
    }


def test_reliability_perfetto_builds_payload() -> None:
    """Should send perfetto payload to the daemon."""
    from android_emu_agent.cli.commands import reliability

    calls: list[tuple[str, str, dict[str, Any] | None]] = []

    class DummyClient:
        def __init__(self, *_: Any, **__: Any) -> None:
            pass

        def request(self, method: str, path: str, json_body: dict[str, Any] | None = None):
            calls.append((method, path, json_body))
            return DummyResponse({"status": "done", "path": "/tmp/trace.perfetto-trace"})

        def close(self) -> None:
            return None

    with patch.object(reliability, "DaemonClient", DummyClient):
        reliability.reliability_perfetto(
            device="emulator-5554",
            session_id=None,
            duration=7,
            categories="sched gfx",
            output="trace.perfetto-trace",
            json_output=False,
        )

    assert calls[0] == (
        "POST",
        "/reliability/perfetto",
        {
            "serial": "emulator-5554",
            "duration_seconds": 7,
            "categories": "sched gfx",
            "filename": "trace.perfetto-trace",
        },
    )


def test_reliability_simpleperf_builds_payload() -> None:
    """Should send simpleperf payload to the daemon."""
    from android_emu_agent.cli.commands import reliability

    calls: list[tuple[str, str, dict[str, Any] | None]] = []

    class DummyClient:
        def __init__(self, *_: Any, **__: Any) -> None:
            pass

        def request(self, method: str, path: str, json_body: dict[str, Any] | None = None):
            calls.append((method, path, json_body))
            return DummyResponse({"status": "done", "path": "/tmp/profile.data"})

        def close(self) -> None:
            return None

    with patch.object(reliability, "DaemonClient", DummyClient):
        reliability.reliability_simpleperf(
            "com.example.app",
            device=None,
            session_id="s-abc123",
            duration=4,
            output="profile.data",
            json_output=False,
        )

    assert calls[0] == (
        "POST",
        "/reliability/simpleperf",
        {
            "session_id": "s-abc123",
            "package": "com.example.app",
            "duration_seconds": 4,
            "filename": "profile.data",
        },
    )


def test_reliability_screenrecord_builds_payload() -> None:
    """Should send screenrecord payload to the daemon."""
    from android_emu_agent.cli.commands import reliability

    calls: list[tuple[str, str, dict[str, Any] | None]] = []

    class DummyClient:
        def __init__(self, *_: Any, **__: Any) -> None:
            pass

        def request(self, method: str, path: str, json_body: dict[str, Any] | None = None):
            calls.append((method, path, json_body))
            return DummyResponse({"status": "done", "path": "/tmp/recording.mp4"})

        def close(self) -> None:
            return None

    with patch.object(reliability, "DaemonClient", DummyClient):
        reliability.reliability_screenrecord(
            device="emulator-5554",
            session_id=None,
            duration=6,
            bit_rate=4_000_000,
            output="recording.mp4",
            json_output=False,
        )

    assert calls[0] == (
        "POST",
        "/reliability/screenrecord",
        {
            "serial": "emulator-5554",
            "duration_seconds": 6,
            "bit_rate": 4_000_000,
            "filename": "recording.mp4",
        },
    )
