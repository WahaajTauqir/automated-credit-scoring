# Complete Database Migration Guide
## From Old JSON Schema (db_old.py) to New Normalized Schema (db.py)

**Date:** November 14, 2025  
**Status:** IN PROGRESS  
**Branch:** MVP-5.4-DatabaseRestructure

---

## Overview

This guide documents the complete migration from the old JSON-based database storage to the new normalized relational schema.

### Old Schema (db_old.py)
- **records** table: Stores JSON blobs for univariate_results, finebin_results, woe_iv_results
- **finebin_details** table: Stores bin merge information

### New Schema (db.py)
- **datasets**: One row per credit scoring run
- **features**: Columns/variables for each dataset
- **binning_steps**: Coarse and fine binning operations
- **bins**: Individual bin details with all metrics
- **merged_bins**: Tracks which bins were merged in fine binning
- **binning_totals**: Summary statistics for binning operations

---

## Changes Made So Far

### ✅ Step 1: Updated Imports
**File:** `backend/app.py`

Removed all `db_old` imports. Now only imports from `db.py`.

### ✅ Step 2: Added Helper Functions
**File:** `backend/app.py`

Added these helper functions after line 55:

```python
def format_dataset_to_record(dataset_dict):
    """Convert new schema dataset to old record format for frontend compatibility."""
    
def format_bin_to_dict(bin_record):
    """Convert bin record to frontend format."""
    
def format_bin_to_woe_dict(bin_record):
    """Convert bin record to WOE/IV format."""
    
def save_coarse_binning_to_db(feature_id, bins_df, var_type):
    """Save coarse binning results to normalized schema."""
```

---

## Required Changes

### 1. Update `/api/records` Endpoint

**Current Implementation:** Uses `get_records_db()` from db_old

**New Implementation:**
```python
@app.route('/api/records', methods=['GET'])
def get_records():
    """List all datasets in old record format for compatibility."""
    try:
        datasets = get_all_datasets()
        records = [format_dataset_to_record(d) for d in datasets]
        return jsonify(records)
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
```

### 2. Update `/api/record/<int:record_id>` GET Endpoint

**Current Implementation:** Uses `get_record_db(record_id)` from db_old

**New Implementation:**
```python
@app.route('/api/record/<int:record_id>', methods=['GET'])
def get_record(record_id):
    """Get specific dataset in old record format."""
    try:
        dataset = get_dataset(record_id)
        if dataset:
            record = format_dataset_to_record(dataset)
            return jsonify(record)
        return jsonify({"error": "Record not found"}), 404
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
```

### 3. Update `/api/record/<int:record_id>` DELETE Endpoint

**Current Implementation:** Uses `delete_record_db(record_id)` from db_old

**New Implementation:**
```python
@app.route('/api/record/<int:record_id>', methods=['DELETE'])
def delete_record(record_id):
    """Delete dataset (cascade deletes features, binning, etc.)."""
    try:
        dataset = get_dataset(record_id)
        if dataset:
            delete_dataset(record_id)
            return jsonify({"success": True})
        return jsonify({"error": "Dataset not found"}), 404
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
```

### 4. Update `/api/latest-record-dataset-path` Endpoint

**Current Implementation:** Uses `get_latest_record_dataset_path_db()` from db_old

**New Implementation:**
```python
@app.route('/api/latest-record-dataset-path', methods=['GET'])
def latest_record_dataset_path():
    """Get path of latest dataset."""
    try:
        dataset = get_latest_dataset()
        if not dataset:
            return jsonify({"dataset_path": None, "resolved_path": None, "valid": False})
        
        dataset_path = dataset.get('file_path')
        resolved = dataset_path
        if dataset_path and not os.path.isabs(dataset_path):
            resolved = os.path.join(os.path.dirname(__file__), dataset_path)
        valid = bool(resolved and os.path.exists(resolved))
        
        return jsonify({
            "dataset_path": dataset_path,
            "resolved_path": resolved,
            "valid": valid
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
```

### 5. Update `/api/upsert-single-record` Endpoint

**Current Implementation:** Uses `upsert_single_record_db()` from db_old

**New Implementation:**
```python
@app.route('/api/upsert-single-record', methods=['POST'])
def upsert_single_record():
    """Create or update dataset and features."""
    try:
        data = request.get_json()
        
        dataset_path = data.get('dataset_path', 'uploaded.csv')
        discrete_columns = data.get('discrete_columns', [])
        continuous_columns = data.get('continuous_columns', [])
        selected_columns = data.get('selected_columns', [])
        target_variable = data.get('target_variable', '')
        
        latest = get_latest_dataset()
        
        if latest is None:
            dataset_id = create_dataset(
                name=f"Dataset {dataset_path}",
                file_path=dataset_path,
                total_features=len(discrete_columns) + len(continuous_columns),
                discrete_features=len(discrete_columns),
                continuous_features=len(continuous_columns),
                target_variable=target_variable
            )
        else:
            dataset_id = latest['id']
            update_dataset(
                dataset_id=dataset_id,
                target_variable=target_variable,
                file_path=dataset_path,
                total_features=len(discrete_columns) + len(continuous_columns),
                discrete_features=len(discrete_columns),
                continuous_features=len(continuous_columns)
            )
        
        # Update features
        existing_features = get_features_by_dataset(dataset_id)
        existing_names = {f['name'] for f in existing_features}
        all_columns = set(discrete_columns + continuous_columns)
        
        # Create new features
        for col in all_columns:
            if col not in existing_names:
                var_type = 'discrete' if col in discrete_columns else 'continuous'
                is_selected = col in selected_columns
                create_feature(
                    dataset_id=dataset_id,
                    name=col,
                    feature_type=var_type,
                    selected=is_selected
                )
        
        # Update existing features
        for feature in existing_features:
            if feature['name'] in all_columns:
                new_type = 'discrete' if feature['name'] in discrete_columns else 'continuous'
                is_selected = feature['name'] in selected_columns
                update_feature(feature['id'], type=new_type, selected=is_selected)
        
        return jsonify({"success": True, "id": dataset_id})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
```

### 6. Update `/api/univariate-analysis` Endpoint

**Current Implementation:** Returns JSON results, doesn't store in DB

**New Implementation:** Store results in binning_steps and bins tables
```python
@app.route('/api/univariate-analysis', methods=['POST'])
def univariate_analysis():
    """Perform coarse binning and store in normalized schema."""
    try:
        req = request.get_json()
        discrete_cols = req.get('discrete', [])
        continuous_cols = req.get('continuous', [])
        target = req.get('target')
        
        if not target:
            return jsonify({"error": "Missing target"}), 400
        
        csv_path = get_csv_path()
        df = pd.read_csv(csv_path)
        
        if target not in df.columns:
            return jsonify({"error": f"Target '{target}' not found"}), 400
        
        df[target] = df[target].fillna(0).astype(int)
        
        results = {}
        dataset = get_latest_dataset()
        
        for col in discrete_cols:
            if col != target and col in df.columns:
                stats, _, _ = coarse_bin_discrete(df, col, target)
                results[col] = {
                    'type': 'discrete',
                    'stats': stats.to_dict(orient='records')
                }
                # Store in DB
                if dataset:
                    feature = get_feature_by_name(dataset['id'], col)
                    if feature:
                        save_coarse_binning_to_db(feature['id'], stats, 'discrete')
        
        for col in continuous_cols:
            if col != target and col in df.columns:
                stats, _ = coarse_bin_continuous(df, col, target)
                results[col] = {
                    'type': 'continuous',
                    'stats': stats.to_dict(orient='records')
                }
                # Store in DB
                if dataset:
                    feature = get_feature_by_name(dataset['id'], col)
                    if feature:
                        save_coarse_binning_to_db(feature['id'], stats, 'continuous')
        
        return jsonify(results)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
```

### 7. Update `/api/fine-bin` Endpoint

**Current Implementation:** Uses `save_finebin_details_db()` and stores in records table

**New Implementation:** Store in binning_steps, bins, and merged_bins tables
```python
@app.route('/api/fine-bin', methods=['POST'])
def fine_bin_api():
    """Perform fine binning and store in normalized schema."""
    try:
        req = request.get_json()
        var = req.get('variable')
        target = req.get('target')
        var_type = req.get('type')
        bin_merges = req.get('bin_merges', {})
        
        if not var or not target or not var_type:
            return jsonify({"error": "Missing required fields"}), 400
        
        csv_path = get_csv_path()
        df = pd.read_csv(csv_path)
        df[target] = df[target].fillna(0).astype(int)

        # Perform binning
        if var_type == 'continuous':
            _, df[f'{var}_binned'] = coarse_bin_continuous(df, var, target)
            existing_bins = set(df[f'{var}_binned'].unique())
            bin_merges = {k: [b for b in v if b in existing_bins] for k, v in bin_merges.items()}
            bin_merges = {k: v for k, v in bin_merges.items() if v}
            tab, _, adjusted_merges, _ = fine_bin_continuous(df, var, target, bin_merges)
        else:
            _, df[f'{var}_binned'], bin_mapping = coarse_bin_discrete(df, var, target)
            tab, _, adjusted_merges = fine_bin_discrete(df, var, target, bin_merges, bin_mapping)

        if tab is None:
            return jsonify({"error": "Fine binning returned no results"}), 400

        # Calculate WOE/IV
        iv, woe_stats = calculate_woe_iv(df, var, target, adjusted_merges, var_type)

        # Store in DB
        dataset = get_latest_dataset()
        if dataset:
            feature = get_feature_by_name(dataset['id'], var)
            if feature:
                # Create fine binning step
                step_id = create_binning_step(
                    feature_id=feature['id'],
                    step_type='fine',
                    method='merged',
                    num_bins=len(tab),
                    iv_value=iv
                )
                
                # Store bins
                bins_data = []
                for idx, row in tab.iterrows():
                    bin_data = {
                        'bin_number': idx + 1,
                        'bin_label': str(row['Bin']),
                        'good_count': int(row['Good']),
                        'bad_count': int(row['Bad']),
                        'total_count': int(row['Total'])
                    }
                    if 'Min' in row:
                        bin_data['min_value'] = float(row['Min'])
                    if 'Max' in row:
                        bin_data['max_value'] = float(row['Max'])
                    if 'Range' in row:
                        bin_data['range_text'] = str(row['Range'])
                    bins_data.append(bin_data)
                
                create_bins_batch(step_id, bins_data)
                
                # Store merge information
                if adjusted_merges:
                    for merged_label, original_labels in adjusted_merges.items():
                        create_merged_bin(
                            fine_step_id=step_id,
                            merged_bin_number=int(merged_label.split('_')[-1]) if '_' in merged_label else 1,
                            original_bin_ids=[],  # IDs not available here
                            original_bin_labels=original_labels
                        )

        return jsonify({
            "success": True,
            "stats": tab.to_dict(orient='records'),
            "bin_merges": adjusted_merges,
            "woe_iv": {"iv": iv, "stats": woe_stats}
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
```

### 8. Update `/api/finebin-details` Endpoints

**Current Implementation:** Uses finebin_details table

**New Implementation:** Use merged_bins table

```python
@app.route('/api/finebin-details', methods=['POST'])
def save_finebin_details():
    """Save bin merge details (now uses merged_bins table)."""
    data = request.get_json()
    record_id = data.get('record_id')
    column_name = data.get('column_name')
    bin_merges = data.get('bin_merges')
    
    if not record_id or not column_name or not isinstance(bin_merges, dict):
        return jsonify({"error": "Missing required fields"}), 400
    
    try:
        dataset = get_dataset(record_id)
        if not dataset:
            return jsonify({"error": "Dataset not found"}), 404
        
        feature = get_feature_by_name(record_id, column_name)
        if not feature:
            return jsonify({"error": "Feature not found"}), 404
        
        fine_step = get_binning_step_by_type(feature['id'], 'fine')
        if not fine_step:
            return jsonify({"error": "Fine binning not found"}), 404
        
        # Delete existing merged_bins for this step
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM merged_bins WHERE fine_step_id = %s", (fine_step['id'],))
        conn.commit()
        
        # Insert new merged_bins
        for merged_label, original_labels in bin_merges.items():
            create_merged_bin(
                fine_step_id=fine_step['id'],
                merged_bin_number=int(merged_label.split('_')[-1]) if '_' in merged_label else 1,
                original_bin_ids=[],
                original_bin_labels=original_labels
            )
        
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/finebin-details/<int:record_id>/<string:column_name>', methods=['GET'])
def get_finebin_details(record_id, column_name):
    """Retrieve bin merge details from merged_bins table."""
    try:
        dataset = get_dataset(record_id)
        if not dataset:
            return jsonify({"error": "Dataset not found"}), 404
        
        feature = get_feature_by_name(record_id, column_name)
        if not feature:
            return jsonify({"error": "Feature not found"}), 404
        
        fine_step = get_binning_step_by_type(feature['id'], 'fine')
        if not fine_step:
            return jsonify([])  # No fine binning yet
        
        merged_bins = get_merged_bins_by_step(fine_step['id'])
        
        # Convert to old format
        result = []
        for mb in merged_bins:
            result.append({
                'group_id': str(mb['merged_bin_number']),
                'merged_bins': json.dumps(mb['original_bin_labels'])
            })
        
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
```

### 9. Update `/api/save-record` Endpoint

**Current Implementation:** Uses `save_record_db()` from db_old

**New Implementation:** Not needed anymore - data is saved incrementally via other endpoints

```python
# This endpoint can be removed or kept as a no-op for compatibility
@app.route('/api/save-record', methods=['POST'])
def save_record():
    """Legacy endpoint - data is now saved incrementally."""
    return jsonify({"success": True, "message": "Data saved via new schema"})
```

---

## Migration Status

### ✅ Completed
- [x] Removed db_old imports
- [x] Added helper functions for format conversion
- [x] Documented all required changes

### 🔄 In Progress
- [ ] Update all API endpoints to use new schema
- [ ] Test each endpoint individually
- [ ] Verify frontend compatibility

### ⏳ Remaining
- [ ] Update WOE/IV calculation endpoint to store in bins table
- [ ] Update auto-monotonic-binning endpoint
- [ ] Update reset-bins endpoint
- [ ] Test complete end-to-end workflow
- [ ] Update frontend if needed
- [ ] Remove db_old.py completely

---

## Testing Checklist

### Backend API Tests
- [ ] Upload CSV → creates dataset and features
- [ ] Classify columns → updates feature types
- [ ] Select target → updates dataset.target_variable
- [ ] Univariate analysis → stores coarse binning
- [ ] Fine binning → stores fine binning and merges
- [ ] WOE/IV calculation → updates bins with WOE/IV values
- [ ] Auto-monotonic binning → performs and stores results
- [ ] Save/load records → uses new schema
- [ ] Delete record → cascade deletes all related data

### Frontend Integration Tests
- [ ] CSV upload works
- [ ] Column classification works
- [ ] Univariate results display correctly
- [ ] Fine binning UI works
- [ ] WOE/IV results display correctly
- [ ] Model training works with new data format

---

## Rollback Plan

If issues arise:
1. Keep backup of current app.py
2. db_old.py is still present in backend folder
3. Can restore old imports and revert changes
4. Old schema tables (records, finebin_details) still exist in database

---

## Next Steps

1. **Implement remaining endpoint changes** (use this guide)
2. **Test each endpoint** with Postman or curl
3. **Run frontend** and verify all features work
4. **Fix any issues** that arise
5. **Remove db_old.py** once fully migrated
6. **Update documentation** with final results

---

## Notes

- Frontend expects data in old format (JSON strings)
- Helper functions convert new schema → old format
- This maintains backward compatibility
- Later, frontend can be updated to use new format directly

