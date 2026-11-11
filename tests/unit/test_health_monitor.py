"""Tests for HealthMonitor."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestDeviceHealth:
    """Tests for DeviceHealth dataclass."""

    def test_healthy_device(self) -> None:
        """Should create healthy device status."""
        from android_emu_agent.daemon.health import DeviceHealth

        health = DeviceHealth(
            serial="emulator-5554",
            adb_ok=True,
            u2_ok=True,
            last_check=datetime.now(),
        )

        assert health.serial == "emulator-5554"
        assert health.adb_ok is True
        assert health.u2_ok is True
        assert health.error is None

    def test_unhealthy_device(self) -> None:
        """Should create unhealthy device status with error."""
        from android_emu_agent.daemon.health import DeviceHealth

        health = DeviceHealth(
            serial="emulator-5554",
            adb_ok=True,
            u2_ok=False,
            last_check=datetime.now(),
            error="ATX server unresponsive",
        )

        assert health.u2_ok is False
        assert health.error == "ATX server unresponsive"


class TestHealthMonitorInit:
    """Tests for HealthMonitor initialization."""

    def test_init(self) -> None:
        """Should initialize with managers."""
        from android_emu_agent.daemon.health import HealthMonitor

        device_manager = MagicMock()
        session_manager = MagicMock()

        monitor = HealthMonitor(device_manager, session_manager)

        assert monitor._device_manager is device_manager
        assert monitor._session_manager is session_manager
        assert monitor._device_health == {}
        assert monitor._task is None


class TestCheckDevice:
    """Tests for check_device method."""

    @pytest.mark.asyncio
    async def test_healthy_adb_and_u2(self) -> None:
        """Should return healthy when both ADB and u2 pass."""
        from android_emu_agent.daemon.health import HealthMonitor

        device_manager = MagicMock()
        device_manager._adb_devices = {"emulator-5554": MagicMock()}
        device_manager._u2_devices = {"emulator-5554": MagicMock()}
        session_manager = MagicMock()

        monitor = HealthMonitor(device_manager, session_manager)

        with (
            pytest.MonkeyPatch.context() as mp,
        ):
            mp.setattr(
                "android_emu_agent.daemon.health.run_device_io",
                AsyncMock(return_value="ok"),
            )

            health = await monitor.check_device("emulator-5554", timeout=1.0)

        assert health.adb_ok is True
        assert health.u2_ok is True
        assert health.error is None

    @pytest.mark.asyncio
    async def test_adb_failure(self) -> None:
        """Should return unhealthy when ADB fails."""
        from android_emu_agent.daemon.health import HealthMonitor

        device_manager = MagicMock()
        device_manager._adb_devices = {"emulator-5554": MagicMock()}
        device_manager._u2_devices = {}
        session_manager = MagicMock()

        monitor = HealthMonitor(device_manager, session_manager)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "android_emu_agent.daemon.health.run_device_io",
                AsyncMock(side_effect=TimeoutError()),
            )

            health = await monitor.check_device("emulator-5554", timeout=1.0)

        assert health.adb_ok is False
        assert health.u2_ok is False
        assert health.error == "ADB connection failed"

    @pytest.mark.asyncio
    async def test_u2_failure(self) -> None:
        """Should return degraded when ADB passes but u2 fails."""
        from android_emu_agent.daemon.health import HealthMonitor

        device_manager = MagicMock()
        mock_adb = MagicMock()
        mock_adb.shell.return_value = "ok"
        device_manager._adb_devices = {"emulator-5554": mock_adb}
        mock_u2 = MagicMock()
        mock_u2.info = property(lambda _: (_ for _ in ()).throw(Exception("timeout")))
        device_manager._u2_devices = {"emulator-5554": mock_u2}
        session_manager = MagicMock()

        monitor = HealthMonitor(device_manager, session_manager)

        # Mock to_thread to call function directly for ADB, raise for u2
        call_count = [0]

        async def mock_run_device_io(_device, _func, *_args, **_kwargs):
            call_count[0] += 1
            if call_count[0] == 1:  # ADB check
                return "ok"
            raise Exception("ATX timeout")

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("android_emu_agent.daemon.health.run_device_io", mock_run_device_io)

            health = await monitor.check_device("emulator-5554", timeout=1.0)

        assert health.adb_ok is True
        assert health.u2_ok is False
        assert health.error is not None
        assert "ATX" in health.error

    @pytest.mark.asyncio
    async def test_no_cached_u2_skips_check(self) -> None:
        """Should skip u2 check if no cached connection exists."""
        from android_emu_agent.daemon.health import HealthMonitor

        device_manager = MagicMock()
        mock_adb = MagicMock()
        device_manager._adb_devices = {"emulator-5554": mock_adb}
        device_manager._u2_devices = {}  # No cached u2
        session_manager = MagicMock()

        monitor = HealthMonitor(device_manager, session_manager)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "android_emu_agent.daemon.health.run_device_io",
                AsyncMock(return_value="ok"),
            )

            health = await monitor.check_device("emulator-5554", timeout=1.0)

        assert health.adb_ok is True
        assert health.u2_ok is True  # Passes because no u2 to check
        assert health.error is None

    @pytest.mark.asyncio
    async def test_no_cached_adb(self) -> None:
        """Should return unhealthy if no ADB connection cached."""
        from android_emu_agent.daemon.health import HealthMonitor

        device_manager = MagicMock()
        device_manager._adb_devices = {}  # No cached ADB
        device_manager._u2_devices = {}
        session_manager = MagicMock()

        monitor = HealthMonitor(device_manager, session_manager)

        health = await monitor.check_device("emulator-5554", timeout=1.0)

        assert health.adb_ok is False
        assert health.u2_ok is False
        assert health.error == "ADB connection failed"


class TestHealthMonitorLifecycle:
    """Tests for start/stop lifecycle."""

    @pytest.mark.asyncio
    async def test_start_creates_task(self) -> None:
        """Should create heartbeat task on start."""
        from android_emu_agent.daemon.health import HealthMonitor

        device_manager = MagicMock()
        session_manager = MagicMock()

        monitor = HealthMonitor(device_manager, session_manager)
        await monitor.start()

        assert monitor._running is True
        assert monitor._task is not None

        # Cleanup
        await monitor.stop()

    @pytest.mark.asyncio
    async def test_stop_cancels_task(self) -> None:
        """Should cancel heartbeat task on stop."""
        from android_emu_agent.daemon.health import HealthMonitor

        device_manager = MagicMock()
        session_manager = MagicMock()

        monitor = HealthMonitor(device_manager, session_manager)
        await monitor.start()
        await monitor.stop()

        assert monitor._running is False
        assert monitor._task is None or monitor._task.cancelled()


class TestGetStatus:
    """Tests for get_status method."""

    def test_get_status_empty(self) -> None:
        """Should return empty status when no devices checked."""
        from android_emu_agent.daemon.health import HealthMonitor

        device_manager = MagicMock()
        session_manager = MagicMock()

        monitor = HealthMonitor(device_manager, session_manager)
        status = monitor.get_status()

        assert status == {"devices": {}}

    def test_get_status_with_devices(self) -> None:
        """Should return device health status."""
        from android_emu_agent.daemon.health import DeviceHealth, HealthMonitor

        device_manager = MagicMock()
        session_manager = MagicMock()

        monitor = HealthMonitor(device_manager, session_manager)
        now = datetime.now()
        monitor._device_health["emulator-5554"] = DeviceHealth(
            serial="emulator-5554",
            adb_ok=True,
            u2_ok=True,
            last_check=now,
        )

        status = monitor.get_status()

        assert "emulator-5554" in status["devices"]
        assert status["devices"]["emulator-5554"]["adb_ok"] is True
        assert status["devices"]["emulator-5554"]["u2_ok"] is True


class TestRunHealthChecks:
    """Tests for the heartbeat's device selection and logging."""

    @staticmethod
    def _monitor(*, sessions: list[str], attached: set[str]):
        from android_emu_agent.daemon.health import HealthMonitor

        device_manager = MagicMock()
        device_manager._adb_devices = {}
        device_manager._u2_devices = {}
        device_manager.get_device = AsyncMock(
            side_effect=lambda serial: object() if serial in attached else None
        )
        device_manager.evict_device = AsyncMock()
        session_manager = MagicMock()
        session_manager.list_sessions = AsyncMock(
            return_value=[SimpleNamespace(device_serial=serial) for serial in sessions]
        )
        return HealthMonitor(device_manager, session_manager), device_manager

    @pytest.mark.asyncio
    async def test_detached_device_without_session_is_dropped(self) -> None:
        """A stopped emulator whose session closed must not keep the daemon degraded."""
        from android_emu_agent.daemon.health import DeviceHealth

        monitor, device_manager = self._monitor(sessions=[], attached=set())
        monitor._device_health["emulator-5554"] = DeviceHealth(
            serial="emulator-5554", adb_ok=True, u2_ok=True, last_check=datetime.now()
        )

        await monitor._run_health_checks()

        assert monitor.get_status() == {"devices": {}}
        device_manager.evict_device.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_attached_device_without_session_is_still_checked(self) -> None:
        """Pruning only drops devices discovery no longer lists."""
        from android_emu_agent.daemon.health import DeviceHealth

        monitor, device_manager = self._monitor(sessions=[], attached={"emulator-5554"})
        device_manager._adb_devices["emulator-5554"] = MagicMock()
        earlier = datetime(2026, 1, 1)
        monitor._device_health["emulator-5554"] = DeviceHealth(
            serial="emulator-5554", adb_ok=True, u2_ok=True, last_check=earlier
        )

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "android_emu_agent.daemon.health.run_device_io",
                AsyncMock(return_value="ok"),
            )
            await monitor._run_health_checks()

        assert monitor._device_health["emulator-5554"].last_check > earlier

    @pytest.mark.asyncio
    async def test_unhealthy_session_device_warns_once_then_logs_recovery(self) -> None:
        """An unchanged unhealthy state is logged once, not on every heartbeat."""
        monitor, device_manager = self._monitor(sessions=["emulator-5554"], attached=set())
        logger = MagicMock()

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("android_emu_agent.daemon.health.logger", logger)
            mp.setattr(
                "android_emu_agent.daemon.health.run_device_io",
                AsyncMock(return_value="ok"),
            )
            await monitor._run_health_checks()
            await monitor._run_health_checks()

            assert logger.warning.call_count == 1
            assert device_manager.evict_device.await_count == 2
            assert monitor.get_status()["devices"]["emulator-5554"]["adb_ok"] is False

            device_manager._adb_devices["emulator-5554"] = MagicMock()
            await monitor._run_health_checks()

        logger.info.assert_called_once_with("device_recovered", serial="emulator-5554")
        assert logger.warning.call_count == 1
        assert monitor.get_status()["devices"]["emulator-5554"]["adb_ok"] is True


@pytest.mark.asyncio
async def test_health_reports_daemon_pid() -> None:
    """The health response should identify the process serving the socket."""
    from android_emu_agent.daemon import server

    core = SimpleNamespace(
        health_monitor=MagicMock(get_status=MagicMock(return_value={"devices": {}})),
        session_manager=SimpleNamespace(list_sessions=AsyncMock(return_value=[])),
        is_running=True,
    )
    previous_core = getattr(server.app.state, "core", None)
    server.app.state.core = core
    try:
        with patch.object(server.os, "getpid", return_value=4242):
            result = await server.health()
    finally:
        server.app.state.core = previous_core

    assert result["pid"] == 4242
