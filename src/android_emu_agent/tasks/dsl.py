"""Line-oriented task script parser."""

from __future__ import annotations

import shlex
from pathlib import Path
from typing import Any

from android_emu_agent.errors import AgentError

SCRIPT_SUFFIXES = {".aea", ".aea-task", ".aea-replay"}


def is_task_script_path(path: str | Path) -> bool:
    """Return whether a path should be parsed as a task script."""
    return Path(path).suffix.lower() in SCRIPT_SUFFIXES


def parse_task_script(script: str, *, source_name: str = "<script>") -> dict[str, Any]:
    """Parse a human-editable task script into the JSON task spec shape.

    The format is intentionally small and maps directly onto the existing task harness:

    - `name "Login smoke"` and `description "..."`
    - `session s-abc123`
    - action lines: `tap`, `long-tap`, `set-text`, `clear`, `back`, `home`, `recents`, `swipe`
    - app lines: `launch`, `force-stop`, `deeplink`
    - wait lines: `wait idle|activity|text|exists|gone ...`
    - verifier lines: `verify ...` attaches to the previous step, `expect ...` is task-level
    - `snapshot [mode=compact|full|raw]`
    """
    spec: dict[str, Any] = {"name": "unnamed script task", "steps": []}
    task_verifiers: list[dict[str, Any]] = []

    for line_number, raw_line in enumerate(script.splitlines(), start=1):
        line = _strip_comment(raw_line).strip()
        if not line:
            continue

        try:
            tokens = shlex.split(line, comments=False, posix=True)
        except ValueError as exc:
            raise _script_error(source_name, line_number, str(exc)) from exc
        if not tokens:
            continue

        keyword = tokens[0].lower()
        args = tokens[1:]
        if keyword == "name":
            spec["name"] = _joined_value(args, source_name, line_number)
        elif keyword == "description":
            spec["description"] = _joined_value(args, source_name, line_number)
        elif keyword == "session":
            spec["session_id"] = _single_arg(args, source_name, line_number)
        elif keyword == "expect":
            task_verifiers.append(_parse_verifier(args, source_name, line_number))
        elif keyword == "verify":
            if not spec["steps"]:
                raise _script_error(source_name, line_number, "verify requires a previous step")
            step = spec["steps"][-1]
            verify = step.setdefault("verify", [])
            if not isinstance(verify, list):
                raise _script_error(source_name, line_number, "previous step has invalid verify list")
            verify.append(_parse_verifier(args, source_name, line_number))
        else:
            spec["steps"].append(_parse_step(keyword, args, source_name, line_number))

    if task_verifiers:
        spec["verifiers"] = task_verifiers
    if not spec["steps"] and not spec.get("verifiers"):
        raise _script_error(source_name, 1, "script must include at least one step or verifier")
    return spec


def _parse_step(
    keyword: str,
    args: list[str],
    source_name: str,
    line_number: int,
) -> dict[str, Any]:
    options, values = _split_options(args)
    if keyword in {"tap", "long-tap", "clear"}:
        ref = _selector_arg(values, source_name, line_number)
        return {"action": keyword.replace("-", "_"), "ref": ref, **options}
    if keyword == "set-text":
        if len(values) < 2:
            raise _script_error(source_name, line_number, "set-text requires selector and text")
        return {"action": "set_text", "ref": values[0], "text": " ".join(values[1:]), **options}
    if keyword in {"back", "home", "recents"}:
        _no_values(values, source_name, line_number)
        return {"action": keyword, **options}
    if keyword == "swipe":
        direction = _single_value(values, source_name, line_number, "swipe requires a direction")
        step = {"action": "swipe", "direction": direction, **options}
        _normalize_numeric_options(step)
        return step
    if keyword == "launch":
        package = _single_value(values, source_name, line_number, "launch requires a package")
        return {"app": "launch", "package": package, **options}
    if keyword == "force-stop":
        package = _single_value(values, source_name, line_number, "force-stop requires a package")
        return {"app": "force_stop", "package": package, **options}
    if keyword == "deeplink":
        uri = _single_value(values, source_name, line_number, "deeplink requires a URI")
        return {"app": "deeplink", "uri": uri, **options}
    if keyword == "wait":
        return _parse_wait(values, options, source_name, line_number)
    if keyword == "snapshot":
        _no_values(values, source_name, line_number)
        return {"ui": "snapshot", **options}
    raise _script_error(source_name, line_number, f"unsupported script command: {keyword}")


def _parse_verifier(
    args: list[str],
    source_name: str,
    line_number: int,
) -> dict[str, Any]:
    options, values = _split_options(args)
    return _parse_wait(values, options, source_name, line_number, verifier=True)


def _parse_wait(
    values: list[str],
    options: dict[str, Any],
    source_name: str,
    line_number: int,
    *,
    verifier: bool = False,
) -> dict[str, Any]:
    if not values:
        raise _script_error(source_name, line_number, "wait/verify requires an operation")
    operation = values[0].replace("-", "_")
    args = values[1:]
    payload: dict[str, Any] = {"type" if verifier else "wait": operation, **options}

    if operation == "idle":
        _no_values(args, source_name, line_number)
    elif operation == "activity":
        payload["activity"] = _single_value(
            args, source_name, line_number, "activity wait requires an activity"
        )
    elif operation == "text":
        payload["text"] = _joined_value(args, source_name, line_number)
    elif operation in {"exists", "gone"}:
        payload["ref"] = _selector_arg(args, source_name, line_number)
    else:
        raise _script_error(source_name, line_number, f"unsupported wait operation: {operation}")

    _normalize_numeric_options(payload)
    return payload


def _split_options(args: list[str]) -> tuple[dict[str, Any], list[str]]:
    options: dict[str, Any] = {}
    values: list[str] = []
    for arg in args:
        if "=" in arg and not arg.startswith(("^", "text:", "id:", "desc:", "class:", "coords:")):
            key, raw_value = arg.split("=", 1)
            options[key.replace("-", "_")] = _option_value(raw_value)
        else:
            values.append(arg)
    return options, values


def _option_value(value: str) -> Any:
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    return value


def _normalize_numeric_options(payload: dict[str, Any]) -> None:
    for key in ("timeout_ms", "duration_ms"):
        if key in payload and isinstance(payload[key], str):
            payload[key] = int(payload[key])
    if "duration" in payload and isinstance(payload["duration"], str):
        payload["duration"] = int(payload["duration"])
    if "distance" in payload and isinstance(payload["distance"], str):
        payload["distance"] = float(payload["distance"])


def _strip_comment(line: str) -> str:
    in_single = False
    in_double = False
    escaped = False
    for index, char in enumerate(line):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
        elif char == "#" and not in_single and not in_double:
            return line[:index]
    return line


def _single_arg(args: list[str], source_name: str, line_number: int) -> str:
    return _single_value(args, source_name, line_number, "expected exactly one argument")


def _single_value(
    values: list[str],
    source_name: str,
    line_number: int,
    message: str,
) -> str:
    if len(values) != 1:
        raise _script_error(source_name, line_number, message)
    return values[0]


def _selector_arg(values: list[str], source_name: str, line_number: int) -> str:
    if not values:
        raise _script_error(source_name, line_number, "selector argument is required")
    return " ".join(values)


def _joined_value(args: list[str], source_name: str, line_number: int) -> str:
    if not args:
        raise _script_error(source_name, line_number, "value is required")
    return " ".join(args)


def _no_values(values: list[str], source_name: str, line_number: int) -> None:
    if values:
        raise _script_error(source_name, line_number, "unexpected argument")


def _script_error(source_name: str, line_number: int, message: str) -> AgentError:
    return AgentError(
        code="ERR_TASK_SCRIPT_INVALID",
        message=f"{source_name}:{line_number}: {message}",
        context={"source": source_name, "line": line_number},
        remediation="Fix the .aea task script and run 'task validate' again.",
    )
