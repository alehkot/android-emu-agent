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


@pytest.mark.asyncio
async def test_artifact_managers_create_owner_only_storage(tmp_path: Path) -> None:
    """Artifact privacy must not depend on the daemon process umask."""
    from android_emu_agent.artifacts.manager import ArtifactManager
    from android_emu_agent.files.manager import FileManager
    from android_emu_agent.reliability.manager import ReliabilityManager
    from android_emu_agent.visual.manager import VisualGroundingManager

    with patch("pathlib.Path.home", return_value=tmp_path):
        artifact_manager = ArtifactManager()
        ReliabilityManager()
        FileManager()
        VisualGroundingManager()

    snapshot_path = await artifact_manager.save_snapshot("{}", "s-abc123", 1)

    artifact_dir = tmp_path / ".android-emu-agent" / "artifacts"
    assert _mode(artifact_dir) == 0o700
    assert _mode(artifact_dir / "reliability") == 0o700
    assert _mode(artifact_dir / "files") == 0o700
    assert _mode(artifact_dir / "visual") == 0o700
    assert _mode(snapshot_path) == 0o600


class TestDaemonSocketPath:
    """Tests for resolving the socket path the daemon serves."""

    def test_defaults_to_shared_path(self, monkeypatch) -> None:
        """Without an override the CLI and daemon must agree on one path."""
        from android_emu_agent.security import (
            DEFAULT_SOCKET_PATH,
            SOCKET_PATH_ENV,
            daemon_socket_path,
        )

        monkeypatch.delenv(SOCKET_PATH_ENV, raising=False)
        assert daemon_socket_path() == DEFAULT_SOCKET_PATH

    def test_environment_override_is_honoured(self, monkeypatch, tmp_path) -> None:
        """An explicit socket path must win so the daemon secures the right file."""
        from android_emu_agent.security import SOCKET_PATH_ENV, daemon_socket_path

        override = tmp_path / "custom.sock"
        monkeypatch.setenv(SOCKET_PATH_ENV, str(override))
        assert daemon_socket_path() == override


class TestSecureOwnSocket:
    """Tests for the daemon tightening its own socket at startup."""

    def test_tightens_socket_permissions(self, monkeypatch) -> None:
        """A world-connectable socket must be reduced to owner-only."""
        import shutil
        import socket as socket_module
        import tempfile

        from android_emu_agent.daemon.server import _secure_own_socket
        from android_emu_agent.security import SOCKET_PATH_ENV

        # AF_UNIX paths are length-limited, so pytest's tmp_path is too deep here.
        socket_dir = tempfile.mkdtemp(prefix="aea-sock-")
        server = socket_module.socket(socket_module.AF_UNIX, socket_module.SOCK_STREAM)
        try:
            socket_path = Path(socket_dir) / "d.sock"
            server.bind(str(socket_path))
            socket_path.chmod(0o777)
            monkeypatch.setenv(SOCKET_PATH_ENV, str(socket_path))

            _secure_own_socket()

            assert socket_path.stat().st_mode & 0o077 == 0
        finally:
            server.close()
            shutil.rmtree(socket_dir, ignore_errors=True)

    def test_missing_socket_is_not_fatal(self, tmp_path, monkeypatch) -> None:
        """Startup must not fail when the socket path does not exist."""
        from android_emu_agent.daemon.server import _secure_own_socket
        from android_emu_agent.security import SOCKET_PATH_ENV

        monkeypatch.setenv(SOCKET_PATH_ENV, str(tmp_path / "absent.sock"))
        _secure_own_socket()

    def test_non_socket_path_is_reported_not_raised(self, tmp_path, monkeypatch) -> None:
        """A path that is not a socket must be refused without killing startup."""
        from android_emu_agent.daemon.server import _secure_own_socket
        from android_emu_agent.security import SOCKET_PATH_ENV

        decoy = tmp_path / "not-a-socket"
        decoy.write_text("plain file", encoding="utf-8")
        monkeypatch.setenv(SOCKET_PATH_ENV, str(decoy))

        _secure_own_socket()

        assert decoy.read_text(encoding="utf-8") == "plain file"
