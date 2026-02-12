"""Debugger CLI commands."""

from __future__ import annotations

import typer

from android_emu_agent.cli.daemon_client import DaemonClient, format_json
from android_emu_agent.cli.utils import handle_response

app = typer.Typer(help="Debugger commands (JDI Bridge)")
break_app = typer.Typer(help="Breakpoint commands")
app.add_typer(break_app, name="break")


@app.command("ping")
def debug_ping(
    session_id: str = typer.Argument(..., help="Session ID"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Ping the JDI Bridge to verify it starts and responds."""
    client = DaemonClient(timeout=30.0)
    resp = client.request("POST", "/debug/ping", json_body={"session_id": session_id})
    client.close()
    if json_output:
        handle_response(resp, json_output=True)
        return

    data = resp.json()
    if isinstance(data, dict) and isinstance(data.get("bridge"), dict) and data.get("status") == "done":
        bridge = data["bridge"]
        typer.echo(format_json({"status": "pong", "session_id": session_id, **bridge}))
        return

    handle_response(resp, json_output=False)


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


@break_app.command("set")
def debug_break_set(
    class_pattern: str = typer.Argument(..., help="Class pattern (e.g. com.example.MainActivity)"),
    line: int = typer.Argument(..., help="1-based source line number"),
    session_id: str = typer.Option(..., "--session", help="Session ID"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Set a breakpoint by class pattern and line number."""
    client = DaemonClient(timeout=30.0)
    resp = client.request(
        "POST",
        "/debug/breakpoint/set",
        json_body={
            "session_id": session_id,
            "class_pattern": class_pattern,
            "line": line,
        },
    )
    client.close()
    handle_response(resp, json_output=json_output)


@break_app.command("remove")
def debug_break_remove(
    breakpoint_id: int = typer.Argument(..., help="Breakpoint ID"),
    session_id: str = typer.Option(..., "--session", help="Session ID"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Remove a breakpoint by ID."""
    client = DaemonClient(timeout=30.0)
    resp = client.request(
        "POST",
        "/debug/breakpoint/remove",
        json_body={"session_id": session_id, "breakpoint_id": breakpoint_id},
    )
    client.close()
    handle_response(resp, json_output=json_output)


@break_app.command("list")
def debug_break_list(
    session_id: str = typer.Option(..., "--session", help="Session ID"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """List active breakpoints."""
    client = DaemonClient(timeout=30.0)
    resp = client.request("GET", f"/debug/breakpoints?session_id={session_id}")
    client.close()
    handle_response(resp, json_output=json_output)


@app.command("threads")
def debug_threads(
    session_id: str = typer.Option(..., "--session", help="Session ID"),
    include_all: bool = typer.Option(
        False,
        "--all",
        help="Include daemon/internal threads and increase output limit",
    ),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """List debugger-visible VM threads."""
    include_daemon = include_all
    max_threads = 100 if include_all else 20
    client = DaemonClient(timeout=30.0)
    resp = client.request(
        "GET",
        (
            f"/debug/threads?session_id={session_id}"
            f"&include_daemon={str(include_daemon).lower()}"
            f"&max_threads={max_threads}"
        ),
    )
    client.close()
    handle_response(resp, json_output=json_output)


@app.command("events")
def debug_events(
    session_id: str = typer.Option(..., "--session", help="Session ID"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Drain and return queued debugger events."""
    client = DaemonClient(timeout=30.0)
    resp = client.request("GET", f"/debug/events?session_id={session_id}")
    client.close()
    handle_response(resp, json_output=json_output)
