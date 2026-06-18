"""Tests for selector types and parser."""

from __future__ import annotations

import pytest

from android_emu_agent.actions.selector import (
    ClassSelector,
    CoordsSelector,
    DescContainsSelector,
    DescMatchesSelector,
    DescSelector,
    FallbackSelector,
    LabelSelector,
    RefSelector,
    ResourceIdMatchesSelector,
    ResourceIdSelector,
    TextContainsSelector,
    TextMatchesSelector,
    TextSelector,
    U2Selector,
    parse_selector,
)
from android_emu_agent.errors import AgentError


class TestRefSelector:
    """Tests for RefSelector."""

    def test_parse_ref_selector(self) -> None:
        """Should parse ^ref syntax."""
        result = parse_selector("^a1")
        assert isinstance(result, RefSelector)
        assert result.ref == "^a1"

    def test_ref_to_u2_kwargs_returns_empty(self) -> None:
        """RefSelector returns empty kwargs (resolved elsewhere)."""
        selector = RefSelector(ref="^a5")
        assert selector.to_u2_kwargs() == {}


class TestTextSelector:
    """Tests for TextSelector."""

    def test_parse_text_with_double_quotes(self) -> None:
        """Should parse text:"..." syntax."""
        result = parse_selector('text:"Sign in"')
        assert isinstance(result, TextSelector)
        assert result.text == "Sign in"

    def test_parse_text_with_single_quotes(self) -> None:
        """Should parse text:'...' syntax."""
        result = parse_selector("text:'Hello World'")
        assert isinstance(result, TextSelector)
        assert result.text == "Hello World"

    def test_parse_text_without_quotes(self) -> None:
        """Should parse text:... without quotes."""
        result = parse_selector("text:Submit")
        assert isinstance(result, TextSelector)
        assert result.text == "Submit"

    def test_text_to_u2_kwargs(self) -> None:
        """TextSelector returns text kwargs."""
        selector = TextSelector(text="Click me")
        assert selector.to_u2_kwargs() == {"text": "Click me"}

    def test_parse_text_contains(self) -> None:
        """Should parse text-contains: syntax."""
        result = parse_selector('text-contains:"Sign"')
        assert isinstance(result, TextContainsSelector)
        assert result.to_u2_kwargs() == {"textContains": "Sign"}

    def test_parse_text_matches(self) -> None:
        """Should parse text-matches: syntax."""
        result = parse_selector("text-matches:^Sign.*")
        assert isinstance(result, TextMatchesSelector)
        assert result.to_u2_kwargs() == {"textMatches": "^Sign.*"}

    def test_parse_label_alias(self) -> None:
        """Should parse label: syntax as content description selector."""
        result = parse_selector('label:"Login"')
        assert isinstance(result, LabelSelector)
        assert result.to_u2_kwargs() == {"description": "Login"}

    def test_parse_compound_selector_with_state_filter(self) -> None:
        """Should parse uiautomator2-compatible compound selector filters."""
        result = parse_selector('text:"Sign in" enabled:true clickable:false')
        assert isinstance(result, U2Selector)
        assert result.to_u2_kwargs() == {
            "text": "Sign in",
            "enabled": True,
            "clickable": False,
        }

    def test_parse_fallback_selector(self) -> None:
        """Should parse ordered fallback selectors separated by ||."""
        result = parse_selector('text:"Sign in" || id:com.example:id/login')
        assert isinstance(result, FallbackSelector)
        assert len(result.options) == 2
        assert result.options[0].to_u2_kwargs() == {"text": "Sign in"}
        assert result.options[1].to_u2_kwargs() == {"resourceId": "com.example:id/login"}


class TestResourceIdSelector:
    """Tests for ResourceIdSelector."""

    def test_parse_resource_id(self) -> None:
        """Should parse id:... syntax."""
        result = parse_selector("id:com.example:id/button")
        assert isinstance(result, ResourceIdSelector)
        assert result.resource_id == "com.example:id/button"

    def test_resource_id_to_u2_kwargs(self) -> None:
        """ResourceIdSelector returns resourceId kwargs."""
        selector = ResourceIdSelector(resource_id="com.app:id/submit")
        assert selector.to_u2_kwargs() == {"resourceId": "com.app:id/submit"}

    def test_parse_resource_id_matches(self) -> None:
        """Should parse id-matches: syntax."""
        result = parse_selector("id-matches:.*submit")
        assert isinstance(result, ResourceIdMatchesSelector)
        assert result.to_u2_kwargs() == {"resourceIdMatches": ".*submit"}


class TestDescSelector:
    """Tests for DescSelector."""

    def test_parse_desc_with_quotes(self) -> None:
        """Should parse desc:"..." syntax."""
        result = parse_selector('desc:"Login button"')
        assert isinstance(result, DescSelector)
        assert result.desc == "Login button"

    def test_parse_desc_without_quotes(self) -> None:
        """Should parse desc:... without quotes."""
        result = parse_selector("desc:Submit")
        assert isinstance(result, DescSelector)
        assert result.desc == "Submit"

    def test_desc_to_u2_kwargs(self) -> None:
        """DescSelector returns description kwargs."""
        selector = DescSelector(desc="Search button")
        assert selector.to_u2_kwargs() == {"description": "Search button"}

    def test_parse_desc_contains(self) -> None:
        """Should parse desc-contains: syntax."""
        result = parse_selector("desc-contains:Search")
        assert isinstance(result, DescContainsSelector)
        assert result.to_u2_kwargs() == {"descriptionContains": "Search"}

    def test_parse_desc_matches(self) -> None:
        """Should parse desc-matches: syntax."""
        result = parse_selector("desc-matches:^Search")
        assert isinstance(result, DescMatchesSelector)
        assert result.to_u2_kwargs() == {"descriptionMatches": "^Search"}


class TestClassSelector:
    """Tests for ClassSelector."""

    def test_parse_class_selector(self) -> None:
        """Should parse class: syntax."""
        result = parse_selector("class:android.widget.Button")
        assert isinstance(result, ClassSelector)
        assert result.to_u2_kwargs() == {"className": "android.widget.Button"}


class TestCoordsSelector:
    """Tests for CoordsSelector."""

    def test_parse_coords(self) -> None:
        """Should parse coords:x,y syntax."""
        result = parse_selector("coords:540,1200")
        assert isinstance(result, CoordsSelector)
        assert result.x == 540
        assert result.y == 1200

    def test_coords_to_u2_kwargs_returns_empty(self) -> None:
        """CoordsSelector returns empty kwargs (handled specially)."""
        selector = CoordsSelector(x=100, y=200)
        assert selector.to_u2_kwargs() == {}


class TestInvalidSelectors:
    """Tests for invalid selector handling."""

    def test_invalid_selector_raises_error(self) -> None:
        """Invalid selector syntax raises ERR_INVALID_SELECTOR."""
        with pytest.raises(AgentError) as exc_info:
            parse_selector("invalid:syntax")
        assert exc_info.value.code == "ERR_INVALID_SELECTOR"
        assert "invalid:syntax" in exc_info.value.message

    def test_invalid_coords_format_raises_error(self) -> None:
        """Invalid coords format raises ERR_INVALID_SELECTOR."""
        with pytest.raises(AgentError) as exc_info:
            parse_selector("coords:abc,def")
        assert exc_info.value.code == "ERR_INVALID_SELECTOR"

    def test_missing_coords_value_raises_error(self) -> None:
        """Missing coords value raises ERR_INVALID_SELECTOR."""
        with pytest.raises(AgentError) as exc_info:
            parse_selector("coords:100")
        assert exc_info.value.code == "ERR_INVALID_SELECTOR"

    def test_empty_selector_raises_error(self) -> None:
        """Empty selector raises ERR_INVALID_SELECTOR."""
        with pytest.raises(AgentError) as exc_info:
            parse_selector("")
        assert exc_info.value.code == "ERR_INVALID_SELECTOR"

    def test_empty_fallback_branch_raises_error(self) -> None:
        """Fallback selectors must contain both alternatives."""
        with pytest.raises(AgentError) as exc_info:
            parse_selector("text:OK ||")
        assert exc_info.value.code == "ERR_INVALID_SELECTOR"
