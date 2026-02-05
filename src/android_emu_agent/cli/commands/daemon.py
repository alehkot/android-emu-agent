"""Daemon lifecycle CLI commands."""

from __future__ import annotations

from typing import Any

import typer

from android_emu_agent.cli.daemon_client import DaemonClient, DaemonController, format_json

app = typer.Typer(help="Daemon lifecycle commands")


@app.command("start")
def daemon_start() -> None:
    """Start the daemon process."""
    controller = DaemonController()
    status = controller.status()
    if status["pid_running"]:
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
    stopped = controller.stop()
    if stopped:
        typer.echo("Daemon stopped")
    else:
        typer.echo("Daemon not running")


@app.command("status")
def daemon_status(json_output: bool = typer.Option(False, "--json", help="Output JSON")) -> None:
    """Show daemon status."""
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
