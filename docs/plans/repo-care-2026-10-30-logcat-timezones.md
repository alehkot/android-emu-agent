# Repo Care: timezone-independent log capture bounds

## Baseline and result

- Repository: [alehkot/android-emu-agent](https://github.com/alehkot/android-emu-agent).
- Persistent working branch: `development`, continuing verified Repo Care history after PR #14.
- Starting development:
  [550a2e9b6dd5ede9e6f574dfbefa4ee18d48e729](https://github.com/alehkot/android-emu-agent/commit/550a2e9b6dd5ede9e6f574dfbefa4ee18d48e729).
- Observed upstream main:
  [a0dc463c57f8c9812fe1cf1d5196378ee2c31a80](https://github.com/alehkot/android-emu-agent/commit/a0dc463c57f8c9812fe1cf1d5196378ee2c31a80),
  unchanged immediately before publication.
- Published implementation:
  [df2ca3476f9440b92b249b841129b5d8b232b066](https://github.com/alehkot/android-emu-agent/commit/df2ca3476f9440b92b249b841129b5d8b232b066).
- Exact implementation tree: `9595b563c870f316ede9098439e0895777a6b7f3`.
- This documentation-only descendant is the final checkpoint. Its exact commit is recorded in
  [recovery issue #12](https://github.com/alehkot/issues-tracker/issues/12), avoiding a self-reference.

## Problem, rationale and scope

The helper converted ISO/relative instants into the daemon host's local wall time, while logcat
interprets that timestamp in the device timezone. For example, `2026-10-30T15:30:00Z` became
`11:30` on a New York host. An emulator using UTC then captured from four hours too early. A host
in Tokyo produced the following day's `00:30`, potentially excluding the desired recent logs.

Parsed ISO and relative inputs now use fractional epoch seconds with three millisecond digits.
The decimal is retained even for whole seconds, so logcat does not mistake the value for a line
count. Native space-separated logcat timestamps, integer line counts, filters, output artifacts,
request schemas and bounded capture behavior are unchanged. T-separated ISO inputs without an
offset retain the existing UTC interpretation. CLI help, generated reference and skill guidance
are synchronized.

[Android 7 logcat source](https://raw.githubusercontent.com/aosp-mirror/platform_system_core/android-7.0.0_r1/logcat/logcat.cpp)
already accepts epoch `%s.%q` alongside the formerly generated year-prefixed timestamp format.
[Current AOSP logcat](https://android.googlesource.com/platform/system/logging/+/refs/heads/main/logcat/logcat.cpp)
retains both. This does not claim new support for historical Android versions lacking either
format, nor correct clocks when host/device wall clocks themselves disagree.

Selected over snapshot-restore failure recovery, which needs a decision about resuming potentially
partial VM state. Multi-process log collection would require broader filtering semantics. Neither
was changed; no speculative recovery, dependency, workflow or unrelated cleanup was introduced.

## Verification and review

- All 43 new regression/control cases pass. On the unchanged starting implementation, 25 fail and
  18 compatibility controls pass.
- Coverage includes UTC/New York/Japan host zones, equivalent explicit ISO offsets, fixed-clock
  relative bounds, native device-local timestamps, line counts, whole-second `.000`, and actual
  manager command construction with existing package/priority filters and artifact output.
- Full supported Python suite: 1,858 passed, two known socket cases deselected.
- Required canonical check passed Ruff format/lint, strict mypy, Pyright, skills, Kotlin bridge
  build and 61 Kotlin tests in 13 suites. It then failed the same two existing AF_UNIX permission
  tests: `test_daemon_controller_restricts_existing_socket` and
  `TestSecureOwnSocket::test_tightens_socket_permissions`. Socket creation returned EPERM; the
  canonical gate is not fully green. No restrictions or checks were weakened.
- Strict MkDocs, Markdown lint and whitespace checks pass separately. Generated docs were
  regenerated, not manually authored.
- Independent full-change review found no moderate-or-higher introduced findings; 65 focused
  artifact tests and 28 separate timezone/DST/offset probes passed. A documentation ambiguity
  between T-separated ISO and native space-separated timestamps was clarified before publication.
- All 264 published implementation blobs/modes match the tested tree. The exact published head
  again passed 1,858 supported tests; independent published review and 65 focused tests found no
  moderate-or-higher introduced findings. The complete change including this checkpoint was
  independently reviewed. Live Android/logcat integration remains unrun. Mocked shell tests
  demonstrate conversion and command wiring, not every device's behavior.

## CI and next steps

The exact implementation has zero Actions runs, check runs and statuses. Development pushes are
excluded by main/PR-only triggers. CI is unrun, not actively pending; the empty combined status's
`pending` default does not represent a running job. No manual Actions or PR was created.

No implementation is unfinished and no introduced review finding remains open. Resume from fresh
remote development, preserving accumulated work. Before the owner's combined merge, run the
canonical gate on a permitted own-machine setup supporting Unix sockets and smoke-test recent log
capture with different host/device timezones. Keep native timestamp and line-count controls.
