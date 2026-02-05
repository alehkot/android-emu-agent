"""Health monitoring - device connectivity checks and stale connection eviction."""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from android_emu_agent.device.manager import DeviceManager
    from android_emu_agent.device.session import SessionManager

logger = structlog.get_logger()


@dataclass
class DeviceHealth:
    """Health status for a single device."""

    serial: str
    adb_ok: bool
    u2_ok: bool
    last_check: datetime
    error: str | None = None


class HealthMonitor:
    """Monitors device health and evicts stale connections."""

    def __init__(
        self,
        device_manager: DeviceManager,
        session_manager: SessionManager,
    ) -> None:
        self._device_manager = device_manager
        self._session_manager = session_manager
        self._device_health: dict[str, DeviceHealth] = {}
        self._task: asyncio.Task[None] | None = None
        self._running = False

    async def check_device(self, serial: str, timeout: float = 3.0) -> DeviceHealth:
        """Check health of a single device.

        Args:
            serial: Device serial to check
            timeout: Timeout in seconds for each check

        Returns:
            DeviceHealth with check results
        """
        now = datetime.now()

        # Step 1: ADB check
        adb_ok = await self._check_adb(serial, timeout)
        if not adb_ok:
            health = DeviceHealth(
                serial=serial,
                adb_ok=False,
                u2_ok=False,
                last_check=now,
                error="ADB connection failed",
            )
            self._device_health[serial] = health
            return health

        # Step 2: u2 check (only if ADB passed)
        u2_ok, u2_error = await self._check_u2(serial, timeout)
        health = DeviceHealth(
            serial=serial,
            adb_ok=True,
            u2_ok=u2_ok,
            last_check=now,
            error=u2_error,
        )
        self._device_health[serial] = health
        return health

    async def _check_adb(self, serial: str, timeout: float) -> bool:
        """Check ADB connectivity."""
        device = self._device_manager._adb_devices.get(serial)
        if not device:
            return False
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(device.shell, "echo ok"),
                timeout=timeout,
            )
            return "ok" in str(result)
        except Exception:
            return False

    async def _check_u2(self, serial: str, timeout: float) -> tuple[bool, str | None]:
        """Check u2/ATX server connectivity."""
        device = self._device_manager._u2_devices.get(serial)
        if not device:
            # No cached u2 connection = nothing to verify, will connect fresh
            return True, None
        try:
            await asyncio.wait_for(
                asyncio.to_thread(lambda: device.info),
                timeout=timeout,
            )
            return True, None
        except Exception as e:
            return False, f"ATX server unresponsive: {e}"

    async def start(self) -> None:
        """Start the health monitor heartbeat loop."""
        logger.info("health_monitor_starting")
        self._running = True
        self._task = asyncio.create_task(self._heartbeat_loop())
        logger.info("health_monitor_started")

    async def stop(self) -> None:
        """Stop the health monitor."""
        logger.info("health_monitor_stopping")
        self._running = False
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        logger.info("health_monitor_stopped")

    def get_status(self) -> dict[str, Any]:
        """Get current health status for all monitored devices.

        Returns:
            Dict with device health information
        """
        devices: dict[str, dict[str, Any]] = {}
        for serial, health in self._device_health.items():
            devices[serial] = {
                "adb_ok": health.adb_ok,
                "u2_ok": health.u2_ok,
                "last_check": health.last_check.isoformat(),
                "error": health.error,
            }
        return {"devices": devices}

    async def _heartbeat_loop(self) -> None:
        """Periodic heartbeat to check device health."""
        while self._running:
            await asyncio.sleep(15)
            try:
                await self._run_health_checks()
            except Exception:
                logger.exception("health_check_error")

    async def _run_health_checks(self) -> None:
        """Run health checks on all relevant devices."""
        # Get devices with active sessions (prioritize)
        sessions = await self._session_manager.list_sessions()
        session_devices = {s.device_serial for s in sessions}

        # Check session devices first, then other known devices
        all_devices = list(session_devices) + [
            s for s in self._device_health if s not in session_devices
        ]

        for serial in all_devices:
            health = await self.check_device(serial, timeout=3.0)

            if not health.adb_ok or not health.u2_ok:
                logger.warning(
                    "device_unhealthy",
                    serial=serial,
                    adb_ok=health.adb_ok,
                    u2_ok=health.u2_ok,
                    error=health.error,
                )
                # Evict stale connections
                await self._device_manager.evict_device(serial)
