# Repository Guidelines

## Project Structure & Module Organization

- `src/android_emu_agent/`: core package.
  - `cli/`: CLI entrypoints and command wiring.
  - `daemon/`: FastAPI server and daemon lifecycle.
  - `device/`: device/session management (adb/uiautomator2).
  - `ui/`: snapshotting and ref resolution.
  - `actions/`: action execution and waits.
  - `db/` + `artifacts/`: persistence and artifact handling.
- `tests/`: pytest suites (`unit/` and `integration/`).
- `scripts/dev.sh`: common dev workflows (lint, format, test, typecheck).
- `README.md`, `ARCH.md`, `PRD.md`: usage, architecture, and product context.

## Build, Test, and Development Commands

- `uv sync`: install runtime deps.
- `uv sync --all-extras`: install dev deps (ruff, mypy, pyright, pytest).
- `./scripts/dev.sh setup`: bootstrap dev environment.
- `./scripts/dev.sh lint`: run ruff linting.
- `./scripts/dev.sh format`: format with ruff, then apply fixes.
- `./scripts/dev.sh format-md`: format Markdown.
- `./scripts/dev.sh lint-md`: lint Markdown.
- `./scripts/dev.sh md`: format + lint Markdown.
- `./scripts/dev.sh hooks`: install git hooks.
- `./scripts/dev.sh typecheck`: run mypy + pyright.
- `./scripts/dev.sh test-unit`: unit tests only.
- `./scripts/dev.sh test-integration`: integration tests (requires emulator).
- `./scripts/dev.sh daemon`: run daemon via Uvicorn on `/tmp/android-emu-agent.sock`.
- After code edits, run `./scripts/dev.sh check` to execute lint + typecheck + unit tests.
- Install git hooks with `./scripts/dev.sh hooks` to automatically format/lint Markdown on commit.

## Coding Style & Naming Conventions

- Python 3.11, type hints required (mypy `strict = true`) and checked with pyright.
- Formatting and linting via ruff; line length is 100.
- Prefer `pathlib` (ruff PTH rules are enabled).
- Naming: `snake_case` for modules/functions/vars, `PascalCase` for classes, tests as `test_*.py`.

## Testing Guidelines

- Frameworks: `pytest` + `pytest-asyncio`.
- Tests live under `tests/`; keep new tests in `tests/unit/` unless device/emulator access is
  required.
- Use `@pytest.mark.integration` for emulator/device-dependent tests; run with `-m integration` or
  skip with `-m "not integration"`.
- Coverage is configured for `src/android_emu_agent`; keep new code covered where practical.

## Commit & Pull Request Guidelines

- Commit messages follow a Conventional Commits pattern seen in history: `feat:`, `fix:`, `docs:`
  with short, imperative summaries.
- PRs should include: a clear description, test commands run (and results), and any emulator/device
  requirements or setup steps.
- If behavior changes UI snapshot formats or device actions, include a brief before/after example or
  sample output in the PR body.

## Environment & Configuration Tips

- Requires Android SDK + `adb` and an emulator or rooted device.
- Verify connectivity with `uv run android-emu-agent device list` before running integration tests.
- Prefer `uv run android-emu-agent ...` for CLI usage to ensure the correct environment.

## Local Agent Skills

- `skills/android-emu-agent/SKILL.md`: Android UI automation skill for emulators or rooted devices
  using an observe-act-verify loop. Use for Android automation/testing requests; ensure the daemon
  is running, a device is connected, and a session exists before acting.
- When updating or adding CLI commands, update the corresponding docs in `skills/android-emu-agent/`
  (especially `references/command-reference.md`) so coding agents stay in sync.
- When asked about coding agent skills updates, check `skills/android-emu-agent/` first.
