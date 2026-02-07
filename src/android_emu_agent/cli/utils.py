"""Shared CLI helpers and constants."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, cast

import typer

from android_emu_agent.cli.daemon_client import format_json

RELIABILITY_TIMEOUT = 60.0
RELIABILITY_BUGREPORT_TIMEOUT = 300.0
RELIABILITY_PULL_TIMEOUT = 180.0
RELIABILITY_DUMPHEAP_TIMEOUT = 180.0
FILE_TRANSFER_TIMEOUT = 120.0
FILE_APP_TRANSFER_TIMEOUT = 180.0
APP_INSTALL_TIMEOUT = 180.0


def _parse_response_json(resp: Any) -> dict[str, Any]:
    try:
        return cast(dict[str, Any], resp.json())
    except Exception as exc:  # pragma: no cover - defensive
        typer.echo("Failed to parse response")
        raise typer.Exit(code=1) from exc


def _maybe_render_error(data: dict[str, Any]) -> None:
    if not (isinstance(data, dict) and data.get("error")):
        return
    error = data["error"]
    message = f"{error.get('code')}: {error.get('message')}"
    remediation = error.get("remediation")
    typer.echo(message)
    if remediation:
        typer.echo(f"Hint: {remediation}")
    raise typer.Exit(code=1)


def _maybe_render_done(data: dict[str, Any]) -> bool:
    if not (isinstance(data, dict) and data.get("status") == "done"):
        return False
    message = "✓ Done"
    if "elapsed_ms" in data:
        message += f" ({data['elapsed_ms']} ms)"
    if "path" in data:
        message += f" -> {data['path']}"
    typer.echo(message)
    return True


def _maybe_render_output(data: dict[str, Any]) -> bool:
    if not (isinstance(data, dict) and "output" in data):
        return False
    output = data.get("output")
    if output:
        typer.echo(output)
        return True
    return False


def handle_response(resp: Any, json_output: bool = False) -> None:
    data = _parse_response_json(resp)
    if json_output:
        typer.echo(format_json(data))
        return

    _maybe_render_error(data)
    if _maybe_render_done(data):
        return
    typer.echo(format_json(data))


def handle_output_response(resp: Any, json_output: bool = False) -> None:
    data = _parse_response_json(resp)
    if json_output:
        typer.echo(format_json(data))
        return

    _maybe_render_error(data)
    if _maybe_render_output(data):
        return
    if _maybe_render_done(data):
        return
    typer.echo(format_json(data))


def handle_response_with_pull(
    resp: Any,
    *,
    json_output: bool = False,
    pull: bool = False,
    output: str | None = None,
) -> None:
    data = _parse_response_json(resp)
    pulled_path: Path | None = None

    if pull and not data.get("error"):
        try:
            path = data.get("path")
            if not path:
                raise typer.BadParameter("Response missing path; cannot pull artifact")
            pulled_path = pull_artifact_path(path, output)
            data["pulled_path"] = str(pulled_path)
        except typer.BadParameter as exc:
            typer.echo(f"Error: {exc}")
            raise typer.Exit(code=1) from None

    if json_output:
        typer.echo(format_json(data))
        return

    _maybe_render_error(data)
    if _maybe_render_done(data):
        if pulled_path:
            typer.echo(f"✓ Pulled -> {pulled_path}")
        return
    typer.echo(format_json(data))


def target_payload(device: str | None, session_id: str | None) -> dict[str, Any]:
    if device and session_id:
        raise typer.BadParameter("--device and --session are mutually exclusive")
    if not device and not session_id:
        raise typer.BadParameter("Provide --device or --session")
    if device:
        return {"serial": device}
    assert session_id is not None
    return {"session_id": session_id}


def resolve_session_id(session_arg: str | None, session_opt: str | None) -> str | None:
    if session_arg and session_opt:
        raise typer.BadParameter("Provide session ID once (argument or --session)")
    return session_arg or session_opt


def pull_artifact_path(path_str: str, output: str | None = None) -> Path:
    src = Path(path_str).expanduser()
    if not src.exists():
        raise typer.BadParameter(f"Artifact not found: {src}")

    if output is None:
        dest = Path.cwd() / src.name
    else:
        output_path = Path(output).expanduser()
        output_str = str(output)
        if output_path.exists() and output_path.is_dir():
            dest = output_path / src.name
        elif output_str.endswith(("/", "\\")):
            output_path.mkdir(parents=True, exist_ok=True)
            dest = output_path / src.name
        else:
            dest = output_path
            dest.parent.mkdir(parents=True, exist_ok=True)

    if src.resolve() == dest.resolve():
        return dest

    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    return dest


def require_target(device: str | None, session_id: str | None) -> dict[str, Any]:
    try:
        return target_payload(device, session_id)
    except typer.BadParameter as exc:
        typer.echo(f"Error: {exc}")
        raise typer.Exit(code=1) from None
