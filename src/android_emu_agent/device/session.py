"""Session manager - session lifecycle and state persistence."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

import structlog

from android_emu_agent.db.models import Database

if TYPE_CHECKING:
    pass

logger = structlog.get_logger()


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

    def __init__(self, database: Database) -> None:
        self._sessions: dict[str, Session] = {}
        self._db = database

    async def start(self) -> None:
        """Start session manager and restore persisted sessions."""
        logger.info("session_manager_starting")
        sessions = await self._db.list_sessions()
        for row in sessions:
            created_at = datetime.fromisoformat(row["created_at"])
            session = Session(
                session_id=row["session_id"],
                device_serial=row["device_serial"],
                created_at=created_at,
                generation=row.get("generation", 0),
            )
            self._sessions[session.session_id] = session
        logger.info("session_manager_started")

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
        logger.info("session_manager_stopped")

    async def create_session(self, device_serial: str) -> Session:
        """Create a new session for a device."""
        session_id = f"s-{uuid.uuid4().hex[:8]}"
        session = Session(session_id=session_id, device_serial=device_serial)
        self._sessions[session_id] = session
        await self._db.save_session(session_id, device_serial, generation=session.generation)
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
        if session_id in self._sessions:
            del self._sessions[session_id]
            await self._db.delete_session(session_id)
            logger.info("session_closed", session_id=session_id)
            return True
        return False

    async def increment_generation(self, session_id: str) -> int:
        """Increment and return the new snapshot generation."""
        session = self._sessions.get(session_id)
        if session:
            session.generation += 1
            await self._db.save_session(
                session.session_id,
                session.device_serial,
                generation=session.generation,
            )
            return session.generation
        raise ValueError(f"Session not found: {session_id}")

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
