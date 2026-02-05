#!/usr/bin/env bash
# Development helper script

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

ensure_supported_os() {
    local os
    os="$(uname -s)"
    case "$os" in
        Darwin|Linux)
            return 0
            ;;
        *)
            echo "Unsupported OS '$os'. Skills installation is supported on macOS and Linux only."
            return 1
            ;;
    esac
}

install_skills() {
    local target_dir="$1"
    local label="$2"
    local skills_root="$PROJECT_DIR/skills"

    if [ ! -d "$skills_root" ]; then
        echo "Skills directory not found at $skills_root."
        return 1
    fi

    mkdir -p "$target_dir"

    local linked=0
    local skill_path
    for skill_path in "$skills_root"/*; do
        [ -d "$skill_path" ] || continue
        [ -f "$skill_path/SKILL.md" ] || continue

        local skill_name
        skill_name="$(basename "$skill_path")"
        local dest="$target_dir/$skill_name"

        if [ -e "$dest" ] && [ ! -L "$dest" ]; then
            echo "Skipping $label skill '$skill_name': $dest exists and is not a symlink."
            continue
        fi

        ln -sfn "$skill_path" "$dest"
        echo "Linked $label skill '$skill_name' -> $dest"
        linked=$((linked + 1))
    done

    if [ "$linked" -eq 0 ]; then
        echo "No skills linked for $label."
    fi
}

case "${1:-help}" in
    setup)
        echo "Setting up development environment..."
        uv sync --all-extras
        if command -v npm >/dev/null 2>&1; then
            echo "Installing Markdown tooling..."
            npm install
            if git config core.hooksPath .githooks; then
                echo "Git hooks installed."
            else
                echo "Unable to set git hooks path; run './scripts/dev.sh hooks' manually."
            fi
        else
            echo "npm not found; skipping Markdown tooling setup."
        fi
        echo "Done! Run 'uv run android-emu-agent --help' to verify."
        ;;

    test)
        echo "Running tests..."
        uv run pytest "${@:2}"
        ;;

    test-unit)
        echo "Running unit tests..."
        uv run pytest tests/unit -v "${@:2}"
        ;;

    test-integration)
        echo "Running integration tests (requires emulator)..."
        uv run pytest tests/integration -v -m integration "${@:2}"
        ;;

    lint)
        echo "Running linter..."
        uv run ruff check .
        ;;

    format)
        echo "Formatting code..."
        uv run ruff format .
        uv run ruff check --fix .
        ;;

    format-md)
        echo "Formatting Markdown..."
        npm run format:md
        npm run fix:md
        ;;

    lint-md)
        echo "Linting Markdown..."
        npm run lint:md
        ;;

    md)
        echo "Formatting and linting Markdown..."
        npm run format:md
        npm run fix:md
        npm run lint:md
        ;;

    hooks)
        echo "Installing git hooks..."
        if git config core.hooksPath .githooks; then
            echo "Git hooks installed."
        else
            echo "Unable to set git hooks path."
            exit 1
        fi
        ;;

    typecheck)
        echo "Running type checker..."
        uv run mypy src/
        uv run pyright
        ;;

    check)
        echo "Running all checks..."
        uv run ruff check .
        uv run mypy src/
        uv run pyright
        uv run pytest tests/unit -q
        if command -v npm >/dev/null 2>&1; then
            npm run lint:md
        else
            echo "npm not found; skipping Markdown lint."
        fi
        echo "All checks passed!"
        ;;

    daemon)
        echo "Starting daemon..."
        uv run uvicorn android_emu_agent.daemon.server:app --uds /tmp/android-emu-agent.sock
        ;;

    skills)
        ensure_supported_os
        target="${2:-all}"
        codex_root="${CODEX_HOME:-$HOME/.codex}"
        claude_root="${AGENTS_HOME:-${CLAUDE_HOME:-$HOME/.agents}}"

        case "$target" in
            codex)
                echo "Installing skills for Codex..."
                install_skills "$codex_root/skills" "Codex"
                ;;
            claude)
                echo "Installing skills for Claude..."
                install_skills "$claude_root/skills" "Claude"
                ;;
            all)
                echo "Installing skills for Codex and Claude..."
                install_skills "$codex_root/skills" "Codex"
                install_skills "$claude_root/skills" "Claude"
                ;;
            *)
                echo "Unknown skills target '$target'. Use 'codex', 'claude', or 'all'."
                exit 1
                ;;
        esac
        ;;

    skills-codex)
        ensure_supported_os
        echo "Installing skills for Codex..."
        codex_root="${CODEX_HOME:-$HOME/.codex}"
        install_skills "$codex_root/skills" "Codex"
        ;;

    skills-claude)
        ensure_supported_os
        echo "Installing skills for Claude..."
        claude_root="${AGENTS_HOME:-${CLAUDE_HOME:-$HOME/.agents}}"
        install_skills "$claude_root/skills" "Claude"
        ;;

    help|*)
        echo "Development helper script"
        echo ""
        echo "Usage: $0 <command>"
        echo ""
        echo "Commands:"
        echo "  setup            Install dependencies"
        echo "  test             Run all tests"
        echo "  test-unit        Run unit tests only"
        echo "  test-integration Run integration tests (requires emulator)"
        echo "  lint             Run linter"
        echo "  format           Format code"
        echo "  format-md        Format Markdown"
        echo "  lint-md          Lint Markdown"
        echo "  md               Format + lint Markdown"
        echo "  hooks            Install git hooks"
        echo "  typecheck        Run type checkers (mypy + pyright)"
        echo "  check            Run all checks (lint + typecheck + unit tests)"
        echo "  daemon           Start the daemon server"
        echo "  skills [target]  Symlink skills into agent directories (codex|claude|all)"
        echo "  skills-codex     Symlink skills into Codex agent directory"
        echo "  skills-claude    Symlink skills into Claude agent directory"
        echo "  help             Show this help"
        ;;
esac
