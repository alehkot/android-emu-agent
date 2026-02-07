"""Tests for DeviceManager."""

from __future__ import annotations

import subprocess
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestSetRotation:
    """Tests for set_rotation."""

    @pytest.mark.asyncio
    async def test_set_portrait(self) -> None:
        """Should set rotation to portrait."""
        from android_emu_agent.device.manager import DeviceManager, Orientation

        manager = DeviceManager()
        mock_device = MagicMock()

        with patch.object(manager, "get_adb_device", return_value=mock_device):
            await manager.set_rotation("emulator-5554", Orientation.PORTRAIT)

        # Should disable auto-rotate and set rotation
        calls = [str(c) for c in mock_device.shell.call_args_list]
        assert any("accelerometer_rotation" in c and "0" in c for c in calls)
        assert any("user_rotation" in c and "0" in c for c in calls)

    @pytest.mark.asyncio
    async def test_set_landscape(self) -> None:
        """Should set rotation to landscape."""
        from android_emu_agent.device.manager import DeviceManager, Orientation

        manager = DeviceManager()
        mock_device = MagicMock()

        with patch.object(manager, "get_adb_device", return_value=mock_device):
            await manager.set_rotation("emulator-5554", Orientation.LANDSCAPE)

        calls = [str(c) for c in mock_device.shell.call_args_list]
        assert any("user_rotation" in c and "1" in c for c in calls)

    @pytest.mark.asyncio
    async def test_set_auto(self) -> None:
        """Should enable auto-rotate."""
        from android_emu_agent.device.manager import DeviceManager, Orientation

        manager = DeviceManager()
        mock_device = MagicMock()

        with patch.object(manager, "get_adb_device", return_value=mock_device):
            await manager.set_rotation("emulator-5554", Orientation.AUTO)

        calls = [str(c) for c in mock_device.shell.call_args_list]
        assert any("accelerometer_rotation" in c and "1" in c for c in calls)


class TestSetWifi:
    """Tests for set_wifi."""

    @pytest.mark.asyncio
    async def test_enable_wifi(self) -> None:
        """Should enable WiFi."""
        from android_emu_agent.device.manager import DeviceManager

        manager = DeviceManager()
        mock_device = MagicMock()

        with patch.object(manager, "get_adb_device", return_value=mock_device):
            await manager.set_wifi("emulator-5554", enabled=True)

        mock_device.shell.assert_called_once()
        call_arg = mock_device.shell.call_args[0][0]
        assert "svc wifi enable" in call_arg

    @pytest.mark.asyncio
    async def test_disable_wifi(self) -> None:
        """Should disable WiFi."""
        from android_emu_agent.device.manager import DeviceManager

        manager = DeviceManager()
        mock_device = MagicMock()

        with patch.object(manager, "get_adb_device", return_value=mock_device):
            await manager.set_wifi("emulator-5554", enabled=False)

        call_arg = mock_device.shell.call_args[0][0]
        assert "svc wifi disable" in call_arg


class TestSetMobile:
    """Tests for set_mobile."""

    @pytest.mark.asyncio
    async def test_enable_mobile(self) -> None:
        """Should enable mobile data."""
        from android_emu_agent.device.manager import DeviceManager

        manager = DeviceManager()
        mock_device = MagicMock()

        with patch.object(manager, "get_adb_device", return_value=mock_device):
            await manager.set_mobile("emulator-5554", enabled=True)

        call_arg = mock_device.shell.call_args[0][0]
        assert "svc data enable" in call_arg

    @pytest.mark.asyncio
    async def test_disable_mobile(self) -> None:
        """Should disable mobile data."""
        from android_emu_agent.device.manager import DeviceManager

        manager = DeviceManager()
        mock_device = MagicMock()

        with patch.object(manager, "get_adb_device", return_value=mock_device):
            await manager.set_mobile("emulator-5554", enabled=False)

        call_arg = mock_device.shell.call_args[0][0]
        assert "svc data disable" in call_arg


class TestSetDoze:
    """Tests for set_doze."""

    @pytest.mark.asyncio
    async def test_enable_doze(self) -> None:
        """Should force device into doze."""
        from android_emu_agent.device.manager import DeviceManager

        manager = DeviceManager()
        mock_device = MagicMock()

        with patch.object(manager, "get_adb_device", return_value=mock_device):
            await manager.set_doze("emulator-5554", enabled=True)

        call_arg = mock_device.shell.call_args[0][0]
        assert "deviceidle force-idle" in call_arg

    @pytest.mark.asyncio
    async def test_disable_doze(self) -> None:
        """Should exit doze mode."""
        from android_emu_agent.device.manager import DeviceManager

        manager = DeviceManager()
        mock_device = MagicMock()

        with patch.object(manager, "get_adb_device", return_value=mock_device):
            await manager.set_doze("emulator-5554", enabled=False)

        call_arg = mock_device.shell.call_args[0][0]
        assert "deviceidle unforce" in call_arg


class TestAppInstall:
    """Tests for app_install."""

    @pytest.mark.asyncio
    async def test_install_default_flags(self, tmp_path) -> None:
        """Should install APK with replace enabled by default."""
        from android_emu_agent.device.manager import DeviceManager

        manager = DeviceManager()
        mock_device = MagicMock()
        apk = tmp_path / "app-debug.apk"
        apk.write_text("fake-apk", encoding="utf-8")
        run_adb = AsyncMock(
            return_value=subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="Success\n",
                stderr="",
            )
        )

        with (
            patch.object(manager, "get_adb_device", return_value=mock_device),
            patch.object(manager, "_run_adb", run_adb),
        ):
            output = await manager.app_install("emulator-5554", str(apk))

        assert output == "Success"
        run_adb.assert_awaited_once_with("emulator-5554", ["install", "-r", str(apk)])

    @pytest.mark.asyncio
    async def test_install_optional_flags(self, tmp_path) -> None:
        """Should include optional install flags when requested."""
        from android_emu_agent.device.manager import DeviceManager

        manager = DeviceManager()
        mock_device = MagicMock()
        apk = tmp_path / "app-release.apk"
        apk.write_text("fake-apk", encoding="utf-8")
        run_adb = AsyncMock(
            return_value=subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="Success\n",
                stderr="",
            )
        )

        with (
            patch.object(manager, "get_adb_device", return_value=mock_device),
            patch.object(manager, "_run_adb", run_adb),
        ):
            await manager.app_install(
                "emulator-5554",
                str(apk),
                replace=False,
                grant_permissions=True,
                allow_downgrade=True,
            )

        run_adb.assert_awaited_once_with(
            "emulator-5554",
            ["install", "-g", "-d", str(apk)],
        )


class TestAppLaunch:
    """Tests for app_launch."""

    @pytest.mark.asyncio
    async def test_launch_with_activity(self) -> None:
        """Should launch app with explicit activity."""
        from android_emu_agent.device.manager import DeviceManager

        manager = DeviceManager()
        mock_device = MagicMock()
        mock_device.shell.return_value = "Starting: Intent { ... }"

        with patch.object(manager, "get_adb_device", return_value=mock_device):
            result = await manager.app_launch(
                "emulator-5554", "com.example.app", activity=".MainActivity"
            )

        call_arg = mock_device.shell.call_args[0][0]
        assert "am start" in call_arg
        assert "com.example.app/.MainActivity" in call_arg
        assert result == ".MainActivity"

    @pytest.mark.asyncio
    async def test_launch_wait_for_debugger(self) -> None:
        """Should add -D when debugger wait is requested."""
        from android_emu_agent.device.manager import DeviceManager

        manager = DeviceManager()
        mock_device = MagicMock()
        mock_device.shell.return_value = "Starting: Intent { ... }"

        with patch.object(manager, "get_adb_device", return_value=mock_device):
            await manager.app_launch(
                "emulator-5554",
                "com.example.app",
                activity=".MainActivity",
                wait_for_debugger=True,
            )

        call_arg = mock_device.shell.call_args[0][0]
        assert "am start -D -n" in call_arg

    @pytest.mark.asyncio
    async def test_launch_resolve_activity(self) -> None:
        """Should resolve launcher activity when not specified."""
        from android_emu_agent.device.manager import DeviceManager

        manager = DeviceManager()
        mock_device = MagicMock()
        # First call: resolve activity, second call: launch
        mock_device.shell.side_effect = [
            "priority=0 preferredOrder=0\ncom.example.app/.LauncherActivity",
            "Starting: Intent { ... }",
        ]

        with patch.object(manager, "get_adb_device", return_value=mock_device):
            result = await manager.app_launch("emulator-5554", "com.example.app")

        assert result == ".LauncherActivity"


class TestAppForceStop:
    """Tests for app_force_stop."""

    @pytest.mark.asyncio
    async def test_force_stop(self) -> None:
        """Should force stop app."""
        from android_emu_agent.device.manager import DeviceManager

        manager = DeviceManager()
        mock_device = MagicMock()

        with patch.object(manager, "get_adb_device", return_value=mock_device):
            await manager.app_force_stop("emulator-5554", "com.example.app")

        call_arg = mock_device.shell.call_args[0][0]
        assert "am force-stop" in call_arg
        assert "com.example.app" in call_arg


class TestAppDeeplink:
    """Tests for app_deeplink."""

    @pytest.mark.asyncio
    async def test_deeplink_custom_scheme(self) -> None:
        """Should open custom scheme deeplink."""
        from android_emu_agent.device.manager import DeviceManager

        manager = DeviceManager()
        mock_device = MagicMock()
        mock_device.shell.return_value = "Starting: Intent { act=android.intent.action.VIEW ... }"

        with patch.object(manager, "get_adb_device", return_value=mock_device):
            await manager.app_deeplink("emulator-5554", "myapp://deep/link")

        call_arg = mock_device.shell.call_args[0][0]
        assert "am start" in call_arg
        assert "android.intent.action.VIEW" in call_arg
        assert "myapp://deep/link" in call_arg

    @pytest.mark.asyncio
    async def test_deeplink_https(self) -> None:
        """Should open https deeplink."""
        from android_emu_agent.device.manager import DeviceManager

        manager = DeviceManager()
        mock_device = MagicMock()
        mock_device.shell.return_value = "Starting: Intent { ... }"

        with patch.object(manager, "get_adb_device", return_value=mock_device):
            await manager.app_deeplink("emulator-5554", "https://example.com/path")

        call_arg = mock_device.shell.call_args[0][0]
        assert "https://example.com/path" in call_arg

    @pytest.mark.asyncio
    async def test_deeplink_wait_for_debugger(self) -> None:
        """Should include debugger wait flag for deeplink launch."""
        from android_emu_agent.device.manager import DeviceManager

        manager = DeviceManager()
        mock_device = MagicMock()
        mock_device.shell.return_value = "Starting: Intent { ... }"

        with patch.object(manager, "get_adb_device", return_value=mock_device):
            await manager.app_deeplink(
                "emulator-5554",
                "https://example.com/path",
                wait_for_debugger=True,
            )

        call_arg = mock_device.shell.call_args[0][0]
        assert "am start -D" in call_arg


class TestAppIntent:
    """Tests for app_start_intent."""

    @pytest.mark.asyncio
    async def test_start_intent_with_component_and_action(self) -> None:
        """Should start explicit intent command."""
        from android_emu_agent.device.manager import DeviceManager

        manager = DeviceManager()
        mock_device = MagicMock()
        mock_device.shell.return_value = "Starting: Intent { ... }"

        with patch.object(manager, "get_adb_device", return_value=mock_device):
            await manager.app_start_intent(
                "emulator-5554",
                action="android.intent.action.MAIN",
                component="com.example.app/.MainActivity",
                package="com.example.app",
            )

        call_arg = mock_device.shell.call_args[0][0]
        assert "android.intent.action.MAIN" in call_arg
        assert "com.example.app/.MainActivity" in call_arg
        assert call_arg.endswith("com.example.app")


class TestListPackages:
    """Tests for list_packages."""

    @pytest.mark.asyncio
    async def test_list_packages_all(self) -> None:
        """Should list all packages."""
        from android_emu_agent.device.manager import DeviceManager

        manager = DeviceManager()
        mock_device = MagicMock()
        mock_device.shell.return_value = "package:com.example\npackage:com.sample\n"

        with patch.object(manager, "get_adb_device", return_value=mock_device):
            packages = await manager.list_packages("emulator-5554", scope="all")

        assert packages == ["com.example", "com.sample"]
        call_arg = mock_device.shell.call_args[0][0]
        assert call_arg == "pm list packages"

    @pytest.mark.asyncio
    async def test_list_packages_system(self) -> None:
        """Should list system packages."""
        from android_emu_agent.device.manager import DeviceManager

        manager = DeviceManager()
        mock_device = MagicMock()
        mock_device.shell.return_value = ""

        with patch.object(manager, "get_adb_device", return_value=mock_device):
            await manager.list_packages("emulator-5554", scope="system")

        call_arg = mock_device.shell.call_args[0][0]
        assert call_arg == "pm list packages -s"

    @pytest.mark.asyncio
    async def test_list_packages_third_party(self) -> None:
        """Should list third-party packages."""
        from android_emu_agent.device.manager import DeviceManager

        manager = DeviceManager()
        mock_device = MagicMock()
        mock_device.shell.return_value = ""

        with patch.object(manager, "get_adb_device", return_value=mock_device):
            await manager.list_packages("emulator-5554", scope="third-party")

        call_arg = mock_device.shell.call_args[0][0]
        assert call_arg == "pm list packages -3"


class TestEmulatorSnapshot:
    """Tests for emulator snapshot methods."""

    @pytest.mark.asyncio
    async def test_snapshot_save(self) -> None:
        """Should save emulator snapshot."""
        from android_emu_agent.device.manager import DeviceManager

        manager = DeviceManager()

        with patch("asyncio.open_connection") as mock_conn:
            mock_reader = AsyncMock()
            mock_writer = MagicMock()
            mock_writer.drain = AsyncMock()
            mock_writer.wait_closed = AsyncMock()
            # Simulate console responses
            mock_reader.read.side_effect = [
                b"Android Console: type 'help' for a list of commands\r\nOK\r\n",
                b"OK\r\n",
            ]
            mock_conn.return_value = (mock_reader, mock_writer)

            await manager.emulator_snapshot_save("emulator-5554", "baseline")

            # Verify command was sent
            write_calls = [str(c) for c in mock_writer.write.call_args_list]
            assert any("avd snapshot save baseline" in c for c in write_calls)

    @pytest.mark.asyncio
    async def test_snapshot_restore(self) -> None:
        """Should restore emulator snapshot."""
        from android_emu_agent.device.manager import DeviceManager

        manager = DeviceManager()

        with patch("asyncio.open_connection") as mock_conn:
            mock_reader = AsyncMock()
            mock_writer = MagicMock()
            mock_writer.drain = AsyncMock()
            mock_writer.wait_closed = AsyncMock()
            mock_reader.read.side_effect = [
                b"Android Console: type 'help' for a list of commands\r\nOK\r\n",
                b"OK\r\n",
            ]
            mock_conn.return_value = (mock_reader, mock_writer)

            await manager.emulator_snapshot_restore("emulator-5554", "baseline")

            write_calls = [str(c) for c in mock_writer.write.call_args_list]
            assert any("avd snapshot load baseline" in c for c in write_calls)

    @pytest.mark.asyncio
    async def test_snapshot_not_emulator(self) -> None:
        """Should reject non-emulator serial."""
        from android_emu_agent.device.manager import DeviceManager
        from android_emu_agent.errors import AgentError

        manager = DeviceManager()

        with pytest.raises(AgentError) as exc_info:
            await manager.emulator_snapshot_save("device-123", "baseline")

        assert exc_info.value.code == "ERR_NOT_EMULATOR"


class TestEvictDevice:
    """Tests for evict_device."""

    @pytest.mark.asyncio
    async def test_evict_clears_connections(self) -> None:
        """Should clear cached adb and u2 connections."""
        from android_emu_agent.device.manager import DeviceManager

        manager = DeviceManager()
        # Simulate cached connections
        manager._adb_devices["emulator-5554"] = MagicMock()
        manager._u2_devices["emulator-5554"] = MagicMock()

        await manager.evict_device("emulator-5554")

        assert "emulator-5554" not in manager._adb_devices
        assert "emulator-5554" not in manager._u2_devices

    @pytest.mark.asyncio
    async def test_evict_preserves_device_info(self) -> None:
        """Should preserve device info dict."""
        from android_emu_agent.device.manager import DeviceInfo, DeviceManager

        manager = DeviceManager()
        info = DeviceInfo(
            serial="emulator-5554",
            model="sdk_phone",
            sdk_version=30,
            is_rooted=False,
            is_emulator=True,
        )
        manager._devices["emulator-5554"] = info
        manager._adb_devices["emulator-5554"] = MagicMock()

        await manager.evict_device("emulator-5554")

        assert "emulator-5554" in manager._devices
        assert manager._devices["emulator-5554"] == info

    @pytest.mark.asyncio
    async def test_evict_nonexistent_device(self) -> None:
        """Should handle evicting device with no cached connections."""
        from android_emu_agent.device.manager import DeviceManager

        manager = DeviceManager()
        # Should not raise
        await manager.evict_device("nonexistent-device")


class TestAppCurrent:
    """Tests for app_current."""

    @pytest.mark.asyncio
    async def test_app_current_parses_component(self) -> None:
        """Should parse foreground package/activity from dumpsys line."""
        from android_emu_agent.device.manager import DeviceManager

        manager = DeviceManager()
        mock_device = MagicMock()
        mock_device.shell.side_effect = [
            "mResumedActivity: ActivityRecord{123 u0 com.example.app/.MainActivity t77}",
            "",
        ]

        with patch.object(manager, "get_adb_device", return_value=mock_device):
            result = await manager.app_current("emulator-5554")

        assert result["package"] == "com.example.app"
        assert result["activity"] == ".MainActivity"
        assert result["component"] == "com.example.app/.MainActivity"


class TestAppTaskStack:
    """Tests for app_task_stack."""

    @pytest.mark.asyncio
    async def test_app_task_stack_runs_cmd_activity_tasks(self) -> None:
        """Should query task stack using cmd activity tasks."""
        from android_emu_agent.device.manager import DeviceManager

        manager = DeviceManager()
        mock_device = MagicMock()
        mock_device.shell.return_value = "TASK 77: com.example.app/.MainActivity"

        with patch.object(manager, "get_adb_device", return_value=mock_device):
            output = await manager.app_task_stack("emulator-5554")

        assert "TASK 77" in output
        call_arg = mock_device.shell.call_args[0][0]
        assert call_arg == "cmd activity tasks"


class TestAppResolveIntent:
    """Tests for app_resolve_intent."""

    @pytest.mark.asyncio
    async def test_app_resolve_intent_parses_component(self) -> None:
        """Should parse resolved component from resolve-activity output."""
        from android_emu_agent.device.manager import DeviceManager

        manager = DeviceManager()
        mock_device = MagicMock()
        mock_device.shell.return_value = (
            "priority=0 preferredOrder=0 match=0x108000 specificIndex=-1 isDefault=true\n"
            "com.example.app/.DeepLinkActivity"
        )

        with patch.object(manager, "get_adb_device", return_value=mock_device):
            result = await manager.app_resolve_intent(
                "emulator-5554",
                action="android.intent.action.VIEW",
                data_uri="https://example.com/item",
                package="com.example.app",
            )

        assert result.component == "com.example.app/.DeepLinkActivity"
        call_arg = mock_device.shell.call_args[0][0]
        assert "cmd package resolve-activity --brief" in call_arg
        assert "android.intent.action.VIEW" in call_arg
        assert "https://example.com/item" in call_arg

    @pytest.mark.asyncio
    async def test_app_resolve_intent_handles_not_found(self) -> None:
        """Should keep resolved component empty when nothing matches."""
        from android_emu_agent.device.manager import DeviceManager

        manager = DeviceManager()
        mock_device = MagicMock()
        mock_device.shell.return_value = "No activity found"

        with patch.object(manager, "get_adb_device", return_value=mock_device):
            result = await manager.app_resolve_intent(
                "emulator-5554",
                action="android.intent.action.VIEW",
            )

        assert result.component is None
