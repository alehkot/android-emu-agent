"""Notifications, permissions, and Android system surfaces."""

from __future__ import annotations

import asyncio
import re
import shlex
from typing import Any

from android_emu_agent.errors import AgentError

_PERMISSION_STATE_RE = re.compile(r"^\s*([A-Za-z0-9_.$]+):\s+granted=(true|false)")
_PERMISSION_NAME_RE = re.compile(r"^[A-Za-z0-9_.]+$")


class SystemManager:
    """Runs safe shell-backed system surface and permission commands."""

    async def open_notifications(self, device: Any) -> dict[str, Any]:
        """Open the notification shade."""
        output = await self._shell(device, "cmd statusbar expand-notifications")
        return {"status": "done", "surface": "notifications", "state": "open", "output": output}

    async def close_notifications(self, device: Any) -> dict[str, Any]:
        """Collapse the notification shade."""
        output = await self._shell(device, "cmd statusbar collapse")
        return {"status": "done", "surface": "notifications", "state": "closed", "output": output}

    async def open_quick_settings(self, device: Any) -> dict[str, Any]:
        """Open quick settings."""
        output = await self._shell(device, "cmd statusbar expand-settings")
        return {"status": "done", "surface": "quick_settings", "state": "open", "output": output}

    async def grant_permission(
        self,
        device: Any,
        package: str,
        permission: str,
    ) -> dict[str, Any]:
        """Grant a runtime permission."""
        self._validate_permission(permission)
        output = await self._shell(
            device,
            f"pm grant {shlex.quote(package)} {shlex.quote(permission)}",
        )
        return {
            "status": "done",
            "package": package,
            "permission": permission,
            "granted": True,
            "output": output,
        }

    async def revoke_permission(
        self,
        device: Any,
        package: str,
        permission: str,
    ) -> dict[str, Any]:
        """Revoke a runtime permission."""
        self._validate_permission(permission)
        output = await self._shell(
            device,
            f"pm revoke {shlex.quote(package)} {shlex.quote(permission)}",
        )
        return {
            "status": "done",
            "package": package,
            "permission": permission,
            "granted": False,
            "output": output,
        }

    async def list_permissions(self, device: Any, package: str) -> dict[str, Any]:
        """List requested and granted package permissions from dumpsys package."""
        output = await self._shell(device, f"dumpsys package {shlex.quote(package)}")
        permissions = self.parse_permissions(output)
        return {
            "status": "done",
            "package": package,
            "permissions": permissions,
            "count": len(permissions),
            "output": self._format_permissions(permissions),
        }

    def parse_permissions(self, dumpsys_output: str) -> list[dict[str, Any]]:
        """Parse permission state from dumpsys package output."""
        requested: dict[str, dict[str, Any]] = {}
        section: str | None = None

        for line in dumpsys_output.splitlines():
            stripped = line.strip()
            if stripped in {
                "requested permissions:",
                "install permissions:",
                "runtime permissions:",
            }:
                section = stripped.removesuffix(":").replace(" ", "_")
                continue

            match = _PERMISSION_STATE_RE.match(line)
            if match:
                permission = match.group(1)
                requested[permission] = {
                    "permission": permission,
                    "granted": match.group(2) == "true",
                    "source": section or "state",
                }
                continue

            if section == "requested_permissions" and _PERMISSION_NAME_RE.fullmatch(stripped):
                requested.setdefault(
                    stripped,
                    {
                        "permission": stripped,
                        "granted": None,
                        "source": "requested",
                    },
                )

        return sorted(requested.values(), key=lambda item: item["permission"])

    async def _shell(self, device: Any, command: str) -> str:
        def _run() -> str:
            result = device.shell(command)
            output = getattr(result, "output", None)
            return output if isinstance(output, str) else str(result)

        return (await asyncio.to_thread(_run)).strip()

    @staticmethod
    def _validate_permission(permission: str) -> None:
        if not _PERMISSION_NAME_RE.fullmatch(permission):
            raise AgentError(
                code="ERR_INVALID_PERMISSION",
                message=f"Invalid permission name: {permission}",
                context={"permission": permission},
                remediation="Use a fully-qualified Android permission name without whitespace.",
            )

    @staticmethod
    def _format_permissions(permissions: list[dict[str, Any]]) -> str:
        lines = []
        for item in permissions:
            granted = item.get("granted")
            state = "requested" if granted is None else "granted" if granted else "denied"
            lines.append(f"{item['permission']} {state}")
        return "\n".join(lines)
