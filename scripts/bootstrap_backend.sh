#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV_DIR="$REPO_ROOT/.venv"

echo "Bootstrap script — prepare Python venv and backend env"

command -v python3 >/dev/null 2>&1 || { echo "python3 is required. Install it and re-run."; exit 1; }

if [ ! -d "$VENV_DIR" ]; then
  echo "Creating virtualenv at $VENV_DIR"
  python3 -m venv "$VENV_DIR"
fi

echo "Activating venv and installing Python dependencies..."
# shellcheck disable=SC1090
source "$VENV_DIR/bin/activate"
pip install --upgrade pip
pip install -r "$REPO_ROOT/backend/requirements.txt"

echo
echo "Preparing backend environment file..."
if [ ! -f "$REPO_ROOT/backend/.env" ]; then
  cp "$REPO_ROOT/backend/.env.example" "$REPO_ROOT/backend/.env"
  echo "Created backend/.env from backend/.env.example — edit it and add your secrets (DATABASE_URL or PG_* and GITHUB_TOKEN)."
else
  echo "backend/.env already exists — leaving it in place."
fi

cat <<EOF

Next steps (run these):
  1) Edit backend/.env and fill in DATABASE_URL or PG_USER/PG_PASSWORD/PG_DBNAME and GITHUB_TOKEN.
     (backend/.env is in .gitignore so it won't be committed.)
  2) Initialize the database (optional) using the DB setup script:
       bash "$REPO_ROOT/scripts/db_setup.sh"
     This will create the role and database (runs psql as the postgres superuser).
  3) Start the backend:
       source "$VENV_DIR/bin/activate"
       ./start_backend.sh

EOF

echo "Bootstrap complete."
