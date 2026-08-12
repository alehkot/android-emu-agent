"""Bounded per-device thread pools for blocking device I/O."""

from __future__ import annotations

import asyncio
import functools
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any, TypeVar

import structlog

logger = structlog.get_logger()

T = TypeVar("T")

# Blocking device calls (adb shell, ATX HTTP) cannot be cancelled once a worker thread has
# entered them, so `asyncio.wait_for` around `asyncio.to_thread` returns while the thread
# stays wedged. On the shared default executor -- roughly 20 workers -- a single
# unresponsive device drains every slot and stalls the whole daemon, including requests
# for healthy devices. Giving each device its own small pool means a wedged device can
# only ever starve itself.
DEFAULT_DEVICE_IO_WORKERS = 6

UNKNOWN_SERIAL = "<unknown>"


def serial_of(device: Any) -> str:
    """Return the serial for a device object, or the value itself if already a serial."""
    if isinstance(device, str):
        return device
    serial = getattr(device, "serial", None)
    return str(serial) if serial else UNKNOWN_SERIAL


class DeviceIOPool:
    """Owns one bounded thread pool per device serial."""

    def __init__(self, max_workers: int = DEFAULT_DEVICE_IO_WORKERS) -> None:
        self._max_workers = max_workers
        self._executors: dict[str, ThreadPoolExecutor] = {}
        self._lock = threading.Lock()

    def executor(self, serial: str) -> ThreadPoolExecutor:
        """Return the pool dedicated to one device, creating it on first use."""
        with self._lock:
            executor = self._executors.get(serial)
            if executor is None:
                executor = ThreadPoolExecutor(
                    max_workers=self._max_workers,
                    thread_name_prefix=f"device-io-{serial}",
                )
                self._executors[serial] = executor
                logger.debug("device_io_pool_created", serial=serial)
            return executor

    async def run(
        self,
        device: Any,
        func: Callable[..., T],
        /,
        *args: Any,
        io_timeout: float | None = None,
        **kwargs: Any,
    ) -> T:
        """Run a blocking device call on that device's pool.

        ``io_timeout`` bounds the await, not the underlying call. Prefer also passing the
        driver's own timeout (e.g. adbutils ``shell(timeout=...)``) so the worker thread
        releases itself; ``io_timeout`` alone frees the caller but not the thread.
        """
        loop = asyncio.get_running_loop()
        call = functools.partial(func, *args, **kwargs)
        future = loop.run_in_executor(self.executor(serial_of(device)), call)
        if io_timeout is None:
            return await future
        return await asyncio.wait_for(future, io_timeout)

    def shutdown(self, serial: str) -> None:
        """Drop one device's pool, cancelling work that has not started yet."""
        with self._lock:
            executor = self._executors.pop(serial, None)
        if executor is not None:
            executor.shutdown(wait=False, cancel_futures=True)
            logger.debug("device_io_pool_shutdown", serial=serial)

    def shutdown_all(self) -> None:
        """Drop every pool, cancelling work that has not started yet."""
        with self._lock:
            executors = list(self._executors.values())
            self._executors.clear()
        for executor in executors:
            executor.shutdown(wait=False, cancel_futures=True)


_pool = DeviceIOPool()


async def run_device_io(
    device: Any,
    func: Callable[..., T],
    /,
    *args: Any,
    io_timeout: float | None = None,
    **kwargs: Any,
) -> T:
    """Run a blocking device call on the calling process's shared per-device pools."""
    return await _pool.run(device, func, *args, io_timeout=io_timeout, **kwargs)


def shutdown_device_io(serial: str) -> None:
    """Release the pool backing one device."""
    _pool.shutdown(serial)


def shutdown_all_device_io() -> None:
    """Release every per-device pool."""
    _pool.shutdown_all()
