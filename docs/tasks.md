# Task Scripts

`.aea` task scripts are line-oriented task files for repeated app flows. They compile to the same
task harness as JSON specs, so `task validate` can check them before any device action runs.

For the formal accepted syntax, see the [`.aea` task script specification](aea-spec.md).

Use them when a flow is easier to review and edit as steps:

```text
name "checkout smoke"
tap text:"Checkout" || id:com.example:id/checkout
verify exists text:"Payment" timeout_ms=5000
expect activity CheckoutActivity
```

Validate a script first, then run it against an active session:

```bash
uv run android-emu-agent task validate examples/tasks/checkout-smoke.aea
uv run android-emu-agent task run examples/tasks/checkout-smoke.aea --session s-abc123 --json
```

The repository includes ready-to-edit examples under `examples/tasks/`:

- `idle-snapshot.aea`: waits for the current screen to settle and captures a compact snapshot.
- `checkout-smoke.aea`: taps a checkout entry point and verifies the payment screen.
- `login-flow.aea`: launches an app, fills a login form, and verifies the home activity.

## Script Syntax

This section is a quick reference. The complete parser contract lives in the
[`.aea` task script specification](aea-spec.md).

Metadata lines set task-level fields:

```text
name "login flow smoke"
description "Launch an app, fill a login form, and verify the home activity."
session s-abc123
```

`session` is optional. If a script omits it, pass `--session` to `task run`.

Action and app lines map to daemon operations:

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

Wait lines pause until the expected state is reached:

```text
wait idle timeout_ms=5000
wait activity HomeActivity timeout_ms=15000
wait exists text:"Payment" timeout_ms=5000
wait gone text:"Loading" timeout_ms=10000
```

`verify` attaches a post-step check to the previous step. `expect` adds a final task-level verifier:

```text
tap text:"Continue" || id:com.example:id/continue
verify exists text:"Welcome" timeout_ms=5000
expect activity HomeActivity
```

Snapshot lines are useful when the task should leave structured UI evidence:

```text
snapshot mode=compact
snapshot mode=full
snapshot mode=raw
```

Use `#` for comments. Comments inside quoted text are preserved.
