# Allow snapshot commands to return their console result

## Baselines and recoverable work

- Repository: [alehkot/android-emu-agent](https://github.com/alehkot/android-emu-agent).
- Persistent remote branch: `development`.
- Actual starting development head:
  [e462b3a7338aceb5fdff5209a295bf30cfbb5909](https://github.com/alehkot/android-emu-agent/commit/e462b3a7338aceb5fdff5209a295bf30cfbb5909).
- Observed upstream `main`:
  [a0dc463c57f8c9812fe1cf1d5196378ee2c31a80](https://github.com/alehkot/android-emu-agent/commit/a0dc463c57f8c9812fe1cf1d5196378ee2c31a80).
  All 14 PRs were merged; there were no open source issues or PRs. Branch provenance, other refs,
  the released previous claim, combined merge #14, instructions and existing checkpoints were checked.
  Accumulated development changes are preserved; no upstream integration was needed.
- Published implementation and complete recoverable patch:
  [e0e1c35ce7b4cf55822a02f80225d0fad746829e](https://github.com/alehkot/android-emu-agent/commit/e0e1c35ce7b4cf55822a02f80225d0fad746829e),
  tree `5a516755de4b956c252e06f7afa43fad9c0ed7c3`, sole parent the starting development head.
- Original tested local commit: `c052df477c02dcbf0dba2a4b68122e129fd0955e`, with the same tree.
  Genuine history and a bundle/patch are retained. The published commit was imported only after its
  exact SHA was verified; the original local commit remains recoverable. Fresh development/main
  checks preceded the non-force expected-head update. No reset or force-push was used.
- This documentation-only checkpoint's final SHA, exact-head CI and publication verification are
  recorded in the existing [verification issue](https://github.com/alehkot/issues-tracker/issues/12).

## Problem, impact and bounded repair

`emulator snapshot save` and `emulator snapshot restore --no-restart` used the ordinary ten-second
HTTP read timeout. The daemon allows thirty seconds for the console command, after up to five
seconds each for the banner and authentication replies. A slower but permitted snapshot operation
could therefore complete after the CLI had already failed with `ReadTimeout`, losing either the
success result or the console's actionable rejection. Retrying blindly could repeat a state change.

Both commands now use a bounded sixty-second HTTP budget. Restart-backed restore retains its
existing 180-second budget. The console deadlines, request payloads, device behavior and mutation
replay protection are unchanged. CLI help, generated reference and bundled guidance are synchronized.
No dependency, workflow, security setting or release behavior changed.

This concrete client/daemon mismatch was selected over speculative broader timeout changes. The
[official Android snapshot guidance](https://developer.android.com/studio/run/emulator-snapshots)
explains that memory pressure and disk swapping can substantially slow snapshot save/load. The
repository's existing thirty-second command allowance provides the relevant bounded contract;
this change does not claim a measured real-device performance improvement.

Reproduction: invoke the actual CLI and DaemonClient with a test HTTP transport that models a
response at fifteen seconds. Inspect HTTPX's request timeout extension and raise `ReadTimeout` if
the read budget is shorter. On the starting head, save/live restore lose the response; restart
restore succeeds. On the final code all three receive the intended response. MockTransport itself
does not enforce elapsed-time deadlines; the regression explicitly models that boundary.

## Tests and review

- **12 regression/control cases pass**; unchanged starting production code: **8 fail, 4 pass**.
  They cover save/live restore/restart restore, human/JSON output, success/console rejection,
  unchanged payloads, bounded HTTPX timeout wiring and one request without daemon restart.
- Focused emulator/manager/client checks: **100 passed**. Independent focused review checks:
  **201 passed**, including existing transport replay, wait timeout and HTTP failure tests.
- Full supported Python 3.12 suite: **1,795 passed**, excluding only the two known AF_UNIX cases.
- Unmodified canonical `./scripts/dev.sh check`: formatting/Ruff, mypy, Pyright, skill validation,
  bridge build and **61 Kotlin tests in 13 suites pass**. It fails only the same two socket tests
  that failed on the untouched starting baseline. The canonical gate is **not fully green**.
- Strict MkDocs, Markdown lint, generated CLI reference and whitespace checks pass separately.
- Full self and independent prepublication reviews found no introduced moderate-or-higher finding.
  All **258 published blobs/modes**, parent and tree match the tested code. Postpublication review
  and tests are recorded with the final checkpoint in the verification issue. A clean review does
  not guarantee bug-free code.

The two unchanged failures are `test_daemon_controller_restricts_existing_socket` and
`TestSecureOwnSocket::test_tightens_socket_permissions`, both AF_UNIX socket creation with
`PermissionError: [Errno 1] Operation not permitted`. Checks and restrictions were not weakened.
Live emulator timing, Android device and daemon-socket integration remain **unrun**. Deterministic
transport tests establish HTTP budget propagation and response handling, not real-device readiness.

## CI and next steps

The exact implementation head has zero Actions runs, check-runs and statuses. CI is **unrun**, not
passed or actively pending: normal workflows trigger on main pushes and PRs, not development.
No workflow dispatch/rerun, check enabling or PR creation was used.

No implementation is unfinished and no introduced moderate-or-higher finding remains. Resume from
freshly checked remote development, retaining accumulated work. Before the owner's combined merge,
run the unmodified canonical gate on a permitted own-machine setup supporting Unix sockets and
exercise snapshot save/live restore on an Android emulator. An HTTP timeout is not cancellation:
inspect the emulator state before deliberately repeating a snapshot mutation. The existing issue
tracks these verification gaps; older resolved findings are historical, not work to reapply.
