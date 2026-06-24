# Workflow Examples

These examples cover the workflows readers are most likely to need first: connect to a device, open
an app, inspect the screen, act, wait, verify, recover from common UI issues, and collect evidence.

Assumptions:

- You are in the repository root.
- Android Emu Agent is installed with `uv sync --all-extras`.
- The daemon can reach an emulator or device.
- `com.example.app` is the target package.
- `./artifacts/` is local scratch space and is ignored by git.

Replace placeholders such as `<session-id>`, `<device-serial>`, and `<apk-path>` before running a
command.

## Connect to a Device and Start a Session

Use this flow at the start of an automation run.

1. Confirm that the Android SDK can see a target.

   ```bash
   adb devices
   uv run android-emu-agent device list
   ```

2. Optional: boot an emulator if no target is running.

   ```bash
   uv run android-emu-agent emulator list-avds
   uv run android-emu-agent emulator start <avd-name> --wait-boot
   ```

3. Start the daemon and check its status.

   ```bash
   uv run android-emu-agent daemon start
   uv run android-emu-agent daemon status --json
   ```

4. Start a session.

   ```bash
   uv run android-emu-agent session start --device <device-serial> --json
   ```

Verify that the response includes `status: done` and `session_id`.

## Install or Reset an App Before Testing

Use this flow when a run must start from a known app state.

1. Install or replace the APK.

   ```bash
   uv run android-emu-agent app install <apk-path> --session <session-id> --grant-permissions --json
   ```

2. Optional: clear app data.

   ```bash
   uv run android-emu-agent app reset <session-id> com.example.app
   ```

3. Launch the app.

   ```bash
   uv run android-emu-agent app launch <session-id> com.example.app
   uv run android-emu-agent wait idle <session-id> --timeout-ms 5000
   ```

4. Verify the foreground app.

   ```bash
   uv run android-emu-agent expect current-app <session-id> --package com.example.app
   ```

If installation fails, check that the target allows APK installs and that `<apk-path>` points to a
local APK file.

## Inspect a Screen and Tap a Control

Use this flow for the normal observe, act, verify loop.

1. Capture a compact text snapshot.

   ```bash
   uv run android-emu-agent ui snapshot <session-id> --format text
   ```

2. Tap a ref from the snapshot.

   ```bash
   uv run android-emu-agent action tap <session-id> ^a1
   ```

3. Verify the new screen.

   ```bash
   uv run android-emu-agent ui snapshot <session-id> --format text
   ```

If the target should be reusable across app versions, prefer a semantic selector:

```bash
uv run android-emu-agent action tap <session-id> 'text:"Sign in" || id:com.example:id/sign_in'
```

## Fill a Form

Use refs from a fresh snapshot for text fields. This avoids typing into the wrong field after the UI
changes.

1. Launch the screen and wait for it to settle.

   ```bash
   uv run android-emu-agent app launch <session-id> com.example.app
   uv run android-emu-agent wait idle <session-id> --timeout-ms 5000
   uv run android-emu-agent ui snapshot <session-id> --format text
   ```

2. Set text on the email and password fields.

   ```bash
   uv run android-emu-agent action set-text <session-id> ^a2 "agent@example.com"
   uv run android-emu-agent action set-text <session-id> ^a3 "test-password"
   ```

3. Submit and verify the next state.

   ```bash
   uv run android-emu-agent action tap <session-id> ^a4
   uv run android-emu-agent expect exists <session-id> --text "Welcome" --timeout-ms 10000
   ```

If the keyboard blocks the submit button, dismiss it before tapping:

```bash
uv run android-emu-agent action back <session-id>
uv run android-emu-agent wait idle <session-id> --timeout-ms 3000
```

## Wait for Navigation or Loading State

Use waits instead of fixed sleeps. Wait commands return structured timeout errors when the expected
state does not appear.

```bash
uv run android-emu-agent action tap <session-id> 'text:"Checkout" || id:com.example:id/checkout'
uv run android-emu-agent wait gone <session-id> --text "Loading" --timeout-ms 10000
uv run android-emu-agent wait exists <session-id> --text "Payment" --timeout-ms 10000
uv run android-emu-agent expect activity <session-id> CheckoutActivity --timeout-ms 5000
```

If the wait times out, capture a fresh snapshot and check whether the app navigated to a different
state than expected.

## Recover When an Element Is Missing

Use this flow after `ERR_NOT_FOUND`, `ERR_STALE_REF`, or a snapshot that does not show the target.

1. Wait for the UI to settle.

   ```bash
   uv run android-emu-agent wait idle <session-id> --timeout-ms 3000
   ```

2. Capture a full snapshot once.

   ```bash
   uv run android-emu-agent ui snapshot <session-id> --full --format text
   ```

3. Inspect selector capability support.

   ```bash
   uv run android-emu-agent device capabilities --session <session-id> --json
   ```

4. Retry with a semantic selector.

   ```bash
   uv run android-emu-agent action tap <session-id> 'text-contains:"Continue" enabled:true clickable:true'
   ```

5. If no selector is reliable, capture a screenshot before using coordinates.

   ```bash
   uv run android-emu-agent ui screenshot <session-id> --pull --output ./artifacts/missing-target.png
   uv run android-emu-agent action tap <session-id> coords:540,1820
   ```

Use coordinates as the last resort because they are sensitive to device size, orientation, font
scale, and layout changes.

## Handle Permission and System Setup

Use this flow when an app needs notification, camera, location, or other runtime permission setup
before a test.

1. List requested and granted permissions.

   ```bash
   uv run android-emu-agent system permissions list com.example.app --session <session-id> --json
   ```

2. Grant a runtime permission.

   ```bash
   uv run android-emu-agent system permissions grant com.example.app android.permission.POST_NOTIFICATIONS --session <session-id> --json
   ```

3. Optional: open Android system surfaces for manual or agent inspection.

   ```bash
   uv run android-emu-agent system notifications open --session <session-id>
   uv run android-emu-agent system quick-settings open --session <session-id>
   ```

Permission changes still follow Android runtime permission rules. If a permission cannot be granted,
check the app manifest, Android version, and device policy.

## Run a Reusable Task Script

Use a `.aea` script when a flow should be checked in, reviewed, and repeated.

1. Validate the script without touching a device.

   ```bash
   uv run android-emu-agent task validate examples/tasks/checkout-smoke.aea
   ```

2. Run it against the active session.

   ```bash
   uv run android-emu-agent task run examples/tasks/checkout-smoke.aea --session <session-id> --json
   ```

3. If it fails, inspect the failure payload and preserve evidence.

   ```bash
   uv run android-emu-agent artifact save-snapshot <session-id> --json
   uv run android-emu-agent artifact screenshot <session-id> --pull --output ./artifacts/task-failure.png --json
   ```

For writing task scripts, use the [task script guide](tasks.md). For exact grammar, use the
[`.aea` specification](aea-spec.md).

## Collect Evidence After a Failed Flow

Use this sequence after a failed action, failed expectation, crash, or confusing UI state. It
collects bounded evidence without changing app state further.

1. Save the latest structured UI state.

   ```bash
   uv run android-emu-agent artifact save-snapshot <session-id> --json
   ```

2. Capture a screenshot.

   ```bash
   uv run android-emu-agent artifact screenshot <session-id> --pull --output ./artifacts/failure-screen.png --json
   ```

3. Pull focused logs from the last few minutes.

   ```bash
   uv run android-emu-agent artifact logs \
     --session <session-id> \
     --app com.example.app \
     --type errors \
     --since "10m ago" \
     --json
   ```

4. Add current app and task context.

   ```bash
   uv run android-emu-agent app current --session <session-id> --json
   uv run android-emu-agent app task-stack --session <session-id> --json
   ```

5. Create one bundle with available evidence.

   ```bash
   uv run android-emu-agent artifact bundle <session-id> --json
   ```

If the failure looks like a crash or ANR, add reliability data:

```bash
uv run android-emu-agent reliability profile com.example.app --session <session-id> --json
uv run android-emu-agent reliability exit-info com.example.app --session <session-id> --json
```

## Record a Trace for a Flaky Flow

Use traces when a flow fails intermittently and you need replayable daemon request/response
evidence. Replay is a dry-run plan, so inspecting a trace does not mutate a device.

```bash
uv run android-emu-agent trace start <session-id> --label checkout-flake
uv run android-emu-agent ui snapshot <session-id> --format text
uv run android-emu-agent action tap <session-id> 'text:"Checkout" || id:com.example:id/checkout'
uv run android-emu-agent wait exists <session-id> --text "Payment" --timeout-ms 5000
uv run android-emu-agent trace stop <session-id> --output ./artifacts/checkout-flake.aea-trace.zip
uv run android-emu-agent trace replay ./artifacts/checkout-flake.aea-trace.zip --until-failure
uv run android-emu-agent trace export ./artifacts/checkout-flake.aea-trace.zip --output ./artifacts/checkout-flake.md
```

Attach the `.aea-trace.zip`, exported Markdown, and any screenshots or logs collected during the
same run.

## Use Visual Grounding for Screenshot Review

Use visual grounding when text output is not enough and a human or vision model needs screenshot
coordinates for selected refs. Grounding uses the latest snapshot; it does not run OCR or image
matching.

```bash
uv run android-emu-agent ui snapshot <session-id> --format text
uv run android-emu-agent ui ground <session-id> --ref ^a1 --ref ^a4 --pull --output ./artifacts/grounding.json --json
uv run android-emu-agent ui screenshot <session-id> --pull --output ./artifacts/screen.png --json
```

Verify that `grounding.json` includes `coordinate_space`, `screenshot_path`, `ref`, `bounds`, and
`center` fields for the selected refs.

## Preflight an Intent or Deep Link

Use `resolve-intent` before launching an implicit intent or deep link on a device that may have
multiple handlers.

```bash
uv run android-emu-agent app resolve-intent \
  --session <session-id> \
  --action android.intent.action.VIEW \
  --data "https://example.com/deep" \
  --json

uv run android-emu-agent app deeplink <session-id> "https://example.com/deep"
uv run android-emu-agent wait activity <session-id> DeepLinkActivity --timeout-ms 10000
```

If the preflight is ambiguous, launch with an explicit package or component:

```bash
uv run android-emu-agent app intent <session-id> \
  --action android.intent.action.VIEW \
  --data "https://example.com/deep" \
  --package com.example.app
```

Use `--component com.example.app/.DeepLinkActivity` when you know the exact activity and want to
avoid resolver choice entirely.

## Attach a Debugger at Startup

Use this flow when UI-level signals are not enough and the target app is debuggable.

```bash
uv run android-emu-agent app launch <session-id> com.example.app --wait-debugger
uv run android-emu-agent debug attach --session <session-id> --package com.example.app --keep-suspended
uv run android-emu-agent debug break set com.example.app.MainActivity 42 --session <session-id>
uv run android-emu-agent debug resume --session <session-id>
uv run android-emu-agent debug events --session <session-id>
uv run android-emu-agent debug observe --session <session-id> --json
uv run android-emu-agent debug detach --session <session-id>
```

Debugger commands require JDK 17+ and a debuggable app. Use `--process` on `debug attach` when the
package has multiple debuggable processes.
