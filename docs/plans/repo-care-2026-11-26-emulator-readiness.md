# Keep emulator boot readiness within its deadline

## What changed

An emulator can appear in ADB before Android is usable. The existing readiness
helper bounded the initial `wait-for-device`, but its later boot-property
command had the general ADB subprocess timeout (300 seconds), and the final
discovery refresh was not bounded by the readiness deadline. Users could wait
past the intended readiness budget or receive an HTTP read timeout instead of
the daemon's readiness error.

A single monotonic deadline now covers the ADB connection wait, boot property
polls and final device refresh. Each worker-thread ADB command receives the
remaining time plus the existing five-second subprocess cleanup grace. This
grace does not extend the coroutine's readiness deadline. A timeout includes
the last stage and any available boot state. The command syntax, console
sequence, startup process cleanup and caller cancellation behavior are
unchanged. This does not change the separate discovery, console or CLI HTTP
budgets or guarantee one end-to-end command deadline.

[Android's ADB documentation](https://developer.android.com/tools/adb#devicestatus)
distinguishes the connected `device` state from a completed Android boot.
[Python 3.11's asyncio timeout documentation](https://docs.python.org/3.11/library/asyncio-task.html#asyncio.timeout_at)
describes the event-loop clock and the distinction between the timeout scope
and caller cancellation.

## Evidence

- Exact starting
  [development](https://github.com/alehkot/android-emu-agent/commit/29484471e180592b6ffc15266eba33f357c53e58)
  and [main](https://github.com/alehkot/android-emu-agent/commit/a1c8bfdf645de9637e878b2fb33762eaf4b854ca)
  passed Woodpecker #46 and #11. The generic reports do not establish hardware
  coverage.
- 104 focused Python tests passed with locked dependencies on CPython 3.12.14.
  The new regression file models stalled ADB connect, boot property and refresh.
  On the exact unchanged baseline the initial wait error lacked stage context
  and the latter two reached the test guard instead of the readiness timeout.
  External cancellation and an independent refresh error remain distinct.
- Ruff lint/format, strict mypy and Pyright passed. Self-reviewed; no independent
  review, real emulator, real device, Kotlin bridge check or full local build.
