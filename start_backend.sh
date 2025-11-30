#!/usr/bin/env bash
set -euo pipefail

# start_backend.sh - simple helper to activate the venv, load backend/.env and run the Flask app
# Usage: ./start_backend.sh

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"

# Activate venv if present
if [ -f "$REPO_ROOT/.venv/bin/activate" ]; then
  # shellcheck disable=SC1090
  source "$REPO_ROOT/.venv/bin/activate"
elif [ -f "$REPO_ROOT/venv/bin/activate" ]; then
  # shellcheck disable=SC1090
  source "$REPO_ROOT/venv/bin/activate"
fi

# Load environment variables from backend/.env if present (don't commit real .env)
# Use direct sourcing so variables are exported to this shell (set -a exports all vars)
if [ -f "$REPO_ROOT/backend/.env" ]; then
  set -a
  # shellcheck disable=SC1090
  # shellcheck source=/dev/null
  source "$REPO_ROOT/backend/.env"
  set +a
fi

echo "Starting backend..."
echo "DATABASE_URL=${DATABASE_URL:-<not set>}"

cd "$REPO_ROOT"
python3 backend/app.py
