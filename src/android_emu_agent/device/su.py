"""Root shell commands that work with both common ``su`` implementations."""

from __future__ import annotations

import shlex
from collections.abc import Awaitable, Callable

from android_emu_agent.errors import AgentError

# AOSP's su, shipped on userdebug and eng emulator images, only accepts
# ``su [WHO [COMMAND...]]``. Given ``-c`` it exits with this message before running
# anything. Magisk and SuperSU accept ``su -c``.
AOSP_SU_REJECTION = "invalid uid/gid '-c'"


def aosp_su_command(command: str) -> str:
    """Return the command that runs ``command`` as uid 0 in AOSP su syntax."""
    return f"su 0 sh -c {shlex.quote(command)}"


async def run_as_root(shell: Callable[[str], Awaitable[str]], command: str) -> str:
    """Run ``command`` through ``su -c``, retrying in AOSP syntax only if ``-c`` is rejected."""
    try:
        return await shell(f"su -c {shlex.quote(command)}")
    except AgentError as exc:
        if AOSP_SU_REJECTION not in str(exc.context.get("reason", "")):
            raise
    return await shell(aosp_su_command(command))
