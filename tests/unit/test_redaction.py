"""Tests for persisted diagnostics and trace redaction."""

from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

from android_emu_agent.redaction import REDACTED, redact_sensitive_data


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
