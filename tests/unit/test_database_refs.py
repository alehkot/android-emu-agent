"""Tests for persisted generation-scoped ref lookup."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from android_emu_agent.db.models import Database


@pytest.mark.asyncio
async def test_persisted_legacy_ref_collision_fails_closed(tmp_path: Path) -> None:
    """SQLite fallback should not pick the newest reuse of a legacy token."""
    database = Database(tmp_path / "state" / "state.db")
    await database.connect()
    try:
        await database.save_refs("s-1", 1, [{"ref": "^a1", "text": "Increment"}])
        await database.save_refs("s-1", 2, [{"ref": "^a1", "text": "Confirm"}])

        assert await database.get_ref_any_generation("s-1", "^a1") is None

        await database.save_refs("s-1", 3, [{"ref": "^g3a1", "text": "Continue"}])
        qualified = await database.get_ref_any_generation("s-1", "^g3a1")
        assert qualified is not None
        assert qualified[0] == 3
        assert qualified[1]["text"] == "Continue"
    finally:
        await database.disconnect()


@pytest.mark.asyncio
async def test_cleanup_old_refs_keeps_exact_generation_count(tmp_path: Path) -> None:
    """Cleanup should retain exactly the current generation and two predecessors."""
    database = Database(tmp_path / "state" / "state.db")
    await database.connect()
    try:
        for generation in range(1, 6):
            await database.save_refs(
                "s-1",
                generation,
                [{"ref": f"^g{generation}a1", "text": f"Generation {generation}"}],
            )

        await database.cleanup_old_refs("s-1", current_generation=5)

        assert await database.get_refs_for_generation("s-1", 1) == []
        assert await database.get_refs_for_generation("s-1", 2) == []
        for generation in (3, 4, 5):
            refs = await database.get_refs_for_generation("s-1", generation)
            assert [ref["ref"] for ref in refs] == [f"^g{generation}a1"]
    finally:
        await database.disconnect()


@pytest.mark.asyncio
async def test_cleanup_uses_current_generation_when_it_has_no_refs(tmp_path: Path) -> None:
    """An empty current snapshot should still advance the retention window."""
    database = Database(tmp_path / "state" / "state.db")
    await database.connect()
    try:
        for generation in range(1, 4):
            await database.save_refs(
                "s-1",
                generation,
                [{"ref": f"^g{generation}a1"}],
            )

        await database.cleanup_old_refs("s-1", current_generation=4)

        assert await database.get_refs_for_generation("s-1", 1) == []
        assert await database.get_refs_for_generation("s-1", 2) != []
    finally:
        await database.disconnect()


@pytest.mark.asyncio
async def test_cleanup_rejects_invalid_retention_count(tmp_path: Path) -> None:
    """A non-positive retention count should fail instead of deleting every ref."""
    database = Database(tmp_path / "state" / "state.db")

    with pytest.raises(ValueError, match="at least 1"):
        await database.cleanup_old_refs("s-1", current_generation=1, keep_generations=0)


@pytest.mark.asyncio
async def test_reads_wait_for_transaction_rollback(tmp_path: Path) -> None:
    """A concurrent read must not observe another coroutine's uncommitted row."""
    database = Database(tmp_path / "state" / "state.db")
    await database.connect()
    inserted = asyncio.Event()
    release_rollback = asyncio.Event()

    async def _write_then_rollback() -> None:
        with pytest.raises(RuntimeError, match="rollback requested"):
            async with database.transaction() as connection:
                await connection.execute(
                    """
                    INSERT INTO sessions
                        (session_id, device_serial, created_at, last_activity, generation, metadata)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    ("s-uncommitted", "emulator-5554", "now", "now", 0, "{}"),
                )
                inserted.set()
                await release_rollback.wait()
                raise RuntimeError("rollback requested")

    try:
        writer = asyncio.create_task(_write_then_rollback())
        await inserted.wait()
        reader = asyncio.create_task(database.get_session("s-uncommitted"))
        await asyncio.sleep(0)

        assert reader.done() is False
        release_rollback.set()
        await writer
        assert await reader is None
    finally:
        release_rollback.set()
        await database.disconnect()


@pytest.mark.asyncio
async def test_cancelled_transaction_rolls_back_before_releasing_lock(tmp_path: Path) -> None:
    """Cancellation must not leave writes for a later transaction to commit accidentally."""
    database = Database(tmp_path / "state" / "state.db")
    await database.connect()
    inserted = asyncio.Event()

    async def _cancelled_writer() -> None:
        async with database.transaction() as connection:
            await connection.execute(
                """
                INSERT INTO sessions
                    (session_id, device_serial, created_at, last_activity, generation, metadata)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                ("s-cancelled", "emulator-5554", "now", "now", 0, "{}"),
            )
            inserted.set()
            await asyncio.Event().wait()

    try:
        writer = asyncio.create_task(_cancelled_writer())
        await inserted.wait()
        writer.cancel()
        with pytest.raises(asyncio.CancelledError):
            await writer

        assert await database.get_session("s-cancelled") is None
    finally:
        await database.disconnect()


class TestSessionMetadataPersistence:
    """Tests that session metadata survives unrelated updates."""

    @pytest.mark.asyncio
    async def test_metadata_survives_generation_bump(self, tmp_path) -> None:
        """A generation update must not silently wipe stored metadata."""
        from android_emu_agent.db.models import Database

        database = Database(tmp_path / "state.db")
        await database.connect()
        try:
            await database.save_session(
                "s-1", "emulator-5554", generation=0, metadata={"label": "checkout flow"}
            )
            # The hot path: increment_generation saves without passing metadata.
            await database.save_session("s-1", "emulator-5554", generation=1)

            stored = await database.get_session("s-1")
        finally:
            await database.disconnect()

        assert stored is not None
        assert stored["generation"] == 1
        assert stored["metadata"] == {"label": "checkout flow"}

    @pytest.mark.asyncio
    async def test_metadata_defaults_to_empty_object(self, tmp_path) -> None:
        """A session saved without metadata reads back as an empty mapping."""
        from android_emu_agent.db.models import Database

        database = Database(tmp_path / "state.db")
        await database.connect()
        try:
            await database.save_session("s-2", "emulator-5554", generation=0)
            stored = await database.get_session("s-2")
        finally:
            await database.disconnect()

        assert stored is not None
        assert stored["metadata"] == {}

    @pytest.mark.asyncio
    async def test_metadata_can_be_replaced_explicitly(self, tmp_path) -> None:
        """Passing metadata explicitly still overwrites the stored value."""
        from android_emu_agent.db.models import Database

        database = Database(tmp_path / "state.db")
        await database.connect()
        try:
            await database.save_session("s-3", "emulator-5554", metadata={"stage": "one"})
            await database.save_session("s-3", "emulator-5554", metadata={"stage": "two"})
            stored = await database.get_session("s-3")
        finally:
            await database.disconnect()

        assert stored is not None
        assert stored["metadata"] == {"stage": "two"}
