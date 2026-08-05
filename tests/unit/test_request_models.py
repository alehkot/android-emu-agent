"""Tests for daemon request schema strictness."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from android_emu_agent.daemon.models import FileFindRequest, TaskValidateRequest


class DummyCore:
    """Minimal daemon core for request-validation tests."""

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None


@contextmanager
def _client() -> Any:
    from android_emu_agent.daemon import server

    with patch.object(server, "DaemonCore", DummyCore), TestClient(server.app) as client:
        yield client


def test_request_model_rejects_unknown_field() -> None:
    """Inherited request models should reject misspelled top-level keys."""
    with pytest.raises(ValidationError) as exc_info:
        FileFindRequest.model_validate(
            {
                "serial": "emulator-5554",
                "path": "/sdcard",
                "name": "*.db",
                "max_dept": 3,
            }
        )

    error = exc_info.value.errors()[0]
    assert error["type"] == "extra_forbidden"
    assert error["loc"] == ("max_dept",)


def test_endpoint_returns_422_for_unknown_request_field() -> None:
    """FastAPI should expose strict model validation before endpoint dispatch."""
    with _client() as client:
        response = client.post(
            "/wait/idle",
            json={"session_id": "s-abc123", "timeot_ms": 500},
        )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail[0]["type"] == "extra_forbidden"
    assert detail[0]["loc"] == ["body", "timeot_ms"]


def test_free_form_task_payload_remains_extensible() -> None:
    """Strict request envelopes should not restrict the documented free-form task object."""
    request = TaskValidateRequest.model_validate(
        {"task": {"steps": [{"future_operation": "value"}]}}
    )

    assert request.task["steps"] == [{"future_operation": "value"}]
