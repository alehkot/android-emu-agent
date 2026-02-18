"""Tests for DebugManager."""

from __future__ import annotations

import asyncio
import os
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from android_emu_agent.debugger.manager import DebugManager, DebugSessionState
from android_emu_agent.errors import AgentError


def _make_open_transport_context(jdwp_output: str) -> MagicMock:
    conn = MagicMock()
    conn.read_string_block = MagicMock(return_value=jdwp_output)
    ctx = MagicMock()
    ctx.__enter__.return_value = conn
    ctx.__exit__.return_value = None
    return ctx


class TestFindJava:
    """Tests for JDK detection."""

    def test_find_java_from_java_home(self, tmp_path: Path) -> None:
        java_bin = tmp_path / "bin" / "java"
        java_bin.parent.mkdir(parents=True)
        java_bin.touch()

        manager = DebugManager()
        with patch.dict(os.environ, {"JAVA_HOME": str(tmp_path)}):
            result = manager._find_java()
        assert result == java_bin

    def test_find_java_from_path(self) -> None:
        manager = DebugManager()
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("shutil.which", return_value="/usr/bin/java"),
        ):
            os.environ.pop("JAVA_HOME", None)
            result = manager._find_java()
        assert result == Path("/usr/bin/java")

    def test_find_java_not_found(self) -> None:
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
        jar = tmp_path / "bridge.jar"
        jar.touch()

        manager = DebugManager()
        with patch.dict(os.environ, {"ANDROID_EMU_AGENT_BRIDGE_JAR": str(jar)}):
            result = manager._find_jar()
        assert result == jar

    def test_find_jar_env_var_missing_file(self) -> None:
        manager = DebugManager()
        with (
            patch.dict(os.environ, {"ANDROID_EMU_AGENT_BRIDGE_JAR": "/nonexistent.jar"}),
            pytest.raises(AgentError) as exc_info,
        ):
            manager._find_jar()
        assert exc_info.value.code == "ERR_BRIDGE_NOT_RUNNING"

    def test_find_jar_uses_downloader(self, tmp_path: Path) -> None:
        downloaded = tmp_path / "jdi-bridge-0.1.10-all.jar"
        downloaded.touch()

        manager = DebugManager()
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("pathlib.Path.cwd", return_value=tmp_path / "empty"),
            patch("android_emu_agent.debugger.manager._DEV_JAR_RELATIVE", Path("missing/build/libs")),
            patch.object(manager._downloader, "resolve", return_value=downloaded) as resolve,
        ):
            result = manager._find_jar()
        resolve.assert_called_once()
        assert result == downloaded


class TestDebugManagerLifecycle:
    """Tests for bridge lifecycle management."""

    @pytest.mark.asyncio
    async def test_get_bridge_not_attached(self) -> None:
        manager = DebugManager()
        with pytest.raises(AgentError) as exc_info:
            await manager.get_bridge("s-nonexistent")
        assert exc_info.value.code == "ERR_DEBUG_NOT_ATTACHED"

    @pytest.mark.asyncio
    async def test_stop_all_empty(self) -> None:
        manager = DebugManager()
        await manager.stop_all()


class TestAttach:
    """Tests for debug attach flow."""

    @pytest.mark.asyncio
    async def test_attach_stores_session_state(self) -> None:
        manager = DebugManager()

        mock_adb = MagicMock()
        mock_bridge = AsyncMock()
        mock_bridge.is_alive = True
        mock_bridge.request = AsyncMock(
            return_value={
                "status": "attached",
                "vm_name": "Dalvik",
                "vm_version": "1.0",
                "thread_count": 8,
                "suspended": False,
            }
        )
        mock_bridge.next_event = AsyncMock()

        with (
            patch.object(manager, "_find_pid", AsyncMock(return_value=(12345, "com.example.app"))),
            patch.object(manager, "_setup_forward", AsyncMock(return_value=54321)),
            patch.object(manager, "start_bridge", AsyncMock(return_value=mock_bridge)),
            patch.object(manager, "_monitor_events", AsyncMock()),
        ):
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
        assert result["threads"] == 8
        assert result["process_name"] == "com.example.app"
        assert result["keep_suspended"] is False
        assert "s-test" in manager._debug_sessions
        ds = manager._debug_sessions["s-test"]
        assert ds.package == "com.example.app"
        assert ds.process_name == "com.example.app"
        assert ds.pid == 12345
        assert ds.state == "attached"
        assert manager._event_queues["s-test"] == []
        mock_bridge.request.assert_awaited_once_with(
            "attach",
            {"host": "localhost", "port": 54321, "keep_suspended": False},
        )

    @pytest.mark.asyncio
    async def test_attach_forwards_keep_suspended(self) -> None:
        manager = DebugManager()

        mock_adb = MagicMock()
        mock_bridge = AsyncMock()
        mock_bridge.is_alive = True
        mock_bridge.request = AsyncMock(
            return_value={
                "status": "attached",
                "vm_name": "Dalvik",
                "vm_version": "1.0",
                "thread_count": 8,
                "suspended": True,
            }
        )
        mock_bridge.next_event = AsyncMock()

        with (
            patch.object(manager, "_find_pid", AsyncMock(return_value=(12345, "com.example.app"))),
            patch.object(manager, "_setup_forward", AsyncMock(return_value=54321)),
            patch.object(manager, "start_bridge", AsyncMock(return_value=mock_bridge)),
            patch.object(manager, "_monitor_events", AsyncMock()),
        ):
            result = await manager.attach(
                session_id="s-test",
                device_serial="emulator-5554",
                package="com.example.app",
                adb_device=mock_adb,
                keep_suspended=True,
            )

        assert result["suspended"] is True
        assert result["keep_suspended"] is True
        mock_bridge.request.assert_awaited_once_with(
            "attach",
            {"host": "localhost", "port": 54321, "keep_suspended": True},
        )

    @pytest.mark.asyncio
    async def test_attach_already_attached_raises(self) -> None:
        manager = DebugManager()
        manager._debug_sessions["s-test"] = DebugSessionState(
            session_id="s-test",
            package="com.example.app",
            process_name="com.example.app",
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

    @pytest.mark.asyncio
    async def test_attach_maps_not_debuggable_error(self) -> None:
        manager = DebugManager()

        mock_adb = MagicMock()
        mock_bridge = AsyncMock()
        mock_bridge.is_alive = True
        mock_bridge.request = AsyncMock(
            return_value={"error": {"message": "JDWP handshake failed: connection closed"}}
        )
        mock_bridge.next_event = AsyncMock()

        with (
            patch.object(manager, "_find_pid", AsyncMock(return_value=(12345, "com.example.app"))),
            patch.object(manager, "_setup_forward", AsyncMock(return_value=54321)),
            patch.object(manager, "start_bridge", AsyncMock(return_value=mock_bridge)),
            patch.object(manager, "_remove_forward", AsyncMock()),
            patch.object(manager, "stop_bridge", AsyncMock()),
            pytest.raises(AgentError) as exc_info,
        ):
            await manager.attach(
                session_id="s-test",
                device_serial="emulator-5554",
                package="com.example.app",
                adb_device=mock_adb,
            )
        assert exc_info.value.code == "ERR_APP_NOT_DEBUGGABLE"


class TestDetach:
    """Tests for debug detach flow."""

    @pytest.mark.asyncio
    async def test_detach_cleans_up(self) -> None:
        manager = DebugManager()
        manager._debug_sessions["s-test"] = DebugSessionState(
            session_id="s-test",
            package="com.example.app",
            process_name="com.example.app",
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
        mock_adb.forward_remove = MagicMock()

        result = await manager.detach("s-test", mock_adb)
        assert result["status"] == "detached"
        assert "s-test" not in manager._debug_sessions
        assert "s-test" not in manager._bridges
        assert "s-test" not in manager._event_queues
        mock_adb.forward_remove.assert_called_once_with("tcp:54321", False)

    @pytest.mark.asyncio
    async def test_detach_when_not_attached_raises(self) -> None:
        manager = DebugManager()
        mock_adb = MagicMock()
        with pytest.raises(AgentError) as exc_info:
            await manager.detach("s-nonexistent", mock_adb)
        assert exc_info.value.code == "ERR_DEBUG_NOT_ATTACHED"


class TestStatus:
    """Tests for debug status."""

    @pytest.mark.asyncio
    async def test_status_not_attached(self) -> None:
        manager = DebugManager()
        result = await manager.status("s-nonexistent")
        assert result["status"] == "not_attached"

    @pytest.mark.asyncio
    async def test_status_attached(self) -> None:
        manager = DebugManager()
        manager._debug_sessions["s-test"] = DebugSessionState(
            session_id="s-test",
            package="com.example.app",
            process_name="com.example.app",
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
                "suspended": False,
            }
        )
        manager._bridges["s-test"] = mock_bridge

        result = await manager.status("s-test")
        assert result["status"] == "attached"
        assert result["package"] == "com.example.app"
        assert result["process_name"] == "com.example.app"
        assert result["pid"] == 123
        assert result["thread_count"] == 5
        assert result["suspended"] is False

    @pytest.mark.asyncio
    async def test_status_disconnected_includes_remediation(self) -> None:
        manager = DebugManager()
        manager._debug_sessions["s-test"] = DebugSessionState(
            session_id="s-test",
            package="com.example.app",
            process_name="com.example.app",
            pid=123,
            jdwp_port=123,
            local_forward_port=54321,
            device_serial="emulator-5554",
            state="disconnected",
            disconnect_reason="app_crashed",
            disconnect_detail="VM disconnected",
        )
        result = await manager.status("s-test")
        assert result["status"] == "disconnected"
        assert "Relaunch" in result["remediation"]


class TestPidResolution:
    """Tests for package PID/JDWP mapping."""

    @pytest.mark.asyncio
    async def test_find_pid_single_match(self) -> None:
        manager = DebugManager()
        mock_adb = MagicMock()
        mock_adb.open_transport = MagicMock(return_value=_make_open_transport_context("12345\n"))
        mock_adb.shell = MagicMock(return_value="PID NAME\n12345 com.example.app\n")

        pid, process_name = await manager._find_pid("com.example.app", mock_adb)
        assert pid == 12345
        assert process_name == "com.example.app"

    @pytest.mark.asyncio
    async def test_find_pid_prefers_main_process(self) -> None:
        manager = DebugManager()
        mock_adb = MagicMock()
        mock_adb.open_transport = MagicMock(return_value=_make_open_transport_context("123 456\n"))
        mock_adb.shell = MagicMock(
            return_value=("PID NAME\n123 com.example.app:remote\n456 com.example.app\n")
        )

        pid, process_name = await manager._find_pid("com.example.app", mock_adb)
        assert pid == 456
        assert process_name == "com.example.app"

    @pytest.mark.asyncio
    async def test_find_pid_multiple_without_main_requires_process(self) -> None:
        manager = DebugManager()
        mock_adb = MagicMock()
        mock_adb.open_transport = MagicMock(return_value=_make_open_transport_context("123 456\n"))
        mock_adb.shell = MagicMock(
            return_value=("PID NAME\n123 com.example.app:alpha\n456 com.example.app:beta\n")
        )

        with pytest.raises(AgentError) as exc_info:
            await manager._find_pid("com.example.app", mock_adb)
        assert exc_info.value.code == "ERR_MULTIPLE_DEBUGGABLE_PROCESSES"

    @pytest.mark.asyncio
    async def test_find_pid_explicit_process(self) -> None:
        manager = DebugManager()
        mock_adb = MagicMock()
        mock_adb.open_transport = MagicMock(return_value=_make_open_transport_context("123 456\n"))
        mock_adb.shell = MagicMock(
            return_value=("PID NAME\n123 com.example.app\n456 com.example.app:remote\n")
        )

        pid, process_name = await manager._find_pid(
            "com.example.app",
            mock_adb,
            process_name="com.example.app:remote",
        )
        assert pid == 456
        assert process_name == "com.example.app:remote"

    @pytest.mark.asyncio
    async def test_find_pid_not_debuggable(self) -> None:
        manager = DebugManager()
        mock_adb = MagicMock()
        mock_adb.open_transport = MagicMock(return_value=_make_open_transport_context(""))
        mock_adb.shell = MagicMock(return_value="PID NAME\n12345 com.example.app\n")

        with pytest.raises(AgentError) as exc_info:
            await manager._find_pid("com.example.app", mock_adb)
        assert exc_info.value.code == "ERR_APP_NOT_DEBUGGABLE"

    @pytest.mark.asyncio
    async def test_find_pid_not_found(self) -> None:
        manager = DebugManager()
        mock_adb = MagicMock()
        mock_adb.open_transport = MagicMock(return_value=_make_open_transport_context(""))
        mock_adb.shell = MagicMock(return_value="PID NAME\n")

        with pytest.raises(AgentError) as exc_info:
            await manager._find_pid("com.example.app", mock_adb)
        assert exc_info.value.code == "ERR_PROCESS_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_list_jdwp_pids_falls_back_to_adb_cli(self) -> None:
        manager = DebugManager()
        mock_adb = MagicMock()
        mock_adb.serial = "emulator-5554"

        with (
            patch.object(
                manager,
                "_read_jdwp_list",
                side_effect=RuntimeError("unknown host service 'jdwp'"),
            ),
            patch.object(
                manager,
                "_read_jdwp_list_via_adb",
                return_value="1649\n5182\n6547\n",
            ),
        ):
            pids = await manager._list_jdwp_pids(mock_adb)

        assert pids == {1649, 5182, 6547}

    def test_read_jdwp_list_via_adb_parses_timeout_partial_output(self) -> None:
        manager = DebugManager()
        timeout = subprocess.TimeoutExpired(
            cmd=["adb", "-s", "emulator-5554", "jdwp"],
            timeout=1.0,
            output=b"1649\n5182\n6547\n",
        )

        with (
            patch("shutil.which", return_value="/usr/bin/adb"),
            patch("subprocess.run", side_effect=timeout),
        ):
            output = manager._read_jdwp_list_via_adb("emulator-5554")

        assert output.strip().splitlines() == ["1649", "5182", "6547"]


class TestForwarding:
    """Tests for ADB forwarding lifecycle."""

    @pytest.mark.asyncio
    async def test_setup_forward_uses_forward_port(self) -> None:
        manager = DebugManager()
        mock_adb = MagicMock()
        mock_adb.forward_port = MagicMock(return_value=54321)

        port = await manager._setup_forward(12345, mock_adb)
        assert port == 54321
        mock_adb.forward_port.assert_called_once_with("jdwp:12345")

    @pytest.mark.asyncio
    async def test_remove_forward_uses_forward_remove(self) -> None:
        manager = DebugManager()
        mock_adb = MagicMock()
        mock_adb.forward_remove = MagicMock()

        await manager._remove_forward(54321, mock_adb)
        mock_adb.forward_remove.assert_called_once_with("tcp:54321", False)


class TestDisconnectEvents:
    """Tests for async bridge events."""

    @pytest.mark.asyncio
    async def test_monitor_event_handles_event_notification_shape(self) -> None:
        manager = DebugManager()
        manager._debug_sessions["s-test"] = DebugSessionState(
            session_id="s-test",
            package="com.example.app",
            process_name="com.example.app",
            pid=12345,
            jdwp_port=12345,
            local_forward_port=54321,
            device_serial="emulator-5554",
            state="attached",
        )

        bridge = MagicMock()
        bridge.next_event = AsyncMock(
            return_value={
                "jsonrpc": "2.0",
                "method": "event",
                "params": {"type": "vm_disconnected", "reason": "device_disconnected"},
            }
        )

        mock_adb = MagicMock()
        with patch.object(manager, "stop_bridge", AsyncMock()) as stop_bridge:
            await manager._monitor_events("s-test", bridge, mock_adb)

        ds = manager._debug_sessions["s-test"]
        assert ds.state == "disconnected"
        assert ds.disconnect_reason == "device_disconnected"
        stop_bridge.assert_awaited_once_with("s-test")


class TestMilestone2DebugMethods:
    """Tests for breakpoint/thread/event manager APIs."""

    @staticmethod
    def _attach_session(manager: DebugManager, session_id: str = "s-test") -> None:
        manager._debug_sessions[session_id] = DebugSessionState(
            session_id=session_id,
            package="com.example.app",
            process_name="com.example.app",
            pid=123,
            jdwp_port=123,
            local_forward_port=54321,
            device_serial="emulator-5554",
            state="attached",
        )

    @pytest.mark.asyncio
    async def test_set_breakpoint_forwards_rpc(self) -> None:
        manager = DebugManager()
        self._attach_session(manager)

        bridge = AsyncMock()
        bridge.is_alive = True
        bridge.request = AsyncMock(return_value={"status": "set", "breakpoint_id": 1})
        manager._bridges["s-test"] = bridge

        result = await manager.set_breakpoint("s-test", "com.example.MainActivity", 25)
        assert result["status"] == "set"
        bridge.request.assert_awaited_once_with(
            "set_breakpoint",
            {"class_pattern": "com.example.MainActivity", "line": 25},
        )

    @pytest.mark.asyncio
    async def test_set_breakpoint_with_condition_forwards_rpc(self) -> None:
        manager = DebugManager()
        self._attach_session(manager)

        bridge = AsyncMock()
        bridge.is_alive = True
        bridge.request = AsyncMock(return_value={
            "status": "set",
            "breakpoint_id": 2,
            "condition": "counter > 5",
        })
        manager._bridges["s-test"] = bridge

        result = await manager.set_breakpoint(
            "s-test", "com.example.MainActivity", 30, condition="counter > 5",
        )
        assert result["status"] == "set"
        assert result["condition"] == "counter > 5"
        bridge.request.assert_awaited_once_with(
            "set_breakpoint",
            {"class_pattern": "com.example.MainActivity", "line": 30, "condition": "counter > 5"},
        )

    @pytest.mark.asyncio
    async def test_set_breakpoint_with_log_message_forwards_rpc(self) -> None:
        manager = DebugManager()
        self._attach_session(manager)

        bridge = AsyncMock()
        bridge.is_alive = True
        bridge.request = AsyncMock(return_value={
            "status": "set",
            "breakpoint_id": 3,
            "log_message": "hit {hitCount} times, val={myVar}",
        })
        manager._bridges["s-test"] = bridge

        result = await manager.set_breakpoint(
            "s-test", "com.example.MainActivity", 35,
            log_message="hit {hitCount} times, val={myVar}",
        )
        assert result["status"] == "set"
        assert result["log_message"] == "hit {hitCount} times, val={myVar}"
        bridge.request.assert_awaited_once_with(
            "set_breakpoint",
            {
                "class_pattern": "com.example.MainActivity",
                "line": 35,
                "log_message": "hit {hitCount} times, val={myVar}",
            },
        )

    @pytest.mark.asyncio
    async def test_set_breakpoint_with_condition_and_log_message_forwards_rpc(self) -> None:
        manager = DebugManager()
        self._attach_session(manager)

        bridge = AsyncMock()
        bridge.is_alive = True
        bridge.request = AsyncMock(return_value={
            "status": "set",
            "breakpoint_id": 4,
            "condition": "x > 0",
            "log_message": "x={x}",
        })
        manager._bridges["s-test"] = bridge

        result = await manager.set_breakpoint(
            "s-test", "com.example.MainActivity", 40,
            condition="x > 0",
            log_message="x={x}",
        )
        assert result["status"] == "set"
        bridge.request.assert_awaited_once_with(
            "set_breakpoint",
            {
                "class_pattern": "com.example.MainActivity",
                "line": 40,
                "condition": "x > 0",
                "log_message": "x={x}",
            },
        )

    @pytest.mark.asyncio
    async def test_set_breakpoint_with_logpoint_stack_capture_forwards_rpc(self) -> None:
        manager = DebugManager()
        self._attach_session(manager)

        bridge = AsyncMock()
        bridge.is_alive = True
        bridge.request = AsyncMock(return_value={
            "status": "set",
            "breakpoint_id": 5,
            "log_message": "x={x}",
            "capture_stack": True,
            "stack_max_frames": 12,
        })
        manager._bridges["s-test"] = bridge

        result = await manager.set_breakpoint(
            "s-test",
            "com.example.MainActivity",
            41,
            log_message="x={x}",
            capture_stack=True,
            stack_max_frames=12,
        )
        assert result["status"] == "set"
        bridge.request.assert_awaited_once_with(
            "set_breakpoint",
            {
                "class_pattern": "com.example.MainActivity",
                "line": 41,
                "log_message": "x={x}",
                "capture_stack": True,
                "stack_max_frames": 12,
            },
        )

    @pytest.mark.asyncio
    async def test_list_threads_forwards_rpc(self) -> None:
        manager = DebugManager()
        self._attach_session(manager)

        bridge = AsyncMock()
        bridge.is_alive = True
        bridge.request = AsyncMock(return_value={"threads": [], "total_threads": 0, "truncated": False})
        manager._bridges["s-test"] = bridge

        result = await manager.list_threads("s-test", include_daemon=True, max_threads=100)
        assert result["status"] == "attached"
        bridge.request.assert_awaited_once_with(
            "list_threads",
            {"include_daemon": True, "max_threads": 100},
        )

    @pytest.mark.asyncio
    async def test_stack_trace_forwards_rpc(self) -> None:
        manager = DebugManager()
        self._attach_session(manager)

        bridge = AsyncMock()
        bridge.is_alive = True
        bridge.request = AsyncMock(return_value={"thread": "main", "frames": []})
        manager._bridges["s-test"] = bridge

        result = await manager.stack_trace("s-test", thread_name="main", max_frames=10)
        assert result["thread"] == "main"
        bridge.request.assert_awaited_once_with(
            "stack_trace",
            {"thread_name": "main", "max_frames": 10},
        )

    @pytest.mark.asyncio
    async def test_inspect_variable_forwards_rpc(self) -> None:
        manager = DebugManager()
        self._attach_session(manager)

        bridge = AsyncMock()
        bridge.is_alive = True
        bridge.request = AsyncMock(return_value={"variable_path": "user", "value": {"class": "User"}})
        manager._bridges["s-test"] = bridge

        result = await manager.inspect_variable(
            "s-test",
            variable_path="user.profile",
            thread_name="main",
            frame_index=0,
            depth=2,
        )
        assert result["variable_path"] == "user"
        bridge.request.assert_awaited_once_with(
            "inspect_variable",
            {
                "thread_name": "main",
                "frame_index": 0,
                "variable_path": "user.profile",
                "depth": 2,
            },
        )

    @pytest.mark.asyncio
    async def test_evaluate_forwards_rpc(self) -> None:
        manager = DebugManager()
        self._attach_session(manager)

        bridge = AsyncMock()
        bridge.is_alive = True
        bridge.request = AsyncMock(return_value={"expression": "user.id", "result": 42})
        manager._bridges["s-test"] = bridge

        result = await manager.evaluate(
            "s-test",
            expression="user.id",
            thread_name="main",
            frame_index=0,
        )
        assert result["expression"] == "user.id"
        bridge.request.assert_awaited_once_with(
            "evaluate",
            {
                "thread_name": "main",
                "frame_index": 0,
                "expression": "user.id",
            },
        )

    @pytest.mark.asyncio
    async def test_load_mapping_forwards_rpc(self) -> None:
        manager = DebugManager()
        self._attach_session(manager)

        bridge = AsyncMock()
        bridge.is_alive = True
        bridge.request = AsyncMock(return_value={"status": "loaded", "path": "/tmp/mapping.txt"})
        manager._bridges["s-test"] = bridge

        result = await manager.load_mapping("s-test", path="/tmp/mapping.txt")
        assert result["status"] == "loaded"
        bridge.request.assert_awaited_once_with("load_mapping", {"path": "/tmp/mapping.txt"})

    @pytest.mark.asyncio
    async def test_clear_mapping_forwards_rpc(self) -> None:
        manager = DebugManager()
        self._attach_session(manager)

        bridge = AsyncMock()
        bridge.is_alive = True
        bridge.request = AsyncMock(return_value={"status": "cleared"})
        manager._bridges["s-test"] = bridge

        result = await manager.clear_mapping("s-test")
        assert result["status"] == "cleared"
        bridge.request.assert_awaited_once_with("clear_mapping")

    @pytest.mark.asyncio
    async def test_step_over_forwards_rpc(self) -> None:
        manager = DebugManager()
        self._attach_session(manager)

        bridge = AsyncMock()
        bridge.is_alive = True
        bridge.request = AsyncMock(return_value={"status": "stopped"})
        manager._bridges["s-test"] = bridge

        result = await manager.step_over("s-test", thread_name="main", timeout_seconds=10.0)
        assert result["status"] == "stopped"
        bridge.request.assert_awaited_once_with(
            "step_over",
            {"thread_name": "main", "timeout_seconds": 10.0},
        )

    @pytest.mark.asyncio
    async def test_step_into_forwards_rpc(self) -> None:
        manager = DebugManager()
        self._attach_session(manager)

        bridge = AsyncMock()
        bridge.is_alive = True
        bridge.request = AsyncMock(return_value={"status": "stopped"})
        manager._bridges["s-test"] = bridge

        result = await manager.step_into("s-test", thread_name="main", timeout_seconds=10.0)
        assert result["status"] == "stopped"
        bridge.request.assert_awaited_once_with(
            "step_into",
            {"thread_name": "main", "timeout_seconds": 10.0},
        )

    @pytest.mark.asyncio
    async def test_step_out_forwards_rpc(self) -> None:
        manager = DebugManager()
        self._attach_session(manager)

        bridge = AsyncMock()
        bridge.is_alive = True
        bridge.request = AsyncMock(return_value={"status": "stopped"})
        manager._bridges["s-test"] = bridge

        result = await manager.step_out("s-test", thread_name="main", timeout_seconds=10.0)
        assert result["status"] == "stopped"
        bridge.request.assert_awaited_once_with(
            "step_out",
            {"thread_name": "main", "timeout_seconds": 10.0},
        )

    @pytest.mark.asyncio
    async def test_resume_forwards_rpc_for_all_threads(self) -> None:
        manager = DebugManager()
        self._attach_session(manager)

        bridge = AsyncMock()
        bridge.is_alive = True
        bridge.request = AsyncMock(return_value={"status": "resumed", "scope": "all"})
        manager._bridges["s-test"] = bridge

        result = await manager.resume("s-test", thread_name=None)
        assert result["scope"] == "all"
        bridge.request.assert_awaited_once_with("resume", {})

    @pytest.mark.asyncio
    async def test_resume_forwards_rpc_for_specific_thread(self) -> None:
        manager = DebugManager()
        self._attach_session(manager)

        bridge = AsyncMock()
        bridge.is_alive = True
        bridge.request = AsyncMock(return_value={"status": "resumed", "scope": "thread"})
        manager._bridges["s-test"] = bridge

        result = await manager.resume("s-test", thread_name="main")
        assert result["scope"] == "thread"
        bridge.request.assert_awaited_once_with("resume", {"thread_name": "main"})

    @pytest.mark.asyncio
    async def test_drain_events_returns_and_clears_queue(self) -> None:
        manager = DebugManager()
        self._attach_session(manager)
        manager._event_queues["s-test"] = [
            {"type": "breakpoint_resolved", "breakpoint_id": 1},
            {"type": "breakpoint_hit", "breakpoint_id": 1},
        ]

        first = await manager.drain_events("s-test")
        assert first["status"] == "attached"
        assert first["count"] == 2
        assert len(first["events"]) == 2

        second = await manager.drain_events("s-test")
        assert second["count"] == 0
        assert second["events"] == []

    @pytest.mark.asyncio
    async def test_monitor_events_queues_breakpoint_notifications(self) -> None:
        manager = DebugManager()
        self._attach_session(manager)

        bridge = MagicMock()
        bridge.next_event = AsyncMock(
            side_effect=[
                {
                    "jsonrpc": "2.0",
                    "method": "event",
                    "params": {
                        "type": "breakpoint_hit",
                        "breakpoint_id": 3,
                        "thread": "main",
                        "location": "com.example.MainActivity:25",
                    },
                },
                asyncio.CancelledError(),
            ]
        )

        adb = MagicMock()
        await manager._monitor_events("s-test", bridge, adb)

        queued = manager._event_queues.get("s-test", [])
        assert len(queued) == 1
        assert queued[0]["type"] == "breakpoint_hit"
        assert queued[0]["breakpoint_id"] == 3
        assert isinstance(queued[0]["timestamp_ms"], int)

    @pytest.mark.asyncio
    async def test_monitor_events_records_logpoint_history(self) -> None:
        manager = DebugManager()
        self._attach_session(manager)

        bridge = MagicMock()
        bridge.next_event = AsyncMock(
            side_effect=[
                {
                    "jsonrpc": "2.0",
                    "method": "event",
                    "params": {
                        "type": "logpoint_hit",
                        "breakpoint_id": 9,
                        "message": "x=3",
                        "hit_count": 1,
                        "thread": "main",
                        "location": "com.example.MainActivity:55",
                    },
                },
                asyncio.CancelledError(),
            ]
        )

        adb = MagicMock()
        await manager._monitor_events("s-test", bridge, adb)

        queued = manager._event_queues.get("s-test", [])
        assert len(queued) == 1
        assert queued[0]["type"] == "logpoint_hit"
        assert isinstance(queued[0]["timestamp_ms"], int)

        history = manager._logpoint_histories.get("s-test", [])
        assert len(history) == 1
        assert history[0]["type"] == "logpoint_hit"
        assert history[0]["breakpoint_id"] == 9

    @pytest.mark.asyncio
    async def test_list_logpoint_hits_filters_by_breakpoint(self) -> None:
        manager = DebugManager()
        self._attach_session(manager)
        manager._logpoint_histories["s-test"] = [
            {"type": "logpoint_hit", "breakpoint_id": 1, "timestamp_ms": 1000, "message": "a"},
            {"type": "logpoint_hit", "breakpoint_id": 2, "timestamp_ms": 2000, "message": "b"},
            {"type": "logpoint_hit", "breakpoint_id": 1, "timestamp_ms": 3000, "message": "c"},
        ]

        result = await manager.list_logpoint_hits(
            "s-test",
            breakpoint_id=1,
            limit=10,
            since_timestamp_ms=1500,
        )

        assert result["count"] == 1
        assert result["hits"][0]["message"] == "c"
        assert result["buffer_count"] == 3


class TestBridgeErrorMapping:
    """Tests for JSON-RPC error mapping in debug manager."""

    def test_object_collected_error_is_mapped(self) -> None:
        with pytest.raises(AgentError) as exc_info:
            DebugManager._ensure_bridge_result(
                {"error": {"code": -32010, "message": "ERR_OBJECT_COLLECTED: stale object id"}},
                method="inspect_variable",
            )
        assert exc_info.value.code == "ERR_OBJECT_COLLECTED"

    def test_not_suspended_error_is_mapped(self) -> None:
        with pytest.raises(AgentError) as exc_info:
            DebugManager._ensure_bridge_result(
                {"error": {"code": -32011, "message": "ERR_NOT_SUSPENDED: thread not paused"}},
                method="stack_trace",
            )
        assert exc_info.value.code == "ERR_NOT_SUSPENDED"

    def test_eval_unsupported_error_is_mapped(self) -> None:
        with pytest.raises(AgentError) as exc_info:
            DebugManager._ensure_bridge_result(
                {"error": {"code": -32012, "message": "ERR_EVAL_UNSUPPORTED: method call forbidden"}},
                method="evaluate",
            )
        assert exc_info.value.code == "ERR_EVAL_UNSUPPORTED"

    def test_step_timeout_error_is_mapped(self) -> None:
        with pytest.raises(AgentError) as exc_info:
            DebugManager._ensure_bridge_result(
                {"error": {"code": -32020, "message": "ERR_STEP_TIMEOUT: step did not complete within 8s"}},
                method="step_over",
                error_context={"thread_name": "main", "timeout_seconds": 8.0},
            )
        assert exc_info.value.code == "ERR_STEP_TIMEOUT"

    def test_class_not_found_error_is_mapped(self) -> None:
        with pytest.raises(AgentError) as exc_info:
            DebugManager._ensure_bridge_result(
                {"error": {"code": -32030, "message": "ERR_CLASS_NOT_FOUND: class not found"}},
                method="set_breakpoint",
                error_context={"class_pattern": "com.example.Missing", "line": 42},
            )
        assert exc_info.value.code == "ERR_CLASS_NOT_FOUND"

    def test_breakpoint_invalid_line_error_is_mapped(self) -> None:
        with pytest.raises(AgentError) as exc_info:
            DebugManager._ensure_bridge_result(
                {"error": {"code": -32031, "message": "ERR_BREAKPOINT_INVALID_LINE: no executable code"}},
                method="set_breakpoint",
                error_context={"class_pattern": "com.example.MainActivity", "line": 42},
            )
        assert exc_info.value.code == "ERR_BREAKPOINT_INVALID_LINE"


class TestExceptionBreakpoints:
    """Tests for exception breakpoint DebugManager proxy methods."""

    @staticmethod
    def _attach_session(manager: DebugManager, session_id: str = "s-test") -> None:
        manager._debug_sessions[session_id] = DebugSessionState(
            session_id=session_id,
            package="com.example.app",
            process_name="com.example.app",
            pid=123,
            jdwp_port=123,
            local_forward_port=54321,
            device_serial="emulator-5554",
            state="attached",
        )

    @pytest.mark.asyncio
    async def test_set_exception_breakpoint_forwards_rpc(self) -> None:
        manager = DebugManager()
        self._attach_session(manager)

        bridge = AsyncMock()
        bridge.is_alive = True
        bridge.request = AsyncMock(return_value={
            "status": "set",
            "breakpoint_id": 1,
            "class_pattern": "java.lang.NullPointerException",
            "caught": True,
            "uncaught": False,
        })
        manager._bridges["s-test"] = bridge

        result = await manager.set_exception_breakpoint(
            "s-test",
            "java.lang.NullPointerException",
            caught=True,
            uncaught=False,
        )
        assert result["status"] == "set"
        assert result["breakpoint_id"] == 1
        bridge.request.assert_awaited_once_with(
            "set_exception_breakpoint",
            {
                "class_pattern": "java.lang.NullPointerException",
                "caught": True,
                "uncaught": False,
            },
        )

    @pytest.mark.asyncio
    async def test_set_exception_breakpoint_wildcard_forwards_rpc(self) -> None:
        manager = DebugManager()
        self._attach_session(manager)

        bridge = AsyncMock()
        bridge.is_alive = True
        bridge.request = AsyncMock(return_value={
            "status": "set",
            "breakpoint_id": 2,
            "class_pattern": "*",
            "caught": True,
            "uncaught": True,
        })
        manager._bridges["s-test"] = bridge

        result = await manager.set_exception_breakpoint("s-test")
        assert result["status"] == "set"
        assert result["class_pattern"] == "*"
        bridge.request.assert_awaited_once_with(
            "set_exception_breakpoint",
            {"class_pattern": "*", "caught": True, "uncaught": True},
        )

    @pytest.mark.asyncio
    async def test_remove_exception_breakpoint_forwards_rpc(self) -> None:
        manager = DebugManager()
        self._attach_session(manager)

        bridge = AsyncMock()
        bridge.is_alive = True
        bridge.request = AsyncMock(return_value={"status": "removed", "breakpoint_id": 1})
        manager._bridges["s-test"] = bridge

        result = await manager.remove_exception_breakpoint("s-test", 1)
        assert result["status"] == "removed"
        bridge.request.assert_awaited_once_with(
            "remove_exception_breakpoint",
            {"breakpoint_id": 1},
        )

    @pytest.mark.asyncio
    async def test_list_exception_breakpoints_forwards_rpc(self) -> None:
        manager = DebugManager()
        self._attach_session(manager)

        bridge = AsyncMock()
        bridge.is_alive = True
        bridge.request = AsyncMock(return_value={
            "count": 1,
            "exception_breakpoints": [
                {
                    "breakpoint_id": 1,
                    "class_pattern": "*",
                    "caught": True,
                    "uncaught": True,
                    "status": "set",
                },
            ],
        })
        manager._bridges["s-test"] = bridge

        result = await manager.list_exception_breakpoints("s-test")
        assert result["status"] == "attached"
        assert result["count"] == 1
        bridge.request.assert_awaited_once_with("list_exception_breakpoints")
