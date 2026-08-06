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
                        "USER PID PPID VSZ RSS WCHAN ADDR S NAME\n"
                        "u0_a123 4321 1 100 50 0 0 S com.example.app",
                        "800",
                        "Name:\texample.app\nState:\tS (sleeping)\nPid:\t4321\n"
                        "PPid:\t1\nVmRSS:\t50 kB\nThreads:\t4\nCapEff:\t0",
                    ]
                ),
            ) as shell_mock,
        ):
            result = await manager.process_info(mock_device, "com.example.app")

        assert result["pid"] == 4321
        assert result["oom_score_adj"] == "800"
        assert "com.example.app" in str(result["ps"])
        assert "State:\tS (sleeping)" in str(result["process_state"])
        assert "VmRSS:\t50 kB" in str(result["process_state"])
        assert "CapEff" not in str(result["process_state"])
        commands = [entry.args[1] for entry in shell_mock.await_args_list]
        assert commands == [
            "ps -p 4321 -o USER,PID,PPID,VSZ,RSS,WCHAN,ADDR,S,NAME",
            "cat /proc/4321/oom_score_adj",
            "cat /proc/4321/status",
        ]


class TestJobScheduler:
    """Tests for package-scoped JobScheduler output."""

    @pytest.mark.asyncio
    async def test_jobscheduler_returns_only_requested_package_jobs(self) -> None:
        """Global settings and other packages should not leak into output."""
        from android_emu_agent.reliability.manager import ReliabilityManager

        manager = ReliabilityManager()
        mock_device = MagicMock()
        dump = """Settings:
  max_jobs=100
Registered 3 jobs:
  JOB #u0a100/1: abc com.other/.OtherJob
    Source: uid=u0a100 user=0 pkg=com.other
    Required constraints: CHARGING
  JOB #u0a101/2: def com.example.app/.SyncJob
    Source: uid=u0a101 user=0 pkg=com.example.app
    Required constraints: CONNECTIVITY
    Unsatisfied constraints: CONNECTIVITY
  JOB androidx.work.systemjobscheduler:u0a101/3: ghi com.example.app/.WorkerJob
    Source: uid=u0a101 user=0 pkg=com.example.app
    Required constraints: CHARGING
Pending queue:
  None
"""

        with patch.object(manager, "_shell", AsyncMock(return_value=dump)) as shell_mock:
            output = await manager.jobscheduler(mock_device, "com.example.app")

        assert output.startswith("Registered jobs for com.example.app: 2")
        assert "com.example.app/.SyncJob" in output
        assert "com.example.app/.WorkerJob" in output
        assert "Unsatisfied constraints: CONNECTIVITY" in output
        assert "Settings:" not in output
        assert "com.other" not in output
        assert "Pending queue:" not in output
        shell_mock.assert_awaited_once_with(mock_device, "dumpsys jobscheduler com.example.app")

    @pytest.mark.asyncio
    async def test_jobscheduler_reports_no_registered_jobs(self) -> None:
        """A package without registered jobs should return a clear bounded result."""
        from android_emu_agent.reliability.manager import ReliabilityManager

        manager = ReliabilityManager()
        mock_device = MagicMock()

        with patch.object(manager, "_shell", AsyncMock(return_value="Settings:\n  max_jobs=100")):
            output = await manager.jobscheduler(mock_device, "com.example.app")

        assert output == "No registered jobs found for com.example.app."

    def test_jobscheduler_output_has_explicit_line_bound(self) -> None:
        """Large packages should be truncated with a visible marker."""
        from android_emu_agent.reliability.manager import (
            JOBSCHEDULER_MAX_CHARS,
            JOBSCHEDULER_MAX_LINES,
            ReliabilityManager,
        )

        lines = [f"line {index}" for index in range(JOBSCHEDULER_MAX_LINES + 20)]

        output = ReliabilityManager._bounded_diagnostic_lines(lines)

        assert len(output.splitlines()) <= JOBSCHEDULER_MAX_LINES
        assert len(output) <= JOBSCHEDULER_MAX_CHARS
        assert "truncated by android-emu-agent" in output

        long_output = ReliabilityManager._bounded_diagnostic_lines(["x" * 20_000] * 5)
        assert len(long_output) <= JOBSCHEDULER_MAX_CHARS
        assert "truncated by android-emu-agent" in long_output


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


class TestShellFailures:
    """Tests for device shell exit-status handling."""

    @pytest.mark.asyncio
    async def test_shell_returns_output_only_after_zero_exit(self) -> None:
        """Successful commands should have their internal status marker removed."""
        from android_emu_agent.reliability.manager import ReliabilityManager

        manager = ReliabilityManager()
        device = MagicMock()
        device.shell.return_value = "entry\n__AEA_EXIT_CODE__:0"

        output = await manager._shell(device, "ls files")

        assert output == "entry"
        assert "__AEA_EXIT_CODE__" in device.shell.call_args.args[0]

    @pytest.mark.asyncio
    async def test_run_as_ls_reports_non_debuggable_app(self) -> None:
        """A rejected run-as command must not be returned as successful listing output."""
        from android_emu_agent.errors import AgentError
        from android_emu_agent.reliability.manager import ReliabilityManager

        manager = ReliabilityManager()
        device = MagicMock()
        device.shell.return_value = "run-as: package not debuggable\n__AEA_EXIT_CODE__:1"

        with pytest.raises(AgentError) as exc_info:
            await manager.run_as_ls(device, "com.example.release", "files")

        assert exc_info.value.code == "ERR_ADB_COMMAND"
        assert exc_info.value.context["reason"] == "run-as: package not debuggable"

    @pytest.mark.asyncio
    async def test_simpleperf_stops_after_record_command_failure(self, tmp_path: Path) -> None:
        """A failed recording must not produce a report or attempt an adb pull."""
        from android_emu_agent.errors import AgentError
        from android_emu_agent.reliability.manager import ReliabilityManager

        manager = ReliabilityManager(output_dir=tmp_path)
        device = MagicMock()
        device.shell.side_effect = [
            "1234\n__AEA_EXIT_CODE__:0",
            "simpleperf: permission denied\n__AEA_EXIT_CODE__:1",
            "\n__AEA_EXIT_CODE__:0",
        ]

        with (
            patch.object(manager, "_run_adb", AsyncMock()) as adb_mock,
            pytest.raises(AgentError) as exc_info,
        ):
            await manager.simpleperf_record(
                device,
                "emulator-5554",
                "com.example.app",
                duration_seconds=1,
            )

        assert exc_info.value.code == "ERR_ADB_COMMAND"
        assert exc_info.value.context["reason"] == "simpleperf: permission denied"
        adb_mock.assert_not_awaited()
        assert list(tmp_path.iterdir()) == []


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

        assert result["path"] == str(
            tmp_path / "perfetto_emulator-5554_20260616_120000.perfetto-trace"
        )
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
    @pytest.mark.parametrize("method_name", ["perfetto_trace", "screenrecord"])
    async def test_native_capture_cleans_remote_file_when_pull_fails(
        self,
        tmp_path: Path,
        method_name: str,
    ) -> None:
        """A failed pull should preserve its error while still removing device artifacts."""
        from android_emu_agent.reliability.manager import ReliabilityManager

        manager = ReliabilityManager(output_dir=tmp_path)
        mock_device = MagicMock()
        method = getattr(manager, method_name)

        with (
            patch.object(manager, "_timestamp", return_value="20260616_120000"),
            patch.object(manager, "_shell", AsyncMock(return_value="")) as shell_mock,
            patch.object(manager, "_run_adb", AsyncMock(side_effect=RuntimeError("pull failed"))),
            pytest.raises(RuntimeError, match="pull failed"),
        ):
            await method(mock_device, "emulator-5554", duration_seconds=1)

        assert shell_mock.await_args_list[-1].args[1].startswith("rm -f ")

    @pytest.mark.asyncio
    async def test_simpleperf_cleans_remote_file_when_report_fails(self, tmp_path: Path) -> None:
        """A report failure should not bypass cleanup of captured simpleperf data."""
        from android_emu_agent.reliability.manager import ReliabilityManager

        manager = ReliabilityManager(output_dir=tmp_path)
        mock_device = MagicMock()

        with (
            patch.object(manager, "_pidof", AsyncMock(return_value=1234)),
            patch.object(
                manager,
                "_shell",
                AsyncMock(side_effect=["", RuntimeError("report failed"), ""]),
            ) as shell_mock,
            pytest.raises(RuntimeError, match="report failed"),
        ):
            await manager.simpleperf_record(
                mock_device,
                "emulator-5554",
                "com.example.app",
                duration_seconds=1,
            )

        assert shell_mock.await_args_list[-1].args[1].startswith("rm -f ")

    @pytest.mark.asyncio
    async def test_cleanup_warning_is_returned_after_successful_capture(
        self, tmp_path: Path
    ) -> None:
        """Successful captures should disclose a remote cleanup failure."""
        from android_emu_agent.reliability.manager import ReliabilityManager

        manager = ReliabilityManager(output_dir=tmp_path)
        mock_device = MagicMock()

        with (
            patch.object(manager, "_timestamp", return_value="20260616_120000"),
            patch.object(
                manager,
                "_shell",
                AsyncMock(side_effect=["", RuntimeError("permission denied")]),
            ),
            patch.object(manager, "_run_adb", AsyncMock()),
        ):
            result = await manager.screenrecord(
                mock_device,
                "emulator-5554",
                duration_seconds=1,
            )

        assert "Unable to remove remote artifact" in result["warning"]

    @pytest.mark.asyncio
    async def test_dump_heap_cleans_remote_file_when_pull_fails(self, tmp_path: Path) -> None:
        """A failed heap pull should still remove the remote dump unless explicitly retained."""
        from android_emu_agent.reliability.manager import ReliabilityManager

        manager = ReliabilityManager(output_dir=tmp_path)
        mock_device = MagicMock()

        with (
            patch.object(manager, "_shell", AsyncMock(return_value="")) as shell_mock,
            patch.object(manager, "_run_adb", AsyncMock(side_effect=RuntimeError("pull failed"))),
            pytest.raises(RuntimeError, match="pull failed"),
        ):
            await manager.dump_heap(
                mock_device,
                "emulator-5554",
                "com.example.app",
                keep_remote=False,
            )

        assert shell_mock.await_args_list[-1].args[1].startswith("rm -f ")

    @pytest.mark.asyncio
    async def test_root_dir_pull_cleans_stage_when_pull_fails(self, tmp_path: Path) -> None:
        """A failed root-directory pull should still remove its staging directory."""
        from android_emu_agent.reliability.manager import ReliabilityManager

        manager = ReliabilityManager(output_dir=tmp_path)
        mock_device = MagicMock()

        with (
            patch.object(manager, "_shell_su", AsyncMock(return_value="")),
            patch.object(manager, "_shell", AsyncMock(return_value="")) as shell_mock,
            patch.object(manager, "_run_adb", AsyncMock(side_effect=RuntimeError("pull failed"))),
            pytest.raises(RuntimeError, match="pull failed"),
        ):
            await manager.pull_root_dir(
                mock_device,
                "emulator-5554",
                "/data/anr",
                "anr",
            )

        shell_mock.assert_awaited_once_with(
            mock_device,
            "rm -rf /data/local/tmp/android-emu-agent/anr",
        )

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

    @pytest.mark.parametrize(
        "filename",
        [
            "../escape",
            "/tmp/escape",
            "nested/trace",
            r"nested\trace",
            "bad\nname",
            "x" * 201,
        ],
    )
    def test_artifact_name_rejects_paths_and_controls(self, filename: str) -> None:
        """Managed reliability outputs must remain inside their artifact directory."""
        from android_emu_agent.errors import AgentError
        from android_emu_agent.reliability.manager import ReliabilityManager

        with pytest.raises(AgentError) as exc_info:
            ReliabilityManager._artifact_name(filename, "default", ".data")

        assert exc_info.value.code == "ERR_INVALID_ARTIFACT_NAME"

    @pytest.mark.asyncio
    async def test_simpleperf_rejects_unsafe_filename_before_device_access(
        self, tmp_path: Path
    ) -> None:
        """An invalid local filename must not start profiling or touch the device."""
        from android_emu_agent.errors import AgentError
        from android_emu_agent.reliability.manager import ReliabilityManager

        manager = ReliabilityManager(output_dir=tmp_path)
        device = MagicMock()

        with (
            patch.object(manager, "_pidof", AsyncMock()) as pidof,
            pytest.raises(AgentError) as exc_info,
        ):
            await manager.simpleperf_record(
                device,
                "emulator-5554",
                "com.example.app",
                duration_seconds=1,
                filename="../../escape",
            )

        assert exc_info.value.code == "ERR_INVALID_ARTIFACT_NAME"
        pidof.assert_not_awaited()
