"""Tests for task CLI command payload wiring."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch


class DummyResponse:
    """Simple response stub for CLI handlers."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def json(self) -> dict[str, Any]:
        return self._payload


def test_task_validate_builds_payload(tmp_path: Path) -> None:
    """Should post task spec to the validation endpoint."""
    from android_emu_agent.cli.commands import task

    task_path = tmp_path / "task.json"
    task_path.write_text(json.dumps({"steps": [{"wait": "idle"}]}), encoding="utf-8")
    calls: list[tuple[str, str, dict[str, Any] | None]] = []

    class DummyClient:
        def __init__(self, *_: Any, **__: Any) -> None:
            pass

        def request(self, method: str, path: str, json_body: dict[str, Any] | None = None):
            calls.append((method, path, json_body))
            return DummyResponse({"status": "done"})

        def close(self) -> None:
            return None

    with patch.object(task, "DaemonClient", DummyClient):
        task.task_validate(str(task_path), json_output=False)

    assert calls[0] == ("POST", "/tasks/validate", {"task": {"steps": [{"wait": "idle"}]}})


def test_task_run_uses_session_override_and_continue_flag(tmp_path: Path) -> None:
    """Should prefer --session and invert continue-on-failure for the daemon."""
    from android_emu_agent.cli.commands import task

    task_payload = {"session_id": "from-file", "steps": [{"wait": "idle"}]}
    task_path = tmp_path / "task.json"
    task_path.write_text(json.dumps(task_payload), encoding="utf-8")
    calls: list[tuple[str, str, dict[str, Any] | None]] = []

    class DummyClient:
        def __init__(self, *_: Any, **__: Any) -> None:
            pass

        def request(self, method: str, path: str, json_body: dict[str, Any] | None = None):
            calls.append((method, path, json_body))
            return DummyResponse({"status": "done"})

        def close(self) -> None:
            return None

    with patch.object(task, "DaemonClient", DummyClient):
        task.task_run(
            str(task_path),
            session="override",
            continue_on_failure=True,
            json_output=False,
        )

    assert calls[0] == (
        "POST",
        "/tasks/run",
        {
            "session_id": "override",
            "task": task_payload,
            "stop_on_failure": False,
        },
    )
