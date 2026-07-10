#!/usr/bin/env bash
# Run pytest with the project's virtual env (which has fastembed installed).
# Usage: scripts/test.sh [pytest args...]
# Examples:
#   scripts/test.sh --testmon
#   scripts/test.sh tests/unit/test_repositories.py -v --tb=short
#   scripts/test.sh --cov=src --cov-report=term-missing --cov-report=html:test-results/coverage
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Prefer venv/, fall back to .venv/, then system python (last resort).
PYTHON=""
for candidate in "$ROOT/venv/bin/python" "$ROOT/.venv/bin/python"; do
  if [[ -x "$candidate" ]]; then
    PYTHON="$candidate"
    break
  fi
done
if [[ -z "$PYTHON" ]]; then
  PYTHON="$(command -v python3)"
  echo "WARNING: no project venv found, using system $PYTHON (fastembed may be missing)" >&2
fi

exec "$PYTHON" -m pytest "$@"
