"""Error model - Actionable errors with remediation hints."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentError(Exception):
    """
    Base error with context and remediation guidance.

    All errors should be actionable - tell the caller what went wrong
    and what they can do about it.
    """

    code: str
    message: str
    context: dict[str, Any] = field(default_factory=dict)
    remediation: str = ""

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "code": self.code,
            "message": self.message,
            "context": self.context,
            "remediation": self.remediation,
        }


# Specific error constructors for common cases


def stale_ref_error(ref: str, ref_generation: int, current_generation: int) -> AgentError:
    """Create error for stale ref usage."""
    return AgentError(
        code="ERR_STALE_REF",
        message=f"Ref {ref} is from generation {ref_generation}, current is {current_generation}",
        context={
            "ref": ref,
            "ref_generation": ref_generation,
            "current_generation": current_generation,
        },
        remediation="Take a new snapshot with 'ui snapshot' and use fresh ^refs",
    )


def not_found_error(ref_or_selector: str, locator: dict[str, Any] | None = None) -> AgentError:
    """Create error for element not found."""
    return AgentError(
        code="ERR_NOT_FOUND",
        message=f"Element not found: {ref_or_selector}",
        context={"target": ref_or_selector, "locator": locator},
        remediation="Take a new snapshot with 'ui snapshot' and verify element exists",
    )


def blocked_input_error(reason: str) -> AgentError:
    """Create error for blocked input (overlay, IME, security)."""
    return AgentError(
        code="ERR_BLOCKED_INPUT",
        message=f"Input blocked: {reason}",
        context={"reason": reason},
        remediation="Try 'wait idle', 'back', or check for system dialogs",
    )


def timeout_error(
    operation: str, timeout_ms: float, last_context: dict[str, Any] | None = None
) -> AgentError:
    """Create error for timeout."""
    return AgentError(
        code="ERR_TIMEOUT",
        message=f"Operation timed out: {operation}",
        context={"operation": operation, "timeout_ms": timeout_ms, "last_context": last_context},
        remediation="Increase timeout or check if condition can be met",
    )


def device_offline_error(serial: str) -> AgentError:
    """Create error for offline device."""
    return AgentError(
        code="ERR_DEVICE_OFFLINE",
        message=f"Device offline: {serial}",
        context={"serial": serial},
        remediation="Check device connection with 'devices list' and reconnect",
    )


def permission_error(operation: str) -> AgentError:
    """Create error for permission denied."""
    return AgentError(
        code="ERR_PERMISSION",
        message=f"Permission denied: {operation}",
        context={"operation": operation},
        remediation="Check device is rooted or emulator has required permissions",
    )


def session_expired_error(session_id: str) -> AgentError:
    """Create error for expired session."""
    return AgentError(
        code="ERR_SESSION_EXPIRED",
        message=f"Session expired: {session_id}",
        context={"session_id": session_id},
        remediation="Start a new session with 'session start --device <serial>'",
    )


def not_emulator_error(serial: str) -> AgentError:
    """Create error for non-emulator device."""
    return AgentError(
        code="ERR_NOT_EMULATOR",
        message=f"Not an emulator: {serial}",
        context={"serial": serial},
        remediation="Snapshots only work on emulators. Use a serial like 'emulator-5554'.",
    )


def console_connect_error(port: int) -> AgentError:
    """Create error for emulator console connection failure."""
    return AgentError(
        code="ERR_CONSOLE_CONNECT",
        message=f"Cannot connect to emulator console on port {port}",
        context={"port": port},
        remediation="Ensure emulator is running and console port is accessible.",
    )


def snapshot_failed_error(name: str, reason: str) -> AgentError:
    """Create error for snapshot operation failure."""
    return AgentError(
        code="ERR_SNAPSHOT_FAILED",
        message=f"Snapshot '{name}' failed: {reason}",
        context={"name": name, "reason": reason},
        remediation="Check snapshot name exists with 'emulator -avd <name> -list-snapshots'.",
    )


def invalid_package_error(package: str) -> AgentError:
    """Create error for invalid package name."""
    return AgentError(
        code="ERR_INVALID_PACKAGE",
        message=f"Invalid package name: {package}",
        context={"package": package},
        remediation="Package names must be like 'com.example.app'.",
    )


def package_not_found_error(package: str) -> AgentError:
    """Create error for package not installed."""
    return AgentError(
        code="ERR_PACKAGE_NOT_FOUND",
        message=f"Package not found: {package}",
        context={"package": package},
        remediation="Check package is installed with 'adb shell pm list packages'.",
    )


def launch_failed_error(package: str, reason: str) -> AgentError:
    """Create error for app launch failure."""
    return AgentError(
        code="ERR_LAUNCH_FAILED",
        message=f"Failed to launch {package}: {reason}",
        context={"package": package, "reason": reason},
        remediation="Verify package is installed and has a launchable activity.",
    )


def invalid_uri_error(uri: str) -> AgentError:
    """Create error for invalid URI."""
    return AgentError(
        code="ERR_INVALID_URI",
        message=f"Invalid URI: {uri}",
        context={"uri": uri},
        remediation="URI must include scheme (e.g., https:// or myapp://).",
    )


def invalid_selector_error(selector: str) -> AgentError:
    """Create error for invalid selector syntax."""
    return AgentError(
        code="ERR_INVALID_SELECTOR",
        message=f"Invalid selector: {selector}",
        context={"selector": selector},
        remediation='Use ^ref, text:"...", id:..., desc:"...", or coords:x,y',
    )


def adb_not_found_error() -> AgentError:
    """Create error for missing adb binary."""
    return AgentError(
        code="ERR_ADB_NOT_FOUND",
        message="adb command not found",
        context={},
        remediation="Install Android platform-tools and ensure adb is in PATH.",
    )


def adb_command_error(command: str, reason: str) -> AgentError:
    """Create error for adb command failure."""
    return AgentError(
        code="ERR_ADB_COMMAND",
        message=f"adb command failed: {command}",
        context={"command": command, "reason": reason},
        remediation="Check adb connection and command arguments, then retry.",
    )


def process_not_found_error(package: str) -> AgentError:
    """Create error for missing process."""
    return AgentError(
        code="ERR_PROCESS_NOT_FOUND",
        message=f"Process not running for {package}",
        context={"package": package},
        remediation="Ensure the app is running and try again.",
    )


def file_not_found_error(path: str) -> AgentError:
    """Create error for missing local file."""
    return AgentError(
        code="ERR_FILE_NOT_FOUND",
        message=f"Local file not found: {path}",
        context={"path": path},
        remediation="Verify the local path and try again.",
    )
