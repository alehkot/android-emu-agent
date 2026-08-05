"""Tests for UI snapshot generation commit behavior."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import Response

from android_emu_agent.daemon.models import SnapshotRequest
from android_emu_agent.device.session import Session, SessionManager
from android_emu_agent.ui.context import UIContext
from android_emu_agent.ui.ref_resolver import RefResolver
from android_emu_agent.ui.snapshotter import UISnapshotter


@dataclass
class SnapshotHarness:
    core: SimpleNamespace
    session: Session
    database: AsyncMock
    u2_device: MagicMock


def _snapshot_harness() -> SnapshotHarness:
    database = AsyncMock()
    session_manager = SessionManager(database)
    session = Session(
        session_id="s-test",
        device_serial="emulator-5554",
        generation=4,
    )
    session_manager._sessions[session.session_id] = session

    u2_device = MagicMock()
    u2_device.dump_hierarchy.return_value = (
        '<hierarchy><node class="android.widget.Button" clickable="true" '
        'bounds="[0,0][100,100]" /></hierarchy>'
    )
    adb_device = MagicMock()
    device_manager = AsyncMock()
    device_manager.get_u2_device.return_value = u2_device
    device_manager.get_adb_device.return_value = adb_device
    device_manager.describe_device.return_value = {"serial": "emulator-5554"}

    context_resolver = AsyncMock()
    context_resolver.resolve.return_value = UIContext(
        package="com.example.app",
        activity=".MainActivity",
        top_resumed_activity="com.example.app/.MainActivity",
        top_window="window",
        orientation="PORTRAIT",
        window_focused=True,
        ime_visible=False,
        ime_package=None,
        system_dialogs=[],
    )

    core = SimpleNamespace(
        session_manager=session_manager,
        device_manager=device_manager,
        context_resolver=context_resolver,
        snapshotter=UISnapshotter(),
        database=database,
        ref_resolver=RefResolver(),
    )
    return SnapshotHarness(core, session, database, u2_device)


@pytest.mark.asyncio
async def test_raw_snapshot_does_not_advance_generation() -> None:
    """Raw XML has no refs and should leave the current generation untouched."""
    from android_emu_agent.daemon import server

    harness = _snapshot_harness()
    server.app.state.core = harness.core

    response = await server.ui_snapshot(SnapshotRequest(session_id="s-test", mode="raw"))

    assert isinstance(response, Response)
    assert response.media_type == "application/xml"
    assert harness.session.generation == 4
    harness.database.save_refs.assert_not_awaited()
    harness.database.save_session.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_snapshot_does_not_advance_generation() -> None:
    """Hierarchy capture failures should not consume a ref generation."""
    from android_emu_agent.daemon import server

    harness = _snapshot_harness()
    harness.u2_device.dump_hierarchy.side_effect = RuntimeError("uiautomator unavailable")
    server.app.state.core = harness.core

    response = await server.ui_snapshot(SnapshotRequest(session_id="s-test"))

    assert isinstance(response, Response)
    assert response.status_code == 500
    assert harness.session.generation == 4
    harness.database.save_refs.assert_not_awaited()
    harness.database.save_session.assert_not_awaited()


@pytest.mark.asyncio
async def test_persistence_failure_does_not_advance_generation() -> None:
    """A snapshot becomes current only after its ref data persists successfully."""
    from android_emu_agent.daemon import server

    harness = _snapshot_harness()
    harness.database.save_refs.side_effect = OSError("disk full")
    server.app.state.core = harness.core

    response = await server.ui_snapshot(SnapshotRequest(session_id="s-test"))

    assert isinstance(response, Response)
    assert response.status_code == 500
    assert harness.session.generation == 4
    harness.database.save_session.assert_not_awaited()


@pytest.mark.asyncio
async def test_structured_snapshot_commits_one_generation() -> None:
    """A successful ref-producing snapshot should commit its provisional generation."""
    from android_emu_agent.daemon import server

    harness = _snapshot_harness()
    server.app.state.core = harness.core

    response = await server.ui_snapshot(SnapshotRequest(session_id="s-test"))

    assert isinstance(response, dict)
    assert response["generation"] == 5
    assert response["elements"][0]["ref"] == "^g5a1"
    assert harness.session.generation == 5
    harness.database.save_refs.assert_awaited_once()
    harness.database.cleanup_old_refs.assert_awaited_once_with("s-test", 5)
    harness.database.save_session.assert_awaited_once_with(
        "s-test",
        "emulator-5554",
        generation=5,
    )


@pytest.mark.asyncio
async def test_concurrent_structured_snapshots_get_distinct_generations() -> None:
    """Per-session serialization should prevent duplicate provisional generations."""
    from android_emu_agent.daemon import server

    harness = _snapshot_harness()
    server.app.state.core = harness.core
    request = SnapshotRequest(session_id="s-test")

    responses = await asyncio.gather(
        server.ui_snapshot(request),
        server.ui_snapshot(request),
    )

    assert all(isinstance(response, dict) for response in responses)
    assert sorted(response["generation"] for response in responses if isinstance(response, dict)) == [
        5,
        6,
    ]
    assert harness.session.generation == 6


@pytest.mark.asyncio
async def test_generation_stays_current_when_session_persistence_fails() -> None:
    """In-memory generation must not get ahead of durable session state."""
    database = AsyncMock()
    database.save_session.side_effect = OSError("disk full")
    manager = SessionManager(database)
    session = Session("s-test", "emulator-5554", generation=4)
    manager._sessions[session.session_id] = session

    with pytest.raises(OSError, match="disk full"):
        await manager.increment_generation("s-test")

    assert session.generation == 4
