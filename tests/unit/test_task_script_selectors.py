"""Task scripts preserve selector quoting through their shell-style tokenization."""

from __future__ import annotations

import pytest

from android_emu_agent.actions.selector import FallbackSelector, parse_selector
from android_emu_agent.tasks import TaskManager


@pytest.mark.parametrize("command", ["tap", "long-tap", "clear", "wait exists", "wait gone"])
def test_script_action_and_wait_preserve_compound_selector(command: str) -> None:
    spec = TaskManager().parse_script(f'{command} text:"Sign in" enabled:true')
    selector = parse_selector(spec["steps"][0]["ref"])
    assert selector.to_u2_kwargs() == {"text": "Sign in", "enabled": True}


@pytest.mark.parametrize("command", ["verify", "expect"])
@pytest.mark.parametrize("operation", ["exists", "gone"])
def test_script_verifiers_preserve_quoted_selector(command: str, operation: str) -> None:
    spec = TaskManager().parse_script(
        f'home\n{command} {operation} desc:"Meeting: 10:30" enabled:true timeout_ms=1000'
    )
    verifier = spec["steps"][0]["verify"][0] if command == "verify" else spec["verifiers"][0]
    assert parse_selector(verifier["ref"]).to_u2_kwargs() == {
        "description": "Meeting: 10:30",
        "enabled": True,
    }
    assert verifier["timeout_ms"] == 1000


@pytest.mark.parametrize("label", ["A || B", "Don't stop", "Meeting: 10:30"])
def test_script_fallback_preserves_literal_selector_content(label: str) -> None:
    spec = TaskManager().parse_script(f'tap text:"{label}" || id:com.example:id/button')
    selector = parse_selector(spec["steps"][0]["ref"])
    assert isinstance(selector, FallbackSelector)
    assert [option.to_u2_kwargs() for option in selector.options] == [
        {"text": label},
        {"resourceId": "com.example:id/button"},
    ]


def test_set_text_preserves_selector_quotes_and_decodes_text_once() -> None:
    spec = TaskManager().parse_script('set-text desc:"Don\'t edit" "x=y # kept"')
    step = spec["steps"][0]
    assert parse_selector(step["ref"]).to_u2_kwargs() == {"description": "Don't edit"}
    assert step["text"] == "x=y # kept"


@pytest.mark.parametrize(
    "selector",
    [
        'text:"Sign in" enabled:true',
        "'text:\"Sign in\" enabled:true'",
        '"text:\\"Sign in\\" enabled:true"',
    ],
)
def test_script_accepts_direct_and_whole_token_selector_quotes(selector: str) -> None:
    spec = TaskManager().parse_script(f"tap {selector}")
    assert parse_selector(spec["steps"][0]["ref"]).to_u2_kwargs() == {
        "text": "Sign in",
        "enabled": True,
    }


@pytest.mark.parametrize("pattern", [r"^Order \d+$", r"^Order \\d+$"])
def test_script_regex_keeps_shlex_backslash_semantics(pattern: str) -> None:
    spec = TaskManager().parse_script(f'tap text-matches:"{pattern}" enabled:true')
    assert parse_selector(spec["steps"][0]["ref"]).to_u2_kwargs() == {
        "textMatches": r"^Order \d+$",
        "enabled": True,
    }


@pytest.mark.parametrize(
    ("container", "description"),
    [
        ('desc:"Don\'t scroll"', "Don't scroll"),
        ("'desc:\"Scroll here\" enabled:true'", "Scroll here"),
    ],
)
def test_script_swipe_container_preserves_selector_quotes(container: str, description: str) -> None:
    spec = TaskManager().parse_script(f"swipe up container={container} distance=0.5")
    step = spec["steps"][0]
    selector = parse_selector(step["container"])
    assert selector.to_u2_kwargs()["description"] == description
    assert step["distance"] == 0.5


def test_script_text_conditions_are_plain_data() -> None:
    spec = TaskManager().parse_script('wait text text:"Sign in" timeout_ms=1000')
    assert spec["steps"][0] == {"wait": "text", "text": "text:Sign in", "timeout_ms": 1000}


@pytest.mark.parametrize(
    ("source", "text"),
    [
        (r"text:Sign\ in", "Sign in"),
        (r'text:"foo\\bar"', r"foo\bar"),
        ('text:"Sign "in', "Sign in"),
        ("text:'Say \"Hi there\"'", 'Say "Hi there"'),
        (r'text:"A\"||id:b||text:\"C"', 'A"||id:b||text:"C'),
        (r'text:"foo\\"', "foo\\"),
    ],
)
def test_script_preserves_existing_shell_decoding(source: str, text: str) -> None:
    spec = TaskManager().parse_script(f"tap {source}")
    assert parse_selector(spec["steps"][0]["ref"]).to_u2_kwargs() == {"text": text}


@pytest.mark.parametrize(
    "source",
    [
        'text:"Sign in"||desc:"Log in"',
        'text:"Sign in" || desc:"Log in"',
        'text:"Sign in"|| desc:"Log in"',
        'text:"Sign in" ||desc:"Log in"',
    ],
)
def test_script_fallback_separator_does_not_require_spaces(source: str) -> None:
    spec = TaskManager().parse_script(f"tap {source}")
    selector = parse_selector(spec["steps"][0]["ref"])
    assert isinstance(selector, FallbackSelector)
    assert [option.to_u2_kwargs() for option in selector.options] == [
        {"text": "Sign in"},
        {"description": "Log in"},
    ]


@pytest.mark.parametrize("source", ['id:button||text:"A || B"', 'id:button ||text:"A || B"'])
def test_script_compact_fallback_preserves_literal_pipes(source: str) -> None:
    spec = TaskManager().parse_script(f"tap {source}")
    selector = parse_selector(spec["steps"][0]["ref"])
    assert isinstance(selector, FallbackSelector)
    assert [option.to_u2_kwargs() for option in selector.options] == [
        {"resourceId": "button"},
        {"text": "A || B"},
    ]


def test_script_shell_valid_quote_concatenation_does_not_raise() -> None:
    spec = TaskManager().parse_script(r"tap text:'a\'x'foo||id:b'")
    selector = parse_selector(spec["steps"][0]["ref"])
    assert isinstance(selector, FallbackSelector)
    assert [option.to_u2_kwargs() for option in selector.options] == [
        {"text": r"a\xfoo"},
        {"resourceId": "b"},
    ]


def test_script_single_quote_escape_mismatch_keeps_real_fallback() -> None:
    spec = TaskManager().parse_script(r"tap text:'a\'x||id:b")
    selector = parse_selector(spec["steps"][0]["ref"])
    assert isinstance(selector, FallbackSelector)
    assert [option.to_u2_kwargs() for option in selector.options] == [
        {"text": r"a\x"},
        {"resourceId": "b"},
    ]
