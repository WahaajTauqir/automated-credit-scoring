#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "Running full local setup: venv + deps + (optional) DB setup"

bash "$REPO_ROOT/scripts/bootstrap_backend.sh"

read -rp "Run DB setup now? This will require sudo access to run psql as the postgres user. [y/N] " run_db
if [[ "$run_db" =~ ^[Yy]$ ]]; then
  bash "$REPO_ROOT/scripts/db_setup.sh"
else
  echo "Skipped DB setup. You can run scripts/db_setup.sh later when ready."
fi

echo "All done. To start backend: source .venv/bin/activate && ./start_backend.sh"
