"""Tests for daemon transport retry safety."""

from __future__ import annotations

from unittest.mock import Mock

import httpx
import pytest

from android_emu_agent.cli.daemon_client import DaemonClient


def _client_with_transport(transport_client: Mock) -> tuple[DaemonClient, Mock, Mock]:
    client = object.__new__(DaemonClient)
    client.auto_start = True
    client._client = transport_client
    controller = Mock()
    wait_for_health = Mock()
    client.controller = controller
    client._ensure_ready = Mock()
    client._wait_for_health = wait_for_health
    return client, controller, wait_for_health


def _read_error() -> httpx.ReadError:
    return httpx.ReadError("connection dropped", request=httpx.Request("POST", "http://daemon"))


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_mutating_request_is_not_replayed_after_transport_error(method: str) -> None:
    """An uncertain mutation result must be returned to the caller without replay."""
    transport_client = Mock()
    transport_client.request.side_effect = _read_error()
    client, controller, wait_for_health = _client_with_transport(transport_client)

    with pytest.raises(httpx.ReadError):
        client.request(method, "/actions/tap", json_body={"session_id": "s-1"})

    transport_client.request.assert_called_once()
    controller.start.assert_not_called()
    wait_for_health.assert_not_called()


def test_safe_request_can_retry_after_transport_error() -> None:
    """A read-only request may restart the daemon and retry once."""
    transport_client = Mock()
    expected = httpx.Response(200, json={"status": "ok"})
    transport_client.request.side_effect = [_read_error(), expected]
    client, controller, wait_for_health = _client_with_transport(transport_client)

    response = client.request("GET", "/health")

    assert response is expected
    assert transport_client.request.call_count == 2
    controller.start.assert_called_once_with()
    wait_for_health.assert_called_once_with()
