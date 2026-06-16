"""Agent trace archives for replayable observe-act-verify evidence."""

from __future__ import annotations

import asyncio
import json
import shutil
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from android_emu_agent.errors import AgentError

TRACE_SCHEMA_VERSION = 1
DEFAULT_TRACE_DIR = Path.home() / ".android-emu-agent" / "traces"
TRACE_ARCHIVE_SUFFIX = ".aea-trace.zip"
SENSITIVE_KEY_MARKERS = ("token", "secret", "password", "authorization", "api_key", "apikey")


@dataclass
class ActiveTrace:
    """Mutable trace session state."""

    trace_id: str
    session_id: str
    label: str | None
    directory: Path
    started_at: str
    sequence: int = 0

    @property
    def events_path(self) -> Path:
        return self.directory / "events.ndjson"

    @property
    def manifest_path(self) -> Path:
        return self.directory / "manifest.json"


class TraceManager:
    """Owns per-session trace logs and zip archive export."""

    def __init__(self, output_dir: Path | None = None) -> None:
        self.output_dir = output_dir or DEFAULT_TRACE_DIR
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._active: dict[str, ActiveTrace] = {}
        self._lock = asyncio.Lock()

    async def start(self, session_id: str, label: str | None = None) -> dict[str, Any]:
        """Start tracing a session."""
        async with self._lock:
            if session_id in self._active:
                trace = self._active[session_id]
                raise AgentError(
                    code="ERR_TRACE_ACTIVE",
                    message=f"Trace already active for session {session_id}",
                    context={"session_id": session_id, "trace_id": trace.trace_id},
                    remediation="Stop the active trace before starting another one.",
                )

            trace_id = f"tr-{uuid4().hex[:10]}"
            directory = self.output_dir / trace_id
            directory.mkdir(parents=True, exist_ok=False)
            trace = ActiveTrace(
                trace_id=trace_id,
                session_id=session_id,
                label=label,
                directory=directory,
                started_at=self.timestamp(),
            )
            self._active[session_id] = trace
            await asyncio.to_thread(self._write_manifest, trace, status="active")
            await self.record_event(
                session_id,
                {
                    "kind": "trace_started",
                    "label": label,
                },
                locked=True,
            )
            return self._trace_payload(trace, status="active")

    async def stop(self, session_id: str, output_path: str | None = None) -> dict[str, Any]:
        """Stop tracing a session and return a zip archive path."""
        async with self._lock:
            trace = self._active.get(session_id)
            if trace is None:
                raise AgentError(
                    code="ERR_TRACE_NOT_ACTIVE",
                    message=f"No active trace for session {session_id}",
                    context={"session_id": session_id},
                    remediation="Start a trace with 'trace start' before stopping it.",
                )

            await self.record_event(
                session_id,
                {
                    "kind": "trace_stopped",
                },
                locked=True,
            )
            stopped_at = self.timestamp()
            await asyncio.to_thread(
                self._write_manifest,
                trace,
                status="stopped",
                stopped_at=stopped_at,
            )
            archive_path = self._archive_path(trace, output_path)
            await asyncio.to_thread(self._zip_trace, trace.directory, archive_path)
            del self._active[session_id]
            return {
                **self._trace_payload(trace, status="stopped"),
                "path": str(archive_path),
                "stopped_at": stopped_at,
            }

    async def status(self, session_id: str | None = None) -> dict[str, Any]:
        """Return active trace status."""
        async with self._lock:
            traces = [
                self._trace_payload(trace, status="active")
                for trace in self._active.values()
                if session_id is None or trace.session_id == session_id
            ]
        return {"status": "done", "traces": traces}

    async def record_event(
        self,
        session_id: str | None,
        event: dict[str, Any],
        *,
        locked: bool = False,
    ) -> None:
        """Append an event if the session has an active trace."""
        if not session_id:
            return
        if locked:
            await self._record_event_locked(session_id, event)
            return
        async with self._lock:
            await self._record_event_locked(session_id, event)

    async def _record_event_locked(self, session_id: str, event: dict[str, Any]) -> None:
        trace = self._active.get(session_id)
        if trace is None:
            return

        trace.sequence += 1
        payload = {
            "schema_version": TRACE_SCHEMA_VERSION,
            "trace_id": trace.trace_id,
            "session_id": session_id,
            "sequence": trace.sequence,
            "timestamp": self.timestamp(),
            **self._redact(event),
        }
        line = json.dumps(payload, ensure_ascii=True, sort_keys=True) + "\n"
        await asyncio.to_thread(self._append_line, trace.events_path, line)

    async def record_daemon_exchange(
        self,
        *,
        session_id: str | None,
        diagnostic_id: str,
        method: str,
        path: str,
        status_code: int,
        elapsed_ms: float,
        request_payload: dict[str, Any] | None,
        response_payload: dict[str, Any] | None,
    ) -> None:
        """Record a daemon request/response exchange for active traces."""
        if path.startswith("/trace/"):
            return
        await self.record_event(
            session_id,
            {
                "kind": "daemon_exchange",
                "diagnostic_id": diagnostic_id,
                "method": method,
                "path": path,
                "status_code": status_code,
                "elapsed_ms": elapsed_ms,
                "request": request_payload,
                "response": response_payload,
                "error": response_payload.get("error") if response_payload else None,
            },
        )

    def replay_archive(
        self, archive_path: str | Path, *, until_failure: bool = False
    ) -> dict[str, Any]:
        """Return a dry replay plan from a trace archive."""
        events = self.load_events(archive_path)
        replayable = [
            self._replay_step(event)
            for event in events
            if event.get("kind") == "daemon_exchange"
        ]
        stopped_at_failure = False
        if until_failure:
            trimmed: list[dict[str, Any]] = []
            for step in replayable:
                trimmed.append(step)
                if step["status_code"] >= 400 or step.get("error"):
                    stopped_at_failure = True
                    break
            replayable = trimmed

        return {
            "status": "done",
            "path": str(archive_path),
            "mode": "dry-run",
            "until_failure": until_failure,
            "stopped_at_failure": stopped_at_failure,
            "steps": replayable,
            "step_count": len(replayable),
        }

    def export_markdown(
        self,
        archive_path: str | Path,
        *,
        output_path: str | Path | None = None,
    ) -> dict[str, Any]:
        """Export a human-readable Markdown report for a trace archive."""
        manifest = self.load_manifest(archive_path)
        events = self.load_events(archive_path)
        markdown = self._render_markdown(manifest, events)
        result: dict[str, Any] = {
            "status": "done",
            "path": str(archive_path),
            "format": "markdown",
            "markdown": markdown,
        }
        if output_path is not None:
            destination = Path(output_path).expanduser()
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(markdown, encoding="utf-8")
            result["output_path"] = str(destination)
        return result

    def load_manifest(self, archive_path: str | Path) -> dict[str, Any]:
        """Load manifest JSON from a trace archive or unpacked trace directory."""
        path = Path(archive_path).expanduser()
        if path.is_dir():
            return self._load_json_file(path / "manifest.json")
        with zipfile.ZipFile(path) as zf, zf.open("manifest.json") as handle:
            return self._as_dict(json.loads(handle.read().decode("utf-8")))

    def load_events(self, archive_path: str | Path) -> list[dict[str, Any]]:
        """Load events from a trace archive or unpacked trace directory."""
        path = Path(archive_path).expanduser()
        if path.is_dir():
            events_path = path / "events.ndjson"
            if not events_path.exists():
                return []
            return [json.loads(line) for line in events_path.read_text().splitlines() if line]

        with zipfile.ZipFile(path) as zf:
            try:
                with zf.open("events.ndjson") as handle:
                    lines = handle.read().decode("utf-8").splitlines()
            except KeyError:
                return []
        return [json.loads(line) for line in lines if line]

    @staticmethod
    def timestamp() -> str:
        """Return an ISO-8601 UTC timestamp."""
        return datetime.now(UTC).isoformat()

    def _redact(self, value: Any) -> Any:
        """Recursively redact sensitive values from trace payloads."""
        if isinstance(value, dict):
            redacted: dict[str, Any] = {}
            for key, item in value.items():
                lowered = key.lower()
                if any(marker in lowered for marker in SENSITIVE_KEY_MARKERS):
                    redacted[key] = "***REDACTED***"
                else:
                    redacted[key] = self._redact(item)
            return redacted
        if isinstance(value, list):
            return [self._redact(item) for item in value]
        return value

    def _trace_payload(self, trace: ActiveTrace, *, status: str) -> dict[str, Any]:
        return {
            "trace_id": trace.trace_id,
            "session_id": trace.session_id,
            "label": trace.label,
            "trace_status": status,
            "started_at": trace.started_at,
            "directory": str(trace.directory),
        }

    def _archive_path(self, trace: ActiveTrace, output_path: str | None) -> Path:
        if output_path:
            path = Path(output_path).expanduser()
            if path.exists() and path.is_dir():
                return path / f"{trace.trace_id}{TRACE_ARCHIVE_SUFFIX}"
            path.parent.mkdir(parents=True, exist_ok=True)
            return path
        return self.output_dir / f"{trace.trace_id}{TRACE_ARCHIVE_SUFFIX}"

    @staticmethod
    def _append_line(path: Path, line: str) -> None:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line)

    @staticmethod
    def _load_json_file(path: Path) -> dict[str, Any]:
        return TraceManager._as_dict(json.loads(path.read_text(encoding="utf-8")))

    @staticmethod
    def _as_dict(value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise ValueError("Expected JSON object")
        return cast(dict[str, Any], value)

    def _write_manifest(
        self,
        trace: ActiveTrace,
        *,
        status: str,
        stopped_at: str | None = None,
    ) -> None:
        manifest = {
            "schema_version": TRACE_SCHEMA_VERSION,
            "trace_id": trace.trace_id,
            "session_id": trace.session_id,
            "label": trace.label,
            "status": status,
            "started_at": trace.started_at,
            "stopped_at": stopped_at,
            "event_count": trace.sequence,
        }
        trace.manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=True, sort_keys=True),
            encoding="utf-8",
        )

    @staticmethod
    def _zip_trace(directory: Path, archive_path: Path) -> None:
        if archive_path.exists():
            archive_path.unlink()
        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for path in sorted(directory.rglob("*")):
                if path.is_file():
                    zf.write(path, path.relative_to(directory))

    @staticmethod
    def _replay_step(event: dict[str, Any]) -> dict[str, Any]:
        return {
            "sequence": event.get("sequence"),
            "method": event.get("method"),
            "path": event.get("path"),
            "request": event.get("request"),
            "status_code": event.get("status_code"),
            "diagnostic_id": event.get("diagnostic_id"),
            "error": event.get("error"),
        }

    def _render_markdown(self, manifest: dict[str, Any], events: list[dict[str, Any]]) -> str:
        lines = [
            "# Android Emu Agent Trace",
            "",
            f"- trace_id: `{manifest.get('trace_id', '')}`",
            f"- session_id: `{manifest.get('session_id', '')}`",
            f"- status: `{manifest.get('status', '')}`",
            f"- started_at: `{manifest.get('started_at', '')}`",
        ]
        if manifest.get("stopped_at"):
            lines.append(f"- stopped_at: `{manifest['stopped_at']}`")
        lines.extend(["", "## Events", ""])
        for event in events:
            summary = self._event_summary(event)
            lines.extend(
                [
                    f"### {event.get('sequence')}. {event.get('kind')}",
                    "",
                    summary,
                    "",
                ]
            )
        return "\n".join(lines).rstrip() + "\n"

    @staticmethod
    def _event_summary(event: dict[str, Any]) -> str:
        if event.get("kind") != "daemon_exchange":
            return "```json\n" + json.dumps(event, indent=2, ensure_ascii=True) + "\n```"

        response = event.get("response")
        error = event.get("error")
        lines = [
            f"- request: `{event.get('method')} {event.get('path')}`",
            f"- status_code: `{event.get('status_code')}`",
            f"- diagnostic_id: `{event.get('diagnostic_id')}`",
        ]
        if error:
            lines.append(f"- error: `{error.get('code')}` {error.get('message')}")
        if isinstance(response, dict) and response.get("path"):
            lines.append(f"- artifact: `{response['path']}`")
        return "\n".join(lines)

    def clear(self) -> None:
        """Clear active traces and trace output directory. Intended for tests."""
        self._active.clear()
        if self.output_dir.exists():
            shutil.rmtree(self.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
