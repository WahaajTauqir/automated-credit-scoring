@echo off
REM GITHUB_TOKEN is sensitive — DO NOT hardcode real tokens in this file.
REM Set your token in a local, untracked `backend/.env` file instead.
REM Example (PowerShell/CMD): set GITHUB_TOKEN=your_token_here
echo Starting backend (ensure GITHUB_TOKEN is set in your environment or backend\.env)
rem PostgreSQL connection settings - update these to your environment

call .venv\Scripts\activate

set PG_DBNAME=mydb
set PG_USER=myuser
set PG_PASSWORD=mypassword
set PG_HOST=localhost
set PG_PORT=5432

python backend\app.py

pause