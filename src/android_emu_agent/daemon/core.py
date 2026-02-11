"""Daemon core - lifecycle, request routing, state management."""

import structlog

from android_emu_agent.actions.executor import ActionExecutor
from android_emu_agent.actions.wait import WaitEngine
from android_emu_agent.artifacts.manager import ArtifactManager
from android_emu_agent.daemon.health import HealthMonitor
from android_emu_agent.db.models import Database
from android_emu_agent.debugger.manager import DebugManager
from android_emu_agent.device.manager import DeviceManager
from android_emu_agent.device.session import SessionManager
from android_emu_agent.files.manager import FileManager
from android_emu_agent.reliability.manager import ReliabilityManager
from android_emu_agent.ui.context import ContextResolver
from android_emu_agent.ui.ref_resolver import RefResolver
from android_emu_agent.ui.snapshotter import UISnapshotter

logger = structlog.get_logger()


class DaemonCore:
    """Central daemon coordinator managing all subsystems."""

    def __init__(self) -> None:
        self.database = Database()
        self.device_manager = DeviceManager()
        self.session_manager = SessionManager(self.database)
        self.snapshotter = UISnapshotter()
        self.ref_resolver = RefResolver()
        self.action_executor = ActionExecutor()
        self.wait_engine = WaitEngine()
        self.artifact_manager = ArtifactManager()
        self.file_manager = FileManager()
        self.reliability_manager = ReliabilityManager()
        self.debug_manager = DebugManager()
        self.context_resolver = ContextResolver()
        self.health_monitor = HealthMonitor(self.device_manager, self.session_manager)
        self._running = False

    async def start(self) -> None:
        """Initialize all subsystems."""
        logger.info("daemon_core_starting")
        await self.database.connect()
        await self.device_manager.start()
        await self.session_manager.start()
        await self.health_monitor.start()
        self._running = True
        logger.info("daemon_core_started")

    async def stop(self) -> None:
        """Gracefully shutdown all subsystems."""
        logger.info("daemon_core_stopping")
        self._running = False
        await self.debug_manager.stop_all()
        await self.health_monitor.stop()
        await self.session_manager.stop()
        await self.device_manager.stop()
        await self.database.disconnect()
        logger.info("daemon_core_stopped")

    @property
    def is_running(self) -> bool:
        """Check if daemon is running."""
        return self._running
