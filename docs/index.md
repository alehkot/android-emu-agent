# Drive Android apps through a tight observe, act, verify loop

Android Emu Agent gives LLMs and developer tools a practical control plane for emulators and rooted
devices: compact UI snapshots, stable action refs, richer selectors with capability introspection,
explicit expectations, JSON task specs, human-editable `.aea` task scripts, app diagnostics,
artifacts, native performance captures, file transfer, JVM debugging, and replayable trace archives
from one CLI. It also exposes shell-backed system surfaces for notification shade, Quick Settings,
and runtime permission setup.

[Explore the CLI reference](reference.md) | [See task script examples](tasks.md) |
[Read the `.aea` spec](aea-spec.md) | [View source](https://github.com/alehkot/android-emu-agent)

```console
$ uv run android-emu-agent session start --device emulator-5554
status: done
session_id: s-abc123

$ uv run android-emu-agent ui snapshot s-abc123 --format text
context: com.example.app/.MainActivity
^a1 button "Sign in"
^a2 input  "Email"
^a3 input  "Password"

$ uv run android-emu-agent action tap s-abc123 ^a1
status: done
generation: 43
```

## Core capabilities

| Capability                  | What it gives you                                                                                                                                  |
| --------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Compact UI snapshots**    | Actionable snapshots across XML Views, Compose, Litho, and mixed Android screens.                                                                  |
| **Generation-scoped refs**  | Short handles like `^a1` for precise taps and text entry, with ref healing when the target can be rebound.                                         |
| **Selector introspection**  | Exact, contains, regex, fallback, state-filter, class, resource ID, content-desc, coordinate, and ref selector support is discoverable per target. |
| **Daemon-first I/O**        | A FastAPI daemon over a Unix socket keeps device sessions warm while the CLI stays thin and scriptable.                                            |
| **Debugger bridge**         | Java 17+ JDI support plus fused app/UI/debug observations for agent planning.                                                                      |
| **Forensics and artifacts** | App health profiles, native perf captures, screenshots, logs, process data, memory reports, and gfxinfo for evidence.                              |
| **Trace archives**          | `.aea-trace.zip` archives capture daemon exchanges for dry replay and Markdown reports.                                                            |
| **Task harness**            | JSON task specs and `.aea` scripts run ordered steps with step-level and final verifiers.                                                          |
| **Expectations**            | Assertion commands turn expected UI/app state into pass/fail JSON.                                                                                 |
| **Visual grounding**        | Optional screenshot-to-ref metadata ties bounds to image artifacts without requiring vision.                                                       |
| **System surfaces**         | Notification shade, Quick Settings, and runtime permission controls for setup and inspection.                                                      |
| **Agent skills included**   | Ready-to-install skill docs with command references, recovery protocols, workflow examples, and safety guardrails.                                 |

## Built for repeated agent work

1. **Start a session.** Bind commands to a specific emulator or rooted device.
2. **Observe the screen.** Capture compact text or JSON snapshots with actionable refs.
3. **Act precisely.** Tap, type, clear, wait, launch apps, resolve intents, and inspect task state.
4. **Verify with evidence.** Re-snapshot, collect artifacts, read logs, and escalate into debugger
   or forensics flows.

## Command surface

`daemon` `device` `expect` `session` `system` `task` `trace` `ui` `action` `wait` `app` `artifact`
`emulator` `reliability` `file` `debug`

Every command keeps human output concise and supports stable JSON where machine consumers need it.
The generated [CLI reference](reference.md) is the source of truth for flags and payloads. For
repeated flows, see the [task script examples](tasks.md) and the
[`.aea` task script specification](aea-spec.md).

## Architecture at a glance

| Layer            | Role                                                                         |
| ---------------- | ---------------------------------------------------------------------------- |
| **CLI**          | Typer commands, concise human output, and `--json` for pipelines.            |
| **Daemon**       | FastAPI over `/tmp/android-emu-agent.sock` with persistent device sessions.  |
| **Device I/O**   | `adbutils`, `uiautomator2`, screenshots, file transfer, logs, and app state. |
| **Debug bridge** | Kotlin JDI Bridge for debugger flows against debuggable Android apps.        |

## Quick start

```bash
uv sync
uv run android-emu-agent emulator list-avds
uv run android-emu-agent daemon start
uv run android-emu-agent session start --device emulator-5554
uv run android-emu-agent ui snapshot s-abc123 --format text
```
