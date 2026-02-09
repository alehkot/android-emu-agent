"""Context resolver - Activity, window, IME, and dialog detection."""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, TypeVar, cast

import structlog

if TYPE_CHECKING:
    from adbutils import AdbDevice

logger = structlog.get_logger()
T = TypeVar("T")


@dataclass
class UIContext:
    """Current UI context from the device."""

    package: str | None
    activity: str | None
    top_resumed_activity: str | None
    top_window: str | None
    orientation: str
    window_focused: bool
    ime_visible: bool
    ime_package: str | None
    system_dialogs: list[str]


class ContextResolver:
    """Resolves current UI context from device state."""

    async def resolve(self, device: AdbDevice) -> UIContext:
        """Resolve current UI context from device."""
        # Run multiple shell commands in parallel
        results = await asyncio.gather(
            self._get_focused_activity(device),
            self._get_window_info(device),
            self._get_ime_info(device),
            return_exceptions=True,
        )

        activity_info = self._unwrap_result(results[0], default={})
        window_info = self._unwrap_result(results[1], default={})
        ime_info = self._unwrap_result(results[2], default={})

        return UIContext(
            package=activity_info.get("package"),
            activity=activity_info.get("activity"),
            top_resumed_activity=activity_info.get("top_resumed"),
            top_window=self._string_or_none(window_info.get("top_window")),
            orientation=self._string_value(window_info.get("orientation"), "PORTRAIT"),
            window_focused=bool(window_info.get("focused", True)),
            ime_visible=bool(ime_info.get("visible", False)),
            ime_package=self._string_or_none(ime_info.get("package")),
            system_dialogs=self._detect_system_dialogs(activity_info, window_info),
        )

    async def _get_focused_activity(self, device: AdbDevice) -> dict[str, str]:
        """Get focused activity info via dumpsys."""

        def _run() -> str:
            return cast(
                str,
                device.shell(
                    "dumpsys activity activities | grep -E 'mResumedActivity|mFocusedActivity'"
                ),
            )

        output = await asyncio.to_thread(_run)
        if not output.strip():
            logger.warning("focused_activity_empty", hint="grep returned no match for mResumedActivity/mFocusedActivity — field name may have changed in this Android version")
        result: dict[str, str] = {}

        # Parse mResumedActivity: ActivityRecord{... com.foo/.MainActivity ...}
        resumed_match = re.search(r"mResumedActivity.*?(\S+/\S+)", output)
        if resumed_match:
            full = resumed_match.group(1)
            result["top_resumed"] = full
            if "/" in full:
                pkg, activity = full.split("/", 1)
                result["package"] = pkg
                result["activity"] = activity

        return result

    async def _get_window_info(self, device: AdbDevice) -> dict[str, str | bool]:
        """Get window focus and orientation info."""

        def _run() -> str:
            focus = device.shell("dumpsys window | grep -E 'mCurrentFocus|mFocusedApp'")
            orientation = device.shell("dumpsys input | grep -E 'SurfaceOrientation'")
            return f"{focus}\n{orientation}"

        output = await asyncio.to_thread(_run)
        if not output.strip():
            logger.warning("window_info_empty", hint="grep returned no match for mCurrentFocus/mFocusedApp/SurfaceOrientation — field name may have changed in this Android version")
        result: dict[str, str | bool] = {"focused": True}

        focus_match = re.search(r"mCurrentFocus=Window\{([^}]+)\}", output)
        if focus_match:
            result["top_window"] = focus_match.group(1)

        orientation = "PORTRAIT"
        orientation_match = re.search(r"SurfaceOrientation:\s*(\d)", output)
        if orientation_match:
            value = orientation_match.group(1)
            if value in {"1", "3"}:
                orientation = "LANDSCAPE"
        result["orientation"] = orientation

        return result

    async def _get_ime_info(self, device: AdbDevice) -> dict[str, str | bool]:
        """Get IME (keyboard) visibility info."""

        def _run() -> str:
            return cast(str, device.shell("dumpsys input_method | grep -E 'mInputShown|mCurId'"))

        output = await asyncio.to_thread(_run)
        result: dict[str, str | bool] = {"visible": False}

        if "mInputShown=true" in output:
            result["visible"] = True

        id_match = re.search(r"mCurId=(\S+)", output)
        if id_match:
            result["package"] = id_match.group(1)

        return result

    def _detect_system_dialogs(
        self,
        activity_info: dict[str, str],  # noqa: ARG002
        window_info: dict[str, str | bool],
    ) -> list[str]:
        """Detect common system dialogs."""
        dialogs: list[str] = []
        top_window = str(window_info.get("top_window", ""))

        # Common system dialog patterns
        if "GrantPermissions" in top_window:
            dialogs.append("runtime_permission")
        if "Chooser" in top_window:
            dialogs.append("chooser")
        if "ResolverActivity" in top_window:
            dialogs.append("app_chooser")

        return dialogs

    @staticmethod
    def _unwrap_result(result: T | BaseException, *, default: T) -> T:
        if isinstance(result, BaseException):
            return default
        return result

    @staticmethod
    def _string_or_none(value: object | None) -> str | None:
        if value is None:
            return None
        return str(value)

    @staticmethod
    def _string_value(value: object | None, fallback: str) -> str:
        if value is None:
            return fallback
        if isinstance(value, bool):
            return fallback
        return str(value)
