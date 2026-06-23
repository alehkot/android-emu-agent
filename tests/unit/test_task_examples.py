"""Tests for checked-in task script examples."""

from __future__ import annotations

from pathlib import Path

from android_emu_agent.tasks import TaskManager


def test_checked_in_task_scripts_parse_and_validate() -> None:
    """Example .aea scripts should stay valid as the task DSL evolves."""
    examples_dir = Path(__file__).resolve().parents[2] / "examples" / "tasks"
    scripts = sorted(examples_dir.glob("*.aea"))
    assert scripts, "expected checked-in .aea task examples"

    manager = TaskManager()
    for script in scripts:
        spec = manager.parse_script(script.read_text(encoding="utf-8"), source_name=str(script))
        plan = manager.validate(spec)
        assert plan["status"] == "done", script.name
