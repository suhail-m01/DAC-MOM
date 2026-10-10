#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

if [[ ! -x "$ROOT/.venv/bin/python" ]]; then
  echo "Create the Python environment and install requirements first (see README.md)." >&2
  exit 1
fi
if [[ ! -d "$ROOT/frontend/node_modules" ]]; then
  echo "Install frontend dependencies first: cd frontend && npm install" >&2
  exit 1
fi

"$ROOT/.venv/bin/python" "$ROOT/app.py" &
API_PID=$!
(
  cd "$ROOT/frontend"
  npm run dev
) &
WEB_PID=$!

cleanup() {
  kill "$WEB_PID" "$API_PID" 2>/dev/null || true
  wait "$WEB_PID" "$API_PID" 2>/dev/null || true
}
trap cleanup INT TERM EXIT
wait "$WEB_PID"
