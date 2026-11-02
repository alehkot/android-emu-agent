# Continue collecting attached task verifiers

## Baseline and scope

- Repository: <https://github.com/alehkot/android-emu-agent>.
- Persistent working branch: `development`.
- Starting development:
  [`bd6177d641347b04cc81beb775dd4470f093a6e8`](https://github.com/alehkot/android-emu-agent/commit/bd6177d641347b04cc81beb775dd4470f093a6e8).
- Observed upstream `main`:
  [`fc5b83f4a7a6658d3ebbf0224337bec278057538`](https://github.com/alehkot/android-emu-agent/commit/fc5b83f4a7a6658d3ebbf0224337bec278057538).
- Prepared publication implementation:
  [`9e128aa9e57549cad57d6f6d5bc6fb600046eea3`](https://github.com/alehkot/android-emu-agent/commit/9e128aa9e57549cad57d6f6d5bc6fb600046eea3).
- Equivalent tested local implementation: `305281dace605b869515ab3c66e3bbe0b0c8c5a5`.
  Both implementation trees are `aa86460aa0086d1c3a38ff1fb1be019c53525b2f`.

The verified Repo Care branch already contained the prior logcat fix; no unfinished implementation,
open PR, open source-repository issue, or competing branch claim required resumption. Upstream is
an ancestor, so integration was unnecessary. Accumulated work and historical local branches were
preserved. No PR, workflow, dependency, platform, or device-operation changes were made.

## Problem and rationale

`task run --continue-on-failure` continued later steps and final verifiers, but silently omitted
remaining attached verifiers after the first verifier failure. A normal script with `home`, two
attached text checks, then `back` collected only the first attached check. This contradicted the
existing flag and prevented collecting all requested observations in a single run.

Forward the existing stop policy into step execution. Continue remaining attached verifiers when
requested, retain the first failure as primary, and keep the step/task failed after later passing
checks. Default fail-fast behavior is unchanged. A failed step operation still skips its attached
verifiers; continue mode proceeds to later steps and final checks as before.

Selected over a suspected device-list error-reporting gap: the latter lacked a demonstrated normal
structured-error path, while this omission reproduced directly with the real task executor.
No broader execution, retry, cancellation, selector, or timeout redesign is included.

Related public research: [Robot Framework continuation semantics](https://robotframework.org/robotframework/latest/RobotFrameworkUserGuide#continuing-on-failure)
and [pytest execution controls](https://pytest.org/en/stable/reference/reference.html#test-execution-control).
They distinguish collecting further observations from clearing failure status. Repository flag/help
and the reproduced behavior, not other projects' semantics, establish the intended scope here.

## Verification and review

- Four new manager cases: baseline one failure and three passing controls; all pass after the fix.
- Eight existing end-to-end CLI combinations extended with a second attached verifier: JSON task
  and `.aea`, human and JSON output, stop and continue. They exercise the real HTTP client and
  task executor with an offline dispatcher, assert all expected results and preserve exit 1.
- Task-focused suite: 450 passed. Final supported Python unit suite: 1,898 passed, two pre-existing
  Unix-socket permission cases deselected (`test_daemon_controller_restricts_existing_socket` and
  `TestSecureOwnSocket::test_tightens_socket_permissions`). This is not an unrestricted full pass.
- Ruff lint/format, strict mypy (72 source files), Pyright, skills validation, Markdown lint (24
  files), generated CLI-reference comparison and whitespace checks pass. Pyright first used the
  wrong interpreter and reported missing imports; explicit test-venv interpreter resolves them.
- Whole-change self-review and independent review found no introduced moderate-or-higher findings.
  Independent tests: 226 task/CLI/API/trace cases and 128 verifier-status/order combinations pass.
  Review is not a guarantee of bug-free code.
- No local full build was run. Build-containing canonical `scripts/dev.sh check`, bridge builds/tests,
  MkDocs build and real Android/emulator checks were not run locally. There is no browser UI for
  this change. Offline tests establish orchestration/reporting, not live Android behavior.

## Publication, CI and next steps

Both exact starting heads have successful Woodpecker statuses and matching PASS comments; latest
reports are development pipeline 7 and main pipeline 6. These generic reports do not enumerate
job/platform coverage. Main also has successful `check`, `build` and `deploy` check-runs; development
has no check-runs. No private runner logs were accessed.

At this checkpoint's preparation, publication objects exist but the branch has not yet advanced.
Only publish after immediate remote development/main rechecks, using a non-force expected-head
update. Verify the exact final commit/tree and normal status/check/comment evidence afterward;
record final publication SHA and CI outcome in the durable external run checkpoint. No manual CI
run or PR is authorized. Local full builds remain unrun until normal CI provides applicable evidence.

No unfinished implementation or unresolved introduced review finding remains. A representative
live-device script with multiple attached checks remains useful before the owner's combined merge.
