"""Artifact manager - Screenshots, logs, and debug bundles."""

from __future__ import annotations

import asyncio
import re
import shlex
import zipfile
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

import structlog

from android_emu_agent.device.io import run_device_io
from android_emu_agent.errors import AgentError, log_follow_unsupported_error
from android_emu_agent.security import ensure_private_directory, ensure_private_file
from android_emu_agent.utils.time_parser import parse_datetime

if TYPE_CHECKING:
    import uiautomator2 as u2

logger = structlog.get_logger()

LOG_PRIORITY_ALIASES = {
    "v": "V",
    "verbose": "V",
    "d": "D",
    "debug": "D",
    "i": "I",
    "info": "I",
    "w": "W",
    "warn": "W",
    "warning": "W",
    "warnings": "W",
    "e": "E",
    "error": "E",
    "errors": "E",
    "f": "F",
    "fatal": "F",
    "fatals": "F",
    "wtf": "F",
    "s": "S",
    "silent": "S",
}

_LOGCAT_TIMESTAMP_RE = re.compile(
    r"^(?:\d{2}-\d{2}|\d{4}-\d{2}-\d{2})\s+\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?$"
)
_RELATIVE_SHORT_RE = re.compile(r"^(\d+)\s*(m|min|mins|minutes?|h|hr|hours?|d|days?)$")


def normalize_log_priority(value: str | None) -> str | None:
    """Normalize log level/type aliases into logcat priority letters."""
    if not value:
        return None
    return LOG_PRIORITY_ALIASES.get(value.strip().lower())


def resolve_logcat_since(since: str | int | None) -> tuple[str | None, bool]:
    """Resolve user-friendly logcat --since into a command-ready value.

    Returns (value, is_datetime), where value is ready for logcat -t/-T.
    """
    if since is None:
        return None, False

    raw_value = str(since).strip()
    if not raw_value:
        return None, False

    # Preserve legacy behavior: integers are treated as line counts.
    if raw_value.isdigit():
        return raw_value, False

    if _LOGCAT_TIMESTAMP_RE.fullmatch(raw_value):
        return raw_value, True

    parse_input = raw_value
    short_relative = _RELATIVE_SHORT_RE.fullmatch(raw_value.lower())
    if short_relative:
        parse_input = f"{short_relative.group(1)} {short_relative.group(2)} ago"

    try:
        since_ms = parse_datetime(parse_input)
    except AgentError as exc:
        raise AgentError(
            code="ERR_INVALID_LOGCAT_SINCE",
            message=f"Invalid logcat since value: {since}",
            context={"since": since},
            remediation=(
                "Use line count (e.g. 200), logcat timestamp (MM-DD HH:MM:SS.mmm), "
                "ISO 8601, or relative time (e.g. '10m ago')."
            ),
        ) from exc

    if since_ms is None:  # Defensive; parse_datetime currently returns int for non-empty values.
        return None, False

    # Logcat accepts fractional epoch seconds. A host-local wall time would be
    # interpreted in the device timezone, shifting this absolute lower bound.
    seconds, milliseconds = divmod(since_ms, 1000)
    return f"{seconds}.{milliseconds:03d}", True


class ArtifactManager:
    """Manages artifact capture and storage.

    Automatically named captures use independent UUIDs so repeated or concurrent
    requests never share a path merely because they occur in the same second.
    Explicit filenames retain their caller-selected replacement semantics.
    """

    def __init__(self, output_dir: Path | None = None) -> None:
        default_dir = Path.home() / ".android-emu-agent" / "artifacts"
        self.output_dir = output_dir or default_dir
        if output_dir is None:
            ensure_private_directory(self.output_dir)
        else:
            self.output_dir.mkdir(parents=True, exist_ok=True)

    async def screenshot(
        self,
        device: u2.Device,
        session_id: str,
        filename: str | None = None,
    ) -> Path:
        """Capture a screenshot from device."""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{session_id}_{timestamp}_{uuid4().hex}.png"

        output_path = self.output_dir / filename

        # uiautomator2 returns PIL Image
        image = await run_device_io(device, device.screenshot)
        if image is None:
            raise RuntimeError("Failed to capture screenshot from device")
        await asyncio.to_thread(image.save, str(output_path))
        ensure_private_file(output_path)

        logger.info("screenshot_captured", path=str(output_path))
        return output_path

    async def pull_logs(
        self,
        device: u2.Device,
        session_id: str,
        package: str | None = None,
        level: str | None = None,
        since: str | int | None = None,
        follow: bool = False,
        filename: str | None = None,
    ) -> Path:
        """Pull logcat logs from device."""
        if follow:
            raise log_follow_unsupported_error()

        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{session_id}_{timestamp}_{uuid4().hex}_logcat.txt"

        output_path = self.output_dir / filename

        def _pull() -> str:
            cmd_parts = ["logcat", "-d"]
            resolved_since, _since_is_datetime = resolve_logcat_since(since)
            if resolved_since:
                cmd_parts.extend(["-t", resolved_since])

            normalized_level = normalize_log_priority(level)
            if normalized_level:
                cmd_parts.append(f"*:{normalized_level}")

            package_pid: str | None = None
            pid_filter_used = False
            if package:
                pid_result = device.shell(f"pidof {shlex.quote(package)}")
                pid_output = getattr(pid_result, "output", None)
                pid_raw = pid_output if isinstance(pid_output, str) else str(pid_result)
                first_pid = pid_raw.strip().split(" ")[0] if pid_raw.strip() else ""
                if first_pid.isdigit():
                    package_pid = first_pid
                    pid_filter_used = True
                    cmd_parts.append(f"--pid={package_pid}")

            cmd = " ".join(shlex.quote(part) for part in cmd_parts)
            result = device.shell(cmd)
            output = getattr(result, "output", None)
            raw_output = output if isinstance(output, str) else str(result)

            # Some devices don't support --pid; retry without it.
            if package_pid and "unknown option --pid" in raw_output.lower():
                fallback_parts = [part for part in cmd_parts if not part.startswith("--pid=")]
                fallback_cmd = " ".join(shlex.quote(part) for part in fallback_parts)
                fallback_result = device.shell(fallback_cmd)
                fallback_output = getattr(fallback_result, "output", None)
                raw_output = (
                    fallback_output if isinstance(fallback_output, str) else str(fallback_result)
                )
                pid_filter_used = False

            if package and not pid_filter_used:
                filtered = [line for line in raw_output.splitlines() if package in line]
                return "\n".join(filtered)

            return raw_output

        logs = await run_device_io(device, _pull)
        output_path.write_text(logs, encoding="utf-8")
        ensure_private_file(output_path)

        logger.info("logs_pulled", path=str(output_path), size=len(logs))
        return output_path

    @staticmethod
    def _normalize_log_level(level: str | None) -> str | None:
        return normalize_log_priority(level)

    async def save_snapshot(
        self,
        snapshot_json: str,
        session_id: str,
        generation: int,
    ) -> Path:
        """Save a snapshot to disk."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{session_id}_gen{generation}_{timestamp}_{uuid4().hex}.json"
        output_path = self.output_dir / filename

        output_path.write_text(snapshot_json, encoding="utf-8")
        ensure_private_file(output_path)
        logger.info("snapshot_saved", path=str(output_path))
        return output_path

    async def create_debug_bundle(
        self,
        device: u2.Device,
        session_id: str,
        snapshot_json: str | None = None,
    ) -> Path:
        """Create a debug bundle with screenshot, logs, and snapshot."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        bundle_name = f"{session_id}_{timestamp}_{uuid4().hex}_debug.zip"
        bundle_path = self.output_dir / bundle_name

        # Collect artifacts
        screenshot_path = await self.screenshot(device, session_id)
        logs_path = await self.pull_logs(device, session_id)

        # Create zip bundle
        def _create_zip() -> None:
            with zipfile.ZipFile(bundle_path, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.write(screenshot_path, screenshot_path.name)
                zf.write(logs_path, logs_path.name)
                if snapshot_json:
                    zf.writestr("snapshot.json", snapshot_json)
                # Add metadata
                metadata = f"session_id: {session_id}\ntimestamp: {timestamp}\n"
                zf.writestr("metadata.txt", metadata)

        await asyncio.to_thread(_create_zip)
        ensure_private_file(bundle_path)

        # Cleanup temp files
        screenshot_path.unlink(missing_ok=True)
        logs_path.unlink(missing_ok=True)

        logger.info("debug_bundle_created", path=str(bundle_path))
        return bundle_path
