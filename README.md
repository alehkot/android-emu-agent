# Android Emu Agent

[![PyPI](https://img.shields.io/pypi/v/android-emu-agent)](https://pypi.org/project/android-emu-agent/)
[![Python](https://img.shields.io/pypi/pyversions/android-emu-agent)](https://pypi.org/project/android-emu-agent/)
[![CI](https://github.com/alehkot/android-emu-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/alehkot/android-emu-agent/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://github.com/alehkot/android-emu-agent/blob/main/LICENSE)

Android Emu Agent lets a coding agent inspect and control an Android emulator or device. It provides
a command-line interface (CLI) backed by a local daemon.

The daemon reads the current screen, assigns short refs such as `^g1a1` to UI elements, performs
actions, and can check the result. This gives an agent a repeatable loop:

```text
observe the screen -> act on a known element -> verify the result -> save evidence
```

[Documentation](https://alehkot.github.io/android-emu-agent/) |
[Installation](https://alehkot.github.io/android-emu-agent/installation/) |
[Agent Skills](https://alehkot.github.io/android-emu-agent/agent-skills/) |
[CLI reference](https://alehkot.github.io/android-emu-agent/reference/)

## Quickstart

You need Python 3.11 or later, `adb` on `PATH`, and a connected emulator or device.

Install the CLI:

```bash
uv tool install android-emu-agent    # or: pipx install android-emu-agent
```

Give your coding agent the bundled skill, so it knows how to drive the CLI:

```bash
npx skills add alehkot/android-emu-agent          # Claude Code, Codex, Cursor, and more
android-emu-agent skills install --agent claude   # same thing, without Node
```

Then ask your agent for what you want:

```text
Use Android Emu Agent to open Settings on emulator-5554 and verify that Wi-Fi is enabled.
```

To drive it yourself:

```bash
android-emu-agent daemon start
android-emu-agent device list
android-emu-agent session start --device emulator-5554 --json
android-emu-agent ui snapshot <session-id> --format text
android-emu-agent action tap <session-id> ^g1a1
android-emu-agent expect exists <session-id> --text "Wi-Fi" --timeout-ms 5000
```

`uvx android-emu-agent --help` works for a quick look, but install persistently before running the
daemon: it outlives the command that started it, and `uvx` builds a fresh temporary environment each
time. Full setup, including the guided first loop, is in the
[installation guide](https://alehkot.github.io/android-emu-agent/installation/).

## Use It With a Coding Agent

The repository ships an
[Agent Skill](https://github.com/alehkot/android-emu-agent/tree/main/skills/android-emu-agent) that
teaches an agent how to use Android Emu Agent: which command to reach for, how to run the
observe-act-verify loop, how to recover from a failed action instead of retrying blindly, when to
ask before destructive actions, and how to triage crashes and ANRs.

The skill is included in the Python package, so any install already has it. Pick either installer:

```bash
npx skills add alehkot/android-emu-agent -a claude-code -g
android-emu-agent skills install --agent claude      # ~/.claude/skills
android-emu-agent skills install --agent codex       # ~/.codex/skills
android-emu-agent skills install --agent claude --project   # .claude/skills, shared with your team
android-emu-agent skills install --dir <path>        # any other agent
```

Check what is installed with `android-emu-agent skills list`, and re-run `skills install` after
upgrading the CLI. See the
[Agent Skills guide](https://alehkot.github.io/android-emu-agent/agent-skills/) for the full list of
destinations and example prompts.

## Why Use Android Emu Agent?

Raw `adb` commands and coordinate taps do not describe the current screen. They also do not confirm
that an action produced the expected result. Android Emu Agent adds observable targets, checks, and
failure evidence to Android automation.

| Task                           | Support                                                                 |
| ------------------------------ | ----------------------------------------------------------------------- |
| Inspect the current screen     | Compact UI snapshots with refs such as `^g1a1`                          |
| Tap, type, swipe, and navigate | Refs, text and resource selectors, coordinates, and device capabilities |
| Wait for a state change        | Wait commands and pass/fail expectations                                |
| Repeat an app flow             | JSON task files and human-editable `.aea` scripts                       |
| Investigate a failure          | Screenshots, logs, trace archives, and artifact bundles                 |
| Debug an app below the UI      | Kotlin bridge for Java Debug Interface (JDI) commands                   |
| Integrate with an agent        | JSON output, daemon-backed sessions, and a bundled agent skill          |

## Choose the Next Task

| Goal                                             | Start here                                                                                |
| ------------------------------------------------ | ----------------------------------------------------------------------------------------- |
| Install the CLI and run the first loop           | [Installation](https://alehkot.github.io/android-emu-agent/installation/)                 |
| Set up a coding agent                            | [Agent Skills](https://alehkot.github.io/android-emu-agent/agent-skills/)                 |
| Follow complete workflow examples                | [Workflow examples](https://alehkot.github.io/android-emu-agent/workflow-examples/)       |
| Write a reusable Android flow                    | [Task script guide](https://alehkot.github.io/android-emu-agent/tasks/)                   |
| Look up `.aea` syntax                            | [`.aea` task script specification](https://alehkot.github.io/android-emu-agent/aea-spec/) |
| Find an exact CLI option                         | [Generated CLI reference](https://alehkot.github.io/android-emu-agent/reference/)         |
| Understand sessions, refs, selectors, and traces | [Core Concepts](#core-concepts)                                                           |

## Core Concepts

### Snapshots, Refs, and Selectors

A UI snapshot describes the current screen. The snapshot assigns a ref, such as `^g1a1`, to each
actionable element. In that token, `g1` identifies snapshot generation 1 and `a1` identifies the
first actionable element. Copy the complete ref from the latest snapshot; the element number alone
is not stable across snapshots.

Refs belong to one snapshot generation. If the screen changes, take a new snapshot before you use
another ref. The daemon can sometimes match a stale ref to the latest snapshot, but it returns a
warning when it does this.

You can also select an element by text, resource ID, content description, coordinates, or a combined
selector:

```text
^g1a1
text:"Sign in"
text-contains:"Continue"
id:com.example:id/login_btn
desc:"Open navigation"
coords:540,1200
text:"Sign in" || id:com.example:id/login_btn
text:"Continue" enabled:true clickable:true
```

To see the selector forms and device features available to an automation planner, run
`android-emu-agent device capabilities --session <session-id> --json`.

### Sessions

The daemon owns device connections and session state. The CLI sends requests to the daemon through
the Unix socket at `/tmp/android-emu-agent.sock`. Each session connects commands to one target
device. Start a session before you inspect or control the device, and stop it when the task is
complete. See the [installation guide](https://alehkot.github.io/android-emu-agent/installation/)
for daemon and artifact file locations.

### Tasks, Traces, and Evidence

Use a `.aea` script or JSON task file to repeat a flow, and a trace when you need to reproduce or
investigate a failure:

```bash
android-emu-agent task validate ./checkout-smoke.aea
android-emu-agent task run ./checkout-smoke.aea --session <session-id> --json

android-emu-agent trace start <session-id> --label checkout-repro
android-emu-agent trace stop <session-id> --output ./artifacts/checkout-repro.aea-trace.zip
android-emu-agent trace replay ./artifacts/checkout-repro.aea-trace.zip --until-failure
android-emu-agent artifact bundle <session-id> --json
```

Example scripts live in
[`examples/tasks/`](https://github.com/alehkot/android-emu-agent/tree/main/examples/tasks).

## Check Device Support and Safety

An emulator or rooted device provides the most features. Many UI operations also work on a non-root
device when `adb` is connected and `uiautomator2` can attach.

These operations usually work without root access:

- Capture UI snapshots, screenshots, and visual grounding data.
- Tap, long-tap, enter text, clear text, swipe, scroll, and press system navigation buttons.
- Run wait and expectation commands.
- Install, uninstall, launch, stop, reset, or open a link in an app.
- List, grant, and revoke runtime permissions.
- Push and pull files in shared storage.
- Find and list files in shell-readable storage.
- Push and pull app-private files for debuggable apps via `run-as`.
- Collect supported reliability, process, memory, graphics, and performance data.

These operations require root or emulator access:

- `reliability oom-adj`
- `reliability pull anr`
- `reliability pull tombstones`
- `reliability pull dropbox`
- `file find` and `file list` for paths the shell user cannot read.
- `file app push` and `file app pull` for apps that do not permit `run-as`.

Emulator snapshot save and restore commands require an emulator serial such as `emulator-5554`. A
non-emulator serial returns `ERR_NOT_EMULATOR`.

## Debug an App

Debugger commands use a Kotlin bridge to connect the Java Debug Interface (JDI) to a debuggable
Android app. These commands require JDK 17 or later. They also require an app built with
`android:debuggable=true`, or a `userdebug` or `eng` target that permits debugging.

The daemon downloads the matching bridge JAR on first use and verifies its checksum.

Use this minimal debugger flow:

```bash
android-emu-agent debug ping <session-id>
android-emu-agent app launch <session-id> com.example.app --wait-debugger
android-emu-agent debug attach --session <session-id> --package com.example.app --keep-suspended
android-emu-agent debug break set com.example.app.MainActivity 42 --session <session-id>
android-emu-agent debug resume --session <session-id>
android-emu-agent debug events --session <session-id>
android-emu-agent debug detach --session <session-id>
```

## Troubleshoot a Connection or Action

Start with these checks:

```bash
android-emu-agent device list
adb devices
android-emu-agent daemon status --json
```

Errors report a code and a remediation hint. The
[installation guide](https://alehkot.github.io/android-emu-agent/installation/#troubleshooting)
lists every error code and its next action.

## Understand the Architecture

```text
CLI client
  -> FastAPI daemon over /tmp/android-emu-agent.sock
    -> sessions, snapshots, actions, waits, expectations, tasks, traces, and artifacts
    -> adbutils and uiautomator2 for device communication
    -> Kotlin JDI Bridge process for debugger commands
      -> Android emulator or device
```

The CLI is a thin client. The daemon keeps device connections and session state, then sends device
commands through `adbutils` and `uiautomator2`. Debugger commands use a separate Kotlin process.

## Develop Android Emu Agent

Clone the repository and install all project dependencies:

```bash
git clone https://github.com/alehkot/android-emu-agent.git
cd android-emu-agent
uv sync --all-extras
```

Inside the checkout, run the CLI as `uv run android-emu-agent <command>` so it uses the project
environment and your local changes take precedence over any installed release.

Use `./scripts/dev.sh` as the main entry point for local development.

| Command                             | Purpose                                                              |
| ----------------------------------- | -------------------------------------------------------------------- |
| `./scripts/dev.sh setup`            | Install dependencies                                                 |
| `./scripts/dev.sh check`            | Run format/lint, typing, Python/Kotlin tests, docs, and skill checks |
| `./scripts/dev.sh test-unit`        | Run unit tests                                                       |
| `./scripts/dev.sh test-integration` | Run tests that require an emulator or device                         |
| `./scripts/dev.sh build-bridge`     | Build the JDI Bridge JAR                                             |
| `./scripts/dev.sh test-bridge`      | Run Kotlin bridge tests                                              |
| `./scripts/dev.sh docs-gen`         | Regenerate `docs/reference.md`                                       |
| `./scripts/dev.sh docs`             | Build the documentation site in `site/`                              |
| `./scripts/dev.sh md`               | Format and lint Markdown                                             |
| `./scripts/dev.sh skills`           | Symlink the bundled skill into local agent directories               |
| `./scripts/dev.sh skills-validate`  | Validate the bundled skill metadata and references                   |

`docs/reference.md` is generated from the CLI. Run `./scripts/dev.sh docs-gen` instead of editing
its command tables by hand. The documentation site navigation is defined in `mkdocs.yml`.

## License

Android Emu Agent uses the MIT License. See the
[license](https://github.com/alehkot/android-emu-agent/blob/main/LICENSE).
