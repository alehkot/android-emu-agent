"""Tests for ReliabilityManager."""

from __future__ import annotations

from pathlib import Path
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

    def test_parse_meminfo_summary_extracts_headline_counters(self) -> None:
        """Should parse stable counters from dumpsys meminfo output."""
        from android_emu_agent.reliability.manager import ReliabilityManager

        output = """
        Native Heap     12,345
        Dalvik Heap      6,789
        TOTAL PSS:      22,222
        TOTAL RSS:      33,333
        """

        assert ReliabilityManager.parse_meminfo_summary(output) == {
            "total_pss_kb": 22222,
            "total_rss_kb": 33333,
            "native_heap_kb": 12345,
            "dalvik_heap_kb": 6789,
        }

    def test_parse_gfxinfo_summary_extracts_frame_metrics(self) -> None:
        """Should parse frame totals, jank, and percentiles."""
        from android_emu_agent.reliability.manager import ReliabilityManager

        output = """
        Total frames rendered: 120
        Janky frames: 6 (5.00%)
        50th percentile: 8ms
        90th percentile: 17ms
        """

        assert ReliabilityManager.parse_gfxinfo_summary(output) == {
            "total_frames": 120,
            "janky_frames": 6,
            "janky_percent": "5.00%",
            "percentiles": {"p50_ms": 8.0, "p90_ms": 17.0},
        }

    @pytest.mark.asyncio
    async def test_profile_collects_bounded_sections(self) -> None:
        """Should aggregate process, memory, graphics, background, exit, and events data."""
        from android_emu_agent.reliability.manager import CommandOutput, ReliabilityManager

        manager = ReliabilityManager()
        mock_device = MagicMock()

        with (
            patch.object(
                manager,
                "process_info",
                AsyncMock(return_value={"pid": 123, "oom_score_adj": "0"}),
            ),
            patch.object(manager, "meminfo", AsyncMock(return_value="TOTAL PSS: 12345")),
            patch.object(
                manager,
                "gfxinfo",
                AsyncMock(return_value="Total frames rendered: 100\nJanky frames: 4 (4.00%)"),
            ),
            patch.object(
                manager,
                "background_restrictions",
                AsyncMock(return_value={"appops": "allow", "standby_bucket": "active"}),
            ),
            patch.object(manager, "exit_info", AsyncMock(return_value="recent exit")),
            patch.object(
                manager,
                "logcat_events",
                AsyncMock(
                    return_value=CommandOutput(
                        output="06-01 am_crash com.example.app\n06-01 am_anr other.app",
                        line_count=2,
                        total_lines=10,
                    )
                ),
            ),
        ):
            profile = await manager.profile(mock_device, "com.example.app", since="100")

        assert profile["package"] == "com.example.app"
        sections = profile["sections"]
        assert sections["process"]["pid"] == 123
        assert "ps" not in sections["process"]
        assert sections["memory"]["summary"]["total_pss_kb"] == 12345
        assert sections["graphics"]["summary"]["janky_frames"] == 4
        assert sections["events"]["line_count"] == 1
        assert "output" not in sections["memory"]
        assert "PROFILE com.example.app" in profile["output"]


class TestDropboxPrint:
    """Tests for DropBoxManager entry printing."""

    @pytest.mark.asyncio
    async def test_dropbox_print_quotes_tag(self) -> None:
        """Should quote tags before passing them to adb shell."""
        from android_emu_agent.reliability.manager import ReliabilityManager

        manager = ReliabilityManager()
        mock_device = MagicMock()

        with patch.object(manager, "_shell", AsyncMock(return_value="ENTRY")) as shell_mock:
            output = await manager.dropbox_print(mock_device, "data_app_crash;id")

        assert output == "ENTRY"
        shell_mock.assert_awaited_once_with(
            mock_device, "dumpsys dropbox --print 'data_app_crash;id'"
        )


class TestNativePerformanceArtifacts:
    """Tests for bounded native artifact captures."""

    @pytest.mark.asyncio
    async def test_perfetto_trace_captures_and_pulls_artifact(self, tmp_path: Path) -> None:
        """Should run perfetto, pull the trace, and clean up the remote file."""
        from android_emu_agent.reliability.manager import ReliabilityManager

        manager = ReliabilityManager(output_dir=tmp_path)
        mock_device = MagicMock()

        with (
            patch.object(manager, "_timestamp", return_value="20260616_120000"),
            patch.object(manager, "_shell", AsyncMock(return_value="")) as shell_mock,
            patch.object(manager, "_run_adb", AsyncMock()) as adb_mock,
        ):
            result = await manager.perfetto_trace(
                mock_device,
                "emulator-5554",
                duration_seconds=3,
                categories="sched gfx",
            )

        assert result["path"] == str(tmp_path / "perfetto_emulator-5554_20260616_120000.perfetto-trace")
        assert "perfetto -o" in shell_mock.await_args_list[0].args[1]
        assert "-t 3s sched gfx" in shell_mock.await_args_list[0].args[1]
        adb_mock.assert_awaited_once_with(
            "emulator-5554",
            [
                "pull",
                "/data/misc/perfetto-traces/perfetto_emulator-5554_20260616_120000.perfetto-trace",
                str(tmp_path / "perfetto_emulator-5554_20260616_120000.perfetto-trace"),
            ],
        )
        assert shell_mock.await_args_list[-1].args[1].startswith("rm -f ")

    @pytest.mark.asyncio
    async def test_simpleperf_record_writes_report_and_pulls_data(self, tmp_path: Path) -> None:
        """Should record simpleperf data and write a local text report."""
        from android_emu_agent.reliability.manager import ReliabilityManager

        manager = ReliabilityManager(output_dir=tmp_path)
        mock_device = MagicMock()

        with (
            patch.object(manager, "_timestamp", return_value="20260616_120000"),
            patch.object(manager, "_pidof", AsyncMock(return_value=1234)),
            patch.object(
                manager,
                "_shell",
                AsyncMock(side_effect=["", "Samples: 42", ""]),
            ) as shell_mock,
            patch.object(manager, "_run_adb", AsyncMock()) as adb_mock,
        ):
            result = await manager.simpleperf_record(
                mock_device,
                "emulator-5554",
                "com.example.app",
                duration_seconds=2,
            )

        assert result["pid"] == 1234
        assert Path(result["report_path"]).read_text(encoding="utf-8") == "Samples: 42"
        assert "simpleperf record -p 1234 --duration 2" in shell_mock.await_args_list[0].args[1]
        assert "simpleperf report -i" in shell_mock.await_args_list[1].args[1]
        adb_mock.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_screenrecord_captures_and_pulls_video(self, tmp_path: Path) -> None:
        """Should run screenrecord with bounded duration and pull the mp4."""
        from android_emu_agent.reliability.manager import ReliabilityManager

        manager = ReliabilityManager(output_dir=tmp_path)
        mock_device = MagicMock()

        with (
            patch.object(manager, "_timestamp", return_value="20260616_120000"),
            patch.object(manager, "_shell", AsyncMock(return_value="")) as shell_mock,
            patch.object(manager, "_run_adb", AsyncMock()) as adb_mock,
        ):
            result = await manager.screenrecord(
                mock_device,
                "emulator-5554",
                duration_seconds=5,
                bit_rate=4_000_000,
            )

        assert result["path"] == str(tmp_path / "screenrecord_emulator-5554_20260616_120000.mp4")
        assert (
            shell_mock.await_args_list[0].args[1]
            == "screenrecord --time-limit 5 --bit-rate 4000000 "
            "/sdcard/screenrecord_emulator-5554_20260616_120000.mp4"
        )
        adb_mock.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_perfetto_rejects_unbounded_duration(self, tmp_path: Path) -> None:
        """Native captures should enforce bounded durations."""
        from android_emu_agent.errors import AgentError
        from android_emu_agent.reliability.manager import ReliabilityManager

        manager = ReliabilityManager(output_dir=tmp_path)

        with pytest.raises(AgentError) as exc_info:
            await manager.perfetto_trace(
                MagicMock(),
                "emulator-5554",
                duration_seconds=0,
            )

        assert exc_info.value.code == "ERR_INVALID_DURATION"
