# Train/Test Split Implementation Guide

## Overview

This document describes the train/test split implementation to prevent data leakage in the credit scoring pipeline.

## Key Principle

**TEST SET IS NEVER SEEN until final evaluation!**

**New Flow (Option 1):**
- Preprocessing happens on FULL dataset first (cleaning, basic transformations)
- Train/Test split happens on PREPROCESSED data
- All learning (binning, WOE calculation, model training) happens on the TRAIN set only

**Benefits:**
- Split is done on clean, preprocessed data
- Ensures consistent data quality before splitting
- Preprocessed train/test files are saved for efficient loading

## Pipeline Flow

```
1. Data Upload
   ↓
2. Variable Classification (discrete/continuous, target)
   ↓
3. Preprocessing (FULL DATASET)
   ├─ Clean: remove duplicates, handle missing values
   ├─ Detect: column types (discrete/continuous)
   └─ Prepare: data for splitting
   ↓
4. ⚠️ TRAIN/TEST SPLIT (80/20, stratified) ⚠️
   ├─ Split happens on PREPROCESSED data
   ├─ Train Set (70%) → Lock for learning
   ├─ Test Set (30%) → Lock until evaluation
   └─ Save: preprocessed train/test files
   ↓
5. Coarse Binning (TRAIN ONLY)
   ├─ Learn: bin boundaries (quantiles, frequency)
   └─ Apply same boundaries to TEST
   ↓
6. Fine Binning / Monotonic Binning (TRAIN ONLY)
   ├─ Learn: merged bins, monotonic adjustments
   └─ Apply same merges to TEST
   ↓
7. WOE Calculation (TRAIN ONLY)
   ├─ Learn: WOE values for each bin
   └─ Apply same WOE mappings to TEST
   ↓
8. Model Training
   ├─ Train: on TRAIN set with WOE features
   └─ Evaluate: on TRAIN set (for overfitting check)
   ↓
9. Model Evaluation (FIRST TIME SEEING TEST!)
   ├─ Load: preprocessed TEST set
   ├─ Apply: learned transformations to TEST
   ├─ Predict: using trained model on TEST
   └─ Evaluate: final metrics on TEST
   ↓
10. Scorecard Generation
    ├─ Train: scorecard parameters from TRAIN
    └─ Validate: scorecard on TEST
```

## Database Schema Changes

Added to `records` table:
- `train_test_split_seed`: Random seed for reproducibility
- `train_test_split_size`: Test proportion (0.2 for 20%)
- `train_test_split_method`: Split method ('stratified')
- `train_size`: Number of rows in train set
- `test_size`: Number of rows in test set
- `train_bad_count`: Bad cases in train set
- `test_bad_count`: Bad cases in test set
- `split_created_at`: When split was created
- `data_hash`: Hash to detect data changes

## New Modules

### 1. `train_test_split.py`
- `create_stratified_split()`: Create 80/20 stratified split
- `regenerate_split()`: Recreate split using stored parameters
- `get_or_create_train_test_split()`: Smart function that reuses or creates split
- `save_split_files()`: Save train/test as separate CSV files

### 2. `data_loader.py`
- `get_data_for_stage()`: Returns correct dataset based on pipeline stage
  - `'binning'` → TRAIN set
  - `'woe'` → TRAIN set
  - `'training'` → TRAIN set
  - `'evaluation'` → TEST set
- `get_train_test_data()`: Load both train and test datasets
- `check_split_required()`: Check if split exists

### 3. Database Functions (`db.py`)
- `save_train_test_split_metadata()`: Save split info to DB
- `get_train_test_split_info()`: Retrieve split info
- `clear_train_test_split()`: Clear split metadata

## Modified API Endpoints

### New Endpoints
- `POST /api/train-test-split`: Create or get train/test split
- `GET /api/train-test-split/<dataset_id>`: Get split info

### Modified Endpoints (now use train set only)
- `/api/univariate-analysis`: Coarse binning on TRAIN set
- `/api/auto-monotonic-binning`: Fine binning on TRAIN set
- `/api/logistic-regression`: Train on TRAIN, evaluate on TEST
- `/api/random-forest`: Train on TRAIN, evaluate on TEST
- `/api/xgboost`: Train on TRAIN, evaluate on TEST

## Stratified Split Behavior

For imbalanced data (e.g., 2% default rate):

```
Full Dataset: 10,000 rows
├─ Bad: 200 (2%)
└─ Good: 9,800 (98%)

After 80/20 Stratified Split:
├─ Train: 8,000 rows
│  ├─ Bad: 160 (2% maintained!)
│  └─ Good: 7,840 (98%)
└─ Test: 2,000 rows
   ├─ Bad: 40 (2% maintained!)
   └─ Good: 1,960 (98%)
```

Stratification ensures:
1. Class distribution is the same in train and test
2. Test set has enough bad cases for evaluation
3. Model sees representative data in both sets

## Data Leakage Prevention Checklist

✅ **Binning boundaries learned from train only**
- Bin edges, quantiles calculated on train set
- Same edges applied to test set

✅ **WOE values calculated from train only**
- Good/Bad ratios from train set
- Same WOE mappings applied to test set

✅ **Model trained on train only**
- All hyperparameters tuned on train set
- Test set never seen during training

✅ **Evaluation on test only**
- Final metrics (AUC, Gini, KS) on test set
- Test set provides unbiased performance estimate

❌ **Common Data Leakage Mistakes (AVOIDED)**
- ❌ Calculating WOE on full dataset
- ❌ Using test set for feature selection
- ❌ Training on full dataset
- ❌ Normalizing/scaling based on full dataset

## Usage Example

### 1. Create Split (after preprocessing)
```python
POST /api/train-test-split
{
  "dataset_id": 1,
  "test_size": 0.2  # 20% test
}

Response:
{
  "success": true,
  "split_info": {
    "train_size": 8000,
    "test_size": 2000,
    "train_bad_count": 160,
    "test_bad_count": 40,
    "stratification_success": true
  },
  "is_existing": false
}
```

### 2. Binning (automatically uses train set)
```python
POST /api/univariate-analysis
# Now automatically uses TRAIN set if split exists
# Bins are learned from train data only
```

### 3. Model Training (uses train, evaluates on test)
```python
POST /api/logistic-regression
{
  "dataset_id": 1,
  "selected_variables": ["age", "income"],
  "target": "default"
}

Response:
{
  "train_metrics": {
    "auc": 0.85,
    "gini": 0.70
  },
  "test_metrics": {  # FIRST time seeing test data!
    "auc": 0.78,      # Realistic performance
    "gini": 0.56
  },
  "overfitting_gap": 0.07
}
```

## Frontend Integration

### Add TTS Creation Step
```typescript
// After variable classification, before binning
const createTrainTestSplit = async () => {
  const response = await fetch('/api/train-test-split', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      dataset_id: datasetId,
      test_size: 0.2
    })
  });
  const data = await response.json();
  
  if (data.success) {
    setSplitInfo(data.split_info);
    alert(`Split created: ${data.split_info.train_size} train, ${data.split_info.test_size} test`);
  }
};
```

### Display Split Info
```typescript
{splitInfo && (
  <div className="split-info">
    <h3>Train/Test Split</h3>
    <p>Training: {splitInfo.train_size} rows ({splitInfo.train_bad_count} bad)</p>
    <p>Test: {splitInfo.test_size} rows ({splitInfo.test_bad_count} bad)</p>
    <p>Stratification: {splitInfo.stratification_success ? '✓' : '✗'}</p>
  </div>
)}
```

## Verification

To verify train/test split is working correctly:

1. **Check split exists:**
   ```bash
   curl http://localhost:5000/api/train-test-split/1
   ```

2. **Check binning uses train set:**
   - Look for logs: `[DATA_LOADER] Stage 'binning': Using TRAIN set`
   - Verify bin counts match train set size, not full dataset

3. **Check model metrics:**
   - Train AUC should be higher than test AUC
   - Gap of 0.05-0.10 is normal
   - Gap > 0.15 indicates overfitting

## Troubleshooting

### Issue: "No train/test split exists"
**Solution:** Create split before binning:
```bash
POST /api/train-test-split with dataset_id
```

### Issue: Test metrics missing
**Solution:** Ensure model training endpoint evaluates on test set

### Issue: Train and test metrics are identical
**Problem:** Model is evaluating on same data!
**Solution:** Check data_loader is returning different datasets for train/test

### Issue: Stratification failed
**Problem:** Too few samples or extreme class imbalance
**Solution:** Adjust min_test_bad parameter or collect more data

## Migration Path

For existing datasets:
1. Dataset already uploaded → Create TTS now
2. Binning already done → Redo binning on train set only
3. Models already trained → Retrain on train set, evaluate on test

The system will warn if binning/training happens without TTS.

