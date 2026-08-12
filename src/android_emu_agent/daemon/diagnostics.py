"""Request-level diagnostics persisted as NDJSON."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from android_emu_agent.redaction import redact_sensitive_data
from android_emu_agent.security import (
    ensure_private_directory,
    ensure_private_file,
    open_private_append,
)

# Every request appends a line here, so without rotation the file grows for the lifetime
# of the install. Keep a bounded window of recent history instead.
DEFAULT_MAX_BYTES = 10 * 1024 * 1024
DEFAULT_BACKUP_COUNT = 3


class RequestDiagnostics:
    """Persist structured request diagnostics for daemon requests."""

    def __init__(
        self,
        output_dir: Path | None = None,
        *,
        max_bytes: int = DEFAULT_MAX_BYTES,
        backup_count: int = DEFAULT_BACKUP_COUNT,
    ) -> None:
        state_dir = Path.home() / ".android-emu-agent"
        self.output_dir = output_dir or (state_dir / "diagnostics")
        ensure_private_directory(self.output_dir)
        self.path = self.output_dir / "requests.ndjson"
        ensure_private_file(self.path)
        self._max_bytes = max_bytes
        self._backup_count = backup_count
        self._lock = asyncio.Lock()

    async def record(self, event: dict[str, Any]) -> None:
        """Append a single NDJSON diagnostics event."""
        line = json.dumps(self.redact(event), ensure_ascii=True, sort_keys=True) + "\n"
        async with self._lock:
            await asyncio.to_thread(self._append_line, line)

    def _append_line(self, line: str) -> None:
        self._rotate_if_needed(len(line.encode()))
        with open_private_append(self.path) as handle:
            handle.write(line)

    def _rotate_if_needed(self, incoming_bytes: int) -> None:
        """Roll the log over once the next write would exceed the size budget."""
        if self._max_bytes <= 0 or self._backup_count < 1:
            return
        try:
            size = self.path.stat().st_size
        except OSError:
            return
        if size + incoming_bytes <= self._max_bytes:
            return

        self._backup_path(self._backup_count).unlink(missing_ok=True)
        for index in range(self._backup_count - 1, 0, -1):
            source = self._backup_path(index)
            if source.exists():
                source.replace(self._backup_path(index + 1))
        # replace() preserves the owner-only mode the current file already carries.
        self.path.replace(self._backup_path(1))

    def _backup_path(self, index: int) -> Path:
        return self.path.with_name(f"{self.path.name}.{index}")

    def redact(self, value: Any) -> Any:
        """Recursively redact sensitive values in payloads."""
        return redact_sensitive_data(value)

    @staticmethod
    def timestamp() -> str:
        """Return an ISO-8601 UTC timestamp."""
        return datetime.now(UTC).isoformat()
