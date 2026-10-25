"""Trace paths belong to the invoking CLI, not the long-lived daemon's cwd."""

from __future__ import annotations

import asyncio
import json
import zipfile
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from android_emu_agent.cli.commands import trace
from android_emu_agent.cli.main import app
from android_emu_agent.tracing.manager import TraceManager


class _Response:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def json(self) -> dict[str, Any]:
        return self.payload


def _capture(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, dict[str, Any]]]:
    calls: list[tuple[str, dict[str, Any]]] = []

    class Client:
        def request(self, method: str, path: str, *, json_body: dict[str, Any]) -> _Response:
            assert method == "POST"
            calls.append((path, json_body))
            return _Response({"status": "done"})

        def close(self) -> None:
            pass

    monkeypatch.setattr(trace, "DaemonClient", Client)
    return calls


@pytest.mark.parametrize("field", ["stop-output", "replay-input", "export-input", "export-output"])
@pytest.mark.parametrize(
    "spelling", ["relative", "absolute", "home", "parent", "spaces", "symlink"]
)
def test_trace_cli_binds_paths_before_daemon_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str, spelling: str
) -> None:
    caller = tmp_path / "caller"
    home = tmp_path / "home"
    caller.mkdir()
    home.mkdir()
    (caller / "link").symlink_to(home, target_is_directory=True)
    monkeypatch.chdir(caller)
    monkeypatch.setenv("HOME", str(home))
    raw = {
        "relative": "artifacts/run.zip",
        "absolute": str(tmp_path / "elsewhere" / "run.zip"),
        "home": "~/artifacts/run.zip",
        "parent": "../artifacts/run.zip",
        "spaces": "artifacts with spaces/трасса.zip",
        "symlink": "link/../run.zip",
    }[spelling]
    expected = str(Path(raw).expanduser().absolute())
    calls = _capture(monkeypatch)
    if field == "stop-output":
        command = ["trace", "stop", "s-test", "--output", raw]
        expected_payload = {"session_id": "s-test", "output_path": expected}
        endpoint = "/trace/stop"
    elif field == "replay-input":
        command = ["trace", "replay", raw, "--until-failure"]
        expected_payload = {"path": expected, "until_failure": True}
        endpoint = "/trace/replay"
    else:
        source = raw if field == "export-input" else str(tmp_path / "source.zip")
        output = raw if field == "export-output" else str(tmp_path / "report.md")
        command = ["trace", "export", source, "--output", output]
        expected_payload = {
            "path": expected if field == "export-input" else source,
            "output_path": expected if field == "export-output" else output,
            "format": "markdown",
        }
        endpoint = "/trace/export"
    result = CliRunner().invoke(app, [*command, "--json"])
    assert result.exit_code == 0, result.output
    assert calls == [(endpoint, expected_payload)]


@pytest.mark.parametrize("command", ["stop", "export"])
@pytest.mark.parametrize("output", [None, ""])
def test_trace_optional_output_preserves_default_and_empty_semantics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, command: str, output: str | None
) -> None:
    calls = _capture(monkeypatch)
    argument = "s-test" if command == "stop" else str(tmp_path / "source.zip")
    args = ["trace", command, argument, "--json"]
    if output is not None:
        args += ["--output", output]
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 0, result.output
    assert calls[0][1]["output_path"] == output


def _archive(path: Path, marker: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    manifest = {"trace_id": marker, "session_id": "s-test", "label": marker}
    event = {"kind": "daemon_exchange", "method": "GET", "path": f"/{marker}", "status_code": 200}
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("events.ndjson", json.dumps(event) + "\n")


@pytest.mark.parametrize("command", ["replay", "export"])
def test_trace_reads_caller_archive_when_daemon_has_same_named_archive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, command: str
) -> None:
    caller = tmp_path / "caller"
    daemon = tmp_path / "daemon"
    _archive(caller / "run.zip", "caller-evidence")
    _archive(daemon / "run.zip", "wrong-daemon-evidence")
    manager = TraceManager(tmp_path / "traces")
    responses: list[dict[str, Any]] = []

    class Client:
        def request(self, method: str, path: str, *, json_body: dict[str, Any]) -> _Response:
            assert method == "POST"
            with monkeypatch.context() as daemon_context:
                daemon_context.chdir(daemon)
                if path == "/trace/replay":
                    payload = manager.replay_archive(json_body["path"], until_failure=True)
                else:
                    payload = manager.export_markdown(
                        json_body["path"], output_path=json_body["output_path"]
                    )
            responses.append(payload)
            return _Response(payload)

        def close(self) -> None:
            pass

    monkeypatch.setattr(trace, "DaemonClient", Client)
    monkeypatch.chdir(caller)
    args = ["trace", command, "run.zip", "--json"]
    args += ["--until-failure"] if command == "replay" else ["--output", "reports/run.md"]
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 0, result.output
    if command == "replay":
        assert responses[0]["steps"][0]["path"] == "/caller-evidence"
    else:
        output = caller / "reports/run.md"
        assert output.is_file()
        assert "caller-evidence" in output.read_text()
        assert "wrong-daemon-evidence" not in output.read_text()
        assert not (daemon / "reports").exists()
    assert json.loads(result.output)["path"] == str(caller / "run.zip")


@pytest.mark.parametrize("directory_output", [False, True])
def test_trace_stop_writes_caller_output_from_other_daemon_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, directory_output: bool
) -> None:
    caller = tmp_path / "caller"
    daemon = tmp_path / "daemon"
    caller.mkdir()
    daemon.mkdir()
    manager = TraceManager(tmp_path / "traces")
    asyncio.run(manager.start("s-test", label="caller trace"))
    if directory_output:
        (caller / "artifacts").mkdir()
        (daemon / "artifacts").mkdir()
    raw = "artifacts" if directory_output else "artifacts/run.zip"
    responses: list[dict[str, Any]] = []

    class Client:
        def request(self, method: str, path: str, *, json_body: dict[str, Any]) -> _Response:
            assert (method, path) == ("POST", "/trace/stop")
            with monkeypatch.context() as daemon_context:
                daemon_context.chdir(daemon)
                payload = asyncio.run(
                    manager.stop(json_body["session_id"], json_body["output_path"])
                )
            responses.append(payload)
            return _Response(payload)

        def close(self) -> None:
            pass

    monkeypatch.setattr(trace, "DaemonClient", Client)
    monkeypatch.chdir(caller)
    result = CliRunner().invoke(app, ["trace", "stop", "s-test", "--output", raw, "--json"])
    assert result.exit_code == 0, result.output
    archive = Path(responses[0]["path"])
    assert archive.is_absolute()
    assert archive.parent == caller / "artifacts"
    assert archive.is_file()
    assert manager.load_manifest(archive)["label"] == "caller trace"
    assert not list(daemon.rglob("*.zip"))
