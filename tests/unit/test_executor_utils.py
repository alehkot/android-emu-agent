"""Tests for executor utilities (RetryPolicy, SwipeDirection, swipe coords)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from android_emu_agent.actions.executor import ActionExecutor, RetryPolicy, SwipeDirection
from android_emu_agent.ui.ref_resolver import LocatorBundle


class TestRetryPolicyDefaults:
    """Tests for RetryPolicy default values."""

    def test_default_values(self) -> None:
        """Should have expected default values."""
        policy = RetryPolicy()

        assert policy.max_attempts == 3
        assert policy.base_delay_ms == 300
        assert policy.backoff_multiplier == 2.0
        assert policy.max_delay_ms == 2000


class TestRetryPolicyGetDelay:
    """Tests for RetryPolicy.get_delay method."""

    def test_get_delay_first_attempt(self) -> None:
        """First attempt (0) should return base delay."""
        policy = RetryPolicy()

        delay = policy.get_delay(0)

        assert delay == 300  # base_delay_ms

    def test_get_delay_with_backoff(self) -> None:
        """Subsequent attempts should apply exponential backoff."""
        policy = RetryPolicy()

        # attempt 0: 300 * 2^0 = 300
        assert policy.get_delay(0) == 300
        # attempt 1: 300 * 2^1 = 600
        assert policy.get_delay(1) == 600
        # attempt 2: 300 * 2^2 = 1200
        assert policy.get_delay(2) == 1200

    def test_get_delay_respects_max(self) -> None:
        """Delay should be capped at max_delay_ms."""
        policy = RetryPolicy()

        # attempt 3: 300 * 2^3 = 2400, but capped at 2000
        assert policy.get_delay(3) == 2000
        # attempt 4: 300 * 2^4 = 4800, but capped at 2000
        assert policy.get_delay(4) == 2000


class TestRetryPolicyCustom:
    """Tests for custom RetryPolicy configurations."""

    def test_custom_policy(self) -> None:
        """Should respect custom configuration."""
        policy = RetryPolicy(
            max_attempts=5,
            base_delay_ms=100,
            backoff_multiplier=1.5,
            max_delay_ms=500,
        )

        assert policy.max_attempts == 5
        assert policy.base_delay_ms == 100
        assert policy.backoff_multiplier == 1.5
        assert policy.max_delay_ms == 500

        # attempt 0: 100 * 1.5^0 = 100
        assert policy.get_delay(0) == 100
        # attempt 1: 100 * 1.5^1 = 150
        assert policy.get_delay(1) == 150
        # attempt 2: 100 * 1.5^2 = 225
        assert policy.get_delay(2) == 225
        # attempt 3: 100 * 1.5^3 = 337.5 -> 337
        assert policy.get_delay(3) == 337
        # attempt 4: 100 * 1.5^4 = 506.25 -> capped at 500
        assert policy.get_delay(4) == 500


class TestSwipeDirection:
    """Tests for SwipeDirection enum."""

    def test_directions_exist(self) -> None:
        """Should have all four directions."""
        assert SwipeDirection.UP.value == "up"
        assert SwipeDirection.DOWN.value == "down"
        assert SwipeDirection.LEFT.value == "left"
        assert SwipeDirection.RIGHT.value == "right"

    def test_from_string(self) -> None:
        """Should parse from string."""
        assert SwipeDirection("up") == SwipeDirection.UP
        assert SwipeDirection("down") == SwipeDirection.DOWN
        assert SwipeDirection("left") == SwipeDirection.LEFT
        assert SwipeDirection("right") == SwipeDirection.RIGHT

    def test_iteration(self) -> None:
        """Should be iterable with exactly four members."""
        directions = list(SwipeDirection)
        assert len(directions) == 4
        assert SwipeDirection.UP in directions
        assert SwipeDirection.DOWN in directions
        assert SwipeDirection.LEFT in directions
        assert SwipeDirection.RIGHT in directions


class TestCalculateSwipeCoords:
    """Tests for ActionExecutor._calculate_swipe_coords method."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.executor = ActionExecutor()
        # Standard test bounds: [left, top, right, bottom]
        # Creates a 200x400 container centered at (200, 300)
        self.bounds = [100, 100, 300, 500]

    def test_swipe_up_coords(self) -> None:
        """Swipe UP should start below center, end above center."""
        start, end = self.executor._calculate_swipe_coords(
            self.bounds, SwipeDirection.UP, distance=0.5
        )

        # Center: (200, 300), height=400, offset_y = 400 * 0.5 / 2 = 100
        # Start: (200, 300 + 100) = (200, 400)
        # End: (200, 300 - 100) = (200, 200)
        assert start == (200, 400)
        assert end == (200, 200)
        # X should stay constant
        assert start[0] == end[0]
        # Y should decrease (swipe up)
        assert start[1] > end[1]

    def test_swipe_down_coords(self) -> None:
        """Swipe DOWN should start above center, end below center."""
        start, end = self.executor._calculate_swipe_coords(
            self.bounds, SwipeDirection.DOWN, distance=0.5
        )

        # Center: (200, 300), height=400, offset_y = 400 * 0.5 / 2 = 100
        # Start: (200, 300 - 100) = (200, 200)
        # End: (200, 300 + 100) = (200, 400)
        assert start == (200, 200)
        assert end == (200, 400)
        # X should stay constant
        assert start[0] == end[0]
        # Y should increase (swipe down)
        assert start[1] < end[1]

    def test_swipe_left_coords(self) -> None:
        """Swipe LEFT should start right of center, end left of center."""
        start, end = self.executor._calculate_swipe_coords(
            self.bounds, SwipeDirection.LEFT, distance=0.5
        )

        # Center: (200, 300), width=200, offset_x = 200 * 0.5 / 2 = 50
        # Start: (200 + 50, 300) = (250, 300)
        # End: (200 - 50, 300) = (150, 300)
        assert start == (250, 300)
        assert end == (150, 300)
        # Y should stay constant
        assert start[1] == end[1]
        # X should decrease (swipe left)
        assert start[0] > end[0]

    def test_swipe_right_coords(self) -> None:
        """Swipe RIGHT should start left of center, end right of center."""
        start, end = self.executor._calculate_swipe_coords(
            self.bounds, SwipeDirection.RIGHT, distance=0.5
        )

        # Center: (200, 300), width=200, offset_x = 200 * 0.5 / 2 = 50
        # Start: (200 - 50, 300) = (150, 300)
        # End: (200 + 50, 300) = (250, 300)
        assert start == (150, 300)
        assert end == (250, 300)
        # Y should stay constant
        assert start[1] == end[1]
        # X should increase (swipe right)
        assert start[0] < end[0]

    def test_swipe_with_custom_distance(self) -> None:
        """Distance parameter should control swipe length."""
        # Full distance (1.0) - covers entire container
        start_full, end_full = self.executor._calculate_swipe_coords(
            self.bounds, SwipeDirection.UP, distance=1.0
        )
        # Center: (200, 300), height=400, offset_y = 400 * 1.0 / 2 = 200
        # Start: (200, 300 + 200) = (200, 500)
        # End: (200, 300 - 200) = (200, 100)
        assert start_full == (200, 500)
        assert end_full == (200, 100)

        # Small distance (0.25) - quarter swipe
        start_small, end_small = self.executor._calculate_swipe_coords(
            self.bounds, SwipeDirection.UP, distance=0.25
        )
        # offset_y = 400 * 0.25 / 2 = 50
        # Start: (200, 300 + 50) = (200, 350)
        # End: (200, 300 - 50) = (200, 250)
        assert start_small == (200, 350)
        assert end_small == (200, 250)

        # Verify full swipe covers more distance than small swipe
        full_distance = abs(start_full[1] - end_full[1])
        small_distance = abs(start_small[1] - end_small[1])
        assert full_distance > small_distance


class TestFrameworkFriendlyLookup:
    """Tests for Compose/Litho-friendly element lookup heuristics."""

    @pytest.mark.asyncio
    async def test_find_element_uses_proxy_label_for_generic_host_views(self) -> None:
        """Proxy labels should be used before falling back to coordinates."""
        executor = ActionExecutor()
        device = MagicMock()
        label_element = MagicMock()
        label_element.exists.return_value = True
        coordinate_element = MagicMock()
        coordinate_element.exists.return_value = False

        def _select(**kwargs: str) -> MagicMock:
            if kwargs == {"description": "Settings"}:
                return label_element
            if kwargs == {"text": "Settings"}:
                return label_element
            return coordinate_element

        device.side_effect = _select

        locator = LocatorBundle(
            ref="^a1",
            generation=2,
            resource_id=None,
            content_desc=None,
            text=None,
            class_name="android.view.View",
            bounds=[10, 10, 50, 50],
            ancestry_hash="abc123",
            index=0,
            role="clickable",
            state={"clickable": True},
            label="Settings",
        )

        element = await executor._find_element(device, locator)

        assert element is label_element
        device.assert_any_call(description="Settings")

    @pytest.mark.asyncio
    async def test_find_element_prefers_exact_resource_id_before_label_fallback(self) -> None:
        """Classic IDs and Compose test tags should still be the first lookup strategy."""
        executor = ActionExecutor()
        device = MagicMock()
        resource_element = MagicMock()
        resource_element.exists.return_value = True
        label_element = MagicMock()
        label_element.exists.return_value = True

        def _select(**kwargs: str) -> MagicMock:
            if kwargs == {"resourceId": "compose_login_button"}:
                return resource_element
            if kwargs == {"description": "Login"}:
                return label_element
            return label_element

        device.side_effect = _select

        locator = LocatorBundle(
            ref="^a2",
            generation=2,
            resource_id="compose_login_button",
            content_desc=None,
            text=None,
            class_name="android.view.View",
            bounds=[10, 10, 50, 50],
            ancestry_hash="abc123",
            index=0,
            role="clickable",
            state={"clickable": True},
            label="Login",
        )

        element = await executor._find_element(device, locator)

        assert element is resource_element
        device.assert_called_with(resourceId="compose_login_button")
