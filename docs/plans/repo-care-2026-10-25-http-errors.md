# CLI HTTP failures return a failure exit status

## Baseline and completed work

- Repository: [alehkot/android-emu-agent](https://github.com/alehkot/android-emu-agent).
- Persistent branch: `development`.
- Actual starting development commit:
  [3f6ff186b5f3b14d46dcfa058efe1d3cd735b1f1](https://github.com/alehkot/android-emu-agent/commit/3f6ff186b5f3b14d46dcfa058efe1d3cd735b1f1).
- Observed upstream `main`:
  [a0dc463c57f8c9812fe1cf1d5196378ee2c31a80](https://github.com/alehkot/android-emu-agent/commit/a0dc463c57f8c9812fe1cf1d5196378ee2c31a80).
  The owner's earlier combined PR is merged. Development already preserves that work and the
  subsequent trace-path fix; no replay, reset, or upstream integration was necessary.
- Final implementation and complete recoverable patch:
  [c40d1b71efd3d9fa76691dd4d1ab03f98fcec755](https://github.com/alehkot/android-emu-agent/commit/c40d1b71efd3d9fa76691dd4d1ab03f98fcec755).
- Verified implementation tree: `a4d8e11c302710ec284dad99f60aef3940077396`. Its sole parent is the
  starting development commit. This record is a subsequent documentation-only checkpoint.

## Problem, impact, and rationale

Shared CLI response handlers inspected only the daemon's `error` envelope. FastAPI validation
rejections instead return HTTP 422 with `detail`, so ordinary invalid commands printed the
rejection but exited successfully. Shell automation could therefore proceed as if a rejected
operation had completed.

Reproduce with `reliability compile com.example --device emulator-5554 --mode speeed`, incompatible
`emulator start Pixel_8 --snapshot saved --cold-boot` options, or `app intent s-example` without an
intent target. Before this change each exits 0 despite a real validation rejection; now each exits
1 in human and JSON modes. No device operation runs for these rejected requests.

The three shared response handlers now honor HTTP 400–599 independently of payload shape. JSON
responses retain their original details and diagnostic IDs; human output retains useful validation
details. Failed HTTP responses cannot render a success indicator or trigger an artifact copy.
Successful output, structured AgentError rendering, request payloads, daemon validation, and retry
behavior are unchanged. Custom command-specific renderers are not redesigned by this patch.

This reproducible false-success defect was selected over broader trace-export lifecycle work
because it affects common invalid-input handling across existing commands and has a small,
independently testable correction. No dependency, workflow, security, release, or device behavior
change is included.

Research:

- [FastAPI validation errors](https://fastapi.tiangolo.com/tutorial/handling-errors/#override-request-validation-exceptions)
  explain the default HTTP 422 validation response, distinct from application error envelopes.
- [HTTPX response status codes](https://www.python-httpx.org/quickstart/#response-status-codes)
  distinguish an unsuccessful HTTP status from successful JSON decoding.

## Tests and review

- 48 new regression/control cases: 36 fail against the exact unchanged starting baseline and 12
  controls pass; all 48 pass on final code.
- Six cases run actual CLI payload construction through real FastAPI validation without starting
  daemon/device services. The remaining cases cover all three shared handlers in human/JSON modes,
  HTTP 400/404/422/500, success-shaped failure payloads, artifact destination preservation,
  successful copies/output, and unchanged AgentError handling.
- Python 3.11 and 3.12 supported full unit suites: **1,698 passed, two deselected** on each runtime.
- Unmodified canonical `./scripts/dev.sh check`: static/type/skill checks and both bridge stages
  pass, then the two existing AF_UNIX socket-creation tests fail with `PermissionError: [Errno 1]
  Operation not permitted`. The canonical gate is **not green**. These are the unchanged
  `test_daemon_controller_restricts_existing_socket` and `test_tightens_socket_permissions` cases;
  no permission control or check was weakened.
- Kotlin bridge: `shadowJar` succeeds and **61 tests pass** across 13 suites, no failures/errors/skips.
- Ruff formatting/lint, strict mypy, Pyright, skill validation, strict MkDocs, Markdown lint, and
  whitespace checks pass. CLI reference was regenerated; no command-surface change resulted.
- Full self-review and independent full prepublication review found no introduced
  moderate-or-higher finding. Independent focused suite: **74 passed**. Unrelated generated-doc
  formatting churn was removed. Independent postpublication review checked all 248 blob paths,
  modes, hashes, filesystem contents, parent, and the entire four-file diff; 74 focused tests pass
  again with no introduced moderate-or-higher findings. The freshly fetched published source also
  passes the full supported suite: 1,698 passed, two deselected.

These checks establish response/exit-status handling and real in-process request validation, not
live daemon-socket or Android-device behavior. Device integration remains unrun. A clean review is
not a guarantee of bug-free code.

## CI and next steps

Normal CI for the exact implementation commit has zero Actions runs, check-runs, and statuses.
The workflow triggers only on main pushes and pull requests, not development. The empty aggregate
status default `pending` is not an active check. No PR, manual dispatch/rerun, or enabling of paused
checks was used.

No implementation is unfinished and no introduced moderate-or-higher finding remains. Resume from
fresh remote development, preserving all accumulated commits. Complete the unmodified canonical
gate in an authorized own-machine setup that supports Unix sockets, and exercise representative
live daemon/device workflows when available. The owner may create a combined PR later. Existing
verification recovery is tracked in
[issues-tracker #12](https://github.com/alehkot/issues-tracker/issues/12); older resolved selector,
timeout, and Gradle limitations in that issue are historical, not new work to revive.
