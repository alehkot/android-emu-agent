# Trace replay stops at failed task results

## Baseline and scope

- Persistent branch: `development`.
- Starting development: [5018e84025a231e40fe6a3a17c7ecbd35da48e70](https://github.com/alehkot/android-emu-agent/commit/5018e84025a231e40fe6a3a17c7ecbd35da48e70).
- Observed upstream main: [3d5d16216189c79c3d7e7af8e6734e846fafaefa](https://github.com/alehkot/android-emu-agent/commit/3d5d16216189c79c3d7e7af8e6734e846fafaefa).
  The trees match; development preserves the owner's main integration and accumulated fixes.
- Implementation: [760f9ff4421c7ff37c3326ef924a85ca3d2d8a98](https://github.com/alehkot/android-emu-agent/commit/760f9ff4421c7ff37c3326ef924a85ca3d2d8a98).
- Original local implementation: `a2242a49229c11bfcdbef99de643f4c7c4718dff`. Native Git push
  had no configured HTTPS credential. Authorized GitHub connector publication preserves the same
  implementation tree (`fad3056f5c8554fb0f966f475b88cd2f6f0e7142`) with server commit metadata.
- All existing PRs are closed; the former Woodpecker draft was superseded by direct main work,
  not revived. No open repository issue or competing branch claim was found.

## Problem and rationale

Task execution deliberately reports failed actions or verifiers with HTTP 200 and a top-level
`status: "failed"`, not a top-level `error`. Trace replay inspected only the HTTP status and error
field after discarding the archived response. Consequently, `trace replay --until-failure` could
include subsequent exchanges and incorrectly report `stopped_at_failure: false`.

Replay now inspects the original response's explicit failure status. It includes the failed task
exchange and omits later exchanges. Unrestricted replay, archive format, projected step fields,
HTTP/daemon-error handling and dry-run behavior are unchanged. No task is executed during replay.
The CLI help, regenerated CLI reference and bundled command guidance explain this behavior.

The concrete repository task-result contract drives this correction. As related research,
[OpenTelemetry HTTP span guidance](https://opentelemetry.io/docs/specs/semconv/http/http-spans/#status)
allows additional request context to classify outcomes more precisely than HTTP status alone.
This project does not adopt OpenTelemetry or change HTTP status semantics.

A separate logcat concern was investigated but not changed: `ArtifactManager.pull_logs` ignores
nonzero `ShellResponse.exit_code`, potentially preserving rejection text as an apparent successful
artifact. Review this separately with real command-status and fallback regression coverage; do not
expand this trace fix into unrelated changes. Snapshot-restore partial-state recovery remains a
separate consequential behavior decision, as noted in the prior checkpoint.

## Verification and review

- Twelve new regressions failed before the implementation and pass afterward. They use real JSON
  and script task execution, HTTP endpoints and trace middleware, covering action, step-verifier and
  final-verifier failures with both stop/continue modes, ZIP and unpacked traces, and no replayed
  device requests.
- Nine additional position/response controls pass. Failed exchanges remain included at first,
  middle and last positions; absent response, nested failure-looking fields and arbitrary
  `passed: false` alone do not redefine the explicit response-status contract.
- Full supported Python unit suite: **1,879 passed, two deselected**. The initial full-selection
  baseline reproduced the same two existing socket-creation EPERM failures:
  `test_daemon_controller_restricts_existing_socket` and
  `TestSecureOwnSocket::test_tightens_socket_permissions`. No tests or restrictions were weakened.
- Ruff format/lint, strict mypy, Pyright with the project interpreter, skill validation, strict
  MkDocs, Markdown lint and whitespace checks pass. CLI reference was regenerated and formatted.
- Full self-review and independent review found no introduced moderate-or-higher findings.
  Independent verification: **182 trace/task tests**, **216 replay matrix cases**, and a legacy
  archive without response fields passed.
- These tests establish archive classification, task-result integration and dry-run behavior;
  they do not verify real Android device interaction. No bridge behavior changed.
- Per the owner's build clarification, the full canonical bridge/build gate is deferred to normal
  CI rather than duplicated locally. No local full-build or emulator/device pass is claimed.

## CI evidence and next steps

Before selecting this change, exact starting development had zero commit statuses, checks,
comments and Actions runs. Main had a successful canonical Actions check but no Woodpecker status
or comment. Empty combined-status `pending` with zero contexts is missing evidence, not an active
build. The repository config targets normal pushes to both branches; no manual CI was dispatched.

This checkpoint is written before publication. The implementation and this documentation-only
checkpoint must have their remote head/tree verified, followed by normal exact-head status/check
and Woodpecker commit-comment inspection. Record the final SHA and observed result in the durable
run checkpoint and, if verification remains blocked, the existing recovery issue
[#12](https://github.com/alehkot/issues-tracker/issues/12). Do not treat a generic green report as
proof of device coverage or claim a build pass when the expected report is missing.

No implementation is unfinished and no introduced review finding remains open. Resume from fresh
remote development, preserve owner changes, and resolve any relevant normal-CI failure before
unrelated improvement work.
