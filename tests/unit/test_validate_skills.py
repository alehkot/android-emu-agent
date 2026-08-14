"""Tests for Agent Skill content validation."""

from __future__ import annotations

from pathlib import Path

from scripts.validate_skills import validate_skills

FRONTMATTER = """---
name: sample-skill
description: Does a thing. Use when the user asks for a thing.
---

# Sample Skill

"""

REFERENCE_HEADER = """# Reference

> **Read this file when** you need the sample reference.

"""


def _write_skill(root: Path, body: str = "", reference_body: str = "") -> Path:
    skill_dir = root / "sample-skill"
    (skill_dir / "references").mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(FRONTMATTER + body, encoding="utf-8")
    (skill_dir / "references" / "guide.md").write_text(
        REFERENCE_HEADER + reference_body, encoding="utf-8"
    )
    return skill_dir


def test_clean_skill_passes(tmp_path: Path) -> None:
    """Should accept a skill using the installed-CLI invocation."""
    _write_skill(tmp_path, body="Run `android-emu-agent daemon start`.\n")
    assert validate_skills(tmp_path) == []


def test_uv_run_in_reference_is_rejected(tmp_path: Path) -> None:
    """Should reject the checkout-only invocation in a reference file."""
    _write_skill(tmp_path, reference_body="Run `uv run android-emu-agent ui snapshot`.\n")
    errors = validate_skills(tmp_path)
    assert any("bare 'android-emu-agent' invocation" in error for error in errors)


def test_uv_run_allowance_in_skill_md(tmp_path: Path) -> None:
    """Should allow SKILL.md to quote the checkout form once for the rule itself."""
    _write_skill(tmp_path, body="Inside the checkout run `uv run android-emu-agent ...`.\n")
    assert validate_skills(tmp_path) == []


def test_uv_run_allowance_is_capped(tmp_path: Path) -> None:
    """Should reject repeated checkout-form usage even in SKILL.md."""
    _write_skill(
        tmp_path,
        body="Use `uv run android-emu-agent a` and `uv run android-emu-agent b`.\n",
    )
    errors = validate_skills(tmp_path)
    assert any("bare 'android-emu-agent' invocation" in error for error in errors)


def test_repository_only_paths_are_rejected(tmp_path: Path) -> None:
    """Should reject paths that do not exist in the shipped skill."""
    _write_skill(
        tmp_path,
        body="See `docs/aea-spec.md`.\n",
        reference_body="Copy `examples/tasks/login-flow.aea` and run `./scripts/dev.sh check`.\n",
    )
    errors = validate_skills(tmp_path)
    joined = "\n".join(errors)
    assert "docs/aea-spec.md" in joined
    assert "examples/tasks" in joined
    assert "scripts/dev.sh" in joined


def test_urls_containing_repository_paths_are_allowed(tmp_path: Path) -> None:
    """Should not flag docs-site or GitHub URLs that embed those path segments."""
    _write_skill(
        tmp_path,
        body="See <https://alehkot.github.io/android-emu-agent/aea-spec/>.\n",
        reference_body=(
            "Copy from <https://github.com/alehkot/android-emu-agent/tree/main/examples/tasks>.\n"
        ),
    )
    assert validate_skills(tmp_path) == []


def test_real_bundled_skill_is_valid() -> None:
    """The shipped skill must satisfy every rule."""
    repo_root = Path(__file__).resolve().parents[2]
    assert validate_skills(repo_root / "skills") == []
