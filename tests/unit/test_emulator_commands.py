"""Tests for emulator CLI commands."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch


class DummyResponse:
    """Simple response stub for CLI handlers."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def json(self) -> dict[str, Any]:
        return self._payload


def test_emulator_snapshot_save_builds_payload() -> None:
    """Should send snapshot save payload to the daemon."""
    from android_emu_agent.cli.commands import emulator

    calls: list[tuple[str, str, dict[str, Any] | None]] = []

    class DummyClient:
        def __init__(self, *_: Any, **__: Any) -> None:
            pass

        def request(self, method: str, path: str, json_body: dict[str, Any] | None = None):
            calls.append((method, path, json_body))
            return DummyResponse({"status": "done"})

        def close(self) -> None:
            return None

    with patch.object(emulator, "DaemonClient", DummyClient):
        emulator.emulator_snapshot_save(
            "emulator-5554",
            "baseline",
            json_output=False,
        )

    method, path, payload = calls[0]
    assert method == "POST"
    assert path == "/emulator/snapshot_save"
    assert payload == {"serial": "emulator-5554", "name": "baseline"}


def test_emulator_list_avds_requests_daemon() -> None:
    """Should request AVDs from the daemon."""
    from android_emu_agent.cli.commands import emulator

    calls: list[tuple[str, str, dict[str, Any] | None]] = []

    class DummyClient:
        def __init__(self, *_: Any, **__: Any) -> None:
            pass

        def request(self, method: str, path: str, json_body: dict[str, Any] | None = None):
            calls.append((method, path, json_body))
            return DummyResponse({"status": "done", "avds": ["Pixel_8_API_34"]})

        def close(self) -> None:
            return None

    with patch.object(emulator, "DaemonClient", DummyClient):
        emulator.emulator_list_avds(json_output=False)

    method, path, payload = calls[0]
    assert method == "GET"
    assert path == "/emulator/avds"
    assert payload is None


def test_emulator_start_builds_payload_with_options() -> None:
    """Should send emulator start options to the daemon."""
    from android_emu_agent.cli.commands import emulator

    calls: list[tuple[str, str, dict[str, Any] | None, float]] = []

    class DummyClient:
        def __init__(self, *_: Any, timeout: float = 10.0, **__: Any) -> None:
            self.timeout = timeout

        def request(self, method: str, path: str, json_body: dict[str, Any] | None = None):
            calls.append((method, path, json_body, self.timeout))
            return DummyResponse({"status": "done", "serial": "emulator-5554"})

        def close(self) -> None:
            return None

    with patch.object(emulator, "DaemonClient", DummyClient):
        emulator.emulator_start(
            "Pixel_8_API_34",
            snapshot="clean",
            wipe_data=False,
            cold_boot=False,
            no_snapshot_save=True,
            read_only=True,
            no_window=True,
            port=5554,
            wait_boot=True,
            json_output=False,
        )

    method, path, payload, timeout = calls[0]
    assert method == "POST"
    assert path == "/emulator/start"
    assert timeout == 240.0
    assert payload == {
        "avd_name": "Pixel_8_API_34",
        "snapshot": "clean",
        "wipe_data": False,
        "cold_boot": False,
        "no_snapshot_save": True,
        "read_only": True,
        "no_window": True,
        "port": 5554,
        "wait_boot": True,
    }


def test_emulator_stop_builds_payload() -> None:
    """Should send emulator stop payload with extended timeout."""
    from android_emu_agent.cli.commands import emulator

    calls: list[tuple[str, str, dict[str, Any] | None, float]] = []

    class DummyClient:
        def __init__(self, *_: Any, timeout: float = 10.0, **__: Any) -> None:
            self.timeout = timeout

        def request(self, method: str, path: str, json_body: dict[str, Any] | None = None):
            calls.append((method, path, json_body, self.timeout))
            return DummyResponse({"status": "done"})

        def close(self) -> None:
            return None

    with patch.object(emulator, "DaemonClient", DummyClient):
        emulator.emulator_stop("emulator-5554", json_output=False)

    method, path, payload, timeout = calls[0]
    assert method == "POST"
    assert path == "/emulator/stop"
    assert timeout == 60.0
    assert payload == {"serial": "emulator-5554"}


def test_emulator_snapshot_restore_builds_restart_payload() -> None:
    """Should request a restart-backed snapshot restore by default."""
    from android_emu_agent.cli.commands import emulator

    calls: list[tuple[str, str, dict[str, Any] | None, float]] = []

    class DummyClient:
        def __init__(self, *_: Any, timeout: float = 10.0, **__: Any) -> None:
            self.timeout = timeout

        def request(self, method: str, path: str, json_body: dict[str, Any] | None = None):
            calls.append((method, path, json_body, self.timeout))
            return DummyResponse({"status": "done"})

        def close(self) -> None:
            return None

    with patch.object(emulator, "DaemonClient", DummyClient):
        emulator.emulator_snapshot_restore(
            "emulator-5554",
            "baseline",
            restart=True,
            json_output=False,
        )

    method, path, payload, timeout = calls[0]
    assert method == "POST"
    assert path == "/emulator/snapshot_restore"
    assert timeout == 180.0
    assert payload == {"serial": "emulator-5554", "name": "baseline", "restart": True}
