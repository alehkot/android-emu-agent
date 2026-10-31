# Trace paths follow the invoking CLI

## Baseline and completed change

- Repository: [alehkot/android-emu-agent](https://github.com/alehkot/android-emu-agent).
- Persistent working branch: `development`.
- Actual working baseline:
  [5cd382c25d5328163bf26642adaaf1e4d3c96816](https://github.com/alehkot/android-emu-agent/commit/5cd382c25d5328163bf26642adaaf1e4d3c96816).
- Observed upstream `main`:
  [a0dc463c57f8c9812fe1cf1d5196378ee2c31a80](https://github.com/alehkot/android-emu-agent/commit/a0dc463c57f8c9812fe1cf1d5196378ee2c31a80),
  the owner's merge of [PR #14](https://github.com/alehkot/android-emu-agent/pull/14). Its tree
  equals the working baseline. No upstream integration or replay of merged changes was necessary.
- Final implementation commit:
  [4d35831ab556ffc5b54a9d8cfa13d5dd7800444d](https://github.com/alehkot/android-emu-agent/commit/4d35831ab556ffc5b54a9d8cfa13d5dd7800444d).
  This checkpoint is a subsequent documentation-only commit.

## Problem, rationale, and scope

`trace stop --output`, `trace replay`, and `trace export` sent relative host paths unchanged to the
long-lived daemon. When launched from a different directory, the daemon wrote reports/archives in
the wrong directory or read a different same-named archive. The documented relative-path workflow
was therefore unreliable, including silent selection of the wrong evidence.

The CLI now expands `~` and binds archive inputs and explicit outputs to its current directory
before sending requests. Optional output defaults and empty-string behavior remain unchanged. Direct
daemon API semantics, trace archive formats, source-directory guards, and device behavior are
unchanged. Generated CLI help, workflow guidance, and the skill command reference describe the
behavior.

This bounded correction was selected over broader artifact-lifecycle work because it reproduces with
ordinary documented commands and follows the existing APK/file path convention.
[Python 3.11 pathlib documentation](https://docs.python.org/3.11/library/pathlib.html#pathlib.Path.absolute)
distinguishes `absolute()` from `resolve()`: preserving symlink and parent-component spelling avoids
changing destination meaning.

Reproduction: create different `run.zip` traces in caller and daemon working directories; run
`trace replay run.zip --json` from the caller directory. Before the fix, the daemon reads its own
archive. The regression tests run the actual trace manager from a different directory and confirm
the intended archive and output files.

## Verification and review

- 32 new cases: 24 failed on unchanged baseline, eight controls passed; all 32 pass after the fix.
- Combined trace CLI, manager, and endpoint suite: 58 passed, also independently rerun.
- Full supported unit suite on Python 3.11 and 3.12: 1,650 passed and two deselected on each
  runtime. A full-selection baseline run reproduces the two unchanged AF_UNIX permission failures in
  `test_daemon_controller_restricts_existing_socket` and `test_tightens_socket_permissions`; no
  checks or permissions were weakened.
- One initial full supported run had a transient failure in the untouched
  `test_task_run_endpoint_dispatches_wait_verifier`; the unchanged baseline targeted case and
  subsequent complete runs passed. This was not hidden by an additional exclusion.
- Ruff formatting/lint, strict mypy, Pyright, skill validation, strict MkDocs, Markdown lint,
  generated-reference regeneration, and whitespace checks passed.
- Full self-review and independent review found no remaining introduced moderate-or-higher findings.
  A low-priority documentation ambiguity was corrected: without `--output`, use `--json` to read the
  Markdown response. An independent real-manager probe confirmed that trace-source output remains
  rejected without damaging the active trace.
- Tests use real host filesystem archives and Markdown reports with mocked daemon transport. They do
  not establish live daemon-socket or Android-device operation; those integration checks were not
  run. A clean review is not a guarantee of bug-free code.

## CI, remaining verification, and next steps

Native bridge verification now passes with the pinned Gradle 8.11 and Temurin JDK 17: `shadowJar`
succeeds and all 61 Kotlin tests pass (13 suites, zero failures/errors/skips). This resolves the
previous local Gradle download/build blocker without changing repository configuration or checks.

The required unmodified `./scripts/dev.sh check` passes static/type/skill checks and both bridge
stages, then fails only at the two existing AF_UNIX permission tests listed above. Its later
documentation stages were therefore run separately and passed. The canonical gate is not reported as
green.

Normal CI is not triggered by development pushes: the current workflow runs on main pushes and pull
requests only. No PR or manual workflow dispatch/rerun is part of this work. Exact published head
observations belong with the publication report; absence of a run is not a pass.

No implementation is unfinished and no introduced moderate-or-higher finding remains. Resume from
fresh remote development, preserve accumulated history, and repeat the complete canonical gate in an
authorized own-machine setup that supports Unix sockets. Live daemon/device integration remains
unrun for this change. The owner may create the next combined PR when desired; do not create one
merely to trigger CI.
