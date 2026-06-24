# Create and Run Task Scripts

Use `.aea` task scripts when an Android flow should be easy to read, review, validate, and rerun.
Each `.aea` file compiles into the same task harness as a JSON task spec.

For exact parser rules, see the [`.aea` task script specification](aea-spec.md).

## Prerequisites

- Android Emu Agent is installed with `uv sync --all-extras`.
- The daemon can reach a target emulator or device.
- You have a session ID, or the script includes a `session <session-id>` line.
- You know the package name, activity names, selectors, and placeholder credentials for your target
  app.

Use these commands to check the target before writing a task:

```bash
uv run android-emu-agent device list
uv run android-emu-agent session start --device emulator-5554 --json
uv run android-emu-agent ui snapshot <session-id> --format text
```

## Write a Minimal Script

Create a file such as `checkout-smoke.aea`:

```text
name "checkout smoke"
tap text:"Checkout" || id:com.example:id/checkout
verify exists text:"Payment" timeout_ms=5000
expect activity CheckoutActivity
```

This script:

- Taps a checkout entry point.
- Verifies the next screen after that step.
- Checks the final activity after all steps run.

## Validate Before Running

Run validation before any device action:

```bash
uv run android-emu-agent task validate checkout-smoke.aea
```

Validation checks parser syntax, required arguments, supported operations, and the compiled task
shape. It does not contact a device and does not prove that selectors exist in your app.

## Run the Script

If the script does not include `session <session-id>`, pass the session at runtime:

```bash
uv run android-emu-agent task run checkout-smoke.aea --session <session-id> --json
```

If the script includes a `session` line, the runtime option is optional:

```text
name "idle snapshot"
session s-abc123
wait idle timeout_ms=5000
snapshot mode=compact
```

```bash
uv run android-emu-agent task run idle-snapshot.aea --json
```

Use `--continue-on-failure` only when collecting all step failures matters more than stopping at the
first failed action or verifier.

## Verify the Result

A successful run returns `status: done` and `passed: true` in JSON output. A failed run returns
`status: failed` with the failing step, verifier, operation, and response payload.

After a failed run, capture evidence before changing the screen:

```bash
uv run android-emu-agent artifact save-snapshot <session-id> --json
uv run android-emu-agent artifact screenshot <session-id> --pull --output ./artifacts/failure.png --json
uv run android-emu-agent artifact logs --session <session-id> --app com.example.app --type errors --since "10m ago" --json
```

## Common Script Lines

### Metadata

```text
name "login flow smoke"
description "Launch the app, fill the login form, and verify the home activity."
session s-abc123
```

`session` is optional. If both the file and the CLI provide a session, the CLI `--session` value
overrides the script value.

### App and Action Steps

```text
launch com.example.app
tap text:"Sign in" || id:com.example:id/sign_in
set-text id:com.example:id/email "agent@example.com"
clear id:com.example:id/search
swipe down distance=0.8 duration_ms=300
back
home
recents
```

`tap`, `long-tap`, and `clear` accept selector strings. `set-text` treats the first value token as
the selector and the rest of the line as text, so use a single selector token such as a ref or
resource ID.

### Waits and Verifiers

```text
wait idle timeout_ms=5000
wait activity HomeActivity timeout_ms=15000
wait text "Payment complete" timeout_ms=5000
wait exists text:"Payment" timeout_ms=5000
wait gone text:"Loading" timeout_ms=10000
```

`verify` attaches to the previous step:

```text
tap text:"Continue" || id:com.example:id/continue
verify exists text:"Welcome" timeout_ms=5000
```

`expect` adds a final task-level verifier:

```text
expect activity HomeActivity
```

### Snapshots

```text
snapshot
snapshot mode=compact
snapshot mode=full
snapshot mode=raw
```

Use snapshots when the task should leave structured UI evidence at a specific point in the flow.

## Use the Checked-In Examples

The repository includes ready-to-edit examples:

| File                                | Purpose                                                         |
| ----------------------------------- | --------------------------------------------------------------- |
| `examples/tasks/idle-snapshot.aea`  | Wait for idle and capture a compact snapshot.                   |
| `examples/tasks/checkout-smoke.aea` | Tap a checkout entry point and verify payment UI.               |
| `examples/tasks/login-flow.aea`     | Launch an app, fill a login form, and verify the home activity. |

Validate and run an example:

```bash
uv run android-emu-agent task validate examples/tasks/checkout-smoke.aea
uv run android-emu-agent task run examples/tasks/checkout-smoke.aea --session <session-id> --json
```

Before running app-specific examples, replace placeholder package names, selectors, activity names,
and credentials with values from your app.

## Troubleshoot

| Symptom                     | Likely cause                                  | Next action                                                            |
| --------------------------- | --------------------------------------------- | ---------------------------------------------------------------------- |
| `ERR_TASK_SCRIPT_INVALID`   | The parser rejected a script line             | Fix the reported line and rerun `task validate`.                       |
| `ERR_TASK_INVALID`          | The compiled task shape is invalid            | Check required fields such as `ref`, `text`, `package`, or `activity`. |
| `ERR_TASK_UNSUPPORTED_STEP` | A command is not part of the task harness     | Use only supported action, wait, app, and UI operations.               |
| `ERR_NOT_FOUND`             | The selector did not match the current screen | Capture a fresh snapshot and update the selector.                      |
| `ERR_TIMEOUT`               | A wait or verifier did not complete           | Check the screen state or increase `timeout_ms`.                       |
| `ERR_EXPECTATION_FAILED`    | A final expectation failed                    | Inspect the failure payload and capture artifacts before retrying.     |
