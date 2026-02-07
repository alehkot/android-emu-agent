"""Tests for artifact-related CLI commands."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch


class DummyResponse:
    """Simple response stub for CLI handlers."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def json(self) -> dict[str, Any]:
        return self._payload


def test_artifact_logs_builds_payload_with_filters() -> None:
    """Should send logs payload with package/level/follow filters."""
    from android_emu_agent.cli.commands import artifact

    calls: list[tuple[str, str, dict[str, Any] | None, float | None]] = []

    class DummyClient:
        def __init__(self, *_: Any, timeout: float = 10.0, **__: Any) -> None:
            self.timeout = timeout

        def request(self, method: str, path: str, json_body: dict[str, Any] | None = None):
            calls.append((method, path, json_body, self.timeout))
            return DummyResponse({"status": "done", "path": "/tmp/logcat.txt"})

        def close(self) -> None:
            return None

    with patch.object(artifact, "DaemonClient", DummyClient):
        artifact.artifact_logs(
            session_id=None,
            session="s-abc123",
            package="com.example.app",
            level="error",
            since="10m",
            follow=True,
            json_output=False,
        )

    method, path, payload, timeout = calls[0]
    assert method == "POST"
    assert path == "/artifacts/logs"
    assert timeout == 3600.0
    assert payload == {
        "session_id": "s-abc123",
        "package": "com.example.app",
        "level": "error",
        "since": "10m",
        "follow": True,
    }

