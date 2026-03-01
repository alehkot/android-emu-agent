# Complete Examples

> **Read this file when** you need a complete end-to-end walkthrough of a multi-step task (launch,
> login, navigate, recover from errors).

End-to-end task walkthroughs that compose multiple patterns. For individual pattern details (e.g.,
permission handling, login fields, form filling), see `references/ui-automation-patterns.md`. For
behavioral protocols (write-action confirmation, inquiry vs. action), see
`references/behavioral-protocols.md`.

## Example 0: Boot an AVD and Restore a Known State

Goal: Start an emulator from the CLI, restore a known snapshot, then begin a fresh automation
session.

```bash
# 1. Inspect available AVDs
uv run android-emu-agent emulator list-avds

# 2. Start the emulator and wait for Android boot
uv run android-emu-agent emulator start Pixel_8_API_34 --wait-boot

# 3. Restore a known snapshot for deterministic tests
uv run android-emu-agent emulator snapshot restore emulator-5554 post-onboarding

# 4. Start the daemon and a session
uv run android-emu-agent daemon start
uv run android-emu-agent session start --device emulator-5554
```

## Example 1: Launch App and Handle Permissions

Goal: Launch an app that requests camera permission and grant it.

Patterns used: permission dialog handling
(`ui-automation-patterns.md > Handling Permission Dialogs`).

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

Patterns used: login flow (`ui-automation-patterns.md > Login and Authentication Flows`).

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

Patterns used: onboarding skip, login flow, permission handling (`ui-automation-patterns.md`).

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

Goal: Tap "Confirm Purchase" but the action fails. Recover through Level 1 then Level 2.

For the full recovery protocol (limits, decision flowchart), see `references/recovery.md`.

```bash
# Observe
uv run android-emu-agent ui snapshot s-abc123
# ^a5 = "Confirm Purchase" button

# Act — stale ref may fail or auto-heal with a warning
uv run android-emu-agent action tap s-abc123 ^a5
# Possible result: status=done with warning about stale ref healing

# --- Level 1: Re-snapshot Recovery ---

# Wait for UI to settle
uv run android-emu-agent wait idle s-abc123 --timeout-ms 5000

# Fresh snapshot to continue with reliable refs
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
