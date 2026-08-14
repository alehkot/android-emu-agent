"""Tests for release workflow safety invariants."""

from __future__ import annotations

from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "dev.sh"


def _function_body(name: str) -> str:
    script = SCRIPT_PATH.read_text(encoding="utf-8")
    marker = f"{name}() {{\n"
    start = script.index(marker) + len(marker)
    end = script.index("\n}\n", start)
    return script[start:end]


def test_clean_worktree_check_includes_untracked_files() -> None:
    """Release inputs should include untracked files in the cleanliness decision."""
    body = _function_body("ensure_clean_worktree")

    assert "git status --porcelain=v1 --untracked-files=normal" in body
    assert "git diff --quiet" not in body


def test_release_validates_and_builds_before_tag_or_push() -> None:
    """No release ref should be created or pushed before validation and artifact builds."""
    body = _function_body("release_current_version")

    checks = body.index("run_release_checks")
    python_build = body.index("build_python_release_artifacts")
    bridge_build = body.index("build_bridge_release_artifacts")
    clean_recheck = body.index("ensure_clean_worktree", checks)
    tag = body.index("ensure_release_tag_at_head")
    push = body.index("push_release_refs")

    assert checks < python_build < bridge_build < clean_recheck < tag < push


def test_version_bump_validates_before_commit_and_tag() -> None:
    """A release bump should pass the gate before creating its commit and local tag."""
    body = _function_body("release_bump_version")

    assert body.index("run_release_checks") < body.index("commit_and_tag_version_bump")


def test_pypi_publish_validates_and_rechecks_before_upload() -> None:
    """PyPI uploads should use checked artifacts from a still-clean source tree."""
    body = _function_body("publish_current_python_version")

    checks = body.index("run_release_checks")
    build = body.index("build_python_release_artifacts")
    clean_recheck = body.index("ensure_clean_worktree", checks)
    publish = body.index("publish_python_release_artifacts")

    assert checks < build < clean_recheck < publish


def test_testpypi_publish_validates_and_rechecks_before_upload() -> None:
    """TestPyPI uploads should follow the same gate as production PyPI uploads."""
    body = _function_body("publish_current_python_test_version")

    checks = body.index("run_release_checks")
    build = body.index("build_python_release_artifacts")
    clean_recheck = body.index("ensure_clean_worktree", checks)
    publish = body.index("publish_python_test_release_artifacts")

    assert checks < build < clean_recheck < publish


def test_testpypi_publish_requires_dedicated_credentials() -> None:
    """TestPyPI uploads must not silently fall back to production PyPI credentials."""
    body = _function_body("publish_python_test_release_artifacts")

    assert "TWINE_TEST_USERNAME" in body
    assert "TWINE_TEST_PASSWORD" in body
    assert "--repository-url" in body
