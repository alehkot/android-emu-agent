"""Android system surface CLI commands."""

from __future__ import annotations

import typer

from android_emu_agent.cli.daemon_client import DaemonClient
from android_emu_agent.cli.utils import handle_output_response, handle_response, require_target

app = typer.Typer(help="Android system surface commands")
notifications_app = typer.Typer(help="Notification shade commands")
quick_settings_app = typer.Typer(help="Quick Settings commands")
permissions_app = typer.Typer(help="Permission commands")

app.add_typer(notifications_app, name="notifications")
app.add_typer(quick_settings_app, name="quick-settings")
app.add_typer(permissions_app, name="permissions")


@notifications_app.command("open")
def system_notifications_open(
    device: str | None = typer.Option(None, "--device", "-d", help="Device serial"),
    session_id: str | None = typer.Option(None, "--session", "-s", help="Session ID"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Open the notification shade."""
    payload = require_target(device, session_id)
    client = DaemonClient()
    resp = client.request("POST", "/system/notifications/open", json_body=payload)
    client.close()
    handle_response(resp, json_output=json_output)


@notifications_app.command("close")
def system_notifications_close(
    device: str | None = typer.Option(None, "--device", "-d", help="Device serial"),
    session_id: str | None = typer.Option(None, "--session", "-s", help="Session ID"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Close the notification shade."""
    payload = require_target(device, session_id)
    client = DaemonClient()
    resp = client.request("POST", "/system/notifications/close", json_body=payload)
    client.close()
    handle_response(resp, json_output=json_output)


@quick_settings_app.command("open")
def system_quick_settings_open(
    device: str | None = typer.Option(None, "--device", "-d", help="Device serial"),
    session_id: str | None = typer.Option(None, "--session", "-s", help="Session ID"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Open Quick Settings."""
    payload = require_target(device, session_id)
    client = DaemonClient()
    resp = client.request("POST", "/system/quick_settings/open", json_body=payload)
    client.close()
    handle_response(resp, json_output=json_output)


@permissions_app.command("list")
def system_permissions_list(
    package: str = typer.Argument(..., help="Package name"),
    device: str | None = typer.Option(None, "--device", "-d", help="Device serial"),
    session_id: str | None = typer.Option(None, "--session", "-s", help="Session ID"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """List requested and granted package permissions."""
    payload = require_target(device, session_id)
    payload["package"] = package
    client = DaemonClient()
    resp = client.request("POST", "/system/permissions/list", json_body=payload)
    client.close()
    handle_output_response(resp, json_output=json_output)


@permissions_app.command("grant")
def system_permissions_grant(
    package: str = typer.Argument(..., help="Package name"),
    permission: str = typer.Argument(..., help="Android permission name"),
    device: str | None = typer.Option(None, "--device", "-d", help="Device serial"),
    session_id: str | None = typer.Option(None, "--session", "-s", help="Session ID"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Grant a runtime permission."""
    payload = require_target(device, session_id)
    payload.update({"package": package, "permission": permission})
    client = DaemonClient()
    resp = client.request("POST", "/system/permissions/grant", json_body=payload)
    client.close()
    handle_response(resp, json_output=json_output)


@permissions_app.command("revoke")
def system_permissions_revoke(
    package: str = typer.Argument(..., help="Package name"),
    permission: str = typer.Argument(..., help="Android permission name"),
    device: str | None = typer.Option(None, "--device", "-d", help="Device serial"),
    session_id: str | None = typer.Option(None, "--session", "-s", help="Session ID"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Revoke a runtime permission."""
    payload = require_target(device, session_id)
    payload.update({"package": package, "permission": permission})
    client = DaemonClient()
    resp = client.request("POST", "/system/permissions/revoke", json_body=payload)
    client.close()
    handle_response(resp, json_output=json_output)
