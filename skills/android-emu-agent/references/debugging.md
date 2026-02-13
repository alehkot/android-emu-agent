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
  │
  ├─ Incorrect state / wrong behavior with app still running
  │    1. debug attach --session <id> --package <package>
  │    2. debug break set <class> <line> --session <id>
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
class loads. Use `debug events` to watch for `breakpoint_resolved` and `breakpoint_hit`.

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
uv run android-emu-agent debug break set com.example.LoginActivity 42 --session <session_id>
uv run android-emu-agent debug resume --session <session_id>
uv run android-emu-agent debug events --session <session_id>
uv run android-emu-agent debug inspect savedInstanceState --session <session_id>
uv run android-emu-agent debug step-over --session <session_id>
uv run android-emu-agent ui snapshot <session_id>
uv run android-emu-agent debug resume --session <session_id>
```
