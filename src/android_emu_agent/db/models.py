"""Database models and connection management."""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import aiosqlite
import structlog

if TYPE_CHECKING:
    pass

logger = structlog.get_logger()

DEFAULT_DB_PATH = Path.home() / ".android-emu-agent" / "state.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    device_serial TEXT NOT NULL,
    created_at TEXT NOT NULL,
    last_activity TEXT NOT NULL,
    generation INTEGER DEFAULT 0,
    metadata TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS ref_maps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    generation INTEGER NOT NULL,
    ref TEXT NOT NULL,
    locator_bundle TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(session_id, generation, ref)
);

CREATE INDEX IF NOT EXISTS idx_sessions_device ON sessions(device_serial);
CREATE INDEX IF NOT EXISTS idx_refs_session_gen ON ref_maps(session_id, generation);
"""


class Database:
    """Async SQLite database manager."""

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        """Connect to database and initialize schema."""
        self._connection = await aiosqlite.connect(self.db_path)
        await self._connection.executescript(SCHEMA)
        await self._connection.commit()
        logger.info("database_connected", path=str(self.db_path))

    async def disconnect(self) -> None:
        """Close database connection."""
        if self._connection:
            await self._connection.close()
            self._connection = None
            logger.info("database_disconnected")

    @asynccontextmanager
    async def transaction(self) -> AsyncGenerator[aiosqlite.Connection, None]:
        """Context manager for database transactions."""
        if not self._connection:
            raise RuntimeError("Database not connected")
        try:
            yield self._connection
            await self._connection.commit()
        except Exception:
            await self._connection.rollback()
            raise

    # Session operations

    async def save_session(
        self,
        session_id: str,
        device_serial: str,
        generation: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Save or update a session."""
        now = datetime.now().isoformat()
        async with self.transaction() as conn:
            await conn.execute(
                """
                INSERT INTO sessions (session_id, device_serial, created_at, last_activity, generation, metadata)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    last_activity = excluded.last_activity,
                    generation = excluded.generation,
                    metadata = excluded.metadata
                """,
                (session_id, device_serial, now, now, generation, json.dumps(metadata or {})),
            )

    async def get_session(self, session_id: str) -> dict[str, Any] | None:
        """Get session by ID."""
        if not self._connection:
            return None
        cursor = await self._connection.execute(
            "SELECT * FROM sessions WHERE session_id = ?",
            (session_id,),
        )
        row = await cursor.fetchone()
        if row:
            return {
                "session_id": row[0],
                "device_serial": row[1],
                "created_at": row[2],
                "last_activity": row[3],
                "generation": row[4],
                "metadata": json.loads(row[5]),
            }
        return None

    async def list_sessions(self) -> list[dict[str, Any]]:
        """List all sessions."""
        if not self._connection:
            return []
        cursor = await self._connection.execute(
            "SELECT * FROM sessions ORDER BY last_activity DESC"
        )
        rows = await cursor.fetchall()
        return [
            {
                "session_id": row[0],
                "device_serial": row[1],
                "created_at": row[2],
                "last_activity": row[3],
                "generation": row[4],
            }
            for row in rows
        ]

    async def delete_session(self, session_id: str) -> None:
        """Delete a session and its refs."""
        async with self.transaction() as conn:
            await conn.execute("DELETE FROM ref_maps WHERE session_id = ?", (session_id,))
            await conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))

    # Ref operations

    async def save_refs(
        self,
        session_id: str,
        generation: int,
        refs: list[dict[str, Any]],
    ) -> None:
        """Save refs for a snapshot generation."""
        now = datetime.now().isoformat()
        async with self.transaction() as conn:
            await conn.executemany(
                """
                INSERT INTO ref_maps (session_id, generation, ref, locator_bundle, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(session_id, generation, ref) DO UPDATE SET
                    locator_bundle = excluded.locator_bundle
                """,
                [(session_id, generation, r["ref"], json.dumps(r), now) for r in refs],
            )

    async def get_ref(
        self,
        session_id: str,
        generation: int,
        ref: str,
    ) -> dict[str, Any] | None:
        """Get a specific ref from a generation."""
        if not self._connection:
            return None
        cursor = await self._connection.execute(
            "SELECT locator_bundle FROM ref_maps WHERE session_id = ? AND generation = ? AND ref = ?",
            (session_id, generation, ref),
        )
        row = await cursor.fetchone()
        if row:
            return cast(dict[str, Any], json.loads(row[0]))
        return None

    async def get_ref_any_generation(
        self,
        session_id: str,
        ref: str,
    ) -> tuple[int, dict[str, Any]] | None:
        """Get the most recent ref across generations."""
        if not self._connection:
            return None
        cursor = await self._connection.execute(
            """
            SELECT generation, locator_bundle
            FROM ref_maps
            WHERE session_id = ? AND ref = ?
            ORDER BY generation DESC
            LIMIT 1
            """,
            (session_id, ref),
        )
        row = await cursor.fetchone()
        if row:
            return row[0], cast(dict[str, Any], json.loads(row[1]))
        return None

    async def cleanup_old_refs(self, session_id: str, keep_generations: int = 3) -> None:
        """Remove refs older than keep_generations."""
        if not self._connection:
            return
        async with self.transaction() as conn:
            # Get current max generation
            cursor = await conn.execute(
                "SELECT MAX(generation) FROM ref_maps WHERE session_id = ?",
                (session_id,),
            )
            row = await cursor.fetchone()
            if row and row[0]:
                max_gen = row[0]
                cutoff = max_gen - keep_generations
                await conn.execute(
                    "DELETE FROM ref_maps WHERE session_id = ? AND generation < ?",
                    (session_id, cutoff),
                )
