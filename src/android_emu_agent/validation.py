"""Validation helpers for user input."""

from __future__ import annotations

import re

from android_emu_agent.errors import (
    invalid_emulator_port_error,
    invalid_package_error,
    invalid_snapshot_name_error,
    invalid_uri_error,
    not_emulator_error,
)

# Package name: starts with letter, segments separated by dots, each segment alphanumeric/underscore
PACKAGE_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]*(\.[a-zA-Z][a-zA-Z0-9_]*)+$")
URI_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:[^\s]+$")
SNAPSHOT_NAME_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
EMULATOR_SERIAL_PATTERN = re.compile(r"^emulator-([0-9]+)$")
EMULATOR_CONSOLE_PORT_MIN = 5554
EMULATOR_CONSOLE_PORT_MAX = 5584


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
    if not URI_PATTERN.fullmatch(uri):
        raise invalid_uri_error(uri)


def validate_snapshot_name(name: str) -> None:
    """Validate an emulator snapshot name before using the line-oriented console protocol."""
    if not SNAPSHOT_NAME_PATTERN.fullmatch(name):
        raise invalid_snapshot_name_error(name)


def validate_emulator_port(port: int) -> None:
    """Validate the Android emulator's supported fixed console port range."""
    if (
        isinstance(port, bool)
        or port < EMULATOR_CONSOLE_PORT_MIN
        or port > EMULATOR_CONSOLE_PORT_MAX
        or port % 2 != 0
    ):
        raise invalid_emulator_port_error(port)


def get_console_port(serial: str) -> int:
    """Extract emulator console port from serial.

    Args:
        serial: Device serial (e.g., 'emulator-5554')

    Returns:
        Console port number

    Raises:
        AgentError: If serial is not an emulator
    """
    match = EMULATOR_SERIAL_PATTERN.fullmatch(serial)
    if not match:
        raise not_emulator_error(serial)
    return int(match.group(1))
