"""Task harness CLI commands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import typer

from android_emu_agent.cli.daemon_client import DaemonClient
from android_emu_agent.cli.utils import handle_response

app = typer.Typer(help="Task harness commands")


def _load_task(path: str) -> dict[str, Any]:
    task_path = Path(path).expanduser()
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
    return cast(dict[str, Any], payload)


def _resolve_session(task: dict[str, Any], session: str | None) -> str:
    if session:
        return session
    task_session = task.get("session_id")
    if isinstance(task_session, str) and task_session:
        return task_session
    typer.echo("Error: provide --session or session_id in the task file")
    raise typer.Exit(code=1)


@app.command("validate")
def task_validate(
    path: str = typer.Argument(..., help="Task JSON file"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Validate a task spec without running it."""
    task = _load_task(path)
    client = DaemonClient()
    resp = client.request("POST", "/tasks/validate", json_body={"task": task})
    client.close()
    handle_response(resp, json_output=json_output)


@app.command("run")
def task_run(
    path: str = typer.Argument(..., help="Task JSON file"),
    session: str | None = typer.Option(None, "--session", "-s", help="Session ID override"),
    continue_on_failure: bool = typer.Option(
        False,
        "--continue-on-failure",
        help="Continue after failed steps or verifiers",
    ),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Run a task spec with verifiers."""
    task = _load_task(path)
    session_id = _resolve_session(task, session)
    client = DaemonClient()
    resp = client.request(
        "POST",
        "/tasks/run",
        json_body={
            "session_id": session_id,
            "task": task,
            "stop_on_failure": not continue_on_failure,
        },
    )
    client.close()
    handle_response(resp, json_output=json_output)
