#!/usr/bin/env bash
# WAKALA bootstrap (macOS / Linux / Git Bash). Creates the backend venv,
# installs all dependencies, runs backend tests and the frontend build.
# Usage (from the repository root):  bash scripts/bootstrap.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if [ -x "$ROOT/backend/.venv/Scripts/python.exe" ] || [ "${OS:-}" = "Windows_NT" ]; then
  PY_BIN="$ROOT/backend/.venv/Scripts/python"
else
  PY_BIN="$ROOT/backend/.venv/bin/python"
fi

echo "==> Backend: virtual environment and dependencies"
cd "$ROOT/backend"
[ -d .venv ] || python3 -m venv .venv 2>/dev/null || python -m venv .venv
"$PY_BIN" -m pip install --upgrade pip --quiet
"$PY_BIN" -m pip install -r requirements.txt --quiet
echo "==> Backend: tests"
"$PY_BIN" -m pytest

echo "==> Frontend: dependencies and production build"
cd "$ROOT/frontend"
npm install --no-audit --no-fund
npm run build

echo
echo "Bootstrap complete. Start the app in two terminals:"
echo "  cd backend  && $PY_BIN run_dev.py"
echo "  cd frontend && npm run dev"
