# Activity starts must report Android rejection

## Baselines and recoverable work

- Repository: [alehkot/android-emu-agent](https://github.com/alehkot/android-emu-agent).
- Persistent working branch: `development`.
- Actual starting development head:
  [ae3335db89b69502f9d70447000d29833cf5ff7c](https://github.com/alehkot/android-emu-agent/commit/ae3335db89b69502f9d70447000d29833cf5ff7c).
- Observed upstream `main`:
  [a0dc463c57f8c9812fe1cf1d5196378ee2c31a80](https://github.com/alehkot/android-emu-agent/commit/a0dc463c57f8c9812fe1cf1d5196378ee2c31a80).
  All 14 PRs were merged, with no open source issues or PRs. Existing development provenance and the
  released prior claim were checked. Accumulated work after combined PR #14 is preserved; no
  upstream integration was required. The prior reset checkpoint explicitly deferred this bug.
- Published implementation and complete recoverable patch:
  [c695a0e1eaf5324534f4b0b5a71a81f9b256b7fe](https://github.com/alehkot/android-emu-agent/commit/c695a0e1eaf5324534f4b0b5a71a81f9b256b7fe),
  tree `ab5f14b908128eacfecb3010db879edf1964617f`, sole parent the starting development head.
- Original tested local implementation: `2becb088ea3985acd75ae7ba096c40a4a3d690f7`, same tree.
  Genuine local history, bundle and patch are retained. The published commit was imported only after
  exact SHA verification. Fresh development/main checks preceded the non-force expected-head update;
  no reset, branch deletion, or synthetic history was used.
- This subsequent documentation-only checkpoint's final SHA and exact-head CI observation are
  recorded in the existing
  [verification recovery issue](https://github.com/alehkot/issues-tracker/issues/12).

## Problem, rationale and bounded repair

Launching a nonexistent or disabled activity, or opening a deeplink without a matching handler,
previously returned success: both launch paths discarded `am start` output. Older Android versions
print failure diagnostics but return shell status zero, so checking only exit status would still
miss the ordinary failure. CLI clients could continue and tasks could run later steps against the
wrong screen. This was selected as the concrete deferred launch counterpart to the earlier reset
fix, rather than making speculative changes to unrelated shell commands.

A shared activity-start helper now uses `adbutils.shell2` and checks both nonzero status and
anchored `Error:` / numbered `Error type` diagnostic lines. It raises actionable
`ERR_LAUNCH_FAILED`, which all three API routes preserve. Human and JSON CLI modes exit nonzero, and
tasks stop after the failed step. Existing successful warnings, activity resolution/class semantics,
quoting, debugger flags, transport-error handling, input validation and threading are preserved.
There is no retry. No dependencies, platform permissions, CI configuration or release behavior
changed. CLI help, generated reference and bundled command guidance describe the failure contract.

Reproduction: supply Android's missing-activity or unresolved-intent diagnostic with exit zero at
the mocked ADB boundary, then call the real manager, API, CLI or task dispatcher. The starting
implementation returns success; the repaired implementation returns a launch failure.

Research:

- [Older AOSP ActivityManager command](https://android.googlesource.com/platform/frameworks/base/+/a42e14ce6379/services/core/java/com/android/server/am/ActivityManagerShellCommand.java)
  prints start-rejection diagnostics before its unconditional zero return.
- [Current AOSP ActivityManager command](https://android.googlesource.com/platform/frameworks/base/+/master/services/core/java/com/android/server/am/ActivityManagerShellCommand.java)
  also exposes start failures through nonzero status.
- [adbutils shell2](https://github.com/openatx/adbutils#run-shell-command) returns status and
  output; the installed locked implementation was checked. Its default shell-v1 output retains
  diagnostics.

## Verification and review

- **47 new regression/control cases pass**. Against isolated exact starting production files: **36
  failed, 11 passed**. Of those, 26 directly demonstrate false success (18 manager, six CLI, two
  task cases); the remainder exercise the checked-shell/status/transport contract.
- Independent focused suite: **153 passed**. Coverage includes zero/nonzero rejection, empty output,
  benign already-running warnings, error-like text within echoed intents, real adbutils status
  parsing, quoting, debugger flags, transport errors and task stop behavior.
- Full supported Python 3.12 suite: **1,783 passed**, with only the two known socket cases excluded.
- Unmodified canonical `./scripts/dev.sh check`: formatting/lint, strict mypy, Pyright, skill
  validation, bridge build and **61 Kotlin tests in 13 suites** pass. Python fails only the two
  existing AF_UNIX restrictions listed below. The canonical gate is **not fully green**.
- Strict MkDocs, Markdown lint, generated CLI reference and whitespace checks pass separately.
- Full self-review and independent review found no introduced moderate-or-higher finding. Published
  verification includes exact parent/tree and full blob/mode comparison; post-publication checks and
  review are recorded in the recovery issue. A clean review is not a bug-free guarantee.

The unchanged failures are `test_daemon_controller_restricts_existing_socket` and
`TestSecureOwnSocket::test_tightens_socket_permissions`, both failing AF_UNIX socket creation with
`PermissionError: [Errno 1] Operation not permitted`. Restrictions and checks were not weakened.
Live Android and daemon-socket verification remain **unrun**. These tests demonstrate error
propagation with a mocked transport, not real-device compatibility or application readiness.

## CI and next steps

The exact implementation head has zero Actions runs, check-runs and statuses. Normal CI is
**unrun**, not passed or actively pending: workflows run on main pushes and PRs, not development. No
manual workflow dispatch/rerun or PR creation was used.

No implementation is unfinished and no introduced moderate-or-higher finding remains. Resume from
freshly checked remote development and preserve accumulated work. Complete the unmodified gate on a
permitted own-machine setup supporting Unix sockets; exercise missing/disabled activity, unhandled
deeplink and already-running activity behavior on an Android test device before the owner's combined
merge. The existing issue tracks verification gaps; older resolved findings are historical, not work
to reapply.
