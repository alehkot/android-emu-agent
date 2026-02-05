"""Device management CLI commands."""

from __future__ import annotations

import typer

from android_emu_agent.cli.daemon_client import DaemonClient, format_json
from android_emu_agent.cli.utils import handle_response

app = typer.Typer(help="Device management commands")
device_set_app = typer.Typer(help="Determinism controls")
app.add_typer(device_set_app, name="set")


@app.command("list")
def device_list(json_output: bool = typer.Option(False, "--json", help="Output JSON")) -> None:
    """List connected devices."""
    client = DaemonClient()
    resp = client.request("GET", "/devices")
    client.close()

    data = resp.json()
    if json_output:
        typer.echo(format_json(data))
        return

    for device in data.get("devices", []):
        typer.echo(
            f"{device['serial']}  model={device['model']} sdk={device['sdk_version']} "
            f"root={device['is_rooted']} emulator={device['is_emulator']}"
        )


@device_set_app.command("animations")
def device_set_animations(
    state: str = typer.Argument(..., help="on|off"),
    device: str = typer.Option(..., "--device", "-d", help="Device serial"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Enable or disable system animations."""
    client = DaemonClient()
    resp = client.request(
        "POST", "/devices/animations", json_body={"serial": device, "state": state}
    )
    client.close()
    handle_response(resp, json_output=json_output)


@device_set_app.command("stay_awake")
def device_set_stay_awake(
    state: str = typer.Argument(..., help="on|off"),
    device: str = typer.Option(..., "--device", "-d", help="Device serial"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Enable or disable stay-awake."""
    client = DaemonClient()
    resp = client.request(
        "POST", "/devices/stay_awake", json_body={"serial": device, "state": state}
    )
    client.close()
    handle_response(resp, json_output=json_output)


@device_set_app.command("rotation")
def device_set_rotation(
    orientation: str = typer.Argument(
        ..., help="portrait|landscape|reverse-portrait|reverse-landscape|auto"
    ),
    device: str = typer.Option(..., "--device", "-d", help="Device serial"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Set screen rotation."""
    client = DaemonClient()
    resp = client.request(
        "POST", "/devices/rotation", json_body={"serial": device, "orientation": orientation}
    )
    client.close()
    handle_response(resp, json_output=json_output)


@device_set_app.command("wifi")
def device_set_wifi(
    state: str = typer.Argument(..., help="on|off"),
    device: str = typer.Option(..., "--device", "-d", help="Device serial"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Enable or disable WiFi."""
    client = DaemonClient()
    enabled = state.lower() == "on"
    resp = client.request("POST", "/devices/wifi", json_body={"serial": device, "enabled": enabled})
    client.close()
    handle_response(resp, json_output=json_output)


@device_set_app.command("mobile")
def device_set_mobile(
    state: str = typer.Argument(..., help="on|off"),
    device: str = typer.Option(..., "--device", "-d", help="Device serial"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Enable or disable mobile data."""
    client = DaemonClient()
    enabled = state.lower() == "on"
    resp = client.request(
        "POST", "/devices/mobile", json_body={"serial": device, "enabled": enabled}
    )
    client.close()
    handle_response(resp, json_output=json_output)


@device_set_app.command("doze")
def device_set_doze(
    state: str = typer.Argument(..., help="on|off"),
    device: str = typer.Option(..., "--device", "-d", help="Device serial"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Force device into or out of doze mode."""
    client = DaemonClient()
    enabled = state.lower() == "on"
    resp = client.request("POST", "/devices/doze", json_body={"serial": device, "enabled": enabled})
    client.close()
    handle_response(resp, json_output=json_output)
