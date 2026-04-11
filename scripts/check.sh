#!/usr/bin/env bash
# Local quality gate: runs the same checks as `make check`.
# Useful for IDE-integrated runs and when GNU make is not available.
#
# Note: if this file loses its executable bit after checkout, restore with:
#   chmod +x scripts/check.sh
# It can also be invoked directly as: bash scripts/check.sh

set -euo pipefail

cd "$(dirname "$0")/.."

echo "==> ruff lint"
uv run ruff check src tests

echo "==> ruff format check"
uv run ruff format --check src tests

echo "==> mypy"
uv run mypy src

echo "==> pytest"
uv run pytest -v

echo "==> all checks passed"
