# Behavioral Protocols

> **Read this file when** you need to decide whether to act or observe, whether to confirm before
> acting, how to handle session startup, or how to approach unlabeled elements.

Decision protocols that govern agent behavior: when to act vs. observe, when to confirm before
acting, how to handle session startup, and how to approach unlabeled elements.

For UI interaction patterns (permissions, login, forms, navigation), see
`references/ui-automation-patterns.md`.

## Session Readiness Check

When the user indicates they want to work with a device (e.g. "I'm going to use my emulator", "let's
test on my phone", "I have a rooted device ready"), the agent should **only ensure prerequisites are
met** and then wait for instructions. Do not take any UI actions.

What to do:

1. Verify the daemon is running (`daemon status`, start if needed)
1. Verify the device is connected (`device list`)
1. Ensure a session exists or create one (`session list` / `session start`)
1. Report readiness to the user and **wait for their next request**

What **not** to do:

- Do not launch any app
- Do not take a snapshot (unless the user asks)
- Do not tap, swipe, type, scroll, or perform any UI action
- Do not make assumptions about what the user wants to do next

The agent is a tool that responds to user requests — it does not drive the session autonomously.

Example:

```bash
# User: "Hey, I'm going to use my Android emulator"

# Agent checks readiness:
uv run android-emu-agent daemon status
# If not running:
uv run android-emu-agent daemon start

uv run android-emu-agent device list
# Confirms: emulator-5554 is connected

uv run android-emu-agent session list
# If no active session:
uv run android-emu-agent session start --device emulator-5554
# Returns: session_id = s-abc123

# Agent responds:
# "Ready. Daemon is running, emulator-5554 is connected, session s-abc123 is active.
#  What would you like to do?"

# Agent does NOT take any further action until the user asks.
```

## Write-Action Confirmation Protocol

Before executing a write or destructive action, determine whether the user explicitly requested it.
If the agent is deciding autonomously, confirm with the user first.

### Classification Rules

**Always safe (no confirmation needed):**

| Category            | Examples                                                     |
| ------------------- | ------------------------------------------------------------ |
| Read-only snapshots | `ui snapshot`, `ui screenshot`                               |
| Wait commands       | `wait idle`, `wait text`, `wait activity`, `wait exists`     |
| Artifacts           | `artifact screenshot`, `artifact logs`, `artifact bundle`    |
| Navigation taps     | Tapping tabs, menu items, "Back", "Next", "Close", "Dismiss" |
| Scrolling           | `action scroll *`, `action swipe *`                          |
| System navigation   | `action back`, `action home`, `action recents`               |
| Read-only queries   | `device list`, `session list`, `daemon status`               |

**Additional considerations:**

- If the user's task is purely informational (inquiry), even "Always safe" actions like navigation
  taps require justification. See Inquiry vs. Action Tasks below.
- If the tap target is unlabeled or unknown, see Unknown and Unlabeled Elements below.

**Requires confirmation (unless user explicitly requested):**

| Category                | Examples                                                             |
| ----------------------- | -------------------------------------------------------------------- |
| App lifecycle           | `app reset`, `app force-stop`, `app uninstall`                       |
| Autonomous text entry   | `action set-text` when the user did not dictate the text content     |
| Destructive tap targets | Tapping "Delete", "Submit", "Place order", "Purchase", "Send"        |
| File operations         | `file push` (writes to device)                                       |
| Device settings         | `device set *` (changes device state)                                |
| Form submissions        | Tapping a submit/confirm button that triggers an irreversible action |

### When Confirmation Is NOT Needed

Skip confirmation when the user specifically asked for the action:

- User says "tap Submit" → tap Submit without asking
- User says "enter my email as `alice@example.com`" → `set-text` without asking
- User says "reset the app" → `app reset` without asking
- User says "delete the item" → tap "Delete" without asking

**Key test:** Did the user specifically ask for this action, or is the agent deciding autonomously?
If the user said to do it, just do it. If the agent is choosing to do it as part of a broader goal,
confirm first.

### Confirmation Format

When confirmation is needed, present:

```text
I'm about to <action description>.
This will <potential side effect>.
Should I proceed? (yes / no / modify)
```

Examples:

```text
I'm about to tap "Place Order" ($49.99).
This will submit a purchase that may charge a payment method.
Should I proceed? (yes / no / modify)
```

```text
I'm about to run `app reset com.example.app`.
This will clear all app data including login state.
Should I proceed? (yes / no / modify)
```

### Detecting Destructive Tap Targets

When the agent decides to tap a button autonomously, classify the label:

**High-risk (always confirm):**

- "Delete", "Remove", "Submit", "Place order", "Purchase", "Buy", "Pay"
- "Send", "Post", "Publish", "Sign out", "Log out", "Deactivate"
- "Confirm" on payment, order, or account-deletion screens

**Low-risk (no confirmation needed):**

- "OK", "Close", "Dismiss", "Cancel", "Allow", "Deny"
- "Next", "Continue", "Back", "Done", "Got it"
- Tab names, menu items, navigation elements

**Ambiguous (use context):**

- "Confirm" — high-risk on payment/order screens, low-risk on permission dialogs
- "Yes" — depends on what the dialog is asking
- "Apply" — depends on whether the change is reversible

For ambiguous labels, check the surrounding context (activity name, dialog text, nearby elements) to
determine the risk level.

## Inquiry vs. Action Tasks

Before choosing an action, classify the user's task intent.

### Classification

| Intent        | Signal Phrases                                                             |
| ------------- | -------------------------------------------------------------------------- |
| **Inquiry**   | "is there", "check if", "find the", "what does", "show me", "does it have" |
| **Action**    | "tap", "open", "type", "launch", "enable", "turn on", "swipe", "scroll to" |
| **Ambiguous** | "go to settings", "try the button" — could be inquiry or action            |

When ambiguous, default to **inquiry**. It is always safer to report findings and ask than to act
and cause unintended state changes.

### Read-Only Escalation Path (Inquiry Tasks)

When the task is an inquiry, use only read-only methods in this order:

1. **Snapshot analysis** — `ui snapshot` to inspect element labels, roles, and state
2. **Screenshot analysis** — `artifact screenshot` for visual identification (icons, colors, layout)
3. **Scroll to reveal** — `action scroll` is non-destructive and may expose off-screen elements
4. **Full snapshot** — `ui snapshot --full` to include all nodes, not just interactive ones
5. **Ask the user** — if none of the above resolves the question, report what you found and ask

**Do NOT** tap, type, swipe (non-scroll), or launch apps to answer an inquiry. These are
state-modifying actions that go beyond what the user asked.

### When Inquiry Becomes Action

An inquiry can transition to an action when the user explicitly bridges the gap:

```text
Agent: "I found three buttons in the media transport bar. Based on the screenshot,
       ^a2 appears to be a play button (triangle icon). Would you like me to tap it?"
User:  "Yes, tap it."
```

At this point, the task has become an action with explicit user authorization. Proceed normally
using the Write-Action Confirmation Protocol for classification.

**Key rule:** The agent must never autonomously escalate from read-only observation to
state-modifying action during an inquiry task. The user must explicitly request the transition.

## Unknown and Unlabeled Elements

When the agent encounters an element without a clear label, it must assess confidence before
interacting.

### Classification by Element State

| Element State                                                             | Action                                          |
| ------------------------------------------------------------------------- | ----------------------------------------------- |
| **Clear label** (text, content_desc, or resource_id with meaningful name) | Classify per Write-Action Confirmation Protocol |
| **Unclear but inferable** (icon + surrounding context suggest purpose)    | State inference, proceed with caution           |
| **No label, no description, unknown purpose**                             | **Do not tap without user confirmation**        |

### Before Tapping an Unknown Element

When a target element lacks a clear label, perform these checks before interacting:

1. **Check available identifiers** — inspect `resource_id`, `content_desc`, `text`, and `role` from
   the snapshot
2. **Take a screenshot** — visual inspection may reveal icons, colors, or positional cues
3. **Check surrounding elements** — nearby labels, container context, or sibling elements may
   clarify purpose
4. **State your best guess and ask** — report your inference to the user with a confidence level and
   request permission

### Applies to All Task Types

**Inquiry tasks:** Describe the unknown element to the user. Do not tap to discover its purpose —
that is a state-modifying action used to answer an informational question.

**Action tasks:** If the user asked to tap a specific function (e.g. "tap the play button") but the
best match is an unlabeled element, state your confidence and ask before tapping:

```text
Agent: "I found an unlabeled ImageButton at ^a2. Based on its position in the media
       transport bar and the triangle icon visible in the screenshot, I believe this is
       the play button (medium confidence). Should I tap it?"
```

If the user confirms, proceed. If the user says no, ask for clarification or try alternative
identification strategies.
