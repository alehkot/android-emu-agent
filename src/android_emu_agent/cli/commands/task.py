"""Task harness CLI commands."""

from __future__ import annotations

import json
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import typer

from android_emu_agent.cli.daemon_client import DaemonClient
from android_emu_agent.cli.utils import handle_response
from android_emu_agent.tasks import is_task_script_path

app = typer.Typer(help="Task harness commands")


@dataclass(frozen=True)
class LoadedTask:
    path: Path
    payload: dict[str, Any] | str
    is_script: bool


def _load_task(path: str) -> LoadedTask:
    task_path = Path(path).expanduser()
    if is_task_script_path(task_path):
        try:
            return LoadedTask(
                path=task_path,
                payload=task_path.read_text(encoding="utf-8"),
                is_script=True,
            )
        except FileNotFoundError:
            typer.echo(f"Error: task file not found: {task_path}")
            raise typer.Exit(code=1) from None

    try:
        payload = json.loads(task_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        typer.echo(f"Error: task file not found: {task_path}")
        raise typer.Exit(code=1) from None
    except json.JSONDecodeError as exc:
        typer.echo(f"Error: invalid JSON in task file: {exc}")
        raise typer.Exit(code=1) from None

    if not isinstance(payload, dict):
        typer.echo("Error: task file must contain a JSON object")
        raise typer.Exit(code=1)
    return LoadedTask(path=task_path, payload=cast(dict[str, Any], payload), is_script=False)


def _resolve_session(task: LoadedTask, session: str | None) -> str:
    if session:
        return session
    if isinstance(task.payload, dict):
        task_session = task.payload.get("session_id")
        if isinstance(task_session, str) and task_session:
            return task_session
    elif isinstance(task.payload, str):
        task_session = _script_session_id(task.payload)
        if task_session:
            return task_session
    typer.echo("Error: provide --session or session_id in the task file")
    raise typer.Exit(code=1)


def _script_session_id(script: str) -> str | None:
    for line in script.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        try:
            tokens = shlex.split(stripped, comments=True, posix=True)
        except ValueError:
            return None
        if len(tokens) == 2 and tokens[0].lower() == "session":
            return tokens[1]
    return None


def _script_body(task: LoadedTask) -> str:
    if not isinstance(task.payload, str):
        raise TypeError("loaded task is not a script")
    return task.payload


def _json_body(task: LoadedTask) -> dict[str, Any]:
    if not isinstance(task.payload, dict):
        raise TypeError("loaded task is not JSON")
    return task.payload


@app.command("validate")
def task_validate(
    path: str = typer.Argument(..., help="Task JSON or .aea script file"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Validate a task spec or script without running it."""
    task = _load_task(path)
    client = DaemonClient()
    if task.is_script:
        resp = client.request(
            "POST",
            "/tasks/script/validate",
            json_body={"script": _script_body(task), "source_name": str(task.path)},
        )
    else:
        resp = client.request("POST", "/tasks/validate", json_body={"task": _json_body(task)})
    client.close()
    handle_response(resp, json_output=json_output)


@app.command("run")
def task_run(
    path: str = typer.Argument(..., help="Task JSON or .aea script file"),
    session: str | None = typer.Option(None, "--session", "-s", help="Session ID override"),
    continue_on_failure: bool = typer.Option(
        False,
        "--continue-on-failure",
        help="Continue after failed steps or verifiers",
    ),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Run a task spec or script with verifiers."""
    task = _load_task(path)
    session_id = _resolve_session(task, session)
    client = DaemonClient()
    if task.is_script:
        resp = client.request(
            "POST",
            "/tasks/script/run",
            json_body={
                "session_id": session_id,
                "script": _script_body(task),
                "source_name": str(task.path),
                "stop_on_failure": not continue_on_failure,
            },
        )
    else:
        resp = client.request(
            "POST",
            "/tasks/run",
            json_body={
                "session_id": session_id,
                "task": _json_body(task),
                "stop_on_failure": not continue_on_failure,
            },
        )
    client.close()
    handle_response(resp, json_output=json_output)
