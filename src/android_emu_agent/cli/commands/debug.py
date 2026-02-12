"""Debugger CLI commands."""

from __future__ import annotations

import typer

from android_emu_agent.cli.daemon_client import DaemonClient
from android_emu_agent.cli.utils import handle_response

app = typer.Typer(help="Debugger commands (JDI Bridge)")


@app.command("ping")
def debug_ping(
    session_id: str = typer.Argument(..., help="Session ID"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Ping the JDI Bridge to verify it starts and responds."""
    client = DaemonClient(timeout=30.0)
    resp = client.request("POST", "/debug/ping", json_body={"session_id": session_id})
    client.close()
    handle_response(resp, json_output=json_output)


@app.command("attach")
def debug_attach(
    session_id: str = typer.Option(..., "--session", help="Session ID"),
    package: str = typer.Option(..., "--package", help="App package name"),
    process: str | None = typer.Option(
        None,
        "--process",
        help="Optional process name (e.g. com.example.app:remote) when multiple are debuggable",
    ),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Attach the debugger to a running app's JVM."""
    client = DaemonClient(timeout=30.0)
    resp = client.request(
        "POST",
        "/debug/attach",
        json_body={"session_id": session_id, "package": package, "process": process},
    )
    client.close()
    handle_response(resp, json_output=json_output)


@app.command("detach")
def debug_detach(
    session_id: str = typer.Option(..., "--session", help="Session ID"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Detach the debugger from a session."""
    client = DaemonClient(timeout=30.0)
    resp = client.request(
        "POST",
        "/debug/detach",
        json_body={"session_id": session_id},
    )
    client.close()
    handle_response(resp, json_output=json_output)


@app.command("status")
def debug_status(
    session_id: str = typer.Option(..., "--session", help="Session ID"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Get the debug session status."""
    client = DaemonClient(timeout=30.0)
    resp = client.request("GET", f"/debug/status/{session_id}")
    client.close()
    handle_response(resp, json_output=json_output)
