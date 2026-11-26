"""Boot readiness has one budget, even if ADB connects before Android finishes."""

from __future__ import annotations

import asyncio
import subprocess
from unittest.mock import AsyncMock

import pytest

from android_emu_agent.device.manager import DeviceManager
from android_emu_agent.errors import AgentError


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["wait-for-device", "boot-property", "refresh"])
async def test_stalled_readiness_stage_returns_actionable_timeout(
    monkeypatch: pytest.MonkeyPatch, stage: str
) -> None:
    manager = DeviceManager()
    entered = asyncio.Event()
    interrupted = asyncio.Event()
    budgets: list[float] = []

    async def stall() -> None:
        entered.set()
        try:
            await asyncio.Future()
        finally:
            interrupted.set()

    async def run_adb(
        _serial: str, args: list[str], *, timeout_s: float = 300.0
    ) -> subprocess.CompletedProcess[str]:
        budgets.append(timeout_s)
        wait = args == ["wait-for-device"]
        if (wait and stage == "wait-for-device") or (not wait and stage == "boot-property"):
            await stall()
        return subprocess.CompletedProcess(args, 0, "" if wait else "1\n", "")

    refresh = AsyncMock(side_effect=stall if stage == "refresh" else None)
    monkeypatch.setattr(manager, "_run_adb", run_adb)
    monkeypatch.setattr(manager, "refresh", refresh)

    with pytest.raises(AgentError) as caught:
        await asyncio.wait_for(
            manager._wait_for_emulator_ready("emulator-5554", timeout_s=0.08),
            timeout=1.0,
        )

    assert entered.is_set() and interrupted.is_set()
    assert caught.value.code == "ERR_TIMEOUT"
    assert caught.value.context["timeout_ms"] == 80.0
    expected = {"serial": "emulator-5554", "stage": stage}
    if stage != "wait-for-device":
        expected["property"] = "sys.boot_completed"
    if stage == "refresh":
        expected["boot_completed"] = "1"
        refresh.assert_awaited_once_with()
    else:
        refresh.assert_not_awaited()
    assert caught.value.context["last_context"] == expected
    assert all(5.0 < seconds <= 5.08 for seconds in budgets)


@pytest.mark.asyncio
async def test_caller_cancellation_is_not_reported_as_boot_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = DeviceManager()
    entered = asyncio.Event()

    async def stall(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        entered.set()
        await asyncio.Future()
        pytest.fail("unexpected resume")

    monkeypatch.setattr(manager, "_run_adb", stall)
    task = asyncio.create_task(manager._wait_for_emulator_ready("emulator-5554", timeout_s=5.0))
    try:
        await asyncio.wait_for(entered.wait(), timeout=1.0)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


@pytest.mark.asyncio
async def test_refresh_error_before_deadline_is_not_mislabeled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = DeviceManager()
    original_error = TimeoutError("refresh failed independently")
    monkeypatch.setattr(
        manager,
        "_run_adb",
        AsyncMock(
            side_effect=[
                subprocess.CompletedProcess([], 0, "", ""),
                subprocess.CompletedProcess([], 0, "1\n", ""),
            ]
        ),
    )
    monkeypatch.setattr(manager, "refresh", AsyncMock(side_effect=original_error))
    with pytest.raises(TimeoutError) as caught:
        await manager._wait_for_emulator_ready("emulator-5554", timeout_s=5.0)
    assert caught.value is original_error
