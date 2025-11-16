# Database Restructuring - Complete Guide

## 🎯 Overview

This document provides a complete guide for the database restructuring of the Credit Scoring application. The new schema provides better data organization, referential integrity, and improved query performance.

## 📋 Table of Contents

1. [Quick Start](#quick-start)
2. [Schema Overview](#schema-overview)
3. [Migration Process](#migration-process)
4. [Usage Examples](#usage-examples)
5. [Testing](#testing)
6. [Troubleshooting](#troubleshooting)

## 🚀 Quick Start

### Prerequisites

- PostgreSQL database running
- Python 3.8+
- Environment variables configured (.env file)

### Required Environment Variables

```bash
# Option 1: Full connection string
DATABASE_URL=postgresql://user:password@host:port/dbname

# Option 2: Individual components
PG_DBNAME=your_database_name
PG_USER=your_database_user
PG_PASSWORD=your_password
PG_HOST=localhost
PG_PORT=5432
```

### Step 1: Validate Current Schema

```bash
cd backend
python validate_and_migrate_schema.py
```

This will check if your database has the correct structure.

### Step 2: Create New Schema (First Time Setup)

```bash
# Option A: Clean installation (no existing data)
python validate_and_migrate_schema.py --force-recreate

# Option B: Backup existing data first
python validate_and_migrate_schema.py --backup-old --force-recreate
```

### Step 3: Test the Schema

```bash
python test_new_schema.py
```

### Step 4: Run Your Application

```bash
python app.py
```

## 📊 Schema Overview

### New Database Structure

```
datasets (credit scoring runs)
   ↓
features (columns in dataset)
   ↓
binning_steps (coarse/fine binning)
   ↓
   ├── bins (bin statistics: Good, Bad, WOE, IV)
   └── merged_bins (tracks merges in fine binning)
```

### Table Descriptions

#### 1. **datasets**
- Stores information about each credit scoring dataset/run
- One row per dataset upload
- Fields: id, name, file_path, total_features, discrete_features, continuous_features, target_variable

#### 2. **features**
- Stores individual features (columns) for each dataset
- One row per feature per dataset
- Fields: id, dataset_id, name, type (discrete/continuous), selected

#### 3. **binning_steps**
- Tracks binning operations (coarse and fine) for each feature
- One row per feature per step_type (coarse/fine)
- Fields: id, feature_id, step_type, method, num_bins, is_monotonic, monotonic_direction, iv_value

#### 4. **bins**
- Stores detailed statistics for each bin
- Multiple rows per binning_step
- Fields: id, binning_step_id, bin_number, bin_label, min_value, max_value, range_text, good_count, bad_count, total_count, woe, iv, dist_good, dist_bad, bad_rate, etc.

#### 5. **merged_bins**
- Tracks which coarse bins were merged during fine binning
- One row per merge operation
- Fields: id, fine_step_id, merged_bin_number, original_bin_ids, original_bin_labels

## 🔄 Migration Process

### Understanding the Migration

The migration moves from a JSON-based schema (where data was stored as text) to a normalized relational schema with proper foreign keys and data types.

**Old Schema:**
```
records (all data in JSON)
   ├── univariate_results (JSON)
   ├── finebin_results (JSON)
   ├── woe_iv_results (JSON)
   └── ...
```

**New Schema:**
```
datasets → features → binning_steps → bins
                               └→ merged_bins
```

### Migration Steps

#### 1. **Backup Your Data** (IMPORTANT!)

```bash
# Backup old database structure
python validate_and_migrate_schema.py --backup-old
```

This creates JSON backups in `backend/backup/`:
- `records_backup_YYYYMMDD_HHMMSS.json`
- `finebin_details_backup_YYYYMMDD_HHMMSS.json`

#### 2. **Validate Schema**

```bash
python validate_and_migrate_schema.py
```

Possible outcomes:
- ✅ **Schema is correct**: No action needed
- ⚠️ **Missing tables**: Will be created automatically
- ❌ **Incorrect structure**: Need to recreate

#### 3. **Recreate Schema** (if needed)

```bash
# This will DROP existing tables and create new ones
python validate_and_migrate_schema.py --force-recreate
```

⚠️ **WARNING**: This is DESTRUCTIVE. All existing data will be lost. Make sure you have backups!

#### 4. **Test New Schema**

```bash
python test_new_schema.py
```

This runs comprehensive tests to ensure:
- Database connection works
- All tables exist and are accessible
- CRUD operations work correctly
- Foreign key relationships are enforced
- Complex queries return expected results

## 💻 Usage Examples

### Example 1: Upload New Dataset

```python
from db_new import create_dataset, create_features_batch

# Create dataset
dataset_id = create_dataset(
    name='Loan_Application_2024',
    file_path='/backend/uploaded.csv',
    total_features=25,
    discrete_features=8,
    continuous_features=17,
    target_variable='default_status'
)

# Create features
features = [
    {'name': 'age', 'type': 'continuous', 'selected': True},
    {'name': 'income', 'type': 'continuous', 'selected': True},
    {'name': 'education_level', 'type': 'discrete', 'selected': True},
    {'name': 'employment_type', 'type': 'discrete', 'selected': False}
]

feature_ids = create_features_batch(dataset_id, features)
```

### Example 2: Perform Coarse Binning

```python
from db_new import (
    get_feature_by_name, create_binning_step, create_bins_batch
)

# Get feature
feature = get_feature_by_name(dataset_id, 'age')

# Create coarse binning step
step_id = create_binning_step(
    feature_id=feature['id'],
    step_type='coarse',
    method='qcut',
    num_bins=5,
    iv_value=0.1234
)

# Store bin results
bins = [
    {
        'bin_number': 1,
        'bin_label': 'Bin_1',
        'min_value': 18.0,
        'max_value': 30.0,
        'good_count': 500,
        'bad_count': 50,
        'total_count': 550,
        'woe': 0.42,
        'iv': 0.025,
        'dist_good': 35.2,
        'dist_bad': 15.8,
        'bad_rate': 9.1
    },
    # ... more bins
]

create_bins_batch(step_id, bins)
```

### Example 3: Perform Fine Binning with Merging

```python
from db_new import create_binning_step, create_merged_bin, create_bins_batch

# Create fine binning step
fine_step_id = create_binning_step(
    feature_id=feature['id'],
    step_type='fine',
    method='merged',
    num_bins=3,
    is_monotonic=True,
    monotonic_direction='increasing',
    iv_value=0.1156
)

# Record which bins were merged
create_merged_bin(
    fine_step_id=fine_step_id,
    merged_bin_number=1,
    original_bin_ids=[1, 2],  # Merged Bin_1 and Bin_2
    original_bin_labels=['Bin_1', 'Bin_2']
)

# Store fine bin results
fine_bins = [
    {
        'bin_number': 1,
        'bin_label': 'Bin_1_2',
        'min_value': 18.0,
        'max_value': 40.0,
        'good_count': 800,
        'bad_count': 90,
        'total_count': 890,
        'woe': 0.45,
        'iv': 0.035,
        'dist_good': 56.3,
        'dist_bad': 28.5,
        'bad_rate': 10.1
    },
    # ... more bins
]

create_bins_batch(fine_step_id, fine_bins)
```

### Example 4: Retrieve Complete Results

```python
from db_new import get_complete_binning_results, get_dataset_with_all_results

# Get complete binning results for a feature
results = get_complete_binning_results(feature_id, step_type='fine')

print(f"Feature: {results['feature']['name']}")
print(f"Binning method: {results['binning_step']['method']}")
print(f"Number of bins: {len(results['bins'])}")
print(f"Monotonic: {results['binning_step']['is_monotonic']}")
print(f"IV Value: {results['binning_step']['iv_value']}")

# Get entire dataset with all features and binning
complete_data = get_dataset_with_all_results(dataset_id)

for feature in complete_data['features']:
    print(f"\nFeature: {feature['name']} ({feature['type']})")
    if feature['binning']['coarse']:
        print(f"  Coarse bins: {len(feature['binning']['coarse']['bins'])}")
    if feature['binning']['fine']:
        print(f"  Fine bins: {len(feature['binning']['fine']['bins'])}")
```

## 🧪 Testing

### Run All Tests

```bash
python test_new_schema.py
```

### Test Individual Components

```python
# Test database connection
from db_new import get_db_connection
conn = get_db_connection()
print("Connected!" if conn else "Failed!")

# Test dataset creation
from db_new import create_dataset
dataset_id = create_dataset(
    name='Test Dataset',
    file_path='/test.csv',
    total_features=10,
    discrete_features=3,
    continuous_features=7,
    target_variable='target'
)
print(f"Created dataset: {dataset_id}")
```

### Expected Test Output

```
============================================================
TEST 1: Database Connection
============================================================
✅ Connected to PostgreSQL
   Version: PostgreSQL 14.5...

============================================================
TEST 2: Dataset Operations
============================================================
✅ Created dataset with ID: 1
✅ Retrieved dataset: Test_Dataset_20240101_120000
✅ Found 1 total datasets
✅ Latest dataset: Test_Dataset_20240101_120000

... (more tests)

============================================================
                ALL TESTS COMPLETED
============================================================

✅ Database schema is working correctly!
```

## 🔧 Troubleshooting

### Problem: Connection Error

**Error:**
```
❌ Connection failed: could not connect to server
```

**Solution:**
1. Check your `.env` file has correct database credentials
2. Ensure PostgreSQL is running: `sudo systemctl status postgresql`
3. Test connection manually: `psql -U username -d database_name`

### Problem: Missing Tables

**Error:**
```
❌ Table 'datasets' does NOT exist
```

**Solution:**
```bash
python validate_and_migrate_schema.py --force-recreate
```

### Problem: Schema Mismatch

**Error:**
```
⚠️  Table 'bins' exists but has incorrect structure:
   Missing columns: woe, iv
```

**Solution:**
```bash
# Backup first!
python validate_and_migrate_schema.py --backup-old

# Then recreate
python validate_and_migrate_schema.py --force-recreate
```

### Problem: Old Tables Still Exist

**Error:**
```
⚠️  Old table 'records' still exists (should be removed)
```

**Solution:**
```bash
python validate_and_migrate_schema.py --drop-old
```

### Problem: Permission Denied

**Error:**
```
ERROR: permission denied for table datasets
```

**Solution:**
Grant proper permissions to your database user:
```sql
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO your_username;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO your_username;
```

## 📚 Additional Resources

### Files Created

1. **schema_new.sql** - Complete SQL schema definition
2. **validate_and_migrate_schema.py** - Schema validation and migration tool
3. **db_new.py** - New database layer with all functions
4. **test_new_schema.py** - Comprehensive test suite
5. **MIGRATION_GUIDE.md** - Detailed migration documentation
6. **DATABASE_RESTRUCTURING_README.md** - This file

### Database Views

The schema includes helpful views:

```sql
-- View all features with dataset info
SELECT * FROM v_features_with_dataset;

-- View all binning results with context
SELECT * FROM v_binning_results;
```

### Useful SQL Queries

```sql
-- Get all datasets
SELECT * FROM datasets ORDER BY created_at DESC;

-- Get features for a dataset
SELECT * FROM features WHERE dataset_id = 1;

-- Get binning results for a feature
SELECT 
    bs.step_type,
    bs.method,
    bs.num_bins,
    bs.iv_value,
    b.bin_number,
    b.bin_label,
    b.good_count,
    b.bad_count,
    b.woe,
    b.iv
FROM binning_steps bs
JOIN bins b ON b.binning_step_id = bs.id
WHERE bs.feature_id = 1
ORDER BY bs.step_type, b.bin_number;

-- Get merged bins information
SELECT 
    mb.merged_bin_number,
    mb.original_bin_labels,
    array_length(mb.original_bin_ids, 1) as num_merged
FROM merged_bins mb
WHERE mb.fine_step_id = 2;
```

## ✅ Verification Checklist

After migration, verify:

- [ ] Database connection works
- [ ] All 5 tables exist (datasets, features, binning_steps, bins, merged_bins)
- [ ] Views are created (v_features_with_dataset, v_binning_results)
- [ ] Can create new dataset
- [ ] Can create features
- [ ] Can create binning steps
- [ ] Can create bins
- [ ] Can retrieve data correctly
- [ ] Foreign key constraints work
- [ ] Old tables removed (records, finebin_details)

## 🆘 Support

If you encounter issues:

1. Check this README
2. Review MIGRATION_GUIDE.md
3. Run test_new_schema.py for diagnostics
4. Check backup files in backend/backup/
5. Review application logs

## 📝 Notes

- Always backup before migration
- Test thoroughly after migration
- The new schema is more efficient and maintainable
- All old functionality is preserved
- Data is properly normalized

---

**Created:** 2024
**Last Updated:** 2024
**Version:** 1.0
