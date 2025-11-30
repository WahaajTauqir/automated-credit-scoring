# Developer setup (local machine)

This repository includes helper scripts to bootstrap a fresh development machine and initialize the PostgreSQL database used by the backend. The scripts are idempotent and conservative — they will not overwrite existing files unless needed.

1) Bootstrap Python environment and backend env

```bash
# create venv, install python deps, and create backend/.env from backend/.env.example
bash scripts/bootstrap_backend.sh
```

After this, edit `backend/.env` and add your values for either `DATABASE_URL` or `PG_USER`/`PG_PASSWORD`/`PG_DBNAME`, and add `GITHUB_TOKEN` for AI classification.

2) Initialize PostgreSQL (optional)

This step requires access to the postgres superuser (typically via `sudo -u postgres`). It will create the role/user, create the database, import the schema from `backend/database.sql`, and grant privileges to the app user.

```bash
bash scripts/db_setup.sh
```

3) Start the backend

```bash
source .venv/bin/activate
./start_backend.sh
```

4) One-shot setup (bootstrap + optional DB)

```bash
bash scripts/setup_all.sh
```

Notes
- `backend/.env` is added to `.gitignore` — do not commit real tokens or passwords.
- If you already have a PostgreSQL server with your own user/database, you can skip `db_setup.sh` and simply set `DATABASE_URL` in `backend/.env`.
- `scripts/db_setup.sh` will prompt for confirmation and will not overwrite an existing database unless you choose to recreate it manually.

+