"""Debug manager - owns JDI Bridge lifecycles and debug sessions."""

from __future__ import annotations

import asyncio
import contextlib
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog

from android_emu_agent.debugger.bridge_client import BridgeClient
from android_emu_agent.debugger.bridge_downloader import BridgeDownloader
from android_emu_agent.errors import (
    AgentError,
    adb_forward_failed_error,
    already_attached_error,
    app_not_debuggable_error,
    breakpoint_invalid_line_error,
    bridge_not_running_error,
    class_not_found_error,
    debug_not_attached_error,
    jdk_not_found_error,
    not_suspended_error,
    object_collected_error,
    process_not_found_error,
    step_timeout_error,
)

logger = structlog.get_logger()

# Default relative path from project root when developing locally.
_DEV_JAR_RELATIVE = Path("jdi-bridge/build/libs")
_JAR_GLOB = "jdi-bridge-*-all.jar"


@dataclass(frozen=True)
class DebuggableProcess:
    """A process that is both running and exposed via JDWP."""

    pid: int
    name: str


@dataclass
class DebugSessionState:
    """Tracks state for one debug-attached session."""

    session_id: str
    package: str
    process_name: str
    pid: int
    jdwp_port: int
    local_forward_port: int
    device_serial: str
    state: str = "attached"  # attached | disconnected
    disconnect_reason: str = ""
    disconnect_detail: str = ""
    vm_name: str = ""
    vm_version: str = ""


class DebugManager:
    """Manages JDI Bridge subprocess lifecycles, one per debug session."""

    def __init__(self) -> None:
        self._bridges: dict[str, BridgeClient] = {}
        self._debug_sessions: dict[str, DebugSessionState] = {}
        self._event_tasks: dict[str, asyncio.Task[None]] = {}
        self._event_queues: dict[str, list[dict[str, Any]]] = {}
        self._jar_path: Path | None = None
        self._java_path: Path | None = None
        self._downloader = BridgeDownloader()

    def _find_java(self) -> Path:
        """Locate the java binary, checking JAVA_HOME first, then PATH."""
        if self._java_path is not None:
            return self._java_path

        java_home = os.environ.get("JAVA_HOME")
        if java_home:
            candidate = Path(java_home) / "bin" / "java"
            if candidate.is_file():
                self._java_path = candidate
                return candidate

        which_java = shutil.which("java")
        if which_java:
            self._java_path = Path(which_java)
            return self._java_path

        raise jdk_not_found_error()

    def _find_jar(self) -> Path:
        """Locate the JDI Bridge JAR, downloading from releases if needed."""
        if self._jar_path is not None:
            return self._jar_path

        env_jar = os.environ.get("ANDROID_EMU_AGENT_BRIDGE_JAR")
        if env_jar:
            path = Path(env_jar)
            if path.is_file():
                self._jar_path = path
                return path
            raise bridge_not_running_error(
                f"JAR not found at ANDROID_EMU_AGENT_BRIDGE_JAR={env_jar}"
            )

        for base in (Path.cwd(), Path(__file__).parent.parent.parent.parent):
            jar_dir = base / _DEV_JAR_RELATIVE
            if not jar_dir.is_dir():
                continue
            jars = sorted(jar_dir.glob(_JAR_GLOB), reverse=True)
            if jars:
                self._jar_path = jars[0]
                logger.info("bridge_jar_found", path=str(self._jar_path))
                return self._jar_path

        try:
            self._jar_path = self._downloader.resolve()
            logger.info("bridge_jar_downloaded", path=str(self._jar_path))
            return self._jar_path
        except AgentError:
            raise
        except Exception as exc:
            raise bridge_not_running_error(f"Failed to resolve bridge JAR: {exc}") from None

    async def start_bridge(self, session_id: str) -> BridgeClient:
        """Start a new bridge for a debug session. Returns the client."""
        if session_id in self._bridges:
            client = self._bridges[session_id]
            if client.is_alive:
                return client
            del self._bridges[session_id]

        java_path = self._find_java()
        jar_path = self._find_jar()

        client = BridgeClient(java_path, jar_path)
        await client.start()

        try:
            result = await client.ping()
            logger.info("bridge_ping_ok", session_id=session_id, result=result)
        except Exception as exc:
            await client.stop()
            if isinstance(exc, AgentError):
                raise
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
        self._event_queues.clear()

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
        process_name: str | None = None,
    ) -> dict[str, Any]:
        """Attach the debugger to a running app."""
        if session_id in self._debug_sessions:
            existing = self._debug_sessions[session_id]
            if existing.state == "attached":
                raise already_attached_error(session_id)
            await self._cleanup_session(session_id, adb_device)

        pid, selected_process_name = await self._find_pid(package, adb_device, process_name)
        local_port = await self._setup_forward(pid, adb_device)

        try:
            bridge = await self.start_bridge(session_id)
            result = await bridge.request("attach", {"host": "localhost", "port": local_port})
        except Exception as exc:
            await self._remove_forward(local_port, adb_device)
            await self.stop_bridge(session_id)
            if isinstance(exc, AgentError):
                raise
            if self._looks_not_debuggable(str(exc)):
                raise app_not_debuggable_error(package) from None
            raise bridge_not_running_error(f"attach failed: {exc}") from None

        if isinstance(result, dict) and "error" in result and result["error"] is not None:
            await self._remove_forward(local_port, adb_device)
            await self.stop_bridge(session_id)
            err = result["error"]
            error_message = str(err.get("message", err))
            if self._looks_not_debuggable(error_message):
                raise app_not_debuggable_error(package)
            raise bridge_not_running_error(f"attach RPC error: {error_message}")

        vm_name = str(result.get("vm_name", ""))
        vm_version = str(result.get("vm_version", ""))
        thread_count_raw = result.get("thread_count")
        thread_count = thread_count_raw if isinstance(thread_count_raw, int) else None
        suspended_raw = result.get("suspended")
        suspended = suspended_raw if isinstance(suspended_raw, bool) else None

        ds = DebugSessionState(
            session_id=session_id,
            package=package,
            process_name=selected_process_name,
            pid=pid,
            jdwp_port=pid,  # JDWP target identifier for adb forward is jdwp:<pid>.
            local_forward_port=local_port,
            device_serial=device_serial,
            state="attached",
            vm_name=vm_name,
            vm_version=vm_version,
        )
        self._debug_sessions[session_id] = ds
        self._event_queues[session_id] = []

        self._event_tasks[session_id] = asyncio.create_task(
            self._monitor_events(session_id, bridge, adb_device)
        )

        logger.info(
            "debug_attached",
            session_id=session_id,
            package=package,
            process_name=selected_process_name,
            pid=pid,
            local_port=local_port,
        )

        return {
            "status": "attached",
            "session_id": session_id,
            "package": package,
            "process_name": selected_process_name,
            "pid": pid,
            "local_port": local_port,
            "vm": vm_name,
            "vm_name": vm_name,
            "vm_version": vm_version,
            "threads": thread_count,
            "thread_count": thread_count,
            "suspended": suspended,
        }

    async def detach(self, session_id: str, adb_device: Any) -> dict[str, Any]:
        """Detach the debugger from a session."""
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
            remediation = self._disconnect_remediation(ds.disconnect_reason)
            return {
                "status": "disconnected",
                "session_id": session_id,
                "package": ds.package,
                "process_name": ds.process_name,
                "pid": ds.pid,
                "reason": ds.disconnect_reason,
                "detail": ds.disconnect_detail,
                "remediation": remediation,
            }

        bridge = self._bridges.get(session_id)
        if bridge and bridge.is_alive:
            try:
                result = await bridge.request("status")
                suspended_raw = result.get("suspended")
                suspended = suspended_raw if isinstance(suspended_raw, bool) else None
                thread_count_raw = result.get("thread_count")
                thread_count = thread_count_raw if isinstance(thread_count_raw, int) else None
                return {
                    "status": result.get("status", "attached"),
                    "session_id": session_id,
                    "package": ds.package,
                    "process_name": ds.process_name,
                    "pid": ds.pid,
                    "local_port": ds.local_forward_port,
                    "vm_name": result.get("vm_name", ds.vm_name),
                    "vm_version": result.get("vm_version", ds.vm_version),
                    "thread_count": thread_count,
                    "suspended": suspended,
                }
            except Exception:
                pass

        return {
            "status": ds.state,
            "session_id": session_id,
            "package": ds.package,
            "process_name": ds.process_name,
            "pid": ds.pid,
            "local_port": ds.local_forward_port,
        }

    async def set_breakpoint(
        self,
        session_id: str,
        class_pattern: str,
        line: int,
    ) -> dict[str, Any]:
        """Set a breakpoint by class pattern and line number."""
        bridge = await self.get_bridge(session_id)
        result = await bridge.request(
            "set_breakpoint",
            {"class_pattern": class_pattern, "line": line},
        )
        return self._ensure_bridge_result(
            result,
            method="set_breakpoint",
            error_context={"class_pattern": class_pattern, "line": line},
        )

    async def remove_breakpoint(self, session_id: str, breakpoint_id: int) -> dict[str, Any]:
        """Remove a breakpoint by ID."""
        bridge = await self.get_bridge(session_id)
        result = await bridge.request(
            "remove_breakpoint",
            {"breakpoint_id": breakpoint_id},
        )
        return self._ensure_bridge_result(
            result,
            method="remove_breakpoint",
            error_context={"breakpoint_id": breakpoint_id},
        )

    async def list_breakpoints(self, session_id: str) -> dict[str, Any]:
        """List breakpoints for an attached debug session."""
        bridge = await self.get_bridge(session_id)
        result = await bridge.request("list_breakpoints")
        mapped = self._ensure_bridge_result(result, method="list_breakpoints")
        return {"status": "attached", **mapped}

    async def list_threads(
        self,
        session_id: str,
        *,
        include_daemon: bool = False,
        max_threads: int = 20,
    ) -> dict[str, Any]:
        """List VM threads with bounded output."""
        bridge = await self.get_bridge(session_id)
        result = await bridge.request(
            "list_threads",
            {"include_daemon": include_daemon, "max_threads": max_threads},
        )
        mapped = self._ensure_bridge_result(result, method="list_threads")
        return {"status": "attached", **mapped}

    async def stack_trace(
        self,
        session_id: str,
        *,
        thread_name: str = "main",
        max_frames: int = 10,
    ) -> dict[str, Any]:
        """Return stack trace for a thread with coroutine frame filtering."""
        bridge = await self.get_bridge(session_id)
        result = await bridge.request(
            "stack_trace",
            {"thread_name": thread_name, "max_frames": max_frames},
        )
        return self._ensure_bridge_result(result, method="stack_trace")

    async def inspect_variable(
        self,
        session_id: str,
        *,
        variable_path: str,
        thread_name: str = "main",
        frame_index: int = 0,
        depth: int = 1,
    ) -> dict[str, Any]:
        """Inspect a variable path at a stack frame."""
        bridge = await self.get_bridge(session_id)
        result = await bridge.request(
            "inspect_variable",
            {
                "thread_name": thread_name,
                "frame_index": frame_index,
                "variable_path": variable_path,
                "depth": depth,
            },
        )
        return self._ensure_bridge_result(result, method="inspect_variable")

    async def evaluate(
        self,
        session_id: str,
        *,
        expression: str,
        thread_name: str = "main",
        frame_index: int = 0,
    ) -> dict[str, Any]:
        """Evaluate a constrained expression at a stack frame."""
        bridge = await self.get_bridge(session_id)
        result = await bridge.request(
            "evaluate",
            {
                "thread_name": thread_name,
                "frame_index": frame_index,
                "expression": expression,
            },
        )
        return self._ensure_bridge_result(result, method="evaluate")

    async def load_mapping(self, session_id: str, *, path: str) -> dict[str, Any]:
        """Load a ProGuard/R8 mapping file into the attached bridge session."""
        bridge = await self.get_bridge(session_id)
        result = await bridge.request("load_mapping", {"path": path})
        return self._ensure_bridge_result(result, method="load_mapping")

    async def clear_mapping(self, session_id: str) -> dict[str, Any]:
        """Clear any loaded ProGuard/R8 mapping from the attached bridge session."""
        bridge = await self.get_bridge(session_id)
        result = await bridge.request("clear_mapping")
        return self._ensure_bridge_result(result, method="clear_mapping")

    async def step_over(
        self,
        session_id: str,
        *,
        thread_name: str = "main",
        timeout_seconds: float = 10.0,
    ) -> dict[str, Any]:
        """Step over and return the stopped state from bridge atomically."""
        return await self._step(
            session_id=session_id,
            method="step_over",
            thread_name=thread_name,
            timeout_seconds=timeout_seconds,
        )

    async def step_into(
        self,
        session_id: str,
        *,
        thread_name: str = "main",
        timeout_seconds: float = 10.0,
    ) -> dict[str, Any]:
        """Step into and return the stopped state from bridge atomically."""
        return await self._step(
            session_id=session_id,
            method="step_into",
            thread_name=thread_name,
            timeout_seconds=timeout_seconds,
        )

    async def step_out(
        self,
        session_id: str,
        *,
        thread_name: str = "main",
        timeout_seconds: float = 10.0,
    ) -> dict[str, Any]:
        """Step out and return the stopped state from bridge atomically."""
        return await self._step(
            session_id=session_id,
            method="step_out",
            thread_name=thread_name,
            timeout_seconds=timeout_seconds,
        )

    async def resume(
        self,
        session_id: str,
        *,
        thread_name: str | None = None,
    ) -> dict[str, Any]:
        """Resume one thread or all threads on the attached VM."""
        bridge = await self.get_bridge(session_id)
        payload: dict[str, Any] = {}
        if thread_name is not None:
            payload["thread_name"] = thread_name
        result = await bridge.request("resume", payload)
        return self._ensure_bridge_result(
            result,
            method="resume",
            error_context={"thread_name": thread_name},
        )

    async def _step(
        self,
        *,
        session_id: str,
        method: str,
        thread_name: str,
        timeout_seconds: float,
    ) -> dict[str, Any]:
        bridge = await self.get_bridge(session_id)
        result = await bridge.request(
            method,
            {
                "thread_name": thread_name,
                "timeout_seconds": timeout_seconds,
            },
        )
        return self._ensure_bridge_result(
            result,
            method=method,
            error_context={
                "thread_name": thread_name,
                "timeout_seconds": timeout_seconds,
            },
        )

    async def drain_events(self, session_id: str) -> dict[str, Any]:
        """Drain and return queued debugger events for a session."""
        ds = self._debug_sessions.get(session_id)
        if ds is None:
            raise debug_not_attached_error(session_id)

        queue = self._event_queues.setdefault(session_id, [])
        events = list(queue)
        queue.clear()
        return {
            "status": ds.state,
            "session_id": session_id,
            "count": len(events),
            "events": events,
        }

    async def _find_pid(
        self,
        package: str,
        adb_device: Any,
        process_name: str | None = None,
    ) -> tuple[int, str]:
        """Find a debuggable PID for a package, optionally selecting a specific process name."""
        jdwp_pids = await self._list_jdwp_pids(adb_device)
        processes = await self._list_processes(adb_device)

        package_processes = [
            DebuggableProcess(pid=pid, name=name)
            for pid, name in processes.items()
            if name == package or name.startswith(f"{package}:")
        ]
        debuggable_processes = [p for p in package_processes if p.pid in jdwp_pids]

        if process_name:
            for proc in debuggable_processes:
                if proc.name == process_name:
                    return proc.pid, proc.name
            if any(proc.name == process_name for proc in package_processes):
                raise app_not_debuggable_error(package)
            raise process_not_found_error(process_name)

        if not debuggable_processes:
            if package_processes:
                raise app_not_debuggable_error(package)
            raise process_not_found_error(package)

        if len(debuggable_processes) == 1:
            selected = debuggable_processes[0]
            return selected.pid, selected.name

        main_process = [proc for proc in debuggable_processes if proc.name == package]
        if len(main_process) == 1:
            selected = main_process[0]
            logger.info(
                "debug_attach_selected_main_process",
                package=package,
                pid=selected.pid,
                process_name=selected.name,
            )
            return selected.pid, selected.name

        candidates = [
            {"pid": proc.pid, "process_name": proc.name}
            for proc in sorted(debuggable_processes, key=lambda p: p.pid)
        ]
        raise AgentError(
            code="ERR_MULTIPLE_DEBUGGABLE_PROCESSES",
            message=f"Multiple debuggable processes found for {package}",
            context={"package": package, "candidates": candidates},
            remediation="Retry with 'debug attach --process <process_name>'.",
        )

    async def _list_jdwp_pids(self, adb_device: Any) -> set[int]:
        """Return the set of PIDs currently available via adb jdwp."""
        raw_output = ""
        try:
            raw_output = await asyncio.to_thread(self._read_jdwp_list, adb_device)
        except Exception as exc:
            logger.warning("jdwp_list_failed", error=str(exc))

        if not raw_output:
            serial = str(getattr(adb_device, "serial", "")).strip()
            if serial:
                try:
                    raw_output = await asyncio.to_thread(self._read_jdwp_list_via_adb, serial)
                except Exception as exc:
                    logger.warning("jdwp_cli_list_failed", serial=serial, error=str(exc))

        pids: set[int] = set()
        for token in raw_output.split():
            if token.isdigit():
                pids.add(int(token))
        return pids

    @staticmethod
    def _read_jdwp_list(adb_device: Any) -> str:
        with adb_device.open_transport("jdwp") as connection:
            raw = connection.read_string_block()
            if isinstance(raw, bytes):
                return raw.decode(errors="ignore")
            return str(raw)

    @staticmethod
    def _read_jdwp_list_via_adb(serial: str) -> str:
        """Fallback JDWP listing via adb CLI.

        `adb jdwp` prints the current PID list quickly and then blocks as a tracker stream.
        We intentionally use a short timeout and parse partial stdout from TimeoutExpired.
        """
        adb_path = shutil.which("adb")
        if not adb_path:
            return ""

        try:
            proc = subprocess.run(
                [adb_path, "-s", serial, "jdwp"],
                check=False,
                capture_output=True,
                text=True,
                timeout=1.0,
            )
        except subprocess.TimeoutExpired as exc:
            partial = exc.stdout or ""
            if isinstance(partial, bytes):
                return partial.decode(errors="ignore")
            return str(partial)

        output = proc.stdout or ""
        if proc.returncode != 0 and not output.strip():
            reason = (proc.stderr or "adb jdwp failed").strip()
            raise RuntimeError(reason)
        return output

    async def _list_processes(self, adb_device: Any) -> dict[int, str]:
        """Return PID -> process name from device process list."""
        compact_output = await asyncio.to_thread(adb_device.shell, "ps -A -o PID,NAME")
        processes = self._parse_compact_ps(compact_output.strip())
        if processes:
            return processes

        legacy_output = await asyncio.to_thread(adb_device.shell, "ps")
        return self._parse_legacy_ps(legacy_output.strip())

    @staticmethod
    def _parse_compact_ps(output: str) -> dict[int, str]:
        processes: dict[int, str] = {}
        for line in output.splitlines():
            text = line.strip()
            if not text or text.upper().startswith("PID"):
                continue
            parts = text.split(maxsplit=1)
            if len(parts) != 2 or not parts[0].isdigit():
                continue
            processes[int(parts[0])] = parts[1]
        return processes

    @staticmethod
    def _parse_legacy_ps(output: str) -> dict[int, str]:
        processes: dict[int, str] = {}
        for line in output.splitlines():
            text = line.strip()
            if not text:
                continue
            parts = text.split()
            if "PID" in parts and "USER" in parts:
                continue
            pid_index = -1
            if parts and parts[0].isdigit():
                pid_index = 0
            elif len(parts) > 1 and parts[1].isdigit():
                pid_index = 1
            if pid_index < 0:
                continue
            processes[int(parts[pid_index])] = parts[-1]
        return processes

    async def _setup_forward(self, pid: int, adb_device: Any) -> int:
        """Set up ADB forward from a local port to jdwp:<pid>. Returns local port."""
        try:
            local_port = await asyncio.to_thread(adb_device.forward_port, f"jdwp:{pid}")
            return int(local_port)
        except Exception as exc:
            raise adb_forward_failed_error(pid, str(exc)) from None

    async def _remove_forward(self, local_port: int, adb_device: Any) -> None:
        """Remove an ADB forward rule."""
        with contextlib.suppress(Exception):
            await asyncio.to_thread(adb_device.forward_remove, f"tcp:{local_port}", False)

    async def _cleanup_session(self, session_id: str, adb_device: Any) -> None:
        """Clean up all resources for a debug session."""
        task = self._event_tasks.pop(session_id, None)
        if task and not task.done():
            task.cancel()

        ds = self._debug_sessions.pop(session_id, None)
        if ds:
            await self._remove_forward(ds.local_forward_port, adb_device)
        self._event_queues.pop(session_id, None)

        await self.stop_bridge(session_id)

    async def _monitor_events(self, session_id: str, bridge: BridgeClient, adb_device: Any) -> None:
        """Background task consuming bridge event queue for VM disconnect."""
        try:
            while True:
                event = await bridge.next_event()
                method = event.get("method")
                params = event.get("params", {})
                params_obj = params if isinstance(params, dict) else {}
                event_type = ""
                if isinstance(method, str) and method != "event":
                    event_type = method
                if method == "event":
                    event_type = str(params_obj.get("type", ""))

                if event_type in {"breakpoint_hit", "breakpoint_resolved"}:
                    self._queue_event(session_id, params_obj, event_type=event_type)
                    logger.info(
                        "debug_event_queued",
                        session_id=session_id,
                        type=event_type,
                    )
                    continue

                is_disconnect = method == "vm_disconnected" or (
                    method == "event" and params_obj.get("type") == "vm_disconnected"
                )
                if not is_disconnect:
                    continue

                raw_reason = str(params_obj.get("detail", params_obj.get("reason", "unknown")))
                normalized_reason = self._normalize_disconnect_reason(
                    str(params_obj.get("reason", raw_reason))
                )
                logger.warning(
                    "vm_disconnected",
                    session_id=session_id,
                    reason=normalized_reason,
                    detail=raw_reason,
                )
                self._queue_event(
                    session_id,
                    {"reason": normalized_reason, "detail": raw_reason},
                    event_type="vm_disconnected",
                )

                ds = self._debug_sessions.get(session_id)
                if ds:
                    ds.state = "disconnected"
                    ds.disconnect_reason = normalized_reason
                    ds.disconnect_detail = raw_reason
                    await self._remove_forward(ds.local_forward_port, adb_device)

                await self.stop_bridge(session_id)
                break
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception("event_monitor_error", session_id=session_id)

    def _queue_event(
        self,
        session_id: str,
        payload: dict[str, Any],
        *,
        event_type: str,
    ) -> None:
        """Append a normalized event payload to the per-session event queue."""
        queue = self._event_queues.setdefault(session_id, [])
        event = {"type": event_type}
        event.update({k: v for k, v in payload.items() if k != "type"})
        queue.append(event)

    @staticmethod
    def _looks_not_debuggable(message: str) -> bool:
        lowered = message.lower()
        markers = (
            "app_not_debuggable",
            "not debuggable",
            "handshake failed",
            "jdwp",
            "connection is closed",
            "prematurely closed",
        )
        return any(marker in lowered for marker in markers)

    @staticmethod
    def _normalize_disconnect_reason(reason: str) -> str:
        lowered = reason.lower()
        if reason in {"app_crashed", "app_killed", "device_disconnected"}:
            return reason
        if any(token in lowered for token in ("transport", "device offline", "connection reset")):
            return "device_disconnected"
        if any(token in lowered for token in ("killed", "terminated", "force stop")):
            return "app_killed"
        return "app_crashed"

    @staticmethod
    def _disconnect_remediation(reason: str) -> str:
        if reason == "app_crashed":
            return "The app crashed. Relaunch it and attach again."
        if reason == "app_killed":
            return "The app process exited. Relaunch it and attach again."
        if reason == "device_disconnected":
            return "Reconnect the device/emulator, relaunch the app, then attach again."
        return "Reattach with 'debug attach --session <id> --package <pkg>'."

    @staticmethod
    def _ensure_bridge_result(
        result: Any,
        *,
        method: str,
        error_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Return a bridge result dict or raise a mapped AgentError for RPC failures."""
        if not isinstance(result, dict):
            raise bridge_not_running_error(f"Invalid {method} response from bridge")

        error_obj = result.get("error")
        if error_obj is None:
            return result

        if isinstance(error_obj, dict):
            message = str(error_obj.get("message", error_obj))
            code = error_obj.get("code")
        else:
            message = str(error_obj)
            code = None

        bridge_context = {
            "method": method,
            "bridge_code": code,
            "bridge_message": message,
        }
        if error_context:
            bridge_context.update(error_context)

        def _attach_context(error: AgentError) -> AgentError:
            return AgentError(
                code=error.code,
                message=error.message,
                context={**error.context, **bridge_context},
                remediation=error.remediation,
            )

        lowered = message.lower()
        if "object_collected" in lowered or "err_object_collected" in lowered:
            raise _attach_context(object_collected_error())
        if "not_suspended" in lowered or "err_not_suspended" in lowered:
            thread_name = None
            if error_context is not None:
                thread = error_context.get("thread_name")
                if isinstance(thread, str) and thread:
                    thread_name = thread
            raise _attach_context(not_suspended_error(thread_name))
        if "err_step_timeout" in lowered or "did not complete within" in lowered:
            thread_name = "main"
            timeout_seconds = 10.0
            if error_context is not None:
                thread = error_context.get("thread_name")
                if isinstance(thread, str) and thread:
                    thread_name = thread
                timeout_raw = error_context.get("timeout_seconds")
                if isinstance(timeout_raw, int | float):
                    timeout_seconds = float(timeout_raw)
            action = method.replace("_", "-")
            raise _attach_context(step_timeout_error(action, thread_name, timeout_seconds))
        if "err_class_not_found" in lowered or "class not found" in lowered:
            class_pattern = ""
            if error_context is not None:
                pattern = error_context.get("class_pattern")
                if isinstance(pattern, str):
                    class_pattern = pattern
            raise _attach_context(class_not_found_error(class_pattern))
        if "err_breakpoint_invalid_line" in lowered or "no executable code" in lowered:
            class_pattern = ""
            line = -1
            if error_context is not None:
                pattern = error_context.get("class_pattern")
                if isinstance(pattern, str):
                    class_pattern = pattern
                line_raw = error_context.get("line")
                if isinstance(line_raw, int):
                    line = line_raw
            raise _attach_context(breakpoint_invalid_line_error(class_pattern, line))
        if "unsupported expression" in lowered or "err_eval_unsupported" in lowered:
            raise _attach_context(
                AgentError(
                    code="ERR_EVAL_UNSUPPORTED",
                    message="Unsupported debug expression",
                    remediation="Use field access (a.b.c) or toString() calls only.",
                )
            )

        raise bridge_not_running_error(f"{method} RPC error: {message}")
