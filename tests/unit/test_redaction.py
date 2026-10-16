"""Tests for persisted diagnostics and trace redaction."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest

from android_emu_agent.daemon.diagnostics import RequestDiagnostics
from android_emu_agent.redaction import REDACTED, redact_sensitive_data
from android_emu_agent.tasks import TaskManager
from android_emu_agent.tracing.manager import TraceManager


def test_set_text_request_redacts_typed_input() -> None:
    """Text sent to an input element should never be persisted."""
    event = {
        "path": "/actions/set_text",
        "request": {"session_id": "s-123", "ref": "^a1", "text": "audit-secret"},
        "response": {"status": "done"},
    }

    redacted = redact_sensitive_data(event)

    assert redacted["request"]["text"] == REDACTED
    assert redacted["request"]["ref"] == "^a1"


def test_task_set_text_and_script_are_redacted() -> None:
    """Task wrappers should not bypass typed-input redaction."""
    task_event = {
        "path": "/tasks/run",
        "request": {
            "task": {
                "steps": [
                    {"action": "set_text", "ref": "^a1", "text": "audit-secret"},
                    {"action": "tap", "ref": "^a2"},
                ]
            }
        },
    }
    script_event = {
        "path": "/tasks/script/run",
        "request": {"script": "set-text ^a1 audit-secret"},
    }

    redacted_task = redact_sensitive_data(task_event)
    redacted_script = redact_sensitive_data(script_event)

    assert redacted_task["request"]["task"]["steps"][0]["text"] == REDACTED
    assert redacted_task["request"]["task"]["steps"][1]["ref"] == "^a2"
    assert redacted_script["request"]["script"] == REDACTED


def test_uri_credentials_and_sensitive_parameters_are_redacted() -> None:
    """Credentials in URI authority, query, and fragment components should be removed."""
    uri = "myapp://user:password@example/path?screen=home&token=audit-secret#code=oauth-code"

    redacted = redact_sensitive_data(uri)
    parsed = urlsplit(redacted)

    assert parsed.netloc == f"user:{REDACTED}@example"
    assert parse_qs(parsed.query) == {"screen": ["home"], "token": [REDACTED]}
    assert parse_qs(parsed.fragment) == {"code": [REDACTED]}
    assert "audit-secret" not in redacted
    assert "oauth-code" not in redacted


def test_non_sensitive_text_and_uri_are_preserved() -> None:
    """Redaction should retain useful non-sensitive diagnostic context."""
    event = {
        "path": "/wait/text",
        "request": {
            "text": "Settings",
            "uri": "myapp://screen?tab=profile&design=compact&postcode=12345",
        },
    }

    assert redact_sensitive_data(event) == event


TASK_SET_TEXT_FORMS = [
    pytest.param({"action": "set_text"}, id="action-shorthand"),
    pytest.param({"kind": "action", "operation": "set_text"}, id="operation"),
    pytest.param({"kind": "action", "op": "set_text"}, id="op-alias"),
    pytest.param({"kind": "action", "operation": "", "op": "set_text"}, id="empty-operation"),
    pytest.param({"kind": "action", "operation": None, "op": "set_text"}, id="null-operation"),
    pytest.param({"kind": "action", "operation": 123, "op": "set_text"}, id="non-string-operation"),
    pytest.param(
        {"kind": "action", "operation": "set_text", "op": "tap"}, id="operation-precedence"
    ),
]


@pytest.mark.parametrize("syntax", TASK_SET_TEXT_FORMS)
@pytest.mark.asyncio
async def test_task_input_aliases_are_redacted_before_persistence(
    tmp_path: Path, syntax: dict[str, Any]
) -> None:
    """Every accepted set_text syntax must redact both persisted diagnostic formats."""
    secret = "private-example-123"
    step = {**syntax, "ref": "^a1", "text": secret}
    task = {"steps": [step]}
    assert TaskManager().validate(task)["steps"][0]["operation"] == "set_text"
    request = {"session_id": "s-123", "task": task}
    event = {"path": "/tasks/run", "request": request}

    redacted = redact_sensitive_data(event)
    expected_step = {**step, "text": REDACTED}
    assert redacted["request"]["task"]["steps"][0] == expected_step
    assert step["text"] == secret  # Logging must not mutate the operation to execute.

    diagnostics = RequestDiagnostics(tmp_path / "diagnostics")
    await diagnostics.record(event)
    diagnostic_text = diagnostics.path.read_text(encoding="utf-8")
    assert secret not in diagnostic_text
    assert json.loads(diagnostic_text)["request"]["task"]["steps"][0] == expected_step

    traces = TraceManager(tmp_path / "traces")
    await traces.start("s-123")
    await traces.record_daemon_exchange(
        session_id="s-123",
        diagnostic_id="diag-123",
        method="POST",
        path="/tasks/run",
        status_code=200,
        elapsed_ms=1.0,
        request_payload=request,
        response_payload={"status": "done"},
    )
    stopped = await traces.stop("s-123")
    with zipfile.ZipFile(stopped["path"]) as archive:
        assert all(secret.encode() not in archive.read(name) for name in archive.namelist())
    exchange = traces.load_events(stopped["path"])[1]
    assert exchange["request"]["task"]["steps"][0] == expected_step
    assert step["text"] == secret


@pytest.mark.parametrize("operation_key", ["operation", "op"])
def test_task_wait_text_aliases_remain_readable(operation_key: str) -> None:
    """Non-input operations retain useful text even when using explicit aliases."""
    task = {"steps": [{"kind": "wait", operation_key: "text", "text": "Settings"}]}
    TaskManager().validate(task)
    assert redact_sensitive_data(task) == task


@pytest.mark.parametrize(
    "syntax",
    [
        {"kind": "action", "operation": "tap", "op": "set_text"},
        {"action": "tap", "kind": "action", "op": "set_text"},
        {"action": "tap", "operation": "set_text"},
        {"action": "set_text", "operation": "tap"},
    ],
)
def test_conflicting_task_aliases_are_redacted_conservatively(syntax: dict[str, str]) -> None:
    """Ignored aliases and invalid requests must not expose supplied input in error logs."""
    step = {**syntax, "ref": "^a1", "text": "private-example-123"}
    assert redact_sensitive_data(step) == {**step, "text": REDACTED}
    assert step["text"] == "private-example-123"
