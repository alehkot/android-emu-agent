"""Validation helpers for user input."""

from __future__ import annotations

import re

from android_emu_agent.errors import invalid_package_error, invalid_uri_error, not_emulator_error

# Package name: starts with letter, segments separated by dots, each segment alphanumeric/underscore
PACKAGE_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]*(\.[a-zA-Z][a-zA-Z0-9_]*)+$")


def validate_package(package: str) -> None:
    """Validate Android package name format.

    Args:
        package: Package name to validate

    Raises:
        AgentError: If package name is invalid
    """
    if not PACKAGE_PATTERN.match(package):
        raise invalid_package_error(package)


def validate_uri(uri: str) -> None:
    """Validate URI has a scheme.

    Args:
        uri: URI to validate

    Raises:
        AgentError: If URI is invalid
    """
    if not uri or "://" not in uri:
        raise invalid_uri_error(uri)


def get_console_port(serial: str) -> int:
    """Extract emulator console port from serial.

    Args:
        serial: Device serial (e.g., 'emulator-5554')

    Returns:
        Console port number

    Raises:
        AgentError: If serial is not an emulator
    """
    if not serial.startswith("emulator-"):
        raise not_emulator_error(serial)

    try:
        port = int(serial.split("-")[1])
    except (IndexError, ValueError) as err:
        raise not_emulator_error(serial) from err

    return port
