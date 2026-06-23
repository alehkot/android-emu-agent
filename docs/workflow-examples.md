# Workflow Examples

These examples fill in multi-command workflows that are easy to miss when reading individual CLI
commands. They assume an active session named `s-abc123` and a target app package `com.example.app`.

## Visual Grounding

Use visual grounding when a compact text snapshot is not enough and a human or vision model needs to
connect refs to screenshot coordinates. Grounding uses the latest snapshot; it does not run OCR or
image matching.

```bash
# 1. Capture a fresh actionable snapshot.
uv run android-emu-agent ui snapshot s-abc123 --format text

# 2. If the element is not in compact mode, widen the snapshot once.
uv run android-emu-agent ui snapshot s-abc123 --full

# 3. Create screenshot-to-ref metadata for the refs you care about.
uv run android-emu-agent ui ground s-abc123 --ref ^a1 --ref ^a4 --pull --output ./artifacts/grounding.json --json

# 4. Pull a companion screenshot if you want a local image beside the metadata.
uv run android-emu-agent ui screenshot s-abc123 --pull --output ./artifacts/screen.png --json
```

The grounding JSON includes `coordinate_space`, `screenshot_path`, each selected `ref`, `bounds`,
and `center`. Use those fields to explain where `^a1` or `^a4` appears in the screenshot.

## Trace Archive for a Flaky Flow

Use traces when a flow fails intermittently and you need replayable evidence of daemon exchanges.
Replay is a dry-run plan, so it is safe to inspect before rerunning anything on a device.

```bash
# 1. Start recording before the repro steps.
uv run android-emu-agent trace start s-abc123 --label checkout-flake

# 2. Run the smallest flow that reproduces the issue.
uv run android-emu-agent ui snapshot s-abc123 --format text
uv run android-emu-agent action tap s-abc123 'text:"Checkout" || id:com.example:id/checkout'
uv run android-emu-agent wait exists s-abc123 --text "Payment" --timeout-ms 5000
uv run android-emu-agent expect activity s-abc123 CheckoutActivity --timeout-ms 5000

# 3. Stop recording into a named archive.
uv run android-emu-agent trace stop s-abc123 --output ./artifacts/checkout-flake.aea-trace.zip

# 4. Inspect the dry-run replay plan and export a bug-report-friendly Markdown summary.
uv run android-emu-agent trace replay ./artifacts/checkout-flake.aea-trace.zip --until-failure
uv run android-emu-agent trace export ./artifacts/checkout-flake.aea-trace.zip --output ./artifacts/checkout-flake.md
```

Attach the `.aea-trace.zip`, exported Markdown, and any screenshots or logs collected during the
same run.

## Capability-Guided Selector Planning

Use `device capabilities` before writing reusable automations. It tells an agent which selector
forms, subsystem features, and device-only operations are available on the target.

```bash
# 1. Inspect capabilities for the active session.
uv run android-emu-agent device capabilities --session s-abc123 --json

# 2. Prefer semantic selectors when available.
uv run android-emu-agent action tap s-abc123 'text:"Sign in" || id:com.example:id/sign_in'

# 3. Add state filters when the screen has multiple matching controls.
uv run android-emu-agent action tap s-abc123 'text:"Continue" enabled:true clickable:true'

# 4. Fall back to coordinates only when the capability report and screenshots make that safe.
uv run android-emu-agent ui screenshot s-abc123 --pull --output ./artifacts/continue.png
uv run android-emu-agent action tap s-abc123 coords:540,1820
```

Useful fields in the JSON response:

- `selectors.target_syntax`: supported selector syntax, including refs, text, IDs, fallback
  selectors, state filters, and coordinates.
- `selectors.ref_healing`: whether stale refs can be rebound against newer snapshots.
- `automation.*`: higher-level features such as task harnesses, traces, visual grounding, and native
  performance artifacts.
- `device_features.root_required_available`: whether root-only file/reliability operations are
  available.

## Intent and Deep-Link Preflight

Use `resolve-intent` to inspect the target before launching an implicit intent or deep link. This is
safer when a device may have multiple handlers.

```bash
# 1. Resolve without launching.
uv run android-emu-agent app resolve-intent \
  --session s-abc123 \
  --action android.intent.action.VIEW \
  --data "https://example.com/deep" \
  --json

# 2. Launch the same URI as a deep link when the resolved target is correct.
uv run android-emu-agent app deeplink s-abc123 "https://example.com/deep"
uv run android-emu-agent wait activity s-abc123 DeepLinkActivity --timeout-ms 10000

# 3. Use an explicit package/component when the preflight shows ambiguity.
uv run android-emu-agent app intent s-abc123 \
  --action android.intent.action.VIEW \
  --data "https://example.com/deep" \
  --package com.example.app

# 4. If debugging startup code, launch the intent paused for JDWP attach.
uv run android-emu-agent app intent s-abc123 \
  --action android.intent.action.VIEW \
  --data "https://example.com/deep" \
  --package com.example.app \
  --wait-debugger
uv run android-emu-agent debug attach --session s-abc123 --package com.example.app --keep-suspended
```

For explicit screens, use `--component com.example.app/.DeepLinkActivity` when you know the activity
name and want to avoid resolver choice entirely.

## Evidence Bundle After a Failed Flow

Use this sequence after a failed action, failed expectation, crash, or confusing UI state. It
collects bounded evidence without changing app state further.

```bash
# 1. Preserve the latest structured UI state.
uv run android-emu-agent artifact save-snapshot s-abc123 --json

# 2. Capture a screenshot for visual context.
uv run android-emu-agent artifact screenshot s-abc123 --pull --output ./artifacts/failure-screen.png --json

# 3. Pull focused logs from the last few minutes.
uv run android-emu-agent artifact logs \
  --session s-abc123 \
  --app com.example.app \
  --type errors \
  --since "10m ago" \
  --json

# 4. Add current app/task context.
uv run android-emu-agent app current --session s-abc123 --json
uv run android-emu-agent app task-stack --session s-abc123 --json

# 5. Create one zip with snapshot, screenshot, and logs.
uv run android-emu-agent artifact bundle s-abc123 --json
```

If the failure looks like a crash or ANR, follow with `reliability profile`,
`reliability exit-info`, and the triage flow in
`skills/android-emu-agent/references/reliability.md`.
