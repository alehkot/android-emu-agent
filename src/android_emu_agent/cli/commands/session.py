"""Session management CLI commands."""

from __future__ import annotations

import typer

from android_emu_agent.cli.daemon_client import DaemonClient, format_json
from android_emu_agent.cli.utils import handle_response

app = typer.Typer(help="Session management commands")


@app.command("start")
def session_start(
    device: str = typer.Option(..., "--device", "-d", help="Device serial"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Start a new session on a device."""
    client = DaemonClient()
    resp = client.request("POST", "/sessions/start", json_body={"device_serial": device})
    client.close()

    data = resp.json()
    if json_output:
        typer.echo(format_json(data))
        return

    if data.get("status") == "done":
        typer.echo(data.get("session_id"))
        return

    handle_response(resp, json_output=json_output)


@app.command("stop")
def session_stop(
    session_id: str = typer.Argument(..., help="Session ID"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Stop a session."""
    client = DaemonClient()
    resp = client.request("POST", "/sessions/stop", json_body={"session_id": session_id})
    client.close()
    handle_response(resp, json_output=json_output)


@app.command("info")
def session_info(
    session_id: str = typer.Argument(..., help="Session ID"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Show session info."""
    client = DaemonClient()
    resp = client.request("GET", f"/sessions/{session_id}")
    client.close()
    handle_response(resp, json_output=json_output)


@app.command("list")
def session_list(json_output: bool = typer.Option(False, "--json", help="Output JSON")) -> None:
    """List active sessions."""
    client = DaemonClient()
    resp = client.request("GET", "/sessions")
    client.close()
    handle_response(resp, json_output=json_output)
