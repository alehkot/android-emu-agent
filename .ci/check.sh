#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export CI=true NO_COLOR=1
mkdir -p .ci-output
trap 'printf "CI check failed at line %s\n" "$LINENO" >&2' ERR
python3 -B .ci/test_report.py

uv sync --locked --all-extras
npm ci
bash scripts/dev.sh check
