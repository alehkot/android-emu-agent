"""Debug manager - owns JDI Bridge lifecycles and debug sessions."""

from __future__ import annotations

import asyncio
import contextlib
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog

from android_emu_agent.debugger.bridge_client import BridgeClient
from android_emu_agent.errors import (
    AgentError,
    adb_forward_failed_error,
    already_attached_error,
    bridge_not_running_error,
    debug_not_attached_error,
    jdk_not_found_error,
    process_not_found_error,
)

logger = structlog.get_logger()

# Default relative path from project root when developing locally
_DEV_JAR_RELATIVE = Path("jdi-bridge/build/libs")
_JAR_GLOB = "jdi-bridge-*-all.jar"


@dataclass
class DebugSessionState:
    """Tracks state for one debug-attached session."""

    session_id: str
    package: str
    pid: int
    jdwp_port: int
    local_forward_port: int
    device_serial: str
    state: str = "attached"  # attached | disconnected
    disconnect_reason: str = ""
    vm_name: str = ""
    vm_version: str = ""


class DebugManager:
    """Manages JDI Bridge subprocess lifecycles, one per debug session."""

    def __init__(self) -> None:
        self._bridges: dict[str, BridgeClient] = {}
        self._debug_sessions: dict[str, DebugSessionState] = {}
        self._event_tasks: dict[str, asyncio.Task[None]] = {}
        self._jar_path: Path | None = None
        self._java_path: Path | None = None

    def _find_java(self) -> Path:
        """Locate the java binary, checking JAVA_HOME first, then PATH."""
        if self._java_path is not None:
            return self._java_path

        # Check JAVA_HOME
        java_home = os.environ.get("JAVA_HOME")
        if java_home:
            candidate = Path(java_home) / "bin" / "java"
            if candidate.is_file():
                self._java_path = candidate
                return candidate

        # Check PATH
        which_java = shutil.which("java")
        if which_java:
            self._java_path = Path(which_java)
            return self._java_path

        raise jdk_not_found_error()

    def _find_jar(self) -> Path:
        """Locate the JDI Bridge JAR."""
        if self._jar_path is not None:
            return self._jar_path

        # 1. Environment variable override
        env_jar = os.environ.get("ANDROID_EMU_AGENT_BRIDGE_JAR")
        if env_jar:
            path = Path(env_jar)
            if path.is_file():
                self._jar_path = path
                return path
            raise bridge_not_running_error(f"JAR not found at ANDROID_EMU_AGENT_BRIDGE_JAR={env_jar}")

        # 2. Local development path (relative to cwd or common project locations)
        for base in (Path.cwd(), Path(__file__).parent.parent.parent.parent):
            jar_dir = base / _DEV_JAR_RELATIVE
            if jar_dir.is_dir():
                jars = sorted(jar_dir.glob(_JAR_GLOB), reverse=True)
                if jars:
                    self._jar_path = jars[0]
                    logger.info("bridge_jar_found", path=str(self._jar_path))
                    return self._jar_path

        # 3. Cached download path (future: auto-download)
        cache_dir = Path.home() / ".android-emu-agent" / "bridge"
        if cache_dir.is_dir():
            jars = sorted(cache_dir.glob(_JAR_GLOB), reverse=True)
            if jars:
                self._jar_path = jars[0]
                return self._jar_path

        raise bridge_not_running_error(
            "JAR not found. Build with './scripts/dev.sh build-bridge' "
            "or set ANDROID_EMU_AGENT_BRIDGE_JAR"
        )

    async def start_bridge(self, session_id: str) -> BridgeClient:
        """Start a new bridge for a debug session. Returns the client."""
        if session_id in self._bridges:
            client = self._bridges[session_id]
            if client.is_alive:
                return client
            # Dead bridge — clean up and restart
            del self._bridges[session_id]

        java_path = self._find_java()
        jar_path = self._find_jar()

        client = BridgeClient(java_path, jar_path)
        await client.start()

        # Verify the bridge is responsive
        try:
            result = await client.ping()
            logger.info("bridge_ping_ok", session_id=session_id, result=result)
        except Exception:
            await client.stop()
            raise bridge_not_running_error("bridge started but ping failed") from None

        self._bridges[session_id] = client
        return client

    async def stop_bridge(self, session_id: str) -> None:
        """Stop the bridge for a debug session."""
        client = self._bridges.pop(session_id, None)
        if client:
            await client.stop()

    async def get_bridge(self, session_id: str) -> BridgeClient:
        """Get the bridge for a session, raising if not attached."""
        client = self._bridges.get(session_id)
        if client is None or not client.is_alive:
            raise debug_not_attached_error(session_id)
        return client

    async def stop_all(self) -> None:
        """Stop all bridges and event monitors. Called on daemon shutdown."""
        for session_id in list(self._event_tasks.keys()):
            task = self._event_tasks.pop(session_id, None)
            if task and not task.done():
                task.cancel()
        for session_id in list(self._bridges.keys()):
            await self.stop_bridge(session_id)
        self._debug_sessions.clear()

    async def ping(self, session_id: str) -> dict[str, Any]:
        """Start a bridge (if needed) and ping it."""
        client = await self.start_bridge(session_id)
        return await client.ping()

    async def attach(
        self,
        session_id: str,
        device_serial: str,
        package: str,
        adb_device: Any,
    ) -> dict[str, Any]:
        """Attach the debugger to a running app.

        1. Check not already attached
        2. Find PID via pidof
        3. ADB forward a local port to jdwp:<pid>
        4. Start bridge, send 'attach' RPC
        5. Store session state, start event monitor
        """
        if session_id in self._debug_sessions:
            existing = self._debug_sessions[session_id]
            if existing.state == "attached":
                raise already_attached_error(session_id)
            # Previous session disconnected — clean up
            await self._cleanup_session(session_id, adb_device)

        # 1. Find PID
        pid = await self._find_pid(package, adb_device)

        # 2. ADB forward
        local_port = await self._setup_forward(pid, adb_device)

        # 3. Start bridge and attach
        try:
            bridge = await self.start_bridge(session_id)
            result = await bridge.request("attach", {"host": "localhost", "port": local_port})
        except Exception as exc:
            # Clean up forward on failure
            await self._remove_forward(local_port, adb_device)
            await self.stop_bridge(session_id)
            if isinstance(exc, AgentError):
                raise
            raise bridge_not_running_error(f"attach failed: {exc}") from None

        # Check for RPC error
        if isinstance(result, dict) and "error" in result and result["error"] is not None:
            await self._remove_forward(local_port, adb_device)
            await self.stop_bridge(session_id)
            err = result["error"]
            raise bridge_not_running_error(
                f"attach RPC error: {err.get('message', err)}"
            )

        # 4. Store state
        ds = DebugSessionState(
            session_id=session_id,
            package=package,
            pid=pid,
            jdwp_port=pid,  # JDWP port is the pid for `jdwp:<pid>`
            local_forward_port=local_port,
            device_serial=device_serial,
            state="attached",
            vm_name=result.get("vm_name", ""),
            vm_version=result.get("vm_version", ""),
        )
        self._debug_sessions[session_id] = ds

        # 5. Start event monitor
        self._event_tasks[session_id] = asyncio.create_task(
            self._monitor_events(session_id, bridge, adb_device)
        )

        logger.info(
            "debug_attached",
            session_id=session_id,
            package=package,
            pid=pid,
            local_port=local_port,
        )

        return {
            "status": "attached",
            "session_id": session_id,
            "package": package,
            "pid": pid,
            "local_port": local_port,
            "vm_name": result.get("vm_name", ""),
            "vm_version": result.get("vm_version", ""),
        }

    async def detach(self, session_id: str, adb_device: Any) -> dict[str, Any]:
        """Detach the debugger from a session.

        1. Send 'detach' to bridge
        2. Stop bridge
        3. Remove ADB forward
        4. Cancel event monitor, clean up state
        """
        ds = self._debug_sessions.get(session_id)
        if ds is None:
            raise debug_not_attached_error(session_id)

        bridge = self._bridges.get(session_id)
        if bridge and bridge.is_alive:
            with contextlib.suppress(Exception):
                await bridge.request("detach")

        await self._cleanup_session(session_id, adb_device)

        logger.info("debug_detached", session_id=session_id)
        return {"status": "detached", "session_id": session_id}

    async def status(self, session_id: str) -> dict[str, Any]:
        """Get the debug session status."""
        ds = self._debug_sessions.get(session_id)
        if ds is None:
            return {"status": "not_attached", "session_id": session_id}

        if ds.state == "disconnected":
            return {
                "status": "disconnected",
                "session_id": session_id,
                "package": ds.package,
                "pid": ds.pid,
                "reason": ds.disconnect_reason,
            }

        # Query bridge for live status
        bridge = self._bridges.get(session_id)
        if bridge and bridge.is_alive:
            try:
                result = await bridge.request("status")
                return {
                    "status": result.get("status", "attached"),
                    "session_id": session_id,
                    "package": ds.package,
                    "pid": ds.pid,
                    "local_port": ds.local_forward_port,
                    "vm_name": result.get("vm_name", ds.vm_name),
                    "vm_version": result.get("vm_version", ds.vm_version),
                    "thread_count": result.get("thread_count"),
                }
            except Exception:
                pass

        return {
            "status": ds.state,
            "session_id": session_id,
            "package": ds.package,
            "pid": ds.pid,
            "local_port": ds.local_forward_port,
        }

    async def _find_pid(self, package: str, adb_device: Any) -> int:
        """Find the PID of a running package."""
        output = await asyncio.to_thread(adb_device.shell, f"pidof {package}")
        output = output.strip()
        if not output:
            raise process_not_found_error(package)

        # pidof may return multiple PIDs; take the first
        pid_str = output.split()[0]
        try:
            return int(pid_str)
        except ValueError:
            raise process_not_found_error(package) from None

    async def _setup_forward(self, pid: int, adb_device: Any) -> int:
        """Set up ADB forward from a local port to jdwp:<pid>. Returns local port."""
        try:
            result = await asyncio.to_thread(
                adb_device.forward, "tcp:0", f"jdwp:{pid}"
            )
            # adbutils returns the local port as an int
            if isinstance(result, int):
                return result
            # Fallback: parse from string
            return int(str(result).strip())
        except Exception as exc:
            raise adb_forward_failed_error(pid, str(exc)) from None

    async def _remove_forward(self, local_port: int, adb_device: Any) -> None:
        """Remove an ADB forward rule."""
        with contextlib.suppress(Exception):
            await asyncio.to_thread(adb_device.forward, f"tcp:{local_port}", "")

    async def _cleanup_session(self, session_id: str, adb_device: Any) -> None:
        """Clean up all resources for a debug session."""
        # Cancel event monitor
        task = self._event_tasks.pop(session_id, None)
        if task and not task.done():
            task.cancel()

        # Remove ADB forward
        ds = self._debug_sessions.pop(session_id, None)
        if ds:
            await self._remove_forward(ds.local_forward_port, adb_device)

        # Stop bridge
        await self.stop_bridge(session_id)

    async def _monitor_events(
        self, session_id: str, bridge: BridgeClient, adb_device: Any
    ) -> None:
        """Background task consuming bridge event queue for VM disconnect."""
        try:
            while True:
                event = await bridge._event_queue.get()
                method = event.get("method")
                if method == "vm_disconnected":
                    params = event.get("params", {})
                    reason = params.get("reason", "unknown")
                    logger.warning(
                        "vm_disconnected",
                        session_id=session_id,
                        reason=reason,
                    )
                    ds = self._debug_sessions.get(session_id)
                    if ds:
                        ds.state = "disconnected"
                        ds.disconnect_reason = reason

                    # Clean up forward and bridge
                    if ds:
                        await self._remove_forward(ds.local_forward_port, adb_device)
                    await self.stop_bridge(session_id)
                    break
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception("event_monitor_error", session_id=session_id)
