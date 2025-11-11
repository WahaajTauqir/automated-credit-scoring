@echo off
REM --- SET ENVIRONMENT VARIABLES ---
REM **SECURITY WARNING**: Replace 'YOUR_REAL_GITHUB_TOKEN_HERE' with your actual token
REM on your local machine only. Do NOT share this file with a real token in it.
set GITHUB_TOKEN=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

REM PostgreSQL connection settings
set PG_DBNAME=mydb
set PG_USER=myuser
set PG_PASSWORD=my123
set PG_HOST=localhost
set PG_PORT=5432

REM Optional runtime settings
set PORT=5000
set DEBUG=true

echo Starting backend service...

REM Activate the virtual environment
call .venv\Scripts\activate

REM Run the main application
python backend\app.py

REM Keep the console open until a key is pressed (optional)
pause