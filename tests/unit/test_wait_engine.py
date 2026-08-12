"""Tests for wait engine synchronization behavior."""

from __future__ import annotations

import asyncio
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from android_emu_agent.actions.wait import WaitEngine


def test_wait_idle_uses_device_primitive_when_available() -> None:
    """A device-specific idle primitive should remain the preferred path."""
    calls: list[float] = []

    class Device:
        def wait_idle(self, *, timeout: float) -> bool:
            calls.append(timeout)
            return True

    result = asyncio.run(WaitEngine().wait_idle(cast(Any, Device()), timeout=0.25))

    assert result.success is True
    assert calls == [0.25]


def test_wait_idle_falls_back_to_stable_hierarchy_not_wait_activity() -> None:
    """uiautomator2 devices should use hierarchy stability, not an invalid activity call."""

    class Device:
        def __init__(self) -> None:
            self.dumps = iter(["<first />", "<stable />", "<stable />"])
            self.wait_activity_called = False

        def wait_activity(self, activity: str, timeout: float = 10) -> bool:
            self.wait_activity_called = True
            raise AssertionError((activity, timeout))

        def dump_hierarchy(self, *, compressed: bool) -> str:
            assert compressed is True
            return next(self.dumps)

    device = Device()
    result = asyncio.run(WaitEngine(poll_interval=0.001).wait_idle(cast(Any, device), timeout=0.1))

    assert result.success is True
    assert device.wait_activity_called is False


def test_wait_idle_times_out_when_hierarchy_never_stabilizes() -> None:
    """A changing hierarchy should produce the normal timeout result."""

    class Device:
        def __init__(self) -> None:
            self.counter = 0

        def dump_hierarchy(self, *, compressed: bool) -> str:
            assert compressed is True
            self.counter += 1
            return f"<hierarchy generation='{self.counter}' />"

    result = asyncio.run(
        WaitEngine(poll_interval=0.001).wait_idle(cast(Any, Device()), timeout=0.01)
    )

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "ERR_TIMEOUT"
    assert result.error.context == {"timeout_ms": 10.0}


def test_wait_idle_normalizes_asyncio_deadline_timeout() -> None:
    """The wait_for deadline race should produce the standard timeout payload."""
    engine = WaitEngine()

    with patch.object(
        engine,
        "_wait_for_stable_hierarchy",
        AsyncMock(side_effect=TimeoutError),
    ):
        result = asyncio.run(engine.wait_idle(cast(Any, object()), timeout=0.01))

    assert result.success is False
    assert result.error is not None
    assert result.error.message == "UI did not become idle before the timeout"
    assert result.error.context == {"timeout_ms": 10.0}


class TestPollConditionClock:
    """Tests that polling deadlines do not depend on the wall clock."""

    @pytest.mark.asyncio
    async def test_deadline_survives_wall_clock_jump(self, monkeypatch) -> None:
        """A backward system clock step must not extend the wait past its timeout."""
        from android_emu_agent.actions import wait as wait_module

        engine = wait_module.WaitEngine(default_timeout=0.3, poll_interval=0.05)
        device = MagicMock()
        device.serial = "emulator-5554"

        # Simulate NTP stepping the wall clock backwards by an hour mid-wait.
        monkeypatch.setattr(wait_module.time, "time", lambda: 0.0)

        result = await asyncio.wait_for(
            engine._poll_condition(
                device,
                predicate=lambda: False,
                timeout=0.3,
                error_message="never",
                remediation="none",
            ),
            timeout=5.0,
        )

        assert result.success is False
        assert result.error is not None
        assert result.error.code == "ERR_TIMEOUT"
