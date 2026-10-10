"""Tests for bounded per-device I/O pools."""

from __future__ import annotations

import asyncio
import threading
import time
from concurrent.futures import Future
from unittest.mock import MagicMock

import pytest

from android_emu_agent.device.io import UNKNOWN_SERIAL, DeviceIOPool, serial_of


class FakeDevice:
    """Minimal stand-in exposing a serial like adbutils/uiautomator2 devices do."""

    def __init__(self, serial: str) -> None:
        self.serial = serial


class TestSerialOf:
    def test_extracts_serial_from_device(self) -> None:
        assert serial_of(FakeDevice("emulator-5554")) == "emulator-5554"

    def test_passes_through_plain_serial(self) -> None:
        assert serial_of("emulator-5554") == "emulator-5554"

    def test_falls_back_for_unknown_object(self) -> None:
        assert serial_of(object()) == UNKNOWN_SERIAL


class TestDeviceIOPool:
    @pytest.mark.asyncio
    async def test_caller_cancellation_wins_race_with_io_completion(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Python 3.11 wait_for can otherwise swallow cancellation of a finished Future."""
        pool = DeviceIOPool(max_workers=1)
        loop = asyncio.get_running_loop()
        completed: Future[bool] = Future()
        executor = MagicMock()
        executor.submit.return_value = completed
        monkeypatch.setattr(pool, "executor", MagicMock(return_value=executor))
        task = asyncio.create_task(pool.run("cancel-race-device", lambda: True, io_timeout=1))
        try:
            await asyncio.sleep(0)  # Let the device await start before racing its completion.
            completed.set_result(True)
            loop.call_soon(task.cancel)
            with pytest.raises(asyncio.CancelledError):
                await task
        finally:
            pool.shutdown_all()

    @pytest.mark.asyncio
    async def test_runs_call_and_returns_result(self) -> None:
        pool = DeviceIOPool(max_workers=2)
        try:
            assert await pool.run("emulator-5554", lambda a, b: a + b, 2, 3) == 5
        finally:
            pool.shutdown_all()

    @pytest.mark.asyncio
    async def test_forwards_keyword_arguments(self) -> None:
        pool = DeviceIOPool(max_workers=2)
        try:
            result = await pool.run("emulator-5554", lambda *, value: value * 2, value=21)
        finally:
            pool.shutdown_all()
        assert result == 42

    @pytest.mark.asyncio
    async def test_io_timeout_bounds_the_await(self) -> None:
        pool = DeviceIOPool(max_workers=2)
        try:
            with pytest.raises(TimeoutError):
                await pool.run("emulator-5554", lambda: time.sleep(5), io_timeout=0.1)
        finally:
            pool.shutdown_all()

    @pytest.mark.asyncio
    async def test_each_device_gets_its_own_executor(self) -> None:
        pool = DeviceIOPool(max_workers=2)
        try:
            first = pool.executor("emulator-5554")
            second = pool.executor("emulator-5556")
            assert first is not second
            assert pool.executor("emulator-5554") is first
        finally:
            pool.shutdown_all()

    @pytest.mark.asyncio
    async def test_wedged_device_does_not_starve_another(self) -> None:
        """The core guarantee: one device's stuck calls cannot block a different device."""
        pool = DeviceIOPool(max_workers=2)
        release = threading.Event()

        def _wedged() -> None:
            release.wait(timeout=10)

        try:
            # Saturate the wedged device's whole pool, plus a queued extra.
            stuck = [
                asyncio.create_task(pool.run("emulator-5556", _wedged, io_timeout=0.2))
                for _ in range(3)
            ]
            results = await asyncio.gather(*stuck, return_exceptions=True)
            assert all(isinstance(r, TimeoutError) for r in results)

            # A different device is served immediately despite that.
            served = await asyncio.wait_for(pool.run("emulator-5554", lambda: "ok"), timeout=2.0)
            assert served == "ok"
        finally:
            release.set()
            pool.shutdown_all()

    @pytest.mark.asyncio
    async def test_shutdown_drops_the_executor(self) -> None:
        pool = DeviceIOPool(max_workers=1)
        try:
            first = pool.executor("emulator-5554")
            pool.shutdown("emulator-5554")
            assert pool.executor("emulator-5554") is not first
        finally:
            pool.shutdown_all()

    def test_shutdown_is_idempotent(self) -> None:
        pool = DeviceIOPool(max_workers=1)
        pool.shutdown("never-seen")
        pool.shutdown_all()
        pool.shutdown_all()
