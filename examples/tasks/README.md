# Task Script Examples

These `.aea` files are small, human-editable task scripts for the task harness. They validate
without a device and run against any active session when you pass `--session`. The formal syntax is
documented in the [`.aea` task script specification](../../docs/aea-spec.md).

```bash
uv run android-emu-agent task validate examples/tasks/idle-snapshot.aea
uv run android-emu-agent task run examples/tasks/idle-snapshot.aea --session s-abc123 --json
```

Use these as starting points:

- `idle-snapshot.aea`: waits for the current screen to settle and captures a compact snapshot.
- `checkout-smoke.aea`: taps a checkout entry point and verifies the payment screen.
- `login-flow.aea`: launches an app, fills a login form, and verifies the home activity.

Before running an app-specific example, replace placeholder package names, activity names, resource
IDs, and sample credentials with values from your target app.
