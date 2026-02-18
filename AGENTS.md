# Android Emu Agent - AGENTS.md

This file is the coding-agent playbook for this repository.

Use it to make changes that are correct, testable, and aligned with project conventions.

## 1. What This Project Is

Android Emu Agent is a daemon-first Android automation and debugging system:

- CLI is a thin Typer client (`android-emu-agent`).
- Daemon is FastAPI over Unix socket (`/tmp/android-emu-agent.sock`).
- Device I/O uses `adbutils` and `uiautomator2`.
- Debugger flows use a Kotlin JDI Bridge JAR (Java 17+).
- Core loop is observe -> act -> verify using snapshot refs (`^a1`, `^a2`, ...).

## 2. Current Source Layout

- `src/android_emu_agent/cli/`: CLI entrypoint, daemon client, command groups.
- `src/android_emu_agent/daemon/`: request models, API routes, daemon lifecycle, health.
- `src/android_emu_agent/device/`: device discovery/controls and session management.
- `src/android_emu_agent/ui/`: snapshot generation, context, ref resolution.
- `src/android_emu_agent/actions/`: action dispatch, selectors, wait logic.
- `src/android_emu_agent/debugger/`: bridge client/downloader and debug manager.
- `src/android_emu_agent/files/`: host/app file push/pull/list/find.
- `src/android_emu_agent/reliability/`: forensics helpers and root-gated diagnostics.
- `src/android_emu_agent/artifacts/`: screenshots/log bundles and export helpers.
- `src/android_emu_agent/db/`: async persistence.
- `src/android_emu_agent/errors.py`: shared `AgentError` factories.
- `src/android_emu_agent/validation.py`: package/URI validation helpers.
- `jdi-bridge/src/main/kotlin/`: Kotlin JSON-RPC bridge implementation.
- `jdi-bridge/src/test/kotlin/`: bridge tests.
- `tests/unit/`: fast, isolated Python tests.
- `tests/integration/`: emulator/device-dependent tests.
- `skills/android-emu-agent/`: skill docs and references.
- `docs/reference.md`: auto-generated CLI reference.
- `scripts/dev.sh`: canonical dev workflow entrypoint.

## 3. Canonical Commands

Setup:

- `./scripts/dev.sh setup`
- `uv sync --all-extras`

Run/check:

- `uv run android-emu-agent --help`
- `./scripts/dev.sh check` (required after code edits)
- `./scripts/dev.sh test-unit`
- `./scripts/dev.sh test-integration` (requires emulator/device)

Debugger bridge:

- `./scripts/dev.sh build-bridge`
- `./scripts/dev.sh test-bridge`

Docs/skills:

- `./scripts/dev.sh docs-gen` (regenerate `docs/reference.md`)
- `./scripts/dev.sh docs` / `./scripts/dev.sh docs-serve`
- `./scripts/dev.sh md` (format + lint Markdown)
- `./scripts/dev.sh skills codex|claude|all`

Release workflow helper:

- `./scripts/dev.sh bump-version`

## 4. Coding Standards

- Python 3.11+, strict typing (`mypy` strict + `pyright`).
- Ruff for lint/format; max line length 100.
- Prefer `pathlib` over `os.path`.
- Use `snake_case` for functions/vars/modules and `PascalCase` for classes.
- Keep daemon methods async; CLI command functions remain sync wrappers.
- Return actionable failures via `AgentError` with remediation.
- For bridge edits, keep Kotlin code compatible with Java 17 toolchain.

## 5. CLI/API/Bridge Change Contract (Important)

When adding or changing a CLI capability, update all relevant layers:

1. CLI command handler in `src/android_emu_agent/cli/commands/`.
2. Daemon request model in `src/android_emu_agent/daemon/models.py`.
3. Daemon endpoint in `src/android_emu_agent/daemon/server.py`.
4. Manager implementation in the relevant subsystem (`device`, `actions`, `files`, `reliability`,
   `artifacts`, or `debugger`).
5. Unit tests for payload wiring and subsystem behavior.
6. Docs and skills:
   - Run `./scripts/dev.sh docs-gen` for `docs/reference.md`.
   - Update `skills/android-emu-agent/references/command-reference.md`.
   - Update other affected references/examples and README command examples.

If the change touches debugger behavior or bridge RPC:

1. Update Python debug models/manager/client as needed.
2. Update Kotlin bridge command handlers in `jdi-bridge/src/main/kotlin/`.
3. Add or update Kotlin tests in `jdi-bridge/src/test/kotlin/`.
4. Run `./scripts/dev.sh build-bridge` and `./scripts/dev.sh test-bridge`.

Do not ship CLI/API/debugger changes that skip docs or tests sync.

## 6. Testing Expectations

- Put most Python tests in `tests/unit/`.
- Use `@pytest.mark.integration` only for real emulator/device flows.
- For new CLI commands, add command payload tests (mock `DaemonClient`).
- For new manager logic, add behavior tests (mock adb/u2/shell calls).
- For debugger bridge behavior, add Kotlin tests under `jdi-bridge/src/test/kotlin/`.
- Run `./scripts/dev.sh check` before finalizing.

## 7. Output and Error Conventions

- Keep CLI human output concise.
- Keep `--json` stable and machine-friendly.
- Prefer existing response helpers in `src/android_emu_agent/cli/utils.py`.
- When adding failures, include:
  - specific error code,
  - clear message,
  - remediation hint.

## 8. Device and Debug Safety

- Primary target is emulator or rooted device.
- Root-only operations must enforce root checks consistently.
- Emulator-only operations must return `ERR_NOT_EMULATOR` consistently.
- Debug attach flows require a debuggable app and Java 17+ runtime.
- Clean up debug resources (bridge process, ADB forward) on detach/stop paths.
- Validate package names and URIs through shared validators when applicable.

## 9. Docs and Skill Synchronization

- Skill root: `skills/android-emu-agent/SKILL.md`.
- If command surface changes, update:
  - `skills/android-emu-agent/references/command-reference.md`,
  - related references (for example `debugging.md`, `examples.md`, `troubleshooting.md`).
- If asked about skills work, inspect `skills/android-emu-agent/` first.

## 10. Generated Artifacts

- `docs/reference.md` is generated; regenerate instead of hand-editing command tables.
- `site/` and `dist/` are build outputs; do not treat them as source of truth.
- In `jdi-bridge/`, treat `src/` as source and avoid editing generated `bin/` artifacts.

## 11. Commits and PRs

- Conventional commit style: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`.
- PR should include:
  - what changed and why,
  - commands run and results,
  - emulator/root/JDK requirements when relevant,
  - before/after command examples when behavior changes.
