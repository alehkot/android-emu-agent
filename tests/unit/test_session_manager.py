"""Tests for atomic session persistence and lifecycle state."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock

import pytest

from android_emu_agent.device.session import Session, SessionManager


@pytest.mark.asyncio
async def test_create_session_is_not_published_when_database_save_fails() -> None:
    """A failed insert must not leave an in-memory ghost session."""
    database = AsyncMock()
    database.save_session.side_effect = OSError("database is read-only")
    manager = SessionManager(database)

    with pytest.raises(OSError, match="read-only"):
        await manager.create_session("emulator-5554")

    assert await manager.list_sessions() == []
    assert manager._snapshot_locks == {}


@pytest.mark.asyncio
async def test_close_session_remains_retryable_when_database_delete_fails() -> None:
    """A failed delete must preserve the live session and its snapshot lock."""
    database = AsyncMock()
    database.delete_session.side_effect = OSError("database is busy")
    manager = SessionManager(database)
    session = Session(session_id="s-test", device_serial="emulator-5554")
    snapshot_lock = asyncio.Lock()
    manager._sessions[session.session_id] = session
    manager._snapshot_locks[session.session_id] = snapshot_lock

    with pytest.raises(OSError, match="database is busy"):
        await manager.close_session(session.session_id)

    assert await manager.get_session(session.session_id) is session
    assert manager._snapshot_locks[session.session_id] is snapshot_lock


@pytest.mark.asyncio
async def test_close_session_waits_for_in_flight_snapshot() -> None:
    """Session deletion must not race a snapshot generation commit."""
    database = AsyncMock()
    manager = SessionManager(database)
    session = Session(session_id="s-test", device_serial="emulator-5554")
    manager._sessions[session.session_id] = session
    snapshot_lock = asyncio.Lock()
    manager._snapshot_locks[session.session_id] = snapshot_lock

    await snapshot_lock.acquire()
    close_task = asyncio.create_task(manager.close_session(session.session_id))
    await asyncio.sleep(0)

    database.delete_session.assert_not_awaited()
    assert await manager.get_session(session.session_id) is session

    snapshot_lock.release()
    assert await close_task is True
    database.delete_session.assert_awaited_once_with(session.session_id)
    assert await manager.get_session(session.session_id) is None


def _row(session_id: str, *, last_activity: str, created_at: str | None = None) -> dict[str, Any]:
    stamp = created_at or last_activity
    return {
        "session_id": session_id,
        "device_serial": "emulator-5554",
        "created_at": stamp,
        "last_activity": last_activity,
        "generation": 3,
    }


@pytest.mark.asyncio
async def test_start_prunes_sessions_idle_past_retention() -> None:
    """Sessions never explicitly stopped must not accumulate across restarts."""
    stale = (datetime.now() - timedelta(days=30)).isoformat()
    fresh = (datetime.now() - timedelta(hours=1)).isoformat()
    database = AsyncMock()
    database.list_sessions.return_value = [
        _row("s-stale", last_activity=stale),
        _row("s-fresh", last_activity=fresh),
    ]
    manager = SessionManager(database, max_idle_days=7)

    await manager.start()

    assert [s.session_id for s in await manager.list_sessions()] == ["s-fresh"]
    database.delete_session.assert_awaited_once_with("s-stale")


@pytest.mark.asyncio
async def test_start_keeps_sessions_within_retention() -> None:
    """A recently active session must survive a daemon restart."""
    recent = (datetime.now() - timedelta(days=2)).isoformat()
    database = AsyncMock()
    database.list_sessions.return_value = [_row("s-recent", last_activity=recent)]
    manager = SessionManager(database, max_idle_days=7)

    await manager.start()

    assert [s.session_id for s in await manager.list_sessions()] == ["s-recent"]
    database.delete_session.assert_not_awaited()
    assert manager._snapshot_locks.keys() == {"s-recent"}


@pytest.mark.asyncio
async def test_start_keeps_session_with_unparseable_activity() -> None:
    """A corrupt timestamp must not be treated as grounds for deletion."""
    database = AsyncMock()
    database.list_sessions.return_value = [
        {
            "session_id": "s-odd",
            "device_serial": "emulator-5554",
            "created_at": datetime.now().isoformat(),
            "last_activity": "not-a-timestamp",
            "generation": 0,
        }
    ]
    manager = SessionManager(database, max_idle_days=7)

    await manager.start()

    assert [s.session_id for s in await manager.list_sessions()] == ["s-odd"]
    database.delete_session.assert_not_awaited()
