# Mapping files belong to the invoking CLI

## Baselines and recoverable work

- Repository: [alehkot/android-emu-agent](https://github.com/alehkot/android-emu-agent).
- Persistent working branch: `development`.
- Starting development head:
  [31460ac7dd47c546952de00e06bf3fc5e70e58a8](https://github.com/alehkot/android-emu-agent/commit/31460ac7dd47c546952de00e06bf3fc5e70e58a8).
- Observed upstream `main`:
  [a0dc463c57f8c9812fe1cf1d5196378ee2c31a80](https://github.com/alehkot/android-emu-agent/commit/a0dc463c57f8c9812fe1cf1d5196378ee2c31a80).
  The owner's combined PR #14 is merged. Its tree equals development's earlier
  `5cd382c25d5328163bf26642adaaf1e4d3c96816`; later accumulated fixes remain preserved. No upstream
  integration, replay, or reset was needed. All 14 PRs are merged, with no open PRs or standalone
  repository issues found. The prior branch claim was released.
- Published implementation and full recoverable patch:
  [63ca8784e614cc27bf1a9964ef44c95ff49d88d5](https://github.com/alehkot/android-emu-agent/commit/63ca8784e614cc27bf1a9964ef44c95ff49d88d5).
  Exact tree: `c321f5c719589ec8b9f103f01fdf13a578910a2a`; its sole parent is the starting head.
- Original tested local commit: `14749e9466352a22e285059ba9c0280caa1702dc`, same tree. Publication
  used real-parent Git objects and a non-force expected-head update after fresh branch checks. The
  exact published commit was reconstructed locally only after its SHA matched. Original local
  history and a recoverable bundle are retained; no synthetic or rewritten history was used.
- This is a subsequent documentation-only checkpoint. Its final SHA and exact-head CI observation
  are recorded in the existing
  [verification recovery issue](https://github.com/alehkot/issues-tracker/issues/12).

## Problem, evidence, and bounded fix

`debug mapping load mapping.txt --session <id>` sent `mapping.txt` unchanged to the long-lived
daemon and JVM. If the daemon started elsewhere, loading failed or silently selected another build's
same-named mapping file. This can make deobfuscated debug information misleading.

Reproduction: put one-class mapping content in the caller's `mapping.txt` and a distinct two-class
mapping in the daemon directory, then invoke the CLI from the caller directory. A native JVM probe
confirmed that the old relative payload loads the two-class decoy; an absolute caller path loads the
one-class intended file. Without a daemon-side file, the old path returns JSON-RPC `-32602`.

The CLI now expands `~` and makes nonblank paths absolute before transport, consistent with existing
APK/file/trace commands. `absolute()` deliberately retains symlink/`..` lookup semantics. Blank
inputs still reach the existing `ERR_INVALID_MAPPING_PATH` validation. Direct API schemas, Kotlin
loader checks, session validation, response/error handling, and timeouts are unchanged. No file is
uploaded or copied. Help, generated reference, and skill guidance are synchronized.

The previous reset-status checkpoint explicitly deferred this candidate. It is now selected because
it is reproducible in the documented mapping workflow and requires only a narrow CLI correction.
Other host-path commands already have caller-relative handling. No speculative debugger redesign,
dependency, permission, workflow, or release change is included.

Research:

- [Python pathlib absolute](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path.absolute):
  makes a path absolute without resolving symlinks or normalizing parent segments.
- [Android R8 retrace](https://developer.android.com/tools/retrace): mapping files reconstruct
  original class and method names, grounding the importance of selecting the intended file.

## Tests, review, and limitations

- Seven regression/control cases: **four failed and three passed on the unchanged baseline**; all
  seven pass after the fix. The actual CLI, FastAPI endpoint, and debug manager are exercised with
  mocked HTTP/session/bridge plumbing and real file reads. Cases cover relative/absolute/home paths,
  Unicode and spaces, symlink-parent traversal, and two blank-path rejections.
- Full supported Python 3.12 suite: **1,724 passed**, with only the two known AF_UNIX-restricted
  tests deselected. Repeated on the exact published implementation tree with the same result.
- Unmodified canonical `./scripts/dev.sh check`: formatting, Ruff, strict mypy, Pyright, skills,
  `shadowJar`, and Kotlin tests pass. Python stage fails only the two pre-existing socket-creation
  restrictions below. The canonical gate is **not fully green**. Strict MkDocs and Markdown checks
  were run separately and pass; generated reference and whitespace checks pass.
- Kotlin bridge: **61 tests across 13 suites**, no failures/errors/skips. No Kotlin source changed.
- An initial separate full unit invocation omitted the required writable HOME and hit nine
  pre-existing read-only-home failures; the corrected writable-HOME runs above supersede that setup
  failure. No extra test exclusions were added to obtain the supported result.
- Independent prepublication full-diff review found no introduced moderate-or-higher findings or
  actionable nits. **114 related tests pass** independently. A separate final-CLI-to-real-JVM probe
  from the daemon directory loads the intended caller mapping despite the decoy. That probe uses a
  mocked HTTP boundary and the unchanged previously built bridge; the final bridge is also rebuilt
  and tested by the canonical command.
- Self-review checks the complete change and current upstream context. All **252 published blobs and
  modes** equal the tested tree; exact parent, commit, and remote branch head were verified. A clean
  review does not guarantee bug-free code.

The unchanged failing tests are `test_daemon_controller_restricts_existing_socket` and
`TestSecureOwnSocket::test_tightens_socket_permissions`, both raising
`PermissionError: [Errno 1] Operation not permitted` when creating AF_UNIX sockets. No permission
controls or tests were weakened. Live daemon-socket and Android-device integration remain unrun;
local in-process tests and JVM probes do not establish real-device compatibility.

## CI and safe next steps

The exact implementation head has zero Actions runs, check-runs, and statuses. The workflow runs on
main pushes and PRs, not development; CI is **unrun**, not passed or actively pending. No manual
Actions dispatch/rerun, PR creation, or enabling of paused checks was used.

No implementation is unfinished or introduced moderate-or-higher finding remains. Resume from
freshly checked remote development and preserve all accumulated work. Complete the unmodified
canonical gate on a permitted own-machine setup supporting Unix sockets, and exercise mapping load
with a suitable debug session when available. The existing recovery issue tracks this verification
limitation; do not revive resolved historical selector/timeout/Gradle work from its older entries.
