# Debugging Workflows

> **Read this file when** you need to investigate runtime behavior, crashes, or incorrect app state
> using the debugger.

Use debugging commands when UI-level signals are not enough to explain behavior. The debugger is
most useful for state validation, breakpoint-driven tracing, and crash root-cause analysis.

## Decision Tree

```text
What are you investigating?
  │
  ├─ App crashed or process died
  │    1. reliability exit-info <package> --session <id>|--device <serial>
  │    2. If exit-info/logs are not enough: app launch ... --wait-debugger
  │    3. debug attach --session <id> --package <package>
  │    4. debug break-exception set --session <id> --class '*' --no-caught --uncaught
  │    5. debug resume, then debug events for exception_hit
  │
  ├─ Incorrect state / wrong behavior with app still running
  │    1. debug attach --session <id> --package <package>
  │    2. debug break set <class> <line> --session <id> [--condition <expr>]
  │    3. debug resume, debug events, debug inspect
  │
  └─ Need to trace execution flow
       1. debug stack --session <id>
       2. debug step-over / debug step-into / debug step-out
       3. debug inspect / debug eval on each stop
```

## OAV Integration

Debugger commands follow the same observe-act-verify rhythm as UI automation:

- `debug step-over`: Act + Observe (returns new state atomically).
- `debug inspect`: Observe (bounded inspection).
- `debug break set`: Act + Verify (confirmation or pending state).

This allows safe interleaving of UI and debugger operations in one session.

## Deferred Breakpoints

`debug break set` may return `status=pending` when the class is not loaded yet. This is expected.
The bridge subscribes to class-prepare events and resolves the breakpoint automatically when the
class loads. Use `debug events` to watch for `breakpoint_resolved` and `breakpoint_hit`. Exception
breakpoints can also resolve lazily (`exception_breakpoint_resolved`).

When launching with `app launch ... --wait-debugger`, attach with `--keep-suspended` if you need to
set initial breakpoints before any code runs:

- `debug attach --session <id> --package <package> --keep-suspended`
- `debug break set ...`
- `debug resume --session <id>`

## Conditional Breakpoints and Logpoints

Use `--condition` to suspend only when an expression is truthy:

- Example:
  `debug break set com.example.CheckoutViewModel 118 --session <id> --condition "cart.total > 10000"`
- Truthy values stop execution; falsy values auto-resume.
- If condition evaluation fails, no stop occurs; `debug events` reports
  `breakpoint_condition_error`.

Use `--log-message` for a non-suspending logpoint:

- Example:
  `debug break set com.example.CheckoutViewModel 118 --session <id> --log-message "hit={hitCount} total={cart.total}"`
- Supports `{hitCount}` and expression placeholders such as `{user.id}`.
- The app auto-resumes and `debug events` reports `logpoint_hit`.
- Use `--capture-stack [--stack-max-frames <n>]` if each hit should include stack frames.
- Query buffered logpoint history later with:
  `debug break hits --session <id> [--breakpoint-id <id>] [--limit <n>]`.

`--condition` and `--log-message` can be combined on the same breakpoint.

## Exception Breakpoints

Use exception breakpoints when failures happen before or between normal breakpoints:

- Catch all uncaught exceptions:
  `debug break-exception set --session <id> --class '*' --no-caught --uncaught`
- Catch a specific type:
  `debug break-exception set --session <id> --class java.lang.NullPointerException --caught --uncaught`
- List/remove: `debug break-exception list --session <id>`,
  `debug break-exception remove <breakpoint_id> --session <id>`

On hit, `debug events` returns `exception_hit` with throw/catch locations and stopped-frame data.

## Event Types to Watch

`debug events` can return mixed event types in one queue drain. Common ones:

- `breakpoint_resolved`, `breakpoint_hit`
- `breakpoint_condition_error`
- `logpoint_hit`
- `exception_breakpoint_resolved`, `exception_hit`
- `vm_disconnected`

## Token Budget Controls

Debugger output is intentionally bounded:

- `debug stack` defaults to 10 frames. Use `--max-frames` to inspect deeper stacks.
- `debug inspect` defaults to depth 1. Use `--depth` (1..3) to expand nested objects.
- `debug threads` defaults to a bounded list. Use `--all` for broader output.

Start narrow, then increase bounds only when needed.

## Coroutine Tip

If the stack trace is full of `kotlinx.coroutines`, use `debug step-out` until you see user code.
Synthetic coroutine frames are auto-filtered but navigation still requires stepping out.

## ANR Safety

Do not leave the main thread suspended for more than 8 seconds. Long suspensions can trigger ANR or
watchdog behavior. If you pause on `main`, inspect quickly and run `debug resume`.

## JDK Requirement

Debugger requires JDK 17+. If you see `ERR_JDK_NOT_FOUND`, guide the user to install it and ensure
`java` is available via `PATH` or `JAVA_HOME`.

## End-to-End Flow

```bash
uv run android-emu-agent app launch <session_id> com.example --wait-debugger
uv run android-emu-agent debug attach --session <session_id> --package com.example
uv run android-emu-agent debug break set com.example.LoginActivity 42 --session <session_id> --condition "attempts > 3"
uv run android-emu-agent debug break set com.example.LoginActivity 45 --session <session_id> --log-message "attempt={hitCount} user={username}" --capture-stack --stack-max-frames 8
uv run android-emu-agent debug break-exception set --session <session_id> --class '*' --no-caught --uncaught
uv run android-emu-agent debug resume --session <session_id>
uv run android-emu-agent debug events --session <session_id>
uv run android-emu-agent debug break hits --session <session_id> --limit 100
uv run android-emu-agent debug inspect savedInstanceState --session <session_id>
uv run android-emu-agent debug step-over --session <session_id>
uv run android-emu-agent ui snapshot <session_id>
uv run android-emu-agent debug resume --session <session_id>
```
