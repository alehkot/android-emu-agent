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


def jdk_not_found_error() -> AgentError:
    """Create error for missing JDK."""
    return AgentError(
        code="ERR_JDK_NOT_FOUND",
        message="Java not found in PATH or JAVA_HOME",
        context={},
        remediation=(
            "JDK 17+ required for the debugger. "
            "Install via 'brew install openjdk@17' or use Android Studio's bundled JDK."
        ),
    )


def bridge_not_running_error(reason: str = "") -> AgentError:
    """Create error for bridge JAR not found or not startable."""
    return AgentError(
        code="ERR_BRIDGE_NOT_RUNNING",
        message=f"JDI Bridge not available: {reason}" if reason else "JDI Bridge not available",
        context={"reason": reason},
        remediation=(
            "Build the bridge with './scripts/dev.sh build-bridge' "
            "or set ANDROID_EMU_AGENT_BRIDGE_JAR to the JAR path."
        ),
    )


def bridge_download_failed_error(url: str, reason: str) -> AgentError:
    """Create error for bridge artifact download failures."""
    return AgentError(
        code="ERR_BRIDGE_DOWNLOAD_FAILED",
        message=f"Could not download JDI Bridge artifact: {url}",
        context={"url": url, "reason": reason},
        remediation=(
            "Check network access and release availability, then retry. "
            "You can also run './scripts/dev.sh build-bridge' and set "
            "ANDROID_EMU_AGENT_BRIDGE_JAR to a local JAR path."
        ),
    )


def bridge_crashed_error(reason: str = "") -> AgentError:
    """Create error for bridge subprocess crash."""
    return AgentError(
        code="ERR_BRIDGE_CRASHED",
        message=f"JDI Bridge process crashed: {reason}" if reason else "JDI Bridge process crashed",
        context={"reason": reason},
        remediation="Check daemon logs for bridge stderr output. Retry the command.",
    )


def app_not_debuggable_error(package: str) -> AgentError:
    """Create error for non-debuggable app."""
    return AgentError(
        code="ERR_APP_NOT_DEBUGGABLE",
        message=f"App is not debuggable: {package}",
        context={"package": package},
        remediation=(
            "The app must be built with android:debuggable=true, "
            "or the device must be running a userdebug/eng build."
        ),
    )


def not_suspended_error(thread_name: str | None = None) -> AgentError:
    """Create error for operations that require a suspended thread."""
    thread_hint = f" for thread '{thread_name}'" if thread_name else ""
    return AgentError(
        code="ERR_NOT_SUSPENDED",
        message=f"Thread is not suspended{thread_hint}",
        context={"thread_name": thread_name},
        remediation="Pause execution at a breakpoint or with a step command, then retry.",
    )


def step_timeout_error(action: str, thread_name: str, timeout_seconds: float) -> AgentError:
    """Create error for step command timeout."""
    return AgentError(
        code="ERR_STEP_TIMEOUT",
        message=f"{action} did not complete within {timeout_seconds:g}s on thread '{thread_name}'",
        context={
            "action": action,
            "thread_name": thread_name,
            "timeout_seconds": timeout_seconds,
        },
        remediation=(
            "Use 'debug resume' to continue execution, then set a breakpoint further ahead "
            "or increase --timeout-seconds."
        ),
    )


def object_collected_error() -> AgentError:
    """Create error for stale object references after resume/step."""
    return AgentError(
        code="ERR_OBJECT_COLLECTED",
        message="Object reference is stale",
        context={},
        remediation="Resume to a fresh suspension point (breakpoint/step), then inspect again.",
    )


def class_not_found_error(class_pattern: str) -> AgentError:
    """Create error for unresolved breakpoint class targets."""
    return AgentError(
        code="ERR_CLASS_NOT_FOUND",
        message=f"Breakpoint target class not found: {class_pattern}",
        context={"class_pattern": class_pattern},
        remediation=(
            "Verify the fully-qualified class name and that the class is loaded in the target "
            "process, then retry."
        ),
    )


def breakpoint_invalid_line_error(class_pattern: str, line: int) -> AgentError:
    """Create error for breakpoints set on non-executable lines."""
    return AgentError(
        code="ERR_BREAKPOINT_INVALID_LINE",
        message=f"No executable code at {class_pattern}:{line}",
        context={"class_pattern": class_pattern, "line": line},
        remediation=(
            "Use a valid executable source line (for example from 'debug stack') and retry."
        ),
    )


def adb_forward_failed_error(pid: int, reason: str) -> AgentError:
    """Create error for ADB port forwarding failure."""
    return AgentError(
        code="ERR_ADB_FORWARD_FAILED",
        message=f"ADB forward failed for pid {pid}: {reason}",
        context={"pid": pid, "reason": reason},
        remediation="Check that the process is still running and JDWP is available.",
    )


def already_attached_error(session_id: str) -> AgentError:
    """Create error for duplicate debug attach."""
    return AgentError(
        code="ERR_ALREADY_ATTACHED",
        message=f"Already attached to a debug session for {session_id}",
        context={"session_id": session_id},
        remediation="Detach first with 'debug detach --session <id>'.",
    )


def vm_disconnected_error(reason: str) -> AgentError:
    """Create error for VM disconnection."""
    return AgentError(
        code="ERR_VM_DISCONNECTED",
        message=f"VM disconnected: {reason}",
        context={"reason": reason},
        remediation="The target process may have exited. Re-launch and re-attach.",
    )


def debug_not_attached_error(session_id: str) -> AgentError:
    """Create error for debug commands without an active debug session."""
    return AgentError(
        code="ERR_DEBUG_NOT_ATTACHED",
        message=f"No active debug session for {session_id}",
        context={"session_id": session_id},
        remediation="Attach first with 'debug attach --session <id> --package <pkg>'.",
    )
