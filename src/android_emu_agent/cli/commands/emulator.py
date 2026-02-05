"""Emulator management CLI commands."""

from __future__ import annotations

import typer

from android_emu_agent.cli.daemon_client import DaemonClient
from android_emu_agent.cli.utils import handle_response

app = typer.Typer(help="Emulator management commands")
snapshot_app = typer.Typer(help="Emulator snapshot commands")
app.add_typer(snapshot_app, name="snapshot")


@snapshot_app.command("save")
def emulator_snapshot_save(
    serial: str = typer.Argument(..., help="Emulator serial (e.g., emulator-5554)"),
    name: str = typer.Argument(..., help="Snapshot name"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Save emulator snapshot."""
    client = DaemonClient()
    resp = client.request(
        "POST",
        "/emulator/snapshot_save",
        json_body={"serial": serial, "name": name},
    )
    client.close()
    handle_response(resp, json_output=json_output)


@snapshot_app.command("restore")
def emulator_snapshot_restore(
    serial: str = typer.Argument(..., help="Emulator serial (e.g., emulator-5554)"),
    name: str = typer.Argument(..., help="Snapshot name"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Restore emulator snapshot."""
    client = DaemonClient()
    resp = client.request(
        "POST",
        "/emulator/snapshot_restore",
        json_body={"serial": serial, "name": name},
    )
    client.close()
    handle_response(resp, json_output=json_output)
