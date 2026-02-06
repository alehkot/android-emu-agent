# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this
repository.

## Project Overview

Android Emu Agent (`android-emu-agent`) is a CLI + daemon system for LLM-driven Android UI control
on emulators and rooted devices. The architecture follows a daemon-first design where the CLI is a
thin client that communicates with a persistent daemon process via Unix socket.

Core workflow: **Observe** (snapshot UI) → **Act** (execute commands via ephemeral refs) →
**Verify** (re-snapshot).

## Development Commands

```bash
# Setup
uv sync                    # Install dependencies
uv sync --all-extras       # Install with dev dependencies

# Run the CLI
uv run android-emu-agent --help
uv run android-emu-agent <command>

# Testing
uv run pytest tests/unit -v                    # Unit tests only
uv run pytest tests/integration -v -m integration  # Integration tests (requires emulator)
uv run pytest tests/unit/test_snapshotter.py   # Single test file
uv run pytest -k test_ref_resolver             # Single test by name

# Code quality
uv run ruff check .        # Lint
uv run ruff format .       # Format
uv run mypy src/           # Type check with mypy
uv run pyright             # Type check with pyright

# Convenience script (./scripts/dev.sh)
./scripts/dev.sh setup            # Full setup (deps + markdown tooling + git hooks)
./scripts/dev.sh check            # Run all checks (lint + typecheck + unit tests + md lint)
./scripts/dev.sh test             # Run all tests
./scripts/dev.sh test-unit        # Run unit tests only
./scripts/dev.sh test-integration # Run integration tests (requires emulator)
./scripts/dev.sh lint             # Lint only (no format)
./scripts/dev.sh format           # Format code (ruff format + fix)
./scripts/dev.sh typecheck        # Type check only (mypy + pyright)
./scripts/dev.sh daemon           # Start daemon on Unix socket
./scripts/dev.sh hooks            # Install git hooks
./scripts/dev.sh format-md        # Format Markdown
./scripts/dev.sh lint-md          # Lint Markdown
./scripts/dev.sh md               # Format + lint Markdown
./scripts/dev.sh skills [target]  # Symlink skills to agent dirs (codex|claude|all)
```

## Architecture

### Component Hierarchy

The system is organized into these layers:

1. **CLI Layer** (`src/android_emu_agent/cli/`)
   - `main.py`: Typer CLI entry point
   - `commands/`: Command groups (daemon, device, session, ui, action, wait, app, artifact,
     reliability, file, emulator)
   - `daemon_client.py`: Unix socket client for communicating with daemon
   - `utils.py`: Shared CLI helpers and timeout constants

2. **Daemon Layer** (`src/android_emu_agent/daemon/`)
   - `core.py`: Central coordinator (`DaemonCore`) that manages all subsystems
   - `server.py`: FastAPI server that exposes daemon functionality over Unix socket
   - `models.py`: Pydantic request/response models
   - `health.py`: `HealthMonitor` for device/daemon health checks

3. **Core Subsystems** (all instantiated in `DaemonCore`)
   - `device/manager.py`: Device discovery and management (via adbutils)
   - `device/session.py`: Session lifecycle and state (`SessionManager`)
   - `ui/snapshotter.py`: UI hierarchy parsing and snapshot generation
   - `ui/ref_resolver.py`: Ephemeral ref (`^a1`, `^a2`, etc.) to locator bundle mapping
   - `ui/context.py`: `ContextResolver` for activity/package/window/IME/dialog detection
   - `actions/executor.py`: Action dispatch (tap, swipe, text input)
   - `actions/wait.py`: Wait conditions (idle, text, element existence)
   - `actions/selector.py`: Selector types (RefSelector, TextSelector, IDSelector, DescSelector,
     CoordsSelector) for target resolution
   - `artifacts/manager.py`: Debug artifact collection (logs, screenshots, bundles)
   - `files/manager.py`: File transfer operations
   - `reliability/manager.py`: Advanced reliability/debugging commands
   - `db/models.py`: SQLite-based session persistence (via aiosqlite)
   - `validation.py`: Input validation helpers (package names, URIs, emulator checks)
   - `errors.py`: Error definitions with remediation codes

### Key Architectural Concepts

**Ephemeral Refs**: The system generates deterministic element handles like `^a1`, `^a2` for each
snapshot generation. These are stored in `RefResolver` which maintains a mapping of refs →
`LocatorBundle` (containing multiple fallback locator strategies: resource_id, content_desc, text,
bounds, ancestry_hash). Refs are generation-scoped and the system warns if you use a stale ref.

**Snapshot Generations**: Each session maintains a `generation` counter that increments with each UI
snapshot. This enables:

- Stale ref detection (refs from old generations)
- Cleanup of old ref mappings (keeps last 3 generations)
- Debugging and time-travel capabilities

**Locator Bundles**: When a ref is created, multiple locator strategies are captured (ID, text,
content description, bounds, ancestry hash). This provides fallback resolution if the primary
strategy fails.

**Session State**: Sessions persist across daemon restarts via SQLite. Each session tracks:

- Device serial
- Current generation counter
- Last snapshot (in-memory for debugging)

**Communication Flow**: CLI → Unix Socket (`/tmp/android-emu-agent.sock`) → FastAPI daemon →
`DaemonCore` → Subsystem managers → Device (via ATX Server on port 7912)

## Code Patterns

### Style Conventions

- Python 3.11 target version
- Line length is 100 (enforced by ruff)
- Prefer `pathlib` over `os.path` (ruff PTH rules enabled)
- `snake_case` for modules/functions/vars, `PascalCase` for classes, tests as `test_*.py`
- Commit messages follow Conventional Commits: `feat:`, `fix:`, `docs:`, etc.

### Error Handling

All errors are actionable with remediation codes. When adding new errors:

- Define in `src/android_emu_agent/errors.py`
- Include error code (e.g., `ERR_STALE_REF`)
- Provide remediation guidance in the error message

### Logging

Uses `structlog` for structured logging:

```python
import structlog
logger = structlog.get_logger()
logger.info("event_name", key=value, other_key=other_value)
```

### Async/Await

Daemon subsystems are async. Use `async def` for daemon methods, synchronous code for CLI commands.

### Type Checking

Strict type checking is enabled:

- All function signatures must have type annotations
- Use `from __future__ import annotations` for forward references
- Use `TYPE_CHECKING` guard for import-time circular dependencies
- External deps without types (uiautomator2, adbutils) are ignored in mypy overrides

### Pydantic Models

Request/response models in `daemon/models.py` use Pydantic for validation and serialization.

## Testing Strategy

- **Unit tests** (`tests/unit/`): Test individual components in isolation. Mock external
  dependencies (adbutils, uiautomator2).
- **Integration tests** (`tests/integration/`): Require running Android emulator. Mark with
  `@pytest.mark.integration`.
- Use `pytest-asyncio` for testing async code with `@pytest.mark.asyncio`.

## Dependencies

Core runtime:

- `fastapi` + `uvicorn`: Daemon server
- `typer`: CLI framework
- `httpx`: HTTP client for daemon communication over Unix socket
- `adbutils`: ADB protocol communication
- `uiautomator2`: Android UI automation (requires ATX Server on device)
- `lxml`: XML parsing for UI hierarchy
- `aiosqlite`: Async SQLite for session persistence
- `structlog`: Structured logging
- `pydantic`: Data validation

Dev-only:

- `pytest` + `pytest-asyncio` + `pytest-cov`: Testing
- `ruff`: Linting and formatting
- `mypy` + `pyright`: Type checking
- `lxml-stubs`: Type stubs for lxml

## Project Structure Conventions

- `src/android_emu_agent/`: All source code (importable as `android_emu_agent` package)
- `tests/unit/`: Fast, isolated tests (no emulator required)
- `tests/integration/`: Tests requiring real Android emulator
- `scripts/`: Development helper scripts
- `skills/android-emu-agent/`: Agent skill for Claude Code and other agent environments
- `AGENTS.md`: Companion guidelines (coding style, commit conventions, environment tips)

## Agent Skills Sync

- When asked about coding agent skills updates, check `skills/android-emu-agent/` first.
- When adding or modifying CLI commands, update `skills/android-emu-agent/` references (especially
  `references/command-reference.md`) so skills stay aligned with the CLI.

## Important Notes

- Sessions persist across daemon restarts (stored in SQLite)
- Ref maps are kept in memory only (last 3 generations per session)
- Artifacts are written to `~/.android-emu-agent/artifacts` by default
- Integration tests must be marked with `@pytest.mark.integration`
- All daemon communication happens over Unix socket at `/tmp/android-emu-agent.sock`
- Device communication uses ATX Server (uiautomator2) on port 7912
