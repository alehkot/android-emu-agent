from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

from android_emu_agent.errors import AgentError


def parse_datetime(val: str | int | None) -> int | None:
    """Parse a flexible datetime string or int into epoch milliseconds.

    Supports:
    - Raw epoch ms (int or string)
    - Relative time ("5m ago", "1 hour ago", "2 days ago")
    - ISO 8601 strings ("2026-02-22T20:24:23")

    If already an int/None, returns it.
    """
    if val is None:
        return None

    if isinstance(val, int):
        if val < 0:
            raise AgentError(
                code="ERR_INVALID_SINCE_TIMESTAMP",
                message=f"Invalid since_timestamp_ms: {val}",
                context={"since_timestamp_ms": val},
                remediation="Use epoch milliseconds >= 0.",
            )
        return val

    val_str = str(val).strip()
    if not val_str:
        return None

    # 1. Raw integer (milliseconds)
    if val_str.isdigit():
        return int(val_str)

    # 2. Relative time ("X [m|h|d] ago", "X [mins|hours|days] ago")
    rel_match = re.match(
        r"^(\d+)\s*(m|min|mins|minutes?|h|hr|hours?|d|days?)\s*ago$", val_str.lower()
    )
    if rel_match:
        amount = int(rel_match.group(1))
        unit = rel_match.group(2)

        delta = timedelta()
        if unit.startswith("m"):
            delta = timedelta(minutes=amount)
        elif unit.startswith("h"):
            delta = timedelta(hours=amount)
        elif unit.startswith("d"):
            delta = timedelta(days=amount)

        target_dt = datetime.now(UTC) - delta
        return int(target_dt.timestamp() * 1000)

    # 3. ISO format parse
    try:  # Support Z for UTC
        val_for_iso = val_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(val_for_iso)
        if dt.tzinfo is None:
            # Assume UTC if no timezone is provided
            dt = dt.replace(tzinfo=UTC)
        return int(dt.timestamp() * 1000)
    except ValueError:
        pass

    raise AgentError(
        code="ERR_INVALID_DATETIME_FORMAT",
        message=f"Cannot parse datetime string: {val}",
        context={"val": val},
        remediation="Use epoch ms, ISO 8601 string, or relative time (e.g., '10m ago', '2 hours ago').",
    )
