"""Tests for ArtifactManager."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


class TestPullLogs:
    """Tests for pull_logs."""

    @pytest.mark.asyncio
    async def test_pull_logs_uses_pid_and_level_filters(self, tmp_path) -> None:
        """Should include --pid and level filters when available."""
        from android_emu_agent.artifacts.manager import ArtifactManager

        manager = ArtifactManager(output_dir=tmp_path)
        mock_device = MagicMock()
        mock_device.shell.side_effect = [
            "1234 4567",
            "01-01 10:00:00.000 E/com.example.app(1234): boom",
        ]

        path = await manager.pull_logs(
            mock_device,
            session_id="s-abc123",
            package="com.example.app",
            level="error",
            since="10m",
            follow=False,
        )

        assert path.exists()
        assert "boom" in path.read_text()
        second_call = mock_device.shell.call_args_list[1][0][0]
        assert "--pid=1234" in second_call
        assert "*:E" in second_call
        assert " -d " in f" {second_call} "

    @pytest.mark.asyncio
    async def test_pull_logs_filters_by_package_when_pid_missing(self, tmp_path) -> None:
        """Should fallback to line filtering when pid lookup fails."""
        from android_emu_agent.artifacts.manager import ArtifactManager

        manager = ArtifactManager(output_dir=tmp_path)
        mock_device = MagicMock()
        mock_device.shell.side_effect = [
            "",
            (
                "01-01 10:00:00.000 I/com.other(999): ignore\n"
                "01-01 10:00:01.000 W/com.example.app(111): keep"
            ),
        ]

        path = await manager.pull_logs(
            mock_device,
            session_id="s-abc123",
            package="com.example.app",
            level=None,
            since=None,
            follow=True,
        )

        output = path.read_text()
        assert "keep" in output
        assert "ignore" not in output
        second_call = mock_device.shell.call_args_list[1][0][0]
        assert " -d " not in f" {second_call} "
