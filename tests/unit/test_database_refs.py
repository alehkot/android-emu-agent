"""Tests for persisted generation-scoped ref lookup."""

from __future__ import annotations

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
