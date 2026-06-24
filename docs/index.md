# Drive Android Apps from an Observe, Act, Verify Loop

Android Emu Agent gives agents and developer tools one control plane for Android UI automation:
compact snapshots, precise actions, explicit verification, and evidence collection through a
daemon-backed CLI.

Use this site to learn the workflow first, then use the generated command reference for exact flags.

## Start by Goal

| Goal                               | Page                                                                                                    |
| ---------------------------------- | ------------------------------------------------------------------------------------------------------- |
| Run a first UI automation loop     | [Connect to a Device and Start a Session](workflow-examples.md#connect-to-a-device-and-start-a-session) |
| Follow multi-command procedures    | [Workflow examples](workflow-examples.md)                                                               |
| Write reusable app flows           | [Task script guide](tasks.md)                                                                           |
| Look up `.aea` parser rules        | [`.aea` task script specification](aea-spec.md)                                                         |
| Look up command syntax and options | [Generated CLI reference](reference.md)                                                                 |

## Core Workflow

1. Start or connect to an emulator or rooted device.
2. Start a session for that target.
3. Capture a compact snapshot and choose a `^ref` or selector.
4. Run one action.
5. Verify the result with a fresh snapshot, wait, expectation, artifact, trace, or debugger read.

Example:

```bash
uv run android-emu-agent session start --device emulator-5554 --json
uv run android-emu-agent ui snapshot <session-id> --format text
uv run android-emu-agent action tap <session-id> ^a1
uv run android-emu-agent expect exists <session-id> --text "Welcome" --timeout-ms 5000
```

## Main Capabilities

| Capability                     | Use it when                                                                            |
| ------------------------------ | -------------------------------------------------------------------------------------- |
| Compact UI snapshots           | You need actionable refs for the current screen.                                       |
| Rich selectors                 | A stable ref is not available or a reusable flow should survive UI generation changes. |
| Waits and expectations         | You need explicit pass/fail checks instead of sleeping.                                |
| Task harness                   | A flow should be reviewable, repeatable, and validated before it touches a device.     |
| Trace archives                 | A flaky run needs replayable daemon request/response evidence.                         |
| Visual grounding               | A human or vision model needs screenshot coordinates for selected refs.                |
| Artifacts and reliability data | A failure needs screenshots, logs, process state, memory, gfxinfo, or native traces.   |
| System surfaces                | Setup requires notifications, Quick Settings, or runtime permission changes.           |
| Debugger bridge                | UI signals are not enough and the target app is debuggable.                            |

## Architecture

```text
CLI client
  -> FastAPI daemon over /tmp/android-emu-agent.sock
    -> sessions, snapshots, actions, waits, expectations, tasks, traces, artifacts
    -> adbutils and uiautomator2
    -> Kotlin JDI Bridge for debugger flows
      -> Android emulator or device
```

The CLI stays scriptable and concise. The daemon keeps device sessions warm, owns request
diagnostics, and returns structured JSON for agent pipelines.

## Where Exact Syntax Lives

`reference.md` is generated from the live Typer CLI and is the command source of truth. Regenerate
it from the repo root with:

```bash
./scripts/dev.sh docs-gen
```

Do not hand-edit generated command tables. Use the task guide, workflow examples, and `.aea`
specification for reader-facing explanations and procedures.
