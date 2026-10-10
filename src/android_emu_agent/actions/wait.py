"""Wait engine - Predicates over context and snapshot."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

import structlog

from android_emu_agent.device.io import run_device_io
from android_emu_agent.errors import AgentError

if TYPE_CHECKING:
    import uiautomator2 as u2

logger = structlog.get_logger()

# Errors that can never become true by waiting: an unknown selector key or a bad call
# raises the same way on every poll, so retrying just burns the caller's timeout.
FATAL_POLL_ERRORS = (TypeError, AttributeError, KeyError)


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
        code = self.error.code if self.error else "ERR_TIMEOUT"
        payload: dict[str, Any] = {
            # A condition that ran out of time is an unmet expectation; anything else is
            # a hard failure and must not be reported as if the screen simply never
            # reached the expected state.
            "status": "timeout" if code == "ERR_TIMEOUT" else "failed",
            "elapsed_ms": round(self.elapsed_ms, 2),
            "error": {
                "code": code,
                "message": self.error.message if self.error else "Wait timed out",
            },
        }
        if self.error and self.error.context.get("last_error"):
            payload["error"]["last_error"] = self.error.context["last_error"]
        return payload


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
        """Wait for UI to become idle or for its hierarchy to stabilize."""
        timeout = timeout or self.default_timeout
        start = time.monotonic()
        deadline = start + timeout

        try:
            wait_fn = getattr(device, "wait_idle", None)
            if callable(wait_fn):
                result = await run_device_io(device, wait_fn, timeout=timeout, io_timeout=timeout)
                success = result is not False
            else:
                success = await self._wait_for_stable_hierarchy(device, deadline)

            elapsed = (time.monotonic() - start) * 1000
            if success:
                return WaitResult(success=True, elapsed_ms=elapsed)
            return self._idle_timeout_result(timeout, elapsed)
        except TimeoutError:
            elapsed = (time.monotonic() - start) * 1000
            return self._idle_timeout_result(timeout, elapsed)
        except Exception as e:
            elapsed = (time.monotonic() - start) * 1000
            return WaitResult(
                success=False,
                elapsed_ms=elapsed,
                error=AgentError(
                    code="ERR_TIMEOUT",
                    message=f"Wait idle timed out: {e}",
                    context={"timeout_ms": timeout * 1000},
                    remediation="UI may still be loading; try again or check for dialogs",
                ),
            )

    async def _wait_for_stable_hierarchy(self, device: u2.Device, deadline: float) -> bool:
        """Wait until two consecutive UI hierarchy dumps match."""
        previous: str | None = None

        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False

            hierarchy = await run_device_io(
                device, device.dump_hierarchy, compressed=True, io_timeout=remaining
            )
            if hierarchy == previous:
                return True
            previous = hierarchy

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            await asyncio.sleep(min(self.poll_interval, remaining))

    @staticmethod
    def _idle_timeout_result(timeout: float, elapsed_ms: float) -> WaitResult:
        """Build the standard timeout result for an idle wait."""
        return WaitResult(
            success=False,
            elapsed_ms=elapsed_ms,
            error=AgentError(
                code="ERR_TIMEOUT",
                message="UI did not become idle before the timeout",
                context={"timeout_ms": timeout * 1000},
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
            device,
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
            device,
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
            device,
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
            device,
            predicate=lambda: self._check_text(device, text),
            timeout=timeout,
            error_message=f"Text not found: '{text}'",
            remediation="Text may not appear; check for typos or case sensitivity",
        )

    async def _poll_condition(
        self,
        device: u2.Device,
        predicate: Callable[[], bool],
        timeout: float | None,
        error_message: str,
        remediation: str,
    ) -> WaitResult:
        """Poll a condition until timeout."""
        timeout = timeout or self.default_timeout
        start = time.monotonic()
        deadline = start + timeout
        last_error: Exception | None = None

        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                # Bound queued and running I/O as well as the time between polls. The
                # device's worker may still finish after this await times out.
                matched = await run_device_io(device, predicate, io_timeout=remaining)
                if matched and time.monotonic() < deadline:
                    elapsed = (time.monotonic() - start) * 1000
                    return WaitResult(success=True, elapsed_ms=elapsed)
                last_error = None
            except FATAL_POLL_ERRORS as exc:
                # A malformed selector raises identically on every poll, so waiting the
                # full timeout only hides the real cause behind ERR_TIMEOUT.
                return WaitResult(
                    success=False,
                    elapsed_ms=(time.monotonic() - start) * 1000,
                    error=AgentError(
                        code="ERR_INVALID_SELECTOR",
                        message=f"{error_message}: {exc}",
                        context={"timeout_ms": timeout * 1000, "reason": str(exc)},
                        remediation=(
                            "The wait target can never match; check the selector keys and syntax."
                        ),
                    ),
                )
            except TimeoutError as exc:
                # wait_for raises an empty TimeoutError when the I/O budget expires.
                # Keep a useful preceding transport error rather than replacing it
                # with an empty diagnostic, while still explaining a first-poll stall.
                if str(exc):
                    last_error = exc
                elif last_error is None:
                    last_error = TimeoutError("Device polling did not complete before the timeout")
            except Exception as exc:
                # Transient failures are normal while polling a screen mid-transition,
                # but the last one is what explains an eventual timeout.
                last_error = exc
                logger.debug("wait_poll_error", condition=error_message, error=str(exc))
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            await asyncio.sleep(min(self.poll_interval, remaining))

        elapsed = (time.monotonic() - start) * 1000
        context: dict[str, Any] = {"timeout_ms": timeout * 1000}
        if last_error is not None:
            context["last_error"] = str(last_error)
        return WaitResult(
            success=False,
            elapsed_ms=elapsed,
            error=AgentError(
                code="ERR_TIMEOUT",
                message=error_message,
                context=context,
                remediation=(
                    f"{remediation}. The last polling attempt failed with: {last_error}"
                    if last_error is not None
                    else remediation
                ),
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
