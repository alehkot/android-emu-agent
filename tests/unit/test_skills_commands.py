"""Tests for Agent Skill installation CLI commands."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import typer

from android_emu_agent.cli.commands import skills


def _install(
    directory: Path,
    *,
    agent: skills.Agent = skills.Agent.claude,
    project: bool = False,
    copy: bool = False,
    symlink: bool = False,
    force: bool = False,
    json_output: bool = False,
) -> None:
    """Invoke the install command with explicit arguments."""
    skills.skills_install(
        agent=agent,
        project=project,
        directory=str(directory),
        copy=copy,
        symlink=symlink,
        force=force,
        json_output=json_output,
    )


def _force_package_origin(monkeypatch: pytest.MonkeyPatch, source: Path) -> None:
    """Make source resolution report a packaged (wheel) origin."""
    monkeypatch.setattr(skills, "_package_source", lambda: source)


def _force_checkout_origin(monkeypatch: pytest.MonkeyPatch, source: Path) -> None:
    """Make source resolution report a source-checkout origin."""
    monkeypatch.setattr(skills, "_package_source", lambda: None)
    monkeypatch.setattr(skills, "_checkout_source", lambda: source)


@pytest.fixture
def fake_skill(tmp_path: Path) -> Path:
    """Create a minimal skill payload to install."""
    source = tmp_path / "src-skill"
    (source / "references").mkdir(parents=True)
    (source / "SKILL.md").write_text("---\nname: android-emu-agent\n---\n")
    (source / "references" / "core-loop.md").write_text("loop\n")
    return source


def test_resolve_source_prefers_package(monkeypatch: pytest.MonkeyPatch, fake_skill: Path) -> None:
    """Should prefer the packaged copy over a checkout."""
    _force_package_origin(monkeypatch, fake_skill)
    source, origin = skills.resolve_skill_source()
    assert source == fake_skill
    assert origin is skills.Origin.package


def test_resolve_source_falls_back_to_checkout(
    monkeypatch: pytest.MonkeyPatch, fake_skill: Path
) -> None:
    """Should fall back to the checkout when no packaged copy exists."""
    _force_checkout_origin(monkeypatch, fake_skill)
    source, origin = skills.resolve_skill_source()
    assert source == fake_skill
    assert origin is skills.Origin.checkout


def test_resolve_source_raises_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Should raise an actionable error when no skill payload is found."""
    monkeypatch.setattr(skills, "_package_source", lambda: None)
    monkeypatch.setattr(skills, "_checkout_source", lambda: None)
    with pytest.raises(Exception) as exc_info:
        skills.resolve_skill_source()
    assert getattr(exc_info.value, "code", "") == "ERR_SKILL_SOURCE_NOT_FOUND"


def test_install_copies_from_package(
    monkeypatch: pytest.MonkeyPatch, fake_skill: Path, tmp_path: Path
) -> None:
    """Should copy files and write a marker for packaged installs."""
    _force_package_origin(monkeypatch, fake_skill)
    target = tmp_path / "target"

    _install(target)

    dest = target / skills.SKILL_NAME
    assert not dest.is_symlink()
    assert (dest / "SKILL.md").is_file()
    assert (dest / "references" / "core-loop.md").is_file()
    marker = json.loads((dest / skills.MARKER_NAME).read_text())
    assert marker["installed_by"] == "android-emu-agent"
    assert marker["source"] == "package"
    assert marker["mode"] == "copy"


def test_install_symlinks_from_checkout(
    monkeypatch: pytest.MonkeyPatch, fake_skill: Path, tmp_path: Path
) -> None:
    """Should symlink a checkout so local edits stay live."""
    _force_checkout_origin(monkeypatch, fake_skill)
    target = tmp_path / "target"

    _install(target)

    dest = target / skills.SKILL_NAME
    assert dest.is_symlink()
    assert dest.resolve() == fake_skill.resolve()
    assert not (dest / skills.MARKER_NAME).exists()


def test_install_copy_flag_overrides_checkout_symlink(
    monkeypatch: pytest.MonkeyPatch, fake_skill: Path, tmp_path: Path
) -> None:
    """Should copy from a checkout when --copy is given."""
    _force_checkout_origin(monkeypatch, fake_skill)
    target = tmp_path / "target"

    _install(target, copy=True)

    dest = target / skills.SKILL_NAME
    assert not dest.is_symlink()
    assert json.loads((dest / skills.MARKER_NAME).read_text())["source"] == "checkout"


def test_install_symlink_from_package_errors(
    monkeypatch: pytest.MonkeyPatch, fake_skill: Path, tmp_path: Path
) -> None:
    """Should refuse symlink mode when the source is a packaged copy."""
    _force_package_origin(monkeypatch, fake_skill)

    with pytest.raises(typer.Exit) as exc_info:
        _install(tmp_path / "target", symlink=True)
    assert exc_info.value.exit_code == 1


def test_install_is_idempotent_and_removes_stale_files(
    monkeypatch: pytest.MonkeyPatch, fake_skill: Path, tmp_path: Path
) -> None:
    """Should replace a managed install wholesale, dropping removed files."""
    _force_package_origin(monkeypatch, fake_skill)
    target = tmp_path / "target"
    _install(target)

    stale = target / skills.SKILL_NAME / "references" / "removed.md"
    stale.write_text("obsolete\n")

    _install(target)

    assert not stale.exists()
    assert (target / skills.SKILL_NAME / "SKILL.md").is_file()


def test_install_refuses_unmanaged_directory(
    monkeypatch: pytest.MonkeyPatch, fake_skill: Path, tmp_path: Path
) -> None:
    """Should not clobber a directory the CLI did not install."""
    _force_package_origin(monkeypatch, fake_skill)
    target = tmp_path / "target"
    existing = target / skills.SKILL_NAME
    existing.mkdir(parents=True)
    (existing / "SKILL.md").write_text("hand written\n")

    with pytest.raises(typer.Exit) as exc_info:
        _install(target)
    assert exc_info.value.exit_code == 1
    assert (existing / "SKILL.md").read_text() == "hand written\n"


def test_install_force_replaces_unmanaged_directory(
    monkeypatch: pytest.MonkeyPatch, fake_skill: Path, tmp_path: Path
) -> None:
    """Should replace an unmanaged directory when --force is given."""
    _force_package_origin(monkeypatch, fake_skill)
    target = tmp_path / "target"
    existing = target / skills.SKILL_NAME
    existing.mkdir(parents=True)
    (existing / "SKILL.md").write_text("hand written\n")

    _install(target, force=True)

    assert (existing / skills.MARKER_NAME).is_file()
    assert (existing / "SKILL.md").read_text().startswith("---")


def test_install_replaces_existing_symlink(
    monkeypatch: pytest.MonkeyPatch, fake_skill: Path, tmp_path: Path
) -> None:
    """Should replace a stale symlink without requiring --force."""
    _force_package_origin(monkeypatch, fake_skill)
    target = tmp_path / "target"
    target.mkdir()
    (target / skills.SKILL_NAME).symlink_to(tmp_path / "gone", target_is_directory=True)

    _install(target)

    dest = target / skills.SKILL_NAME
    assert not dest.is_symlink()
    assert (dest / "SKILL.md").is_file()


def test_install_rejects_conflicting_modes(tmp_path: Path) -> None:
    """Should reject --copy together with --symlink."""
    with pytest.raises(typer.BadParameter):
        _install(tmp_path / "target", copy=True, symlink=True)


def test_install_rejects_dir_with_project(tmp_path: Path) -> None:
    """Should reject --dir together with --project."""
    with pytest.raises(typer.BadParameter):
        _install(tmp_path / "target", project=True)


def test_claude_dir_honors_config_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Should honor CLAUDE_CONFIG_DIR for the global Claude target."""
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "cfg"))
    assert skills._agent_skills_dir(skills.Agent.claude, False) == tmp_path / "cfg" / "skills"


def test_claude_project_dir_uses_cwd(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Should place project-scoped Claude skills under the working directory."""
    monkeypatch.chdir(tmp_path)
    assert skills._agent_skills_dir(skills.Agent.claude, True) == tmp_path / ".claude" / "skills"


def test_codex_dir_honors_home_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Should honor CODEX_HOME for the Codex target."""
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex"))
    assert skills._agent_skills_dir(skills.Agent.codex, False) == tmp_path / "codex" / "skills"


def test_codex_project_scope_rejected() -> None:
    """Should reject project scope for Codex."""
    with pytest.raises(typer.BadParameter):
        skills._agent_skills_dir(skills.Agent.codex, True)


def test_vscode_requires_project_scope() -> None:
    """Should reject global scope for VS Code."""
    with pytest.raises(typer.BadParameter):
        skills._agent_skills_dir(skills.Agent.vscode, False)


def test_list_reports_target_states(
    monkeypatch: pytest.MonkeyPatch,
    fake_skill: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Should report installed, symlinked, and absent targets as JSON."""
    _force_package_origin(monkeypatch, fake_skill)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex"))
    monkeypatch.chdir(tmp_path)
    _install(tmp_path / "cfg" / "skills")
    capsys.readouterr()

    skills.skills_list(json_output=True)

    payload = json.loads(capsys.readouterr().out)
    assert payload["origin"] == "package"
    states = {(t["agent"], t["scope"]): t["state"] for t in payload["targets"]}
    assert states[("claude", "global")] == "copy"
    assert states[("codex", "global")] == "absent"


def test_path_outputs_source(
    monkeypatch: pytest.MonkeyPatch, fake_skill: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Should print the resolved skill source path."""
    _force_package_origin(monkeypatch, fake_skill)

    skills.skills_path(json_output=True)

    payload = json.loads(capsys.readouterr().out)
    assert payload["path"] == str(fake_skill)
    assert payload["origin"] == "package"
