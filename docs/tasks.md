# Create and Run Task Scripts

Use `.aea` task scripts when an Android flow should be easy to read, review, validate, and rerun.
Each `.aea` file compiles into the same task harness as a JSON task spec.

For exact parser rules, see the [`.aea` task script specification](aea-spec.md).

## Prerequisites

- The `android-emu-agent` CLI is installed and on `PATH`. See [Installation](installation.md).
- The daemon can reach a target emulator or device.
- You have a session ID, or the script includes a `session <session-id>` line.
- You know the package name, activity names, selectors, and placeholder credentials for your target
  app.

Use these commands to check the target before writing a task:

```bash
android-emu-agent device list
android-emu-agent session start --device emulator-5554 --json
android-emu-agent ui snapshot <session-id> --format text
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
android-emu-agent task validate checkout-smoke.aea
```

Validation checks parser syntax, required arguments, supported operations, and the compiled task
shape. Every step and verifier is also checked against the daemon's request model, including field
types and snapshot modes. For example, a JSON wait with `"timeout_ms": "later"` is rejected with
`ERR_TASK_INVALID` and the field location before any step runs. Existing supported type conversions,
such as a numeric string timeout, remain accepted.

`task run` performs the same whole-task preflight before dispatching its first action, including
when `--continue-on-failure` is set. Invalid fields in a later step, an attached verifier, or a
final verifier therefore cannot cause earlier steps to run first. Validation does not contact a
device and does not prove that selectors exist, packages are installed, or runtime operation
constraints will be satisfied. Runtime failures can still occur after earlier steps have run.

## Run the Script

If the script does not include `session <session-id>`, pass the session at runtime:

```bash
android-emu-agent task run checkout-smoke.aea --session <session-id> --json
```

If the script includes a `session` line, the runtime option is optional:

```text
name "idle snapshot"
session s-abc123
wait idle timeout_ms=5000
snapshot mode=compact
```

```bash
android-emu-agent task run idle-snapshot.aea --json
```

Use `--continue-on-failure` only when collecting all step failures matters more than stopping at the
first failed action or verifier.

### Long-running tasks

The daemon returns one report after all sequential steps and verifiers finish. For a task that may
take longer than ten seconds, explicitly allow a longer HTTP response wait:

```bash
android-emu-agent task run examples/tasks/login-flow.aea --session <session-id> --http-timeout-seconds 120 --json
```

`--http-timeout-seconds` accepts a finite positive number of seconds (default: `10`). Choose a
budget covering the full sequence, including attached and final verifiers and device I/O, not just
the longest individual wait. It changes only the run request's HTTP read timeout; connection, write,
pool, and daemon-startup health checks retain their existing timeouts. Validation commands and
per-condition `timeout_ms` values are unchanged.

This is an HTTP inactivity timeout, not a total task deadline or a cancellation mechanism. A
transport timeout can leave the daemon still executing the task. The CLI does not automatically
replay a possibly delivered task; inspect device state before deciding whether to run it again. The
timeout is not automatically inferred from the task.

## Verify the Result

A successful run returns `status: done` and `passed: true` in JSON output. A failed run returns
`status: failed` with the failing step, verifier, operation, and response payload. `task run` exits
with code `0` on success and `1` when a step or verifier fails, in both human and `--json` output
modes. The complete failure report is printed before exiting. `--continue-on-failure` continues
collecting results; it does not turn a failed run into a successful exit.

After a failed run, capture evidence before changing the screen:

```bash
android-emu-agent artifact save-snapshot <session-id> --json
android-emu-agent artifact screenshot <session-id> --pull --output ./artifacts/failure.png --json
android-emu-agent artifact logs --session <session-id> --app com.example.app --type errors --since "10m ago" --json
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

Quote literal text containing `=` so it is not treated as an option, for example
`set-text id:com.example:id/search "x=y"`. Deep links can contain query parameters:
`deeplink "https://example.com/search?q=android&sort=date"`. Quoting an entire token makes it
literal; quoting just an option value, as in `timeout_ms="5000"`, still sets the option.

### Waits and Verifiers

```text
wait idle timeout_ms=5000
wait activity HomeActivity timeout_ms=15000
wait text "Payment complete" timeout_ms=5000
wait exists text:"Payment" timeout_ms=5000
wait gone text:"Loading" timeout_ms=10000
```

For activity, text, exists, and gone conditions, `timeout_ms` covers device polling and the delays
between polls. The same deadline applies when these conditions are used as verifiers. A stalled
device call produces `ERR_TIMEOUT`; it cannot turn into a successful result after the deadline. The
underlying device I/O may still finish after the wait returns, since running worker threads cannot
be forcibly cancelled.

`verify` attaches to the previous step:

```text
tap text:"Continue" || id:com.example:id/continue
verify exists text:"Welcome" timeout_ms=5000
```

For `exists` and `gone`, task waits and verifiers accept snapshot refs or direct element
selectors, including quoted values, regexes, and compound state filters such as
`text:"Welcome" enabled:true`. Coordinate selectors and `||` fallback chains are rejected during
validation, before any device actions run. JSON tasks can use the same selector expression in
`ref`, or a `selector` dictionary with string and boolean values.

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
android-emu-agent task validate examples/tasks/checkout-smoke.aea
android-emu-agent task run examples/tasks/checkout-smoke.aea --session <session-id> --json
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

### Nonfinite swipe distances

JSON task swipe distances must be finite, including values supplied as numeric strings. NaN,
infinity, and overflowing exponents such as `"1e999"` produce `ERR_TASK_INVALID` with the step and
field location (for example, `steps[2].distance`). Validation and execution reject the entire task
before any action runs, even with `--continue-on-failure`. Finite distance range checks remain
runtime checks. Direct swipe requests return `ERR_INVALID_DISTANCE` for nonfinite or out-of-range
distances.
