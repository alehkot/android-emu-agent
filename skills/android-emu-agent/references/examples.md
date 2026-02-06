# Complete Examples

## Example 1: Launch App and Handle Permissions

Goal: Launch an app that requests camera permission and grant it.

```bash
# 1. Start session
uv run android-emu-agent session start --device emulator-5554
# Returns: session_id = s-abc123

# 2. Launch the app
uv run android-emu-agent app launch s-abc123 com.example.camera.app
uv run android-emu-agent wait idle s-abc123 --timeout-ms 5000

# 3. Take snapshot - might show permission dialog
uv run android-emu-agent ui snapshot s-abc123
# context.package = "com.google.android.permissioncontroller"
# ^a1 = "While using the app"
# ^a2 = "Only this time"
# ^a3 = "Don't allow"

# 4. Grant permission
uv run android-emu-agent action tap s-abc123 ^a1
uv run android-emu-agent wait idle s-abc123

# 5. Verify permission granted and app is ready
uv run android-emu-agent ui snapshot s-abc123
# context.package = "com.example.camera.app"
# context.activity = ".MainActivity"
```

## Example 2: Login Flow

Goal: Log into an app with email and password.

```bash
uv run android-emu-agent ui snapshot s-abc123
# ^a1 = "Email" text field
# ^a2 = "Password" text field
# ^a3 = "Sign In" button

# Enter email
uv run android-emu-agent action tap s-abc123 ^a1
uv run android-emu-agent ui snapshot s-abc123
uv run android-emu-agent action set-text s-abc123 ^a1 "user@example.com"

# Enter password
uv run android-emu-agent ui snapshot s-abc123
uv run android-emu-agent action tap s-abc123 ^a2
uv run android-emu-agent ui snapshot s-abc123
uv run android-emu-agent action set-text s-abc123 ^a2 "mySecurePassword123"

# Dismiss keyboard
uv run android-emu-agent action back s-abc123

# Submit login
uv run android-emu-agent ui snapshot s-abc123
uv run android-emu-agent action tap s-abc123 ^a3

# Wait for success
uv run android-emu-agent wait activity s-abc123 "HomeActivity" --timeout-ms 15000

# Verify logged in
uv run android-emu-agent ui snapshot s-abc123
# context.activity = ".HomeActivity"
```

## Example 3: Navigate and Interact with Settings

Goal: Open navigation drawer, go to settings, and toggle a setting.

```bash
# Open navigation drawer
uv run android-emu-agent ui snapshot s-abc123
# ^a1 = hamburger menu icon (desc: "Open navigation drawer")

uv run android-emu-agent action tap s-abc123 ^a1
uv run android-emu-agent wait idle s-abc123

# Navigate to Settings
uv run android-emu-agent ui snapshot s-abc123
# ^a7 = "Settings"

uv run android-emu-agent action tap s-abc123 ^a7
uv run android-emu-agent wait activity s-abc123 "SettingsActivity" --timeout-ms 5000

# Toggle a setting
uv run android-emu-agent ui snapshot s-abc123
# ^a2 = "Dark Mode" switch, state: { checked: false }

uv run android-emu-agent action tap s-abc123 ^a2
uv run android-emu-agent wait idle s-abc123

# Verify
uv run android-emu-agent ui snapshot s-abc123
# ^a2 state: { checked: true }
```

## Example 4: Scroll to Find and Tap Element

Goal: Find "Privacy Policy" in a long settings list.

```bash
uv run android-emu-agent ui snapshot s-abc123
# "Privacy Policy" not visible

uv run android-emu-agent action scroll down -s s-abc123
uv run android-emu-agent wait idle s-abc123
uv run android-emu-agent ui snapshot s-abc123

uv run android-emu-agent action scroll down -s s-abc123
uv run android-emu-agent wait idle s-abc123
uv run android-emu-agent ui snapshot s-abc123
# ^a8 = "Privacy Policy"

uv run android-emu-agent action tap s-abc123 ^a8
uv run android-emu-agent wait idle s-abc123
```

## Example 5: Handle App Crash and Recover

Goal: Detect and recover from an app crash.

```bash
uv run android-emu-agent action tap s-abc123 ^a5
uv run android-emu-agent wait idle s-abc123 --timeout-ms 3000

uv run android-emu-agent ui snapshot s-abc123
# context.package = "android"
# Text: "MyApp has stopped"
# ^a1 = "Close app"

uv run android-emu-agent action tap s-abc123 ^a1
uv run android-emu-agent wait idle s-abc123

uv run android-emu-agent app launch s-abc123 com.example.myapp
uv run android-emu-agent wait activity s-abc123 "MainActivity" --timeout-ms 10000

uv run android-emu-agent ui snapshot s-abc123
# context.package = "com.example.myapp"
```

## Example 6: Complete E2E Test Flow

Goal: Full end-to-end test - launch app, skip onboarding, login, verify home screen.

```bash
uv run android-emu-agent daemon status
uv run android-emu-agent session start --device emulator-5554
# session_id = s-test01

uv run android-emu-agent app reset s-test01 com.example.app
uv run android-emu-agent app launch s-test01 com.example.app
uv run android-emu-agent wait idle s-test01 --timeout-ms 10000

uv run android-emu-agent ui snapshot s-test01
# ^a1 = "Skip"

uv run android-emu-agent action tap s-test01 ^a1
uv run android-emu-agent wait idle s-test01

uv run android-emu-agent ui snapshot s-test01
# ^a2 = "Email", ^a3 = "Password", ^a4 = "Login"

uv run android-emu-agent action tap s-test01 ^a2
uv run android-emu-agent ui snapshot s-test01
uv run android-emu-agent action set-text s-test01 ^a2 "test@example.com"

uv run android-emu-agent ui snapshot s-test01
uv run android-emu-agent action tap s-test01 ^a3
uv run android-emu-agent ui snapshot s-test01
uv run android-emu-agent action set-text s-test01 ^a3 "testPassword123"

uv run android-emu-agent action back s-test01
uv run android-emu-agent ui snapshot s-test01
uv run android-emu-agent action tap s-test01 ^a4

uv run android-emu-agent wait activity s-test01 "HomeActivity" --timeout-ms 15000

uv run android-emu-agent ui snapshot s-test01
# context.package = "com.example.app"
# context.activity = ".HomeActivity"

uv run android-emu-agent artifact screenshot s-test01 --pull --output ./artifacts/
uv run android-emu-agent session stop s-test01
```

## Example 7: Action Failure Recovery Escalation

Goal: Tap "Confirm Purchase" but the action fails. Recover through Level 1 → Level 2.

```bash
# Observe
uv run android-emu-agent ui snapshot s-abc123
# ^a5 = "Confirm Purchase" button

# Act — fails with ERR_STALE_REF
uv run android-emu-agent action tap s-abc123 ^a5
# Error: ERR_STALE_REF - Element ^a5 not found or bounds changed

# --- Level 1: Re-snapshot Recovery ---

# Wait for UI to settle
uv run android-emu-agent wait idle s-abc123 --timeout-ms 5000

# Fresh snapshot
uv run android-emu-agent ui snapshot s-abc123
# "Confirm Purchase" not visible in snapshot — Level 1 cannot resolve

# --- Level 2: Visual / Screenshot Recovery ---

# Capture screenshot for visual analysis
uv run android-emu-agent artifact screenshot s-abc123 --pull --output ./debug-purchase.png
# Screenshot reveals "Confirm Purchase" is below the fold

# Full snapshot to confirm
uv run android-emu-agent ui snapshot s-abc123 --full
# Scrollable container detected

# Corrective action: scroll down
uv run android-emu-agent action scroll down -s s-abc123
uv run android-emu-agent wait idle s-abc123

# Re-snapshot — target found
uv run android-emu-agent ui snapshot s-abc123
# ^a3 = "Confirm Purchase"

# Retry action — success
uv run android-emu-agent action tap s-abc123 ^a3
uv run android-emu-agent wait idle s-abc123

# Verify
uv run android-emu-agent ui snapshot s-abc123
# context.activity = ".OrderConfirmationActivity"
```

## Example 8: Write-Action Confirmation

Goal: Agent is navigating a checkout flow and reaches the "Place Order" button. The user's original
request was "show me the checkout page", not "place the order".

```bash
# User said: "show me the checkout page"

# Agent navigated to checkout
uv run android-emu-agent ui snapshot s-abc123
# context.activity = ".CheckoutActivity"
# ^a1 = "Edit Cart"
# ^a2 = "Promo Code" text field
# ^a3 = "Place Order" button ($49.99)
# ^a4 = "Back"

# Agent has reached the checkout page as requested.
# The user asked to "show" the page, not to place the order.
# "Place Order" is a high-risk destructive action.

# ✓ Report to user instead of tapping:
# "You're on the checkout page. Total is $49.99. Items: ...
#  Would you like me to place the order, or do something else?"

# User responds: "Yes, place the order"

# Now the user explicitly requested it — proceed without confirmation
uv run android-emu-agent action tap s-abc123 ^a3
uv run android-emu-agent wait idle s-abc123 --timeout-ms 10000

# Verify
uv run android-emu-agent ui snapshot s-abc123
# context.activity = ".OrderConfirmationActivity"
# Text: "Order placed successfully"
```

## Example 9: Session Start — Readiness Only

Goal: User says they want to use their emulator. Agent ensures readiness and waits.

```bash
# User: "Hey, I'm going to use my Android emulator"

# ✓ Check daemon
uv run android-emu-agent daemon status
# Daemon is not running → start it
uv run android-emu-agent daemon start

# ✓ Check device
uv run android-emu-agent device list
# emulator-5554 | online

# ✓ Ensure session
uv run android-emu-agent session start --device emulator-5554
# session_id = s-abc123

# ✓ Report to user:
# "Ready. Daemon running, emulator-5554 connected, session s-abc123 active.
#  What would you like to do?"

# ✗ Do NOT take a snapshot
# ✗ Do NOT launch any app
# ✗ Do NOT tap, swipe, or type anything
# ✗ Do NOT assume the user wants to test a specific app

# Wait for the user's next request.
```

## Example 10: Inquiry Task — Identifying Unknown Buttons (Read-Only)

Goal: User asks "check if there is a button to play music." The agent must answer using only
read-only methods and must NOT tap any buttons to discover their purpose.

```bash
# User said: "check if there is a button to play music"
# This is an INQUIRY task — the user wants information, not an action.

# Step 1: Take a snapshot to inspect elements
uv run android-emu-agent ui snapshot s-abc123
# context.package = "com.example.musicplayer"
# context.activity = ".NowPlayingActivity"
# ^a1 = ImageButton, no text, no content_desc, resource_id: "btn_prev"
# ^a2 = ImageButton, no text, no content_desc, resource_id: "btn_play_pause"
# ^a3 = ImageButton, no text, no content_desc, resource_id: "btn_next"
# ^a4 = TextView, text: "Song Title - Artist Name"
# ^a5 = SeekBar, resource_id: "seekbar_progress"

# Observation: Three unlabeled ImageButtons found. resource_ids suggest
# prev/play_pause/next but there is no text or content_desc to confirm.

# Step 2: Take a screenshot for visual identification
uv run android-emu-agent artifact screenshot s-abc123 --pull --output ./debug-music.png
# Screenshot reveals: Three icons in a horizontal transport bar.
# Left icon: skip-back (|◁), Center icon: play triangle (▶), Right icon: skip-forward (▷|)

# Step 3: Take a full snapshot for additional context
uv run android-emu-agent ui snapshot s-abc123 --full
# Full tree confirms: The three ImageButtons are inside a LinearLayout
# with resource_id "media_controls". SeekBar and song title are siblings.

# Step 4: Report findings to user
# "Yes, there appears to be a play button. I found three unlabeled ImageButtons
#  in a media transport bar:
#  - ^a1: skip-back icon (resource_id: btn_prev) — high confidence
#  - ^a2: play/pause icon (resource_id: btn_play_pause) — high confidence
#  - ^a3: skip-forward icon (resource_id: btn_next) — high confidence
#
#  The center button ^a2 shows a play triangle (▶) in the screenshot and has
#  resource_id 'btn_play_pause'. This is very likely the play button.
#
#  Would you like me to tap it?"

# Step 5: Wait for user response
# User: "Yes, tap the play button"

# NOW this is an action task with explicit user authorization — proceed
uv run android-emu-agent action tap s-abc123 ^a2
uv run android-emu-agent wait idle s-abc123

# Verify
uv run android-emu-agent ui snapshot s-abc123
# ^a2 icon changed to pause (❚❚) — confirms it was the play button

# ✗ Do NOT tap ^a2 autonomously to "confirm" it is the play button
# ✗ Do NOT tap any unlabeled button to discover its function
# ✗ Do NOT escalate from read-only to state-modifying during an inquiry
# ✗ Do NOT assume a button's purpose and act on it without user permission
```
