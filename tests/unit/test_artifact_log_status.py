"""A failed logcat must never become a successful (possibly empty) artifact."""

from unittest.mock import MagicMock

import pytest
from uiautomator2.abstract import ShellResponse

from android_emu_agent.artifacts.manager import ArtifactManager
from android_emu_agent.errors import AgentError


@pytest.mark.asyncio
@pytest.mark.parametrize("package", [None, "com.example.app"])
@pytest.mark.parametrize("output", ["logcat: Invalid time specified", "", "partial log data"])
async def test_failed_logcat_preserves_existing_destination(tmp_path, package, output):
    manager = ArtifactManager(tmp_path)
    destination = tmp_path / "logs.txt"
    destination.write_text("previous evidence")
    device = MagicMock()
    responses = [ShellResponse(output, 1)]
    if package:
        responses.insert(0, ShellResponse("1234", 0))
    device.shell.side_effect = responses

    with pytest.raises(AgentError) as error:
        await manager.pull_logs(device, "s-test", package=package, filename="logs.txt")

    assert error.value.code == "ERR_LOGCAT_FAILED"
    assert error.value.context["exit_code"] == 1
    assert error.value.context["output"] == output
    assert error.value.remediation
    assert destination.read_text() == "previous evidence"
    assert list(tmp_path.iterdir()) == [destination]


@pytest.mark.asyncio
@pytest.mark.parametrize("fallback_status", [0, 1])
async def test_pid_fallback_checks_final_capture_status(tmp_path, fallback_status):
    manager = ArtifactManager(tmp_path)
    device = MagicMock()
    device.shell.side_effect = [
        ShellResponse("1234", 0),
        ShellResponse("logcat: unknown option --pid", 1),
        ShellResponse("com.example.app: retained\ncom.other: dropped", fallback_status),
    ]
    if fallback_status:
        with pytest.raises(AgentError) as error:
            await manager.pull_logs(device, "s-test", package="com.example.app")
        assert error.value.code == "ERR_LOGCAT_FAILED"
        assert "--pid" not in error.value.context["command"]
        assert not list(tmp_path.iterdir())
    else:
        path = await manager.pull_logs(device, "s-test", package="com.example.app")
        assert path.read_text() == "com.example.app: retained"
    assert device.shell.call_count == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("output", ["", "logcat: Invalid time specified", "normal log line"])
async def test_successful_logcat_preserves_output_even_when_it_looks_like_error(tmp_path, output):
    manager = ArtifactManager(tmp_path)
    device = MagicMock()
    device.shell.return_value = ShellResponse(output, 0)
    path = await manager.pull_logs(device, "s-test")
    assert path.read_text() == output


@pytest.mark.asyncio
async def test_missing_pid_still_allows_successful_text_filter_fallback(tmp_path):
    manager = ArtifactManager(tmp_path)
    device = MagicMock()
    device.shell.side_effect = [
        ShellResponse("", 1),
        ShellResponse("com.example.app: retained\ncom.other: dropped", 0),
    ]
    path = await manager.pull_logs(device, "s-test", package="com.example.app")
    assert path.read_text() == "com.example.app: retained"


@pytest.mark.asyncio
async def test_successful_pid_capture_does_not_retry_log_text_resembling_option_error(tmp_path):
    manager = ArtifactManager(tmp_path)
    device = MagicMock()
    output = "com.example.app: received unknown option --pid from a child tool"
    device.shell.side_effect = [ShellResponse("1234", 0), ShellResponse(output, 0)]
    path = await manager.pull_logs(device, "s-test", package="com.example.app")
    assert path.read_text() == output
    assert device.shell.call_count == 2
