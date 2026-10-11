"""Action executor - UI action execution with retries and fallbacks."""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

import structlog

from android_emu_agent.device.io import run_device_io
from android_emu_agent.errors import AgentError, ambiguous_selector_error
from android_emu_agent.ui.ref_resolver import LocatorBundle

if TYPE_CHECKING:
    import uiautomator2 as u2

logger = structlog.get_logger()


@dataclass
class RetryPolicy:
    """Configurable retry behavior."""

    max_attempts: int = 3
    base_delay_ms: int = 300
    backoff_multiplier: float = 2.0
    max_delay_ms: int = 2000

    def get_delay(self, attempt: int) -> int:
        """Calculate delay for attempt (0-indexed).

        Args:
            attempt: The attempt number (0 for first retry)

        Returns:
            Delay in milliseconds
        """
        delay = self.base_delay_ms * (self.backoff_multiplier**attempt)
        return min(int(delay), self.max_delay_ms)


class ActionType(Enum):
    """Supported action types."""

    TAP = "tap"
    LONG_TAP = "long_tap"
    DOUBLE_TAP = "double_tap"
    SWIPE = "swipe"
    SCROLL = "scroll"
    SET_TEXT = "set_text"
    CLEAR = "clear"
    FOCUS = "focus"
    BACK = "back"
    HOME = "home"
    RECENTS = "recents"


class SwipeDirection(Enum):
    """Swipe direction for scroll/swipe actions."""

    UP = "up"
    DOWN = "down"
    LEFT = "left"
    RIGHT = "right"


@dataclass
class ActionResult:
    """Result of an action execution."""

    success: bool
    elapsed_ms: float
    error: AgentError | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON response."""
        if self.success:
            return {"status": "done", "elapsed_ms": round(self.elapsed_ms, 2)}
        return {
            "status": "error",
            "elapsed_ms": round(self.elapsed_ms, 2),
            "error": {
                "code": self.error.code if self.error else "UNKNOWN",
                "message": self.error.message if self.error else "Unknown error",
                "remediation": self.error.remediation if self.error else None,
            },
        }


class ActionExecutor:
    """Executes UI actions on device with retry logic."""

    def __init__(self, max_retries: int = 2, retry_delay: float = 0.3) -> None:
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    def _calculate_swipe_coords(
        self,
        bounds: list[int],
        direction: SwipeDirection,
        distance: float,
    ) -> tuple[tuple[int, int], tuple[int, int]]:
        """Calculate start and end coordinates for swipe.

        Args:
            bounds: Container bounds [left, top, right, bottom]
            direction: Swipe direction
            distance: Fraction of container to swipe (0.0-1.0)

        Returns:
            Tuple of (start_coords, end_coords)
        """
        left, top, right, bottom = bounds
        cx = (left + right) // 2
        cy = (top + bottom) // 2
        width = right - left
        height = bottom - top

        offset_x = int(width * distance / 2)
        offset_y = int(height * distance / 2)

        if direction == SwipeDirection.UP:
            return (cx, cy + offset_y), (cx, cy - offset_y)
        elif direction == SwipeDirection.DOWN:
            return (cx, cy - offset_y), (cx, cy + offset_y)
        elif direction == SwipeDirection.LEFT:
            return (cx + offset_x, cy), (cx - offset_x, cy)
        else:  # RIGHT
            return (cx - offset_x, cy), (cx + offset_x, cy)

    async def execute(
        self,
        device: u2.Device,
        action: ActionType,
        locator: LocatorBundle | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        """Execute an action on the device."""
        start = time.monotonic()

        try:
            if action == ActionType.BACK:
                await self._press_back(device)
            elif action == ActionType.HOME:
                await self._press_home(device)
            elif action == ActionType.RECENTS:
                await self._press_recents(device)
            elif locator is None:
                raise AgentError(
                    code="ERR_NO_LOCATOR",
                    message="Action requires a locator",
                    context={},
                    remediation="Provide a valid ^ref or selector",
                )
            elif action == ActionType.TAP:
                await self._tap(device, locator)
            elif action == ActionType.LONG_TAP:
                await self._long_tap(device, locator)
            elif action == ActionType.SET_TEXT:
                await self._set_text(device, locator, kwargs.get("text", ""))
            elif action == ActionType.CLEAR:
                await self._clear(device, locator)
            else:
                raise AgentError(
                    code="ERR_UNSUPPORTED_ACTION",
                    message=f"Action not implemented: {action.value}",
                    context={"action": action.value},
                    remediation="Use a supported action type",
                )

            elapsed = (time.monotonic() - start) * 1000
            logger.info("action_executed", action=action.value, elapsed_ms=round(elapsed, 2))
            return ActionResult(success=True, elapsed_ms=elapsed)

        except AgentError as e:
            elapsed = (time.monotonic() - start) * 1000
            return ActionResult(success=False, elapsed_ms=elapsed, error=e)
        except Exception as e:
            elapsed = (time.monotonic() - start) * 1000
            logger.exception("action_failed", action=action.value)
            return ActionResult(
                success=False,
                elapsed_ms=elapsed,
                error=AgentError(
                    code="ERR_ACTION_FAILED",
                    message=str(e),
                    context={"action": action.value},
                    remediation="Take a new snapshot and retry",
                ),
            )

    async def _tap(self, device: u2.Device, locator: LocatorBundle) -> None:
        """Tap an element using locator strategies."""
        element = await self._find_element(device, locator)
        await run_device_io(device, element.click)

    async def _long_tap(self, device: u2.Device, locator: LocatorBundle) -> None:
        """Long tap an element."""
        element = await self._find_element(device, locator)
        await run_device_io(device, element.long_click)

    async def _set_text(self, device: u2.Device, locator: LocatorBundle, text: str) -> None:
        """Set text on an element."""
        element = await self._find_element(device, locator)
        await run_device_io(device, element.set_text, text)

    async def _clear(self, device: u2.Device, locator: LocatorBundle) -> None:
        """Clear text from an element."""
        element = await self._find_element(device, locator)
        await run_device_io(device, element.clear_text)

    async def _press_back(self, device: u2.Device) -> None:
        """Press back button."""
        await run_device_io(device, device.press, "back")

    async def _press_home(self, device: u2.Device) -> None:
        """Press home button."""
        await run_device_io(device, device.press, "home")

    async def _press_recents(self, device: u2.Device) -> None:
        """Press recents button."""
        await run_device_io(device, device.press, "recent")

    async def _find_element(self, device: u2.Device, locator: LocatorBundle) -> Any:
        """Find element using locator bundle strategies."""
        selector_candidates: list[dict[str, str]] = []

        # Strategy 1: resource-id (most reliable)
        if locator.resource_id:
            selector_candidates.append({"resourceId": locator.resource_id})

        # Strategy 2: content-desc
        if locator.content_desc:
            selector_candidates.append({"description": locator.content_desc})

        # Strategy 3: text match
        if locator.text:
            selector_candidates.append({"text": locator.text})

        # Strategy 4: semantic label fallback for Compose/Litho host views
        if locator.label and locator.label not in {locator.text, locator.content_desc}:
            selector_candidates.extend(({"description": locator.label}, {"text": locator.label}))

        ambiguous_match: tuple[str, int] | None = None
        for kwargs in selector_candidates:
            element = device(**kwargs)
            match_count = int(await run_device_io(device, getattr, element, "count"))
            if match_count == 1:
                return element
            if match_count > 1:
                selector_label = " ".join(f"{key}:{value}" for key, value in kwargs.items())
                ambiguous_match = ambiguous_match or (selector_label, match_count)
                logger.warning(
                    "ambiguous_ref_selector_skipped",
                    ref=locator.ref,
                    selector=selector_label,
                    match_count=match_count,
                )

        # Strategy 5: bounds (coordinate fallback)
        if self._bounds_are_usable(locator.bounds):
            # Calculate center point
            x = (locator.bounds[0] + locator.bounds[2]) // 2
            y = (locator.bounds[1] + locator.bounds[3]) // 2
            logger.warning("using_coordinate_fallback", ref=locator.ref, x=x, y=y)
            # Return a coordinate-based "element" proxy
            return _CoordinateProxy(device, x, y)

        if ambiguous_match:
            selector_label, match_count = ambiguous_match
            raise ambiguous_selector_error(selector_label, match_count)

        raise AgentError(
            code="ERR_NOT_FOUND",
            message=f"Element not found: {locator.ref}",
            context={"ref": locator.ref, "locator": locator.to_dict()},
            remediation="Take a new snapshot and use a fresh ^ref",
        )

    @staticmethod
    def _bounds_are_usable(bounds: list[int]) -> bool:
        """Return whether stored ref bounds identify a non-empty rectangle."""
        return (
            len(bounds) == 4
            and all(isinstance(value, int) for value in bounds)
            and bounds[2] > bounds[0]
            and bounds[3] > bounds[1]
        )


class _CoordinateProxy:
    """Proxy for coordinate-based actions when element lookup fails."""

    def __init__(self, device: u2.Device, x: int, y: int) -> None:
        self._device = device
        self._x = x
        self._y = y

    def click(self) -> None:
        """Click at coordinates."""
        self._device.click(self._x, self._y)

    def long_click(self) -> None:
        """Long click at coordinates."""
        self._device.long_click(self._x, self._y)

    def set_text(self, text: str) -> None:
        """Focus the field and replace its text."""
        self._device.click(self._x, self._y)
        if text:
            self._device.send_keys(text, clear=True)
        else:
            self._device.clear_text()

    def clear_text(self) -> None:
        """Focus the field and clear its text."""
        self._device.click(self._x, self._y)
        self._device.clear_text()
