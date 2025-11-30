#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SQL_FILE="$REPO_ROOT/backend/database.sql"

echo "Database setup helper"

# Load backend/.env if present to pick up defaults
if [ -f "$REPO_ROOT/backend/.env" ]; then
  # shellcheck disable=SC1090
  source "$REPO_ROOT/backend/.env"
fi

# Read variables from env or prompt
: ${PG_DBNAME:=${PG_DBNAME:-}}
: ${PG_USER:=${PG_USER:-}}
: ${PG_PASSWORD:=${PG_PASSWORD:-}}

if [ -z "${PG_DBNAME:-}" ]; then
  read -rp "Enter database name to create (PG_DBNAME): " PG_DBNAME
fi
if [ -z "${PG_USER:-}" ]; then
  read -rp "Enter database role/user name to create (PG_USER): " PG_USER
fi
if [ -z "${PG_PASSWORD:-}" ]; then
  read -rsp "Enter password for $PG_USER (PG_PASSWORD): " PG_PASSWORD
  echo
fi

echo "Using PG_DBNAME=$PG_DBNAME, PG_USER=$PG_USER"

if [ ! -f "$SQL_FILE" ]; then
  echo "ERROR: schema file not found at $SQL_FILE" >&2
  exit 1
fi

echo "This script will create the database and role using the local postgres superuser (sudo -u postgres psql)."
read -rp "Proceed? [y/N] " yn
case "$yn" in
  [Yy]*) ;;
  *) echo "Aborted."; exit 1 ;;
esac


echo "Creating role (if not exists)..."
# Use a here-doc so the DO $$ block is passed to psql verbatim and shell variables are expanded safely
sudo -u postgres psql -v ON_ERROR_STOP=1 <<SQL
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = '${PG_USER}') THEN
    CREATE ROLE "${PG_USER}" WITH LOGIN PASSWORD '${PG_PASSWORD}';
    RAISE NOTICE 'Role % created', '${PG_USER}';
  ELSE
    RAISE NOTICE 'Role % already exists', '${PG_USER}';
  END IF;
END
$$;
SQL

echo "Creating database if it does not exist..."
DB_EXISTS=$(sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname = '$PG_DBNAME'" | tr -d '[:space:]' || true)
if [ "$DB_EXISTS" = "1" ]; then
  echo "Database $PG_DBNAME already exists"
else
  echo "Creating database $PG_DBNAME owned by $PG_USER"
  sudo -u postgres createdb -O "$PG_USER" "$PG_DBNAME"
fi

echo "Importing schema into $PG_DBNAME"
sudo -u postgres psql -d "$PG_DBNAME" -v ON_ERROR_STOP=1 -f "$SQL_FILE"

echo "Setting privileges: GRANT ALL PRIVILEGES ON DATABASE to $PG_USER"
sudo -u postgres psql -d "$PG_DBNAME" -c "GRANT ALL PRIVILEGES ON DATABASE \"$PG_DBNAME\" TO \"$PG_USER\";"

echo "Database setup complete. You can now set DATABASE_URL=postgresql://$PG_USER:$PG_PASSWORD@127.0.0.1:5432/$PG_DBNAME in backend/.env"
