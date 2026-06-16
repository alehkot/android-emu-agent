"""Tests for Android system surface manager."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from android_emu_agent.errors import AgentError
from android_emu_agent.system.manager import SystemManager


@dataclass
class ShellResult:
    output: str


class FakeDevice:
    def __init__(self, outputs: dict[str, str] | None = None) -> None:
        self.outputs = outputs or {}
        self.commands: list[str] = []

    def shell(self, command: str) -> ShellResult:
        self.commands.append(command)
        return ShellResult(self.outputs.get(command, "ok"))


def test_parse_permissions_combines_requested_and_runtime_state() -> None:
    """Should preserve requested-only permissions and granted runtime state."""
    manager = SystemManager()
    permissions = manager.parse_permissions(
        """
        requested permissions:
          android.permission.CAMERA
          android.permission.POST_NOTIFICATIONS
        runtime permissions:
          android.permission.CAMERA: granted=true, flags=[ USER_SENSITIVE_WHEN_GRANTED ]
          android.permission.POST_NOTIFICATIONS: granted=false, flags=[ USER_SET ]
        """
    )

    assert permissions == [
        {
            "permission": "android.permission.CAMERA",
            "granted": True,
            "source": "runtime_permissions",
        },
        {
            "permission": "android.permission.POST_NOTIFICATIONS",
            "granted": False,
            "source": "runtime_permissions",
        },
    ]


@pytest.mark.asyncio
async def test_grant_and_revoke_permission_build_shell_commands() -> None:
    """Should quote package and permission arguments in pm commands."""
    manager = SystemManager()
    device = FakeDevice()

    grant = await manager.grant_permission(
        device,
        "com.example.app",
        "android.permission.POST_NOTIFICATIONS",
    )
    revoke = await manager.revoke_permission(
        device,
        "com.example.app",
        "android.permission.POST_NOTIFICATIONS",
    )

    assert grant["granted"] is True
    assert revoke["granted"] is False
    assert device.commands == [
        "pm grant com.example.app android.permission.POST_NOTIFICATIONS",
        "pm revoke com.example.app android.permission.POST_NOTIFICATIONS",
    ]


@pytest.mark.asyncio
async def test_list_permissions_formats_output() -> None:
    """Should return structured permissions and a concise human output."""
    dumpsys = """
    requested permissions:
      android.permission.CAMERA
    runtime permissions:
      android.permission.CAMERA: granted=true, flags=[ USER_SET ]
    """
    device = FakeDevice({"dumpsys package com.example.app": dumpsys})
    manager = SystemManager()

    result = await manager.list_permissions(device, "com.example.app")

    assert result["count"] == 1
    assert result["permissions"][0]["permission"] == "android.permission.CAMERA"
    assert result["output"] == "android.permission.CAMERA granted"
    assert device.commands == ["dumpsys package com.example.app"]


@pytest.mark.asyncio
async def test_invalid_permission_rejected_before_shell() -> None:
    """Should reject permission names with whitespace or shell separators."""
    device = FakeDevice()
    manager = SystemManager()

    with pytest.raises(AgentError) as exc_info:
        await manager.grant_permission(device, "com.example.app", "android.permission.CAMERA;id")

    assert exc_info.value.code == "ERR_INVALID_PERMISSION"
    assert device.commands == []
