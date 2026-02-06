# Android Emu Agent

CLI + daemon for LLM-driven Android UI control — ships with **ready-to-use coding agent skills**.

## Overview

Android Emu Agent automates Android apps using a fast observe-act-verify loop:

1. Observe: capture a compact UI snapshot (interactive elements only)
2. Act: issue commands using ephemeral element refs like `^a1`
3. Verify: re-snapshot when needed

The CLI is a thin client. A long-running daemon handles all device I/O. All commands support
`--json` for machine-readable output, making the tool ideal for agent consumption.

**Highlights:**

- **Daemon-first architecture** — persistent process handles device I/O over Unix socket
- **Ephemeral refs** — deterministic `^a1`-style handles with locator bundle fallbacks
- **Agent skills included** — structured reference docs, workflow templates, and safety guardrails
- **Machine-readable output** — every command supports `--json` for agent pipelines

## Inspiration

Inspired by [agent-browser](https://github.com/vercel-labs/agent-browser), a fast headless browser
automation CLI for AI agents.

## Requirements

- Python 3.11+
- `uv` package manager
- Android SDK with `adb` on PATH
- Android emulator or rooted device (primary target)

## Install

```bash
# Clone the repository
git clone https://github.com/alehkot/android-emu-agent.git
cd android-emu-agent

# Install dependencies
uv sync
```

Inside this repo, prefer `uv run android-emu-agent <command>`.

## Quick Start (2 minutes)

```bash
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

1. Start the daemon: `uv run android-emu-agent daemon start`
2. Confirm a device is visible: `uv run android-emu-agent device list`
3. If needed, start a session explicitly:
   `uv run android-emu-agent session start --device emulator-5554`

## Core Concepts

Sessions

- Sessions tie actions to a specific device. Most commands accept a session id.
- `session start` returns a session id. `session stop` releases it.

Snapshots and refs

- `ui snapshot` returns `^refs` that are stable only for that snapshot.
- If you get `ERR_STALE_REF`, take a new snapshot and use fresh refs.

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

Compact snapshot output includes context and interactive elements only:

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

## Daemon and State

- Socket: `/tmp/android-emu-agent.sock`
- Logs: `~/.android-emu-agent/daemon.log`
- PID file: `~/.android-emu-agent/daemon.pid`

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
```

Emulator snapshots

```bash
uv run android-emu-agent emulator snapshot save emulator-5554 clean
uv run android-emu-agent emulator snapshot restore emulator-5554 clean
```

These commands require an emulator serial (`emulator-5554`). If you pass a non-emulator serial, you
will see `ERR_NOT_EMULATOR`.

## Real Devices (Non-Root)

The project targets emulators and rooted devices, but many commands do not enforce root and can work
on real devices as long as `adb` is connected and uiautomator2 can attach (ATX server on port 7912).
In practice, these are usually safe on non-root devices:

- UI snapshots and screenshots
- Actions (tap, set-text, swipe, scroll, back/home/recents)
- Wait commands
- App list/launch/force-stop/reset/deeplink
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

| Error Code            | Meaning                  | Fix                                             |
| --------------------- | ------------------------ | ----------------------------------------------- |
| `ERR_STALE_REF`       | Ref from an old snapshot | Take a new snapshot                             |
| `ERR_NOT_FOUND`       | Element not found        | Verify screen, use `--full` or a selector       |
| `ERR_BLOCKED_INPUT`   | Dialog/IME blocking      | `wait idle` or `back`                           |
| `ERR_TIMEOUT`         | Wait condition not met   | Increase `--timeout-ms` or check condition      |
| `ERR_DEVICE_OFFLINE`  | Device disconnected      | Reconnect and re-run `device list`              |
| `ERR_SESSION_EXPIRED` | Session is gone          | Start a new session                             |
| `ERR_PERMISSION`      | Root required            | Use a rooted device/emulator                    |
| `ERR_ADB_NOT_FOUND`   | `adb` not on PATH        | Install Android SDK and ensure `adb` is on PATH |
| `ERR_ADB_COMMAND`     | ADB command failed       | Check device connectivity and retry             |

For deeper guidance, see `skills/android-emu-agent/references/troubleshooting.md`.

## CLI Reference

A concise command list lives at `skills/android-emu-agent/references/command-reference.md`.

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
| `./scripts/dev.sh setup`            | Full setup (deps + markdown tooling + git hooks)         |
| `./scripts/dev.sh check`            | Run all checks (lint + typecheck + unit tests + md lint) |
| `./scripts/dev.sh test`             | Run all tests                                            |
| `./scripts/dev.sh test-unit`        | Run unit tests only                                      |
| `./scripts/dev.sh test-integration` | Run integration tests (requires emulator)                |
| `./scripts/dev.sh lint`             | Lint only (ruff check, no format)                        |
| `./scripts/dev.sh format`           | Format code (ruff format + fix)                          |
| `./scripts/dev.sh typecheck`        | Type check (mypy + pyright)                              |
| `./scripts/dev.sh daemon`           | Start daemon on Unix socket                              |
| `./scripts/dev.sh skills`           | Symlink skills to agent dirs (codex, claude, all)        |
| `./scripts/dev.sh hooks`            | Install git hooks                                        |
| `./scripts/dev.sh md`               | Format + lint Markdown                                   |

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
