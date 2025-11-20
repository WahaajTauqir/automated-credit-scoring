#!/bin/bash

# Database Setup Script for Credit Scoring Application
# This script sets up the new database schema

echo "========================================="
echo "Credit Scoring Database Setup"
echo "========================================="
echo ""

# Detect Python command (prefer python from venv, fallback to python3)
if command -v python &> /dev/null && python --version 2>&1 | grep -q "Python 3"; then
    PYTHON_CMD="python"
    echo "✅ Using: $(python --version)"
elif command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
    echo "✅ Using: $(python3 --version)"
else
    echo "❌ Error: Python 3 is not installed"
    exit 1
fi
echo ""

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo "⚠️  Warning: .env file not found"
    echo ""
    echo "Please create a .env file with your database credentials:"
    echo ""
    echo "DATABASE_URL=postgresql://user:password@host:port/dbname"
    echo "# OR"
    echo "PG_DBNAME=your_db_name"
    echo "PG_USER=your_user"
    echo "PG_PASSWORD=your_password"
    echo "PG_HOST=localhost"
    echo "PG_PORT=5432"
    echo ""
    read -p "Do you want to continue anyway? (y/N): " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo ""
echo "Step 0: Cleaning up legacy tables..."
echo "-----------------------------------"
$PYTHON_CMD - <<'PY'
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
PY
echo ""
echo "Step 1: Validating current database schema..."
echo "-------------------------------------------"
echo "Note: This will automatically:"
echo "      - Remove created_at columns from features, binning_steps, bins, merged_bins, and binning_totals tables"
echo "      - Remove derived columns (good_bad_ratio, bad_rate, freq_percent, odds, index_value, odds_index, dist_good, dist_bad) from bins table"
echo "      - Add train/test split columns to records table (if missing)"
echo ""
$PYTHON_CMD validate_and_migrate_schema.py

VALIDATION_RESULT=$?

if [ $VALIDATION_RESULT -eq 0 ]; then
    echo ""
    echo "✅ Database schema is correct!"
    echo ""
    read -p "Do you want to run tests? (Y/n): " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Nn]$ ]]; then
        echo ""
        echo "Step 2: Running tests..."
        echo "------------------------"
        
        TEST_RESULT=$?
        if [ $TEST_RESULT -eq 0 ]; then
            echo ""
            echo "========================================="
            echo "✅ Setup Complete! Database is ready."
            echo "========================================="
            echo ""
            echo "You can now run your application:"
            echo "  python app.py"
            echo ""
        else
            echo ""
            echo "⚠️  Some tests failed. Please review the output above."
            exit 1
        fi
    fi
else
    echo ""
    echo "⚠️  Database schema needs to be created or fixed."
    echo ""
    read -p "Do you want to backup existing data first? (Y/n): " -n 1 -r
    echo ""
    
    BACKUP_FLAG=""
    if [[ ! $REPLY =~ ^[Nn]$ ]]; then
        BACKUP_FLAG="--backup-old"
    fi
    
    echo ""
    read -p "Do you want to recreate the database schema now? (y/N): " -n 1 -r
    echo ""
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo ""
        echo "⚠️  WARNING: This will DROP existing tables!"
        echo ""
        read -p "Are you absolutely sure? Type 'yes' to continue: " CONFIRM
        
        if [ "$CONFIRM" = "yes" ]; then
            echo ""
            echo "Step 2: Creating database schema..."
            echo "-----------------------------------"
            $PYTHON_CMD validate_and_migrate_schema.py $BACKUP_FLAG --force-recreate
            
            CREATE_RESULT=$?
            if [ $CREATE_RESULT -eq 0 ]; then
                echo ""
                echo "Step 3: Running tests..."
                echo "------------------------"
                
                TEST_RESULT=$?
                if [ $TEST_RESULT -eq 0 ]; then
                    echo ""
                    echo "========================================="
                    echo "✅ Setup Complete! Database is ready."
                    echo "========================================="
                    echo ""
                    echo "You can now run your application:"
                    echo "  python app.py"
                    echo ""
                else
                    echo ""
                    echo "⚠️  Some tests failed. Please review the output above."
                    exit 1
                fi
            else
                echo ""
                echo "❌ Failed to create database schema."
                echo "Please check the error messages above."
                exit 1
            fi
        else
            echo ""
            echo "Aborted. No changes were made."
            exit 0
        fi
    else
        echo ""
        echo "Aborted. Please fix the database schema manually."
        echo ""
        echo "You can run:"
        echo "  $PYTHON_CMD validate_and_migrate_schema.py --force-recreate"
        echo ""
        exit 1
    fi
fi
