"""Tests for wait CLI selector payloads."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch


class DummyResponse:
    """Simple response stub for CLI handlers."""

    def json(self) -> dict[str, Any]:
        return {"status": "done"}


def test_wait_exists_builds_rich_selector_payload() -> None:
    """Wait command should expose the richer selector keys."""
    from android_emu_agent.cli.commands import wait

    calls: list[tuple[str, str, dict[str, Any] | None]] = []

    class DummyClient:
        def __init__(self, *_: Any, **__: Any) -> None:
            pass

        def request(self, method: str, path: str, json_body: dict[str, Any] | None = None):
            calls.append((method, path, json_body))
            return DummyResponse()

        def close(self) -> None:
            return None

    with patch.object(wait, "DaemonClient", DummyClient):
        wait.wait_exists(
            "s-abc123",
            ref=None,
            text=None,
            text_contains="Checkout",
            resource_id=None,
            resource_id_matches=".*checkout.*",
            desc=None,
            desc_contains="Pay",
            class_name="android.widget.Button",
            timeout_ms=500,
            json_output=False,
        )

    assert calls[0] == (
        "POST",
        "/wait/exists",
        {
            "session_id": "s-abc123",
            "ref": None,
            "selector": {
                "textContains": "Checkout",
                "resourceIdMatches": ".*checkout.*",
                "descriptionContains": "Pay",
                "className": "android.widget.Button",
            },
            "timeout_ms": 500,
        },
    )
