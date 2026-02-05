"""Reliability and forensics CLI commands."""

from __future__ import annotations

import typer

from android_emu_agent.cli.daemon_client import DaemonClient
from android_emu_agent.cli.utils import (
    RELIABILITY_BUGREPORT_TIMEOUT,
    RELIABILITY_DUMPHEAP_TIMEOUT,
    RELIABILITY_PULL_TIMEOUT,
    RELIABILITY_TIMEOUT,
    handle_output_response,
    handle_response,
    require_target,
)

app = typer.Typer(help="Reliability and forensics commands")
dropbox_app = typer.Typer(help="DropBoxManager commands")
pull_app = typer.Typer(help="Pull protected artifacts (rooted/emulator)")
app.add_typer(dropbox_app, name="dropbox")
app.add_typer(pull_app, name="pull")


@app.command("exit-info")
def reliability_exit_info(
    package: str = typer.Argument(..., help="Package name"),
    device: str | None = typer.Option(None, "--device", "-d", help="Device serial"),
    session_id: str | None = typer.Option(None, "--session", "-s", help="Session ID"),
    list_only: bool = typer.Option(False, "--list", help="List exit-info entries only"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Show ApplicationExitInfo for a package."""
    payload = require_target(device, session_id)
    payload.update({"package": package, "list_only": list_only})
    client = DaemonClient(timeout=RELIABILITY_TIMEOUT)
    resp = client.request("POST", "/reliability/exit_info", json_body=payload)
    client.close()
    handle_output_response(resp, json_output=json_output)


@app.command("bugreport")
def reliability_bugreport(
    device: str | None = typer.Option(None, "--device", "-d", help="Device serial"),
    session_id: str | None = typer.Option(None, "--session", "-s", help="Session ID"),
    output: str | None = typer.Option(None, "--output", help="Output filename (.zip)"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Capture a system bugreport."""
    payload = require_target(device, session_id)
    payload.update({"filename": output})
    client = DaemonClient(timeout=RELIABILITY_BUGREPORT_TIMEOUT)
    resp = client.request("POST", "/reliability/bugreport", json_body=payload)
    client.close()
    handle_response(resp, json_output=json_output)


@app.command("events")
def reliability_events(
    device: str | None = typer.Option(None, "--device", "-d", help="Device serial"),
    session_id: str | None = typer.Option(None, "--session", "-s", help="Session ID"),
    pattern: str | None = typer.Option(None, "--pattern", help="Regex filter for events"),
    package: str | None = typer.Option(None, "--package", help="Filter for package name"),
    since: str | None = typer.Option(None, "--since", help="Logcat -t value"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Dump ActivityManager events log."""
    payload = require_target(device, session_id)
    payload.update({"pattern": pattern, "package": package, "since": since})
    client = DaemonClient(timeout=RELIABILITY_TIMEOUT)
    resp = client.request("POST", "/reliability/events", json_body=payload)
    client.close()
    handle_output_response(resp, json_output=json_output)


@dropbox_app.command("list")
def reliability_dropbox_list(
    device: str | None = typer.Option(None, "--device", "-d", help="Device serial"),
    session_id: str | None = typer.Option(None, "--session", "-s", help="Session ID"),
    package: str | None = typer.Option(None, "--package", help="Filter for package name"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """List DropBoxManager entries."""
    payload = require_target(device, session_id)
    payload.update({"package": package})
    client = DaemonClient(timeout=RELIABILITY_TIMEOUT)
    resp = client.request("POST", "/reliability/dropbox_list", json_body=payload)
    client.close()
    handle_output_response(resp, json_output=json_output)


@dropbox_app.command("print")
def reliability_dropbox_print(
    tag: str = typer.Argument(..., help="DropBox tag (e.g., data_app_crash)"),
    device: str | None = typer.Option(None, "--device", "-d", help="Device serial"),
    session_id: str | None = typer.Option(None, "--session", "-s", help="Session ID"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Print a DropBoxManager entry."""
    payload = require_target(device, session_id)
    payload.update({"tag": tag})
    client = DaemonClient(timeout=RELIABILITY_TIMEOUT)
    resp = client.request("POST", "/reliability/dropbox_print", json_body=payload)
    client.close()
    handle_output_response(resp, json_output=json_output)


@app.command("background")
def reliability_background(
    package: str = typer.Argument(..., help="Package name"),
    device: str | None = typer.Option(None, "--device", "-d", help="Device serial"),
    session_id: str | None = typer.Option(None, "--session", "-s", help="Session ID"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Check background restrictions and standby bucket."""
    payload = require_target(device, session_id)
    payload.update({"package": package})
    client = DaemonClient(timeout=RELIABILITY_TIMEOUT)
    resp = client.request("POST", "/reliability/background", json_body=payload)
    client.close()
    handle_output_response(resp, json_output=json_output)


@app.command("last-anr")
def reliability_last_anr(
    device: str | None = typer.Option(None, "--device", "-d", help="Device serial"),
    session_id: str | None = typer.Option(None, "--session", "-s", help="Session ID"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Show the last ANR summary from ActivityManager."""
    payload = require_target(device, session_id)
    client = DaemonClient(timeout=RELIABILITY_TIMEOUT)
    resp = client.request("POST", "/reliability/last_anr", json_body=payload)
    client.close()
    handle_output_response(resp, json_output=json_output)


@app.command("jobscheduler")
def reliability_jobscheduler(
    package: str = typer.Argument(..., help="Package name"),
    device: str | None = typer.Option(None, "--device", "-d", help="Device serial"),
    session_id: str | None = typer.Option(None, "--session", "-s", help="Session ID"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Inspect JobScheduler constraints for a package."""
    payload = require_target(device, session_id)
    payload.update({"package": package})
    client = DaemonClient(timeout=RELIABILITY_TIMEOUT)
    resp = client.request("POST", "/reliability/jobscheduler", json_body=payload)
    client.close()
    handle_output_response(resp, json_output=json_output)


@app.command("compile")
def reliability_compile(
    package: str = typer.Argument(..., help="Package name"),
    mode: str = typer.Option("reset", "--mode", help="reset|speed"),
    device: str | None = typer.Option(None, "--device", "-d", help="Device serial"),
    session_id: str | None = typer.Option(None, "--session", "-s", help="Session ID"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Reset or force package compilation."""
    payload = require_target(device, session_id)
    payload.update({"package": package, "mode": mode})
    client = DaemonClient(timeout=RELIABILITY_TIMEOUT)
    resp = client.request("POST", "/reliability/compile", json_body=payload)
    client.close()
    handle_output_response(resp, json_output=json_output)


@app.command("always-finish")
def reliability_always_finish(
    state: str = typer.Argument(..., help="on|off"),
    device: str | None = typer.Option(None, "--device", "-d", help="Device serial"),
    session_id: str | None = typer.Option(None, "--session", "-s", help="Session ID"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Toggle always-finish-activities developer setting."""
    payload = require_target(device, session_id)
    payload.update({"state": state})
    client = DaemonClient(timeout=RELIABILITY_TIMEOUT)
    resp = client.request("POST", "/reliability/always_finish", json_body=payload)
    client.close()
    handle_response(resp, json_output=json_output)


@app.command("run-as-ls")
def reliability_run_as_ls(
    package: str = typer.Argument(..., help="Package name"),
    path: str = typer.Option("files/", "--path", help="Relative path under app data"),
    device: str | None = typer.Option(None, "--device", "-d", help="Device serial"),
    session_id: str | None = typer.Option(None, "--session", "-s", help="Session ID"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """List app-private files for debuggable apps using run-as."""
    payload = require_target(device, session_id)
    payload.update({"package": package, "path": path})
    client = DaemonClient(timeout=RELIABILITY_TIMEOUT)
    resp = client.request("POST", "/reliability/run_as_ls", json_body=payload)
    client.close()
    handle_output_response(resp, json_output=json_output)


@app.command("dumpheap")
def reliability_dumpheap(
    package: str = typer.Argument(..., help="Package name"),
    keep_remote: bool = typer.Option(False, "--keep-remote", help="Keep heap on device"),
    device: str | None = typer.Option(None, "--device", "-d", help="Device serial"),
    session_id: str | None = typer.Option(None, "--session", "-s", help="Session ID"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Dump a heap profile and pull it locally."""
    payload = require_target(device, session_id)
    payload.update({"package": package, "keep_remote": keep_remote})
    client = DaemonClient(timeout=RELIABILITY_DUMPHEAP_TIMEOUT)
    resp = client.request("POST", "/reliability/dumpheap", json_body=payload)
    client.close()
    handle_response(resp, json_output=json_output)


@app.command("sigquit")
def reliability_sigquit(
    package: str = typer.Argument(..., help="Package name"),
    device: str | None = typer.Option(None, "--device", "-d", help="Device serial"),
    session_id: str | None = typer.Option(None, "--session", "-s", help="Session ID"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Send SIGQUIT to dump thread stacks."""
    payload = require_target(device, session_id)
    payload.update({"package": package})
    client = DaemonClient(timeout=RELIABILITY_TIMEOUT)
    resp = client.request("POST", "/reliability/sigquit", json_body=payload)
    client.close()
    handle_response(resp, json_output=json_output)


@app.command("oom-adj")
def reliability_oom_adj(
    package: str = typer.Argument(..., help="Package name"),
    score: int = typer.Option(1000, "--score", help="oom_score_adj value"),
    device: str | None = typer.Option(None, "--device", "-d", help="Device serial"),
    session_id: str | None = typer.Option(None, "--session", "-s", help="Session ID"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Adjust oom_score_adj to make a process more killable (root required)."""
    payload = require_target(device, session_id)
    payload.update({"package": package, "score": score})
    client = DaemonClient(timeout=RELIABILITY_TIMEOUT)
    resp = client.request("POST", "/reliability/oom_adj", json_body=payload)
    client.close()
    handle_response(resp, json_output=json_output)


@app.command("trim-memory")
def reliability_trim_memory(
    package: str = typer.Argument(..., help="Package name"),
    level: str = typer.Option("RUNNING_CRITICAL", "--level", help="Trim level constant"),
    device: str | None = typer.Option(None, "--device", "-d", help="Device serial"),
    session_id: str | None = typer.Option(None, "--session", "-s", help="Session ID"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Send a trim memory signal to the app."""
    payload = require_target(device, session_id)
    payload.update({"package": package, "level": level})
    client = DaemonClient(timeout=RELIABILITY_TIMEOUT)
    resp = client.request("POST", "/reliability/trim_memory", json_body=payload)
    client.close()
    handle_output_response(resp, json_output=json_output)


@pull_app.command("anr")
def reliability_pull_anr(
    device: str | None = typer.Option(None, "--device", "-d", help="Device serial"),
    session_id: str | None = typer.Option(None, "--session", "-s", help="Session ID"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Pull /data/anr (root required)."""
    payload = require_target(device, session_id)
    client = DaemonClient(timeout=RELIABILITY_PULL_TIMEOUT)
    resp = client.request("POST", "/reliability/pull_anr", json_body=payload)
    client.close()
    handle_response(resp, json_output=json_output)


@pull_app.command("tombstones")
def reliability_pull_tombstones(
    device: str | None = typer.Option(None, "--device", "-d", help="Device serial"),
    session_id: str | None = typer.Option(None, "--session", "-s", help="Session ID"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Pull /data/tombstones (root required)."""
    payload = require_target(device, session_id)
    client = DaemonClient(timeout=RELIABILITY_PULL_TIMEOUT)
    resp = client.request("POST", "/reliability/pull_tombstones", json_body=payload)
    client.close()
    handle_response(resp, json_output=json_output)


@pull_app.command("dropbox")
def reliability_pull_dropbox(
    device: str | None = typer.Option(None, "--device", "-d", help="Device serial"),
    session_id: str | None = typer.Option(None, "--session", "-s", help="Session ID"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Pull /data/system/dropbox (root required)."""
    payload = require_target(device, session_id)
    client = DaemonClient(timeout=RELIABILITY_PULL_TIMEOUT)
    resp = client.request("POST", "/reliability/pull_dropbox", json_body=payload)
    client.close()
    handle_response(resp, json_output=json_output)
