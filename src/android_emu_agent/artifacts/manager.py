"""Artifact manager - Screenshots, logs, and debug bundles."""

from __future__ import annotations

import asyncio
import zipfile
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    import uiautomator2 as u2

logger = structlog.get_logger()


class ArtifactManager:
    """Manages artifact capture and storage."""

    def __init__(self, output_dir: Path | None = None) -> None:
        default_dir = Path.home() / ".android-agent" / "artifacts"
        self.output_dir = output_dir or default_dir
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
            filename = f"{session_id}_{timestamp}.png"

        output_path = self.output_dir / filename

        # uiautomator2 returns PIL Image
        image = await asyncio.to_thread(device.screenshot)
        if image is None:
            raise RuntimeError("Failed to capture screenshot from device")
        await asyncio.to_thread(image.save, str(output_path))

        logger.info("screenshot_captured", path=str(output_path))
        return output_path

    async def pull_logs(
        self,
        device: u2.Device,
        session_id: str,
        since: str | None = None,
        filename: str | None = None,
    ) -> Path:
        """Pull logcat logs from device."""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{session_id}_{timestamp}_logcat.txt"

        output_path = self.output_dir / filename

        def _pull() -> str:
            cmd = "logcat -d"
            if since:
                cmd += f" -t '{since}'"
            result = device.shell(cmd)
            output = getattr(result, "output", None)
            return output if isinstance(output, str) else str(result)

        logs = await asyncio.to_thread(_pull)
        output_path.write_text(logs)

        logger.info("logs_pulled", path=str(output_path), size=len(logs))
        return output_path

    async def save_snapshot(
        self,
        snapshot_json: str,
        session_id: str,
        generation: int,
    ) -> Path:
        """Save a snapshot to disk."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{session_id}_gen{generation}_{timestamp}.json"
        output_path = self.output_dir / filename

        output_path.write_text(snapshot_json)
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
        bundle_name = f"{session_id}_{timestamp}_debug.zip"
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

        # Cleanup temp files
        screenshot_path.unlink(missing_ok=True)
        logs_path.unlink(missing_ok=True)

        logger.info("debug_bundle_created", path=str(bundle_path))
        return bundle_path
