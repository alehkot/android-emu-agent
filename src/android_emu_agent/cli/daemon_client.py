"""Daemon control and HTTP client for CLI commands."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import httpx

STATE_DIR = Path.home() / ".android-emu-agent"
SOCKET_PATH = Path("/tmp/android-emu-agent.sock")
PID_FILE = STATE_DIR / "daemon.pid"
LOG_FILE = STATE_DIR / "daemon.log"
BASE_URL = "http://android-emu-agent"


class DaemonController:
    """Start/stop/status for the daemon process."""

    def __init__(self, socket_path: Path = SOCKET_PATH) -> None:
        self.socket_path = socket_path
        STATE_DIR.mkdir(parents=True, exist_ok=True)

    def _pid_running(self, pid: int) -> bool:
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True

    def _read_pid(self) -> int | None:
        if not PID_FILE.exists():
            return None
        try:
            return int(PID_FILE.read_text().strip())
        except ValueError:
            return None

    def _socket_healthy(self) -> bool:
        if not self.socket_path.exists():
            return False
        client = httpx.Client(
            transport=httpx.HTTPTransport(uds=str(self.socket_path)),
            base_url=BASE_URL,
            timeout=1.0,
        )
        try:
            resp = client.get("/health")
            return resp.status_code == 200
        except httpx.HTTPError:
            return False
        finally:
            client.close()

    def health(self) -> bool:
        """Return True if the daemon socket responds to /health."""
        return self._socket_healthy()

    def start(self) -> int:
        """Start the daemon; returns PID, or -1 if already running but PID unknown."""
        pid = self._read_pid()
        if pid and self._pid_running(pid):
            return pid
        if pid:
            PID_FILE.unlink(missing_ok=True)
        if self._socket_healthy():
            return -1

        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        args = [
            sys.executable,
            "-m",
            "uvicorn",
            "android_emu_agent.daemon.server:app",
            "--uds",
            str(self.socket_path),
            "--log-level",
            "info",
        ]
        with LOG_FILE.open("a", encoding="utf-8") as log_handle:
            proc = subprocess.Popen(
                args,
                stdout=log_handle,
                stderr=log_handle,
                start_new_session=True,
            )
        PID_FILE.write_text(str(proc.pid))
        return proc.pid

    def stop(self) -> bool:
        """Stop the daemon if running."""
        pid = self._read_pid()
        if not pid:
            return False
        if not self._pid_running(pid):
            PID_FILE.unlink(missing_ok=True)
            return False

        os.kill(pid, signal.SIGTERM)
        for _ in range(20):
            if not self._pid_running(pid):
                PID_FILE.unlink(missing_ok=True)
                return True
            time.sleep(0.1)
        return False

    def status(self) -> dict[str, Any]:
        """Return daemon status summary."""
        pid = self._read_pid()
        return {
            "pid": pid,
            "pid_running": self._pid_running(pid) if pid else False,
            "socket": str(self.socket_path),
            "socket_exists": self.socket_path.exists(),
        }


class DaemonClient:
    """HTTP client using Unix Domain Socket transport."""

    def __init__(
        self,
        socket_path: Path = SOCKET_PATH,
        *,
        auto_start: bool = True,
        timeout: float = 10.0,
    ) -> None:
        self.socket_path = socket_path
        self.auto_start = auto_start
        self.controller = DaemonController(socket_path)
        self._client = httpx.Client(
            transport=httpx.HTTPTransport(uds=str(self.socket_path)),
            base_url=BASE_URL,
            timeout=timeout,
        )

    def close(self) -> None:
        self._client.close()

    def request(
        self, method: str, path: str, json_body: dict[str, Any] | None = None
    ) -> httpx.Response:
        if self.auto_start:
            self._ensure_ready()

        try:
            return self._client.request(method, path, json=json_body)
        except httpx.TransportError:
            if not self.auto_start:
                raise
            self.controller.start()
            self._wait_for_health()
            return self._client.request(method, path, json=json_body)

    def _ensure_ready(self) -> None:
        try:
            resp = self._client.get("/health")
            if resp.status_code == 200:
                return
        except httpx.TransportError:
            pass
        self.controller.start()
        self._wait_for_health()

    def _wait_for_health(self) -> None:
        deadline = time.time() + 5
        while time.time() < deadline:
            try:
                resp = self._client.get("/health")
                if resp.status_code == 200:
                    return
            except httpx.TransportError:
                pass
            time.sleep(0.1)
        raise RuntimeError("Daemon did not become healthy in time")


def format_json(data: Any) -> str:
    return json.dumps(data, indent=2, ensure_ascii=True)
