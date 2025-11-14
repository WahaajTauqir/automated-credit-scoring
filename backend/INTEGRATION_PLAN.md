# Database Schema Integration Plan

## Overview
Migrating from JSON-based storage (old db.py) to normalized relational schema (db_new.py with 6 tables including new binning_totals).

## Schema Structure

```
datasets (run information)
   └── features (columns/variables)
          └── binning_steps (coarse/fine)
                 ├── bins (per-bin statistics)
                 ├── binning_totals (NEW: overall totals)
                 └── merged_bins (fine binning only)
```

## Endpoints to Migrate

### 1. ✅ `/api/upload-csv` (POST)
**Current Behavior**: Saves CSV file, returns column info
**New Behavior**: 
- Create dataset record
- Create feature records for each column
- Save file path and metadata
**Changes Required**:
- Call `create_dataset()` with file metadata
- Call `create_features_batch()` with column list
- Store dataset_id in session or return to frontend

### 2. ✅ `/api/ai-classify-columns` (POST)
**Current Behavior**: Classifies columns as discrete/continuous
**New Behavior**:
- Update feature records with classification
- Mark features as discrete/continuous
**Changes Required**:
- Get dataset_id from request
- Update features table with type information
- Call `update_feature()` for each classified column

### 3. ✅ `/api/univariate-analysis` (POST - Coarse Binning)
**Current Behavior**: Performs coarse binning, saves to records table as JSON
**New Behavior**:
- Create binning_step record (step_type='coarse')
- Create bins records for each bin
- Create binning_totals record with overall stats
**Changes Required**:
- Get feature_id from database by name
- Call `create_binning_step()` with method, num_bins, IV
- Call `create_bins_batch()` with bin statistics
- Call `create_binning_totals()` with aggregated totals
- Calculate and store: total_good, total_bad, total_count, IV

### 4. ✅ `/api/fine-bin` (POST)
**Current Behavior**: Merges coarse bins, saves to records table as JSON
**New Behavior**:
- Create binning_step record (step_type='fine')
- Create bins records for merged bins
- Create binning_totals record with overall stats
- Create merged_bins records tracking merge operations
**Changes Required**:
- Get feature_id and coarse bins from database
- Call `create_binning_step()` with method='merged'
- Call `create_bins_batch()` with new bin statistics
- Call `create_binning_totals()` with updated totals
- Call `create_merged_bin()` for each merge operation
- Store which coarse bins were merged into which fine bins

### 5. ✅ `/api/woe-iv` (POST/GET)
**Current Behavior**: Calculates WOE/IV from records JSON
**New Behavior**:
- Retrieve from bins and binning_totals tables
- Calculate WOE/IV from structured data
**Changes Required**:
- Use `get_complete_binning_results()` to fetch all data
- Read from bins table (woe, iv already stored)
- Read from binning_totals table for overall IV
- Return formatted response

### 6. 🔧 Model Training Endpoints
**Endpoints**: `/api/logistic-regression`, `/api/random-forest`, `/api/xgboost`
**Changes Required**:
- Get selected features from features table where selected=true
- Get WOE values from bins table
- Transform data using stored WOE mappings
- Train models as before

### 7. 🔧 `/api/scorecard` (POST)
**Changes Required**:
- Retrieve binning results from normalized tables
- Get WOE/IV from bins table
- Generate scorecard using structured data

## Data Flow Examples

### Upload CSV Flow
```
POST /api/upload-csv
  ↓
1. Save CSV file
2. create_dataset(name, path, row_count, ...)
3. create_features_batch([{name: 'age', type: 'continuous'}, ...])
4. Return dataset_id to frontend
```

### Coarse Binning Flow
```
POST /api/univariate-analysis
  ↓
1. Get feature_id from features table by name
2. Perform binning calculations
3. create_binning_step(feature_id, 'coarse', method='qcut', num_bins=5, iv=0.045)
4. create_bins_batch(step_id, [{bin_number: 1, good: 180, bad: 30, woe: 0.12, ...}, ...])
5. create_binning_totals(step_id, total_good=1800, total_bad=300, iv=0.045)
6. Return success with bin statistics
```

### Fine Binning Flow
```
POST /api/fine-bin
  ↓
1. Get coarse binning_step_id and bins
2. Merge bins based on request
3. create_binning_step(feature_id, 'fine', method='merged', num_bins=3, iv=0.050)
4. create_bins_batch(step_id, [{bin_number: 1, ...}, ...])
5. create_binning_totals(step_id, total_good=1800, total_bad=300, iv=0.050)
6. create_merged_bin(fine_step_id, 1, [1,2], ['Bin_1','Bin_2'])  # For each merge
7. Return success
```

### WOE/IV Retrieval Flow
```
POST /api/woe-iv
  ↓
1. Get dataset_id
2. Get all features with selected=true
3. For each feature:
   - Get fine binning results (or coarse if fine doesn't exist)
   - Get bins with woe, iv values
   - Get binning_totals for overall IV
4. Format and return
```

## Frontend Changes Required

### State Management
- Store `dataset_id` after upload
- Store `feature_id` mappings for each column
- Pass dataset_id with all subsequent requests

### API Request Updates

**Before:**
```javascript
// Upload
const response = await fetch('/api/upload-csv', {formData})
// No dataset tracking

// Binning
const response = await fetch('/api/univariate-analysis', {
  body: JSON.stringify({selectedColumns, targetColumn, bins})
})
```

**After:**
```javascript
// Upload - save dataset_id
const response = await fetch('/api/upload-csv', {formData})
const data = await response.json()
setDatasetId(data.dataset_id)  // Store in state

// Binning - include dataset_id
const response = await fetch('/api/univariate-analysis', {
  body: JSON.stringify({
    dataset_id: datasetId,  // Include dataset_id
    selectedColumns, 
    targetColumn, 
    bins
  })
})
```

### Data Display Updates

**Before:**
```javascript
// Results structure from JSON
{
  variable: "age",
  binning_table: [...],
  iv_value: 0.045
}
```

**After:**
```javascript
// Results from normalized schema
{
  feature: {
    id: 1,
    name: "age",
    type: "continuous",
    selected: true
  },
  binning_step: {
    id: 1,
    step_type: "coarse",
    method: "qcut",
    num_bins: 5,
    iv_value: 0.045,
    is_monotonic: false
  },
  bins: [
    {bin_number: 1, bin_label: "Bin_1", good_count: 180, bad_count: 30, woe: 0.12, iv: 0.004, ...},
    ...
  ],
  totals: {
    total_good: 1800,
    total_bad: 300,
    total_count: 2100,
    good_bad_ratio: 6.0,
    bad_rate: 0.1428,
    iv: 0.045
  }
}
```

## Migration Steps

### Phase 1: Backend Setup ✅
- [x] Add binning_totals table to schema
- [x] Update db_new.py with binning_totals functions
- [x] Test new schema with test suite

### Phase 2: Backend Integration 🔄
- [ ] Backup old app.py → app_old.py
- [ ] Update import: `from db_new import *` 
- [ ] Migrate `/api/upload-csv` endpoint
- [ ] Migrate `/api/ai-classify-columns` endpoint
- [ ] Migrate `/api/univariate-analysis` endpoint
- [ ] Migrate `/api/fine-bin` endpoint
- [ ] Migrate `/api/woe-iv` endpoint
- [ ] Update model training endpoints
- [ ] Update scorecard endpoint

### Phase 3: Frontend Integration 🔄
- [ ] Add dataset_id state management
- [ ] Update CSVReader component to store dataset_id
- [ ] Update ColumnSelectionPage to use dataset_id
- [ ] Update univariate analysis to include dataset_id
- [ ] Update fine binning to use new response structure
- [ ] Update WOE/IV display components
- [ ] Update results components to use new data structure

### Phase 4: Testing 🔄
- [ ] Test CSV upload flow
- [ ] Test feature classification
- [ ] Test coarse binning
- [ ] Test fine binning
- [ ] Test WOE/IV calculation
- [ ] Test model training
- [ ] Test scorecard generation
- [ ] End-to-end testing

### Phase 5: Cleanup 🔄
- [ ] Remove old db.py (or rename to db_old.py)
- [ ] Remove old database.sql
- [ ] Update documentation
- [ ] Remove unused code

## Binning Totals Usage

The new `binning_totals` table stores aggregate statistics for each binning step:

```python
# Example: Creating totals after coarse binning
step_id = create_binning_step(feature_id, 'coarse', 'qcut', num_bins=5, iv_value=0.045)

# Create bins...
create_bins_batch(step_id, bins_data)

# Create totals
create_binning_totals(
    binning_step_id=step_id,
    total_good=1800,
    total_bad=300,
    total_count=2100,
    good_bad_ratio=6.0,
    bad_rate=0.1428,
    freq_percent=100.0,
    iv=0.045
)

# Retrieve totals
totals = get_binning_totals(step_id)
# Returns: {
#   id: 1,
#   binning_step_id: 1,
#   total_good: 1800,
#   total_bad: 300,
#   total_count: 2100,
#   good_bad_ratio: 6.0,
#   bad_rate: 0.1428,
#   freq_percent: 100.0,
#   iv: 0.045
# }
```

## Testing Commands

```bash
# 1. Setup database
cd backend
./setup_database.sh

# 2. Test new schema
python test_new_schema.py

# 3. Start backend
python app.py

# 4. Start frontend
cd ..
npm run dev

# 5. Test complete workflow
# - Upload CSV
# - Classify columns
# - Run coarse binning
# - Run fine binning
# - View WOE/IV
# - Train models
```

## Rollback Plan

If issues occur:
1. Stop application
2. Restore old database: `python validate_and_migrate_schema.py --restore-backup`
3. Revert code: `git checkout app.py`
4. Restart with old schema

## Success Criteria

- ✅ All endpoints working without errors
- ✅ Data persisted correctly in normalized tables
- ✅ Frontend displays results correctly
- ✅ No data loss during migration
- ✅ Performance improved (faster queries)
- ✅ Complete workflow functional: Upload → Classify → Bin → Train → Score
