"""UI observation CLI commands."""

from __future__ import annotations

import typer

from android_emu_agent.cli.daemon_client import DaemonClient, format_json
from android_emu_agent.cli.utils import (
    handle_response_with_pull,
    require_target,
    resolve_session_id,
)

app = typer.Typer(help="UI observation commands")


def _validate_snapshot_flags(full: bool, raw: bool) -> str:
    """Validate and determine snapshot mode from CLI flags.

    Args:
        full: True if --full flag was provided
        raw: True if --raw flag was provided

    Returns:
        The mode string: "compact", "full", or "raw"

    Raises:
        typer.BadParameter: If both --full and --raw are provided
    """
    if full and raw:
        raise typer.BadParameter("--full and --raw are mutually exclusive")
    if raw:
        return "raw"
    if full:
        return "full"
    return "compact"


@app.command("snapshot")
def ui_snapshot(
    session_id: str = typer.Argument(..., help="Session ID"),
    full: bool = typer.Option(False, "--full", help="Include all nodes (JSON)"),
    raw: bool = typer.Option(False, "--raw", help="Return raw XML hierarchy"),
    format_: str = typer.Option("json", "--format", "-f", help="Output format: json|text"),
) -> None:
    """Take a UI snapshot.

    Modes (mutually exclusive):
    - Default (compact): Interactive elements only, JSON format
    - --full: All elements, JSON format
    - --raw: Original XML hierarchy string
    """
    try:
        mode = _validate_snapshot_flags(full, raw)
    except typer.BadParameter as exc:
        typer.echo(f"Error: {exc}")
        raise typer.Exit(code=1) from None

    client = DaemonClient()
    resp = client.request(
        "POST",
        "/ui/snapshot",
        json_body={"session_id": session_id, "mode": mode},
    )
    client.close()

    content_type = resp.headers.get("content-type", "")
    if "application/xml" in content_type:
        typer.echo(resp.text)
        return

    data = resp.json()
    if format_ == "text" and not data.get("error"):
        elements = data.get("elements", [])
        header = (
            f"session={data.get('session_id')} generation={data.get('generation')} "
            f"elements={len(elements)}"
        )
        typer.echo(header)
        for elem in elements:
            label = elem.get("label") or elem.get("text") or ""
            role = elem.get("role") or "element"
            rid = elem.get("resource_id") or "-"
            typer.echo(f"{elem['ref']} {role} '{label}' id={rid} bounds={elem.get('bounds')}")
        return

    typer.echo(format_json(data))


@app.command("screenshot")
def ui_screenshot(
    session_id: str | None = typer.Argument(None, help="Session ID"),
    device: str | None = typer.Option(None, "--device", "-d", help="Device serial"),
    session: str | None = typer.Option(None, "--session", "-s", help="Session ID"),
    pull: bool = typer.Option(False, "--pull", help="Copy screenshot to local path"),
    output: str | None = typer.Option(
        None, "--output", "-o", help="Output path (file or directory)"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Capture a screenshot."""
    try:
        resolved_session = resolve_session_id(session_id, session)
    except typer.BadParameter as exc:
        typer.echo(f"Error: {exc}")
        raise typer.Exit(code=1) from None

    payload = require_target(device, resolved_session)
    client = DaemonClient()
    resp = client.request("POST", "/ui/screenshot", json_body=payload)
    client.close()
    handle_response_with_pull(resp, json_output=json_output, pull=pull, output=output)
