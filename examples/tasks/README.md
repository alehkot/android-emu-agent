# Task Script Examples

This directory contains small `.aea` task scripts you can validate without a device and run against
any active session with `--session`.

Use these files as starting points:

| File                 | Purpose                                                               |
| -------------------- | --------------------------------------------------------------------- |
| `idle-snapshot.aea`  | Wait for the current screen to settle and capture a compact snapshot. |
| `checkout-smoke.aea` | Tap a checkout entry point and verify the payment screen.             |
| `login-flow.aea`     | Launch an app, fill a login form, and verify the home activity.       |

Validate before running:

```bash
uv run android-emu-agent task validate examples/tasks/idle-snapshot.aea
```

Run against an active session:

```bash
uv run android-emu-agent task run examples/tasks/idle-snapshot.aea --session <session-id> --json
```

Before running app-specific examples, replace placeholder package names, activity names, selectors,
resource IDs, and sample credentials with values from your target app.

For the full task-writing workflow, see [the task script guide](../../docs/tasks.md). For exact
syntax, see [the `.aea` task script specification](../../docs/aea-spec.md).
