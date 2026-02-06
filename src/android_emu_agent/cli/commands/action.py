"""Action execution CLI commands."""

from __future__ import annotations

import typer

from android_emu_agent.cli.daemon_client import DaemonClient
from android_emu_agent.cli.utils import handle_response

app = typer.Typer(help="Action execution commands")


@app.command("tap")
def action_tap(
    session_id: str = typer.Argument(..., help="Session ID"),
    ref: str = typer.Argument(..., help="Element ref (^a1)"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Tap an element."""
    client = DaemonClient()
    resp = client.request("POST", "/actions/tap", json_body={"session_id": session_id, "ref": ref})
    client.close()
    handle_response(resp, json_output=json_output)


@app.command("long-tap")
def action_long_tap(
    session_id: str = typer.Argument(..., help="Session ID"),
    ref: str = typer.Argument(..., help="Element ref (^a1)"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Long tap an element."""
    client = DaemonClient()
    resp = client.request(
        "POST", "/actions/long_tap", json_body={"session_id": session_id, "ref": ref}
    )
    client.close()
    handle_response(resp, json_output=json_output)


@app.command("set-text")
def action_set_text(
    session_id: str = typer.Argument(..., help="Session ID"),
    ref: str = typer.Argument(..., help="Element ref (^a1)"),
    text: str = typer.Argument(..., help="Text to set"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Set text on an element."""
    client = DaemonClient()
    resp = client.request(
        "POST",
        "/actions/set_text",
        json_body={"session_id": session_id, "ref": ref, "text": text},
    )
    client.close()
    handle_response(resp, json_output=json_output)


@app.command("clear")
def action_clear(
    session_id: str = typer.Argument(..., help="Session ID"),
    ref: str = typer.Argument(..., help="Element ref (^a1)"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Clear text."""
    client = DaemonClient()
    resp = client.request(
        "POST", "/actions/clear", json_body={"session_id": session_id, "ref": ref}
    )
    client.close()
    handle_response(resp, json_output=json_output)


@app.command("back")
def action_back(
    session_id: str = typer.Argument(..., help="Session ID"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Press back."""
    client = DaemonClient()
    resp = client.request("POST", "/actions/back", json_body={"session_id": session_id})
    client.close()
    handle_response(resp, json_output=json_output)


@app.command("home")
def action_home(
    session_id: str = typer.Argument(..., help="Session ID"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Press home."""
    client = DaemonClient()
    resp = client.request("POST", "/actions/home", json_body={"session_id": session_id})
    client.close()
    handle_response(resp, json_output=json_output)


@app.command("recents")
def action_recents(
    session_id: str = typer.Argument(..., help="Session ID"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Press recents."""
    client = DaemonClient()
    resp = client.request("POST", "/actions/recents", json_body={"session_id": session_id})
    client.close()
    handle_response(resp, json_output=json_output)


@app.command("swipe")
def action_swipe(
    direction: str = typer.Argument(..., help="Direction: up, down, left, right"),
    session: str = typer.Option(..., "--session", "-s", help="Session ID"),
    container: str | None = typer.Option(None, "--in", help="Container ^ref or selector"),
    distance: float = typer.Option(0.8, "--distance", "-d", help="Swipe distance (0.0-1.0)"),
    duration: int = typer.Option(300, "--duration", help="Swipe duration in ms"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Perform swipe gesture."""
    client = DaemonClient()
    resp = client.request(
        "POST",
        "/actions/swipe",
        json_body={
            "session_id": session,
            "direction": direction,
            "container": container,
            "distance": distance,
            "duration_ms": duration,
        },
    )
    client.close()
    handle_response(resp, json_output=json_output)


@app.command("scroll")
def action_scroll(
    direction: str = typer.Argument(..., help="Direction: up, down, left, right"),
    session: str = typer.Option(..., "--session", "-s", help="Session ID"),
    container: str | None = typer.Option(None, "--in", help="Container ^ref or selector"),
    distance: float = typer.Option(0.8, "--distance", "-d", help="Scroll distance (0.0-1.0)"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Scroll in a direction (alias for swipe)."""
    client = DaemonClient()
    resp = client.request(
        "POST",
        "/actions/swipe",
        json_body={
            "session_id": session,
            "direction": direction,
            "container": container,
            "distance": distance,
            "duration_ms": 300,
        },
    )
    client.close()
    handle_response(resp, json_output=json_output)
