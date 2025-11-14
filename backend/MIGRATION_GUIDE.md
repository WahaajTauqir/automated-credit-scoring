# Database Schema Migration Guide

## Overview

This document describes the migration from the old database schema to the new structured schema for the Credit Scoring application.

## Old Schema (Legacy)

### Tables:
1. **records** - Stored all data in JSON blobs
   - Columns: id, dataset_path, discrete_columns, continuous_columns, selected_columns, dashboard_selected_columns, target_variable, univariate_results, finebin_results, crosstab_results, woe_iv_results, created_at

2. **finebin_details** - Stored fine binning merge information
   - Columns: id, record_id, column_name, group_id, merged_bins

### Problems with Old Schema:
- Data stored as JSON strings (hard to query)
- No referential integrity
- Difficult to track relationships between entities
- Poor performance for complex queries
- Data duplication and inconsistency

## New Schema (Restructured)

### Tables:

#### 1. `datasets`
Stores dataset/run information (one per credit scoring run)
```sql
CREATE TABLE datasets (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    file_path TEXT,
    total_features INT,
    discrete_features INT,
    continuous_features INT,
    target_variable TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

**Example Row:**
```
(1, 'Loan_Data_Run1', '/backend/uploaded.csv', 30, 10, 20, 'default', '2024-01-01', '2024-01-01')
```

#### 2. `features`
Each dataset has many features (one row per feature/column)
```sql
CREATE TABLE features (
    id SERIAL PRIMARY KEY,
    dataset_id INT NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    type VARCHAR(20) NOT NULL CHECK (type IN ('discrete', 'continuous')),
    selected BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(dataset_id, name)
);
```

**Example Rows:**
```
(1, 1, 'age', 'continuous', true, '2024-01-01')
(2, 1, 'gender', 'discrete', true, '2024-01-01')
(3, 1, 'income', 'continuous', false, '2024-01-01')
```

#### 3. `binning_steps`
Tracks coarse and fine binning operations
```sql
CREATE TABLE binning_steps (
    id SERIAL PRIMARY KEY,
    feature_id INT NOT NULL REFERENCES features(id) ON DELETE CASCADE,
    step_type VARCHAR(20) NOT NULL CHECK (step_type IN ('coarse', 'fine')),
    method VARCHAR(50),
    num_bins INT,
    is_monotonic BOOLEAN DEFAULT FALSE,
    monotonic_direction VARCHAR(20),
    iv_value NUMERIC(10, 6),
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(feature_id, step_type)
);
```

**Example Rows:**
```
(1, 1, 'coarse', 'qcut', 5, false, null, 0.1234, '2024-01-01')
(2, 1, 'fine', 'merged', 3, true, 'increasing', 0.1156, '2024-01-01')
```

#### 4. `bins`
Stores detailed bin results (Min, Max, Good, Bad, WOE, IV, etc.)
```sql
CREATE TABLE bins (
    id SERIAL PRIMARY KEY,
    binning_step_id INT NOT NULL REFERENCES binning_steps(id) ON DELETE CASCADE,
    bin_number INT NOT NULL,
    bin_label TEXT,
    min_value NUMERIC,
    max_value NUMERIC,
    range_text TEXT,
    good_count INT NOT NULL DEFAULT 0,
    bad_count INT NOT NULL DEFAULT 0,
    total_count INT NOT NULL DEFAULT 0,
    good_bad_ratio NUMERIC(10, 4),
    bad_rate NUMERIC(10, 4),
    freq_percent NUMERIC(10, 4),
    odds NUMERIC(10, 4),
    index_value NUMERIC(10, 4),
    odds_index NUMERIC(10, 4),
    dist_good NUMERIC(10, 4),
    dist_bad NUMERIC(10, 4),
    woe NUMERIC(10, 4),
    iv NUMERIC(10, 6),
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(binning_step_id, bin_number)
);
```

**Example Rows:**
```
(1, 1, 1, 'Bin_1', 18.0, 25.0, null, 200, 50, 250, 4.0, 20.0, 12.5, ..., 0.32, 0.012, '2024-01-01')
(2, 1, 2, 'Bin_2', 25.0, 35.0, null, 300, 40, 340, 7.5, 11.8, 17.0, ..., 0.45, 0.015, '2024-01-01')
```

#### 5. `merged_bins`
Tracks which coarse bins were merged in fine binning
```sql
CREATE TABLE merged_bins (
    id SERIAL PRIMARY KEY,
    fine_step_id INT NOT NULL REFERENCES binning_steps(id) ON DELETE CASCADE,
    merged_bin_number INT NOT NULL,
    original_bin_ids INT[] NOT NULL,
    original_bin_labels TEXT[] NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);
```

**Example Rows:**
```
(1, 2, 1, {1,2}, {'Bin_1','Bin_2'}, '2024-01-01')
(2, 2, 2, {3,4,5}, {'Bin_3','Bin_4','Bin_5'}, '2024-01-01')
```

## Database Structure Overview

```
datasets
   └── features
          └── binning_steps (coarse / fine)
                 ├── bins (results)
                 └── merged_bins (only for fine binning)
```

## Example Workflow

### 1. Upload Dataset
```python
dataset_id = create_dataset(
    name='Loan_Data_Run1',
    file_path='/backend/uploaded.csv',
    total_features=30,
    discrete_features=10,
    continuous_features=20,
    target_variable='default'
)
```

### 2. Create Features
```python
features = [
    {'name': 'age', 'type': 'continuous', 'selected': True},
    {'name': 'gender', 'type': 'discrete', 'selected': True},
    {'name': 'income', 'type': 'continuous', 'selected': False}
]
create_features_batch(dataset_id, features)
```

### 3. Perform Coarse Binning
```python
feature_id = get_feature_by_name(dataset_id, 'age')['id']
step_id = create_binning_step(
    feature_id=feature_id,
    step_type='coarse',
    method='qcut',
    num_bins=5,
    iv_value=0.1234
)
```

### 4. Store Coarse Bins
```python
bins_data = [
    {
        'bin_number': 1,
        'bin_label': 'Bin_1',
        'min_value': 18.0,
        'max_value': 25.0,
        'good_count': 200,
        'bad_count': 50,
        'total_count': 250,
        'woe': 0.32,
        'iv': 0.012,
        'dist_good': 15.5,
        'dist_bad': 10.2
    },
    # ... more bins
]
create_bins_batch(step_id, bins_data)
```

### 5. Perform Fine Binning
```python
fine_step_id = create_binning_step(
    feature_id=feature_id,
    step_type='fine',
    method='merged',
    num_bins=3,
    is_monotonic=True,
    monotonic_direction='increasing',
    iv_value=0.1156
)
```

### 6. Store Merged Bins Mapping
```python
create_merged_bin(
    fine_step_id=fine_step_id,
    merged_bin_number=1,
    original_bin_ids=[1, 2],
    original_bin_labels=['Bin_1', 'Bin_2']
)
```

### 7. Store Fine Bins
```python
fine_bins_data = [
    {
        'bin_number': 1,
        'bin_label': 'Bin_1_2',
        'min_value': 18.0,
        'max_value': 35.0,
        'good_count': 500,
        'bad_count': 90,
        'total_count': 590,
        'woe': 0.38,
        'iv': 0.025,
        'dist_good': 32.8,
        'dist_bad': 18.4
    },
    # ... more bins
]
create_bins_batch(fine_step_id, fine_bins_data)
```

## Migration Steps

### Step 1: Backup Existing Data
```bash
python backend/validate_and_migrate_schema.py --backup-old
```

### Step 2: Validate Current Schema
```bash
python backend/validate_and_migrate_schema.py
```

### Step 3: Create New Schema
```bash
# Option 1: Drop everything and recreate (DESTRUCTIVE)
python backend/validate_and_migrate_schema.py --force-recreate

# Option 2: Keep data and just drop old tables
python backend/validate_and_migrate_schema.py --drop-old
```

### Step 4: Update Application Code
The application code has been updated to use the new database layer (`db_new.py`). The changes are backward compatible where possible.

### Step 5: Test the New Schema
Run your application and test all functionality:
- Dataset upload
- Feature classification
- Coarse binning
- Fine binning
- WOE/IV calculation
- Model training
- Scorecard generation

## Benefits of New Schema

1. **Better Data Integrity**: Foreign key constraints ensure referential integrity
2. **Easier Queries**: No need to parse JSON strings
3. **Better Performance**: Indexed columns for faster lookups
4. **Clearer Structure**: Explicit relationships between entities
5. **Scalability**: Can handle large datasets more efficiently
6. **Maintainability**: Easier to understand and modify
7. **Atomicity**: Each entity has its own table with proper columns
8. **Auditability**: Timestamps on all tables for tracking changes

## Rollback Plan

If you need to rollback to the old schema:

1. Restore from backup:
```bash
# Restore the old database dump
psql -U username -d database_name -f backup/database_backup_YYYYMMDD.sql
```

2. Revert code changes:
```bash
git checkout main  # or your previous working branch
```

## Support

If you encounter any issues during migration:
1. Check the backup files in `backend/backup/`
2. Review the migration logs
3. Consult the validation script output
4. Contact the development team

## Database Diagram

```
┌─────────────────┐
│    datasets     │
│─────────────────│
│ id (PK)         │
│ name            │
│ file_path       │
│ total_features  │
│ ...             │
└────────┬────────┘
         │
         │ 1:N
         │
┌────────▼────────┐
│    features     │
│─────────────────│
│ id (PK)         │
│ dataset_id (FK) │
│ name            │
│ type            │
│ selected        │
└────────┬────────┘
         │
         │ 1:N
         │
┌────────▼─────────┐
│  binning_steps   │
│──────────────────│
│ id (PK)          │
│ feature_id (FK)  │
│ step_type        │
│ method           │
│ num_bins         │
│ is_monotonic     │
│ iv_value         │
└────┬────────┬────┘
     │        │
     │ 1:N    │ 1:N
     │        │
┌────▼───┐ ┌─▼──────────┐
│  bins  │ │merged_bins │
│────────│ │────────────│
│ id (PK)│ │ id (PK)    │
│ step_id│ │ step_id    │
│ ...    │ │ ...        │
└────────┘ └────────────┘
```
