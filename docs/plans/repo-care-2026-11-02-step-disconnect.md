# CI follow-up: keep pending debugger steps reachable on disconnect

## Trigger and baseline

- Repository: <https://github.com/alehkot/android-emu-agent>, persistent branch `development`.
- Original run baseline:
  [`451f5b651ae4412f2e404e76bd24d2811d10a1bf`](https://github.com/alehkot/android-emu-agent/commit/451f5b651ae4412f2e404e76bd24d2811d10a1bf).
- This follow-up starts from the newly published app-push checkpoint:
  [`80aca9ff429aeb76b9f65bc8b6774eefd991f855`](https://github.com/alehkot/android-emu-agent/commit/80aca9ff429aeb76b9f65bc8b6774eefd991f855).
- Upstream main remains
  [`fc5b83f4a7a6658d3ebbf0224337bec278057538`](https://github.com/alehkot/android-emu-agent/commit/fc5b83f4a7a6658d3ebbf0224337bec278057538).

Normal [Woodpecker pipeline 9's exact-commit report](https://github.com/alehkot/android-emu-agent/commit/80aca9ff429aeb76b9f65bc8b6774eefd991f855#commitcomment-207696186)
reported FAIL, matching its GitHub status. Kotlin's existing disconnect characterization test timed
out waiting 15 seconds for a step whose product timeout is 20 seconds. The report lists 61 tests,
one failure at `JdiSessionCharacterizationTest.kt:97`; Python static/type/skill stages passed.
No private runner logs were accessed and no CI was manually rerun.

The complete JDI subtree was identical on that commit, starting development, and upstream main
(`05dae282f11d0cb51849575eb4d85fa9ebe3105e`). Thus the earlier Python file-transfer change did not
alter the failing subsystem. CI-first priority prompted diagnosis instead of unrelated work.

## Reproduced defect and bounded repair

`handleStepEvent` removed `activeStep` before remote JDI reads needed to construct its stopped
payload. A disconnect during those reads reached the existing disconnect handler, but that handler
could no longer find the waiting future. The step waited for its ordinary timeout rather than
promptly returning the existing VM-disconnected explanation and re-attach remediation.

A deterministic Java proxy against the matching existing bridge artifact reproduced
`disconnected=true`, `activeStep=null`, and `completionDone=false`. A new Kotlin regression also
failed on unchanged production code. This is a demonstrated product race consistent with the CI
symptom; the bounded CI excerpt cannot establish the exact interleaving of that specific failure.

The pending step now stays registered through every throwing JDI payload/suspension read. Success
checks pending identity under the state lock, records suspension, retires the pending step, and
completes its future together. An already retired/replaced step resumes its stale event without
clearing newer work or adding stale suspension state. Existing event-loop disconnect handling can
therefore complete the original future on failure. No timeout was increased, assertion removed,
workflow changed, or new retry introduced. CLI/API payloads and Python code are unchanged.

Research: [JDI VMDisconnectedException](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jdi/com/sun/jdi/VMDisconnectedException.html)
documents failure of operations after target disconnection;
[CompletableFuture completion](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
defines its single successful terminal completion. Existing project result semantics define the
repair, not a new error policy.

## Verification and publication checkpoint

- Prepared publication implementation:
  [`761ae88b8e7c7be9e441db975664749524d1b1fd`](https://github.com/alehkot/android-emu-agent/commit/761ae88b8e7c7be9e441db975664749524d1b1fd).
  Equivalent local implementation: `a9fba5d6bc0d3f0dbdb229382bcd39159db28de1`.
  Both implementation trees are `e007f525648e3141135005a5748bf6781fcd7935`.
- Baseline targeted event-loop selection: six tests, one new regression failure. The same defect
  also reproduced against the matching existing artifact with a direct Java proxy.
- Final focused offline Gradle tests: **11 passed** (nine event-loop, two characterization),
  including the unchanged characterization that failed in CI. Independent review separately ran
  those 11 tests with zero failures/errors/skips. No timing assertion was relaxed.
- Regression cases inject disconnects at event access, location payload construction and final
  suspension-ID access; controls verify normal success, unrelated requests, retired events and
  replacement pending steps. The direct Java probe on final compiled classes now reports
  `completionDone=true` and the expected interrupted/re-attach payload.
- Whole-change self and independent review found no remaining introduced moderate-or-higher issue.
  Whitespace checks pass. A clean review does not guarantee bug-free code.
- The earlier app-push tests remain preserved: 1,929 Python unit tests passed on its exact published
  tree with the same two known AF_UNIX exclusions, plus independent 246-case file/CLI coverage.

Only targeted offline/native-JVM test tasks were run locally, including their required compilation;
no full bridge/release build, `shadowJar`, full build-containing canonical check, or real Android
device check was run. A local target JVM is not an Android-device validation. The independent
compiler initially logged daemon startup warnings, recovered, and completed successfully; no
settings or dependencies were changed.

At checkpoint preparation these objects are not yet the branch head. Immediately recheck development
and main, publish with a non-force expected-head update, and verify the exact resulting commit/tree
and normal GitHub status/check/comment evidence. Final publication SHA and CI outcome belong in
the durable external run checkpoint. No manual CI dispatch or PR is authorized. Resume any
reported relevant failure before unrelated improvements; do not infer a pass from older heads.
