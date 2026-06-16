"""Tests for expectation CLI command payload wiring."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch


class DummyResponse:
    """Simple response stub for CLI handlers."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def json(self) -> dict[str, Any]:
        return self._payload


def test_expect_text_builds_payload() -> None:
    """Should send text expectation payload to the daemon."""
    from android_emu_agent.cli.commands import expect

    calls: list[tuple[str, str, dict[str, Any] | None]] = []

    class DummyClient:
        def __init__(self, *_: Any, **__: Any) -> None:
            pass

        def request(self, method: str, path: str, json_body: dict[str, Any] | None = None):
            calls.append((method, path, json_body))
            return DummyResponse({"status": "done"})

        def close(self) -> None:
            return None

    with patch.object(expect, "DaemonClient", DummyClient):
        expect.expect_text("s-abc123", "Ready", timeout_ms=500, json_output=False)

    assert calls[0] == (
        "POST",
        "/expect/text",
        {"session_id": "s-abc123", "text": "Ready", "timeout_ms": 500},
    )


def test_expect_exists_builds_selector_payload() -> None:
    """Should translate selector options into a selector dict."""
    from android_emu_agent.cli.commands import expect

    calls: list[tuple[str, str, dict[str, Any] | None]] = []

    class DummyClient:
        def __init__(self, *_: Any, **__: Any) -> None:
            pass

        def request(self, method: str, path: str, json_body: dict[str, Any] | None = None):
            calls.append((method, path, json_body))
            return DummyResponse({"status": "done"})

        def close(self) -> None:
            return None

    with patch.object(expect, "DaemonClient", DummyClient):
        expect.expect_exists(
            "s-abc123",
            ref=None,
            text="Checkout",
            text_contains="Check",
            resource_id="checkout_button",
            resource_id_matches=".*checkout.*",
            desc=None,
            desc_contains="Pay",
            class_name="android.widget.Button",
            timeout_ms=1000,
            json_output=False,
        )

    assert calls[0] == (
        "POST",
        "/expect/exists",
        {
            "session_id": "s-abc123",
            "ref": None,
            "selector": {
                "text": "Checkout",
                "textContains": "Check",
                "resourceId": "checkout_button",
                "resourceIdMatches": ".*checkout.*",
                "descriptionContains": "Pay",
                "className": "android.widget.Button",
            },
            "timeout_ms": 1000,
        },
    )


def test_expect_current_app_builds_payload() -> None:
    """Should send current-app expectation payload to the daemon."""
    from android_emu_agent.cli.commands import expect

    calls: list[tuple[str, str, dict[str, Any] | None]] = []

    class DummyClient:
        def __init__(self, *_: Any, **__: Any) -> None:
            pass

        def request(self, method: str, path: str, json_body: dict[str, Any] | None = None):
            calls.append((method, path, json_body))
            return DummyResponse({"status": "done"})

        def close(self) -> None:
            return None

    with patch.object(expect, "DaemonClient", DummyClient):
        expect.expect_current_app(
            "s-abc123",
            package="com.example",
            activity="MainActivity",
            json_output=False,
        )

    assert calls[0] == (
        "POST",
        "/expect/current_app",
        {"session_id": "s-abc123", "package": "com.example", "activity": "MainActivity"},
    )
