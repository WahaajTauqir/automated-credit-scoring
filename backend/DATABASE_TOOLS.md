# 🗄️ Database Management Tools

Complete set of tools for managing the credit scoring database.

## 📋 Available Tools

### 1. 🚀 Setup Database
**File**: `setup_database.sh`  
**Purpose**: Initialize and validate database schema

```bash
./setup_database.sh
```

**What it does**:
- ✅ Validates database connection
- ✅ Checks if schema exists
- ✅ Creates tables if needed
- ✅ Runs comprehensive tests
- ✅ Verifies everything works

**When to use**: 
- First time setup
- After schema changes
- When tables are missing

---

### 2. 🧹 Clear Database
**Files**: `clear_database.sh` / `clear_database.py`  
**Purpose**: Remove all data while keeping schema intact

#### Usage Options

**A. Interactive Mode (Recommended)**
```bash
./clear_database.sh
```
Shows statistics and asks for confirmation before deleting.

**B. Force Mode (No Confirmation)**
```bash
./clear_database.sh --force
```
⚠️ **Warning**: Deletes all data immediately without asking!

**C. Show Statistics Only**
```bash
./clear_database.sh --stats
```
View current row counts without deleting anything.

**D. Delete Specific Dataset**
```bash
./clear_database.sh --dataset 1
```
Delete only dataset #1 and all its related data (CASCADE).

**E. Using Python Directly**
```bash
python clear_database.py --help
python clear_database.py --stats
python clear_database.py --force
python clear_database.py --dataset 1
```

#### Example Output

**Statistics Mode**:
```bash
$ ./clear_database.sh --stats

============================================================
CURRENT DATABASE STATISTICS
============================================================

  datasets             :     3 rows
  features             :    45 rows
  binning_steps        :    30 rows
  bins                 :   150 rows
  merged_bins          :    15 rows
  binning_totals       :    30 rows
------------------------------------------------------------
  TOTAL                :   273 rows
============================================================
```

**Interactive Mode**:
```bash
$ ./clear_database.sh

============================================================
CURRENT DATABASE STATISTICS
============================================================
  datasets             :     3 rows
  features             :    45 rows
  ...
  TOTAL                :   273 rows

============================================================
⚠️  WARNING: DATABASE CLEAR OPERATION
============================================================

This will DELETE ALL DATA from the following tables:
  - binning_totals
  - merged_bins
  - bins
  - binning_steps
  - features
  - datasets

The table structure will remain intact.
This operation CANNOT be undone!

============================================================

Type 'DELETE ALL DATA' to confirm: DELETE ALL DATA

============================================================
CLEARING DATABASE
============================================================

✅ Cleared binning_totals (30 rows deleted)
✅ Cleared merged_bins (15 rows deleted)
✅ Cleared bins (150 rows deleted)
✅ Cleared binning_steps (30 rows deleted)
✅ Cleared features (45 rows deleted)
✅ Cleared datasets (3 rows deleted)

============================================================
VERIFICATION
============================================================

✅ binning_totals: 0 rows
✅ merged_bins: 0 rows
✅ bins: 0 rows
✅ binning_steps: 0 rows
✅ features: 0 rows
✅ datasets: 0 rows

============================================================
✅ SUCCESS: All data cleared successfully!
============================================================

The database is now empty but the schema is intact.
You can start using the application from scratch.
```

---

### 3. ✅ Test Database
**File**: `test_new_schema.py`  
**Purpose**: Comprehensive test suite

```bash
python test_new_schema.py
```

**What it tests**:
- ✅ Database connection
- ✅ Dataset CRUD operations
- ✅ Feature operations
- ✅ Binning operations (coarse & fine)
- ✅ Binning totals
- ✅ Complex queries
- ✅ Full workflow

---

### 4. ✅ Verify Integration
**File**: `verify_integration.py`  
**Purpose**: Quick integration check

```bash
python verify_integration.py
```

**Runs**:
- Import checks
- Connection test
- Schema validation
- CRUD operations test
- Binning operations test
- API endpoints check

---

### 5. 🔧 Validate & Migrate Schema
**File**: `validate_and_migrate_schema.py`  
**Purpose**: Schema management and migration

```bash
# Check schema
python validate_and_migrate_schema.py

# Backup old data
python validate_and_migrate_schema.py --backup-old

# Force recreate schema
python validate_and_migrate_schema.py --force-recreate

# Backup and recreate
python validate_and_migrate_schema.py --backup-old --force-recreate

# Drop old tables
python validate_and_migrate_schema.py --drop-old
```

---

## 🎯 Common Scenarios

### Fresh Start
```bash
# 1. Setup database
./setup_database.sh

# 2. Start using the application
python app.py
```

### Reset Everything
```bash
# Clear all data (keeps schema)
./clear_database.sh

# Upload new CSV and start fresh
```

### Development/Testing
```bash
# Check current data
./clear_database.sh --stats

# Clear after testing
./clear_database.sh --force

# Run tests
python test_new_schema.py
```

### Delete One Dataset
```bash
# List datasets first
./clear_database.sh --stats

# Delete specific dataset
./clear_database.sh --dataset 2
```

### Schema Issues
```bash
# Validate schema
python validate_and_migrate_schema.py

# Recreate if needed
python validate_and_migrate_schema.py --force-recreate
```

---

## 📊 Database Schema

**6 Tables (Normalized Structure)**:

```
datasets (run information)
   └── features (columns/variables)
          └── binning_steps (coarse/fine)
                 ├── bins (per-bin statistics)
                 ├── binning_totals (aggregate stats)
                 └── merged_bins (fine binning only)
```

**Relationships**:
- All have CASCADE delete
- Foreign key constraints enforced
- Referential integrity maintained

---

## ⚠️ Important Notes

### About Clearing Data

**Safe Operations**:
- ✅ `--stats` - Always safe, read-only
- ✅ Interactive mode - Asks for confirmation
- ✅ `--dataset ID` - Only deletes one dataset

**Dangerous Operations**:
- ⚠️ `--force` - No confirmation, deletes everything
- ⚠️ Manual SQL truncate/drop commands

### What Gets Deleted

**When clearing all data** (`./clear_database.sh`):
- ❌ All datasets deleted
- ❌ All features deleted
- ❌ All binning results deleted
- ❌ All bins deleted
- ❌ All totals deleted
- ✅ Schema remains intact
- ✅ Tables still exist
- ✅ Relationships preserved

**When deleting one dataset** (`--dataset ID`):
- ❌ That dataset deleted
- ❌ Its features deleted (CASCADE)
- ❌ Its binning steps deleted (CASCADE)
- ❌ Its bins deleted (CASCADE)
- ❌ Its totals deleted (CASCADE)
- ✅ Other datasets unaffected

### Cannot Be Undone

**No undo/rollback** - Once data is deleted, it's gone forever!

**Backup first** if you need to preserve data:
```bash
# Backup using validate script
python validate_and_migrate_schema.py --backup-old

# Or manual pg_dump
pg_dump -U username dbname > backup.sql
```

---

## 🛠️ Troubleshooting

### "No module named 'db'"
```bash
# Ensure db.py exists
ls -la db.py

# Run from backend directory
cd backend
./clear_database.sh
```

### "Connection refused"
```bash
# Check PostgreSQL is running
sudo systemctl status postgresql

# Check .env file
cat .env | grep PG_
```

### "Permission denied"
```bash
# Make scripts executable
chmod +x setup_database.sh
chmod +x clear_database.sh
chmod +x clear_database.py
```

### Want to delete specific records?
```python
# Use Python directly
from db import delete_dataset, delete_binning_step

# Delete dataset 1
delete_dataset(1)

# Delete binning for feature 5
delete_all_binning_for_feature(5)
```

---

## 📝 Summary

| Tool | Purpose | Safe? | Use When |
|------|---------|-------|----------|
| `setup_database.sh` | Initialize DB | ✅ Yes | First time / Schema issues |
| `clear_database.sh` | Clear all data | ⚠️ Destructive | Reset / Testing |
| `clear_database.sh --stats` | View data | ✅ Yes | Check status |
| `clear_database.sh --dataset ID` | Clear one dataset | ⚠️ Partial | Remove specific run |
| `test_new_schema.py` | Run tests | ✅ Yes | Verify functionality |
| `verify_integration.py` | Quick check | ✅ Yes | Validate setup |

---

**Created**: November 14, 2024  
**Version**: 2.0  
**Status**: ✅ Production Ready
