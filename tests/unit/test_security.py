"""Tests for owner-only daemon state permissions."""

from __future__ import annotations

import socket
import stat
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from android_emu_agent.cli import daemon_client
from android_emu_agent.cli.daemon_client import DaemonController
from android_emu_agent.db.models import Database
from android_emu_agent.security import PERMISSIONS_MARKER, secure_private_tree


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_secure_private_tree_migrates_existing_permissions(tmp_path: Path) -> None:
    """Existing daemon state should be migrated to owner-only access."""
    state_dir = tmp_path / "state"
    nested_dir = state_dir / "diagnostics"
    nested_dir.mkdir(parents=True, mode=0o755)
    state_file = nested_dir / "requests.ndjson"
    state_file.write_text("sensitive\n", encoding="utf-8")
    state_dir.chmod(0o755)
    nested_dir.chmod(0o755)
    state_file.chmod(0o644)

    secure_private_tree(state_dir)

    assert _mode(state_dir) == 0o700
    assert _mode(nested_dir) == 0o700
    assert _mode(state_file) == 0o600


def test_daemon_controller_restricts_existing_socket(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A daemon socket should be owner-only before the client connects."""
    state_dir = tmp_path / "state"
    monkeypatch.setattr(daemon_client, "STATE_DIR", state_dir)

    with tempfile.TemporaryDirectory(prefix="aea-sock-", dir="/tmp") as socket_dir:
        socket_path = Path(socket_dir) / "daemon.sock"
        server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            server_socket.bind(str(socket_path))
            socket_path.chmod(0o666)

            DaemonController(socket_path)

            assert _mode(socket_path) == 0o600
            assert _mode(state_dir / PERMISSIONS_MARKER) == 0o600
        finally:
            server_socket.close()


def test_daemon_start_creates_private_control_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Daemon startup should use a restrictive umask and private PID/log files."""
    state_dir = tmp_path / "state"
    socket_path = tmp_path / "daemon.sock"
    monkeypatch.setattr(daemon_client, "STATE_DIR", state_dir)
    monkeypatch.setattr(daemon_client, "PID_FILE", state_dir / "daemon.pid")
    monkeypatch.setattr(daemon_client, "LOG_FILE", state_dir / "daemon.log")
    controller = DaemonController(socket_path)
    monkeypatch.setattr(controller, "_socket_healthy", lambda: False)
    wait_for_secure_socket = Mock()
    monkeypatch.setattr(controller, "_wait_for_secure_socket", wait_for_secure_socket)

    process = SimpleNamespace(pid=12345)
    with patch.object(
        daemon_client.subprocess,
        "Popen",
        return_value=process,
    ) as popen:
        assert controller.start() == 12345

    assert popen.call_args.kwargs["umask"] == 0o077
    wait_for_secure_socket.assert_called_once_with(process)
    assert _mode(daemon_client.LOG_FILE) == 0o600
    assert _mode(daemon_client.PID_FILE) == 0o600


@pytest.mark.asyncio
async def test_database_creates_private_state(tmp_path: Path) -> None:
    """SQLite state should not be readable by other local users."""
    db_path = tmp_path / "state" / "state.db"
    database = Database(db_path)

    await database.connect()
    try:
        assert _mode(db_path.parent) == 0o700
        assert _mode(db_path) == 0o600
    finally:
        await database.disconnect()
