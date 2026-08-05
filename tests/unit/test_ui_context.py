"""Tests for Android UI context resolution."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from android_emu_agent.ui.context import ContextResolver


@pytest.mark.asyncio
async def test_resolve_parses_android_36_top_resumed_activity() -> None:
    """Android 36 foreground context should use topResumedActivity."""
    device = MagicMock()

    def shell(command: str) -> str:
        if command.startswith("dumpsys activity"):
            return "topResumedActivity=ActivityRecord{123 u0 com.example.app/.MainActivity t77}"
        if command.startswith("dumpsys window"):
            return "mCurrentFocus=Window{abc u0 com.example.app/com.example.app.MainActivity}"
        if command.startswith("dumpsys input |"):
            return "SurfaceOrientation: 0"
        return ""

    device.shell.side_effect = shell

    context = await ContextResolver().resolve(device)

    assert context.package == "com.example.app"
    assert context.activity == ".MainActivity"
    assert context.top_resumed_activity == "com.example.app/.MainActivity"


@pytest.mark.asyncio
async def test_resolve_falls_back_to_current_window_component() -> None:
    """Window focus should supply context when activity fields are unavailable."""
    device = MagicMock()

    def shell(command: str) -> str:
        if command.startswith("dumpsys activity"):
            return ""
        if command.startswith("dumpsys window"):
            return "mCurrentFocus=Window{abc u0 com.example.app/com.example.app.MainActivity}"
        if command.startswith("dumpsys input |"):
            return "SurfaceOrientation: 0"
        return ""

    device.shell.side_effect = shell

    context = await ContextResolver().resolve(device)

    assert context.package == "com.example.app"
    assert context.activity == "com.example.app.MainActivity"
    assert context.top_resumed_activity is None
