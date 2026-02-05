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
# @a1 = "While using the app"
# @a2 = "Only this time"
# @a3 = "Don't allow"

# 4. Grant permission
uv run android-emu-agent action tap s-abc123 @a1
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
# @a1 = "Email" text field
# @a2 = "Password" text field
# @a3 = "Sign In" button

# Enter email
uv run android-emu-agent action tap s-abc123 @a1
uv run android-emu-agent ui snapshot s-abc123
uv run android-emu-agent action set-text s-abc123 @a1 "user@example.com"

# Enter password
uv run android-emu-agent ui snapshot s-abc123
uv run android-emu-agent action tap s-abc123 @a2
uv run android-emu-agent ui snapshot s-abc123
uv run android-emu-agent action set-text s-abc123 @a2 "mySecurePassword123"

# Dismiss keyboard
uv run android-emu-agent action back s-abc123

# Submit login
uv run android-emu-agent ui snapshot s-abc123
uv run android-emu-agent action tap s-abc123 @a3

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
# @a1 = hamburger menu icon (desc: "Open navigation drawer")

uv run android-emu-agent action tap s-abc123 @a1
uv run android-emu-agent wait idle s-abc123

# Navigate to Settings
uv run android-emu-agent ui snapshot s-abc123
# @a7 = "Settings"

uv run android-emu-agent action tap s-abc123 @a7
uv run android-emu-agent wait activity s-abc123 "SettingsActivity" --timeout-ms 5000

# Toggle a setting
uv run android-emu-agent ui snapshot s-abc123
# @a2 = "Dark Mode" switch, state: { checked: false }

uv run android-emu-agent action tap s-abc123 @a2
uv run android-emu-agent wait idle s-abc123

# Verify
uv run android-emu-agent ui snapshot s-abc123
# @a2 state: { checked: true }
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
# @a8 = "Privacy Policy"

uv run android-emu-agent action tap s-abc123 @a8
uv run android-emu-agent wait idle s-abc123
```

## Example 5: Handle App Crash and Recover

Goal: Detect and recover from an app crash.

```bash
uv run android-emu-agent action tap s-abc123 @a5
uv run android-emu-agent wait idle s-abc123 --timeout-ms 3000

uv run android-emu-agent ui snapshot s-abc123
# context.package = "android"
# Text: "MyApp has stopped"
# @a1 = "Close app"

uv run android-emu-agent action tap s-abc123 @a1
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
# @a1 = "Skip"

uv run android-emu-agent action tap s-test01 @a1
uv run android-emu-agent wait idle s-test01

uv run android-emu-agent ui snapshot s-test01
# @a2 = "Email", @a3 = "Password", @a4 = "Login"

uv run android-emu-agent action tap s-test01 @a2
uv run android-emu-agent ui snapshot s-test01
uv run android-emu-agent action set-text s-test01 @a2 "test@example.com"

uv run android-emu-agent ui snapshot s-test01
uv run android-emu-agent action tap s-test01 @a3
uv run android-emu-agent ui snapshot s-test01
uv run android-emu-agent action set-text s-test01 @a3 "testPassword123"

uv run android-emu-agent action back s-test01
uv run android-emu-agent ui snapshot s-test01
uv run android-emu-agent action tap s-test01 @a4

uv run android-emu-agent wait activity s-test01 "HomeActivity" --timeout-ms 15000

uv run android-emu-agent ui snapshot s-test01
# context.package = "com.example.app"
# context.activity = ".HomeActivity"

uv run android-emu-agent artifact screenshot s-test01 --pull --output ./artifacts/
uv run android-emu-agent session stop s-test01
```
