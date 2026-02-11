"""Tests for DebugManager."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from android_emu_agent.debugger.manager import DebugManager, DebugSessionState
from android_emu_agent.errors import AgentError


class TestFindJava:
    """Tests for JDK detection."""

    def test_find_java_from_java_home(self, tmp_path: Path) -> None:
        """Should find java from JAVA_HOME."""
        java_bin = tmp_path / "bin" / "java"
        java_bin.parent.mkdir(parents=True)
        java_bin.touch()

        manager = DebugManager()
        with patch.dict(os.environ, {"JAVA_HOME": str(tmp_path)}):
            result = manager._find_java()
        assert result == java_bin

    def test_find_java_from_path(self) -> None:
        """Should find java from PATH via shutil.which."""
        manager = DebugManager()
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("shutil.which", return_value="/usr/bin/java"),
        ):
            # Clear JAVA_HOME
            os.environ.pop("JAVA_HOME", None)
            result = manager._find_java()
        assert result == Path("/usr/bin/java")

    def test_find_java_not_found(self) -> None:
        """Should raise ERR_JDK_NOT_FOUND when java is missing."""
        manager = DebugManager()
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("shutil.which", return_value=None),
        ):
            os.environ.pop("JAVA_HOME", None)
            with pytest.raises(AgentError) as exc_info:
                manager._find_java()
            assert exc_info.value.code == "ERR_JDK_NOT_FOUND"


class TestFindJar:
    """Tests for JAR resolution."""

    def test_find_jar_from_env_var(self, tmp_path: Path) -> None:
        """Should find JAR from ANDROID_EMU_AGENT_BRIDGE_JAR env var."""
        jar = tmp_path / "bridge.jar"
        jar.touch()

        manager = DebugManager()
        with patch.dict(os.environ, {"ANDROID_EMU_AGENT_BRIDGE_JAR": str(jar)}):
            result = manager._find_jar()
        assert result == jar

    def test_find_jar_env_var_missing_file(self) -> None:
        """Should raise when env var points to nonexistent file."""
        manager = DebugManager()
        with (
            patch.dict(os.environ, {"ANDROID_EMU_AGENT_BRIDGE_JAR": "/nonexistent.jar"}),
            pytest.raises(AgentError) as exc_info,
        ):
            manager._find_jar()
        assert exc_info.value.code == "ERR_BRIDGE_NOT_RUNNING"

    def test_find_jar_not_found(self, tmp_path: Path) -> None:
        """Should raise when JAR is not found anywhere."""
        manager = DebugManager()
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("pathlib.Path.cwd", return_value=tmp_path),
            patch(
                "android_emu_agent.debugger.manager._DEV_JAR_RELATIVE",
                Path("nonexistent/path"),
            ),
            pytest.raises(AgentError) as exc_info,
        ):
            os.environ.pop("ANDROID_EMU_AGENT_BRIDGE_JAR", None)
            manager._jar_path = None  # Reset cached path
            manager._find_jar()
        assert exc_info.value.code == "ERR_BRIDGE_NOT_RUNNING"


class TestDebugManagerLifecycle:
    """Tests for bridge lifecycle management."""

    @pytest.mark.asyncio
    async def test_get_bridge_not_attached(self) -> None:
        """Should raise ERR_DEBUG_NOT_ATTACHED for unknown session."""
        manager = DebugManager()
        with pytest.raises(AgentError) as exc_info:
            await manager.get_bridge("s-nonexistent")
        assert exc_info.value.code == "ERR_DEBUG_NOT_ATTACHED"

    @pytest.mark.asyncio
    async def test_stop_all_empty(self) -> None:
        """Stopping all bridges when none exist should be a no-op."""
        manager = DebugManager()
        await manager.stop_all()  # Should not raise


class TestAttach:
    """Tests for debug attach flow."""

    @pytest.mark.asyncio
    async def test_attach_stores_session_state(self) -> None:
        """Attach should store DebugSessionState after successful attach."""
        manager = DebugManager()

        mock_adb = MagicMock()
        mock_adb.shell = MagicMock(return_value="12345")
        mock_adb.forward = MagicMock(return_value=54321)

        mock_bridge = AsyncMock()
        mock_bridge.is_alive = True
        mock_bridge.ping = AsyncMock(return_value={"pong": True})
        mock_bridge.request = AsyncMock(
            return_value={"status": "attached", "vm_name": "Dalvik", "vm_version": "1.0"}
        )
        mock_bridge._event_queue = asyncio.Queue()

        with patch.object(manager, "start_bridge", return_value=mock_bridge):
            result = await manager.attach(
                session_id="s-test",
                device_serial="emulator-5554",
                package="com.example.app",
                adb_device=mock_adb,
            )

        assert result["status"] == "attached"
        assert result["pid"] == 12345
        assert result["local_port"] == 54321
        assert result["vm_name"] == "Dalvik"
        assert "s-test" in manager._debug_sessions
        ds = manager._debug_sessions["s-test"]
        assert ds.package == "com.example.app"
        assert ds.pid == 12345
        assert ds.state == "attached"

    @pytest.mark.asyncio
    async def test_attach_already_attached_raises(self) -> None:
        """Attach when already attached should raise ERR_ALREADY_ATTACHED."""
        manager = DebugManager()
        manager._debug_sessions["s-test"] = DebugSessionState(
            session_id="s-test",
            package="com.example.app",
            pid=123,
            jdwp_port=123,
            local_forward_port=54321,
            device_serial="emulator-5554",
            state="attached",
        )

        mock_adb = MagicMock()
        with pytest.raises(AgentError) as exc_info:
            await manager.attach(
                session_id="s-test",
                device_serial="emulator-5554",
                package="com.example.app",
                adb_device=mock_adb,
            )
        assert exc_info.value.code == "ERR_ALREADY_ATTACHED"


class TestDetach:
    """Tests for debug detach flow."""

    @pytest.mark.asyncio
    async def test_detach_cleans_up(self) -> None:
        """Detach should clean up session state, bridge, and forward."""
        manager = DebugManager()
        manager._debug_sessions["s-test"] = DebugSessionState(
            session_id="s-test",
            package="com.example.app",
            pid=123,
            jdwp_port=123,
            local_forward_port=54321,
            device_serial="emulator-5554",
            state="attached",
        )

        mock_bridge = AsyncMock()
        mock_bridge.is_alive = True
        mock_bridge.request = AsyncMock(return_value={"status": "detached"})
        manager._bridges["s-test"] = mock_bridge

        mock_adb = MagicMock()
        mock_adb.forward = MagicMock()
        mock_adb.shell = MagicMock(return_value="")

        result = await manager.detach("s-test", mock_adb)
        assert result["status"] == "detached"
        assert "s-test" not in manager._debug_sessions
        assert "s-test" not in manager._bridges

    @pytest.mark.asyncio
    async def test_detach_when_not_attached_raises(self) -> None:
        """Detach when not attached should raise ERR_DEBUG_NOT_ATTACHED."""
        manager = DebugManager()
        mock_adb = MagicMock()
        with pytest.raises(AgentError) as exc_info:
            await manager.detach("s-nonexistent", mock_adb)
        assert exc_info.value.code == "ERR_DEBUG_NOT_ATTACHED"


class TestStatus:
    """Tests for debug status."""

    @pytest.mark.asyncio
    async def test_status_not_attached(self) -> None:
        """Status for unknown session should return not_attached."""
        manager = DebugManager()
        result = await manager.status("s-nonexistent")
        assert result["status"] == "not_attached"

    @pytest.mark.asyncio
    async def test_status_attached(self) -> None:
        """Status for attached session should query bridge."""
        manager = DebugManager()
        manager._debug_sessions["s-test"] = DebugSessionState(
            session_id="s-test",
            package="com.example.app",
            pid=123,
            jdwp_port=123,
            local_forward_port=54321,
            device_serial="emulator-5554",
            state="attached",
            vm_name="Dalvik",
            vm_version="1.0",
        )

        mock_bridge = AsyncMock()
        mock_bridge.is_alive = True
        mock_bridge.request = AsyncMock(
            return_value={
                "status": "attached",
                "vm_name": "Dalvik",
                "vm_version": "1.0",
                "thread_count": 5,
            }
        )
        manager._bridges["s-test"] = mock_bridge

        result = await manager.status("s-test")
        assert result["status"] == "attached"
        assert result["package"] == "com.example.app"
        assert result["pid"] == 123
        assert result["thread_count"] == 5


class TestFindPid:
    """Tests for PID resolution."""

    @pytest.mark.asyncio
    async def test_find_pid_not_found(self) -> None:
        """Should raise ERR_PROCESS_NOT_FOUND when pidof returns empty."""
        manager = DebugManager()
        mock_adb = MagicMock()
        mock_adb.shell = MagicMock(return_value="")

        with pytest.raises(AgentError) as exc_info:
            await manager._find_pid("com.example.app", mock_adb)
        assert exc_info.value.code == "ERR_PROCESS_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_find_pid_returns_first(self) -> None:
        """Should return first PID when pidof returns multiple."""
        manager = DebugManager()
        mock_adb = MagicMock()
        mock_adb.shell = MagicMock(return_value="123 456")

        pid = await manager._find_pid("com.example.app", mock_adb)
        assert pid == 123
