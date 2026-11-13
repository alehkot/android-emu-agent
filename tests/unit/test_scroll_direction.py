"""Scroll names where the view moves; swipe names where the finger moves."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from android_emu_agent.cli.commands import action


@pytest.mark.parametrize(
    ("scroll", "swipe"),
    [
        ("down", "up"),
        ("up", "down"),
        ("right", "left"),
        ("left", "right"),
        ("diagonal", "diagonal"),
    ],
)
def test_scroll_sends_the_opposite_swipe(scroll: str, swipe: str) -> None:
    """'scroll down' reveals lower content, so the finger swipes up."""
    bodies: list[dict[str, Any]] = []

    class Response:
        def json(self) -> dict[str, Any]:
            return {"status": "done"}

    class Client:
        def request(self, _method: str, path: str, json_body: dict[str, Any]) -> Response:
            assert path == "/actions/swipe"
            bodies.append(json_body)
            return Response()

        def close(self) -> None:
            return None

    with patch.object(action, "DaemonClient", Client):
        action.action_scroll(
            scroll, session="s-abc123", container=None, distance=0.8, json_output=True
        )

    assert bodies == [
        {
            "session_id": "s-abc123",
            "direction": swipe,
            "container": None,
            "distance": 0.8,
            "duration_ms": 300,
        }
    ]
