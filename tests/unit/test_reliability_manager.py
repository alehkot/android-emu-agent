"""Tests for ReliabilityManager."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestProcessInfo:
    """Tests for process_info."""

    @pytest.mark.asyncio
    async def test_process_info_collects_expected_fields(self) -> None:
        """Should return pid, oom score and process snippets."""
        from android_emu_agent.reliability.manager import ReliabilityManager

        manager = ReliabilityManager()
        mock_device = MagicMock()

        with (
            patch.object(manager, "_pidof", AsyncMock(return_value=4321)),
            patch.object(
                manager,
                "_shell",
                AsyncMock(
                    side_effect=[
                        "u0_a123 4321 com.example.app",
                        "800",
                        "*APP* proc com.example.app",
                    ]
                ),
            ),
        ):
            result = await manager.process_info(mock_device, "com.example.app")

        assert result["pid"] == 4321
        assert result["oom_score_adj"] == "800"
        assert "com.example.app" in str(result["ps"])
        assert "proc com.example.app" in str(result["process_state"])


class TestMemGfxInfo:
    """Tests for meminfo/gfxinfo."""

    @pytest.mark.asyncio
    async def test_meminfo_runs_dumpsys_meminfo(self) -> None:
        """Should invoke dumpsys meminfo command."""
        from android_emu_agent.reliability.manager import ReliabilityManager

        manager = ReliabilityManager()
        mock_device = MagicMock()

        with patch.object(manager, "_shell", AsyncMock(return_value="MEMINFO")) as shell_mock:
            output = await manager.meminfo(mock_device, "com.example.app")

        assert output == "MEMINFO"
        shell_mock.assert_awaited_once_with(mock_device, "dumpsys meminfo com.example.app")

    @pytest.mark.asyncio
    async def test_gfxinfo_runs_dumpsys_gfxinfo(self) -> None:
        """Should invoke dumpsys gfxinfo command."""
        from android_emu_agent.reliability.manager import ReliabilityManager

        manager = ReliabilityManager()
        mock_device = MagicMock()

        with patch.object(manager, "_shell", AsyncMock(return_value="GFXINFO")) as shell_mock:
            output = await manager.gfxinfo(mock_device, "com.example.app")

        assert output == "GFXINFO"
        shell_mock.assert_awaited_once_with(mock_device, "dumpsys gfxinfo com.example.app")
