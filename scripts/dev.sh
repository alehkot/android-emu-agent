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

read_project_version() {
    awk '
        BEGIN { in_project = 0 }
        /^\[project\][[:space:]]*$/ { in_project = 1; next }
        /^\[[^]]+\][[:space:]]*$/ { in_project = 0 }
        in_project && /^[[:space:]]*version[[:space:]]*=/ {
            line = $0
            sub(/^[^"]*"/, "", line)
            sub(/".*$/, "", line)
            print line
            exit 0
        }
    ' pyproject.toml
}

is_semver() {
    [[ "$1" =~ ^[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.-]+)?(\+[0-9A-Za-z.-]+)?$ ]]
}

calculate_next_version() {
    local current_version="$1"
    local bump_type="$2"

    if ! [[ "$current_version" =~ ^([0-9]+)\.([0-9]+)\.([0-9]+)$ ]]; then
        return 1
    fi

    local major="${BASH_REMATCH[1]}"
    local minor="${BASH_REMATCH[2]}"
    local patch="${BASH_REMATCH[3]}"

    case "$bump_type" in
        patch)
            printf "%s.%s.%s\n" "$major" "$minor" "$((patch + 1))"
            ;;
        minor)
            printf "%s.%s.0\n" "$major" "$((minor + 1))"
            ;;
        major)
            printf "%s.0.0\n" "$((major + 1))"
            ;;
        *)
            return 1
            ;;
    esac
}

render_pyproject_with_version() {
    local new_version="$1"
    local output_file="$2"

    awk -v version="$new_version" '
        BEGIN { in_project = 0; updated = 0 }
        /^\[project\][[:space:]]*$/ { in_project = 1; print; next }
        /^\[[^]]+\][[:space:]]*$/ { in_project = 0 }
        in_project && !updated && /^[[:space:]]*version[[:space:]]*=/ {
            sub(/"[^"]*"/, "\"" version "\"")
            updated = 1
        }
        { print }
        END {
            if (!updated) {
                exit 1
            }
        }
    ' pyproject.toml > "$output_file"
}

render_init_with_version() {
    local new_version="$1"
    local output_file="$2"

    awk -v version="$new_version" '
        BEGIN { updated = 0 }
        !updated && /^[[:space:]]*__version__[[:space:]]*=/ {
            sub(/"[^"]*"/, "\"" version "\"")
            updated = 1
        }
        { print }
        END {
            if (!updated) {
                exit 1
            }
        }
    ' src/android_emu_agent/__init__.py > "$output_file"
}

maybe_update_uv_lock() {
    if [ ! -f uv.lock ]; then
        return 0
    fi

    local lock_confirm
    read -r -p "Update uv.lock now with 'uv lock'? [Y/n]: " lock_confirm
    case "$lock_confirm" in
        n|N|no|NO)
            echo "Skipped uv.lock update."
            return 0
            ;;
    esac

    echo "Updating uv.lock..."
    if uv lock; then
        echo "Updated uv.lock."
        return 0
    fi

    echo "Failed to update uv.lock. Run 'uv lock' manually."
    return 1
}

bump_version() {
    local current_version
    current_version="$(read_project_version)"

    if [ -z "$current_version" ]; then
        echo "Unable to read version from pyproject.toml [project].version."
        return 1
    fi

    local patch_version=""
    local minor_version=""
    local major_version=""

    if [[ "$current_version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        patch_version="$(calculate_next_version "$current_version" patch)"
        minor_version="$(calculate_next_version "$current_version" minor)"
        major_version="$(calculate_next_version "$current_version" major)"
    fi

    echo "Current version: $current_version"

    local choice=""
    local new_version=""
    while :; do
        if [ -n "$patch_version" ]; then
            echo ""
            echo "Select bump type:"
            echo "  1) patch -> $patch_version"
            echo "  2) minor -> $minor_version"
            echo "  3) major -> $major_version"
            echo "  4) custom"
            echo "  5) cancel"
            read -r -p "Choice [1-5]: " choice
        else
            echo "Current version is not a plain x.y.z semver."
            choice="4"
        fi

        case "$choice" in
            ""|1|patch|p|P)
                if [ -z "$patch_version" ]; then
                    echo "Patch/minor/major suggestions require an x.y.z current version."
                    continue
                fi
                new_version="$patch_version"
                ;;
            2|minor|m|M)
                if [ -z "$minor_version" ]; then
                    echo "Patch/minor/major suggestions require an x.y.z current version."
                    continue
                fi
                new_version="$minor_version"
                ;;
            3|major)
                if [ -z "$major_version" ]; then
                    echo "Patch/minor/major suggestions require an x.y.z current version."
                    continue
                fi
                new_version="$major_version"
                ;;
            4|custom|c|C)
                local suggested_version="$patch_version"
                if [ -z "$suggested_version" ]; then
                    suggested_version="$current_version"
                fi
                while :; do
                    read -r -p "Enter new version [$suggested_version]: " new_version
                    new_version="${new_version:-$suggested_version}"
                    if is_semver "$new_version"; then
                        break
                    fi
                    echo "Invalid semantic version. Expected format: x.y.z[-prerelease][+build]."
                done
                ;;
            5|cancel|q|quit)
                echo "Version bump cancelled."
                return 0
                ;;
            *)
                echo "Invalid choice '$choice'."
                continue
                ;;
        esac

        if ! is_semver "$new_version"; then
            echo "Version '$new_version' is not a valid semantic version."
            continue
        fi

        if [ "$new_version" = "$current_version" ]; then
            echo "Version unchanged ($current_version)."
            return 0
        fi

        local confirm
        read -r -p "Bump version from $current_version to $new_version? [y/N]: " confirm
        case "$confirm" in
            y|Y|yes|YES)
                break
                ;;
            *)
                echo "No changes made."
                return 0
                ;;
        esac
    done

    local pyproject_tmp
    local init_tmp
    local pyproject_backup
    local init_backup
    pyproject_tmp="$(mktemp)"
    init_tmp="$(mktemp)"
    pyproject_backup="$(mktemp)"
    init_backup="$(mktemp)"

    cp pyproject.toml "$pyproject_backup"
    cp src/android_emu_agent/__init__.py "$init_backup"

    if ! render_pyproject_with_version "$new_version" "$pyproject_tmp"; then
        rm -f "$pyproject_tmp" "$init_tmp" "$pyproject_backup" "$init_backup"
        echo "Failed to prepare updated pyproject.toml."
        return 1
    fi

    if ! render_init_with_version "$new_version" "$init_tmp"; then
        rm -f "$pyproject_tmp" "$init_tmp" "$pyproject_backup" "$init_backup"
        echo "Failed to prepare updated __init__.py."
        return 1
    fi

    if ! mv "$pyproject_tmp" pyproject.toml || ! mv "$init_tmp" src/android_emu_agent/__init__.py; then
        cp "$pyproject_backup" pyproject.toml
        cp "$init_backup" src/android_emu_agent/__init__.py
        rm -f "$pyproject_tmp" "$init_tmp" "$pyproject_backup" "$init_backup"
        echo "Failed to write version updates. Original files restored."
        return 1
    fi

    rm -f "$pyproject_backup" "$init_backup"

    echo "Version bumped: $current_version -> $new_version"
    echo "Updated files:"
    echo "  pyproject.toml"
    echo "  src/android_emu_agent/__init__.py"

    if ! maybe_update_uv_lock; then
        return 1
    fi

    local tag="v$new_version"
    local tag_confirm
    read -r -p "Create git tag $tag? [y/N]: " tag_confirm
    case "$tag_confirm" in
        y|Y|yes|YES)
            if git tag "$tag"; then
                echo "Created git tag: $tag"
            else
                echo "Failed to create git tag $tag."
                return 1
            fi
            ;;
        *)
            echo "Skipped git tag creation."
            ;;
    esac
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
        uv run mkdocs build --strict
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

    bump-version)
        bump_version
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

    docs)
        echo "Building docs..."
        uv run mkdocs build --strict
        ;;

    docs-serve)
        echo "Serving docs locally..."
        uv run mkdocs serve
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
        echo "  check            Run all checks (lint + typecheck + unit tests + docs)"
        echo "  daemon           Start the daemon server"
        echo "  bump-version     Interactively bump package version (patch/minor/major/custom),"
        echo "                   optionally refresh uv.lock, and optionally create a git tag"
        echo "  docs             Build documentation (mkdocs)"
        echo "  docs-serve       Serve documentation locally"
        echo "  skills [target]  Symlink skills into agent directories (codex|claude|all)"
        echo "  skills-codex     Symlink skills into Codex agent directory"
        echo "  skills-claude    Symlink skills into Claude agent directory"
        echo "  help             Show this help"
        ;;
esac
