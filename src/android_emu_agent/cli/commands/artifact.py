"""Artifact and debugging CLI commands."""

from __future__ import annotations

import typer

from android_emu_agent.cli.daemon_client import DaemonClient
from android_emu_agent.cli.utils import (
    handle_response,
    handle_response_with_pull,
    require_target,
    resolve_session_id,
)

app = typer.Typer(help="Artifact and debugging commands")


@app.command("save-snapshot")
def artifact_save_snapshot(
    session_id: str = typer.Argument(..., help="Session ID"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Save the last snapshot to disk."""
    client = DaemonClient()
    resp = client.request("POST", "/artifacts/save_snapshot", json_body={"session_id": session_id})
    client.close()
    handle_response(resp, json_output=json_output)


@app.command("screenshot")
def artifact_screenshot(
    session_id: str | None = typer.Argument(None, help="Session ID"),
    device: str | None = typer.Option(None, "--device", "-d", help="Device serial"),
    session: str | None = typer.Option(None, "--session", "-s", help="Session ID"),
    pull: bool = typer.Option(False, "--pull", help="Copy screenshot to local path"),
    output: str | None = typer.Option(
        None, "--output", "-o", help="Output path (file or directory)"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Capture a screenshot artifact."""
    try:
        resolved_session = resolve_session_id(session_id, session)
    except typer.BadParameter as exc:
        typer.echo(f"Error: {exc}")
        raise typer.Exit(code=1) from None

    payload = require_target(device, resolved_session)
    client = DaemonClient()
    resp = client.request("POST", "/ui/screenshot", json_body=payload)
    client.close()
    handle_response_with_pull(resp, json_output=json_output, pull=pull, output=output)


@app.command("logs")
def artifact_logs(
    session_id: str | None = typer.Argument(None, help="Session ID"),
    session: str | None = typer.Option(None, "--session", "-s", help="Session ID"),
    package: str | None = typer.Option(None, "--package", "-p", help="Filter by package"),
    level: str | None = typer.Option(
        None, "--level", help="Log level (v|d|i|w|e|f|s or verbose/debug/...)"
    ),
    since: str | None = typer.Option(
        None, "--since", help="Logcat -t value: timestamp (MM-DD HH:MM:SS.mmm) or line count"
    ),
    follow: bool = typer.Option(False, "--follow", help="Follow logs (live stream)"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Pull logcat logs."""
    try:
        resolved_session = resolve_session_id(session_id, session)
        if not resolved_session:
            raise typer.BadParameter("Provide session ID as argument or --session")
    except typer.BadParameter as exc:
        typer.echo(f"Error: {exc}")
        raise typer.Exit(code=1) from None

    client = DaemonClient(timeout=3600.0 if follow else 10.0)
    resp = client.request(
        "POST",
        "/artifacts/logs",
        json_body={
            "session_id": resolved_session,
            "package": package,
            "level": level,
            "since": since,
            "follow": follow,
        },
    )
    client.close()
    handle_response(resp, json_output=json_output)


@app.command("bundle")
def artifact_bundle(
    session_id: str = typer.Argument(..., help="Session ID"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Create a debug bundle."""
    client = DaemonClient()
    resp = client.request("POST", "/artifacts/debug_bundle", json_body={"session_id": session_id})
    client.close()
    handle_response(resp, json_output=json_output)
