"""Debugger CLI commands."""

from __future__ import annotations

from urllib.parse import urlencode

import typer

from android_emu_agent.cli.daemon_client import DaemonClient, format_json
from android_emu_agent.cli.utils import handle_response

app = typer.Typer(help="Debugger commands (JDI Bridge)")
break_app = typer.Typer(help="Breakpoint commands")
break_exception_app = typer.Typer(help="Exception breakpoint commands")
mapping_app = typer.Typer(help="ProGuard/R8 mapping commands")
app.add_typer(break_app, name="break")
app.add_typer(break_exception_app, name="break-exception")
app.add_typer(mapping_app, name="mapping")


@app.command("ping")
def debug_ping(
    session_id: str = typer.Argument(..., help="Session ID"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Ping the JDI Bridge to verify it starts and responds."""
    client = DaemonClient(timeout=30.0)
    resp = client.request("POST", "/debug/ping", json_body={"session_id": session_id})
    client.close()
    if json_output:
        handle_response(resp, json_output=True)
        return

    data = resp.json()
    if (
        isinstance(data, dict)
        and isinstance(data.get("bridge"), dict)
        and data.get("status") == "done"
    ):
        bridge = data["bridge"]
        typer.echo(format_json({"status": "pong", "session_id": session_id, **bridge}))
        return

    handle_response(resp, json_output=False)


@app.command("attach")
def debug_attach(
    session_id: str = typer.Option(..., "--session", help="Session ID"),
    package: str = typer.Option(..., "--package", help="App package name"),
    process: str | None = typer.Option(
        None,
        "--process",
        help="Optional process name (e.g. com.example.app:remote) when multiple are debuggable",
    ),
    keep_suspended: bool = typer.Option(
        False,
        "--keep-suspended",
        help="Do not auto-resume a fully suspended VM on attach",
    ),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Attach the debugger to a running app's JVM."""
    client = DaemonClient(timeout=30.0)
    resp = client.request(
        "POST",
        "/debug/attach",
        json_body={
            "session_id": session_id,
            "package": package,
            "process": process,
            "keep_suspended": keep_suspended,
        },
    )
    client.close()
    handle_response(resp, json_output=json_output)


@app.command("detach")
def debug_detach(
    session_id: str = typer.Option(..., "--session", help="Session ID"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Detach the debugger from a session."""
    client = DaemonClient(timeout=30.0)
    resp = client.request(
        "POST",
        "/debug/detach",
        json_body={"session_id": session_id},
    )
    client.close()
    handle_response(resp, json_output=json_output)


@app.command("status")
def debug_status(
    session_id: str = typer.Option(..., "--session", help="Session ID"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Get the debug session status."""
    client = DaemonClient(timeout=30.0)
    resp = client.request("GET", f"/debug/status/{session_id}")
    client.close()
    handle_response(resp, json_output=json_output)


@break_app.command("set")
def debug_break_set(
    class_pattern: str = typer.Argument(..., help="Class pattern (e.g. com.example.MainActivity)"),
    line: int = typer.Argument(..., help="1-based source line number"),
    session_id: str = typer.Option(..., "--session", help="Session ID"),
    condition: str | None = typer.Option(None, "--condition", help="Condition expression"),
    log_message: str | None = typer.Option(
        None,
        "--log-message",
        help="Log message template with {expr} placeholders (non-suspending logpoint)",
    ),
    capture_stack: bool = typer.Option(
        False,
        "--capture-stack",
        help="Capture stack on logpoint hit",
    ),
    stack_max_frames: int = typer.Option(
        8,
        "--stack-max-frames",
        min=1,
        help="Frames to capture per logpoint hit",
    ),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Set a breakpoint by class pattern and line number."""
    client = DaemonClient(timeout=30.0)
    body: dict[str, object] = {
        "session_id": session_id,
        "class_pattern": class_pattern,
        "line": line,
    }
    if condition is not None:
        body["condition"] = condition
    if log_message is not None:
        body["log_message"] = log_message
    capture_stack_enabled = capture_stack if isinstance(capture_stack, bool) else False
    resolved_stack_max_frames = stack_max_frames if isinstance(stack_max_frames, int) else 8
    if capture_stack_enabled:
        body["capture_stack"] = True
        body["stack_max_frames"] = resolved_stack_max_frames
    resp = client.request(
        "POST",
        "/debug/breakpoint/set",
        json_body=body,
    )
    client.close()
    handle_response(resp, json_output=json_output)


@break_app.command("remove")
def debug_break_remove(
    breakpoint_id: int = typer.Argument(..., help="Breakpoint ID"),
    session_id: str = typer.Option(..., "--session", help="Session ID"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Remove a breakpoint by ID."""
    client = DaemonClient(timeout=30.0)
    resp = client.request(
        "POST",
        "/debug/breakpoint/remove",
        json_body={"session_id": session_id, "breakpoint_id": breakpoint_id},
    )
    client.close()
    handle_response(resp, json_output=json_output)


@break_app.command("list")
def debug_break_list(
    session_id: str = typer.Option(..., "--session", help="Session ID"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """List active breakpoints."""
    client = DaemonClient(timeout=30.0)
    resp = client.request("GET", f"/debug/breakpoints?session_id={session_id}")
    client.close()
    handle_response(resp, json_output=json_output)


@break_app.command("hits")
def debug_break_hits(
    session_id: str = typer.Option(..., "--session", help="Session ID"),
    breakpoint_id: int | None = typer.Option(
        None,
        "--breakpoint-id",
        help="Optional breakpoint ID filter",
    ),
    limit: int = typer.Option(100, "--limit", help="Maximum buffered hits to return"),
    since: str | None = typer.Option(
        None,
        "--since",
        help="Lower-bound timestamp (epoch ms, ISO 8601, or relative e.g. '10m ago')",
    ),
    since_timestamp_ms: int | None = typer.Option(
        None,
        "--since-timestamp-ms",
        help="Deprecated: Use --since instead",
        hidden=True,
    ),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """List buffered non-suspending breakpoint hits."""
    query_params: dict[str, int | str] = {"session_id": session_id, "limit": limit}
    if breakpoint_id is not None:
        query_params["breakpoint_id"] = breakpoint_id

    val_since = since if since is not None else since_timestamp_ms
    if val_since is not None:
        query_params["since_timestamp_ms"] = val_since

    client = DaemonClient(timeout=30.0)
    resp = client.request("GET", f"/debug/logpoint_hits?{urlencode(query_params)}")
    client.close()
    handle_response(resp, json_output=json_output)


@break_exception_app.command("set")
def debug_break_exception_set(
    session_id: str = typer.Option(..., "--session", help="Session ID"),
    class_pattern: str = typer.Option(
        "*",
        "--class",
        help="Exception class pattern or '*' for all",
    ),
    caught: bool = typer.Option(True, "--caught/--no-caught", help="Break on caught exceptions"),
    uncaught: bool = typer.Option(
        True, "--uncaught/--no-uncaught", help="Break on uncaught exceptions"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Set an exception breakpoint by class pattern."""
    client = DaemonClient(timeout=30.0)
    resp = client.request(
        "POST",
        "/debug/exception_breakpoint/set",
        json_body={
            "session_id": session_id,
            "class_pattern": class_pattern,
            "caught": caught,
            "uncaught": uncaught,
        },
    )
    client.close()
    handle_response(resp, json_output=json_output)


@break_exception_app.command("remove")
def debug_break_exception_remove(
    breakpoint_id: int = typer.Argument(..., help="Exception breakpoint ID"),
    session_id: str = typer.Option(..., "--session", help="Session ID"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Remove an exception breakpoint by ID."""
    client = DaemonClient(timeout=30.0)
    resp = client.request(
        "POST",
        "/debug/exception_breakpoint/remove",
        json_body={"session_id": session_id, "breakpoint_id": breakpoint_id},
    )
    client.close()
    handle_response(resp, json_output=json_output)


@break_exception_app.command("list")
def debug_break_exception_list(
    session_id: str = typer.Option(..., "--session", help="Session ID"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """List active exception breakpoints."""
    client = DaemonClient(timeout=30.0)
    resp = client.request("GET", f"/debug/exception_breakpoints?session_id={session_id}")
    client.close()
    handle_response(resp, json_output=json_output)


@app.command("threads")
def debug_threads(
    session_id: str = typer.Option(..., "--session", help="Session ID"),
    include_all: bool = typer.Option(
        False,
        "--all",
        help="Include daemon/internal threads and increase output limit",
    ),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """List debugger-visible VM threads."""
    include_daemon = include_all
    max_threads = 100 if include_all else 20
    client = DaemonClient(timeout=30.0)
    resp = client.request(
        "GET",
        (
            f"/debug/threads?session_id={session_id}"
            f"&include_daemon={str(include_daemon).lower()}"
            f"&max_threads={max_threads}"
        ),
    )
    client.close()
    handle_response(resp, json_output=json_output)


@app.command("events")
def debug_events(
    session_id: str = typer.Option(..., "--session", help="Session ID"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Drain and return queued debugger events."""
    client = DaemonClient(timeout=30.0)
    resp = client.request("GET", f"/debug/events?session_id={session_id}")
    client.close()
    handle_response(resp, json_output=json_output)


@app.command("stack")
def debug_stack(
    session_id: str = typer.Option(..., "--session", help="Session ID"),
    thread: str = typer.Option("main", "--thread", help="Thread name"),
    max_frames: int = typer.Option(10, "--max-frames", help="Maximum frames to return"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Return stack trace for a debugger thread."""
    client = DaemonClient(timeout=30.0)
    resp = client.request(
        "POST",
        "/debug/stack",
        json_body={
            "session_id": session_id,
            "thread": thread,
            "max_frames": max_frames,
        },
    )
    client.close()
    handle_response(resp, json_output=json_output)


@app.command("inspect")
def debug_inspect(
    variable_path: str = typer.Argument(
        ..., help="Variable path (e.g. user.profile.name or obj_1)"
    ),
    session_id: str = typer.Option(..., "--session", help="Session ID"),
    thread: str = typer.Option("main", "--thread", help="Thread name"),
    frame: int = typer.Option(0, "--frame", help="Zero-based frame index"),
    depth: int = typer.Option(1, "--depth", help="Nested expansion depth (1-3)"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Inspect a variable path in the selected frame."""
    client = DaemonClient(timeout=30.0)
    resp = client.request(
        "POST",
        "/debug/inspect",
        json_body={
            "session_id": session_id,
            "variable_path": variable_path,
            "thread": thread,
            "frame": frame,
            "depth": depth,
        },
    )
    client.close()
    handle_response(resp, json_output=json_output)


@app.command("eval")
def debug_eval(
    expression: str = typer.Argument(..., help="Expression (field access or toString())"),
    session_id: str = typer.Option(..., "--session", help="Session ID"),
    thread: str = typer.Option("main", "--thread", help="Thread name"),
    frame: int = typer.Option(0, "--frame", help="Zero-based frame index"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Evaluate a constrained expression in the selected frame."""
    client = DaemonClient(timeout=30.0)
    resp = client.request(
        "POST",
        "/debug/eval",
        json_body={
            "session_id": session_id,
            "expression": expression,
            "thread": thread,
            "frame": frame,
        },
    )
    client.close()
    handle_response(resp, json_output=json_output)


@mapping_app.command("load")
def debug_mapping_load(
    path: str = typer.Argument(..., help="Path to ProGuard/R8 mapping.txt"),
    session_id: str = typer.Option(..., "--session", help="Session ID"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Load a ProGuard/R8 mapping file for deobfuscation."""
    client = DaemonClient(timeout=30.0)
    resp = client.request(
        "POST",
        "/debug/mapping/load",
        json_body={
            "session_id": session_id,
            "path": path,
        },
    )
    client.close()
    handle_response(resp, json_output=json_output)


@mapping_app.command("clear")
def debug_mapping_clear(
    session_id: str = typer.Option(..., "--session", help="Session ID"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Clear the loaded ProGuard/R8 mapping from this debug session."""
    client = DaemonClient(timeout=30.0)
    resp = client.request(
        "POST",
        "/debug/mapping/clear",
        json_body={"session_id": session_id},
    )
    client.close()
    handle_response(resp, json_output=json_output)


@app.command("step-over")
def debug_step_over(
    session_id: str = typer.Option(..., "--session", help="Session ID"),
    thread: str = typer.Option("main", "--thread", help="Thread name"),
    timeout_seconds: float = typer.Option(
        10.0,
        "--timeout-seconds",
        help="Step timeout in seconds",
    ),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Step over and return stopped state atomically."""
    client = DaemonClient(timeout=60.0)
    resp = client.request(
        "POST",
        "/debug/step_over",
        json_body={
            "session_id": session_id,
            "thread": thread,
            "timeout_seconds": timeout_seconds,
        },
    )
    client.close()
    handle_response(resp, json_output=json_output)


@app.command("step-into")
def debug_step_into(
    session_id: str = typer.Option(..., "--session", help="Session ID"),
    thread: str = typer.Option("main", "--thread", help="Thread name"),
    timeout_seconds: float = typer.Option(
        10.0,
        "--timeout-seconds",
        help="Step timeout in seconds",
    ),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Step into and return stopped state atomically."""
    client = DaemonClient(timeout=60.0)
    resp = client.request(
        "POST",
        "/debug/step_into",
        json_body={
            "session_id": session_id,
            "thread": thread,
            "timeout_seconds": timeout_seconds,
        },
    )
    client.close()
    handle_response(resp, json_output=json_output)


@app.command("step-out")
def debug_step_out(
    session_id: str = typer.Option(..., "--session", help="Session ID"),
    thread: str = typer.Option("main", "--thread", help="Thread name"),
    timeout_seconds: float = typer.Option(
        10.0,
        "--timeout-seconds",
        help="Step timeout in seconds",
    ),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Step out and return stopped state atomically."""
    client = DaemonClient(timeout=60.0)
    resp = client.request(
        "POST",
        "/debug/step_out",
        json_body={
            "session_id": session_id,
            "thread": thread,
            "timeout_seconds": timeout_seconds,
        },
    )
    client.close()
    handle_response(resp, json_output=json_output)


@app.command("resume")
def debug_resume(
    session_id: str = typer.Option(..., "--session", help="Session ID"),
    thread: str | None = typer.Option(
        None,
        "--thread",
        help="Optional thread name; omit to resume all threads",
    ),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Resume one thread or all threads."""
    payload: dict[str, str | None] = {"session_id": session_id}
    if thread is not None:
        payload["thread"] = thread
    client = DaemonClient(timeout=30.0)
    resp = client.request("POST", "/debug/resume", json_body=payload)
    client.close()
    handle_response(resp, json_output=json_output)
