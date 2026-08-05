"""Parsers for stable values embedded in Android dumpsys output."""

from __future__ import annotations

import re

_ACTIVITY_COMPONENT_PATTERN = re.compile(
    r"(?P<package>[A-Za-z0-9._$]+)/(?P<activity>[A-Za-z0-9._$/$]+)"
)


def parse_activity_component(output: str) -> tuple[str, str, str] | None:
    """Extract an Android package/activity component from dumpsys output."""
    match = _ACTIVITY_COMPONENT_PATTERN.search(output)
    if match is None:
        return None

    package = match.group("package")
    activity = match.group("activity")
    return package, activity, f"{package}/{activity}"
