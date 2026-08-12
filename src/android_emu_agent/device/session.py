"""Session manager - session lifecycle and state persistence."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

import structlog

from android_emu_agent.db.models import Database

if TYPE_CHECKING:
    pass

logger = structlog.get_logger()

# Sessions persist across daemon restarts, so an agent that never calls `session stop`
# would otherwise accumulate rows (and their ref maps) indefinitely.
DEFAULT_SESSION_MAX_IDLE_DAYS = 7


@dataclass
class Session:
    """Represents an active session with a device."""

    session_id: str
    device_serial: str
    created_at: datetime = field(default_factory=datetime.now)
    generation: int = 0  # Snapshot generation counter
    last_snapshot: dict[str, Any] | None = None
    last_snapshot_json: str | None = None


class SessionManager:
    """Manages session lifecycle and persistence."""

    def __init__(
        self,
        database: Database,
        *,
        max_idle_days: int = DEFAULT_SESSION_MAX_IDLE_DAYS,
    ) -> None:
        self._sessions: dict[str, Session] = {}
        self._snapshot_locks: dict[str, asyncio.Lock] = {}
        self._db = database
        self._max_idle_days = max_idle_days
        self._lifecycle_lock = asyncio.Lock()

    async def start(self) -> None:
        """Start session manager and restore persisted sessions."""
        logger.info("session_manager_starting")
        sessions = await self._db.list_sessions()
        cutoff = datetime.now() - timedelta(days=self._max_idle_days)
        pruned = 0
        for row in sessions:
            created_at = datetime.fromisoformat(row["created_at"])
            # Sessions that are never explicitly stopped otherwise persist forever and
            # are restored on every start, along with their ref rows.
            if self._is_expired(row, cutoff):
                await self._db.delete_session(row["session_id"])
                pruned += 1
                continue
            session = Session(
                session_id=row["session_id"],
                device_serial=row["device_serial"],
                created_at=created_at,
                generation=row.get("generation", 0),
            )
            self._sessions[session.session_id] = session
            self._snapshot_locks[session.session_id] = asyncio.Lock()
        logger.info("session_manager_started", restored=len(self._sessions), pruned=pruned)

    def _is_expired(self, row: dict[str, Any], cutoff: datetime) -> bool:
        """Return whether a persisted session has been idle past the retention window."""
        raw = row.get("last_activity") or row.get("created_at")
        if not raw:
            return False
        try:
            return datetime.fromisoformat(str(raw)) < cutoff
        except ValueError:
            # An unparseable timestamp is not grounds for deleting a session.
            logger.warning("session_activity_unparseable", session_id=row.get("session_id"))
            return False

    async def stop(self) -> None:
        """Stop session manager and cleanup."""
        logger.info("session_manager_stopping")
        for session in self._sessions.values():
            await self._db.save_session(
                session.session_id,
                session.device_serial,
                generation=session.generation,
            )
        self._sessions.clear()
        self._snapshot_locks.clear()
        logger.info("session_manager_stopped")

    async def create_session(self, device_serial: str) -> Session:
        """Create a new session for a device."""
        async with self._lifecycle_lock:
            session_id = f"s-{uuid.uuid4().hex[:8]}"
            session = Session(session_id=session_id, device_serial=device_serial)
            await self._db.save_session(session_id, device_serial, generation=session.generation)
            self._sessions[session_id] = session
            self._snapshot_locks[session_id] = asyncio.Lock()
        logger.info("session_created", session_id=session_id, device=device_serial)
        return session

    async def get_session(self, session_id: str) -> Session | None:
        """Get session by ID."""
        return self._sessions.get(session_id)

    async def list_sessions(self) -> list[Session]:
        """List active sessions."""
        return list(self._sessions.values())

    async def close_session(self, session_id: str) -> bool:
        """Close and remove a session."""
        async with self._lifecycle_lock:
            if session_id not in self._sessions:
                return False
            snapshot_lock = self._snapshot_locks.setdefault(session_id, asyncio.Lock())
            async with snapshot_lock:
                await self._db.delete_session(session_id)
                del self._sessions[session_id]
                self._snapshot_locks.pop(session_id, None)
            logger.info("session_closed", session_id=session_id)
            return True

    async def increment_generation(self, session_id: str) -> int:
        """Increment and return the new snapshot generation."""
        session = self._sessions.get(session_id)
        if session:
            next_generation = session.generation + 1
            await self._db.save_session(
                session.session_id,
                session.device_serial,
                generation=next_generation,
            )
            session.generation = next_generation
            return next_generation
        raise ValueError(f"Session not found: {session_id}")

    def snapshot_lock(self, session_id: str) -> asyncio.Lock:
        """Return the lock that serializes ref-generating snapshots for a session."""
        if session_id not in self._sessions:
            raise ValueError(f"Session not found: {session_id}")
        return self._snapshot_locks.setdefault(session_id, asyncio.Lock())

    async def update_snapshot(
        self,
        session_id: str,
        snapshot: dict[str, Any],
        snapshot_json: str,
    ) -> None:
        """Store last snapshot in memory for artifacts/debugging."""
        session = self._sessions.get(session_id)
        if session:
            session.last_snapshot = snapshot
            session.last_snapshot_json = snapshot_json

    async def get_last_snapshot(self, session_id: str) -> dict[str, Any] | None:
        """Get the last snapshot for a session."""
        session = self._sessions.get(session_id)
        if session:
            return session.last_snapshot
        return None

    async def get_last_snapshot_json(self, session_id: str) -> str | None:
        """Get the last snapshot JSON for a session."""
        session = self._sessions.get(session_id)
        if session:
            return session.last_snapshot_json
        return None
