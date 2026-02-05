"""File transfer CLI commands."""

from __future__ import annotations

import typer

from android_emu_agent.cli.daemon_client import DaemonClient
from android_emu_agent.cli.utils import (
    FILE_APP_TRANSFER_TIMEOUT,
    FILE_TRANSFER_TIMEOUT,
    handle_output_response,
    handle_response,
    require_target,
)

app = typer.Typer(help="File transfer commands")
app_private = typer.Typer(help="App-private file operations (rooted/emulator)")
app.add_typer(app_private, name="app")


@app.command("push")
def file_push(
    local_path: str = typer.Argument(..., help="Local file or directory"),
    remote_path: str | None = typer.Option(
        None,
        "--remote",
        help="Remote path (default: /sdcard/Download/<name>)",
    ),
    device: str | None = typer.Option(None, "--device", "-d", help="Device serial"),
    session_id: str | None = typer.Option(None, "--session", "-s", help="Session ID"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Push a local file to shared storage (sdcard)."""
    payload = require_target(device, session_id)
    payload.update({"local_path": local_path, "remote_path": remote_path})
    client = DaemonClient(timeout=FILE_TRANSFER_TIMEOUT)
    resp = client.request("POST", "/files/push", json_body=payload)
    client.close()
    handle_response(resp, json_output=json_output)


@app.command("pull")
def file_pull(
    remote_path: str = typer.Argument(..., help="Remote file or directory"),
    local_path: str | None = typer.Option(None, "--local", help="Local output path"),
    device: str | None = typer.Option(None, "--device", "-d", help="Device serial"),
    session_id: str | None = typer.Option(None, "--session", "-s", help="Session ID"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Pull a file from shared storage (sdcard)."""
    payload = require_target(device, session_id)
    payload.update({"remote_path": remote_path, "local_path": local_path})
    client = DaemonClient(timeout=FILE_TRANSFER_TIMEOUT)
    resp = client.request("POST", "/files/pull", json_body=payload)
    client.close()
    handle_response(resp, json_output=json_output)


@app.command("find")
def file_find(
    path: str = typer.Argument(..., help="Root directory to search"),
    name: str = typer.Option(..., "--name", help="Filename glob (e.g. *.db or cache*)"),
    kind: str = typer.Option("any", "--type", help="file|dir|any"),
    max_depth: int = typer.Option(4, "--max-depth", help="Max directory depth"),
    device: str | None = typer.Option(None, "--device", "-d", help="Device serial"),
    session_id: str | None = typer.Option(None, "--session", "-s", help="Session ID"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Find files/folders and return metadata (rooted/emulator)."""
    payload = require_target(device, session_id)
    payload.update(
        {
            "path": path,
            "name": name,
            "kind": kind,
            "max_depth": max_depth,
        }
    )
    client = DaemonClient(timeout=FILE_TRANSFER_TIMEOUT)
    resp = client.request("POST", "/files/find", json_body=payload)
    client.close()
    handle_output_response(resp, json_output=json_output)


@app.command("list")
def file_list(
    path: str = typer.Argument(..., help="Directory to list"),
    kind: str = typer.Option("any", "--type", help="file|dir|any"),
    device: str | None = typer.Option(None, "--device", "-d", help="Device serial"),
    session_id: str | None = typer.Option(None, "--session", "-s", help="Session ID"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """List files/folders in a directory (rooted/emulator)."""
    payload = require_target(device, session_id)
    payload.update({"path": path, "kind": kind})
    client = DaemonClient(timeout=FILE_TRANSFER_TIMEOUT)
    resp = client.request("POST", "/files/list", json_body=payload)
    client.close()
    handle_output_response(resp, json_output=json_output)


@app_private.command("push")
def file_app_push(
    package: str = typer.Argument(..., help="Package name"),
    local_path: str = typer.Argument(..., help="Local file or directory"),
    remote_path: str | None = typer.Option(
        None,
        "--remote",
        help="App data path (default: files/<name>)",
    ),
    device: str | None = typer.Option(None, "--device", "-d", help="Device serial"),
    session_id: str | None = typer.Option(None, "--session", "-s", help="Session ID"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Push a file into app-private storage (rooted/emulator)."""
    payload = require_target(device, session_id)
    payload.update({"package": package, "local_path": local_path, "remote_path": remote_path})
    client = DaemonClient(timeout=FILE_APP_TRANSFER_TIMEOUT)
    resp = client.request("POST", "/files/app_push", json_body=payload)
    client.close()
    handle_response(resp, json_output=json_output)


@app_private.command("pull")
def file_app_pull(
    package: str = typer.Argument(..., help="Package name"),
    remote_path: str = typer.Argument(..., help="App data path (relative or absolute)"),
    local_path: str | None = typer.Option(None, "--local", help="Local output path"),
    device: str | None = typer.Option(None, "--device", "-d", help="Device serial"),
    session_id: str | None = typer.Option(None, "--session", "-s", help="Session ID"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Pull a file from app-private storage (rooted/emulator)."""
    payload = require_target(device, session_id)
    payload.update({"package": package, "remote_path": remote_path, "local_path": local_path})
    client = DaemonClient(timeout=FILE_APP_TRANSFER_TIMEOUT)
    resp = client.request("POST", "/files/app_pull", json_body=payload)
    client.close()
    handle_response(resp, json_output=json_output)
