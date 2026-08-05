"""Generation-qualified UI ref formatting and parsing."""

from __future__ import annotations

import re

REF_PATTERN = re.compile(r"^\^g(?P<generation>\d+)a(?P<element>\d+)$")


def format_ref(generation: int, element: int) -> str:
    """Build a ref that remains unique across snapshot generations."""
    return f"^g{generation}a{element}"


def ref_generation(ref: str) -> int | None:
    """Return the encoded generation, or None for a legacy/non-ref token."""
    match = REF_PATTERN.fullmatch(ref)
    if match is None:
        return None
    return int(match.group("generation"))
