"""Tests for daemon lifecycle CLI safeguards."""

from __future__ import annotations

from unittest.mock import Mock, patch

import pytest
import typer

from android_emu_agent.cli.commands import daemon


def test_stop_refuses_unverified_pid(capsys: pytest.CaptureFixture[str]) -> None:
    """The CLI should explain why it refuses to signal an unowned PID."""
    controller = Mock()
    controller.status.return_value = {
        "pid": 4242,
        "pid_running": True,
        "pid_matches_daemon": False,
    }

    with (
        patch.object(daemon, "DaemonController", return_value=controller),
        pytest.raises(typer.Exit) as exc_info,
    ):
        daemon.daemon_stop()

    assert exc_info.value.exit_code == 1
    assert "ERR_DAEMON_IDENTITY" in capsys.readouterr().err
    controller.stop.assert_not_called()


def test_start_checks_verified_daemon_identity(capsys: pytest.CaptureFixture[str]) -> None:
    """A reused raw PID should not short-circuit normal daemon startup."""
    controller = Mock()
    controller.status.return_value = {
        "pid": 4242,
        "pid_running": True,
        "pid_matches_daemon": False,
    }
    controller.health.return_value = False
    controller.start.return_value = 5151

    with patch.object(daemon, "DaemonController", return_value=controller):
        daemon.daemon_start()

    assert capsys.readouterr().out == "Daemon started (pid 5151)\n"
    controller.start.assert_called_once_with()
