"""Expectation/assertion CLI commands."""

from __future__ import annotations

import typer

from android_emu_agent.cli.daemon_client import DaemonClient
from android_emu_agent.cli.utils import handle_response

app = typer.Typer(help="Expectation and assertion commands")


def _selector(
    text: str | None,
    text_contains: str | None,
    resource_id: str | None,
    resource_id_matches: str | None,
    desc: str | None,
    desc_contains: str | None,
    class_name: str | None,
) -> dict[str, str] | None:
    selector: dict[str, str] = {}
    if text:
        selector["text"] = text
    if text_contains:
        selector["textContains"] = text_contains
    if resource_id:
        selector["resourceId"] = resource_id
    if resource_id_matches:
        selector["resourceIdMatches"] = resource_id_matches
    if desc:
        selector["description"] = desc
    if desc_contains:
        selector["descriptionContains"] = desc_contains
    if class_name:
        selector["className"] = class_name
    return selector or None


@app.command("idle")
def expect_idle(
    session_id: str = typer.Argument(..., help="Session ID"),
    timeout_ms: int | None = typer.Option(None, "--timeout-ms", help="Timeout in ms"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Assert that the UI becomes idle."""
    client = DaemonClient()
    resp = client.request(
        "POST",
        "/expect/idle",
        json_body={"session_id": session_id, "timeout_ms": timeout_ms},
    )
    client.close()
    handle_response(resp, json_output=json_output)


@app.command("text")
def expect_text(
    session_id: str = typer.Argument(..., help="Session ID"),
    text: str = typer.Argument(..., help="Expected text"),
    timeout_ms: int | None = typer.Option(None, "--timeout-ms", help="Timeout in ms"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Assert that text appears."""
    client = DaemonClient()
    resp = client.request(
        "POST",
        "/expect/text",
        json_body={"session_id": session_id, "text": text, "timeout_ms": timeout_ms},
    )
    client.close()
    handle_response(resp, json_output=json_output)


@app.command("activity")
def expect_activity(
    session_id: str = typer.Argument(..., help="Session ID"),
    activity: str = typer.Argument(..., help="Expected activity substring"),
    timeout_ms: int | None = typer.Option(None, "--timeout-ms", help="Timeout in ms"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Assert that the current activity appears."""
    client = DaemonClient()
    resp = client.request(
        "POST",
        "/expect/activity",
        json_body={"session_id": session_id, "activity": activity, "timeout_ms": timeout_ms},
    )
    client.close()
    handle_response(resp, json_output=json_output)


@app.command("exists")
def expect_exists(
    session_id: str = typer.Argument(..., help="Session ID"),
    ref: str | None = typer.Option(None, "--ref", help="Element ref (^a1)"),
    text: str | None = typer.Option(None, "--text", help="Text selector"),
    text_contains: str | None = typer.Option(None, "--text-contains", help="Text contains selector"),
    resource_id: str | None = typer.Option(None, "--id", help="Resource ID selector"),
    resource_id_matches: str | None = typer.Option(
        None, "--id-matches", help="Resource ID regex selector"
    ),
    desc: str | None = typer.Option(None, "--desc", help="Content-desc selector"),
    desc_contains: str | None = typer.Option(
        None, "--desc-contains", help="Content-desc contains selector"
    ),
    class_name: str | None = typer.Option(None, "--class", help="Class name selector"),
    timeout_ms: int | None = typer.Option(None, "--timeout-ms", help="Timeout in ms"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Assert that an element exists."""
    client = DaemonClient()
    resp = client.request(
        "POST",
        "/expect/exists",
        json_body={
            "session_id": session_id,
            "ref": ref,
            "selector": _selector(
                text,
                text_contains,
                resource_id,
                resource_id_matches,
                desc,
                desc_contains,
                class_name,
            ),
            "timeout_ms": timeout_ms,
        },
    )
    client.close()
    handle_response(resp, json_output=json_output)


@app.command("gone")
def expect_gone(
    session_id: str = typer.Argument(..., help="Session ID"),
    ref: str | None = typer.Option(None, "--ref", help="Element ref (^a1)"),
    text: str | None = typer.Option(None, "--text", help="Text selector"),
    text_contains: str | None = typer.Option(None, "--text-contains", help="Text contains selector"),
    resource_id: str | None = typer.Option(None, "--id", help="Resource ID selector"),
    resource_id_matches: str | None = typer.Option(
        None, "--id-matches", help="Resource ID regex selector"
    ),
    desc: str | None = typer.Option(None, "--desc", help="Content-desc selector"),
    desc_contains: str | None = typer.Option(
        None, "--desc-contains", help="Content-desc contains selector"
    ),
    class_name: str | None = typer.Option(None, "--class", help="Class name selector"),
    timeout_ms: int | None = typer.Option(None, "--timeout-ms", help="Timeout in ms"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Assert that an element is gone."""
    client = DaemonClient()
    resp = client.request(
        "POST",
        "/expect/gone",
        json_body={
            "session_id": session_id,
            "ref": ref,
            "selector": _selector(
                text,
                text_contains,
                resource_id,
                resource_id_matches,
                desc,
                desc_contains,
                class_name,
            ),
            "timeout_ms": timeout_ms,
        },
    )
    client.close()
    handle_response(resp, json_output=json_output)


@app.command("current-app")
def expect_current_app(
    session_id: str = typer.Argument(..., help="Session ID"),
    package: str | None = typer.Option(None, "--package", "-p", help="Expected package"),
    activity: str | None = typer.Option(None, "--activity", "-a", help="Expected activity substring"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Assert the foreground app/activity."""
    client = DaemonClient()
    resp = client.request(
        "POST",
        "/expect/current_app",
        json_body={"session_id": session_id, "package": package, "activity": activity},
    )
    client.close()
    handle_response(resp, json_output=json_output)
