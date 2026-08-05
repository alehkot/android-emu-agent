"""Shared redaction helpers for persisted diagnostics and traces."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

REDACTED = "***REDACTED***"
SENSITIVE_KEY_MARKERS = (
    "token",
    "secret",
    "password",
    "authorization",
    "api_key",
    "apikey",
    "credential",
    "private_key",
)
AUTHORIZATION_PATTERN = re.compile(r"\b(Bearer|Basic)\s+[^\s,;]+", re.IGNORECASE)


def redact_sensitive_data(value: Any) -> Any:
    """Recursively redact credentials, typed input, and URI secrets."""
    if isinstance(value, dict):
        operation = _operation_name(value)
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            lowered = key.lower()
            if _contains_marker(lowered, SENSITIVE_KEY_MARKERS) or (
                operation == "set_text" and lowered == "text"
            ):
                redacted[key] = REDACTED
            else:
                redacted[key] = redact_sensitive_data(item)

        path = value.get("path")
        request = redacted.get("request")
        if isinstance(path, str) and isinstance(request, dict):
            if path == "/actions/set_text" and "text" in request:
                request["text"] = REDACTED
            if path.startswith("/tasks/script/") and "script" in request:
                request["script"] = REDACTED
        return redacted
    if isinstance(value, list):
        return [redact_sensitive_data(item) for item in value]
    if isinstance(value, str):
        return _redact_string(value)
    return value


def _operation_name(value: dict[str, Any]) -> str | None:
    for key in ("action", "operation"):
        operation = value.get(key)
        if isinstance(operation, str):
            return operation.replace("-", "_").lower()
    return None


def _contains_marker(value: str, markers: tuple[str, ...]) -> bool:
    normalized = value.replace("-", "_")
    return any(marker in normalized for marker in markers)


def _redact_string(value: str) -> str:
    redacted = AUTHORIZATION_PATTERN.sub(lambda match: f"{match.group(1)} {REDACTED}", value)
    try:
        parsed = urlsplit(redacted)
    except ValueError:
        return redacted

    netloc = parsed.netloc
    changed = redacted != value
    if "@" in netloc:
        user_info, host = netloc.rsplit("@", 1)
        if ":" in user_info:
            username, _password = user_info.split(":", 1)
            netloc = f"{username}:{REDACTED}@{host}"
            changed = True

    query, query_changed = _redact_parameter_string(parsed.query)
    fragment, fragment_changed = _redact_parameter_string(parsed.fragment)
    changed = changed or query_changed or fragment_changed
    if not changed:
        return redacted
    return urlunsplit((parsed.scheme, netloc, parsed.path, query, fragment))


def _redact_parameter_string(value: str) -> tuple[str, bool]:
    if not value or "=" not in value:
        return value, False
    pairs = parse_qsl(value, keep_blank_values=True)
    changed = False
    redacted_pairs: list[tuple[str, str]] = []
    for key, item in pairs:
        if _is_sensitive_uri_key(key):
            redacted_pairs.append((key, REDACTED))
            changed = True
        else:
            redacted_pairs.append((key, item))
    if not changed:
        return value, False
    return urlencode(redacted_pairs), True


def _is_sensitive_uri_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return _contains_marker(normalized, SENSITIVE_KEY_MARKERS) or normalized in {
        "code",
        "sig",
        "signature",
    }
