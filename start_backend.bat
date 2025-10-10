@echo off
set GITHUB_TOKEN=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
echo Starting backend with GitHub token...
echo Token prefix: %GITHUB_TOKEN:~0,20%...
rem PostgreSQL connection settings - update these to your environment

call .venv\Scripts\activate

set PG_DBNAME=mydb
set PG_USER=myuser
set PG_PASSWORD=mypassword
set PG_HOST=localhost
set PG_PORT=5432

python backend\app.py

pause