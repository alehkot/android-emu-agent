"""JSON-RPC client for communicating with a JDI Bridge subprocess."""

from __future__ import annotations

import asyncio
import contextlib
import json
from pathlib import Path
from typing import Any

import structlog

from android_emu_agent.errors import bridge_crashed_error

logger = structlog.get_logger()


class BridgeClient:
    """Manages a single JDI Bridge subprocess and speaks JSON-RPC 2.0 over stdin/stdout."""

    def __init__(self, java_path: Path, jar_path: Path) -> None:
        self._java_path = java_path
        self._jar_path = jar_path
        self._process: asyncio.subprocess.Process | None = None
        self._request_id = 0
        self._lock = asyncio.Lock()
        self._pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._stderr_task: asyncio.Task[None] | None = None
        self._stdout_task: asyncio.Task[None] | None = None
        self._event_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    @property
    def is_alive(self) -> bool:
        """Check if the bridge subprocess is running."""
        return self._process is not None and self._process.returncode is None

    async def start(self) -> None:
        """Spawn the bridge subprocess and start reader loops."""
        if self.is_alive:
            return

        self._process = await asyncio.create_subprocess_exec(
            str(self._java_path),
            "--add-modules",
            "jdk.jdi",
            "-jar",
            str(self._jar_path),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        logger.info(
            "bridge_started",
            pid=self._process.pid,
            jar=str(self._jar_path),
        )
        self._stdout_task = asyncio.create_task(self._read_stdout_loop())
        self._stderr_task = asyncio.create_task(self._read_stderr_loop())

    async def stop(self) -> None:
        """Gracefully stop the bridge subprocess."""
        if not self.is_alive or self._process is None:
            return

        # Try graceful shutdown first
        with contextlib.suppress(Exception):
            await asyncio.wait_for(self.request("shutdown"), timeout=2.0)

        # Wait for process to exit
        try:
            await asyncio.wait_for(self._process.wait(), timeout=3.0)
        except TimeoutError:
            logger.warning("bridge_kill", pid=self._process.pid)
            self._process.kill()
            await self._process.wait()

        # Cancel reader tasks
        for task in (self._stdout_task, self._stderr_task):
            if task and not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

        # Fail any pending requests
        for future in self._pending.values():
            if not future.done():
                future.set_exception(bridge_crashed_error("bridge stopped"))
        self._pending.clear()

        logger.info("bridge_stopped", pid=self._process.pid)
        self._process = None

    async def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Send a JSON-RPC request and wait for the response."""
        if not self.is_alive or self._process is None or self._process.stdin is None:
            raise bridge_crashed_error("bridge process not running")

        async with self._lock:
            self._request_id += 1
            req_id = self._request_id

        msg = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params or {},
        }

        loop = asyncio.get_event_loop()
        future: asyncio.Future[dict[str, Any]] = loop.create_future()
        self._pending[req_id] = future

        line = json.dumps(msg, ensure_ascii=True) + "\n"
        self._process.stdin.write(line.encode())
        await self._process.stdin.drain()

        try:
            return await asyncio.wait_for(future, timeout=30.0)
        except TimeoutError:
            self._pending.pop(req_id, None)
            raise bridge_crashed_error("request timed out") from None

    async def ping(self) -> dict[str, Any]:
        """Send a ping request to verify the bridge is responsive."""
        return await self.request("ping")

    async def _read_stdout_loop(self) -> None:
        """Read JSON-RPC responses and notifications from bridge stdout."""
        assert self._process is not None and self._process.stdout is not None
        try:
            while True:
                raw = await self._process.stdout.readline()
                if not raw:
                    break  # EOF

                line = raw.decode().strip()
                if not line:
                    continue

                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    logger.warning("bridge_stdout_invalid_json", line=line[:200])
                    continue

                req_id = data.get("id")
                if req_id is not None and req_id in self._pending:
                    future = self._pending.pop(req_id)
                    if not future.done():
                        if "error" in data and data["error"] is not None:
                            future.set_result(data)
                        else:
                            future.set_result(data.get("result", {}))
                else:
                    # Notification (no id or unknown id)
                    await self._event_queue.put(data)

        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception("bridge_stdout_loop_error")
        finally:
            # Bridge stdout closed — fail all pending requests
            for future in self._pending.values():
                if not future.done():
                    future.set_exception(bridge_crashed_error("bridge stdout closed"))
            self._pending.clear()

    async def _read_stderr_loop(self) -> None:
        """Read log lines from bridge stderr and forward to structlog."""
        assert self._process is not None and self._process.stderr is not None
        try:
            while True:
                raw = await self._process.stderr.readline()
                if not raw:
                    break
                line = raw.decode().rstrip()
                if line:
                    logger.debug("bridge_log", message=line)
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception("bridge_stderr_loop_error")
