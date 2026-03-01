---
name: android-emu-agent
description:
  Automate Android apps on emulators and rooted devices via observe-act-verify UI snapshots and
  actions. Use for Android UI automation/testing, emulator control, tapping/typing/navigation,
  handling dialogs, diagnosing UI automation issues, and reliability forensics.
---

# Android Emu Agent Skill

Use the `android-emu-agent` CLI + daemon to control Android UI with actionable snapshots and
generation-scoped element refs. Compact snapshots are designed to work well across classic XML
layouts and modern frameworks such as Compose and Litho. If you're working inside this repo, prefer
`uv run android-emu-agent ...` to ensure the correct environment.

## SDK CLI Prerequisites

- For connected-device workflows, `adb` must be available.
- For emulator lifecycle workflows, `emulator` should be available.
- For creating or inspecting AVD definitions outside the agent, `avdmanager` is recommended.
- The daemon resolves tools from `PATH` first, then standard Android SDK roots from
  `ANDROID_SDK_ROOT` / `ANDROID_HOME`.

## Quick Start

1. Start the daemon.

```bash
uv run android-emu-agent daemon start
uv run android-emu-agent daemon status
```

1. Verify a device is connected.

```bash
uv run android-emu-agent device list
```

1. If no emulator is running, boot one first.

```bash
uv run android-emu-agent emulator list-avds
uv run android-emu-agent emulator start <avd_name> --wait-boot
```

1. Start a session.

```bash
uv run android-emu-agent session start --device <serial>
# Returns: session_id = s-abc123
```

1. Run the observe-act-verify loop.

```bash
# Observe
uv run android-emu-agent ui snapshot <session_id>

# Act (one action)
uv run android-emu-agent action tap <session_id> ^a1

# Verify
uv run android-emu-agent ui snapshot <session_id>
```

## Daemon Lifecycle (When and How to Start)

- Start the daemon before any device/session/ui/action/app/reliability/file commands.
- The CLI can auto-start the daemon on first request, but start it explicitly for stable sessions.
- Verify health with `uv run android-emu-agent daemon status` before long runs.
- Stop it when you are done with `uv run android-emu-agent daemon stop`.
- If you are working inside this repo, use `uv run android-emu-agent ...` for all of the above.

## Core Rules

- **Never act without a user request.** When the user starts a session (e.g. "I'm going to use my
  emulator"), only ensure readiness (daemon up, device connected, session active). Do not tap,
  swipe, type, launch apps, or take any UI action until the user explicitly asks. See
  `references/behavioral-protocols.md` > Session Readiness Check.
- One action per snapshot. Refs are generation-scoped.
- Re-snapshot after any action or wait.
- Verify state changes after each action.
- If blocked by dialogs or loading, handle the blocker first.
- If a stale ref is auto-healed, treat the warning as a prompt to re-snapshot before the next
  action.
- When an action fails, follow the recovery protocol (re-snapshot, visual analysis, then ask user).
  Do not blindly retry. See `references/recovery.md`.
- Confirm before write/destructive actions unless the user explicitly requested them. See
  `references/behavioral-protocols.md` > Write-Action Confirmation Protocol.
- **Read-only first for informational tasks.** When the user asks a question about the UI (e.g. "is
  there a button for...", "what does this screen show", "check if..."), use only read-only methods
  (snapshots, screenshots, scrolling) to answer. Do not tap, type, or otherwise modify UI state to
  investigate. See `references/behavioral-protocols.md` > Inquiry vs. Action Tasks.

## Decision Guide

Match your situation to the right file:

- **Starting a session or understanding the loop** → `references/core-loop.md`
- **Looking up a command or selector syntax** → `references/command-reference.md`
- **Handling a UI scenario** (permissions, dialogs, login, onboarding, navigation, forms, scrolling)
  → `references/ui-automation-patterns.md`
- **Deciding whether to act or confirm first** (inquiry vs. action, write-action confirmation,
  unknown elements) → `references/behavioral-protocols.md`
- **Action failed with an error** → `references/recovery.md`
- **Hit an error or unexpected behavior** → `references/troubleshooting.md`
- **Need a complete end-to-end walkthrough** → `references/examples.md`
- **Diagnosing a crash, ANR, or process death** → `references/reliability.md`
- **Investigating runtime behavior with breakpoints/stack/inspect** → `references/debugging.md`
- **Pushing or pulling files to/from device** → `references/files.md`
