#!/usr/bin/env bash
# Development helper script

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
RELEASE_FORCE_TAG_PUSH_OLD_SHA=""

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

render_bridge_downloader_with_version() {
    local new_version="$1"
    local output_file="$2"

    awk -v version="$new_version" '
        BEGIN { updated = 0 }
        !updated && /^[[:space:]]*_DEFAULT_BRIDGE_VERSION[[:space:]]*=/ {
            sub(/"[^"]*"/, "\"" version "\"")
            updated = 1
        }
        { print }
        END {
            if (!updated) {
                exit 1
            }
        }
    ' src/android_emu_agent/debugger/bridge_downloader.py > "$output_file"
}

render_bridge_gradle_with_version() {
    local new_version="$1"
    local output_file="$2"

    awk -v version="$new_version" '
        BEGIN { updated = 0 }
        !updated && /^[[:space:]]*version[[:space:]]*=/ {
            sub(/"[^"]*"/, "\"" version "\"")
            updated = 1
        }
        { print }
        END {
            if (!updated) {
                exit 1
            }
        }
    ' jdi-bridge/build.gradle.kts > "$output_file"
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

ensure_command() {
    local command_name="$1"
    local install_hint="$2"

    if command -v "$command_name" >/dev/null 2>&1; then
        return 0
    fi

    echo "Missing required command: $command_name. $install_hint"
    return 1
}

ensure_clean_worktree() {
    if ! git diff --quiet || ! git diff --cached --quiet; then
        echo "Working tree has uncommitted changes. Commit or stash them first."
        return 1
    fi
}

ensure_version_consistency() {
    local version="$1"
    local init_version
    local downloader_version
    local gradle_version
    local lock_version=""

    init_version="$(awk '
        /^[[:space:]]*__version__[[:space:]]*=/ {
            line = $0
            sub(/^[^"]*"/, "", line)
            sub(/".*$/, "", line)
            print line
            exit 0
        }
    ' src/android_emu_agent/__init__.py)"
    downloader_version="$(awk '
        /^[[:space:]]*_DEFAULT_BRIDGE_VERSION[[:space:]]*=/ {
            line = $0
            sub(/^[^"]*"/, "", line)
            sub(/".*$/, "", line)
            print line
            exit 0
        }
    ' src/android_emu_agent/debugger/bridge_downloader.py)"
    gradle_version="$(awk '
        /^[[:space:]]*version[[:space:]]*=/ {
            line = $0
            sub(/^[^"]*"/, "", line)
            sub(/".*$/, "", line)
            print line
            exit 0
        }
    ' jdi-bridge/build.gradle.kts)"

    if [ -f uv.lock ]; then
        lock_version="$(awk '
            /^[[:space:]]*name[[:space:]]*=[[:space:]]*"android-emu-agent"[[:space:]]*$/ {
                in_package = 1
                next
            }
            in_package && /^[[:space:]]*version[[:space:]]*=/ {
                line = $0
                sub(/^[^"]*"/, "", line)
                sub(/".*$/, "", line)
                print line
                exit 0
            }
        ' uv.lock)"
    fi

    if [ "$init_version" != "$version" ]; then
        echo "Version mismatch: src/android_emu_agent/__init__.py has $init_version, expected $version."
        return 1
    fi

    if [ "$downloader_version" != "$version" ]; then
        echo "Version mismatch: bridge_downloader.py has $downloader_version, expected $version."
        return 1
    fi

    if [ "$gradle_version" != "$version" ]; then
        echo "Version mismatch: jdi-bridge/build.gradle.kts has $gradle_version, expected $version."
        return 1
    fi

    if [ -f uv.lock ] && [ "$lock_version" != "$version" ]; then
        echo "Version mismatch: uv.lock has $lock_version, expected $version."
        return 1
    fi
}

ensure_release_tag_at_head() {
    local tag="$1"
    local head_sha
    local local_tag_sha
    local remote_tag_sha

    head_sha="$(git rev-parse HEAD)"

    if git rev-parse -q --verify "refs/tags/$tag" >/dev/null; then
        local_tag_sha="$(git rev-list -n 1 "$tag")"
        if [ "$local_tag_sha" != "$head_sha" ]; then
            remote_tag_sha="$(remote_tag_commit "$tag")"
            echo "Tag $tag exists but does not point at HEAD."
            echo "  tag:  $local_tag_sha"
            echo "  HEAD: $head_sha"
            if [ -n "$remote_tag_sha" ]; then
                echo "  GitHub tag: $remote_tag_sha"
            fi

            local move_confirm
            read -r -p "Move $tag to HEAD and update the GitHub tag during release? [y/N]: " \
                move_confirm
            case "$move_confirm" in
                y|Y|yes|YES)
                    git tag -f "$tag" "$head_sha"
                    RELEASE_FORCE_TAG_PUSH_OLD_SHA="$remote_tag_sha"
                    echo "Moved local tag $tag to HEAD."
                    ;;
                *)
                    echo "Release cancelled. Check out $tag or move the tag before retrying."
                    return 1
                    ;;
            esac
        fi
        return 0
    fi

    git tag "$tag"
    echo "Created local tag: $tag"
}

github_push_url() {
    local repo_slug
    if ! repo_slug="$(gh repo view --json nameWithOwner --jq .nameWithOwner)" \
        || [ -z "$repo_slug" ]; then
        echo "Unable to determine GitHub repository from gh." >&2
        return 1
    fi

    printf "https://github.com/%s.git\n" "$repo_slug"
}

remote_tag_commit() {
    local tag="$1"
    local push_url
    local remote_ref

    push_url="$(github_push_url)" || return 1
    if ! remote_ref="$(git ls-remote --tags "$push_url" "refs/tags/$tag")"; then
        echo "Unable to inspect GitHub tag $tag." >&2
        return 1
    fi
    if [ -z "$remote_ref" ]; then
        return 0
    fi

    printf "%s\n" "${remote_ref%%[[:space:]]*}"
}

push_release_refs() {
    local branch="$1"
    local tag="$2"
    local push_url

    push_url="$(github_push_url)" || return 1
    echo "Pushing $branch and $tag to GitHub..."
    git push "$push_url" "$branch"
    if [ -n "$RELEASE_FORCE_TAG_PUSH_OLD_SHA" ]; then
        git push --force-with-lease="refs/tags/$tag:$RELEASE_FORCE_TAG_PUSH_OLD_SHA" \
            "$push_url" "refs/tags/$tag"
    else
        git push "$push_url" "$tag"
    fi
}

build_bridge_release_artifacts() {
    local version="$1"
    local jar_path="$PROJECT_DIR/jdi-bridge/build/libs/jdi-bridge-$version-all.jar"
    local checksum_path="$jar_path.sha256"

    echo "Building JDI Bridge release artifact..."
    "$PROJECT_DIR/jdi-bridge/gradlew" -p "$PROJECT_DIR/jdi-bridge" shadowJar

    if [ ! -f "$jar_path" ]; then
        echo "Expected bridge JAR was not built: $jar_path"
        return 1
    fi

    shasum -a 256 "$jar_path" | awk '{ print $1 }' > "$checksum_path"
    echo "Prepared release assets:"
    echo "  $jar_path"
    echo "  $checksum_path"
}

build_python_release_artifacts() {
    local version="$1"
    local wheel_path="$PROJECT_DIR/dist/android_emu_agent-$version-py3-none-any.whl"
    local sdist_path="$PROJECT_DIR/dist/android_emu_agent-$version.tar.gz"

    ensure_command uv "Install uv from https://docs.astral.sh/uv/." || return 1
    ensure_command uvx "Install uv from https://docs.astral.sh/uv/." || return 1

    echo "Building Python release distributions..."
    mkdir -p "$PROJECT_DIR/dist"
    rm -f "$PROJECT_DIR/dist"/*.whl "$PROJECT_DIR/dist"/*.tar.gz "$PROJECT_DIR/dist"/*.zip
    uv build

    if [ ! -f "$wheel_path" ]; then
        echo "Expected wheel was not built: $wheel_path"
        return 1
    fi

    if [ ! -f "$sdist_path" ]; then
        echo "Expected source distribution was not built: $sdist_path"
        return 1
    fi

    echo "Checking Python distributions with Twine..."
    uvx --from twine twine check "$wheel_path" "$sdist_path"

    echo "Prepared Python distributions:"
    echo "  $wheel_path"
    echo "  $sdist_path"
}

publish_python_release_artifacts() {
    local version="$1"
    local wheel_path="$PROJECT_DIR/dist/android_emu_agent-$version-py3-none-any.whl"
    local sdist_path="$PROJECT_DIR/dist/android_emu_agent-$version.tar.gz"

    if [ ! -f "$wheel_path" ] || [ ! -f "$sdist_path" ]; then
        build_python_release_artifacts "$version" || return 1
    fi

    echo "Uploading Python distributions to PyPI..."
    uvx --from twine twine upload "$wheel_path" "$sdist_path"
}

verify_github_release_assets() {
    local tag="$1"
    local version="$2"
    local jar_name="jdi-bridge-$version-all.jar"
    local checksum_name="$jar_name.sha256"

    if ! gh release view "$tag" >/dev/null 2>&1; then
        echo "GitHub release $tag was not found."
        return 1
    fi

    if ! gh release view "$tag" --json assets --jq '.assets[].name' | grep -Fxq "$jar_name"; then
        echo "GitHub release $tag is missing asset: $jar_name"
        return 1
    fi

    if ! gh release view "$tag" --json assets --jq '.assets[].name' | grep -Fxq "$checksum_name"; then
        echo "GitHub release $tag is missing asset: $checksum_name"
        return 1
    fi

    echo "Verified GitHub release assets for $tag."
}

release_current_version() {
    ensure_command gh "Install GitHub CLI and run 'gh auth login'." || return 1
    if ! gh auth status >/dev/null 2>&1; then
        echo "GitHub CLI is not authenticated. Run 'gh auth login' and retry."
        return 1
    fi
    ensure_clean_worktree || return 1

    local version
    version="$(read_project_version)"
    if [ -z "$version" ]; then
        echo "Unable to read version from pyproject.toml [project].version."
        return 1
    fi

    ensure_version_consistency "$version" || return 1

    local branch
    branch="$(git branch --show-current)"
    if [ -z "$branch" ]; then
        echo "Release requires a named branch; current checkout is detached."
        return 1
    fi

    local tag="v$version"
    local jar_path="$PROJECT_DIR/jdi-bridge/build/libs/jdi-bridge-$version-all.jar"
    local checksum_path="$jar_path.sha256"

    ensure_release_tag_at_head "$tag" || return 1
    build_python_release_artifacts "$version" || return 1
    build_bridge_release_artifacts "$version" || return 1
    push_release_refs "$branch" "$tag" || return 1

    if gh release view "$tag" >/dev/null 2>&1; then
        gh release upload "$tag" "$jar_path" "$checksum_path" --clobber
    else
        gh release create "$tag" "$jar_path" "$checksum_path" \
            --title "$tag" \
            --notes "Release $tag"
    fi

    verify_github_release_assets "$tag" "$version"
    echo "Release $tag is published with bridge artifacts."
    publish_python_release_artifacts "$version"
    echo "Release $tag is published to GitHub and PyPI."
}

verify_current_release() {
    ensure_command gh "Install GitHub CLI and run 'gh auth login'." || return 1

    local version
    version="$(read_project_version)"
    if [ -z "$version" ]; then
        echo "Unable to read version from pyproject.toml [project].version."
        return 1
    fi

    ensure_version_consistency "$version" || return 1
    verify_github_release_assets "v$version" "$version"
}

publish_current_python_version() {
    ensure_clean_worktree || return 1

    local version
    version="$(read_project_version)"
    if [ -z "$version" ]; then
        echo "Unable to read version from pyproject.toml [project].version."
        return 1
    fi

    ensure_version_consistency "$version" || return 1
    build_python_release_artifacts "$version" || return 1
    publish_python_release_artifacts "$version"
}

bump_version() {
    if ! git diff --quiet || ! git diff --cached --quiet; then
        echo "Working tree has uncommitted changes. Please commit or stash them first."
        return 1
    fi

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
    local bridge_downloader_tmp
    local bridge_gradle_tmp
    local pyproject_backup
    local init_backup
    local bridge_downloader_backup
    local bridge_gradle_backup
    pyproject_tmp="$(mktemp)"
    init_tmp="$(mktemp)"
    bridge_downloader_tmp="$(mktemp)"
    bridge_gradle_tmp="$(mktemp)"
    pyproject_backup="$(mktemp)"
    init_backup="$(mktemp)"
    bridge_downloader_backup="$(mktemp)"
    bridge_gradle_backup="$(mktemp)"

    cp pyproject.toml "$pyproject_backup"
    cp src/android_emu_agent/__init__.py "$init_backup"
    cp src/android_emu_agent/debugger/bridge_downloader.py "$bridge_downloader_backup"
    cp jdi-bridge/build.gradle.kts "$bridge_gradle_backup"

    if ! render_pyproject_with_version "$new_version" "$pyproject_tmp"; then
        rm -f "$pyproject_tmp" "$init_tmp" "$bridge_downloader_tmp" "$bridge_gradle_tmp" \
            "$pyproject_backup" "$init_backup" "$bridge_downloader_backup" "$bridge_gradle_backup"
        echo "Failed to prepare updated pyproject.toml."
        return 1
    fi

    if ! render_init_with_version "$new_version" "$init_tmp"; then
        rm -f "$pyproject_tmp" "$init_tmp" "$bridge_downloader_tmp" "$bridge_gradle_tmp" \
            "$pyproject_backup" "$init_backup" "$bridge_downloader_backup" "$bridge_gradle_backup"
        echo "Failed to prepare updated __init__.py."
        return 1
    fi

    if ! render_bridge_downloader_with_version "$new_version" "$bridge_downloader_tmp"; then
        rm -f "$pyproject_tmp" "$init_tmp" "$bridge_downloader_tmp" "$bridge_gradle_tmp" \
            "$pyproject_backup" "$init_backup" "$bridge_downloader_backup" "$bridge_gradle_backup"
        echo "Failed to prepare updated bridge_downloader.py."
        return 1
    fi

    if ! render_bridge_gradle_with_version "$new_version" "$bridge_gradle_tmp"; then
        rm -f "$pyproject_tmp" "$init_tmp" "$bridge_downloader_tmp" "$bridge_gradle_tmp" \
            "$pyproject_backup" "$init_backup" "$bridge_downloader_backup" "$bridge_gradle_backup"
        echo "Failed to prepare updated jdi-bridge/build.gradle.kts."
        return 1
    fi

    if ! mv "$pyproject_tmp" pyproject.toml \
        || ! mv "$init_tmp" src/android_emu_agent/__init__.py \
        || ! mv "$bridge_downloader_tmp" src/android_emu_agent/debugger/bridge_downloader.py \
        || ! mv "$bridge_gradle_tmp" jdi-bridge/build.gradle.kts; then
        cp "$pyproject_backup" pyproject.toml
        cp "$init_backup" src/android_emu_agent/__init__.py
        cp "$bridge_downloader_backup" src/android_emu_agent/debugger/bridge_downloader.py
        cp "$bridge_gradle_backup" jdi-bridge/build.gradle.kts
        rm -f "$pyproject_tmp" "$init_tmp" "$bridge_downloader_tmp" "$bridge_gradle_tmp" \
            "$pyproject_backup" "$init_backup" "$bridge_downloader_backup" "$bridge_gradle_backup"
        echo "Failed to write version updates. Original files restored."
        return 1
    fi

    rm -f "$pyproject_backup" "$init_backup" "$bridge_downloader_backup" "$bridge_gradle_backup"

    echo "Version bumped: $current_version -> $new_version"
    echo "Updated files:"
    echo "  pyproject.toml"
    echo "  src/android_emu_agent/__init__.py"
    echo "  src/android_emu_agent/debugger/bridge_downloader.py"
    echo "  jdi-bridge/build.gradle.kts"

    if ! maybe_update_uv_lock; then
        return 1
    fi

    local tag="v$new_version"
    local tag_confirm
    read -r -p "Commit and tag as $tag? [y/N]: " tag_confirm
    case "$tag_confirm" in
        y|Y|yes|YES)
            git add pyproject.toml src/android_emu_agent/__init__.py
            git add src/android_emu_agent/debugger/bridge_downloader.py
            git add jdi-bridge/build.gradle.kts
            if [ -f uv.lock ]; then
                git add uv.lock
            fi
            if git commit -m "chore: bump version to $new_version"; then
                echo "Committed version bump."
            else
                echo "Failed to commit version bump."
                return 1
            fi
            if git tag "$tag"; then
                echo "Created git tag: $tag"
            else
                echo "Failed to create git tag $tag."
                return 1
            fi
            echo "Next: run './scripts/dev.sh release' to push, upload, and verify bridge assets."
            ;;
        *)
            echo "Skipped commit and tag creation."
            echo "After committing and tagging, run './scripts/dev.sh release'."
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
        uv run python scripts/validate_skills.py
        "$PROJECT_DIR/jdi-bridge/gradlew" -p "$PROJECT_DIR/jdi-bridge" shadowJar
        "$PROJECT_DIR/jdi-bridge/gradlew" -p "$PROJECT_DIR/jdi-bridge" test
        uv run pytest tests/unit -q
        uv run mkdocs build --strict
        if command -v npm >/dev/null 2>&1; then
            npm run lint:md
        else
            echo "npm not found; skipping Markdown lint."
        fi
        echo "All checks passed!"
        ;;

    build-bridge)
        echo "Building JDI Bridge..."
        if [ ! -f "$PROJECT_DIR/jdi-bridge/gradlew" ]; then
            echo "Gradle wrapper not found in jdi-bridge/. Run 'gradle wrapper' first."
            exit 1
        fi
        "$PROJECT_DIR/jdi-bridge/gradlew" -p "$PROJECT_DIR/jdi-bridge" shadowJar
        echo "JAR: $PROJECT_DIR/jdi-bridge/build/libs/"
        ls -lh "$PROJECT_DIR/jdi-bridge/build/libs/"*-all.jar 2>/dev/null || echo "No JAR found."
        ;;

    test-bridge)
        echo "Running JDI Bridge tests..."
        if [ ! -f "$PROJECT_DIR/jdi-bridge/gradlew" ]; then
            echo "Gradle wrapper not found in jdi-bridge/."
            exit 1
        fi
        "$PROJECT_DIR/jdi-bridge/gradlew" -p "$PROJECT_DIR/jdi-bridge" test
        ;;

    daemon)
        echo "Starting daemon..."
        uv run uvicorn android_emu_agent.daemon.server:app --uds /tmp/android-emu-agent.sock
        ;;

    bump-version)
        bump_version
        ;;

    release)
        release_current_version
        ;;

    verify-release)
        verify_current_release
        ;;

    publish-pypi)
        publish_current_python_version
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
            vscode)
                echo "Installing skills for VS Code..."
                install_skills "$PROJECT_DIR/.agents/skills" "VS Code"
                ;;
            all)
                echo "Installing skills for Codex, Claude, and VS Code..."
                install_skills "$codex_root/skills" "Codex"
                install_skills "$claude_root/skills" "Claude"
                install_skills "$PROJECT_DIR/.agents/skills" "VS Code"
                ;;
            *)
                echo "Unknown skills target '$target'. Use 'codex', 'claude', 'vscode', or 'all'."
                exit 1
                ;;
        esac
        ;;

    skills-validate)
        echo "Validating bundled Agent Skills..."
        uv run python scripts/validate_skills.py
        ;;

    skills-codex)
        ensure_supported_os
        echo "Installing skills for Codex..."
        codex_root="${CODEX_HOME:-$HOME/.codex}"
        install_skills "$codex_root/skills" "Codex"
        ;;

    skills-vscode)
        ensure_supported_os
        echo "Installing skills for VS Code..."
        install_skills "$PROJECT_DIR/.agents/skills" "VS Code"
        ;;

    docs)
        echo "Building docs..."
        uv run mkdocs build --strict
        ;;

    docs-serve)
        echo "Serving docs locally..."
        uv run mkdocs serve
        ;;

    docs-gen)
        echo "Regenerating CLI reference docs..."
        uv run typer android_emu_agent.cli.main utils docs --name android-emu-agent \
            | sed 's/^\$ //' \
            | sed 's/^- /\* /' \
            | sed -e :a -e '/^\n*$/{$d;N;ba' -e '}' \
            > docs/reference.md
        if command -v npm >/dev/null 2>&1; then
            npx markdownlint-cli2 --fix docs/reference.md 2>/dev/null || true
        fi
        echo "Updated docs/reference.md"
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
        echo "  build-bridge     Build the JDI Bridge fat JAR (jdi-bridge/)"
        echo "  test-bridge      Run JDI Bridge Kotlin tests"
        echo "  daemon           Start the daemon server"
        echo "  bump-version     Interactively bump package version (patch/minor/major/custom),"
        echo "                   optionally refresh uv.lock, and optionally create a git tag"
        echo "  release          Build artifacts, push branch+tag, publish GitHub release and PyPI"
        echo "  verify-release   Verify the GitHub release has bridge JAR and checksum assets"
        echo "  publish-pypi     Rebuild checked Python dist artifacts and upload with Twine"
        echo "  docs             Build documentation (mkdocs)"
        echo "  docs-serve       Serve documentation locally"
        echo "  docs-gen         Regenerate CLI reference from Typer app"
        echo "  skills [target]  Symlink skills into agent directories (codex|claude|vscode|all)"
        echo "  skills-validate  Validate bundled Agent Skills"
        echo "  skills-codex     Symlink skills into Codex agent directory"
        echo "  skills-vscode    Symlink skills into VS Code .agents/skills"
        echo "  skills-claude    Symlink skills into Claude agent directory"
        echo "  help             Show this help"
        ;;
esac
