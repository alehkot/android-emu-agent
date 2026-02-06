# Template: Action Failure Recovery Escalation

Replace placeholders: `<session_id>`, `<failed_action>`, `<target_description>`.

## Level 1: Re-snapshot Recovery

```bash
# Action failed: <failed_action> targeting <target_description>

# Step 1: Wait for UI to settle
uv run android-emu-agent wait idle <session_id> --timeout-ms 5000

# Step 2: Fresh snapshot
uv run android-emu-agent ui snapshot <session_id>

# Step 3: Search for <target_description> by text/desc/role/id in snapshot output
# If found under new ^ref → retry:
uv run android-emu-agent <failed_action> <session_id> @<new_ref>

# Step 4: If blocker detected (dialog, overlay), handle it first:
# uv run android-emu-agent action back <session_id>
# uv run android-emu-agent ui snapshot <session_id>
# Then retry the action.

# Step 5: If target exists but disabled, wait once more:
# uv run android-emu-agent wait idle <session_id> --timeout-ms 5000
# uv run android-emu-agent ui snapshot <session_id>
# Then retry.

# → If still failing after 2 attempts total, escalate to Level 2.
```

## Level 2: Visual / Screenshot Recovery

```bash
# Step 1: Capture screenshot for visual analysis
uv run android-emu-agent artifact screenshot <session_id> --pull --output ./debug-recovery.png

# Step 2: Full snapshot (all elements including non-interactive)
uv run android-emu-agent ui snapshot <session_id> --full

# Step 3: Diagnose from screenshot + full snapshot
# - Off-screen? → scroll
# - Behind dialog? → dismiss
# - Wrong activity? → navigate
# - WebView/custom? → use coordinates
# - Error state? → handle error

# Step 4: Apply corrective action (example: scroll to find element)
uv run android-emu-agent action scroll down -s <session_id>
uv run android-emu-agent wait idle <session_id>

# Step 5: Re-snapshot and retry
uv run android-emu-agent ui snapshot <session_id>
# Find <target_description> → retry:
uv run android-emu-agent <failed_action> <session_id> @<new_ref>

# → If still failing after 3 corrective actions, escalate to Level 3.
```

## Level 3: User Guidance

```text
Present to the user:

1. What was attempted:
   Action: <failed_action>
   Target: <target_description>

2. Current state:
   [Include latest snapshot summary and screenshot path]

3. Possible causes:
   - [Best guess from Level 2 analysis]
   - [Second possibility]

4. Suggested recovery options:
   a) [Option 1 — e.g., wait longer and retry]
   b) [Option 2 — e.g., navigate to correct screen]
   c) [Option 3 — e.g., abort this flow]

Await user direction before proceeding.
```
