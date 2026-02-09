# Action Failure Recovery Protocol

> **Read this file when** an action fails (tap, set-text, etc. returns an error). Follow the 3-level
> escalation to recover.

Structured 3-level escalation when an action fails. Each level is progressively more expensive.

## When to Trigger

| Error Code          | Start At | Notes                                         |
| ------------------- | -------- | --------------------------------------------- |
| `ERR_STALE_REF`     | Level 1  | Ref expired; re-snapshot usually resolves     |
| `ERR_NOT_FOUND`     | Level 1  | Element missing from current hierarchy        |
| `ERR_BLOCKED_INPUT` | Level 1  | Dialog or keyboard blocking; dismiss first    |
| `ERR_ACTION_FAILED` | Level 1  | Action dispatched but did not succeed         |
| `ERR_TIMEOUT`       | Level 2  | Wait condition never met; needs visual check  |
| `ERR_NO_LOCATOR`    | Level 2  | No locator strategy resolved; deeper analysis |

Not recoverable (stop and report):

- `ERR_DEVICE_OFFLINE` — device disconnected, no recovery possible
- `ERR_SESSION_EXPIRED` — session timed out, must create a new one
- `ERR_DAEMON_OFFLINE` — daemon not running, must restart

## Level 1: Re-snapshot Recovery (Automatic)

Cost: low. Two CLI calls at most.

1. `wait idle` for UI to settle (timeout 3-5 s)
1. Take a fresh `ui snapshot`
1. Search for the target element by its characteristics (text, description, role, resource_id)
1. If found under a new `^ref` → retry the original action with the new ref
1. If a blocker is detected (dialog, overlay, keyboard) → handle the blocker first, re-snapshot,
   retry
1. If the target exists but is disabled (`state.enabled = false`) → `wait idle` once more, then
   re-snapshot

Max attempts: **2** (initial attempt + 1 retry). If both fail → escalate to Level 2.

```bash
# Level 1 example
uv run android-emu-agent wait idle <session_id> --timeout-ms 5000
uv run android-emu-agent ui snapshot <session_id>
# Find target again by text/desc/role, get new ^ref
uv run android-emu-agent action tap <session_id> ^<new_ref>
```

## Level 2: Visual / Screenshot Recovery (Automatic)

Cost: medium. Screenshot + full snapshot + corrective action.

1. `artifact screenshot --pull` for visual analysis
1. `ui snapshot --full` to see all elements (including non-interactive)
1. Analyze the combined evidence to determine root cause:

| Diagnosis             | Corrective Action                                       |
| --------------------- | ------------------------------------------------------- |
| Element off-screen    | Scroll in the appropriate direction, re-snapshot        |
| Element behind dialog | Dismiss the dialog (tap dismiss / back), re-snapshot    |
| Wrong activity        | Navigate back or launch correct activity, re-snapshot   |
| Inside WebView        | Use coordinate-based tap (`action tap-xy`), re-snapshot |
| App in error state    | Handle error (dismiss, retry, reset), re-snapshot       |

1. After corrective action, take a fresh snapshot and retry the original action

Max corrective actions: **3**. If the target is still unreachable → escalate to Level 3.

```bash
# Level 2 example
uv run android-emu-agent artifact screenshot <session_id> --pull --output ./debug.png
uv run android-emu-agent ui snapshot <session_id> --full
# Analyze: element is below the fold → scroll
uv run android-emu-agent action scroll down -s <session_id>
uv run android-emu-agent wait idle <session_id>
uv run android-emu-agent ui snapshot <session_id>
# Find target, retry action
uv run android-emu-agent action tap <session_id> ^<new_ref>
```

## Level 3: User Guidance (Interactive)

Cost: high. Requires human input.

When Levels 1 and 2 are exhausted, present the following to the user:

1. **What was attempted** — the original action and target description
1. **Current state** — latest snapshot summary + screenshot (if captured)
1. **Possible causes** — best guess from Level 2 analysis
1. **Suggested recovery options** — concrete next steps the user can choose from

Wait for user direction before taking further action.

Example prompt:

```text
I was unable to tap "Place Order" after recovery attempts:
- Level 1: Re-snapshot did not find the button (2 attempts)
- Level 2: Screenshot shows a loading overlay; waited 15 s but it persists

Possible causes:
  a) Server-side delay — the order API may be slow
  b) Network issue — the device may have lost connectivity

Suggested options:
  1. Wait longer (I'll retry in 30 s)
  2. Check device network and retry
  3. Abort this flow

Which option should I take, or do you have another suggestion?
```

## Recovery Limits

These caps prevent infinite loops:

| Limit                              | Value |
| ---------------------------------- | ----- |
| Level 1 attempts (per action)      | 2     |
| Level 2 corrective actions         | 3     |
| Total recovery cycles (per action) | 1     |

"Total recovery cycles" means the full L1 → L2 → L3 path runs at most once per failed action. If the
same action fails again after a successful recovery cycle, escalate directly to Level 3.

## Quick Decision Flowchart

```text
Action fails
  │
  ├─ Infrastructure error? (device offline / session expired / daemon down)
  │    └─ YES → Stop. Report error to user.
  │
  └─ NO → Level 1: wait idle → re-snapshot → find target
           │
           ├─ Target found? → Retry action
           │    ├─ Success → Done ✓
           │    └─ Fails again (attempt 2) → Level 2
           │
           └─ Target NOT found → Level 2
                │
                └─ Screenshot + full snapshot → diagnose
                     │
                     ├─ Corrective action possible?
                     │    └─ YES → Apply fix → re-snapshot → retry
                     │         ├─ Success → Done ✓
                     │         └─ Still failing (3 corrections) → Level 3
                     │
                     └─ NO corrective action → Level 3
                          │
                          └─ Present state + options to user → Wait
```
