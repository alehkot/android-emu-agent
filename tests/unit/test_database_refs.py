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
