# Workflow Examples

These examples cover the workflows readers are most likely to need first: connect to a device, open
an app, inspect the screen, act, wait, verify, recover from common UI issues, and collect evidence.

Assumptions:

- The `android-emu-agent` CLI is installed and on `PATH`. See [Installation](installation.md).
- The daemon can reach an emulator or device.
- `com.example.app` is the target package.
- `./artifacts/` is local scratch space and is ignored by git.

Replace placeholders such as `<session-id>`, `<device-serial>`, and `<apk-path>` before running a
command.

## Connect to a Device and Start a Session

Use this flow at the start of an automation run.

Confirm that the Android SDK can see a target:

```bash
adb devices
android-emu-agent device list
```

Optional: boot an emulator if no target is running:

```bash
android-emu-agent emulator list-avds
android-emu-agent emulator start <avd-name> --wait-boot
```

Start the daemon and check its status:

```bash
android-emu-agent daemon start
android-emu-agent daemon status --json
```

Start a session:

```bash
android-emu-agent session start --device <device-serial> --json
```

Verify that the response includes `status: done` and `session_id`.

## Install or Reset an App Before Testing

Use this flow when a run must start from a known app state.

Install or replace the APK. Relative APK paths are resolved from the CLI's current directory, not
the directory where the daemon was started:

```bash
android-emu-agent app install <apk-path> --session <session-id> --grant-permissions --json
```

Optional: clear app data:

```bash
android-emu-agent app reset <session-id> com.example.app
```

Launch the app:

```bash
android-emu-agent app launch <session-id> com.example.app
android-emu-agent wait idle <session-id> --timeout-ms 5000
```

Verify the foreground app:

```bash
android-emu-agent expect current-app <session-id> --package com.example.app
```

If installation fails, check that the target allows APK installs and that `<apk-path>` points to a
local APK file.

## Inspect a Screen and Tap a Control

Use this flow for the normal observe, act, verify loop.

Capture a compact text snapshot:

```bash
android-emu-agent ui snapshot <session-id> --format text
```

Tap a ref from the snapshot:

```bash
android-emu-agent action tap <session-id> ^g1a1
```

Verify the new screen:

```bash
android-emu-agent ui snapshot <session-id> --format text
```

If the target should be reusable across app versions, prefer a semantic selector:

```bash
android-emu-agent action tap <session-id> 'text:"Sign in" || id:com.example:id/sign_in'
```

## Fill a Form

Use refs from a fresh snapshot for text fields. This avoids typing into the wrong field after the UI
changes.

Launch the screen and wait for it to settle:

```bash
android-emu-agent app launch <session-id> com.example.app
android-emu-agent wait idle <session-id> --timeout-ms 5000
android-emu-agent ui snapshot <session-id> --format text
```

Set text on the email and password fields:

```bash
android-emu-agent action set-text <session-id> ^g1a2 "agent@example.com"
android-emu-agent action set-text <session-id> ^g1a3 "test-password"
```

Submit and verify the next state:

```bash
android-emu-agent action tap <session-id> ^g1a4
android-emu-agent expect exists <session-id> --text "Welcome" --timeout-ms 10000
```

If the keyboard blocks the submit button, dismiss it before tapping:

```bash
android-emu-agent action back <session-id>
android-emu-agent wait idle <session-id> --timeout-ms 3000
```

## Wait for Navigation or Loading State

Use waits instead of fixed sleeps. Wait commands return structured timeout errors when the expected
state does not appear.

```bash
android-emu-agent action tap <session-id> 'text:"Checkout" || id:com.example:id/checkout'
android-emu-agent wait gone <session-id> --text "Loading" --timeout-ms 10000
android-emu-agent wait exists <session-id> --text "Payment" --timeout-ms 10000
android-emu-agent expect activity <session-id> CheckoutActivity --timeout-ms 5000
```

If the wait times out, capture a fresh snapshot and check whether the app navigated to a different
state than expected.

## Recover When an Element Is Missing

Use this flow after `ERR_NOT_FOUND`, `ERR_STALE_REF`, or a snapshot that does not show the target.

Wait for the UI to settle:

```bash
android-emu-agent wait idle <session-id> --timeout-ms 3000
```

Capture a full snapshot once:

```bash
android-emu-agent ui snapshot <session-id> --full --format text
```

Inspect selector capability support:

```bash
android-emu-agent device capabilities --session <session-id> --json
```

Retry with a semantic selector:

```bash
android-emu-agent action tap <session-id> 'text-contains:"Continue" enabled:true clickable:true'
```

If no selector is reliable, capture a screenshot before using coordinates:

```bash
android-emu-agent ui screenshot <session-id> --pull --output ./artifacts/missing-target.png
android-emu-agent action tap <session-id> coords:540,1820
```

Use coordinates as the last resort because they are sensitive to device size, orientation, font
scale, and layout changes.

## Handle Permission and System Setup

Use this flow when an app needs notification, camera, location, or other runtime permission setup
before a test.

List requested and granted permissions:

```bash
android-emu-agent system permissions list com.example.app --session <session-id> --json
```

Grant a runtime permission:

```bash
android-emu-agent system permissions grant com.example.app android.permission.POST_NOTIFICATIONS --session <session-id> --json
```

Optional: open Android system surfaces for manual or agent inspection:

```bash
android-emu-agent system notifications open --session <session-id>
android-emu-agent system quick-settings open --session <session-id>
```

Permission changes still follow Android runtime permission rules. If a permission cannot be granted,
check the app manifest, Android version, and device policy.

## Run a Reusable Task Script

Use a `.aea` script when a flow should be checked in, reviewed, and repeated.

Validate the script without touching a device:

```bash
android-emu-agent task validate examples/tasks/checkout-smoke.aea
```

Run it against the active session:

```bash
android-emu-agent task run examples/tasks/checkout-smoke.aea --session <session-id> --json
```

If it fails, inspect the failure payload and preserve evidence:

```bash
android-emu-agent artifact save-snapshot <session-id> --json
android-emu-agent artifact screenshot <session-id> --pull --output ./artifacts/task-failure.png --json
```

For writing task scripts, use the [task script guide](tasks.md). For exact grammar, use the
[`.aea` specification](aea-spec.md).

## Collect Evidence After a Failed Flow

Use this sequence after a failed action, failed expectation, crash, or confusing UI state. It
collects bounded evidence without changing app state further.

Save the latest structured UI state:

```bash
android-emu-agent artifact save-snapshot <session-id> --json
```

Capture a screenshot:

```bash
android-emu-agent artifact screenshot <session-id> --pull --output ./artifacts/failure-screen.png --json
```

Pull focused logs from the last few minutes:

```bash
android-emu-agent artifact logs \
  --session <session-id> \
  --app com.example.app \
  --type errors \
  --since "10m ago" \
  --json
```

Add current app and task context:

```bash
android-emu-agent app current --session <session-id> --json
android-emu-agent app task-stack --session <session-id> --json
```

Create one bundle with available evidence:

```bash
android-emu-agent artifact bundle <session-id> --json
```

If the failure looks like a crash or ANR, add reliability data:

```bash
android-emu-agent reliability profile com.example.app --session <session-id> --json
android-emu-agent reliability exit-info com.example.app --session <session-id> --json
```

## Record a Trace for a Flaky Flow

Use traces when a flow fails intermittently and you need replayable daemon request/response
evidence. Replay is a dry-run plan, so inspecting a trace does not mutate a device.

```bash
android-emu-agent trace start <session-id> --label checkout-flake
android-emu-agent ui snapshot <session-id> --format text
android-emu-agent action tap <session-id> 'text:"Checkout" || id:com.example:id/checkout'
android-emu-agent wait exists <session-id> --text "Payment" --timeout-ms 5000
android-emu-agent trace stop <session-id> --output ./artifacts/checkout-flake.aea-trace.zip
android-emu-agent trace replay ./artifacts/checkout-flake.aea-trace.zip --until-failure
android-emu-agent trace export ./artifacts/checkout-flake.aea-trace.zip --output ./artifacts/checkout-flake.md
```

Trace input paths and explicit output paths expand `~` and are relative to the directory where you
run the CLI, not the daemon's working directory. With no `--output`, `trace stop` uses the daemon's
default archive directory. For `trace export`, omit `--output` and use `--json` to read the
Markdown response without writing a report file.

Diagnostics and traces redact `set_text` input in JSON tasks using `action`, `kind` plus
`operation`, or `kind` plus `op`. This applies to newly recorded data; existing diagnostics and
archives are not rewritten. Review traces, screenshots, and logs for sensitive app content before
sharing them.

Attach the `.aea-trace.zip`, exported Markdown, and any screenshots or logs collected during the
same run.

## Use Visual Grounding for Screenshot Review

Use visual grounding when text output is not enough and a human or vision model needs screenshot
coordinates for selected refs. Grounding uses the latest snapshot; it does not run OCR or image
matching.

```bash
android-emu-agent ui snapshot <session-id> --format text
android-emu-agent ui ground <session-id> --ref ^g1a1 --ref ^g1a4 --pull --output ./artifacts/grounding.json --json
android-emu-agent ui screenshot <session-id> --pull --output ./artifacts/screen.png --json
```

Verify that `grounding.json` includes `coordinate_space`, `screenshot_path`, `ref`, `bounds`, and
`center` fields for the selected refs.

## Preflight an Intent or Deep Link

Use `resolve-intent` before launching an implicit intent or deep link on a device that may have
multiple handlers.

```bash
android-emu-agent app resolve-intent \
  --session <session-id> \
  --action android.intent.action.VIEW \
  --data "https://example.com/deep" \
  --json

android-emu-agent app deeplink <session-id> "https://example.com/deep"
android-emu-agent wait activity <session-id> DeepLinkActivity --timeout-ms 10000
```

If the preflight is ambiguous, launch with an explicit package or component:

```bash
android-emu-agent app intent <session-id> \
  --action android.intent.action.VIEW \
  --data "https://example.com/deep" \
  --package com.example.app
```

Use `--component com.example.app/.DeepLinkActivity` when you know the exact activity and want to
avoid resolver choice entirely.

## Attach a Debugger at Startup

Use this flow when UI-level signals are not enough and the target app is debuggable.

```bash
android-emu-agent app launch <session-id> com.example.app --wait-debugger
android-emu-agent debug attach --session <session-id> --package com.example.app --keep-suspended
android-emu-agent debug break set com.example.app.MainActivity 42 --session <session-id>
android-emu-agent debug resume --session <session-id>
android-emu-agent debug events --session <session-id>
android-emu-agent debug observe --session <session-id> --json
android-emu-agent debug detach --session <session-id>
```

Debugger commands require JDK 17+ and a debuggable app. Use `--process` on `debug attach` when the
package has multiple debuggable processes.
