"""Daemon startup must not report readiness after an exit or health deadline."""

from __future__ import annotations

from unittest.mock import Mock

import httpx
import pytest
from typer.testing import CliRunner

from android_emu_agent.cli import daemon_client
from android_emu_agent.cli.commands import daemon
from android_emu_agent.cli.daemon_client import DaemonClient, DaemonController
from android_emu_agent.errors import AgentError


@pytest.fixture
def startup(monkeypatch, tmp_path):
    controller = object.__new__(DaemonController)
    controller.socket_path = tmp_path / "daemon.sock"
    process = Mock(pid=5151)
    process.poll.return_value = None
    pid_file = tmp_path / "daemon.pid"
    monkeypatch.setattr(daemon_client, "PID_FILE", pid_file)
    monkeypatch.setattr(daemon_client, "LOG_FILE", tmp_path / "daemon.log")
    monkeypatch.setattr(daemon_client.subprocess, "Popen", Mock(return_value=process))
    monkeypatch.setattr(controller, "_socket_healthy", Mock(return_value=False))
    monkeypatch.setattr(daemon, "DaemonController", Mock(return_value=controller))
    monkeypatch.setattr(daemon_client.time, "sleep", Mock())
    return controller, process, pid_file


@pytest.mark.parametrize("exit_code", [0, 1, -9])
def test_start_exited_child_reports_failure(startup, exit_code):
    _controller, process, pid_file = startup
    process.poll.return_value = exit_code
    result = CliRunner().invoke(daemon.app, ["start"])
    assert result.exit_code == 1, result.output
    assert result.stdout == ""
    assert "ERR_DAEMON_START_FAILED" in result.stderr
    assert f"exit code {exit_code}" in result.stderr
    assert "daemon.log" in result.stderr
    assert "Daemon started" not in result.output
    assert pid_file.read_text() == "5151"
    process.terminate.assert_not_called()
    process.kill.assert_not_called()


def test_start_health_deadline_is_not_success_or_cancellation(startup, monkeypatch):
    _controller, process, pid_file = startup
    monkeypatch.setattr(daemon_client.time, "monotonic", Mock(side_effect=[0, 0, 6]))
    result = CliRunner().invoke(daemon.app, ["start"])
    assert result.exit_code == 1, result.output
    assert result.stdout == ""
    assert "ERR_DAEMON_START_FAILED" in result.stderr
    assert "did not become healthy" in result.stderr
    assert "daemon status" in result.stderr
    assert "Daemon started" not in result.output
    assert pid_file.read_text() == "5151"
    process.terminate.assert_not_called()
    process.kill.assert_not_called()


@pytest.mark.parametrize("delayed", [False, True])
def test_start_reports_success_only_after_health(startup, delayed):
    controller, process, pid_file = startup
    controller._socket_healthy.side_effect = [False, False] + ([False] if delayed else []) + [True]
    result = CliRunner().invoke(daemon.app, ["start"])
    assert result.exit_code == 0, result.output
    assert result.stdout == "Daemon started (pid 5151)\n"
    assert result.stderr == ""
    assert pid_file.read_text() == "5151"
    process.terminate.assert_not_called()
    process.kill.assert_not_called()


@pytest.mark.parametrize("known_pid", [False, True])
def test_start_existing_healthy_daemon_remains_success(monkeypatch, known_pid):
    controller = Mock()
    controller.status.return_value = {"pid_matches_daemon": known_pid, "pid": 4242}
    controller.health.return_value = True
    monkeypatch.setattr(daemon, "DaemonController", Mock(return_value=controller))
    result = CliRunner().invoke(daemon.app, ["start"])
    assert result.exit_code == 0, result.output
    expected = "pid 4242" if known_pid else "pid unknown"
    assert result.stdout == f"Daemon already running ({expected})\n"
    controller.start.assert_not_called()


def test_start_race_already_running_remains_success(monkeypatch):
    controller = Mock()
    controller.status.return_value = {"pid_matches_daemon": False, "pid": None}
    controller.health.return_value = False
    controller.start.return_value = -1
    monkeypatch.setattr(daemon, "DaemonController", Mock(return_value=controller))
    result = CliRunner().invoke(daemon.app, ["start"])
    assert result.exit_code == 0, result.output
    assert result.stdout == "Daemon already running (pid unknown)\n"


@pytest.mark.parametrize("method", ["GET", "POST"])
def test_auto_start_failure_does_not_replay_request(startup, method):
    controller, process, _pid_file = startup
    process.poll.return_value = 1
    client = object.__new__(DaemonClient)
    client.auto_start = True
    client.controller = controller
    client._client = Mock()
    client._client.request.side_effect = httpx.ConnectError("not running")
    client._wait_for_health = Mock()
    with pytest.raises(AgentError) as exc:
        client.request(method, "/devices")
    assert exc.value.code == "ERR_DAEMON_START_FAILED"
    assert exc.value.context["pid"] == 5151
    client._client.request.assert_called_once()
    client._wait_for_health.assert_not_called()
