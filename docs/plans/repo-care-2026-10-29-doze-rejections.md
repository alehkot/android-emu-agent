# Report rejected doze test preconditions

## Baseline and recoverable work

- Repository: [alehkot/android-emu-agent](https://github.com/alehkot/android-emu-agent).
- Persistent working branch: `development`.
- Actual starting development head:
  [96099156b8f40d6afbbda3ee95b551c9d2a50d2e](https://github.com/alehkot/android-emu-agent/commit/96099156b8f40d6afbbda3ee95b551c9d2a50d2e).
- Observed upstream `main`:
  [a0dc463c57f8c9812fe1cf1d5196378ee2c31a80](https://github.com/alehkot/android-emu-agent/commit/a0dc463c57f8c9812fe1cf1d5196378ee2c31a80).
  Its tree equals the development head merged in PR #14. No later upstream change or open PR was
  present; accumulated development work was preserved without reset, replay, or integration.
- Final implementation and full recoverable patch:
  [0b08e5372e53740653e25f3db26b6eeafc16df3f](https://github.com/alehkot/android-emu-agent/commit/0b08e5372e53740653e25f3db26b6eeafc16df3f).
- Exact implementation tree: `3fae80cebc0685420cd16e75d5bc3c90c51b6bd2`; sole parent is the starting
  development head. All 260 remote file paths, modes, and blobs match tested local contents.
- Original local implementation: `45e81cc2506f31513316d11a1071827dd5e69fbd`, identical tree.
  Genuine local history and a complete recovery bundle are retained. The published object was
  imported only after verifying its exact SHA; this document is a subsequent checkpoint commit.

## Problem, impact, rationale, and scope

`device set doze on` discarded the result of `dumpsys deviceidle force-idle`. When Android reported
that deep idle was disabled or the transition stalled, the API still returned `status: done` and
`doze: on`, and both CLI modes exited successfully. Automation could incorrectly treat subsequent
app behavior as tested under a doze precondition that Android had explicitly rejected.

The manager now recognizes the documented anchored idle-transition rejection diagnostic and raises
`ERR_DOZE_CHANGE_FAILED` with the original output, command, and serial. The doze endpoint preserves
this actionable error instead of replacing it with an offline-device error. Human and JSON CLI
modes exit 1. Existing commands, success responses, transport handling, and device policies are
unchanged. The command neither enables a disabled idle mode nor retries the mutation.

This is deliberately not a general device-state verifier or a rewrite of all system setters.
Permission/service diagnostics and other unrecognized outputs retain existing behavior. No live
Android state was changed. The skill command reference explains the narrower failure contract.

This bounded false-success defect was selected over speculative foreground-window fallback changes
and a broader shell-status sweep: AOSP documents the failure and existing CLI/API/manager behavior
reproduces the incorrect success without relying on a guessed device transition.

Research:

- [Android 16 DeviceIdleController](https://github.com/aosp-mirror/platform_frameworks_base/blob/android16-release/apex/jobscheduler/service/java/com/android/server/DeviceIdleController.java)
  documents disabled/stalled deep-idle rejection and the dumpsys wrapper's discarded command result.
- [Android 6 DeviceIdleController](https://github.com/aosp-mirror/platform_frameworks_base/blob/android-6.0.1_r1/services/core/java/com/android/server/DeviceIdleController.java)
  establishes the older diagnostic without a deep/light qualifier.

## Verification and review

- Ten new tests exercise real CLI payload construction, FastAPI routing, and DeviceManager with
  mocked ADB/HTTP transport. They cover disabled/stalled/legacy rejection, on/off success, both output
  modes, unchanged commands, preserved diagnostics, and no replay. All pass; the exact unchanged
  baseline produces six regression failures and four passing success controls.
- 90 focused tests pass. Full supported Python 3.12 suite: **1,805 passed, two deselected**; repeated
  against the exact published implementation. The exclusions are only the existing AF_UNIX cases.
- Canonical `./scripts/dev.sh check` passes Ruff format/lint, strict mypy, Pyright, bundled skills,
  Kotlin bridge build, and **61 Kotlin tests across 13 suites**. It then fails only the two existing
  socket tests below. The canonical gate is **not fully green**; no check or restriction was changed.
- Strict MkDocs, Markdown lint, and whitespace checks pass separately. An introduced Markdown line
  length issue was corrected and lint rerun successfully. No CLI signature/help surface changed.
- Author self-review and independent full-diff review against the starting development and upstream
  context found no introduced moderate-or-higher findings. Thirteen additional independent probes
  passed for benign/empty output, anchored multiline diagnostics, and transport errors without retry.
  Published-code full review and 90 focused tests confirmed the same outcome.
  A clean review is not a guarantee of bug-free code.

## Remaining verification limitations and next steps

The unchanged tests `test_daemon_controller_restricts_existing_socket` and
`TestSecureOwnSocket::test_tightens_socket_permissions` fail while creating AF_UNIX sockets with
`PermissionError: [Errno 1] Operation not permitted`. Live Android/emulator and daemon-socket
integration are **unrun**. Mocked tests establish propagation of Android-style rejection, not actual
hardware behavior or that a successful response proves the app remained idle afterward.

Normal CI for the exact implementation is **unrun**, not passed or actively pending: zero Actions
runs, check-runs, and statuses. The workflow triggers on main pushes and PRs, not development. No
manual dispatch/rerun, paused-check change, or PR creation was used.

No implementation is unfinished and no introduced moderate-or-higher finding remains. Resume from
freshly checked remote development, preserving accumulated work. Complete the canonical gate on a
permitted own-machine setup supporting Unix sockets, and exercise successful/rejected doze requests
on Android before the owner's combined merge. Do not change device policy merely to make a rejected
precondition pass. The existing recovery issue tracks verification gaps:
[issues-tracker #12](https://github.com/alehkot/issues-tracker/issues/12).
