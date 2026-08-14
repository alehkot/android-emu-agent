"""Daemon lifecycle CLI commands."""

from __future__ import annotations

from typing import Any

import typer

from android_emu_agent.cli.daemon_client import DaemonClient, DaemonController, format_json
from android_emu_agent.errors import daemon_identity_error

app = typer.Typer(help="Daemon lifecycle commands")


@app.command("start")
def daemon_start() -> None:
    """Start the daemon process.

    Start this before any device, session, ui, action, app, or file command. The daemon owns
    device connections and session state.

    Examples:

    ```bash
    # Start the daemon, then confirm it is healthy
    android-emu-agent daemon start
    android-emu-agent daemon status --json
    ```
    """
    controller = DaemonController()
    status = controller.status()
    if status["pid_matches_daemon"]:
        typer.echo(f"Daemon already running (pid {status['pid']})")
        return
    if controller.health():
        typer.echo("Daemon already running (pid unknown)")
        return
    pid = controller.start()
    if pid == -1:
        typer.echo("Daemon already running (pid unknown)")
        return
    typer.echo(f"Daemon started (pid {pid})")


@app.command("stop")
def daemon_stop() -> None:
    """Stop the daemon process."""
    controller = DaemonController()
    status = controller.status()
    if status["pid_running"] and not status["pid_matches_daemon"]:
        error = daemon_identity_error(status["pid"])
        typer.echo(str(error), err=True)
        typer.echo(f"Remediation: {error.remediation}", err=True)
        raise typer.Exit(code=1)
    stopped = controller.stop()
    if stopped:
        typer.echo("Daemon stopped")
    else:
        typer.echo("Daemon not running")


@app.command("status")
def daemon_status(json_output: bool = typer.Option(False, "--json", help="Output JSON")) -> None:
    """Show daemon status.

    Reports whether the daemon is running, which process owns the socket, and the daemon's
    version. Check the version when a source checkout and an installed release are both in use.

    Examples:

    ```bash
    # Human-readable status
    android-emu-agent daemon status

    # Machine-readable status, including health.version
    android-emu-agent daemon status --json
    ```
    """
    controller = DaemonController()
    status = controller.status()

    health: dict[str, Any] | None = None
    try:
        client = DaemonClient(auto_start=False)
        resp = client.request("GET", "/health")
        health = resp.json()
        client.close()
    except Exception:
        health = None

    status["health"] = health
    if json_output:
        typer.echo(format_json(status))
    else:
        typer.echo(format_json(status))
