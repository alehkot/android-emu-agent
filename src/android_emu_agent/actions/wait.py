"""Wait engine - Predicates over context and snapshot."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

import structlog

from android_emu_agent.errors import AgentError

if TYPE_CHECKING:
    import uiautomator2 as u2

logger = structlog.get_logger()


class WaitCondition(Enum):
    """Wait condition types."""

    IDLE = "idle"
    ACTIVITY = "activity"
    EXISTS = "exists"
    GONE = "gone"
    TEXT = "text"


@dataclass
class WaitResult:
    """Result of a wait operation."""

    success: bool
    elapsed_ms: float
    error: AgentError | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON response."""
        if self.success:
            return {"status": "done", "elapsed_ms": round(self.elapsed_ms, 2)}
        return {
            "status": "timeout",
            "elapsed_ms": round(self.elapsed_ms, 2),
            "error": {
                "code": self.error.code if self.error else "ERR_TIMEOUT",
                "message": self.error.message if self.error else "Wait timed out",
            },
        }


class WaitEngine:
    """Wait for conditions on device state."""

    def __init__(self, default_timeout: float = 10.0, poll_interval: float = 0.5) -> None:
        self.default_timeout = default_timeout
        self.poll_interval = poll_interval

    async def wait_idle(
        self,
        device: u2.Device,
        timeout: float | None = None,
    ) -> WaitResult:
        """Wait for UI to become idle."""
        timeout = timeout or self.default_timeout
        start = time.time()

        try:
            wait_fn = getattr(device, "wait_idle", None)
            if wait_fn is None:
                wait_fn = getattr(device, "wait_activity", None)
            if wait_fn is None:
                await asyncio.sleep(timeout)
            else:
                await asyncio.to_thread(wait_fn, timeout=timeout)
            elapsed = (time.time() - start) * 1000
            return WaitResult(success=True, elapsed_ms=elapsed)
        except Exception as e:
            elapsed = (time.time() - start) * 1000
            return WaitResult(
                success=False,
                elapsed_ms=elapsed,
                error=AgentError(
                    code="ERR_TIMEOUT",
                    message=f"Wait idle timed out: {e}",
                    context={},
                    remediation="UI may still be loading; try again or check for dialogs",
                ),
            )

    async def wait_activity(
        self,
        device: u2.Device,
        activity_pattern: str,
        timeout: float | None = None,
    ) -> WaitResult:
        """Wait for a specific activity to appear."""
        return await self._poll_condition(
            predicate=lambda: self._check_activity(device, activity_pattern),
            timeout=timeout,
            error_message=f"Activity '{activity_pattern}' not found",
            remediation="Check activity name or wait longer",
        )

    async def wait_exists(
        self,
        device: u2.Device,
        selector: dict[str, str],
        timeout: float | None = None,
    ) -> WaitResult:
        """Wait for an element to exist."""
        return await self._poll_condition(
            predicate=lambda: self._check_exists(device, selector),
            timeout=timeout,
            error_message=f"Element not found: {selector}",
            remediation="Element may not appear; check selector",
        )

    async def wait_gone(
        self,
        device: u2.Device,
        selector: dict[str, str],
        timeout: float | None = None,
    ) -> WaitResult:
        """Wait for an element to disappear."""
        return await self._poll_condition(
            predicate=lambda: not self._check_exists(device, selector),
            timeout=timeout,
            error_message=f"Element still present: {selector}",
            remediation="Element may be persistent; try different approach",
        )

    async def wait_text(
        self,
        device: u2.Device,
        text: str,
        timeout: float | None = None,
    ) -> WaitResult:
        """Wait for text to appear on screen."""
        return await self._poll_condition(
            predicate=lambda: self._check_text(device, text),
            timeout=timeout,
            error_message=f"Text not found: '{text}'",
            remediation="Text may not appear; check for typos or case sensitivity",
        )

    async def _poll_condition(
        self,
        predicate: Callable[[], bool],
        timeout: float | None,
        error_message: str,
        remediation: str,
    ) -> WaitResult:
        """Poll a condition until timeout."""
        timeout = timeout or self.default_timeout
        start = time.time()

        while time.time() - start < timeout:
            try:
                if await asyncio.to_thread(predicate):
                    elapsed = (time.time() - start) * 1000
                    return WaitResult(success=True, elapsed_ms=elapsed)
            except Exception:
                pass  # Ignore errors during polling
            await asyncio.sleep(self.poll_interval)

        elapsed = (time.time() - start) * 1000
        return WaitResult(
            success=False,
            elapsed_ms=elapsed,
            error=AgentError(
                code="ERR_TIMEOUT",
                message=error_message,
                context={"timeout_ms": timeout * 1000},
                remediation=remediation,
            ),
        )

    def _check_activity(self, device: u2.Device, pattern: str) -> bool:
        """Check if current activity matches pattern."""
        info = device.app_current()
        current = info.get("activity", "")
        return pattern in current

    def _check_exists(self, device: u2.Device, selector: dict[str, str]) -> bool:
        """Check if element exists."""
        return bool(device(**selector).exists())

    def _check_text(self, device: u2.Device, text: str) -> bool:
        """Check if text exists on screen."""
        return bool(device(text=text).exists()) or bool(device(textContains=text).exists())
