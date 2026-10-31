# Repo Care: reject occupied emulator ports

## Baseline and result

- Repository: [alehkot/android-emu-agent](https://github.com/alehkot/android-emu-agent)
- Persistent branch: `development`, verified Repo Care history after combined PR #14.
- Starting development: `0783ed3e8400585e64535b0f7beaa3a4b16113ce`.
- Observed upstream main: `a0dc463c57f8c9812fe1cf1d5196378ee2c31a80`, unchanged before push.
- Published implementation:
  [72e040d1dab6e8a215ca66e4b5a9b47ce164adf3](https://github.com/alehkot/android-emu-agent/commit/72e040d1dab6e8a215ca66e4b5a9b47ce164adf3).
- Exact implementation tree: `ee875ab955659253f27b3f76dac8d4b4ca28c612`.
- This documentation-only descendant is the final checkpoint; its exact SHA is recorded in the
  recovery issue and local manifest, avoiding a self-referential commit hash.

## Problem and bounded fix

Starting a new AVD with `--port 5554` while `emulator-5554` was already listed by ADB could return
the existing emulator as the newly started AVD. The discovery helper accepted the expected serial
before checking the spawned process. Subsequent automation could act on the wrong device.

The manager now rejects an explicitly requested console port already present in its fresh ADB
emulator inventory, before spawning anything. The existing launch error includes the port and
suggests a free port or automatic selection. This applies with and without boot waiting; existing
emulators are neither stopped nor otherwise changed. Free and automatic port paths, parameters and
successful output are unchanged. CLI-generated and skill reference documentation are synchronized.

[Android's emulator command-line documentation](https://developer.android.com/studio/run/emulator-commandline#common)
explains console/ADB port pairs and that occupied ports prevent startup. The fix uses the existing
inventory, not an OS port probe or new reservation system. It does not claim atomicity against
concurrent external launches or detection of non-ADB port users.

An alternative device-list error-rendering concern was not pursued: a fabricated JSON 500 is not
evidence that the real unhandled discovery failure takes that path.

## Verification

- Ten new regression/control tests pass. Against the exact baseline, six fail and four controls
  pass.
- Tests cover occupied ports with both wait modes, free and automatic launches, and real FastAPI
  endpoint-to-CLI human/JSON failure propagation with mocked emulator I/O.
- Supported Python suite: 1,815 passed, two known environment-limited socket cases deselected.
- Full canonical check passed Ruff format/lint, strict mypy, pyright, skill validation, JDI bridge
  build and 61 Kotlin tests in 13 suites, then encountered the same two AF_UNIX creation
  `PermissionError: Operation not permitted` failures as baseline. Canonical gate is not fully
  green.
- Strict MkDocs, Markdown lint and whitespace checks passed separately. Initial bridge invocation
  lacked the installed JDK17 path; rerunning with that existing JDK passed.
- Independent pre-publication review: 97 focused tests and 12 probes across occupied/free ports
  5554, 5556 and 5584, both wait modes, using the actual discovery helper. No moderate-or-higher
  introduced finding remained.
- Independent post-publication full five-file implementation review and 97 focused tests passed on
  `72e040d1`; the final checkpoint was reviewed separately with no moderate-or-higher introduced
  findings.
- All 262 published file blobs matched the reviewed local tree. No unrelated source, dependency,
  workflow or settings changes.
- Real emulator/device behavior remains unrun. Mocked tests establish control flow and error
  propagation, not live Android compatibility.

## CI and next steps

Exact implementation commit has zero Actions runs, check runs and status checks. Workflows trigger
on main/PRs, not development. CI is unrun; the empty combined status's default pending value is not
a running job. No manual Actions or PR was created.

Resume from fresh remote development, preserving accumulated work. Run the canonical gate with
permitted Unix-socket support and smoke-test an occupied fixed port on an own-machine Android
emulator before a later combined merge. No implementation is unfinished. Recovery details and exact
final checkpoint commit are appended to
[recovery issue](https://github.com/alehkot/issues-tracker/issues/12).
