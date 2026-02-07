---
name: android-emu-agent
description:
  Automate Android apps on emulators and rooted devices via observe-act-verify UI snapshots and
  actions. Use for Android UI automation/testing, emulator control, tapping/typing/navigation,
  handling dialogs, diagnosing UI automation issues, and reliability forensics.
---

# Android Emu Agent Skill

Use the `android-emu-agent` CLI + daemon to control Android UI with snapshots and ephemeral element
refs. If you're working inside this repo, prefer `uv run android-emu-agent ...` to ensure the
correct environment.

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
  `references/patterns.md` > Session Readiness Check.
- One action per snapshot. Refs are ephemeral.
- Re-snapshot after any action or wait.
- Verify state changes after each action.
- If blocked by dialogs or loading, handle the blocker first.
- When an action fails, follow the recovery protocol (re-snapshot, visual analysis, then ask user).
  Do not blindly retry. See `references/recovery.md`.
- Confirm before write/destructive actions unless the user explicitly requested them. See
  `references/patterns.md` > Write-Action Confirmation Protocol.
- **Read-only first for informational tasks.** When the user asks a question about the UI (e.g. "is
  there a button for...", "what does this screen show", "check if..."), use only read-only methods
  (snapshots, screenshots, scrolling) to answer. Do not tap, type, or otherwise modify UI state to
  investigate. See `references/patterns.md` > Inquiry vs. Action Tasks.

## Decision Guide

- Need snapshot format or loop details: `references/core-loop.md`
- Need full command/selector reference: `references/command-reference.md`
- Need app state / routing debug (`app current`, `app task-stack`, `app resolve-intent`):
  `references/command-reference.md`
- Need patterns (permissions, dialogs, login, onboarding, navigation, forms, scrolling):
  `references/patterns.md`
- Need error handling or debug playbooks: `references/troubleshooting.md`
- Need end-to-end examples: `references/examples.md`
- Need reliability and forensics workflows: `references/reliability.md`
- Need file transfer workflows: `references/files.md`
- Need action failure recovery: `references/recovery.md`
- Need write-action confirmation rules: `references/patterns.md` > Write-Action Confirmation
  Protocol
- Need inquiry vs. action task rules: `references/patterns.md` > Inquiry vs. Action Tasks

## Templates (Ready-to-Use)

Templates are copy-pasteable flows with placeholders like `<session_id>` and `<package>`.

- `templates/flow-permission.md` - handle runtime permission dialogs
- `templates/flow-login.md` - login with email/password
- `templates/flow-onboarding.md` - skip onboarding or tap-through tutorial
- `templates/flow-e2e.md` - full E2E flow (reset, onboarding, login, verify)
- `templates/flow-reliability-triage.md` - crash/ANR reliability triage
- `templates/flow-recovery.md` - action failure recovery escalation (L1/L2/L3)
