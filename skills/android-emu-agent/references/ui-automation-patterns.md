# UI Automation Patterns

> **Read this file when** you need to handle a specific UI scenario: permissions, system dialogs,
> login, onboarding, navigation, forms, scrolling, or stale refs.

Common patterns for handling typical Android UI scenarios: permissions, dialogs, login flows,
onboarding, navigation, forms, and scrolling.

For behavioral decision protocols (when to confirm actions, how to classify inquiry vs. action
tasks), see `references/behavioral-protocols.md`.

## Handling Permission Dialogs

Android runtime permissions appear as system dialogs that block app interaction until dismissed.

Detection:

- `context.package` contains `permissioncontroller` or `com.google.android.permissioncontroller`
- Button text: "Allow", "Deny", "While using the app", "Only this time", "Don't allow"
- On Android 11+: Three-option dialogs for location, camera, microphone

Strategy:

1. Take a snapshot and check `context.package`
2. If permission dialog detected, decide on response based on automation goal
3. Tap the appropriate option
4. Verify dialog dismissed with fresh snapshot

Example:

```bash
# Snapshot shows permission dialog
uv run android-emu-agent ui snapshot s-abc123
# context.package = "com.google.android.permissioncontroller"
# ^a1 = "While using the app", ^a2 = "Only this time", ^a3 = "Don't allow"

# Grant permission
uv run android-emu-agent action tap s-abc123 ^a1

# Verify dismissed
uv run android-emu-agent ui snapshot s-abc123
# context.package should now be your app
```

Android version differences:

| Android Version | Permission Behavior                                    |
| --------------- | ------------------------------------------------------ |
| 6-9             | "Allow" / "Deny" two-button dialog                     |
| 10              | "Allow all the time" option added for location         |
| 11+             | Three options: "While using", "Only this time", "Deny" |
| 12+             | Approximate location option; permission auto-reset     |
| 13+             | Granular media permissions (photos, videos, music)     |

## Handling System Dialogs

Detection:

- `context.package` is `android` or `com.android.systemui`
- Text patterns: "isn't responding", "has stopped", "Keep waiting", "Close app"

ANR dialog (App Not Responding):

```bash
uv run android-emu-agent ui snapshot s-abc123
# context.package = "android"
# Text: "MyApp isn't responding"
# ^a1 = "Wait", ^a2 = "Close app"

# Option 1: Wait for recovery
uv run android-emu-agent action tap s-abc123 ^a1

# Option 2: Close and restart
uv run android-emu-agent action tap s-abc123 ^a2
uv run android-emu-agent app launch s-abc123 com.example.myapp
```

Crash dialog:

```bash
# Text: "MyApp has stopped" or "MyApp keeps stopping"
# ^a1 = "Close app", ^a2 = "App info" (optional)

uv run android-emu-agent action tap s-abc123 ^a1
uv run android-emu-agent wait idle s-abc123
uv run android-emu-agent app launch s-abc123 com.example.myapp
```

Strategy:

1. Always check `context.package` after each action
2. If system package detected, identify dialog type
3. Handle appropriately: dismiss, wait, or restart app
4. Resume normal automation flow

## Dealing With Stale Refs

`ERR_STALE_REF` occurs when an `^ref` from a previous snapshot no longer matches a current element.

Common causes:

- Animation changed element bounds
- Content dynamically loaded (RecyclerView, lazy loading)
- Dialog appeared or dismissed
- Screen transitioned to new activity
- List scrolled and element recycled

Recovery flow:

```bash
# Action fails with ERR_STALE_REF
uv run android-emu-agent action tap s-abc123 ^a3
# Error: ERR_STALE_REF - Element ^a3 not found or bounds changed

# Recovery: Take fresh snapshot
uv run android-emu-agent ui snapshot s-abc123
# Find the element again by its characteristics
# ^a5 now has the same label "Submit"

# Use new ref
uv run android-emu-agent action tap s-abc123 ^a5
```

Prevention tips:

1. Minimize time between snapshot and action
2. Wait for stability with `wait idle`
3. Avoid acting during animations
4. Re-snapshot after any delay

For structured multi-level recovery, see `references/recovery.md`.

## Waiting for UI Stability

When to wait:

| Scenario              | Wait Command                                       |
| --------------------- | -------------------------------------------------- |
| App launch            | `wait activity` or `wait idle`                     |
| Navigation/transition | `wait activity` or `wait idle`                     |
| Form submission       | `wait text` for success/error or `wait activity`   |
| Loading indicator     | `wait gone` for spinner, `wait exists` for content |
| Dialog appearance     | `wait exists` with expected text                   |
| Animation             | `wait idle`                                        |

Examples:

```bash
# Wait for animations and pending operations to complete
uv run android-emu-agent wait idle s-abc123 --timeout-ms 5000

# Wait for specific activity to be in foreground
uv run android-emu-agent wait activity s-abc123 "HomeActivity" --timeout-ms 10000

# Wait for text to appear anywhere on screen
uv run android-emu-agent wait text s-abc123 "Welcome back" --timeout-ms 5000

# Wait for element with specific text to exist
uv run android-emu-agent wait exists s-abc123 --text "Continue" --timeout-ms 5000

# Wait for loading indicator to disappear
uv run android-emu-agent wait gone s-abc123 --text "Loading..." --timeout-ms 15000
```

Best practices:

1. Always wait after `app launch` before snapshotting
2. Use `wait activity` for screen transitions when you know the target
3. Use `wait idle` as a general-purpose stability check
4. Combine waits for robustness

## Login and Authentication Flows

Identifying elements:

| Element        | Common Identifiers                                        |
| -------------- | --------------------------------------------------------- |
| Username field | `id:*username*`, `id:*email*`, `id:*login*`, hint text    |
| Password field | `id:*password*`, `id:*pass*`, input type password         |
| Submit button  | text "Sign in", "Log in", "Submit", `id:*login*`, `*btn*` |
| Error message  | text "incorrect", "invalid", "failed", red-colored text   |

Step-by-step login flow:

```bash
# 1. Launch app and wait for login screen
uv run android-emu-agent app launch s-abc123 com.example.app
uv run android-emu-agent wait idle s-abc123 --timeout-ms 5000
uv run android-emu-agent ui snapshot s-abc123
# Identify: ^a1 = username field, ^a2 = password field, ^a3 = sign in button

# 2. Enter username
uv run android-emu-agent action tap s-abc123 ^a1
uv run android-emu-agent ui snapshot s-abc123
uv run android-emu-agent action set-text s-abc123 ^a1 "user@example.com"

# 3. Enter password (re-snapshot to get fresh refs)
uv run android-emu-agent ui snapshot s-abc123
uv run android-emu-agent action tap s-abc123 ^a2
uv run android-emu-agent ui snapshot s-abc123
uv run android-emu-agent action set-text s-abc123 ^a2 "secretpassword"

# 4. Dismiss keyboard if visible
uv run android-emu-agent ui snapshot s-abc123
# Check: context.ime_visible = true
uv run android-emu-agent action back s-abc123

# 5. Submit login
uv run android-emu-agent ui snapshot s-abc123
uv run android-emu-agent action tap s-abc123 ^a3

# 6. Wait and verify success
uv run android-emu-agent wait activity s-abc123 "HomeActivity" --timeout-ms 15000
uv run android-emu-agent ui snapshot s-abc123
```

Handling login failures:

```bash
# After tapping submit, check for error messages
uv run android-emu-agent wait idle s-abc123 --timeout-ms 5000
uv run android-emu-agent ui snapshot s-abc123

# Look for error indicators in snapshot:
# - Text containing "incorrect", "invalid", "failed"
# - Still on login activity
# - Error message element appeared
```

Social login notes:

- WebViews or external apps may appear
- `context.package` can change to `com.google.android.gms` or a browser
- Handle account chooser dialogs and 2FA

## Skipping Onboarding and Tutorials

Detection:

- Activity names: `*Onboarding*`, `*Welcome*`, `*Tutorial*`, `*Intro*`
- UI elements: "Skip", "Next", "Get Started", "Continue", page indicators
- ViewPager/carousel layouts with swipeable pages

Strategy 1: Look for a skip button

```bash
uv run android-emu-agent ui snapshot s-abc123
# Look for ^ref with text "Skip"
uv run android-emu-agent action tap s-abc123 ^a5
uv run android-emu-agent wait idle s-abc123
```

Strategy 2: Tap through pages

```bash
uv run android-emu-agent ui snapshot s-abc123
# ^a1 = "Next"
uv run android-emu-agent action tap s-abc123 ^a1
uv run android-emu-agent wait idle s-abc123

uv run android-emu-agent ui snapshot s-abc123
uv run android-emu-agent action tap s-abc123 ^a1
uv run android-emu-agent wait idle s-abc123

uv run android-emu-agent ui snapshot s-abc123
# ^a2 = "Get Started"
uv run android-emu-agent action tap s-abc123 ^a2
```

Strategy 3: Swipe through carousel

```bash
uv run android-emu-agent action swipe left -s s-abc123
uv run android-emu-agent wait idle s-abc123

uv run android-emu-agent action swipe left -s s-abc123
uv run android-emu-agent wait idle s-abc123

uv run android-emu-agent action swipe left -s s-abc123
uv run android-emu-agent wait idle s-abc123

uv run android-emu-agent ui snapshot s-abc123
uv run android-emu-agent action tap s-abc123 ^a1
```

Strategy 4: Use emulator snapshots for repeated testing

```bash
# In Android Studio / emulator
# 1. Complete onboarding manually
# 2. Save a snapshot: "post-onboarding"
# 3. For automation, start from that snapshot
```

## Navigation Patterns

Bottom navigation tabs:

```bash
uv run android-emu-agent ui snapshot s-abc123
# ^a10 = "Home", ^a11 = "Search", ^a12 = "Profile"

uv run android-emu-agent action tap s-abc123 ^a12
uv run android-emu-agent wait idle s-abc123
```

Hamburger menu (navigation drawer):

```bash
uv run android-emu-agent ui snapshot s-abc123
# ^a1 = hamburger menu button

uv run android-emu-agent action tap s-abc123 ^a1
uv run android-emu-agent wait idle s-abc123
uv run android-emu-agent ui snapshot s-abc123
# Drawer items: ^a5 = "Settings", ^a6 = "Help"

uv run android-emu-agent action tap s-abc123 ^a5
```

Back navigation:

```bash
# System back button
uv run android-emu-agent action back s-abc123

# Toolbar back arrow
uv run android-emu-agent ui snapshot s-abc123
# ^a1 = "Navigate up"
uv run android-emu-agent action tap s-abc123 ^a1
```

Toolbar actions:

```bash
uv run android-emu-agent ui snapshot s-abc123
# ^a2 = "Search", ^a3 = "More options"

uv run android-emu-agent action tap s-abc123 ^a3
uv run android-emu-agent wait idle s-abc123
uv run android-emu-agent ui snapshot s-abc123
# Menu items: ^a5 = "Settings", ^a6 = "Share"
```

Tab switching (TabLayout):

```bash
uv run android-emu-agent ui snapshot s-abc123
# ^a1 = "Tab 1" (selected), ^a2 = "Tab 2"

uv run android-emu-agent action tap s-abc123 ^a2
uv run android-emu-agent wait idle s-abc123
```

## Form Filling

Text fields:

```bash
uv run android-emu-agent ui snapshot s-abc123
uv run android-emu-agent action tap s-abc123 ^a1
uv run android-emu-agent ui snapshot s-abc123
uv run android-emu-agent action set-text s-abc123 ^a1 "My text input"

# Clear existing text first
uv run android-emu-agent action clear s-abc123 ^a1
uv run android-emu-agent action set-text s-abc123 ^a1 "New text"

# Dismiss keyboard after entry
uv run android-emu-agent action back s-abc123
```

Checkboxes and toggles:

```bash
uv run android-emu-agent ui snapshot s-abc123
# ^a5 = checkbox, state: { checked: false }

uv run android-emu-agent action tap s-abc123 ^a5
uv run android-emu-agent ui snapshot s-abc123
# Verify: state.checked true
```

Dropdowns and spinners:

```bash
uv run android-emu-agent ui snapshot s-abc123
# ^a3 = spinner showing current selection

uv run android-emu-agent action tap s-abc123 ^a3
uv run android-emu-agent wait idle s-abc123
uv run android-emu-agent ui snapshot s-abc123
# ^a10 = "Option A", ^a11 = "Option B"

uv run android-emu-agent action tap s-abc123 ^a11
uv run android-emu-agent wait idle s-abc123
```

Date pickers:

```bash
uv run android-emu-agent ui snapshot s-abc123
# ^a4 = date field showing "Select date"

uv run android-emu-agent action tap s-abc123 ^a4
uv run android-emu-agent wait idle s-abc123
uv run android-emu-agent ui snapshot s-abc123
# ^a1 = prev month, ^a2 = next month
# Days: ^a15 = "15", ^a20 = "20"

uv run android-emu-agent action tap s-abc123 ^a20
uv run android-emu-agent ui snapshot s-abc123
uv run android-emu-agent action tap s-abc123 ^a30  # "OK"
```

Form validation:

```bash
uv run android-emu-agent action tap s-abc123 ^a1
uv run android-emu-agent wait idle s-abc123
uv run android-emu-agent ui snapshot s-abc123

# Look for:
# - Error text elements
# - "required", "invalid", "must be" in text
```

## Scrolling to Find Elements

Basic scroll commands:

```bash
uv run android-emu-agent action scroll down -s s-abc123
uv run android-emu-agent action scroll up -s s-abc123
uv run android-emu-agent action scroll down -s s-abc123 --distance 0.5
```

Scrolling within containers:

```bash
uv run android-emu-agent ui snapshot s-abc123
# ^a5 = scrollable container

uv run android-emu-agent action scroll down -s s-abc123 --in ^a5
```

Finding elements by scrolling:

```bash
uv run android-emu-agent ui snapshot s-abc123
# Target not visible

uv run android-emu-agent action scroll down -s s-abc123
uv run android-emu-agent wait idle s-abc123
uv run android-emu-agent ui snapshot s-abc123
# Repeat until found or max scrolls reached
```

Scroll distance guidelines:

| Distance | Use Case                              |
| -------- | ------------------------------------- |
| 0.2-0.3  | Small increments, precise positioning |
| 0.5      | Default, half-screen scroll           |
| 0.7-0.8  | Fast scrolling through long lists     |
| 1.0      | Maximum scroll, nearly full screen    |

Horizontal scrolling:

```bash
uv run android-emu-agent action scroll left -s s-abc123
uv run android-emu-agent action scroll right -s s-abc123
uv run android-emu-agent action scroll left -s s-abc123 --in ^a3
```

Loop termination:

1. Set a maximum scroll count (e.g., 10) to avoid infinite loops
2. After each scroll, compare the new snapshot to the previous one — if the elements are unchanged,
   you have reached the end of the list
3. Always `wait idle` before snapshotting after a scroll
4. Use smaller distances when approaching the target area
