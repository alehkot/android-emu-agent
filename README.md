# Android Emu Agent

Android Emu Agent lets a coding agent inspect and control an Android emulator or device. It provides
a command-line interface (CLI) backed by a local daemon.

The daemon reads the current screen, assigns short refs such as `^g1a1` to UI elements, performs
actions, and can check the result. This gives an agent a repeatable loop:

```text
observe the screen -> act on a known element -> verify the result -> save evidence
```

[Documentation](https://alehkot.github.io/android-emu-agent/) |
[CLI reference](https://alehkot.github.io/android-emu-agent/reference/) |
[Source](https://github.com/alehkot/android-emu-agent)

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

## Requirements

Install these tools before you start:

| Requirement                          | Purpose                                          |
| ------------------------------------ | ------------------------------------------------ |
| Python 3.11 or later                 | Run the CLI and daemon                           |
| `uv`                                 | Install and run the project from this repository |
| Android SDK `platform-tools`         | Provide `adb` device access                      |
| Connected Android emulator or device | Provide the automation target                    |

Some workflows need more tools or access:

| Optional requirement        | Needed for                                          |
| --------------------------- | --------------------------------------------------- |
| Android SDK `emulator`      | Start and stop Android Virtual Devices (AVDs)       |
| Android SDK `cmdline-tools` | Use `avdmanager` and `sdkmanager`                   |
| Root access                 | Read private app files and collect some diagnostics |
| JDK 17 or later             | Use debugger commands                               |

On macOS, you can add the Android SDK tools to `PATH` with these commands:

```bash
export ANDROID_SDK_ROOT="$HOME/Library/Android/sdk"
export PATH="$ANDROID_SDK_ROOT/platform-tools:$ANDROID_SDK_ROOT/emulator:$ANDROID_SDK_ROOT/cmdline-tools/latest/bin:$PATH"

adb version
emulator -list-avds
avdmanager list avd
```

## Install From Source

Clone the repository and install all project dependencies:

```bash
git clone https://github.com/alehkot/android-emu-agent.git
cd android-emu-agent
uv sync --all-extras
```

In this repository, run the CLI through `uv`:

```bash
uv run android-emu-agent <command>
```

## Complete the First Automation Loop

Use this procedure to confirm that the CLI, daemon, and target device work together.

In the commands:

- Replace `<avd-name>` with an AVD name.
- Replace `<device-serial>` with the serial shown by `device list`.
- Replace `<session-id>` with the ID returned by `session start`.

1. Connect an Android device or start an emulator.

   Optional: start an existing AVD with Android Emu Agent:

   ```bash
   uv run android-emu-agent emulator list-avds
   uv run android-emu-agent emulator start <avd-name> --wait-boot
   ```

2. Start the daemon.

   ```bash
   uv run android-emu-agent daemon start
   ```

3. Verify that the daemon is running.

   ```bash
   uv run android-emu-agent daemon status --json
   ```

4. Verify that `adb` can see the target device.

   ```bash
   uv run android-emu-agent device list
   ```

5. Start a session and copy the returned `session_id`.

   ```bash
   uv run android-emu-agent session start --device <device-serial> --json
   ```

6. Capture the current screen.

   ```bash
   uv run android-emu-agent ui snapshot <session-id> --format text
   ```

   The snapshot lists actionable elements with refs such as `^g1a1`.

7. Tap an element from the snapshot.

   ```bash
   uv run android-emu-agent action tap <session-id> ^g1a1
   ```

8. Check the result with an expectation.

   ```bash
   uv run android-emu-agent expect exists <session-id> --text "<expected-text>" --timeout-ms 5000
   ```

   Replace `<expected-text>` with text that must appear after the tap. The expectation fails if the
   text does not appear before the timeout.

9. Stop the session when the task is complete.

   ```bash
   uv run android-emu-agent session stop <session-id>
   ```

   This archives an active trace and releases debugger and ADB-forward resources before deleting the
   session.

Most commands support `--json` for machine-readable output. JSON responses include a
`diagnostic_id`. The daemon also returns this value in the `x-diagnostic-id` response header.

## Choose the Next Task

| Goal                                             | Start here                                                                                |
| ------------------------------------------------ | ----------------------------------------------------------------------------------------- |
| Follow complete workflow examples                | [Workflow examples](https://alehkot.github.io/android-emu-agent/workflow-examples/)       |
| Write a reusable Android flow                    | [Task script guide](https://alehkot.github.io/android-emu-agent/tasks/)                   |
| Look up `.aea` syntax                            | [`.aea` task script specification](https://alehkot.github.io/android-emu-agent/aea-spec/) |
| Find an exact CLI option                         | [Generated CLI reference](https://alehkot.github.io/android-emu-agent/reference/)         |
| Install the bundled agent skill                  | [Agent Skill](#install-the-agent-skill)                                                   |
| Understand sessions, refs, selectors, and traces | [Core Concepts](#core-concepts)                                                           |

## Core Concepts

### Daemon and Sessions

The daemon owns device connections and session state. The CLI sends requests to the daemon through
the Unix socket at `/tmp/android-emu-agent.sock`.

Each session connects commands to one target device. Start a session before you inspect or control
the device, and stop the session when the task is complete.

Important paths:

| Path                                               | Purpose                         |
| -------------------------------------------------- | ------------------------------- |
| `/tmp/android-emu-agent.sock`                      | Daemon socket                   |
| `~/.android-emu-agent/daemon.log`                  | Daemon log                      |
| `~/.android-emu-agent/daemon.pid`                  | Daemon process ID file          |
| `~/.android-emu-agent/diagnostics/requests.ndjson` | Request diagnostics             |
| `~/.android-emu-agent/artifacts`                   | Default artifact directory      |
| `~/.android-emu-agent/traces`                      | Default trace archive directory |

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

To see the selector forms and device features available to an automation planner, run:

```bash
uv run android-emu-agent device capabilities --session <session-id> --json
```

### Tasks, Traces, and Evidence

Use a `.aea` script or JSON task file to repeat a flow. Validate the task before you run it:

```bash
uv run android-emu-agent task validate examples/tasks/checkout-smoke.aea
uv run android-emu-agent task run examples/tasks/checkout-smoke.aea --session <session-id> --json
```

A trace records the actions and observations in a session. Use a trace or artifact bundle when you
need to reproduce or investigate a failure:

```bash
uv run android-emu-agent trace start <session-id> --label checkout-repro
uv run android-emu-agent trace stop <session-id> --output ./artifacts/checkout-repro.aea-trace.zip
uv run android-emu-agent trace replay ./artifacts/checkout-repro.aea-trace.zip --until-failure
uv run android-emu-agent artifact bundle <session-id> --json
```

## Install the Agent Skill

The repository includes an `android-emu-agent` skill in `skills/android-emu-agent/`. The skill helps
coding agents select commands, follow the observe-act-verify loop, recover from errors, and apply
safety rules.

Install or refresh the skill links for a supported agent:

```bash
./scripts/dev.sh skills          # all supported local agent targets
./scripts/dev.sh skills codex    # Codex only
./scripts/dev.sh skills claude   # Claude Code only
./scripts/dev.sh skills vscode   # VS Code .agents/skills only
./scripts/dev.sh skills-validate
```

After installation, give the agent a specific target and task. For example:

```text
Use Android Emu Agent to open Settings on emulator-5554 and verify that Wi-Fi is enabled.
```

If your environment cannot use symbolic links, copy `skills/android-emu-agent/` into the agent's
skill directory. Python wheels also include the same files under
`android_emu_agent/skills/android-emu-agent/`; locate that installed copy with:

```bash
python -c "from importlib.resources import files; print(files('android_emu_agent') / 'skills' / 'android-emu-agent')"
```

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

Use this minimal debugger flow:

```bash
uv run android-emu-agent debug ping <session-id>
uv run android-emu-agent app launch <session-id> com.example.app --wait-debugger
uv run android-emu-agent debug attach --session <session-id> --package com.example.app --keep-suspended
uv run android-emu-agent debug break set com.example.app.MainActivity 42 --session <session-id>
uv run android-emu-agent debug resume --session <session-id>
uv run android-emu-agent debug events --session <session-id>
uv run android-emu-agent debug detach --session <session-id>
```

During bridge development, build and test the bridge with these commands:

```bash
./scripts/dev.sh build-bridge
./scripts/dev.sh test-bridge
```

## Troubleshoot a Connection or Action

Start with these checks:

```bash
uv run android-emu-agent device list
adb devices
uv run android-emu-agent daemon status --json
```

| Error code                   | Meaning                                      | Next action                                               |
| ---------------------------- | -------------------------------------------- | --------------------------------------------------------- |
| `ERR_STALE_REF`              | The ref came from an old snapshot            | Take a new snapshot and use a current ref or selector     |
| `ERR_NOT_FOUND`              | The target element was not found             | Inspect the screen with `--full` or use another selector  |
| `ERR_BLOCKED_INPUT`          | A dialog, keyboard, or overlay blocked input | Dismiss the blocker or wait for the device to become idle |
| `ERR_TIMEOUT`                | A wait or expectation did not complete       | Check the condition or increase `--timeout-ms`            |
| `ERR_SESSION_EXPIRED`        | The session no longer exists                 | Start a new session                                       |
| `ERR_DEVICE_OFFLINE`         | The device disconnected                      | Reconnect the device and rerun `device list`              |
| `ERR_PERMISSION`             | The operation requires root access           | Use a rooted target or skip the operation                 |
| `ERR_ADB_NOT_FOUND`          | `adb` is not on `PATH`                       | Install Android SDK platform-tools and update `PATH`      |
| `ERR_SDK_TOOL_NOT_FOUND`     | An Android SDK command is missing            | Add `emulator` or `avdmanager` to `PATH`                  |
| `ERR_JDK_NOT_FOUND`          | A Java runtime is missing                    | Install JDK 17 or later, or set `JAVA_HOME`               |
| `ERR_JDK_UNSUPPORTED`        | Java is too old or lacks the JDI module      | Install JDK 17 or later, or update `JAVA_HOME`            |
| `ERR_INVALID_SNAPSHOT_NAME`  | Snapshot name contains unsupported input     | Use only letters, digits, `.`, `_`, or `-`                |
| `ERR_INVALID_EMULATOR_PORT`  | Emulator console port is unsupported         | Use an even port from 5554 through 5584                   |
| `ERR_CONSOLE_AUTH`           | Emulator console authentication failed       | Check `.emulator_console_auth_token` permissions/content  |
| `ERR_LOG_FOLLOW_UNSUPPORTED` | Artifact logs cannot stream over this API    | Omit `--follow` or use `adb -s <serial> logcat`           |
| `ERR_INVALID_ARTIFACT_NAME`  | Managed artifact filename is unsafe          | Use a plain filename without directories                  |
| `ERR_DAEMON_IDENTITY`        | A live PID does not own the daemon socket    | Inspect the daemon log and process before manual cleanup  |
| `ERR_TASK_INVALID`           | A JSON task file is invalid                  | Fix the task and rerun `task validate`                    |
| `ERR_TASK_SCRIPT_INVALID`    | A `.aea` script is invalid                   | Fix the reported line and rerun `task validate`           |
| `ERR_EXPECTATION_FAILED`     | The expected state was not observed          | Inspect the state, selector, and timeout                  |

For more recovery guidance, see the
[troubleshooting reference](https://github.com/alehkot/android-emu-agent/blob/main/skills/android-emu-agent/references/troubleshooting.md).

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
| `./scripts/dev.sh skills-validate`  | Validate the bundled skill metadata and references                   |

Useful direct commands:

```bash
uv run android-emu-agent --help
uv run android-emu-agent <group> --help
uv run pytest tests/unit -v
uv run ruff check .
uv run mypy src/
```

`docs/reference.md` is generated from the CLI. Run `./scripts/dev.sh docs-gen` instead of editing
its command tables by hand. The documentation site navigation is defined in `mkdocs.yml`.

## License

Android Emu Agent uses the MIT License. See the
[license](https://github.com/alehkot/android-emu-agent/blob/main/LICENSE).
