"""Tests for daemon transport retry safety."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock, patch

import httpx
import pytest

from android_emu_agent.cli import daemon_client
from android_emu_agent.cli.daemon_client import DaemonClient, DaemonController


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


def _controller(socket_path: Path) -> DaemonController:
    controller = object.__new__(DaemonController)
    controller.socket_path = socket_path
    return controller


def test_stop_refuses_pid_not_serving_daemon_socket(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A reused PID must never receive the daemon's termination signal."""
    pid_file = tmp_path / "daemon.pid"
    pid_file.write_text("4242", encoding="utf-8")
    monkeypatch.setattr(daemon_client, "PID_FILE", pid_file)
    controller = _controller(tmp_path / "daemon.sock")
    monkeypatch.setattr(controller, "_pid_running", lambda _pid: True)
    monkeypatch.setattr(controller, "_socket_health", lambda: {"pid": 9898})

    with patch.object(daemon_client.os, "kill") as kill:
        assert controller.stop() is False

    kill.assert_not_called()
    assert pid_file.read_text(encoding="utf-8") == "4242"


def test_start_does_not_treat_live_unowned_pid_as_daemon(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A stale reused PID should not prevent a daemon from starting."""
    pid_file = tmp_path / "daemon.pid"
    pid_file.write_text("4242", encoding="utf-8")
    monkeypatch.setattr(daemon_client, "PID_FILE", pid_file)
    monkeypatch.setattr(daemon_client, "LOG_FILE", tmp_path / "daemon.log")
    controller = _controller(tmp_path / "daemon.sock")
    monkeypatch.setattr(controller, "_pid_running", lambda _pid: True)
    monkeypatch.setattr(controller, "_pid_matches_daemon", lambda _pid: False)
    monkeypatch.setattr(controller, "_socket_healthy", lambda: False)
    monkeypatch.setattr(controller, "_wait_for_secure_socket", Mock())
    process = Mock(pid=5151)

    with patch.object(daemon_client.subprocess, "Popen", return_value=process):
        assert controller.start() == 5151

    assert pid_file.read_text(encoding="utf-8") == "5151"
