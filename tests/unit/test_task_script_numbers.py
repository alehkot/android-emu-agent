"""Numeric task-script syntax errors and conversion compatibility."""

from __future__ import annotations

import pytest

from android_emu_agent.errors import AgentError
from android_emu_agent.tasks import TaskManager


@pytest.mark.parametrize("command", ["wait idle", "verify idle", "expect idle", "swipe up"])
@pytest.mark.parametrize(
    "option",
    [
        "timeout_ms=later",
        "duration_ms=1.5",
        "duration=",
        "distance=far",
        "distance=nan",
        "distance=inf",
        "distance=-Infinity",
        "distance=1e999",
    ],
)
def test_invalid_numeric_option_has_source_line_and_remediation(command: str, option: str) -> None:
    script = f"# heading\n\nhome\n{command} {option}\n"
    with pytest.raises(AgentError) as caught:
        TaskManager().parse_script(script, source_name="numbers.aea")
    error = caught.value
    assert error.code == "ERR_TASK_SCRIPT_INVALID"
    assert error.context == {"source": "numbers.aea", "line": 4}
    assert "numbers.aea:4:" in error.message
    assert option.split("=", 1)[0] in error.message
    assert "task validate" in error.remediation


@pytest.mark.parametrize(
    ("option", "key", "expected"),
    [
        ("timeout-ms=+100", "timeout_ms", 100),
        ("duration_ms=1_000", "duration_ms", 1000),
        ("duration=٠١٢", "duration", 12),
        ("distance=.5", "distance", 0.5),
        ("distance=1e-2", "distance", 0.01),
        ("distance=-0", "distance", -0.0),
        ("timeout_ms=true", "timeout_ms", True),
        ("distance=false", "distance", False),
    ],
)
def test_valid_numeric_conversion_is_preserved(option: str, key: str, expected: object) -> None:
    spec = TaskManager().parse_script(f"swipe up {option}")
    value = spec["steps"][0][key]
    assert value == expected
    assert type(value) is type(expected)


def test_invalid_number_does_not_echo_input_value() -> None:
    with pytest.raises(AgentError) as caught:
        TaskManager().parse_script("wait idle timeout_ms=private-value")
    assert "private-value" not in caught.value.message
