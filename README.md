# Android Emu Agent

CLI + daemon for LLM-driven Android UI control — ships with **ready-to-use coding agent skills**.

## Overview

Android Emu Agent automates Android apps using a fast observe-act-verify loop:

1. Observe: capture a compact actionable UI snapshot
2. Act: issue commands using ephemeral element refs like `^a1`
3. Verify: re-snapshot when needed

The CLI is a thin client. A long-running daemon handles all device I/O. All commands support
`--json` for machine-readable output, making the tool ideal for agent consumption.

**Highlights:**

- **Daemon-first architecture** — persistent process handles device I/O over Unix socket
- **Framework-aware snapshots** — actionable output works across classic XML Views and modern UI
  frameworks such as Compose and Litho
- **Ref healing** — deterministic `^a1`-style handles with selector-chain rebinding when a newer
  snapshot still contains the same target
- **Diagnostics** — JSON responses and headers include `diagnostic_id` for request-level tracing
- **Agent skills included** — structured reference docs, workflow templates, and safety guardrails
- **Machine-readable output** — every command supports `--json` for agent pipelines

## Inspiration

Inspired by [agent-browser](https://github.com/vercel-labs/agent-browser), a fast headless browser
automation CLI for AI agents.

## Requirements

- Python 3.11+
- `uv` package manager
- Android SDK with `adb`, `emulator`, and ideally `avdmanager` on `PATH`
- Android emulator or rooted device (primary target)
- JDK 17+ (only for debugger commands; set `JAVA_HOME` or have `java` on PATH)

## Install

```bash
# Clone the repository
git clone https://github.com/alehkot/android-emu-agent.git
cd android-emu-agent

# Install dependencies
uv sync
```

Inside this repo, prefer `uv run android-emu-agent <command>`.

## Android SDK CLI Prerequisites

For emulator lifecycle commands, the daemon expects Android SDK command-line tools to be available.
It checks `PATH` first and then common SDK roots derived from `ANDROID_SDK_ROOT` / `ANDROID_HOME`.

Recommended `PATH` entries:

- `platform-tools` for `adb`
- `emulator` for `emulator`
- `cmdline-tools/latest/bin` for `avdmanager` and `sdkmanager`

Example macOS setup:

```bash
export ANDROID_SDK_ROOT="$HOME/Library/Android/sdk"
export PATH="$ANDROID_SDK_ROOT/platform-tools:$ANDROID_SDK_ROOT/emulator:$ANDROID_SDK_ROOT/cmdline-tools/latest/bin:$PATH"

adb version
emulator -list-avds
avdmanager list avd
```

If you only plan to control an already-running device, `adb` is enough. If you want
`android-emu-agent` to boot or manage emulator instances, make `emulator` available too.

## Quick Start (2 minutes)

```bash
# 0. Optional: boot an AVD from the CLI
uv run android-emu-agent emulator list-avds
uv run android-emu-agent emulator start Pixel_8_API_34 --wait-boot

# 1. Start the daemon (optional, CLI will auto-start by default)
uv run android-emu-agent daemon start

# 2. List connected devices
uv run android-emu-agent device list

# 3. Start a session (prints the session id)
uv run android-emu-agent session start --device emulator-5554

# 4. Take a compact snapshot and read refs
uv run android-emu-agent ui snapshot s-abc123 --format text

# 5. Tap an element using a ref
uv run android-emu-agent action tap s-abc123 ^a1

# 6. Stop the session
uv run android-emu-agent session stop s-abc123
```

Most commands accept `--json` for machine-readable output.

Example `--json` output for `session start`:

```json
{
  "status": "done",
  "session_id": "s-abc123",
  "device_serial": "emulator-5554",
  "generation": 0
}
```

## Agent Skills

This repo ships a first-class `android-emu-agent` skill in `skills/android-emu-agent/` for coding
agents that support skills (Claude Code, Codex, and similar environments).

The skill provides:

- **Structured reference docs** — command reference, troubleshooting, error codes
- **Workflow templates** — login flows, navigation patterns, form filling
- **Recovery protocols** — handling stale refs, dialog blockers, idle waits
- **Safety guardrails** — root-required checks, emulator-only safeguards

### Install via dev script (recommended)

```bash
./scripts/dev.sh skills          # Symlink to all supported agents
./scripts/dev.sh skills claude   # Claude Code only
./scripts/dev.sh skills codex    # Codex only
```

### Manual install

**Claude Code:**

```bash
mkdir -p ~/.claude/skills
ln -sfn "$(pwd)/skills/android-emu-agent" ~/.claude/skills/android-emu-agent
```

**Codex:**

```bash
export CODEX_HOME="$HOME/.codex"
mkdir -p "$CODEX_HOME/skills"
ln -sfn "$(pwd)/skills/android-emu-agent" "$CODEX_HOME/skills/android-emu-agent"
```

If symlinks are not an option, copy the directory instead.

### Using the Skill

After installation, the agent should be primed to start a session with your connected device before
you ask for specific actions. Begin with a direct initialization request, for example:

`I want to interact with my connected Android emulator.`

Once the agent has initialized the session, you can proceed with normal requests (snapshots,
tap/type actions, app launches, waits, etc.).

Prerequisites you may need (if the agent reports it cannot connect):

1. If no emulator is running yet, list and boot one: `uv run android-emu-agent emulator list-avds`
   `uv run android-emu-agent emulator start <avd_name> --wait-boot`
2. Start the daemon: `uv run android-emu-agent daemon start`
3. Confirm a device is visible: `uv run android-emu-agent device list`
4. If needed, start a session explicitly:
   `uv run android-emu-agent session start --device emulator-5554`

## Core Concepts

Sessions

- Sessions tie actions to a specific device. Most commands accept a session id.
- `session start` returns a session id. `session stop` releases it.

Snapshots and refs

- `ui snapshot` returns actionable `^refs` that are generation-scoped and optimized for agent use.
- Compact snapshots are designed to work well with classic XML layouts and modern frameworks such as
  Compose and Litho.
- If a ref is stale, the daemon may heal it against the latest snapshot and return a warning. You
  should still take a fresh snapshot before the next action.

Selectors

- `action tap` accepts an `^ref` or a selector.
- `long-tap`, `set-text`, and `clear` require an `^ref`.

Selector examples:

```text
^a1
text:"Sign in"
id:com.example:id/login_btn
desc:"Open navigation"
coords:120,450
```

## Snapshot Format

Compact snapshot output includes context and actionable UI elements only:

```json
{
  "schema_version": 1,
  "session_id": "s-abc123",
  "generation": 42,
  "context": {
    "package": "com.example.app",
    "activity": ".MainActivity",
    "orientation": "PORTRAIT",
    "ime_visible": false
  },
  "elements": [
    {
      "ref": "^a1",
      "role": "button",
      "label": "Sign in",
      "resource_id": "com.example:id/login_btn",
      "bounds": [100, 200, 300, 250],
      "state": { "clickable": true, "enabled": true }
    }
  ]
}
```

Compact mode may proxy descendant text onto an unlabeled clickable container when that makes the
target easier to identify. Use `--full` for the unpruned hierarchy view, or `--raw` for the raw XML
tree.

## Daemon and State

- Socket: `/tmp/android-emu-agent.sock`
- Logs: `~/.android-emu-agent/daemon.log`
- PID file: `~/.android-emu-agent/daemon.pid`
- Request diagnostics: `~/.android-emu-agent/diagnostics/requests.ndjson`

The CLI auto-starts the daemon on first request. Use these to debug:

```bash
uv run android-emu-agent daemon status --json
uv run android-emu-agent daemon stop
uv run android-emu-agent daemon start
```

## Common Workflows

Login flow

```bash
uv run android-emu-agent app launch s-abc123 com.example.app
uv run android-emu-agent wait idle s-abc123 --timeout-ms 5000
uv run android-emu-agent ui snapshot s-abc123 --format text
uv run android-emu-agent action set-text s-abc123 ^a3 "user@example.com"
uv run android-emu-agent action set-text s-abc123 ^a4 "hunter2"
uv run android-emu-agent action tap s-abc123 ^a5
```

When elements are missing

```bash
uv run android-emu-agent ui snapshot s-abc123 --full
uv run android-emu-agent wait idle s-abc123 --timeout-ms 3000
uv run android-emu-agent ui snapshot s-abc123
```

Visual debug

```bash
uv run android-emu-agent ui screenshot --device emulator-5554 --pull --output ./screen.png
uv run android-emu-agent artifact bundle s-abc123
uv run android-emu-agent artifact logs --session s-abc123 --app com.example.app --type errors --since "10m ago"
```

App debug helpers

```bash
uv run android-emu-agent app current --session s-abc123
uv run android-emu-agent app task-stack --session s-abc123
uv run android-emu-agent app resolve-intent --session s-abc123 --action android.intent.action.VIEW --data "https://example.com/deep"
uv run android-emu-agent reliability process com.example.app --device emulator-5554
uv run android-emu-agent reliability meminfo com.example.app --device emulator-5554
uv run android-emu-agent reliability gfxinfo com.example.app --device emulator-5554
```

Debugger (JDI Bridge)

Attach a JDWP debugger to a running Android app's JVM. This requires JDK 17+ and a debuggable app
(built with `android:debuggable=true` or running on a userdebug/eng device).

```bash
# Verify bridge startup and JSON-RPC health
uv run android-emu-agent debug ping s-abc123

# Launch the app in wait-for-debugger mode
uv run android-emu-agent app launch s-abc123 com.example.app --wait-debugger

# Attach the debugger (finds PID, sets up ADB forward, connects via JDI)
uv run android-emu-agent debug attach --session s-abc123 --package com.example.app

# Keep the VM suspended after attach (useful with app launch --wait-debugger)
uv run android-emu-agent debug attach --session s-abc123 --package com.example.app --keep-suspended

# If multiple debuggable processes exist, pick one explicitly
uv run android-emu-agent debug attach --session s-abc123 --package com.example.app --process com.example.app:remote

# Check debug session status (VM name, version, thread count)
uv run android-emu-agent debug status --session s-abc123

# Set/list/remove breakpoints
uv run android-emu-agent debug break set com.example.app.MainActivity 42 --session s-abc123
uv run android-emu-agent debug break list --session s-abc123
uv run android-emu-agent debug break remove 1 --session s-abc123

# List threads (default skips daemon threads; --all includes them)
uv run android-emu-agent debug threads --session s-abc123
uv run android-emu-agent debug threads --session s-abc123 --all

# Drain debugger event queue (breakpoint hits/resolutions, disconnect events)
uv run android-emu-agent debug events --session s-abc123

# Stack and variable inspection on suspended threads
uv run android-emu-agent debug stack --session s-abc123 --thread main --max-frames 10
uv run android-emu-agent debug inspect savedInstanceState --session s-abc123 --thread main --frame 0 --depth 1
uv run android-emu-agent debug eval savedInstanceState.toString() --session s-abc123 --thread main --frame 0

# Optional: load/clear ProGuard-R8 mapping for deobfuscated names in stack/inspect output
uv run android-emu-agent debug mapping load ./mapping.txt --session s-abc123
uv run android-emu-agent debug mapping clear --session s-abc123

# Step execution (observe-act-verify): returns new location + locals atomically
uv run android-emu-agent debug step-over --session s-abc123 --thread main
uv run android-emu-agent debug step-into --session s-abc123 --thread main
uv run android-emu-agent debug step-out --session s-abc123 --thread main

# Resume one thread or all threads
uv run android-emu-agent debug resume --session s-abc123 --thread main
uv run android-emu-agent debug resume --session s-abc123

# Detach when done (cleans up ADB forward and bridge process)
uv run android-emu-agent debug detach --session s-abc123
```

Step commands default to a 10s timeout (`--timeout-seconds`) and return actionable timeout payloads
when a step cannot complete. If the main thread has been suspended for too long, responses include
an ANR warning so you can resume before Android's ANR threshold. When a mapping file is loaded,
stack class/method names and inspect field names are deobfuscated. Mapping state is per attached
bridge instance and clears on detach.

Example debugger workflows

Launch suspended, attach, set breakpoints, then resume

```bash
# Start app in wait-for-debugger mode (process is paused before app code runs)
uv run android-emu-agent app launch s-abc123 com.example.app --wait-debugger

# Attach and keep VM suspended (do not auto-resume on attach)
uv run android-emu-agent debug attach --session s-abc123 --package com.example.app --keep-suspended

# Set breakpoints while execution is still paused
uv run android-emu-agent debug break set com.example.app.MainActivity 42 --session s-abc123
uv run android-emu-agent debug break set com.example.checkout.CartViewModel 118 --session s-abc123 --condition "cart.total > 10000"

# Optional: verify configured breakpoints before continuing
uv run android-emu-agent debug break list --session s-abc123

# Resume only after breakpoints are in place
uv run android-emu-agent debug resume --session s-abc123
```

Conditional breakpoint for state-specific bugs

```bash
# Attach
uv run android-emu-agent app launch s-abc123 com.example.app --wait-debugger
uv run android-emu-agent debug attach --session s-abc123 --package com.example.app

# Stop only when cart total crosses threshold
uv run android-emu-agent debug break set com.example.checkout.CartViewModel 118 --session s-abc123 --condition "cart.total > 10000"
uv run android-emu-agent debug resume --session s-abc123

# Wait for hit, then inspect state
uv run android-emu-agent debug events --session s-abc123
uv run android-emu-agent debug stack --session s-abc123 --thread main --max-frames 15
uv run android-emu-agent debug inspect cart.total --session s-abc123 --thread main --frame 0
uv run android-emu-agent debug resume --session s-abc123
```

Condition syntax supports value paths, literals (`null`, booleans, numbers, strings), boolean
operators (`!`, `&&`, `||`), comparisons (`==`, `!=`, `>`, `>=`, `<`, `<=`), and parentheses.
Malformed condition syntax fails fast during `debug break set`. Runtime evaluation failures emit
`breakpoint_condition_error` and auto-resume.

Non-suspending logpoint trace

```bash
# Attach and set a logpoint (does not suspend thread)
uv run android-emu-agent debug attach --session s-abc123 --package com.example.app
uv run android-emu-agent debug break set com.example.login.LoginViewModel 87 --session s-abc123 --log-message "attempt={hitCount} user={username} locked={isLocked}" --capture-stack --stack-max-frames 8

# Keep app running; hits are buffered with timestamps (and optional stack)
uv run android-emu-agent debug resume --session s-abc123
uv run android-emu-agent debug break hits --session s-abc123 --limit 100
uv run android-emu-agent debug break hits --session s-abc123 --breakpoint-id 1

# Clean up
uv run android-emu-agent debug break list --session s-abc123
uv run android-emu-agent debug break remove 1 --session s-abc123
```

Buffered logpoint example use cases

```bash
# 1) High-frequency callback tracing without pausing app execution
uv run android-emu-agent debug break set com.example.sync.SyncWorker 214 --session s-abc123 --log-message "sync run={hitCount} state={state}" --capture-stack --stack-max-frames 6
uv run android-emu-agent debug resume --session s-abc123
uv run android-emu-agent debug break hits --session s-abc123 --breakpoint-id 1 --limit 50

# 2) Investigate only hits after a known incident timestamp (epoch ms)
uv run android-emu-agent debug break hits --session s-abc123 --since-timestamp-ms 1735689600000 --limit 200

# 3) Compare two non-suspending logpoints independently
uv run android-emu-agent debug break set com.example.login.LoginViewModel 87 --session s-abc123 --log-message "attempt={hitCount} user={username}"
uv run android-emu-agent debug break set com.example.session.SessionStore 55 --session s-abc123 --log-message "refresh={hitCount} token={tokenState}"
uv run android-emu-agent debug break hits --session s-abc123 --breakpoint-id 1 --limit 100
uv run android-emu-agent debug break hits --session s-abc123 --breakpoint-id 2 --limit 100
```

Crash triage with exception breakpoints

```bash
# Attach and break on uncaught exceptions
uv run android-emu-agent app launch s-abc123 com.example.app --wait-debugger
uv run android-emu-agent debug attach --session s-abc123 --package com.example.app
uv run android-emu-agent debug break-exception set --session s-abc123 --class '*' --no-caught --uncaught

# Reproduce crash path, then inspect exception event
uv run android-emu-agent debug resume --session s-abc123
uv run android-emu-agent debug events --session s-abc123
uv run android-emu-agent debug stack --session s-abc123 --thread main --max-frames 20

# Optional: narrow to one exception class after first capture
uv run android-emu-agent debug break-exception remove 1 --session s-abc123
uv run android-emu-agent debug break-exception set --session s-abc123 --class java.lang.NullPointerException --caught --uncaught
```

Under the hood, the daemon spawns a **JDI Bridge** sidecar (a Kotlin/JVM subprocess in
`jdi-bridge/`) that speaks JSON-RPC over stdin/stdout. The bridge connects to the target app via
JDWP and monitors for VM disconnect events. Build the bridge JAR with:

```bash
cd jdi-bridge && ./gradlew shadowJar
```

Emulator lifecycle and snapshots

```bash
uv run android-emu-agent emulator list-avds
uv run android-emu-agent emulator start Pixel_8_API_34 --snapshot clean --no-snapshot-save
uv run android-emu-agent emulator stop emulator-5554
uv run android-emu-agent emulator snapshot save emulator-5554 clean
uv run android-emu-agent emulator snapshot restore emulator-5554 clean
```

These commands require an emulator serial (`emulator-5554`). If you pass a non-emulator serial, you
will see `ERR_NOT_EMULATOR`. Snapshot restore restarts the emulator by default so the loaded
snapshot becomes the active runtime state again. Use `--no-restart` if you explicitly want the old
live-load behavior. Create AVD definitions ahead of time with Android Studio or `avdmanager`.

## Real Devices (Non-Root)

The project targets emulators and rooted devices, but many commands do not enforce root and can work
on real devices as long as `adb` is connected and uiautomator2 can attach (ATX server on port 7912).
In practice, these are usually safe on non-root devices:

- UI snapshots and screenshots
- Actions (tap, set-text, swipe, scroll, back/home/recents)
- Wait commands
- App list/install/uninstall/launch/intent/force-stop/reset/deeplink
- File `push` and `pull` to shared storage

Emulator-only commands are `emulator snapshot save|restore`. Root-required commands are listed
below.

## Root-Required Operations

The following require a rooted device or emulator with root access:

- `reliability oom-adj`
- `reliability pull anr`
- `reliability pull tombstones`
- `reliability pull dropbox`
- `file find`
- `file list`
- `file app push`
- `file app pull`

If root is missing, you will see `ERR_PERMISSION`.

## Artifacts

Artifacts are written to `~/.android-emu-agent/artifacts` by default.

- Reliability outputs: `~/.android-emu-agent/artifacts/reliability`
- File transfers: `~/.android-emu-agent/artifacts/files`

## Troubleshooting

Quick checks

```bash
uv run android-emu-agent device list
adb devices
uv run android-emu-agent daemon status --json
```

Common errors

| Error Code               | Meaning                  | Fix                                             |
| ------------------------ | ------------------------ | ----------------------------------------------- |
| `ERR_STALE_REF`          | Ref from an old snapshot | Re-snapshot; if auto-healed, use warning as cue |
| `ERR_NOT_FOUND`          | Element not found        | Verify screen, use `--full` or a selector       |
| `ERR_BLOCKED_INPUT`      | Dialog/IME blocking      | `wait idle` or `back`                           |
| `ERR_TIMEOUT`            | Wait condition not met   | Increase `--timeout-ms` or check condition      |
| `ERR_DEVICE_OFFLINE`     | Device disconnected      | Reconnect and re-run `device list`              |
| `ERR_SESSION_EXPIRED`    | Session is gone          | Start a new session                             |
| `ERR_PERMISSION`         | Root required            | Use a rooted device/emulator                    |
| `ERR_ADB_NOT_FOUND`      | `adb` not on PATH        | Install Android SDK and ensure `adb` is on PATH |
| `ERR_SDK_TOOL_NOT_FOUND` | SDK CLI tool missing     | Add `emulator` / `avdmanager` to PATH           |
| `ERR_ADB_COMMAND`        | ADB command failed       | Check device connectivity and retry             |
| `ERR_ALREADY_ATTACHED`   | Debug session exists     | Detach first with `debug detach`                |
| `ERR_DEBUG_NOT_ATTACHED` | No debug session         | Attach first with `debug attach`                |
| `ERR_JDK_NOT_FOUND`      | Java not found           | Install JDK 17+ or set `JAVA_HOME`              |
| `ERR_VM_DISCONNECTED`    | Target VM exited         | Re-launch the app and re-attach                 |

For deeper guidance, see `skills/android-emu-agent/references/troubleshooting.md`.

Every JSON response also includes a `diagnostic_id`, and the same ID is returned as the
`x-diagnostic-id` header for correlation with daemon request logs.

## CLI Reference

Full auto-generated CLI reference is available at [`docs/reference.md`](docs/reference.md).

To regenerate or browse the docs locally:

```bash
./scripts/dev.sh docs-gen      # Regenerate docs/reference.md from CLI
./scripts/dev.sh docs          # Build to site/
./scripts/dev.sh docs-serve    # Serve at http://127.0.0.1:8000
```

A concise command list also lives at `skills/android-emu-agent/references/command-reference.md`.

If you prefer an interactive guide:

```bash
uv run android-emu-agent --help
uv run android-emu-agent <group> --help
```

## Architecture

```text
┌─────────────────┐     Unix Socket      ┌──────────────────────────────────┐
│                 │  ◄────────────────►  │            Daemon                │
│   CLI Client    │                      │  ┌────────────────────────────┐  │
│                 │                      │  │     Device Manager         │  │
└─────────────────┘                      │  │  (adbutils, uiautomator2)  │  │
                                         │  └────────────────────────────┘  │
                                         │  ┌────────────────────────────┐  │
                                         │  │    Session Manager         │  │
                                         │  │  (refs, state, SQLite)     │  │
                                         │  └────────────────────────────┘  │
                                         │  ┌────────────────────────────┐  │
                                         │  │    UI Snapshotter          │  │
                                         │  │  (lxml, filtering)         │  │
                                         │  └────────────────────────────┘  │
                                         │  ┌────────────────────────────┐  │
                                         │  │    Debug Manager           │  │
                                         │  │  (JDI Bridge, JDWP)       │──┼──► JDI Bridge
                                         │  └────────────────────────────┘  │    (Kotlin subprocess)
                                         └──────────────────────────────────┘
                                                         │
                                                         ▼
                                         ┌──────────────────────────────────┐
                                         │     Android Device/Emulator      │
                                         │  (ATX Server on port 7912)       │
                                         └──────────────────────────────────┘
```

## Development Scripts

The `./scripts/dev.sh` helper centralizes common development tasks. Make it executable with
`chmod +x scripts/dev.sh` if needed.

| Command                             | Description                                              |
| ----------------------------------- | -------------------------------------------------------- |
| `./scripts/dev.sh setup`            | Install dependencies                                     |
| `./scripts/dev.sh check`            | Run all checks (lint + typecheck + unit tests + docs)    |
| `./scripts/dev.sh test`             | Run all tests                                            |
| `./scripts/dev.sh test-unit`        | Run unit tests only                                      |
| `./scripts/dev.sh test-integration` | Run integration tests (requires emulator)                |
| `./scripts/dev.sh build-bridge`     | Build the JDI Bridge fat JAR (jdi-bridge/)               |
| `./scripts/dev.sh test-bridge`      | Run JDI Bridge Kotlin tests                              |
| `./scripts/dev.sh lint`             | Run linter                                               |
| `./scripts/dev.sh format`           | Format code                                              |
| `./scripts/dev.sh format-md`        | Format Markdown                                          |
| `./scripts/dev.sh lint-md`          | Lint Markdown                                            |
| `./scripts/dev.sh md`               | Format + lint Markdown                                   |
| `./scripts/dev.sh hooks`            | Install git hooks                                        |
| `./scripts/dev.sh typecheck`        | Run type checkers (mypy + pyright)                       |
| `./scripts/dev.sh daemon`           | Start the daemon server                                  |
| `./scripts/dev.sh bump-version`     | Interactively bump version, refresh lock, optionally tag |
| `./scripts/dev.sh docs`             | Build documentation (mkdocs)                             |
| `./scripts/dev.sh docs-serve`       | Serve documentation locally                              |
| `./scripts/dev.sh docs-gen`         | Regenerate CLI reference from Typer app                  |
| `./scripts/dev.sh skills [target]`  | Symlink skills into agent directories (codex/claude/all) |
| `./scripts/dev.sh skills-codex`     | Symlink skills into Codex agent directory                |
| `./scripts/dev.sh skills-claude`    | Symlink skills into Claude agent directory               |

### Raw `uv run` commands

```bash
# Install with dev dependencies
uv sync --all-extras

# Run tests
uv run pytest tests/unit -v

# Run linter
uv run ruff check .

# Format code
uv run ruff format .

# Type check
uv run mypy src/
```

## License

MIT. See `LICENSE`.
