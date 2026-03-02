# Android Emu Agent - Gemini Context

This file provides context and instructions for AI agents working in this repository.

## Project Overview

Android Emu Agent is a daemon-first Android automation system designed for LLM-driven control. It
implements an **Observe-Act-Verify** loop:

1. **Observe:** Capture a compact UI snapshot with interactive elements only.
2. **Act:** Issue commands using ephemeral element references (e.g., `^a1`).
3. **Verify:** Re-snapshot to confirm the state change.

### Key Technologies

- **Python 3.11+**: Core implementation with strict typing (`mypy`, `pyright`).
- **uv**: Package and environment management.
- **FastAPI**: Daemon server running over a Unix socket (`/tmp/android-emu-agent.sock`).
- **Typer**: CLI framework for the thin client.
- **adbutils & uiautomator2**: Device communication and UI automation (requires ATX Server on port
  7912).
- **SQLite (aiosqlite)**: Async persistence for sessions and state.
- **Kotlin/JVM**: `jdi-bridge` sidecar for JDWP/JDI debugging.

## Core Concepts

### Ephemeral Refs (`^a1`, `^a2`)

Deterministic handles generated for each UI snapshot. They are stable only within a specific
"generation" of a session. If a ref is used after a new snapshot is taken, the system may report
`ERR_STALE_REF`.

### Locator Bundles

When a ref is created, the system captures multiple fallback strategies (Resource ID, Content
Description, Text, Bounds, Ancestry Hash) to ensure reliable re-resolution if the UI slightly
shifts.

### Snapshot Generations

Each session tracks a `generation` counter that increments with every snapshot, enabling state
tracking and ref validation.

## Architecture

- **CLI Layer (`src/android_emu_agent/cli/`)**: Command parsing and machine-readable output
  (`--json`).
- **Daemon Layer (`src/android_emu_agent/daemon/`)**: Central `DaemonCore` coordinating subsystems.
- **Subsystems**:
  - `device/`: Discovery and app controls.
  - `ui/`: Snapshotting and ref resolution.
  - `actions/`: Action execution and wait logic.
  - `debugger/`: JDI bridge integration.
  - `reliability/`: Forensics and triage helpers.
- **JDI Bridge (`jdi-bridge/`)**: A Kotlin project that enables JVM debugging via JSON-RPC.

## Development Workflow

### Key Commands

```bash
# Setup
uv sync --all-extras

# Run CLI
uv run android-emu-agent --help

# Start Daemon (CLI auto-starts it if needed)
uv run android-emu-agent daemon start

# Full Validation (Lint + Typecheck + Unit Tests)
./scripts/dev.sh check

# Unit Tests
uv run pytest tests/unit

# Integration Tests (Requires Emulator)
uv run pytest tests/integration -m integration

# Build JDI Bridge
cd jdi-bridge && ./gradlew shadowJar

# Regenerate CLI Docs
./scripts/dev.sh docs-gen
```

### Coding Conventions

- **Line Length**: 100 characters (enforced by Ruff).
- **Typing**: Strict typing is required for all new code.
- **Async/Sync**: Subsystem managers and daemon endpoints are `async`. CLI command functions are
  sync wrappers.
- **Errors**: Use `AgentError` with specific error codes and remediation hints.
- **Logging**: Use structured logging via `structlog`.
- **Commits**: Do not create, amend, or rewrite commits unless the user explicitly asks you to do
  so.

## Testing Expectations

- **Unit Tests**: Mock `adbutils`, `uiautomator2`, and `DaemonClient`. Place in `tests/unit/`.
- **Integration Tests**: Only for flows requiring a real device/emulator. Mark with
  `@pytest.mark.integration`.
- **Validation**: Always run `./scripts/dev.sh check` before finalizing changes.

## Agent Skills

The repository includes a specialized agent skill in `skills/android-emu-agent/`.

- **Sync Rule**: If the CLI surface changes, update
  `skills/android-emu-agent/references/command-reference.md` and `docs/reference.md`.
