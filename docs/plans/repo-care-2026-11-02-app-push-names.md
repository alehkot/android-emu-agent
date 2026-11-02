# Preserve source names in app-private pushes

## Baseline and completed scope

- Repository: <https://github.com/alehkot/android-emu-agent>.
- Persistent Repo Care branch: `development`.
- Actual starting development:
  [`451f5b651ae4412f2e404e76bd24d2811d10a1bf`](https://github.com/alehkot/android-emu-agent/commit/451f5b651ae4412f2e404e76bd24d2811d10a1bf).
- Observed upstream `main`:
  [`fc5b83f4a7a6658d3ebbf0224337bec278057538`](https://github.com/alehkot/android-emu-agent/commit/fc5b83f4a7a6658d3ebbf0224337bec278057538).
- Prepared publication implementation:
  [`12530022145f7d8eb45ac3fbaf22e9be4b870c3a`](https://github.com/alehkot/android-emu-agent/commit/12530022145f7d8eb45ac3fbaf22e9be4b870c3a).
- Equivalent tested local implementation: `7469f8c5928ecf7788a7268562ee2bb965bab1e8`.
  Both implementation trees are `c50d43a0f4bd4d1c901f76f0e3aa66aa52e14320`.

Fresh branch, issue and PR inspection found no active competing work, open PR, source issue or
unfinished implementation. Main is an ancestor of development; no upstream integration was needed.
Prior task-verifier and logcat fixes remain intact. Alternate historical local commit identities
were preserved separately; this change starts from the exact published development head.

## Problem and rationale

`file app push com.example.app config.json --remote files` should copy the source file into an
existing app-private `files` directory. Instead, the final `cp -r` used the UUID-prefixed staging
basename, so `files/config.json` was not created or updated even though the command reported success.
Directory copies into existing containers also leaked staging names instead of merging the
same-named source directory. Both root and `run-as` routes shared the problem.

The fix keeps the original basename inside a unique staging **parent** directory. Final copy
semantics are unchanged: an existing resolved destination directory contains the source basename;
an absent destination is the new path. Existing default and trailing-slash destination resolution
is preserved, including its nesting behavior. This is not a redesign into exact-destination merges
or atomic replacement. Matching files may be replaced; unrelated directory contents are retained.

The ordinary Android shell creates and owns the unique parent, using the existing traversal
permission convention. Cleanup removes only that transfer's directory, including after partial
preparation, ADB failure or app-copy failure. Common staging setup, root selection, app access
checks, file modes, shared-storage transfers and app-private pulls are unchanged.

Terminal `.` and `..` use the resolved directory's basename without changing the source path or
ordinary symlink names. A filesystem root has no usable basename and is rejected before staging;
it cannot become an empty or escaping child path. This closes a staging escape introduced by the
initial implementation, not a broader filesystem-path rewrite.

Selected over unproven device-list structured-error handling and broader shell-result changes:
the basename issue reproduced with real local copy commands in a common fixture-upload workflow.
The first directory reproduction suggested exact-target merging, but that would change native
copy semantics. Preserving the original basename is the narrower evidence-backed repair.

Research:

- [AOSP ADB push implementation](https://android.googlesource.com/platform/system/core/+/8ef1e1b535ba860d4aef9ffecdeae2478852ab31/adb/client/file_sync_client.cpp)
  appends the source basename when the destination is already a directory.
- [Toybox cp implementation](https://github.com/landley/toybox/blob/master/toys/posix/cp.c)
  likewise uses source names inside destination directories. No new copy option is required.

## Tests and review

- Original 16-case regression/control selection on unchanged development: eight failures and
  eight passing controls. All pass after the fix.
- 31 new cases total cover files/directories, repeated pushes, existing/new/trailing-slash targets,
  hidden files, empty/nested directories, literal spaces and punctuation, cleanup failures,
  shell-owned staging dispatch, dot/parent/symlink traversal and root rejection. Existing
  overlapping-transfer and long-ASCII/Unicode-name tests retain their isolation assertions.
- Final related file/CLI/endpoint suite: **246 passed**. Independent full-change review separately
  ran the same 246 relevant tests and found no remaining introduced moderate-or-higher findings.
- Final supported Python 3.11 unit suite: **1,929 passed, two deselected**. The unchanged excluded
  tests are `test_daemon_controller_restricts_existing_socket` and
  `TestSecureOwnSocket::test_tightens_socket_permissions`, previously blocked by sandbox AF_UNIX
  creation permissions. No test or permission requirement was weakened.
- Ruff lint/format (174 files), strict mypy (72 source files), explicit-interpreter Pyright,
  bundled skill validation, Markdown lint (24 files), regenerated CLI-reference comparison and
  whitespace checks passed. CLI help and bundled references document destination behavior.
- Self/independent review identified and fixed two introduced moderate findings: root-owned
  traversal-only staging parents could not be recursively cleaned by the shell, and a terminal
  `..` basename could escape its unique staging parent. Final full review is clear; review does
  not guarantee absence of bugs.

Tests execute generated shell copy commands on temporary synthetic host fixtures and mock ADB
transport/root dispatch. They establish naming, orchestration and cleanup, not actual Android
SELinux, device ownership or live ADB behavior. No real device/emulator check was run. There is no
browser UI change. Local full builds, bridge build/tests, MkDocs build and the build-containing
canonical `scripts/dev.sh check` were intentionally not run under the current local-build policy.

## Publication, CI and next steps

Exact starting development has a successful Woodpecker pipeline 8 status and matching PASS comment;
upstream main's latest matching report is pipeline 6. Development has zero check-runs; main has
successful `check`, `build` and `deploy` check-runs. Generic Woodpecker reports do not enumerate
actual job/platform coverage. No private runner logs were accessed.

At checkpoint preparation, publication objects exist but the persistent branch has not yet moved.
Recheck both exact heads immediately before a non-force expected-head update, then verify the
published commit/tree and its normal statuses, check-runs and commit comments. Record the resulting
final SHA and exact-head CI outcome in the durable external run checkpoint. Do not manually run CI
or create a PR to obtain coverage. Full local builds remain unrun.

No implementation or introduced review finding remains unfinished. Before the owner's combined
merge, a representative live Android file and directory push into an existing app-private
container remains useful, with both successful replacement and failed-copy cleanup paths.
