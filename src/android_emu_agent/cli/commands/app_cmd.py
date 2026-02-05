"""App management CLI commands."""

from __future__ import annotations

import typer

from android_emu_agent.cli.daemon_client import DaemonClient
from android_emu_agent.cli.utils import handle_output_response, handle_response, require_target

app = typer.Typer(help="App management commands")


@app.command("reset")
def app_reset(
    session_id: str = typer.Argument(..., help="Session ID"),
    package: str = typer.Argument(..., help="Package name"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Clear app data for a package."""
    client = DaemonClient()
    resp = client.request(
        "POST",
        "/app/reset",
        json_body={"session_id": session_id, "package": package},
    )
    client.close()
    handle_response(resp, json_output=json_output)


@app.command("launch")
def app_launch(
    session_id: str = typer.Argument(..., help="Session ID"),
    package: str = typer.Argument(..., help="Package name"),
    activity: str | None = typer.Option(None, "--activity", "-a", help="Activity name"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Launch an app."""
    client = DaemonClient()
    resp = client.request(
        "POST",
        "/app/launch",
        json_body={"session_id": session_id, "package": package, "activity": activity},
    )
    client.close()
    handle_response(resp, json_output=json_output)


@app.command("force-stop")
def app_force_stop(
    session_id: str = typer.Argument(..., help="Session ID"),
    package: str = typer.Argument(..., help="Package name"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Force stop an app."""
    client = DaemonClient()
    resp = client.request(
        "POST",
        "/app/force_stop",
        json_body={"session_id": session_id, "package": package},
    )
    client.close()
    handle_response(resp, json_output=json_output)


@app.command("deeplink")
def app_deeplink(
    session_id: str = typer.Argument(..., help="Session ID"),
    uri: str = typer.Argument(..., help="URI to open"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Open a deeplink URI."""
    client = DaemonClient()
    resp = client.request(
        "POST",
        "/app/deeplink",
        json_body={"session_id": session_id, "uri": uri},
    )
    client.close()
    handle_response(resp, json_output=json_output)


@app.command("list")
def app_list(
    device: str | None = typer.Option(None, "--device", "-d", help="Device serial"),
    session_id: str | None = typer.Option(None, "--session", "-s", help="Session ID"),
    scope: str = typer.Option("all", "--scope", help="all|system|third-party"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """List installed packages."""
    payload = require_target(device, session_id)
    payload.update({"scope": scope})
    client = DaemonClient()
    resp = client.request("POST", "/app/list", json_body=payload)
    client.close()
    handle_output_response(resp, json_output=json_output)
