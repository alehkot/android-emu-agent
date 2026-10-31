#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
trap 'printf "CI check failed at line %s\n" "$LINENO" >&2' ERR

uv sync --locked --all-extras
npm ci
bash scripts/dev.sh check
