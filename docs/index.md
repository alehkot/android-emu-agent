# Drive Android apps through a tight observe, act, verify loop

Android Emu Agent gives LLMs and developer tools a practical control plane for emulators and rooted
devices: compact UI snapshots, stable action refs, task specs with verifiers, app diagnostics,
artifacts, file transfer, JVM debugging, and replayable trace archives from one CLI.

[Explore the CLI reference](reference.md) |
[View source](https://github.com/alehkot/android-emu-agent)

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

| Capability                  | What it gives you                                                                                                       |
| --------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| **Compact UI snapshots**    | Actionable snapshots across XML Views, Compose, Litho, and mixed Android screens.                                       |
| **Generation-scoped refs**  | Short handles like `^a1` for precise taps and text entry, with ref healing when the target can be rebound.              |
| **Daemon-first I/O**        | A FastAPI daemon over a Unix socket keeps device sessions warm while the CLI stays thin and scriptable.                 |
| **Debugger bridge**         | Java 17+ JDI support for threads, stack traces, breakpoints, exception breaks, stepping, and constrained eval.          |
| **Forensics and artifacts** | Screenshots, log bundles, request diagnostics, process data, memory reports, and gfxinfo for evidence-driven debugging. |
| **Trace archives**          | `.aea-trace.zip` archives capture daemon exchanges for dry replay and Markdown reports.                                 |
| **Task harness**            | JSON task specs run ordered steps with step-level and final verifiers.                                                  |
| **Agent skills included**   | Ready-to-install skill docs with command references, recovery protocols, workflow examples, and safety guardrails.      |

## Built for repeated agent work

1. **Start a session.** Bind commands to a specific emulator or rooted device.
2. **Observe the screen.** Capture compact text or JSON snapshots with actionable refs.
3. **Act precisely.** Tap, type, clear, wait, launch apps, resolve intents, and inspect task state.
4. **Verify with evidence.** Re-snapshot, collect artifacts, read logs, and escalate into debugger
   or forensics flows.

## Command surface

`daemon` `device` `session` `task` `trace` `ui` `action` `wait` `app` `artifact` `emulator`
`reliability` `file` `debug`

Every command keeps human output concise and supports stable JSON where machine consumers need it.
The generated [CLI reference](reference.md) is the source of truth for flags and payloads.

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
