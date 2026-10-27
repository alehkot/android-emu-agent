# Rejected app resets return failure

## Baseline and completed work

- Repository: [alehkot/android-emu-agent](https://github.com/alehkot/android-emu-agent).
- Persistent branch: `development`.
- Actual starting development head:
  [a698cf2bf66ca7f855a3a649acf174451a32231c](https://github.com/alehkot/android-emu-agent/commit/a698cf2bf66ca7f855a3a649acf174451a32231c).
- Observed upstream `main`:
  [a0dc463c57f8c9812fe1cf1d5196378ee2c31a80](https://github.com/alehkot/android-emu-agent/commit/a0dc463c57f8c9812fe1cf1d5196378ee2c31a80).
  Existing development work and the owner's merged combined PR are preserved. No upstream
  integration was needed; both heads were rechecked immediately before the non-force push.
- Final implementation and full recoverable patch:
  [60d20dd021b8be07df9eec98ce1bc2dff30a4514](https://github.com/alehkot/android-emu-agent/commit/60d20dd021b8be07df9eec98ce1bc2dff30a4514).
- Exact tested/published tree: `7f927e4e03efb93eeb0daddd84926f341b78e784`, with the starting
  development head as the implementation commit's sole parent. This is a subsequent
  documentation-only checkpoint.

## Problem, impact, and scope

`app reset` previously discarded the result of Android's `pm clear`. Android can reject a reset (for
example, for a missing package or a user restriction) while ADB still returns ordinary output. The
endpoint then reported `done` and both human and JSON CLI modes exited zero. Test automation could
continue with app data it incorrectly believed had been cleared.

The manager now uses the existing adbutils `shell2` API through the same per-device I/O worker and
checks the command's exit status. Nonzero status becomes the existing `ERR_ADB_COMMAND` with the
original diagnostic output (or an exit-status fallback). The endpoint preserves that error instead
of relabeling it as a disconnected device. Successful output, package quoting, request schemas,
transport errors, cancellation, and timeouts are unchanged. No reset is retried automatically. The
CLI help, generated reference, workflow guide, and skill command reference explain the result.

Selected over a separate debugger mapping-file path issue because false success affects ordinary
app-reset setup and can invalidate subsequent tests. The mapping command still forwards relative
paths to the daemon/JVM rather than binding them to the CLI directory; it is a separate, unmodified
follow-up candidate. Launch/intent result handling is also outside this bounded fix.

Research:

- [AOSP PackageManagerShellCommand](https://android.googlesource.com/platform/frameworks/base/+/main/services/core/java/com/android/server/pm/PackageManagerShellCommand.java):
  `runClear` reports success with exit 0 and failure with exit 1.
- [Locked adbutils 2.12.0 implementation](https://github.com/openatx/adbutils/blob/2.12.0/adbutils/_device_base.py):
  `shell2` preserves status using its shell-v1 exit marker without requiring a new local ADB
  process.

## Verification and review

- 19 new regression/control cases pass. The initial 11-case suite produced six failures and five
  passing controls on the unchanged starting implementation, reproducing false success.
- Tests cover Android rejection, permission diagnostics, empty diagnostic output, nonzero status
  with misleading success text, zero status with warning text, successful response preservation,
  missing devices, transport failures, and preserved offline endpoint errors.
- Human and JSON CLI tests traverse actual CLI, FastAPI endpoint, and DeviceManager code with only
  in-process HTTP/session test plumbing and mocked device transport. Three cases use the real pinned
  adbutils shell2 parser and mocked raw transport bytes. No device data is cleared by these tests.
- Full supported Python 3.12 unit suite: **1,717 passed, two deselected**. The unmodified canonical
  `./scripts/dev.sh check` passes formatting, lint, strict mypy, Pyright, skills, and bridge stages,
  then fails only the two existing AF_UNIX socket-creation restrictions. It is **not fully green**.
- Kotlin bridge: `shadowJar` succeeds; **61 tests across 13 suites** pass with no failures, errors,
  or skips. Strict MkDocs, Markdown lint, generated CLI documentation, and whitespace checks pass.
- Full self-review and independent full-diff review found no introduced moderate-or-higher finding.
  The independent final focused suite passed **92 tests**. All 250 published file blobs match the
  reviewed local content, and the published commit parent/tree were checked.
- Independent post-publication full review again found no moderate-or-higher findings; all 250 blobs
  and modes and the full diff were checked, and 92 focused tests passed again. The complete
  supported suite on the published tree again passed 1,717 tests with two known exclusions.

The two unchanged environment-limited tests are `test_daemon_controller_restricts_existing_socket`
and `TestSecureOwnSocket::test_tightens_socket_permissions`; each fails with socket-creation
`PermissionError: [Errno 1] Operation not permitted`. No permissions or checks were weakened. Real
daemon-socket and Android device/emulator integration remain unrun. These tests establish status
propagation and compatibility, not physical-device behavior. A clean review is not a promise of
bug-free code.

## CI and next steps

CI is not manually dispatched or rerun, and no PR is created just to trigger checks. The current
workflow runs on main pushes and PRs, not development. The exact implementation head has zero
Actions runs, check-runs, and statuses: CI is unrun, not passed or actively pending. Final
checkpoint commit observations are retained in the linked recovery issue.

No implementation remains unfinished. Resume from freshly checked remote development, preserving all
commits. Complete the unmodified canonical check in a permitted own-machine environment with
Unix-socket support, and exercise reset success/rejection against a suitable test device when
available. Existing verification recovery:
[issues-tracker #12](https://github.com/alehkot/issues-tracker/issues/12).
