# Step-by-Step Backend Migration Guide

## Current Status
✅ Schema created with 6 tables (including binning_totals)
✅ New db.py created with all CRUD operations
✅ Old files backed up (db_old.py, app_old.py)
🔄 App.py partially updated (imports changed, upload endpoint updated)
❌ Many endpoints still using old functions

## Critical Endpoints Status

### ✅ COMPLETED
1. `/api/upload-csv` - Now creates dataset + features

### 🔄 IN PROGRESS
2. `/api/ai-classify-columns` - Needs updating
3. `/api/univariate-analysis` - Needs complete rewrite
4. `/api/fine-bin` - Needs complete rewrite
5. `/api/woe-iv` - Needs complete rewrite

### ❌ NOT STARTED
- Model training endpoints (logistic, random forest, xgboost)
- Scorecard generation
- All other endpoints using old db functions

## Implementation Strategy

Given the complexity (3800+ lines), I recommend a **phased approach**:

### Phase 1: Create Adapter Functions (RECOMMENDED)
Create temporary adapter functions in app.py that translate between old and new schema:

```python
# Temporary adapter functions at top of app.py

def get_current_dataset_id():
    """Get the latest dataset ID (simulates old behavior)"""
    dataset = get_latest_dataset()
    return dataset['id'] if dataset else None

def get_or_create_dataset_id():
    """Get latest dataset or create one if none exists"""
    dataset = get_latest_dataset()
    if dataset:
        return dataset['id']
    # Create default dataset
    return create_dataset(
        name="default_dataset",
        file_path="uploaded.csv",
        total_features=0,
        discrete_features=0,
        continuous_features=0,
        target_variable=None
    )
```

### Phase 2: Update Core Endpoints One by One

#### A. `/api/univariate-analysis` (Coarse Binning)

**Current logic:**
1. Read CSV
2. Perform coarse binning (continuous/discrete)
3. Save results to records table as JSON

**New logic:**
```python
@app.route('/api/univariate-analysis', methods=['POST'])
def univariate_analysis():
    try:
        req = request.get_json()
        dataset_id = req.get('dataset_id')  # NEW: Get from frontend
        discrete_cols = req.get('discrete', [])
        continuous_cols = req.get('continuous', [])
        target = req.get('target')
        
        if not dataset_id:
            # Fallback: get latest dataset
            dataset_id = get_or_create_dataset_id()
        
        # Update dataset with target variable
        update_dataset(dataset_id, target_variable=target)
        
        # Load CSV
        csv_path = get_csv_path()
        df = pd.read_csv(csv_path)
        df[target] = df[target].fillna(0).astype(int)
        
        results = {}
        
        # Process each column
        for col in discrete_cols + continuous_cols:
            if col == target or col not in df.columns:
                continue
            
            # Get feature record
            feature = get_feature_by_name(dataset_id, col)
            if not feature:
                continue
            
            # Determine type
            is_continuous = col in continuous_cols
            var_type = 'continuous' if is_continuous else 'discrete'
            
            # Perform coarse binning
            if is_continuous:
                stats, _ = coarse_bin_continuous(df, col, target)
            else:
                stats, _, _ = coarse_bin_discrete(df, col, target)
            
            # Calculate totals
            total_good = stats['Good'].sum()
            total_bad = stats['Bad'].sum()
            total_count = stats['Total'].sum()
            
            # Calculate WOE and IV for each bin
            bins_data = []
            for idx, row in stats.iterrows():
                bin_number = idx + 1
                good = row['Good']
                bad = row['Bad']
                total = row['Total']
                
                # Calculate distributions
                dist_good = (good / total_good) if total_good > 0 else 0
                dist_bad = (bad / total_bad) if total_bad > 0 else 0
                
                # Calculate WOE
                woe = np.log(dist_good / dist_bad) if (dist_good > 0 and dist_bad > 0) else 0
                
                # Calculate IV contribution
                iv_contrib = (dist_good - dist_bad) * woe
                
                bin_data = {
                    'bin_number': bin_number,
                    'bin_label': row.get('Bin', f'Bin_{bin_number}'),
                    'good_count': int(good),
                    'bad_count': int(bad),
                    'total_count': int(total),
                    'good_bad_ratio': float(good / bad) if bad > 0 else 0,
                    'bad_rate': float(bad / total) if total > 0 else 0,
                    'freq_percent': float((total / total_count) * 100) if total_count > 0 else 0,
                    'dist_good': float(dist_good * 100),
                    'dist_bad': float(dist_bad * 100),
                    'woe': float(woe),
                    'iv': float(iv_contrib)
                }
                
                # Add min/max for continuous
                if is_continuous:
                    bin_data['min_value'] = float(row.get('Min', 0))
                    bin_data['max_value'] = float(row.get('Max', 0))
                else:
                    bin_data['range_text'] = row.get('Range', '')
                
                bins_data.append(bin_data)
            
            # Calculate total IV
            total_iv = sum([b['iv'] for b in bins_data])
            
            # Create binning step
            step_id = create_binning_step(
                feature_id=feature['id'],
                step_type='coarse',
                method='qcut' if is_continuous else 'bad_rate',
                num_bins=len(bins_data),
                is_monotonic=False,  # TODO: Check monotonicity
                monotonic_direction=None,
                iv_value=total_iv
            )
            
            # Create bins
            create_bins_batch(step_id, bins_data)
            
            # Create totals
            create_binning_totals(
                binning_step_id=step_id,
                total_good=int(total_good),
                total_bad=int(total_bad),
                total_count=int(total_count),
                good_bad_ratio=float(total_good / total_bad) if total_bad > 0 else 0,
                bad_rate=float(total_bad / total_count) if total_count > 0 else 0,
                freq_percent=100.0,
                iv=total_iv
            )
            
            results[col] = {
                'type': var_type,
                'feature_id': feature['id'],
                'step_id': step_id,
                'stats': stats.to_dict(orient='records'),
                'total_iv': total_iv
            }
        
        return jsonify({
            'success': True,
            'dataset_id': dataset_id,
            'results': results
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500
```

#### B. `/api/fine-bin` (Fine Binning with Merges)

**New logic:**
```python
@app.route('/api/fine-bin', methods=['POST'])
def fine_bin():
    try:
        req = request.get_json()
        dataset_id = req.get('dataset_id')
        var = req.get('variable')
        target = req.get('target')
        bin_merges = req.get('bin_merges')  # List of bins to merge: [[1,2], [3,4,5]]
        
        if not dataset_id:
            dataset_id = get_or_create_dataset_id()
        
        # Get feature
        feature = get_feature_by_name(dataset_id, var)
        if not feature:
            return jsonify({"error": f"Feature {var} not found"}), 404
        
        # Get coarse binning step
        coarse_step = get_binning_step_by_type(feature['id'], 'coarse')
        if not coarse_step:
            return jsonify({"error": "No coarse binning found. Run univariate analysis first."}), 400
        
        # Get coarse bins
        coarse_bins = get_bins_by_step(coarse_step['id'])
        
        # Load CSV for recalculation
        csv_path = get_csv_path()
        df = pd.read_csv(csv_path)
        df[target] = df[target].fillna(0).astype(int)
        
        # Apply merges and create new bins
        # ... (merge logic - aggregate Good/Bad counts, recalculate WOE/IV)
        
        # Create fine binning step
        fine_step_id = create_binning_step(
            feature_id=feature['id'],
            step_type='fine',
            method='merged',
            num_bins=len(bin_merges),
            is_monotonic=False,  # TODO: Check
            monotonic_direction=None,
            iv_value=total_iv
        )
        
        # Create fine bins
        create_bins_batch(fine_step_id, merged_bins_data)
        
        # Create totals
        create_binning_totals(
            binning_step_id=fine_step_id,
            total_good=total_good,
            total_bad=total_bad,
            total_count=total_count,
            good_bad_ratio=total_good / total_bad if total_bad > 0 else 0,
            bad_rate=total_bad / total_count if total_count > 0 else 0,
            freq_percent=100.0,
            iv=total_iv
        )
        
        # Record merge operations
        for merge_idx, merge_group in enumerate(bin_merges):
            create_merged_bin(
                fine_step_id=fine_step_id,
                merged_bin_number=merge_idx + 1,
                original_bin_ids=[coarse_bins[i-1]['id'] for i in merge_group],
                original_bin_labels=[coarse_bins[i-1]['bin_label'] for i in merge_group]
            )
        
        return jsonify({
            'success': True,
            'dataset_id': dataset_id,
            'feature_id': feature['id'],
            'fine_step_id': fine_step_id
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500
```

#### C. `/api/woe-iv` (Retrieve WOE/IV Results)

**New logic:**
```python
@app.route('/api/woe-iv', methods=['POST'])
def woe_iv():
    try:
        req = request.get_json()
        dataset_id = req.get('dataset_id')
        
        if not dataset_id:
            dataset_id = get_or_create_dataset_id()
        
        # Get all selected features
        features = get_features_by_dataset(dataset_id)
        selected_features = [f for f in features if f['selected']]
        
        results = {}
        
        for feature in selected_features:
            # Get fine binning if exists, else coarse
            fine_results = get_complete_binning_results(feature['id'], 'fine')
            coarse_results = get_complete_binning_results(feature['id'], 'coarse')
            
            binning_data = fine_results if fine_results else coarse_results
            
            if not binning_data:
                continue
            
            results[feature['name']] = {
                'feature_id': feature['id'],
                'feature_name': feature['name'],
                'feature_type': feature['type'],
                'binning_type': binning_data['binning_step']['step_type'],
                'num_bins': binning_data['binning_step']['num_bins'],
                'is_monotonic': binning_data['binning_step']['is_monotonic'],
                'total_iv': binning_data['binning_step']['iv_value'],
                'bins': binning_data['bins'],
                'totals': binning_data['totals']
            }
        
        return jsonify({
            'success': True,
            'dataset_id': dataset_id,
            'results': results
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500
```

## Frontend Changes Required

### 1. Update State Management

**src/components/CSVReader.tsx**:
```typescript
// After successful upload
const response = await fetch('/api/upload-csv', formData)
const data = await response.json()

// Store dataset_id in state or context
setDatasetId(data.dataset_id)
localStorage.setItem('dataset_id', data.dataset_id)
```

### 2. Update API Calls

**All subsequent API calls should include dataset_id**:
```typescript
// Before
const response = await fetch('/api/univariate-analysis', {
  body: JSON.stringify({
    discrete, continuous, target
  })
})

// After
const datasetId = localStorage.getItem('dataset_id')
const response = await fetch('/api/univariate-analysis', {
  body: JSON.stringify({
    dataset_id: datasetId,  // ADD THIS
    discrete, continuous, target
  })
})
```

### 3. Update Result Parsing

Components need to handle new response structure:

**Before (JSON blob)**:
```javascript
const results = data.results
// results['age'] = {type: 'continuous', stats: [...]}
```

**After (structured)**:
```javascript
const results = data.results
// results['age'] = {
//   type: 'continuous',
//   feature_id: 1,
//   step_id: 1,
//   stats: [...],
//   total_iv: 0.045
// }
```

## Recommended Implementation Order

1. ✅ **Setup database** - `./setup_database.sh`
2. ✅ **Update upload endpoint** - Done
3. 🔄 **Add adapter functions** - Create compatibility layer
4. 🔄 **Update univariate endpoint** - Step by step
5. 🔄 **Update fine-bin endpoint**
6. 🔄 **Update woe-iv endpoint**
7. 🔄 **Test core workflow**
8. 🔄 **Update frontend state management**
9. 🔄 **Update frontend API calls**
10. 🔄 **Update frontend display components**
11. 🔄 **Update model training endpoints**
12. 🔄 **Update scorecard endpoint**
13. 🔄 **End-to-end testing**
14. 🔄 **Remove old code & cleanup**

## Testing Plan

After each endpoint update:

```python
# Test script
python test_new_schema.py  # Verify database
# Then test endpoint:
curl -X POST http://localhost:5000/api/univariate-analysis \
  -H "Content-Type: application/json" \
  -d '{
    "dataset_id": 1,
    "discrete": ["gender"],
    "continuous": ["age"],
    "target": "default"
  }'
```

## Need Help?

If you get stuck:
1. Check INTEGRATION_PLAN.md for data flow examples
2. Check DATABASE_DIAGRAM.md for schema visualization
3. Check README_DATABASE.md for function reference
4. Restore backup: `git checkout app.py` or use app_old.py

## Estimated Timeline

- Phase 1 (Adapters): 1 hour
- Phase 2 (Core endpoints): 2-3 hours
- Phase 3 (Frontend updates): 2-3 hours
- Phase 4 (Testing & refinement): 2-3 hours
- **Total: 7-10 hours of focused work**
