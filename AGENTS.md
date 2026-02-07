# Android Emu Agent - AGENTS.md

This file is the coding-agent playbook for this repository.

Use it to make changes that are correct, testable, and aligned with project conventions.

## 1. What This Project Is

Android Emu Agent is a daemon-first Android automation system:

- CLI is a thin Typer client.
- Daemon is FastAPI over Unix socket (`/tmp/android-emu-agent.sock`).
- Device I/O uses `adbutils` and `uiautomator2`.
- Workflow is observe -> act -> verify using snapshot refs (`^a1`, `^a2`, ...).

## 2. Current Source Layout

- `src/android_emu_agent/cli/`: CLI entrypoint and command groups.
- `src/android_emu_agent/daemon/`: API models, server routes, daemon lifecycle.
- `src/android_emu_agent/device/`: device discovery, app/device controls, sessions.
- `src/android_emu_agent/ui/`: snapshot parsing and ref resolution.
- `src/android_emu_agent/actions/`: action dispatch, selectors, wait logic.
- `src/android_emu_agent/files/`: file transfer logic.
- `src/android_emu_agent/reliability/`: reliability/forensics helpers.
- `src/android_emu_agent/db/`: async persistence.
- `src/android_emu_agent/artifacts/`: screenshots/log bundles.
- `tests/unit/`: fast, isolated tests.
- `tests/integration/`: emulator/device-dependent tests.
- `skills/android-emu-agent/`: agent skill docs/templates.
- `docs/reference.md`: auto-generated CLI reference.
- `scripts/dev.sh`: canonical dev workflow entrypoint.

## 3. Canonical Commands

Setup:

- `uv sync`
- `uv sync --all-extras`

Run/check:

- `uv run android-emu-agent --help`
- `./scripts/dev.sh check` (required after code edits)
- `./scripts/dev.sh test-unit`
- `./scripts/dev.sh test-integration` (when emulator/device is needed)

Docs/skills:

- `./scripts/dev.sh docs-gen` (regenerate `docs/reference.md`)
- `./scripts/dev.sh md` (format + lint Markdown)
- `./scripts/dev.sh skills codex|claude|all`

## 4. Coding Standards

- Python 3.11+, strict typing (`mypy` strict + `pyright`).
- Ruff for lint/format; max line length 100.
- Prefer `pathlib` over `os.path`.
- Use `snake_case` for functions/vars/modules, `PascalCase` for classes.
- Keep daemon methods async; CLI command functions remain sync wrappers.
- Return actionable errors via `AgentError` (with remediation).

## 5. CLI/API Change Contract (Important)

When adding or changing a CLI capability, update all relevant layers:

1. CLI command handler in `src/android_emu_agent/cli/commands/`.
2. Daemon request model in `src/android_emu_agent/daemon/models.py`.
3. Daemon endpoint in `src/android_emu_agent/daemon/server.py`.
4. Device/files/reliability manager implementation in the appropriate subsystem.
5. Unit tests for payload wiring and subsystem behavior.
6. Docs:
   - `./scripts/dev.sh docs-gen` for `docs/reference.md`.
   - Update skill docs in `skills/android-emu-agent/references/` (especially
     `command-reference.md`).
   - Update README examples if user-facing behavior changed.

Do not ship CLI/API changes that skip docs sync.

## 6. Testing Expectations

- Put most tests in `tests/unit/`.
- Use `@pytest.mark.integration` only for true emulator/device flows.
- For new CLI commands, add command payload tests (mock `DaemonClient`).
- For new manager logic, add behavior tests (mock adb/u2/device shell calls).
- Run `./scripts/dev.sh check` before finalizing.

## 7. Output and Error Conventions

- Keep CLI human output concise.
- Keep `--json` stable and machine-friendly.
- Prefer existing response helpers in `cli/utils.py`.
- When adding failures, include:
  - specific error code,
  - clear message,
  - remediation hint.

## 8. Device Reality and Safety

- Primary target is emulator or rooted device.
- Some commands are safe on non-root devices; root-only operations must enforce checks.
- Emulator-only operations must return `ERR_NOT_EMULATOR` behavior consistently.
- Validate package names/URIs through shared validators when applicable.

## 9. Commits and PRs

- Conventional commit style: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`.
- PR should include:
  - what changed and why,
  - commands run and results,
  - emulator/root requirements if relevant,
  - before/after command examples when behavior changes.

## 10. Agent Skill Synchronization

- The local skill lives at `skills/android-emu-agent/SKILL.md`.
- If command surface changes, update:
  - `skills/android-emu-agent/references/command-reference.md`,
  - any affected examples/troubleshooting docs.
- If asked about skills work, inspect `skills/android-emu-agent/` first.
