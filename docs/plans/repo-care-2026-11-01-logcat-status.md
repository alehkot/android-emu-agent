# Logcat artifact failure reporting

## Baseline and scope

- Repository: <https://github.com/alehkot/android-emu-agent>.
- Persistent working branch: `development`.
- Starting development and observed upstream `main`:
  [`fc5b83f4a7a6658d3ebbf0224337bec278057538`](https://github.com/alehkot/android-emu-agent/commit/fc5b83f4a7a6658d3ebbf0224337bec278057538).
- Implementation:
  [`a5c334e8a291cdf4dc8388fef6f290ff607206e0`](https://github.com/alehkot/android-emu-agent/commit/a5c334e8a291cdf4dc8388fef6f290ff607206e0).
  This checkpoint is a following documentation-only commit; final publication and CI evidence are
  recorded in the durable run checkpoint.

Both branches contained the previous trace-replay fix and the owner's subsequent CI changes.
There were no open PRs or issues and no active competing branch claim. Development's accumulated
work and the current upstream were preserved without resetting or reintroducing merged changes.

## Problem, rationale and change

`uiautomator2.Device.shell` returns command failures as `ShellResponse(output, exit_code)` rather
than raising automatically. Log capture ignored that status, saving diagnostics as successful
artifacts. Package filtering could even hide a failed fallback's diagnostic and return an empty
successful file. This real false-success defect was selected over broader atomic-bundle or selector
redesigns; it resumes the prior checkpoint's logcat-status investigation.

Check the final logcat status before filtering or writing. Preserve unsupported-PID retry and
missing-process PID lookup fallback, but do not retry successful logs merely containing option-error
text. Return `ERR_LOGCAT_FAILED` with diagnostics and remediation through log and bundle APIs and
nonzero CLI exits, including JSON mode. Preserve existing explicit output files when capture fails.
Legacy string-only shell responses retain their previous behavior. A screenshot already captured
before a bundle failure can remain; bundle transactionality was not redesigned.

Research: [uiautomator2 3.5.0 shell implementation](https://github.com/openatx/uiautomator2/blob/3.5.0/uiautomator2/__init__.py)
and [AOSP logcat failure handling](https://android.googlesource.com/platform/system/core/+/refs/heads/android11-platform-release/logcat/logcat.cpp).
The installed pinned adapter was also inspected and exercised with a mocked ADB transport.

## Verification and review

- Initial regression suite on unchanged baseline: seven failures, five passing controls.
- Fifteen new regression cases pass: thirteen manager cases and two real-manager API cases that
  additionally exercise both human and JSON CLI failure output.
- Final supported unit selection: 1,894 passed, two known Unix-socket permission cases excluded.
  The full-selection attempt reproduced only those two `EPERM` failures; it was not fully green.
- Ruff format/lint, strict mypy (72 source files), Pyright (zero errors), skills validation,
  Markdown lint (24 files), generated CLI-reference synchronization and whitespace checks pass.
- Full self-review and independent review found no introduced moderate-or-higher findings.
  Independent checks: 80 artifact tests and 30 production-shell-adapter probes passed.
- No local full build was run, per the current policy. Canonical build-containing `check`, Kotlin
  bridge build/tests, live Android/device/emulator checks and rendered UI verification were not run
  locally. This CLI/status change has no browser UI. Mocked transport tests do not establish device
  behavior, timing or log availability on every Android version.

## CI and next steps

Starting exact head had successful Woodpecker pipeline 6 status and PASS comment (pipeline 5 also
passed). Those generic reports do not enumerate job/platform coverage. Exact-head GitHub Actions
`check` also passed with its canonical-check step successful; this describes the baseline only.

At checkpoint creation the new commits were local-only, with no applicable remote build result.
Publish only after rechecking development and main; verify the exact remote tree and normal
Woodpecker status/comments, without manually dispatching CI. Record final SHA/results in the
external durable checkpoint. No unresolved introduced review findings or unfinished code remain.
A real-device logcat rejection/success smoke test remains useful before the owner's combined merge.
