# Core Loop Deep Dive

> **Read this file when** you need to understand the observe-act-verify loop, snapshot format, or
> the decision process between observing and acting.

## Observe

Request a UI snapshot to see interactive elements:

```bash
uv run android-emu-agent ui snapshot <session_id>
```

The snapshot returns context and interactive elements with ephemeral `^ref` handles.

Example snapshot output:

```json
{
  "context": {
    "package": "com.example.app",
    "activity": ".MainActivity",
    "orientation": "PORTRAIT",
    "ime_visible": false
  },
  "elements": [
    {
      "ref": "^a1",
      "role": "button",
      "label": "Sign in",
      "resource_id": "com.example:id/login_btn",
      "bounds": [100, 200, 300, 250],
      "state": { "clickable": true, "enabled": true }
    }
  ]
}
```

Use `--format text` for a compact line-oriented summary. Use `--full` when the target element is not
in the default interactive-only snapshot (e.g., labels, images, non-clickable containers). Use
`--raw` for the raw XML hierarchy when debugging the UI tree structure.

## Decide

Quick decision checklist (work through in order):

1. **Blocker check** — Is `context.package` a system package (`android`,
   `com.google.android.permissioncontroller`, `com.android.systemui`)? If yes, handle the dialog
   first (see
   `references/ui-automation-patterns.md > Handling Permission Dialogs / System Dialogs`).
2. **Task intent** — Is the user asking for information (inquiry) or requesting an action? If
   inquiry, use only read-only methods (snapshot, screenshot, scroll). If ambiguous, default to
   inquiry. (Full protocol: `references/behavioral-protocols.md > Inquiry vs. Action Tasks`.)
3. **Target identification** — Find the target element by `^ref`, label, or role. If the element is
   unlabeled or its purpose is unclear, do not tap without user confirmation. (Full protocol:
   `references/behavioral-protocols.md > Unknown and Unlabeled Elements`.)
4. **Risk classification** — Is this a write/destructive action (delete, submit, purchase, reset)?
   If the agent is choosing to do it autonomously (not explicitly requested by user), confirm first.
   (Full protocol: `references/behavioral-protocols.md > Write-Action Confirmation Protocol`.)
5. **Proceed** — If no blockers, task is an action, target is identified, and risk is acceptable,
   execute the action.

## Act

Execute one action at a time using the `^ref` from the current snapshot:

```bash
uv run android-emu-agent action tap <session_id> ^a1
uv run android-emu-agent action set-text <session_id> ^a2 "username"
uv run android-emu-agent action back <session_id>
```

Refs are ephemeral and tied to a specific snapshot generation. After any action, take a new snapshot
before acting again.

If an action fails, follow the Action Failure Recovery Protocol (`references/recovery.md`): Level 1
re-snapshots automatically, Level 2 uses screenshots for visual analysis, Level 3 asks the user for
guidance.

## Verify

Take a new snapshot to confirm the action had the expected effect:

```bash
uv run android-emu-agent ui snapshot <session_id>
```

Verify that the expected UI change occurred and no error dialogs appeared. If the expected state is
not present, treat this as a potential action failure and enter the recovery protocol at Level 1
(see `references/recovery.md`).
