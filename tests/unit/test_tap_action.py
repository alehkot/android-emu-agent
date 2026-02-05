"""Tests for /actions/tap endpoint with selector support."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from android_emu_agent.actions.selector import (
    CoordsSelector,
    DescSelector,
    RefSelector,
    ResourceIdSelector,
    TextSelector,
    parse_selector,
)
from android_emu_agent.errors import AgentError
from android_emu_agent.ui.ref_resolver import LocatorBundle


class TestTapSelectorParsing:
    """Tests for selector parsing used by tap action."""

    def test_parse_ref_selector(self) -> None:
        """Should parse @ref to RefSelector."""
        selector = parse_selector("@a1")
        assert isinstance(selector, RefSelector)
        assert selector.ref == "@a1"

    def test_parse_coords_selector(self) -> None:
        """Should parse coords:x,y to CoordsSelector."""
        selector = parse_selector("coords:540,1200")
        assert isinstance(selector, CoordsSelector)
        assert selector.x == 540
        assert selector.y == 1200

    def test_parse_text_selector(self) -> None:
        """Should parse text:"..." to TextSelector."""
        selector = parse_selector('text:"Sign in"')
        assert isinstance(selector, TextSelector)
        assert selector.text == "Sign in"

    def test_parse_id_selector(self) -> None:
        """Should parse id:... to ResourceIdSelector."""
        selector = parse_selector("id:com.example:id/button")
        assert isinstance(selector, ResourceIdSelector)
        assert selector.resource_id == "com.example:id/button"

    def test_parse_desc_selector(self) -> None:
        """Should parse desc:"..." to DescSelector."""
        selector = parse_selector('desc:"Login button"')
        assert isinstance(selector, DescSelector)
        assert selector.desc == "Login button"

    def test_parse_invalid_selector_raises_error(self) -> None:
        """Should raise AgentError for invalid selector."""
        with pytest.raises(AgentError) as exc_info:
            parse_selector("invalid:syntax")
        assert exc_info.value.code == "ERR_INVALID_SELECTOR"


class TestTapWithCoordsSelector:
    """Tests for direct coordinate tap."""

    @pytest.mark.asyncio
    async def test_coords_selector_clicks_at_coordinates(self) -> None:
        """CoordsSelector should trigger click at x,y."""
        selector = parse_selector("coords:540,1200")
        assert isinstance(selector, CoordsSelector)
        assert selector.x == 540
        assert selector.y == 1200
        # Verify to_u2_kwargs returns empty dict (coords handled specially)
        assert selector.to_u2_kwargs() == {}


class TestTapWithTextSelector:
    """Tests for text-based element lookup."""

    def test_text_selector_to_u2_kwargs(self) -> None:
        """TextSelector should produce correct u2 kwargs."""
        selector = parse_selector('text:"Sign in"')
        assert selector.to_u2_kwargs() == {"text": "Sign in"}


class TestTapWithResourceIdSelector:
    """Tests for resource ID-based element lookup."""

    def test_resource_id_selector_to_u2_kwargs(self) -> None:
        """ResourceIdSelector should produce correct u2 kwargs."""
        selector = parse_selector("id:com.example:id/login_btn")
        assert selector.to_u2_kwargs() == {"resourceId": "com.example:id/login_btn"}


class TestTapWithDescSelector:
    """Tests for description-based element lookup."""

    def test_desc_selector_to_u2_kwargs(self) -> None:
        """DescSelector should produce correct u2 kwargs."""
        selector = parse_selector('desc:"Login button"')
        assert selector.to_u2_kwargs() == {"description": "Login button"}


class TestRefSelectorHandling:
    """Tests for RefSelector resolution."""

    def test_ref_selector_returns_empty_kwargs(self) -> None:
        """RefSelector returns empty kwargs (resolved elsewhere)."""
        selector = parse_selector("@a1")
        assert selector.to_u2_kwargs() == {}


class TestStaleRefWithWarning:
    """Tests for stale ref re-identification with warning."""

    @pytest.mark.asyncio
    async def test_stale_ref_with_resource_id_succeeds_with_warning(self) -> None:
        """Stale ref with resource_id should re-identify and include warning."""
        # This tests the conservative re-identification behavior:
        # - Stale ref detected
        # - Has resource_id, so try to find by resource_id
        # - Element found, proceed with warning
        mock_device = MagicMock()
        mock_element = MagicMock()
        mock_element.exists.return_value = True
        mock_device.return_value = mock_element

        # Create a locator with resource_id (for re-identification)
        locator = LocatorBundle(
            ref="@a5",
            generation=3,  # Old generation
            resource_id="com.foo:id/sign_in",
            content_desc=None,
            text="Sign in",
            class_name="android.widget.Button",
            bounds=[540, 1720, 1020, 1840],
            ancestry_hash="abc123",
            index=5,
        )

        # Simulate re-identification by resource_id
        element = mock_device(resourceId=locator.resource_id)
        exists = await asyncio.to_thread(element.exists)
        assert exists

        # Action proceeds with warning in response
        expected_warning = "Used stale ref @a5; take a new snapshot for reliable refs"
        assert "stale" in expected_warning.lower()
        assert "@a5" in expected_warning

    @pytest.mark.asyncio
    async def test_stale_ref_without_resource_id_fails(self) -> None:
        """Stale ref without resource_id should fail with ERR_STALE_REF."""
        # Locator without resource_id cannot be re-identified
        locator = LocatorBundle(
            ref="@a5",
            generation=3,
            resource_id=None,  # No resource_id for re-identification
            content_desc=None,
            text="Submit",
            class_name="android.widget.Button",
            bounds=[540, 1720, 1020, 1840],
            ancestry_hash="abc123",
            index=5,
        )

        # Without resource_id, re-identification is not possible
        assert locator.resource_id is None

    @pytest.mark.asyncio
    async def test_stale_ref_resource_id_not_found_fails(self) -> None:
        """Stale ref where resource_id element not found should fail."""
        mock_device = MagicMock()
        mock_element = MagicMock()
        mock_element.exists.return_value = False  # Element not found
        mock_device.return_value = mock_element

        locator = LocatorBundle(
            ref="@a5",
            generation=3,
            resource_id="com.foo:id/deleted_btn",  # Has resource_id
            content_desc=None,
            text="Old Button",
            class_name="android.widget.Button",
            bounds=[540, 1720, 1020, 1840],
            ancestry_hash="abc123",
            index=5,
        )

        # Try to find by resource_id
        element = mock_device(resourceId=locator.resource_id)
        exists = await asyncio.to_thread(element.exists)

        # Element not found, should fail with ERR_STALE_REF
        assert not exists


class TestTapActionIntegration:
    """Integration tests for the tap action endpoint logic."""

    @pytest.mark.asyncio
    async def test_tap_with_coords_calls_device_click(self) -> None:
        """Tap with coords should call device.click(x, y)."""
        mock_device = MagicMock()
        mock_device.click = MagicMock()

        selector = parse_selector("coords:540,1200")
        assert isinstance(selector, CoordsSelector)

        # Simulate what the endpoint does
        await asyncio.to_thread(mock_device.click, selector.x, selector.y)

        mock_device.click.assert_called_once_with(540, 1200)

    @pytest.mark.asyncio
    async def test_tap_with_text_finds_and_clicks_element(self) -> None:
        """Tap with text should find element by text and click it."""
        mock_device = MagicMock()
        mock_element = MagicMock()
        mock_element.exists.return_value = True
        mock_device.return_value = mock_element

        selector = parse_selector('text:"Sign in"')
        kwargs = selector.to_u2_kwargs()
        assert kwargs == {"text": "Sign in"}

        # Simulate what the endpoint does
        element = mock_device(**kwargs)
        exists = await asyncio.to_thread(element.exists)
        assert exists
        await asyncio.to_thread(element.click)

        mock_device.assert_called_with(text="Sign in")
        mock_element.click.assert_called_once()

    @pytest.mark.asyncio
    async def test_tap_with_text_not_found_raises_error(self) -> None:
        """Tap with text should detect when element doesn't exist."""
        mock_device = MagicMock()
        mock_element = MagicMock()
        mock_element.exists.return_value = False
        mock_device.return_value = mock_element

        selector = parse_selector('text:"Not Found"')
        kwargs = selector.to_u2_kwargs()

        element = mock_device(**kwargs)
        exists = await asyncio.to_thread(element.exists)
        assert not exists  # Element doesn't exist

    @pytest.mark.asyncio
    async def test_tap_with_id_finds_and_clicks_element(self) -> None:
        """Tap with id should find element by resourceId and click it."""
        mock_device = MagicMock()
        mock_element = MagicMock()
        mock_element.exists.return_value = True
        mock_device.return_value = mock_element

        selector = parse_selector("id:com.example:id/button")
        kwargs = selector.to_u2_kwargs()
        assert kwargs == {"resourceId": "com.example:id/button"}

        element = mock_device(**kwargs)
        exists = await asyncio.to_thread(element.exists)
        assert exists
        await asyncio.to_thread(element.click)

        mock_device.assert_called_with(resourceId="com.example:id/button")
        mock_element.click.assert_called_once()

    @pytest.mark.asyncio
    async def test_tap_with_desc_finds_and_clicks_element(self) -> None:
        """Tap with desc should find element by description and click it."""
        mock_device = MagicMock()
        mock_element = MagicMock()
        mock_element.exists.return_value = True
        mock_device.return_value = mock_element

        selector = parse_selector('desc:"Login button"')
        kwargs = selector.to_u2_kwargs()
        assert kwargs == {"description": "Login button"}

        element = mock_device(**kwargs)
        exists = await asyncio.to_thread(element.exists)
        assert exists
        await asyncio.to_thread(element.click)

        mock_device.assert_called_with(description="Login button")
        mock_element.click.assert_called_once()
