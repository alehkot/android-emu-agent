"""Preserve Android activity class names through launch and task dispatch."""

from __future__ import annotations

import shlex
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from android_emu_agent.daemon import server
from android_emu_agent.daemon.models import AppLaunchRequest, TaskRunRequest
from android_emu_agent.device.manager import DeviceManager
from android_emu_agent.tasks import TaskManager

ACTIVITIES = [
    ("MainActivity", ".MainActivity"),
    (".MainActivity", ".MainActivity"),
    (".ui.MainActivity", ".ui.MainActivity"),
    ("com.example.app.MainActivity", "com.example.app.MainActivity"),
    ("org.shared.ui.MainActivity", "org.shared.ui.MainActivity"),
    ("org.shared.ui.Outer$Inner", "org.shared.ui.Outer$Inner"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("activity", "expected"), ACTIVITIES)
@pytest.mark.parametrize("resolved", [False, True])
@pytest.mark.parametrize("wait_debugger", [False, True])
async def test_launch_preserves_activity_class(
    activity: str, expected: str, resolved: bool, wait_debugger: bool
) -> None:
    """Both explicit and resolved classes retain Android component semantics."""
    manager = DeviceManager()
    device = MagicMock()
    if resolved:
        device.shell.return_value = f"priority=0 preferredOrder=0\ncom.example.app/{activity}"
    device.shell2.return_value = SimpleNamespace(returncode=0, output="Starting: Intent { ... }")

    with patch.object(manager, "get_adb_device", new=AsyncMock(return_value=device)):
        result = await manager.app_launch(
            "emulator-5554",
            "com.example.app",
            activity=None if resolved else activity,
            wait_for_debugger=wait_debugger,
        )

    assert result == expected
    expected_args = ["am", "start", *(["-D"] if wait_debugger else [])]
    expected_args.extend(["-n", f"com.example.app/{expected}"])
    assert shlex.split(device.shell2.call_args.args[0]) == expected_args
    assert device.shell2.call_count == 1
    assert device.shell.call_count == (1 if resolved else 0)
    if resolved:
        assert shlex.split(device.shell.call_args_list[0].args[0]) == [
            "cmd",
            "package",
            "resolve-activity",
            "--brief",
            "-c",
            "android.intent.category.LAUNCHER",
            "com.example.app",
        ]


@pytest.mark.asyncio
@pytest.mark.parametrize(("activity", "expected"), ACTIVITIES)
@pytest.mark.parametrize("as_task", [False, True])
async def test_launch_endpoint_and_task_preserve_activity_class(
    activity: str, expected: str, as_task: bool
) -> None:
    """Real request normalization and endpoint dispatch reach the real manager."""
    manager = DeviceManager()
    device = MagicMock()
    device.shell2.return_value = SimpleNamespace(returncode=0, output="Starting: Intent { ... }")
    core = SimpleNamespace(
        device_manager=manager,
        session_manager=SimpleNamespace(
            get_session=AsyncMock(return_value=SimpleNamespace(device_serial="emulator-5554"))
        ),
        task_manager=TaskManager(),
    )
    with (
        patch.object(server.app.state, "core", core, create=True),
        patch.object(manager, "get_adb_device", new=AsyncMock(return_value=device)),
    ):
        if as_task:
            result = await server.task_run(
                TaskRunRequest(
                    session_id="s-test",
                    task={
                        "steps": [
                            {
                                "app": "launch",
                                "package": "com.example.app",
                                "activity": activity,
                                "wait_debugger": True,
                            }
                        ]
                    },
                )
            )
            assert isinstance(result, dict)
            assert result["passed"] is True
            assert result["steps"][0]["response"]["activity"] == expected
        else:
            result = await server.app_launch(
                AppLaunchRequest(
                    session_id="s-test",
                    package="com.example.app",
                    activity=activity,
                    wait_debugger=True,
                )
            )
            assert isinstance(result, dict)
            assert result["activity"] == expected
        assert result["status"] == "done"
    assert shlex.split(device.shell2.call_args.args[0]) == [
        "am",
        "start",
        "-D",
        "-n",
        f"com.example.app/{expected}",
    ]
