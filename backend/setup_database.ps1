<#
    PowerShell Database Setup Script for Credit Scoring Application
    Ported from setup_database.sh (bash) to PowerShell for Windows users
#>

Push-Location -Path $PSScriptRoot

Write-Host "========================================="
Write-Host "Credit Scoring Database Setup"
Write-Host "=========================================`n"

# Detect Python command (prefer python from venv, fallback to python3)
$pythonCmd = $null
try {
    $pyVersion = (& python --version 2>&1) -join "`n"
} catch {
    $pyVersion = $null
}

if ($pyVersion -and $pyVersion -match 'Python 3') {
    $pythonCmd = 'python'
    Write-Host "✅ Using: $pyVersion"
} elseif (Get-Command python3 -ErrorAction SilentlyContinue) {
    $pythonCmd = 'python3'
    $pyVersion = (& python3 --version 2>&1) -join "`n"
    Write-Host "✅ Using: $pyVersion"
} else {
    Write-Host "❌ Error: Python 3 is not installed"
    Pop-Location
    exit 1
}

Write-Host ""

# Helper for yes/no prompts (default No if user presses Enter)
function Read-YesNo($prompt, $defaultYes = $false) {
    if ($defaultYes) {
        $fullPrompt = "$prompt (Y/n): "
    } else {
        $fullPrompt = "$prompt (y/N): "
    }
    $resp = Read-Host -Prompt $fullPrompt
    if ([string]::IsNullOrWhiteSpace($resp)) {
        return $defaultYes
    }
    return ($resp -match '^[Yy]')
}

# Check if .env file exists
if (-not (Test-Path -Path ".env")) {
    Write-Host "⚠️  Warning: .env file not found`n"
    Write-Host "Please create a .env file with your database credentials:`n"
    Write-Host "DATABASE_URL=postgresql://user:password@host:port/dbname"
    Write-Host "# OR"
    Write-Host "PG_DBNAME=your_db_name"
    Write-Host "PG_USER=your_user"
    Write-Host "PG_PASSWORD=your_password"
    Write-Host "PG_HOST=localhost"
    Write-Host "PG_PORT=5432`n"

    $cont = Read-YesNo "Do you want to continue anyway?" $false
    if (-not $cont) {
        Pop-Location
        exit 1
    }
}

Write-Host "Step 0: Cleaning up legacy tables..."
Write-Host "-----------------------------------"
$cleanupScript = @"
try:
    from db import get_db_connection
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS datasets CASCADE")
    conn.commit()
    cur.close()
    conn.close()
    print("🧹 Removed legacy 'datasets' table (if it existed).")
except Exception as e:
    print(f"⚠️  Warning: Could not drop legacy 'datasets' table automatically: {e}")
"@
& $pythonCmd -c $cleanupScript
Write-Host ""

Write-Host "`nStep 1: Validating current database schema..."
Write-Host "-------------------------------------------"
Write-Host "Note: This will automatically remove created_at columns from"
Write-Host "      features, binning_steps, bins, merged_bins, and binning_totals tables."
Write-Host ""
& $pythonCmd .\validate_and_migrate_schema.py
$VALIDATION_RESULT = $LASTEXITCODE

if ($VALIDATION_RESULT -eq 0) {
    Write-Host "`n✅ Database schema is correct!`n"
    $runTests = Read-YesNo "Do you want to run tests?" $true
    if ($runTests) {
        Write-Host "`nStep 2: Running tests..."
        Write-Host "------------------------"
        & $pythonCmd .\test_new_schema.py
        $TEST_RESULT = $LASTEXITCODE
        if ($TEST_RESULT -eq 0) {
            Write-Host "`n========================================="
            Write-Host "✅ Setup Complete! Database is ready."
            Write-Host "=========================================`n"
            Write-Host "You can now run your application:`n  python app.py`n"
            Pop-Location
            exit 0
        } else {
            Write-Host "`n⚠️  Some tests failed. Please review the output above."
            Pop-Location
            exit 1
        }
    } else {
        Write-Host "Aborted by user. No tests were run.`n"
        Pop-Location
        exit 0
    }
} else {
    Write-Host "`n⚠️  Database schema needs to be created or fixed.`n"
    $backupFirst = Read-YesNo "Do you want to backup existing data first?" $true

    $BACKUP_FLAG = ""
    if ($backupFirst) { $BACKUP_FLAG = "--backup-old" }

    $recreate = Read-YesNo "Do you want to recreate the database schema now?" $false
    if ($recreate) {
        Write-Host "`n⚠️  WARNING: This will DROP existing tables!`n"
        $confirm = Read-Host -Prompt "Are you absolutely sure? Type 'yes' to continue"
        if ($confirm -eq 'yes') {
            Write-Host "`nStep 2: Creating database schema..."
            Write-Host "-----------------------------------"
            & $pythonCmd .\validate_and_migrate_schema.py $BACKUP_FLAG --force-recreate
            $CREATE_RESULT = $LASTEXITCODE
            if ($CREATE_RESULT -eq 0) {
                Write-Host "`nStep 3: Running tests..."
                Write-Host "------------------------"
                & $pythonCmd .\test_new_schema.py
                $TEST_RESULT = $LASTEXITCODE
                if ($TEST_RESULT -eq 0) {
                    Write-Host "`n========================================="
                    Write-Host "✅ Setup Complete! Database is ready."
                    Write-Host "=========================================`n"
                    Write-Host "You can now run your application:`n  python app.py`n"
                    Pop-Location
                    exit 0
                } else {
                    Write-Host "`n⚠️  Some tests failed. Please review the output above."
                    Pop-Location
                    exit 1
                }
            } else {
                Write-Host "`n❌ Failed to create database schema.`nPlease check the error messages above."
                Pop-Location
                exit 1
            }
        } else {
            Write-Host "`nAborted. No changes were made."
            Pop-Location
            exit 0
        }
    } else {
        Write-Host "`nAborted. Please fix the database schema manually.`n"
        Write-Host "You can run:`n  $pythonCmd validate_and_migrate_schema.py --force-recreate`n"
        Pop-Location
        exit 1
    }
}

Pop-Location
