"""Pytest configuration and fixtures."""

from __future__ import annotations

from collections.abc import Generator
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, patch

import pytest

if TYPE_CHECKING:
    pass


@pytest.fixture
def mock_adb() -> Generator[MagicMock, None, None]:
    """Mock adbutils for unit tests."""
    with patch("adbutils.adb") as mock:
        # Setup default device list
        mock_device = MagicMock()
        mock_device.serial = "emulator-5554"
        mock_device.prop.model = "Pixel_7"
        mock.device_list.return_value = [mock_device]
        yield mock


@pytest.fixture
def mock_device() -> MagicMock:
    """Mock uiautomator2 device for unit tests."""
    device = MagicMock()

    # Mock common methods
    device.dump_hierarchy.return_value = b"""<?xml version="1.0" encoding="UTF-8"?>
    <hierarchy rotation="0">
        <node class="android.widget.FrameLayout" package="com.test">
            <node class="android.widget.Button"
                  resource-id="com.test:id/button1"
                  text="Click me"
                  clickable="true"
                  bounds="[100,200][300,250]" />
        </node>
    </hierarchy>
    """

    device.info = {"displayWidth": 1080, "displayHeight": 2400}
    device.app_current.return_value = {
        "package": "com.test",
        "activity": ".MainActivity",
    }

    # Mock element finding
    mock_element = MagicMock()
    mock_element.exists.return_value = True
    device.return_value = mock_element

    return device


@pytest.fixture
def sample_hierarchy_xml() -> bytes:
    """Sample UI hierarchy XML for testing."""
    return b"""<?xml version="1.0" encoding="UTF-8"?>
    <hierarchy rotation="0">
        <node class="android.widget.FrameLayout"
              package="com.example"
              clickable="false"
              bounds="[0,0][1080,2400]">
            <node class="android.widget.LinearLayout"
                  clickable="false"
                  bounds="[0,100][1080,2300]">
                <node class="android.widget.TextView"
                      resource-id="com.example:id/title"
                      text="Welcome"
                      clickable="false"
                      bounds="[100,150][980,200]" />
                <node class="android.widget.Button"
                      resource-id="com.example:id/login_button"
                      text="Sign In"
                      content-desc="Login button"
                      clickable="true"
                      enabled="true"
                      bounds="[200,400][880,500]" />
                <node class="android.widget.EditText"
                      resource-id="com.example:id/email_input"
                      text=""
                      content-desc="Email address"
                      clickable="true"
                      focusable="true"
                      editable="true"
                      bounds="[100,550][980,650]" />
                <node class="android.widget.CheckBox"
                      resource-id="com.example:id/remember_me"
                      text="Remember me"
                      clickable="true"
                      checkable="true"
                      checked="false"
                      bounds="[100,700][400,750]" />
            </node>
        </node>
    </hierarchy>
    """


@pytest.fixture
def sample_session_data() -> dict[str, Any]:
    """Sample session data for testing."""
    return {
        "session_id": "s-test123",
        "device_serial": "emulator-5554",
        "generation": 1,
    }


@pytest.fixture
def sample_device_info() -> dict[str, Any]:
    """Sample device info for testing."""
    return {
        "serial": "emulator-5554",
        "sdk": 34,
        "model": "Pixel_7",
    }


@pytest.fixture
def sample_context_info() -> dict[str, Any]:
    """Sample UI context for testing."""
    return {
        "package": "com.example",
        "activity": "com.example.MainActivity",
        "orientation": "PORTRAIT",
        "ime_visible": False,
    }
