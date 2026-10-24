"""Quoted task data must not become key=value options."""

from __future__ import annotations

import pytest

from android_emu_agent.tasks import TaskManager


@pytest.mark.parametrize(
    "literal",
    [
        '"x=y"',
        "'x=y'",
        '"hello x=y"',
        '"timeout_ms=5000"',
        r"x\=y",
        '"x"=y',
        '"x="y',
        '"x=y # kept"',
        '""',
    ],
)
def test_set_text_preserves_literal_tokens(literal: str) -> None:
    import shlex

    expected = shlex.split(literal)[0]
    spec = TaskManager().parse_script(f"set-text id:com.example:id/input {literal}")
    assert spec["steps"] == [
        {"action": "set_text", "ref": "id:com.example:id/input", "text": expected}
    ]


@pytest.mark.parametrize("quote", ["", '"', "'"])
def test_deeplink_query_is_a_value(quote: str) -> None:
    uri = "https://example.com/search?q=android&sort=date"
    spec = TaskManager().parse_script(f"deeplink {quote}{uri}{quote}")
    assert spec["steps"] == [{"app": "deeplink", "uri": uri}]
    assert TaskManager().validate(spec)["step_count"] == 1


@pytest.mark.parametrize("command", ["wait", "verify", "expect"])
@pytest.mark.parametrize("before", [False, True])
def test_text_conditions_keep_literal_option_names(command: str, before: bool) -> None:
    args = (
        'timeout-ms="1000" text "timeout_ms=5000"'
        if before
        else ('text "timeout_ms=5000" timeout-ms="1000"')
    )
    spec = TaskManager().parse_script(f"home\n{command} {args}")
    if command == "wait":
        result = spec["steps"][1]
        expected = {"wait": "text", "text": "timeout_ms=5000", "timeout_ms": 1000}
    else:
        result = spec["steps"][0]["verify"][0] if command == "verify" else spec["verifiers"][0]
        expected = {"type": "text", "text": "timeout_ms=5000", "timeout_ms": 1000}
    assert result == expected


def test_options_keep_quoted_values_booleans_and_order() -> None:
    spec = TaskManager().parse_script(
        'launch wait_debugger=true com.example.app activity="Main Activity"\n'
        'swipe duration-ms="300" down distance="0.8"\n'
        'snapshot mode="full"\n'
    )
    assert spec["steps"] == [
        {
            "app": "launch",
            "package": "com.example.app",
            "wait_debugger": True,
            "activity": "Main Activity",
        },
        {"action": "swipe", "direction": "down", "duration_ms": 300, "distance": 0.8},
        {"ui": "snapshot", "mode": "full"},
    ]


@pytest.mark.parametrize("selector", ['text:"x=y"', 'text-contains:"x=y"', 'label:"x=y"'])
def test_selectors_with_equals_are_values(selector: str) -> None:
    spec = TaskManager().parse_script(f"tap {selector} || id:com.example:id/input")
    assert spec["steps"] == [{"action": "tap", "ref": f"{selector} || id:com.example:id/input"}]


def test_metadata_and_whitespace_are_unchanged() -> None:
    spec = TaskManager().parse_script(
        'name "x=y"\ndescription "x=y # text"\nsession s-abc123\n'
        '\tset-text\t^g1a1\t"first x=y"\t"last"\t# ignored\n'
    )
    assert spec["name"] == "x=y"
    assert spec["description"] == "x=y # text"
    assert spec["session_id"] == "s-abc123"
    assert spec["steps"] == [{"action": "set_text", "ref": "^g1a1", "text": "first x=y last"}]
