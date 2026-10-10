"""Regression tests for bounded polling waits, including blocked device I/O."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable
from concurrent.futures import Future
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest

from android_emu_agent.actions import wait as wait_module
from android_emu_agent.actions.wait import WaitEngine, WaitResult
from android_emu_agent.device.io import DeviceIOPool


async def _wait_for_kind(engine: WaitEngine, device: Any, kind: str) -> WaitResult:
    if kind == "activity":
        return await engine.wait_activity(device, "Ready", timeout=0.02)
    if kind == "text":
        return await engine.wait_text(device, "Ready", timeout=0.02)
    if kind == "exists":
        return await engine.wait_exists(device, {"text": "Ready"}, timeout=0.02)
    return await engine.wait_gone(device, {"text": "Ready"}, timeout=0.02)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["activity", "text", "exists", "gone"])
async def test_wait_returns_timeout_while_device_call_is_still_blocked(
    kind: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """All polling entry points must return without waiting for the device to recover."""
    pool = DeviceIOPool(max_workers=1)
    release = threading.Event()
    started = threading.Event()
    device = MagicMock()
    device.serial = "blocked-wait-device"

    def blocked() -> Any:
        started.set()
        release.wait(timeout=5)
        return {"activity": "Ready"} if kind == "activity" else kind != "gone"

    device.app_current.side_effect = blocked
    device.return_value.exists.side_effect = blocked
    monkeypatch.setattr(wait_module, "run_device_io", pool.run)
    try:
        result = await asyncio.wait_for(_wait_for_kind(WaitEngine(), device, kind), timeout=1)

        assert started.is_set()
        assert not release.is_set()
        assert result.success is False
        assert result.error is not None
        assert result.error.code == "ERR_TIMEOUT"
        assert result.to_dict()["status"] == "timeout"
        assert result.error.context["last_error"]
    finally:
        release.set()
        # Drain the isolated worker so this regression test leaves no running I/O behind.
        await pool.run(device, lambda: None, io_timeout=2)
        pool.shutdown_all()


class FakeClock:
    def __init__(self) -> None:
        self.now = 100.0

    def monotonic(self) -> float:
        return self.now


@pytest.mark.asyncio
async def test_polls_and_sleeps_share_one_deadline(monkeypatch: pytest.MonkeyPatch) -> None:
    """Device time and polling delay both consume the remaining budget."""
    clock = FakeClock()
    budgets: list[float] = []
    sleeps: list[float] = []
    durations = iter([0.1, 0.2])

    async def run_io(_device: Any, _predicate: Callable[[], bool], *, io_timeout: float) -> bool:
        budgets.append(io_timeout)
        clock.now += next(durations)
        return False

    async def sleep(delay: float) -> None:
        sleeps.append(delay)
        clock.now += delay

    monkeypatch.setattr(wait_module, "time", clock)
    monkeypatch.setattr(wait_module, "asyncio", SimpleNamespace(sleep=sleep))
    monkeypatch.setattr(wait_module, "run_device_io", run_io)

    result = await WaitEngine(poll_interval=0.4)._poll_condition(
        cast(Any, object()),
        lambda: False,
        timeout=1,
        error_message="Missing",
        remediation="Check selector",
    )

    assert result.success is False
    assert result.elapsed_ms == pytest.approx(1000)
    assert budgets == pytest.approx([1.0, 0.5])
    assert sleeps == pytest.approx([0.4, 0.3])


@pytest.mark.asyncio
async def test_result_delivered_after_deadline_is_not_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A late completion must not win a race with the deadline callback."""
    clock = FakeClock()

    async def late_success(*_args: Any, **_kwargs: Any) -> bool:
        clock.now += 2
        return True

    sleep = AsyncMock()
    monkeypatch.setattr(wait_module, "time", clock)
    monkeypatch.setattr(wait_module, "asyncio", SimpleNamespace(sleep=sleep))
    monkeypatch.setattr(wait_module, "run_device_io", late_success)

    result = await WaitEngine()._poll_condition(
        cast(Any, object()),
        lambda: True,
        timeout=1,
        error_message="Missing",
        remediation="Check selector",
    )

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "ERR_TIMEOUT"
    sleep.assert_not_awaited()


@pytest.mark.asyncio
async def test_deadline_timeout_preserves_preceding_transport_diagnostic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty I/O timeout should not hide the transport error from the prior poll."""
    clock = FakeClock()
    attempts = 0

    async def run_io(*_args: Any, **_kwargs: Any) -> bool:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("ATX server disconnected")
        clock.now += 1
        raise TimeoutError

    async def sleep(delay: float) -> None:
        clock.now += delay

    monkeypatch.setattr(wait_module, "time", clock)
    monkeypatch.setattr(wait_module, "asyncio", SimpleNamespace(sleep=sleep))
    monkeypatch.setattr(wait_module, "run_device_io", run_io)

    result = await WaitEngine(poll_interval=0.1)._poll_condition(
        cast(Any, object()),
        lambda: False,
        timeout=1,
        error_message="Missing",
        remediation="Check selector",
    )

    assert attempts == 2
    assert result.error is not None
    assert result.error.context["last_error"] == "ATX server disconnected"
    assert "ATX server disconnected" in result.error.remediation
    assert result.to_dict()["error"]["last_error"] == "ATX server disconnected"


@pytest.mark.asyncio
async def test_transient_device_timeout_can_recover_before_deadline() -> None:
    """A driver's early timeout is retryable while the overall budget remains."""
    predicate = MagicMock(side_effect=[TimeoutError("temporary device timeout"), True])

    result = await WaitEngine(poll_interval=0.001)._poll_condition(
        cast(Any, "recovering-wait-device"),
        predicate,
        timeout=1,
        error_message="Missing",
        remediation="Check selector",
    )

    assert result.success is True
    assert predicate.call_count == 2


@pytest.mark.asyncio
async def test_cancelling_wait_propagates_without_waiting_for_device(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Caller cancellation stays cancellation, rather than becoming a timeout result."""
    entered = asyncio.Event()

    async def blocked_io(*_args: Any, **_kwargs: Any) -> bool:
        entered.set()
        await asyncio.Future()
        return False

    monkeypatch.setattr(wait_module, "run_device_io", blocked_io)
    task = asyncio.create_task(
        WaitEngine()._poll_condition(
            cast(Any, object()),
            lambda: False,
            timeout=10,
            error_message="Missing",
            remediation="Check",
        )
    )
    await asyncio.wait_for(entered.wait(), timeout=1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_cancellation_racing_success_does_not_continue_workflow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exercise the real I/O helper so Python 3.11 cancellation cannot look like success."""
    pool = DeviceIOPool(max_workers=1)
    loop = asyncio.get_running_loop()
    completed: Future[bool] = Future()
    following_action = MagicMock()
    executor = MagicMock()
    executor.submit.return_value = completed
    monkeypatch.setattr(pool, "executor", MagicMock(return_value=executor))
    monkeypatch.setattr(wait_module, "run_device_io", pool.run)

    async def workflow() -> None:
        await WaitEngine()._poll_condition(
            cast(Any, "wait-cancel-race-device"),
            lambda: True,
            timeout=1,
            error_message="Missing",
            remediation="Check selector",
        )
        following_action()

    task = asyncio.create_task(workflow())
    try:
        await asyncio.sleep(0)
        completed.set_result(True)
        loop.call_soon(task.cancel)
        with pytest.raises(asyncio.CancelledError):
            await task
        following_action.assert_not_called()
    finally:
        pool.shutdown_all()


@pytest.mark.asyncio
async def test_timeout_cancels_queued_poll_before_device_recovers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An expired poll queued behind a wedged call must never run later."""
    pool = DeviceIOPool(max_workers=1)
    release = threading.Event()
    predicate = MagicMock(return_value=True)
    serial = "queued-wait-device"
    blocker = pool.executor(serial).submit(release.wait, 5)
    monkeypatch.setattr(wait_module, "run_device_io", pool.run)

    try:
        result = await asyncio.wait_for(
            WaitEngine()._poll_condition(
                cast(Any, serial),
                predicate,
                timeout=0.02,
                error_message="Missing",
                remediation="Check",
            ),
            timeout=1,
        )
        assert result.success is False
        assert not blocker.done()
        predicate.assert_not_called()
    finally:
        release.set()
        await pool.run(serial, lambda: None, io_timeout=2)
        pool.shutdown_all()
    predicate.assert_not_called()
