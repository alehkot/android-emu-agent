"""Emulator management CLI commands."""

from __future__ import annotations

import typer

from android_emu_agent.cli.daemon_client import DaemonClient
from android_emu_agent.cli.utils import (
    EMULATOR_RESTORE_TIMEOUT,
    EMULATOR_START_TIMEOUT,
    EMULATOR_STOP_TIMEOUT,
    handle_output_response,
    handle_response,
)

app = typer.Typer(help="Emulator management commands")
snapshot_app = typer.Typer(help="Emulator snapshot commands")
app.add_typer(snapshot_app, name="snapshot")


@app.command("list-avds")
def emulator_list_avds(
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """List available Android Virtual Devices."""
    client = DaemonClient()
    resp = client.request("GET", "/emulator/avds")
    client.close()
    handle_output_response(resp, json_output=json_output)


@app.command("start")
def emulator_start(
    avd_name: str = typer.Argument(..., help="AVD name from 'emulator -list-avds'"),
    snapshot: str | None = typer.Option(None, "--snapshot", help="Snapshot name to load on boot"),
    wipe_data: bool = typer.Option(False, "--wipe-data", help="Wipe userdata before boot"),
    cold_boot: bool = typer.Option(
        False,
        "--cold-boot",
        help="Start without loading Quick Boot or snapshot state",
    ),
    no_snapshot_save: bool = typer.Option(
        False,
        "--no-snapshot-save",
        help="Do not save Quick Boot state on exit",
    ),
    read_only: bool = typer.Option(False, "--read-only", help="Start the AVD in read-only mode"),
    no_window: bool = typer.Option(False, "--no-window", help="Run the emulator headless"),
    port: int | None = typer.Option(
        None,
        "--port",
        help="Console port to use for the emulator instance",
    ),
    wait_boot: bool = typer.Option(
        True,
        "--wait-boot/--no-wait-boot",
        help="Wait for boot before returning",
    ),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Start an AVD using the Android emulator CLI."""
    client = DaemonClient(timeout=EMULATOR_START_TIMEOUT if wait_boot else 10.0)
    resp = client.request(
        "POST",
        "/emulator/start",
        json_body={
            "avd_name": avd_name,
            "snapshot": snapshot,
            "wipe_data": wipe_data,
            "cold_boot": cold_boot,
            "no_snapshot_save": no_snapshot_save,
            "read_only": read_only,
            "no_window": no_window,
            "port": port,
            "wait_boot": wait_boot,
        },
    )
    client.close()
    handle_output_response(resp, json_output=json_output)


@app.command("stop")
def emulator_stop(
    serial: str = typer.Argument(..., help="Running emulator serial (e.g., emulator-5554)"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Stop a running emulator instance."""
    client = DaemonClient(timeout=EMULATOR_STOP_TIMEOUT)
    resp = client.request(
        "POST",
        "/emulator/stop",
        json_body={"serial": serial},
    )
    client.close()
    handle_output_response(resp, json_output=json_output)


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
    restart: bool = typer.Option(
        True,
        "--restart/--no-restart",
        help="Restart after loading the snapshot",
    ),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Restore emulator snapshot and restart by default."""
    client = DaemonClient(timeout=EMULATOR_RESTORE_TIMEOUT if restart else 10.0)
    resp = client.request(
        "POST",
        "/emulator/snapshot_restore",
        json_body={"serial": serial, "name": name, "restart": restart},
    )
    client.close()
    handle_response(resp, json_output=json_output)
