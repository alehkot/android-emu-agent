"""Trace archive CLI commands."""

from __future__ import annotations

from pathlib import Path

import typer

from android_emu_agent.cli.daemon_client import DaemonClient
from android_emu_agent.cli.utils import handle_response

app = typer.Typer(help="Agent trace recording and replay commands")


@app.command("start")
def trace_start(
    session_id: str = typer.Argument(..., help="Session ID"),
    label: str | None = typer.Option(None, "--label", "-l", help="Optional trace label"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Start recording a trace for a session."""
    client = DaemonClient()
    resp = client.request(
        "POST",
        "/trace/start",
        json_body={"session_id": session_id, "label": label},
    )
    client.close()
    handle_response(resp, json_output=json_output)


@app.command("stop")
def trace_stop(
    session_id: str = typer.Argument(..., help="Session ID"),
    output: str | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Archive output path or directory, outside the trace source directory",
    ),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Stop recording and write a trace archive.

    Explicit output paths expand ~ and are relative to your current directory.
    Omit --output to use the daemon's default archive directory.
    """
    client = DaemonClient()
    resp = client.request(
        "POST",
        "/trace/stop",
        json_body={
            "session_id": session_id,
            "output_path": str(Path(output).expanduser().absolute()) if output else output,
        },
    )
    client.close()
    handle_response(resp, json_output=json_output)


@app.command("status")
def trace_status(
    session_id: str | None = typer.Option(None, "--session", "-s", help="Filter by session ID"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """List active traces."""
    path = "/trace/status"
    if session_id:
        path = f"{path}?session_id={session_id}"
    client = DaemonClient()
    resp = client.request("GET", path)
    client.close()
    handle_response(resp, json_output=json_output)


@app.command("replay")
def trace_replay(
    path: str = typer.Argument(..., help="Trace archive path"),
    until_failure: bool = typer.Option(
        False,
        "--until-failure",
        help="Stop the dry-run replay plan at the first failed daemon exchange",
    ),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Return a dry-run replay plan from a trace archive.

    Archive paths expand ~ and are relative to your current directory, even if
    the daemon started elsewhere.
    """
    client = DaemonClient()
    resp = client.request(
        "POST",
        "/trace/replay",
        json_body={
            "path": str(Path(path).expanduser().absolute()),
            "until_failure": until_failure,
        },
    )
    client.close()
    handle_response(resp, json_output=json_output)


@app.command("export")
def trace_export(
    path: str = typer.Argument(..., help="Trace archive path"),
    output: str | None = typer.Option(None, "--output", "-o", help="Markdown output path"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Export a trace archive to Markdown.

    Archive and explicit output paths expand ~ and are relative to your current
    directory. Omit --output and use --json to read the Markdown response without
    writing a report file.
    """
    client = DaemonClient()
    resp = client.request(
        "POST",
        "/trace/export",
        json_body={
            "path": str(Path(path).expanduser().absolute()),
            "output_path": str(Path(output).expanduser().absolute()) if output else output,
            "format": "markdown",
        },
    )
    client.close()
    handle_response(resp, json_output=json_output)
