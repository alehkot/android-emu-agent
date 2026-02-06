"""Wait/synchronization CLI commands."""

from __future__ import annotations

import typer

from android_emu_agent.cli.daemon_client import DaemonClient
from android_emu_agent.cli.utils import handle_response

app = typer.Typer(help="Wait/synchronization commands")


def _build_selector(
    text: str | None, resource_id: str | None, desc: str | None
) -> dict[str, str] | None:
    selector: dict[str, str] = {}
    if text:
        selector["text"] = text
    if resource_id:
        selector["resourceId"] = resource_id
    if desc:
        selector["description"] = desc
    return selector or None


@app.command("idle")
def wait_idle(
    session_id: str = typer.Argument(..., help="Session ID"),
    timeout_ms: int | None = typer.Option(None, "--timeout-ms", help="Timeout in ms"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Wait for UI idle."""
    client = DaemonClient()
    resp = client.request(
        "POST",
        "/wait/idle",
        json_body={"session_id": session_id, "timeout_ms": timeout_ms},
    )
    client.close()
    handle_response(resp, json_output=json_output)


@app.command("activity")
def wait_activity(
    session_id: str = typer.Argument(..., help="Session ID"),
    activity: str = typer.Argument(..., help="Activity substring"),
    timeout_ms: int | None = typer.Option(None, "--timeout-ms", help="Timeout in ms"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Wait for an activity to appear."""
    client = DaemonClient()
    resp = client.request(
        "POST",
        "/wait/activity",
        json_body={"session_id": session_id, "activity": activity, "timeout_ms": timeout_ms},
    )
    client.close()
    handle_response(resp, json_output=json_output)


@app.command("text")
def wait_text(
    session_id: str = typer.Argument(..., help="Session ID"),
    text: str = typer.Argument(..., help="Text to wait for"),
    timeout_ms: int | None = typer.Option(None, "--timeout-ms", help="Timeout in ms"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Wait for text to appear."""
    client = DaemonClient()
    resp = client.request(
        "POST",
        "/wait/text",
        json_body={"session_id": session_id, "text": text, "timeout_ms": timeout_ms},
    )
    client.close()
    handle_response(resp, json_output=json_output)


@app.command("exists")
def wait_exists(
    session_id: str = typer.Argument(..., help="Session ID"),
    ref: str | None = typer.Option(None, "--ref", help="Element ref (^a1)"),
    text: str | None = typer.Option(None, "--text", help="Text selector"),
    resource_id: str | None = typer.Option(None, "--id", help="Resource ID selector"),
    desc: str | None = typer.Option(None, "--desc", help="Content-desc selector"),
    timeout_ms: int | None = typer.Option(None, "--timeout-ms", help="Timeout in ms"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Wait for element to exist."""
    selector = _build_selector(text, resource_id, desc)

    client = DaemonClient()
    resp = client.request(
        "POST",
        "/wait/exists",
        json_body={
            "session_id": session_id,
            "ref": ref,
            "selector": selector,
            "timeout_ms": timeout_ms,
        },
    )
    client.close()
    handle_response(resp, json_output=json_output)


@app.command("gone")
def wait_gone(
    session_id: str = typer.Argument(..., help="Session ID"),
    ref: str | None = typer.Option(None, "--ref", help="Element ref (^a1)"),
    text: str | None = typer.Option(None, "--text", help="Text selector"),
    resource_id: str | None = typer.Option(None, "--id", help="Resource ID selector"),
    desc: str | None = typer.Option(None, "--desc", help="Content-desc selector"),
    timeout_ms: int | None = typer.Option(None, "--timeout-ms", help="Timeout in ms"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Wait for element to disappear."""
    selector = _build_selector(text, resource_id, desc)

    client = DaemonClient()
    resp = client.request(
        "POST",
        "/wait/gone",
        json_body={
            "session_id": session_id,
            "ref": ref,
            "selector": selector,
            "timeout_ms": timeout_ms,
        },
    )
    client.close()
    handle_response(resp, json_output=json_output)
