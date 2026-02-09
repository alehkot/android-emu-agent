"""Reliability manager - ADB diagnostics and forensics commands."""

from __future__ import annotations

import asyncio
import re
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import structlog

from android_emu_agent.errors import (
    AgentError,
    adb_command_error,
    adb_not_found_error,
    permission_error,
    process_not_found_error,
)

if TYPE_CHECKING:
    from adbutils import AdbDevice

logger = structlog.get_logger()

DEFAULT_EVENTS_PATTERN = r"am_proc_died|am_anr|am_crash|am_low_memory|wm_on_paused|wm_on_resumed"

TRIM_LEVELS = {
    "RUNNING_MODERATE",
    "RUNNING_LOW",
    "RUNNING_CRITICAL",
    "UI_HIDDEN",
    "BACKGROUND",
    "MODERATE",
    "COMPLETE",
}


@dataclass(frozen=True)
class CommandOutput:
    output: str
    line_count: int
    total_lines: int


class ReliabilityManager:
    """Runs reliability diagnostics via ADB."""

    def __init__(self, output_dir: Path | None = None) -> None:
        default_dir = Path.home() / ".android-emu-agent" / "artifacts" / "reliability"
        self.output_dir = output_dir or default_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def exit_info(self, device: AdbDevice, package: str) -> str:
        return await self._shell(device, f"dumpsys activity exit-info {package}")

    async def bugreport(self, serial: str, filename: str | None = None) -> Path:
        timestamp = self._timestamp()
        name = filename or f"bugreport_{serial}_{timestamp}.zip"
        if not name.endswith(".zip"):
            name = f"{name}.zip"
        output_path = self.output_dir / name
        await self._run_adb(serial, ["bugreport", str(output_path)])
        logger.info("bugreport_saved", serial=serial, path=str(output_path))
        return output_path

    async def logcat_events(
        self, device: AdbDevice, pattern: str | None, since: str | None
    ) -> CommandOutput:
        cmd = "logcat -b events -d"
        if since:
            cmd += f" -t {shlex.quote(since)}"
        output = await self._shell(device, cmd)
        lines = output.splitlines()
        if pattern:
            try:
                regex = re.compile(pattern)
            except re.error as exc:  # pragma: no cover - depends on user input
                raise AgentError(
                    code="ERR_INVALID_PATTERN",
                    message=f"Invalid regex pattern: {pattern}",
                    context={"pattern": pattern},
                    remediation="Provide a valid regex for --pattern",
                ) from exc
            filtered = [line for line in lines if regex.search(line)]
        else:
            filtered = lines
        return CommandOutput(
            output="\n".join(filtered),
            line_count=len(filtered),
            total_lines=len(lines),
        )

    async def dropbox_list(self, device: AdbDevice, package: str | None) -> str:
        output = await self._shell(device, "dumpsys dropbox")
        if package:
            filtered = [line for line in output.splitlines() if package in line]
            return "\n".join(filtered)
        return output

    async def dropbox_print(self, device: AdbDevice, tag: str) -> str:
        return await self._shell(device, f"dumpsys dropbox --print {tag}")

    async def background_restrictions(self, device: AdbDevice, package: str) -> dict[str, str]:
        appops = await self._shell(device, f"cmd appops get {package} RUN_IN_BACKGROUND")
        standby = await self._shell(device, f"am get-standby-bucket {package}")
        return {"appops": appops, "standby_bucket": standby}

    async def last_anr(self, device: AdbDevice) -> str:
        output = await self._shell(device, "dumpsys activity lastanr")
        if not output.strip() or "Unknown command" in output:
            output = await self._shell(device, "dumpsys activity anr")
        return output

    async def jobscheduler(self, device: AdbDevice, package: str) -> str:
        return await self._shell(device, f"dumpsys jobscheduler {package}")

    async def process_info(self, device: AdbDevice, package: str) -> dict[str, str | int]:
        pid = await self._pidof(device, package)
        pid_str = str(pid)
        ps = await self._shell(device, f"ps -A | grep -F {shlex.quote(package)}")
        oom_adj = await self._shell(device, f"cat /proc/{pid_str}/oom_score_adj")
        proc_state = await self._shell(
            device, f"dumpsys activity processes | grep -m 20 -A 3 -F {shlex.quote(package)}"
        )
        return {
            "pid": pid,
            "oom_score_adj": oom_adj.strip(),
            "ps": ps,
            "process_state": proc_state,
        }

    async def meminfo(self, device: AdbDevice, package: str) -> str:
        return await self._shell(device, f"dumpsys meminfo {package}")

    async def gfxinfo(self, device: AdbDevice, package: str) -> str:
        return await self._shell(device, f"dumpsys gfxinfo {package}")

    async def compile_package(self, device: AdbDevice, package: str, mode: str) -> str:
        if mode == "reset":
            return await self._shell(device, f"cmd package compile --reset {package}")
        if mode == "speed":
            return await self._shell(device, f"cmd package compile -m speed -f {package}")
        raise AgentError(
            code="ERR_INVALID_MODE",
            message=f"Invalid compile mode: {mode}",
            context={"mode": mode},
            remediation="Use 'reset' or 'speed'",
        )

    async def always_finish_activities(self, device: AdbDevice, enabled: bool) -> str:
        value = "1" if enabled else "0"
        return await self._shell(device, f"settings put global always_finish_activities {value}")

    async def run_as_ls(self, device: AdbDevice, package: str, path: str) -> str:
        safe_path = shlex.quote(path)
        return await self._shell(device, f"run-as {package} ls -R {safe_path}")

    async def dump_heap(
        self,
        device: AdbDevice,
        serial: str,
        package: str,
        keep_remote: bool,
    ) -> Path:
        timestamp = self._timestamp()
        safe_pkg = package.replace(".", "_")
        remote_path = f"/data/local/tmp/{safe_pkg}_{timestamp}.hprof"
        await self._shell(device, f"am dumpheap {package} {remote_path}")

        local_path = self.output_dir / f"heap_{safe_pkg}_{timestamp}.hprof"
        await self._run_adb(serial, ["pull", remote_path, str(local_path)])

        if not keep_remote:
            await self._shell(device, f"rm -f {remote_path}")

        logger.info("heap_dump_saved", serial=serial, path=str(local_path))
        return local_path

    async def sigquit(self, device: AdbDevice, package: str) -> int:
        pid = await self._pidof(device, package)
        await self._shell(device, f"kill -3 {pid}")
        return pid

    async def oom_score_adj(self, device: AdbDevice, package: str, score: int) -> int:
        pid = await self._pidof(device, package)
        await self._shell_su(device, f"echo {score} > /proc/{pid}/oom_score_adj")
        return pid

    async def trim_memory(self, device: AdbDevice, package: str, level: str) -> str:
        return await self._shell(device, f"am send-trim-memory {package} {level}")

    async def pull_root_dir(
        self,
        device: AdbDevice,
        serial: str,
        remote_dir: str,
        name: str,
    ) -> Path:
        stage_parent = "/data/local/tmp/android-emu-agent"
        stage_dir = f"{stage_parent}/{name}"
        stage_cmd = (
            f"rm -rf {stage_dir} && mkdir -p {stage_parent} && cp -r {remote_dir} {stage_parent}"
        )
        await self._shell_su(device, stage_cmd)

        local_path = self.output_dir / f"{serial}_{self._timestamp()}_{name}"
        await self._run_adb(serial, ["pull", stage_dir, str(local_path)])

        await self._shell(device, f"rm -rf {stage_dir}")
        logger.info("root_dir_pulled", serial=serial, remote=remote_dir, local=str(local_path))
        return local_path

    async def _shell(self, device: AdbDevice, command: str) -> str:
        def _run() -> str:
            result = device.shell(command)
            output = getattr(result, "output", None)
            return output if isinstance(output, str) else str(result)

        return await asyncio.to_thread(_run)

    async def _shell_su(self, device: AdbDevice, command: str) -> str:
        return await self._shell(device, f"su -c {shlex.quote(command)}")

    async def _pidof(self, device: AdbDevice, package: str) -> int:
        output = await self._shell(device, f"pidof {package}")
        pid = output.strip().split(" ")[0] if output.strip() else ""
        if not pid.isdigit():
            raise process_not_found_error(package)
        return int(pid)

    async def _run_adb(self, serial: str, args: list[str]) -> subprocess.CompletedProcess[str]:
        def _run() -> subprocess.CompletedProcess[str]:
            adb_path = shutil.which("adb")
            if not adb_path:
                raise adb_not_found_error()
            return subprocess.run(
                [adb_path, "-s", serial, *args],
                check=True,
                capture_output=True,
                text=True,
            )

        try:
            return await asyncio.to_thread(_run)
        except AgentError:
            raise
        except FileNotFoundError as exc:
            raise adb_not_found_error() from exc
        except subprocess.CalledProcessError as exc:
            reason = (exc.stderr or exc.stdout or str(exc)).strip()
            raise adb_command_error(" ".join(args), reason) from exc

    @staticmethod
    def _timestamp() -> str:
        return datetime.now().strftime("%Y%m%d_%H%M%S")


def require_root(is_rooted: bool, operation: str) -> None:
    if not is_rooted:
        raise permission_error(operation)
