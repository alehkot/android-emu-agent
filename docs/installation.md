# Installation

Android Emu Agent is a Python package that publishes a single command, `android-emu-agent`.

## Install the CLI

Install it as a standalone tool so the command is always on `PATH`:

```bash
uv tool install android-emu-agent
```

`pipx` works the same way:

```bash
pipx install android-emu-agent
```

To try a command without installing anything, use `uvx`:

```bash
uvx android-emu-agent --help
```

Prefer a persistent install for real work. The CLI starts a background daemon that outlives the
command that spawned it, and `uvx` resolves a fresh temporary environment per invocation, so a
daemon left running can end up tied to an environment that later disappears.

Upgrade with `uv tool upgrade android-emu-agent` or `pipx upgrade android-emu-agent`.

## Requirements

| Requirement                          | Purpose                       |
| ------------------------------------ | ----------------------------- |
| Python 3.11 or later                 | Run the CLI and daemon        |
| Android SDK `platform-tools`         | Provide `adb` device access   |
| Connected Android emulator or device | Provide the automation target |

Some workflows need more tools or access:

| Optional requirement        | Needed for                                          |
| --------------------------- | --------------------------------------------------- |
| Android SDK `emulator`      | Start and stop Android Virtual Devices (AVDs)       |
| Android SDK `cmdline-tools` | Use `avdmanager` and `sdkmanager`                   |
| Root access                 | Read private app files and collect some diagnostics |
| JDK 17 or later             | Use debugger commands                               |

On macOS, add the Android SDK tools to `PATH` with these commands:

```bash
export ANDROID_SDK_ROOT="$HOME/Library/Android/sdk"
export PATH="$ANDROID_SDK_ROOT/platform-tools:$ANDROID_SDK_ROOT/emulator:$ANDROID_SDK_ROOT/cmdline-tools/latest/bin:$PATH"

adb version
emulator -list-avds
avdmanager list avd
```

## Set up your coding agent

Install the bundled Agent Skill so your agent knows how to drive the CLI. See
[Agent Skills](agent-skills.md).

## Complete the first automation loop

Use this procedure to confirm that the CLI, daemon, and target device work together.

In the commands:

- Replace `<avd-name>` with an AVD name.
- Replace `<device-serial>` with the serial shown by `device list`.
- Replace `<session-id>` with the ID returned by `session start`.

1. Connect an Android device or start an emulator.

   Optional: start an existing AVD with Android Emu Agent:

   ```bash
   android-emu-agent emulator list-avds
   android-emu-agent emulator start <avd-name> --wait-boot
   ```

1. Start the daemon.

   ```bash
   android-emu-agent daemon start
   ```

1. Verify that the daemon is running.

   ```bash
   android-emu-agent daemon status --json
   ```

1. Verify that `adb` can see the target device.

   ```bash
   android-emu-agent device list
   ```

1. Start a session and copy the returned `session_id`.

   ```bash
   android-emu-agent session start --device <device-serial> --json
   ```

1. Capture the current screen.

   ```bash
   android-emu-agent ui snapshot <session-id> --format text
   ```

   The snapshot lists actionable elements with refs such as `^g1a1`.

1. Tap an element from the snapshot.

   ```bash
   android-emu-agent action tap <session-id> ^g1a1
   ```

1. Check the result with an expectation.

   ```bash
   android-emu-agent expect exists <session-id> --text "<expected-text>" --timeout-ms 5000
   ```

   Replace `<expected-text>` with text that must appear after the tap. The expectation fails if the
   text does not appear before the timeout.

1. Stop the session when the task is complete.

   ```bash
   android-emu-agent session stop <session-id>
   ```

   This archives an active trace and releases debugger and ADB-forward resources before deleting the
   session.

Most commands support `--json` for machine-readable output. JSON responses include a
`diagnostic_id`. The daemon also returns this value in the `x-diagnostic-id` response header.

## Daemon and file locations

The daemon owns device connections and session state. The CLI sends requests to the daemon through
the Unix socket at `/tmp/android-emu-agent.sock`.

Each session connects commands to one target device. Start a session before you inspect or control
the device, and stop the session when the task is complete.

| Path                                               | Purpose                         |
| -------------------------------------------------- | ------------------------------- |
| `/tmp/android-emu-agent.sock`                      | Daemon socket                   |
| `~/.android-emu-agent/daemon.log`                  | Daemon log                      |
| `~/.android-emu-agent/daemon.pid`                  | Daemon process ID file          |
| `~/.android-emu-agent/diagnostics/requests.ndjson` | Request diagnostics             |
| `~/.android-emu-agent/artifacts`                   | Default artifact directory      |
| `~/.android-emu-agent/traces`                      | Default trace archive directory |

## Debugger prerequisites

Debugger commands need JDK 17 or later and a debuggable app.

The daemon downloads the matching JDI Bridge JAR from the project's GitHub release on first use,
verifies its SHA-256 checksum, and caches it in `~/.android-emu-agent/bridge`. Set
`ANDROID_EMU_AGENT_BRIDGE_JAR` to use a local JAR instead.

## Install from source

Contributors run the CLI from a checkout:

```bash
git clone https://github.com/alehkot/android-emu-agent.git
cd android-emu-agent
uv sync --all-extras
```

Inside the checkout, prefix commands with `uv run` so they use the project environment and pick up
local changes:

```bash
uv run android-emu-agent <command>
```

### When both installs exist

A checkout and an installed release share one daemon socket, so a daemon started by one serves
commands issued by the other. After switching between them, restart the daemon:

```bash
android-emu-agent daemon stop
android-emu-agent daemon start
```

`android-emu-agent daemon status --json` reports the running daemon's `version` so you can tell
which install owns the socket.

## Troubleshooting

Start with these checks:

```bash
android-emu-agent device list
adb devices
android-emu-agent daemon status --json
```

| Error code                   | Meaning                                      | Next action                                                 |
| ---------------------------- | -------------------------------------------- | ----------------------------------------------------------- |
| `ERR_STALE_REF`              | The ref came from an old snapshot            | Take a new snapshot and use a current ref or selector       |
| `ERR_NOT_FOUND`              | The target element was not found             | Inspect the screen with `--full` or use another selector    |
| `ERR_BLOCKED_INPUT`          | A dialog, keyboard, or overlay blocked input | Dismiss the blocker or wait for the device to become idle   |
| `ERR_TIMEOUT`                | A wait or expectation did not complete       | Check the condition or increase `--timeout-ms`              |
| `ERR_SESSION_EXPIRED`        | The session no longer exists                 | Start a new session                                         |
| `ERR_DEVICE_OFFLINE`         | The device disconnected                      | Reconnect the device and rerun `device list`                |
| `ERR_PERMISSION`             | The operation requires root access           | Use a rooted target or skip the operation                   |
| `ERR_ADB_NOT_FOUND`          | `adb` is not on `PATH`                       | Install Android SDK platform-tools and update `PATH`        |
| `ERR_SDK_TOOL_NOT_FOUND`     | An Android SDK command is missing            | Add `emulator` or `avdmanager` to `PATH`                    |
| `ERR_JDK_NOT_FOUND`          | A Java runtime is missing                    | Install JDK 17 or later, or set `JAVA_HOME`                 |
| `ERR_JDK_UNSUPPORTED`        | Java is too old or lacks the JDI module      | Install JDK 17 or later, or update `JAVA_HOME`              |
| `ERR_BRIDGE_DOWNLOAD_FAILED` | The JDI Bridge JAR could not be downloaded   | Check network access, or set `ANDROID_EMU_AGENT_BRIDGE_JAR` |
| `ERR_SKILL_TARGET_EXISTS`    | A skill directory was not created by the CLI | Re-run `skills install --force` or remove the directory     |
| `ERR_INVALID_SNAPSHOT_NAME`  | Snapshot name contains unsupported input     | Use only letters, digits, `.`, `_`, or `-`                  |
| `ERR_INVALID_EMULATOR_PORT`  | Emulator console port is unsupported         | Use an even port from 5554 through 5584                     |
| `ERR_CONSOLE_AUTH`           | Emulator console authentication failed       | Check `.emulator_console_auth_token` permissions/content    |
| `ERR_LOG_FOLLOW_UNSUPPORTED` | Artifact logs cannot stream over this API    | Omit `--follow` or use `adb -s <serial> logcat`             |
| `ERR_INVALID_ARTIFACT_NAME`  | Managed artifact filename is unsafe          | Use a plain filename without directories                    |
| `ERR_AMBIGUOUS_SELECTOR`     | A single-target selector matched many nodes  | Add filters or use a fresh `^ref`                           |
| `ERR_DAEMON_IDENTITY`        | A live PID does not own the daemon socket    | Inspect the daemon log and process before manual cleanup    |
| `ERR_TASK_INVALID`           | A JSON task file is invalid                  | Fix the task and rerun `task validate`                      |
| `ERR_TASK_SCRIPT_INVALID`    | A `.aea` script is invalid                   | Fix the reported line and rerun `task validate`             |
| `ERR_EXPECTATION_FAILED`     | The expected state was not observed          | Inspect the state, selector, and timeout                    |

For more recovery guidance, see the
[troubleshooting reference](https://github.com/alehkot/android-emu-agent/blob/main/skills/android-emu-agent/references/troubleshooting.md).
