"""Device manager - ADB connections, root checks, determinism controls."""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

import structlog

from android_emu_agent.errors import console_connect_error, snapshot_failed_error
from android_emu_agent.validation import get_console_port


class Orientation(Enum):
    """Screen orientation values."""

    PORTRAIT = 0
    LANDSCAPE = 1
    REVERSE_PORTRAIT = 2
    REVERSE_LANDSCAPE = 3
    AUTO = -1  # Special: re-enable auto-rotate


if TYPE_CHECKING:
    import uiautomator2 as u2
    from adbutils import AdbDevice

logger = structlog.get_logger()


@dataclass
class DeviceInfo:
    """Device information."""

    serial: str
    model: str
    sdk_version: int
    is_rooted: bool
    is_emulator: bool


class DeviceManager:
    """Manages ADB device connections and state."""

    def __init__(self) -> None:
        self._devices: dict[str, DeviceInfo] = {}
        self._adb_devices: dict[str, AdbDevice] = {}
        self._u2_devices: dict[str, u2.Device] = {}
        self._lock = asyncio.Lock()
        self._heartbeat_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Start device manager and begin device discovery."""
        logger.info("device_manager_starting")
        await self._discover_devices()
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        logger.info("device_manager_started", device_count=len(self._devices))

    async def stop(self) -> None:
        """Stop device manager and cleanup connections."""
        logger.info("device_manager_stopping")
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._heartbeat_task
        self._adb_devices.clear()
        self._u2_devices.clear()
        self._devices.clear()
        logger.info("device_manager_stopped")

    async def list_devices(self) -> list[dict[str, str]]:
        """List all connected devices."""
        await self._discover_devices()
        return [
            {
                "serial": info.serial,
                "model": info.model,
                "sdk_version": str(info.sdk_version),
                "is_rooted": str(info.is_rooted),
                "is_emulator": str(info.is_emulator),
            }
            for info in self._devices.values()
        ]

    async def get_device(self, serial: str) -> DeviceInfo | None:
        """Get device info by serial."""
        return self._devices.get(serial)

    async def refresh(self) -> None:
        """Force device discovery refresh."""
        await self._discover_devices()

    async def get_adb_device(self, serial: str) -> AdbDevice | None:
        """Get or create an adbutils device connection."""
        await self._discover_devices()
        if serial not in self._devices:
            return None
        if serial in self._adb_devices:
            return self._adb_devices[serial]

        from adbutils import adb

        def _connect() -> AdbDevice:
            return adb.device(serial)

        device = await asyncio.to_thread(_connect)
        self._adb_devices[serial] = device
        return device

    async def get_u2_device(self, serial: str) -> u2.Device | None:
        """Get or create a uiautomator2 device connection."""
        await self._discover_devices()
        if serial not in self._devices:
            return None
        if serial in self._u2_devices:
            return self._u2_devices[serial]

        import uiautomator2 as u2

        def _connect() -> u2.Device:
            return u2.connect(serial)

        device = await asyncio.to_thread(_connect)
        self._u2_devices[serial] = device
        return device

    async def describe_device(self, serial: str) -> dict[str, Any]:
        """Return device info suitable for snapshot metadata."""
        info = self._devices.get(serial)
        if info is None:
            return {"serial": serial}
        return {
            "serial": info.serial,
            "sdk": info.sdk_version,
            "model": info.model,
            "is_rooted": info.is_rooted,
            "is_emulator": info.is_emulator,
        }

    async def set_animations(self, serial: str, enabled: bool) -> None:
        """Enable or disable system animations."""
        device = await self.get_adb_device(serial)
        if not device:
            raise RuntimeError(f"Device not found: {serial}")

        scale = "1" if enabled else "0"

        def _apply() -> None:
            device.shell(f"settings put global window_animation_scale {scale}")
            device.shell(f"settings put global transition_animation_scale {scale}")
            device.shell(f"settings put global animator_duration_scale {scale}")

        await asyncio.to_thread(_apply)

    async def set_stay_awake(self, serial: str, enabled: bool) -> None:
        """Keep device awake while plugged in."""
        device = await self.get_adb_device(serial)
        if not device:
            raise RuntimeError(f"Device not found: {serial}")

        value = "3" if enabled else "0"

        def _apply() -> None:
            device.shell(f"settings put global stay_on_while_plugged_in {value}")

        await asyncio.to_thread(_apply)

    async def app_reset(self, serial: str, package: str) -> None:
        """Clear app data for a package."""
        device = await self.get_adb_device(serial)
        if not device:
            raise RuntimeError(f"Device not found: {serial}")

        def _apply() -> None:
            device.shell(f"pm clear {package}")

        await asyncio.to_thread(_apply)

    async def set_rotation(self, serial: str, orientation: Orientation) -> None:
        """Set screen rotation.

        Args:
            serial: Device serial
            orientation: Target orientation (or AUTO to enable auto-rotate)
        """
        device = await self.get_adb_device(serial)
        if not device:
            raise RuntimeError(f"Device not found: {serial}")

        def _apply() -> None:
            if orientation == Orientation.AUTO:
                # Enable auto-rotate
                device.shell("settings put system accelerometer_rotation 1")
            else:
                # Disable auto-rotate and set fixed orientation
                device.shell("settings put system accelerometer_rotation 0")
                device.shell(f"settings put system user_rotation {orientation.value}")

        await asyncio.to_thread(_apply)

    async def set_wifi(self, serial: str, enabled: bool) -> None:
        """Enable or disable WiFi.

        Args:
            serial: Device serial
            enabled: True to enable, False to disable
        """
        device = await self.get_adb_device(serial)
        if not device:
            raise RuntimeError(f"Device not found: {serial}")

        state = "enable" if enabled else "disable"

        def _apply() -> None:
            device.shell(f"svc wifi {state}")

        await asyncio.to_thread(_apply)

    async def set_mobile(self, serial: str, enabled: bool) -> None:
        """Enable or disable mobile data.

        Args:
            serial: Device serial
            enabled: True to enable, False to disable
        """
        device = await self.get_adb_device(serial)
        if not device:
            raise RuntimeError(f"Device not found: {serial}")

        state = "enable" if enabled else "disable"

        def _apply() -> None:
            device.shell(f"svc data {state}")

        await asyncio.to_thread(_apply)

    async def set_doze(self, serial: str, enabled: bool) -> None:
        """Force device into or out of doze mode.

        Args:
            serial: Device serial
            enabled: True to force doze, False to exit doze
        """
        device = await self.get_adb_device(serial)
        if not device:
            raise RuntimeError(f"Device not found: {serial}")

        def _apply() -> None:
            if enabled:
                device.shell("dumpsys deviceidle force-idle")
            else:
                device.shell("dumpsys deviceidle unforce")

        await asyncio.to_thread(_apply)

    async def app_launch(self, serial: str, package: str, activity: str | None = None) -> str:
        """Launch an app.

        Args:
            serial: Device serial
            package: Package name
            activity: Activity name (optional, will resolve launcher if not provided)

        Returns:
            Activity that was launched
        """
        device = await self.get_adb_device(serial)
        if not device:
            raise RuntimeError(f"Device not found: {serial}")

        def _launch() -> str:
            target_activity = activity
            if not target_activity:
                # Resolve launcher activity
                output = device.shell(
                    f"cmd package resolve-activity --brief "
                    f"-c android.intent.category.LAUNCHER {package}"
                )
                lines = output.strip().split("\n")
                if len(lines) >= 2:
                    # Second line contains package/activity
                    resolved = lines[-1].strip()
                    if "/" in resolved:
                        target_activity = resolved.split("/")[1]

            if not target_activity:
                raise RuntimeError(f"Could not resolve launcher activity for {package}")

            # Normalize activity name
            if not target_activity.startswith(".") and "/" not in target_activity:
                target_activity = f".{target_activity}"

            component = f"{package}/{target_activity}"
            device.shell(f"am start -n {component}")
            return target_activity

        return await asyncio.to_thread(_launch)

    async def app_force_stop(self, serial: str, package: str) -> None:
        """Force stop an app.

        Args:
            serial: Device serial
            package: Package name
        """
        device = await self.get_adb_device(serial)
        if not device:
            raise RuntimeError(f"Device not found: {serial}")

        def _stop() -> None:
            device.shell(f"am force-stop {package}")

        await asyncio.to_thread(_stop)

    async def app_deeplink(self, serial: str, uri: str) -> None:
        """Open a deeplink URI.

        Args:
            serial: Device serial
            uri: URI to open (e.g., 'myapp://path' or 'https://example.com')
        """
        device = await self.get_adb_device(serial)
        if not device:
            raise RuntimeError(f"Device not found: {serial}")

        def _open() -> None:
            device.shell(f'am start -a android.intent.action.VIEW -d "{uri}"')

        await asyncio.to_thread(_open)

    async def list_packages(self, serial: str, scope: str = "all") -> list[str]:
        """List installed packages.

        Args:
            serial: Device serial
            scope: all|system|third-party
        """
        device = await self.get_adb_device(serial)
        if not device:
            raise RuntimeError(f"Device not found: {serial}")

        scope_key = scope.lower()
        if scope_key not in {"all", "system", "third-party"}:
            raise ValueError(f"Invalid package scope: {scope}")

        def _list() -> str:
            args = ["pm", "list", "packages"]
            if scope_key == "system":
                args.append("-s")
            elif scope_key == "third-party":
                args.append("-3")
            return str(device.shell(" ".join(args)))

        output = await asyncio.to_thread(_list)
        packages: list[str] = []
        for line in output.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("package:"):
                packages.append(line.removeprefix("package:"))
        return packages

    async def _discover_devices(self) -> None:
        """Discover connected ADB devices."""
        from adbutils import adb

        async with self._lock:

            def _list() -> list[AdbDevice]:
                return list(adb.device_list())

            devices = await asyncio.to_thread(_list)
            seen: set[str] = set()

            for dev in devices:
                serial = dev.serial
                if not serial:
                    logger.warning("device_missing_serial")
                    continue
                seen.add(serial)
                self._adb_devices[serial] = dev
                if serial not in self._devices:
                    info = await self._build_device_info(dev)
                    self._devices[serial] = info
                    logger.info("device_discovered", serial=serial, model=info.model)

            # Remove disconnected devices
            disconnected = set(self._devices.keys()) - seen
            for serial in disconnected:
                self._devices.pop(serial, None)
                self._adb_devices.pop(serial, None)
                self._u2_devices.pop(serial, None)
                logger.info("device_disconnected", serial=serial)

    async def _build_device_info(self, device: AdbDevice) -> DeviceInfo:
        """Build DeviceInfo from adb device."""

        def _props() -> dict[str, str]:
            props = device.prop
            return {
                "model": props.model or props.get("ro.product.model") or "unknown",
                "sdk": props.get("ro.build.version.sdk") or "0",
                "is_emulator": props.get("ro.kernel.qemu") or "0",
            }

        props = await asyncio.to_thread(_props)

        serial = device.serial
        if not serial:
            raise RuntimeError("Device serial missing")
        model = props["model"]
        sdk_version = int(props["sdk"]) if props["sdk"].isdigit() else 0
        is_emulator = serial.startswith("emulator-") or props["is_emulator"] == "1"
        is_rooted = await self._check_root(device)

        return DeviceInfo(
            serial=serial,
            model=model,
            sdk_version=sdk_version,
            is_rooted=is_rooted,
            is_emulator=is_emulator,
        )

    async def _check_root(self, device: AdbDevice) -> bool:
        """Best-effort root detection."""

        def _run() -> str:
            try:
                return str(device.shell("su -c id"))
            except Exception:
                return ""

        output = await asyncio.to_thread(_run)
        return "uid=0" in output

    async def _heartbeat_loop(self) -> None:
        """Periodic heartbeat to check device connectivity."""
        while True:
            await asyncio.sleep(30)
            try:
                await self._discover_devices()
            except Exception:
                logger.exception("heartbeat_error")

    async def evict_device(self, serial: str) -> None:
        """Remove cached connections for a device, forcing reconnect on next use.

        Args:
            serial: Device serial to evict
        """
        async with self._lock:
            evicted_adb = self._adb_devices.pop(serial, None) is not None
            evicted_u2 = self._u2_devices.pop(serial, None) is not None

            if evicted_adb or evicted_u2:
                logger.info("device_evicted", serial=serial, adb=evicted_adb, u2=evicted_u2)

    async def emulator_snapshot_save(self, serial: str, name: str) -> None:
        """Save emulator snapshot.

        Args:
            serial: Emulator serial (e.g., 'emulator-5554')
            name: Snapshot name
        """
        port = get_console_port(serial)
        await self._send_console_command(port, f"avd snapshot save {name}")
        logger.info("snapshot_saved", serial=serial, name=name)

    async def emulator_snapshot_restore(self, serial: str, name: str) -> None:
        """Restore emulator snapshot.

        Args:
            serial: Emulator serial (e.g., 'emulator-5554')
            name: Snapshot name
        """
        port = get_console_port(serial)
        await self._send_console_command(port, f"avd snapshot load {name}")
        logger.info("snapshot_restored", serial=serial, name=name)

    async def _send_console_command(self, port: int, command: str) -> str:
        """Send command to emulator console.

        Args:
            port: Console port number
            command: Command to send

        Returns:
            Console response

        Raises:
            AgentError: If connection fails or command returns error
        """
        try:
            reader, writer = await asyncio.open_connection("localhost", port)
        except OSError as e:
            raise console_connect_error(port) from e

        try:
            # Read initial banner until OK
            await asyncio.wait_for(reader.read(1024), timeout=5.0)

            # Send command
            writer.write(f"{command}\n".encode())
            await writer.drain()

            # Read response
            response = await asyncio.wait_for(reader.read(1024), timeout=30.0)
            response_str = response.decode()

            if "OK" not in response_str:
                # Extract error message
                error_msg = response_str.strip() or "Unknown error"
                raise snapshot_failed_error(command.split()[-1], error_msg)

            return response_str
        finally:
            writer.close()
            await writer.wait_closed()
