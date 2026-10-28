# Permission changes must preserve Android rejection status

## Baselines and recoverable work

- Repository: [alehkot/android-emu-agent](https://github.com/alehkot/android-emu-agent).
- Persistent working branch: `development`.
- Actual starting development head:
  [81be0a7d37353c6eebba65c271fdb11996805d04](https://github.com/alehkot/android-emu-agent/commit/81be0a7d37353c6eebba65c271fdb11996805d04).
- Observed upstream `main`:
  [a0dc463c57f8c9812fe1cf1d5196378ee2c31a80](https://github.com/alehkot/android-emu-agent/commit/a0dc463c57f8c9812fe1cf1d5196378ee2c31a80).
  All 14 PRs are merged; no open PR or standalone source issue was present. The owner's combined PR
  #14 has the same tree as earlier development `5cd382c25d5328163bf26642adaaf1e4d3c96816`. Later
  accumulated work is preserved without replay, reset, or unnecessary upstream integration. The
  previous claim was released and no unfinished implementation remained.
- Published implementation/full recoverable patch:
  [8edf29e3a2e0a5303aaa87aad216a0d7d7bcda4e](https://github.com/alehkot/android-emu-agent/commit/8edf29e3a2e0a5303aaa87aad216a0d7d7bcda4e),
  tree `0537b1106ca72b2627c0732b06a74092a6af9965`, sole parent the starting head.
- Original tested local implementation: `edaa406863d68919eb481f6f16724d01335001d8`, same tree.
  Original history and a recoverable bundle/patch are retained. Publication used real-parent Git
  objects and a non-force expected-head update after fresh development/main checks. The genuine
  published commit was imported only after exact SHA verification; no synthetic history.
- This subsequent documentation-only checkpoint's final SHA and exact-head CI observation are
  recorded in the existing
  [verification recovery issue](https://github.com/alehkot/issues-tracker/issues/12).

## Problem, evidence, and bounded repair

`system permissions grant/revoke` used `adbutils.AdbDevice.shell`, which returns command output
without the remote exit status. Android may reject a normal setup request, for example granting
CAMERA when the installed app did not declare it. The manager nevertheless returned `status: done`
and `granted: true/false`; both human and JSON CLI modes exited zero. Automation could continue with
a permission state that was never established.

Reproduction uses the real CLI, FastAPI endpoint, and SystemManager with only ADB/session/HTTP
plumbing mocked. Return Android-style rejection text and a nonzero status at the device boundary.
The unchanged baseline reports success. No real device permission or policy was changed.

Only grant/revoke now use `shell2`, inspecting its integer return code. A nonzero result becomes
`ERR_PERMISSION_CHANGE_FAILED`, carrying the operation, package, permission, exit code and output.
The existing endpoint emits an error response and the CLI exits 1, including with `--json`. Empty
rejection output still produces a useful exit-status message. Success output, shell quoting, input
validation, transport-exception behavior, and threading remain unchanged. No automatic retry occurs.
Notification/quick-settings commands and permission listing retain their existing implementation.
CLI help, generated reference, command guidance, and troubleshooting are synchronized.

This was selected over device-list error rendering: artificial JSON errors show a weakness there,
but ordinary discovery exceptions return plaintext failures and already fail parsing. That evidence
was insufficient to prioritize a separate fix. No speculative broad system-command rewrite is
included.

Research:

- [adbutils shell2](https://github.com/openatx/adbutils#run-shell-command) exposes remote status and
  output; the installed locked implementation was inspected as well.
- [AOSP permission commands](https://android.googlesource.com/platform/frameworks/base/+/android11-release/services/core/java/com/android/server/pm/PackageManagerShellCommand.java)
  invoke the runtime grant/revoke APIs.
- [AOSP shell exception handling](https://android.googlesource.com/platform/frameworks/base/+/android10-release/core/java/android/os/ShellCommand.java)
  reports security exceptions without changing the failure result to success.

## Verification and review

- **12 regression/control cases pass**: grant/revoke, human/JSON, empty success, textual rejection,
  and empty rejection. Against unchanged baseline: **8 failed, 4 passed**. Actual CLI/API/manager
  layers and the installed `ShellReturn` type are exercised with a mocked device boundary.
- Full supported Python 3.12 suite: **1,736 passed**, two known AF_UNIX cases deselected. Repeated
  after publication against the verified exact published tree with the same result.
- Unmodified canonical `./scripts/dev.sh check`: Ruff formatting/lint, strict mypy, Pyright, skill
  validation, Kotlin bridge build and **61 tests in 13 suites** pass. Python fails only the two
  existing socket-creation restrictions below. The canonical gate is **not fully green**.
- Strict MkDocs, Markdown lint, regenerated reference, and whitespace checks pass separately.
- Full self-review and independent review found no introduced moderate-or-higher issue. Independent
  verification: **68 focused tests and 16 extra probes** pass, covering both operations, empty and
  warning success output, several nonzero statuses, transport failures/no retry, and invalid-input
  preflight. No Kotlin behavior changed. A clean review is not a bug-free guarantee.
- Published commit, parent, tree, and all **254 blobs/modes** match tested local content.

The unchanged failures are `test_daemon_controller_restricts_existing_socket` and
`TestSecureOwnSocket::test_tightens_socket_permissions`, both
`PermissionError: [Errno 1] Operation not permitted` while creating AF_UNIX sockets. Restrictions
and checks were not weakened. Live Android and daemon-socket verification remain **unrun**: these
tests demonstrate status propagation, not real-device permission compatibility.

## CI and next steps

The exact implementation head has zero Actions runs, check-runs and statuses. CI is **unrun**, not
passed or actively pending: normal workflows run on main/PRs, not development. No Actions
rerun/dispatch, PR creation, paused-check changes, deployment, or security-setting changes occurred.

No implementation is unfinished and no introduced moderate-or-higher finding remains. Resume from
freshly checked remote development and preserve accumulated work. Complete the unchanged canonical
gate on a permitted own-machine setup supporting Unix sockets, and verify grant/revoke success and
rejection on a suitable test device before the owner's combined merge. The existing recovery issue
tracks the verification gap; older resolved selector/timeout/Gradle entries are historical.
