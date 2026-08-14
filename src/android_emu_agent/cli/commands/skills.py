"""Agent Skill installation CLI commands."""

from __future__ import annotations

import json
import os
import shutil
from enum import Enum
from importlib.resources import files
from pathlib import Path
from typing import Any, NoReturn

import typer

from android_emu_agent import __version__
from android_emu_agent.cli.daemon_client import format_json
from android_emu_agent.errors import (
    AgentError,
    skill_source_not_found_error,
    skill_symlink_unsupported_error,
    skill_target_exists_error,
)

app = typer.Typer(help="Install the bundled Agent Skill into coding agent directories")

SKILL_NAME = "android-emu-agent"
MARKER_NAME = ".android-emu-agent-skill.json"
_CHECKOUT_SEARCH_DEPTH = 6


class Agent(str, Enum):
    """Supported coding agents."""

    claude = "claude"
    codex = "codex"
    vscode = "vscode"


class Origin(str, Enum):
    """Where the bundled skill files were resolved from."""

    package = "package"
    checkout = "checkout"


def _package_source() -> Path | None:
    """Return the skill directory shipped inside the installed wheel."""
    try:
        candidate = Path(str(files("android_emu_agent") / "skills" / SKILL_NAME))
    except (ModuleNotFoundError, TypeError):  # pragma: no cover - defensive
        return None
    return candidate if (candidate / "SKILL.md").is_file() else None


def _checkout_source() -> Path | None:
    """Return the skill directory from a source checkout containing this module."""
    for parent in list(Path(__file__).resolve().parents)[:_CHECKOUT_SEARCH_DEPTH]:
        candidate = parent / "skills" / SKILL_NAME
        if (candidate / "SKILL.md").is_file() and (parent / "pyproject.toml").is_file():
            return candidate
    return None


def resolve_skill_source() -> tuple[Path, Origin]:
    """Resolve the bundled skill directory, preferring the installed package copy."""
    package = _package_source()
    if package is not None:
        return package, Origin.package
    checkout = _checkout_source()
    if checkout is not None:
        return checkout, Origin.checkout
    raise skill_source_not_found_error()


def _agent_skills_dir(agent: Agent, project: bool) -> Path:
    """Return the skills directory for an agent, honoring documented env overrides."""
    if agent is Agent.claude:
        if project:
            return Path.cwd() / ".claude" / "skills"
        config = os.environ.get("CLAUDE_CONFIG_DIR")
        root = Path(config).expanduser() if config else Path.home() / ".claude"
        return root / "skills"
    if agent is Agent.codex:
        if project:
            raise typer.BadParameter(
                "Codex reads skills from a global directory; use --dir for a custom location"
            )
        codex_home = os.environ.get("CODEX_HOME")
        root = Path(codex_home).expanduser() if codex_home else Path.home() / ".codex"
        return root / "skills"
    if not project:
        raise typer.BadParameter("VS Code skills are project-scoped; pass --project")
    return Path.cwd() / ".agents" / "skills"


def _resolve_target_dir(agent: Agent, project: bool, directory: str | None) -> Path:
    if directory is not None:
        return Path(directory).expanduser()
    return _agent_skills_dir(agent, project)


def _read_marker(dest: Path) -> dict[str, Any] | None:
    marker = dest / MARKER_NAME
    if not marker.is_file():
        return None
    try:
        data = json.loads(marker.read_text())
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _write_marker(dest: Path, origin: Origin) -> None:
    payload = {
        "installed_by": "android-emu-agent",
        "version": __version__,
        "mode": "copy",
        "source": origin.value,
    }
    (dest / MARKER_NAME).write_text(format_json(payload) + "\n")


def _clear_destination(dest: Path, force: bool) -> None:
    """Remove an existing destination, refusing to clobber unmanaged directories."""
    if dest.is_symlink():
        dest.unlink()
        return
    if not dest.exists():
        return
    if not dest.is_dir():
        if not force:
            raise skill_target_exists_error(str(dest))
        dest.unlink()
        return
    if _read_marker(dest) is None and not force:
        raise skill_target_exists_error(str(dest))
    shutil.rmtree(dest)


def _emit_error(error: AgentError, json_output: bool) -> NoReturn:
    if json_output:
        typer.echo(format_json({"error": error.to_dict()}))
    else:
        typer.echo(str(error), err=True)
        typer.echo(f"Remediation: {error.remediation}", err=True)
    raise typer.Exit(code=1)


@app.command("install")
def skills_install(
    agent: Agent = typer.Option(Agent.claude, "--agent", help="Target coding agent"),
    project: bool = typer.Option(
        False, "--project", help="Install into the current project instead of the home directory"
    ),
    directory: str | None = typer.Option(
        None, "--dir", help="Install into an explicit directory (overrides --agent/--project)"
    ),
    copy: bool = typer.Option(False, "--copy", help="Copy files even from a source checkout"),
    symlink: bool = typer.Option(False, "--symlink", help="Symlink a source checkout (dev flow)"),
    force: bool = typer.Option(False, "--force", help="Replace an existing skill directory"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Install the bundled Agent Skill for a coding agent."""
    if copy and symlink:
        raise typer.BadParameter("--copy and --symlink are mutually exclusive")
    if directory is not None and project:
        raise typer.BadParameter("--dir and --project are mutually exclusive")

    try:
        source, origin = resolve_skill_source()
        if symlink and origin is not Origin.checkout:
            raise skill_symlink_unsupported_error()

        use_symlink = symlink or (origin is Origin.checkout and not copy)
        target_dir = _resolve_target_dir(agent, project, directory)
        dest = target_dir / SKILL_NAME

        _clear_destination(dest, force)
        target_dir.mkdir(parents=True, exist_ok=True)

        if use_symlink:
            dest.symlink_to(source, target_is_directory=True)
        else:
            shutil.copytree(source, dest)
            _write_marker(dest, origin)
    except AgentError as error:
        _emit_error(error, json_output)

    mode = "symlink" if use_symlink else "copy"
    payload = {
        "status": "done",
        "skill": SKILL_NAME,
        "agent": None if directory is not None else agent.value,
        "scope": "custom" if directory is not None else ("project" if project else "global"),
        "mode": mode,
        "source": origin.value,
        "version": __version__,
        "path": str(dest),
    }
    if json_output:
        typer.echo(format_json(payload))
        return
    typer.echo(f"✓ Installed skill '{SKILL_NAME}' ({mode}, v{__version__}) -> {dest}")


@app.command("list")
def skills_list(json_output: bool = typer.Option(False, "--json", help="Output JSON")) -> None:
    """Show where the bundled Agent Skill is installed."""
    try:
        source, origin = resolve_skill_source()
    except AgentError as error:
        _emit_error(error, json_output)

    targets: list[dict[str, Any]] = []
    for agent, project in (
        (Agent.claude, False),
        (Agent.claude, True),
        (Agent.codex, False),
        (Agent.vscode, True),
    ):
        try:
            dest = _agent_skills_dir(agent, project) / SKILL_NAME
        except typer.BadParameter:  # pragma: no cover - defensive
            continue
        entry: dict[str, Any] = {
            "agent": agent.value,
            "scope": "project" if project else "global",
            "path": str(dest),
        }
        if dest.is_symlink():
            entry["state"] = "symlink"
            entry["target"] = str(dest.readlink())
        elif dest.is_dir():
            marker = _read_marker(dest)
            entry["state"] = "copy" if marker else "unmanaged"
            entry["version"] = marker.get("version") if marker else None
        else:
            entry["state"] = "absent"
        targets.append(entry)

    payload = {
        "skill": SKILL_NAME,
        "source": str(source),
        "origin": origin.value,
        "cli_version": __version__,
        "targets": targets,
    }
    if json_output:
        typer.echo(format_json(payload))
        return

    typer.echo(f"Skill source: {source} ({origin.value}, v{__version__})")
    for entry in targets:
        detail = entry["state"]
        if detail == "symlink":
            detail = f"symlink -> {entry['target']}"
        elif detail == "copy":
            detail = f"copy (v{entry.get('version') or 'unknown'})"
        typer.echo(f"  {entry['agent']:<7} {entry['scope']:<7} {entry['path']}  [{detail}]")


@app.command("path")
def skills_path(json_output: bool = typer.Option(False, "--json", help="Output JSON")) -> None:
    """Print the path to the bundled Agent Skill files."""
    try:
        source, origin = resolve_skill_source()
    except AgentError as error:
        _emit_error(error, json_output)

    if json_output:
        typer.echo(
            format_json({"path": str(source), "origin": origin.value, "version": __version__})
        )
        return
    typer.echo(str(source))
