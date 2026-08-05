"""Request-level diagnostics persisted as NDJSON."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from android_emu_agent.security import (
    ensure_private_directory,
    ensure_private_file,
    open_private_append,
)

SENSITIVE_KEY_MARKERS = ("token", "secret", "password", "authorization", "api_key", "apikey")


class RequestDiagnostics:
    """Persist structured request diagnostics for daemon requests."""

    def __init__(self, output_dir: Path | None = None) -> None:
        state_dir = Path.home() / ".android-emu-agent"
        self.output_dir = output_dir or (state_dir / "diagnostics")
        ensure_private_directory(self.output_dir)
        self.path = self.output_dir / "requests.ndjson"
        ensure_private_file(self.path)
        self._lock = asyncio.Lock()

    async def record(self, event: dict[str, Any]) -> None:
        """Append a single NDJSON diagnostics event."""
        line = json.dumps(self.redact(event), ensure_ascii=True, sort_keys=True) + "\n"
        async with self._lock:
            await asyncio.to_thread(self._append_line, line)

    def _append_line(self, line: str) -> None:
        with open_private_append(self.path) as handle:
            handle.write(line)

    def redact(self, value: Any) -> Any:
        """Recursively redact sensitive values in payloads."""
        if isinstance(value, dict):
            redacted: dict[str, Any] = {}
            for key, item in value.items():
                lowered = key.lower()
                if any(marker in lowered for marker in SENSITIVE_KEY_MARKERS):
                    redacted[key] = "***REDACTED***"
                else:
                    redacted[key] = self.redact(item)
            return redacted
        if isinstance(value, list):
            return [self.redact(item) for item in value]
        return value

    @staticmethod
    def timestamp() -> str:
        """Return an ISO-8601 UTC timestamp."""
        return datetime.now(UTC).isoformat()
