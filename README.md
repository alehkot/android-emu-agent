# Android Emu Agent

Android Emu Agent turns an Android emulator or device into a reliable control plane for coding
agents.

It gives agents what raw `adb`, brittle coordinate taps, and one-off test scripts do not: a current
screen model, generation-scoped action targets, explicit verification, reusable flows, and evidence
when something fails.

[Documentation](https://alehkot.github.io/android-emu-agent/) |
[CLI reference](https://alehkot.github.io/android-emu-agent/reference/) |
[Source](https://github.com/alehkot/android-emu-agent)

## 10-Second Pitch

If a coding agent needs to use Android like a developer would, Android Emu Agent provides the loop:

```text
observe the screen -> act on a known target -> verify the result -> keep evidence
```

| Need                                  | What Android Emu Agent gives you                                      |
| ------------------------------------- | --------------------------------------------------------------------- |
| Understand the current screen         | Compact UI snapshots with actionable refs such as `^a1`               |
| Tap, type, swipe, and navigate safely | Refs, semantic selectors, fallback selectors, and capability reports  |
| Avoid blind sleeps                    | Waits and expectations with structured pass/fail results              |
| Repeat an app flow                    | JSON task specs and human-editable `.aea` scripts                     |
| Debug failures instead of guessing    | Screenshots, logs, trace archives, artifact bundles, reliability data |
| Go below the UI when needed           | Kotlin JDI Bridge flows for debuggable apps                           |
| Fit into an agent toolchain           | Thin CLI, daemon-backed sessions, JSON output, bundled agent skills   |

## First Useful Loop

After install, run this once you have an emulator or device visible to `adb`:

```bash
uv run android-emu-agent daemon start
uv run android-emu-agent session start --device emulator-5554 --json
uv run android-emu-agent ui snapshot <session-id> --format text
uv run android-emu-agent action tap <session-id> ^a1
uv run android-emu-agent expect exists <session-id> --text "Welcome" --timeout-ms 5000
```

The important part is the contract: every action starts from observed state and ends with an
explicit check, not an assumption.

## Start by Goal

| Goal                                                    | Start here                                           |
| ------------------------------------------------------- | ---------------------------------------------------- |
| See complete workflow examples                          | [Workflow examples](docs/workflow-examples.md)       |
| Write a reusable Android flow                           | [Task script guide](docs/tasks.md)                   |
| Look up `.aea` syntax                                   | [`.aea` task script specification](docs/aea-spec.md) |
| Find exact CLI flags                                    | [Generated CLI reference](docs/reference.md)         |
| Install the bundled agent skill                         | [Agent Skill](#agent-skill)                          |
| Understand daemon sessions, refs, selectors, and traces | [Core Concepts](#core-concepts)                      |

## Requirements

| Requirement                  | Needed for                                        |
| ---------------------------- | ------------------------------------------------- |
| Python 3.11+                 | Running the Python CLI and daemon                 |
| `uv`                         | Installing and running the project in this repo   |
| Android SDK `platform-tools` | `adb` device discovery and most device operations |
| Android SDK `emulator`       | Starting and stopping Android Virtual Devices     |
| Android SDK `cmdline-tools`  | `avdmanager` and `sdkmanager` workflows           |
| Emulator or rooted device    | Primary automation and diagnostics target         |
| JDK 17+                      | Debugger bridge commands only                     |

If you only control an already-running device, `adb` is enough. If you want this tool to start AVDs,
ensure `emulator` is also on `PATH`.

Recommended macOS Android SDK setup:

```bash
export ANDROID_SDK_ROOT="$HOME/Library/Android/sdk"
export PATH="$ANDROID_SDK_ROOT/platform-tools:$ANDROID_SDK_ROOT/emulator:$ANDROID_SDK_ROOT/cmdline-tools/latest/bin:$PATH"

adb version
emulator -list-avds
avdmanager list avd
```

## Install

```bash
git clone https://github.com/alehkot/android-emu-agent.git
cd android-emu-agent
uv sync --all-extras
```

Inside the repo, run commands as:

```bash
uv run android-emu-agent <command>
```

## Quick Start

Use this flow to verify that the CLI, daemon, and target device are working.

1. Optional: list and boot an emulator.

   ```bash
   uv run android-emu-agent emulator list-avds
   uv run android-emu-agent emulator start <avd-name> --wait-boot
   ```

2. Start the daemon. The CLI can auto-start it, but starting it explicitly makes setup easier to
   debug.

   ```bash
   uv run android-emu-agent daemon start
   uv run android-emu-agent daemon status --json
   ```

3. Confirm that a device is visible.

   ```bash
   uv run android-emu-agent device list
   ```

4. Start a session and copy the returned `session_id`.

   ```bash
   uv run android-emu-agent session start --device emulator-5554 --json
   ```

5. Capture an actionable snapshot.

   ```bash
   uv run android-emu-agent ui snapshot <session-id> --format text
   ```

6. Tap an element by ref, then verify the screen again.

   ```bash
   uv run android-emu-agent action tap <session-id> ^a1
   uv run android-emu-agent ui snapshot <session-id> --format text
   ```

7. Stop the session when you are done.

   ```bash
   uv run android-emu-agent session stop <session-id>
   ```

Most commands support `--json` for machine-readable output. JSON responses include a `diagnostic_id`
that also appears as the daemon `x-diagnostic-id` response header.

## Core Concepts

### Daemon and Sessions

The daemon owns device connections and session state. The CLI sends requests over the Unix socket at
`/tmp/android-emu-agent.sock`.

Important paths:

| Path                                               | Purpose                           |
| -------------------------------------------------- | --------------------------------- |
| `/tmp/android-emu-agent.sock`                      | Daemon socket                     |
| `~/.android-emu-agent/daemon.log`                  | Daemon log                        |
| `~/.android-emu-agent/daemon.pid`                  | Daemon PID file                   |
| `~/.android-emu-agent/diagnostics/requests.ndjson` | Request diagnostics               |
| `~/.android-emu-agent/artifacts`                   | Default artifact output root      |
| `~/.android-emu-agent/traces`                      | Default trace archive output root |

### Snapshots, Refs, and Selectors

`ui snapshot` returns generation-scoped refs such as `^a1`. Use refs for the next action whenever
possible. If a ref becomes stale, the daemon may heal it against the latest snapshot and return a
warning; take a fresh snapshot before continuing.

Common target forms:

```text
^a1
text:"Sign in"
text-contains:"Continue"
id:com.example:id/login_btn
desc:"Open navigation"
coords:540,1200
text:"Sign in" || id:com.example:id/login_btn
text:"Continue" enabled:true clickable:true
```

Run this command when an automation planner needs to know which selector forms and device features
are available:

```bash
uv run android-emu-agent device capabilities --session <session-id> --json
```

### Tasks and Evidence

Use `.aea` task scripts or JSON task specs for repeatable flows. Validate task files before running
them:

```bash
uv run android-emu-agent task validate examples/tasks/checkout-smoke.aea
uv run android-emu-agent task run examples/tasks/checkout-smoke.aea --session <session-id> --json
```

Use traces and artifact bundles when a failure needs evidence:

```bash
uv run android-emu-agent trace start <session-id> --label checkout-repro
uv run android-emu-agent trace stop <session-id> --output ./artifacts/checkout-repro.aea-trace.zip
uv run android-emu-agent trace replay ./artifacts/checkout-repro.aea-trace.zip --until-failure
uv run android-emu-agent artifact bundle <session-id> --json
```

## Common Workflows

| Goal                                                    | Start here                                               |
| ------------------------------------------------------- | -------------------------------------------------------- |
| Inspect and act on a screen                             | [Workflow examples](docs/workflow-examples.md)           |
| Write a reusable `.aea` flow                            | [Task script guide](docs/tasks.md)                       |
| Look up exact `.aea` grammar                            | [`.aea` specification](docs/aea-spec.md)                 |
| Look up a command option                                | [Generated CLI reference](docs/reference.md)             |
| Diagnose stale refs, missing elements, or blocked input | `skills/android-emu-agent/references/troubleshooting.md` |
| Use debugger breakpoints, stack, inspect, or logpoints  | `skills/android-emu-agent/references/debugging.md`       |

## Agent Skill

This repo includes an `android-emu-agent` skill under `skills/android-emu-agent/` for agents that
support skill directories. The skill contains command lookup material, workflow templates, recovery
protocols, and safety guidance.

Install or refresh skill symlinks:

```bash
./scripts/dev.sh skills          # all supported local agent targets
./scripts/dev.sh skills codex    # Codex only
./scripts/dev.sh skills claude   # Claude Code only
./scripts/dev.sh skills vscode   # VS Code .agents/skills only
./scripts/dev.sh skills-validate
```

After installation, prime the agent with a concrete target request, for example:

```text
I want to interact with my connected Android emulator.
```

If symlinks are not usable in your environment, copy `skills/android-emu-agent/` into the target
agent skill directory instead.

## Device Support and Safety

The primary target is an emulator or rooted device. Many UI operations also work on non-root devices
when `adb` is connected and `uiautomator2` can attach.

Usually safe on non-root devices:

- UI snapshots, screenshots, and visual grounding.
- Tap, long tap, set text, clear, swipe, scroll, back, home, and recents.
- Wait and expect commands.
- App install, uninstall, launch, force stop, reset, deep link, and intent commands.
- Runtime permission list, grant, and revoke commands.
- Shared-storage file push and pull.
- Reliability profile, events, process, meminfo, gfxinfo, and native perf captures when supported by
  the target.

Root or emulator access is required for:

- `reliability oom-adj`
- `reliability pull anr`
- `reliability pull tombstones`
- `reliability pull dropbox`
- `file find`
- `file list`
- `file app push`
- `file app pull`

Emulator snapshot save and restore commands require an emulator serial such as `emulator-5554`. A
non-emulator serial returns `ERR_NOT_EMULATOR`.

## Debugger Bridge

Debugger commands attach a JDI Bridge sidecar to a debuggable Android app. They require JDK 17+ and
an app built with `android:debuggable=true`, or a userdebug/eng target that allows debugging.

Minimal debugger flow:

```bash
uv run android-emu-agent debug ping <session-id>
uv run android-emu-agent app launch <session-id> com.example.app --wait-debugger
uv run android-emu-agent debug attach --session <session-id> --package com.example.app --keep-suspended
uv run android-emu-agent debug break set com.example.app.MainActivity 42 --session <session-id>
uv run android-emu-agent debug resume --session <session-id>
uv run android-emu-agent debug events --session <session-id>
uv run android-emu-agent debug detach --session <session-id>
```

Build and test the bridge during development:

```bash
./scripts/dev.sh build-bridge
./scripts/dev.sh test-bridge
```

## Troubleshooting

Start with these checks:

```bash
uv run android-emu-agent device list
adb devices
uv run android-emu-agent daemon status --json
```

Common errors:

| Error code                | Meaning                               | Next action                                                  |
| ------------------------- | ------------------------------------- | ------------------------------------------------------------ |
| `ERR_STALE_REF`           | Ref came from an old snapshot         | Re-snapshot and retry with a current ref or selector         |
| `ERR_NOT_FOUND`           | Target element was not found          | Verify the screen, use `--full`, or use another selector     |
| `ERR_BLOCKED_INPUT`       | Dialog, IME, or overlay blocked input | Dismiss the blocker or wait for idle                         |
| `ERR_TIMEOUT`             | Wait or expectation did not complete  | Check the condition or increase `--timeout-ms`               |
| `ERR_SESSION_EXPIRED`     | Session no longer exists              | Start a new session                                          |
| `ERR_DEVICE_OFFLINE`      | Device disconnected                   | Reconnect and rerun `device list`                            |
| `ERR_PERMISSION`          | Operation requires root               | Use a rooted target or skip the root-only command            |
| `ERR_ADB_NOT_FOUND`       | `adb` is not on `PATH`                | Install Android SDK platform-tools and update `PATH`         |
| `ERR_SDK_TOOL_NOT_FOUND`  | Android SDK CLI tool is missing       | Add `emulator` or `avdmanager` to `PATH`                     |
| `ERR_JDK_NOT_FOUND`       | Java runtime is missing               | Install JDK 17+ or set `JAVA_HOME`                           |
| `ERR_TASK_INVALID`        | JSON task spec is invalid             | Fix the task and rerun `task validate`                       |
| `ERR_TASK_SCRIPT_INVALID` | `.aea` script syntax is invalid       | Fix the line reported by the error and rerun `task validate` |
| `ERR_EXPECTATION_FAILED`  | Expected state was not observed       | Inspect actual state, selector, and timeout                  |

For deeper recovery guidance, see `skills/android-emu-agent/references/troubleshooting.md`.

## Documentation

`docs/reference.md` is generated from the live Typer CLI. Regenerate it instead of hand-editing
command tables:

```bash
./scripts/dev.sh docs-gen
./scripts/dev.sh docs
./scripts/dev.sh docs-serve
```

The docs site navigation is defined in `mkdocs.yml`.

## Architecture

```text
CLI client
  -> FastAPI daemon over /tmp/android-emu-agent.sock
    -> session manager, UI snapshotter, actions, waits, expectations, tasks, traces, artifacts
    -> adbutils and uiautomator2 for device I/O
    -> Kotlin JDI Bridge subprocess for debugger flows
      -> Android emulator or device
```

## Development

The `./scripts/dev.sh` helper is the canonical entry point for local development.

| Command                             | Purpose                                                              |
| ----------------------------------- | -------------------------------------------------------------------- |
| `./scripts/dev.sh setup`            | Install dependencies                                                 |
| `./scripts/dev.sh check`            | Run lint, type checks, unit tests, docs checks, and skill validation |
| `./scripts/dev.sh test-unit`        | Run unit tests                                                       |
| `./scripts/dev.sh test-integration` | Run emulator/device-dependent tests                                  |
| `./scripts/dev.sh build-bridge`     | Build the JDI Bridge fat JAR                                         |
| `./scripts/dev.sh test-bridge`      | Run Kotlin bridge tests                                              |
| `./scripts/dev.sh docs-gen`         | Regenerate `docs/reference.md`                                       |
| `./scripts/dev.sh docs`             | Build the MkDocs site into `site/`                                   |
| `./scripts/dev.sh md`               | Format and lint Markdown                                             |
| `./scripts/dev.sh skills-validate`  | Validate bundled agent skill metadata and references                 |

Useful raw commands:

```bash
uv run android-emu-agent --help
uv run android-emu-agent <group> --help
uv run pytest tests/unit -v
uv run ruff check .
uv run mypy src/
```

## License

MIT. See `LICENSE`.
