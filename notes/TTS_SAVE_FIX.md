# Train/Test Split Save Fix

## Issues Fixed

### 1. Key Conflict in split_info Dictionary
**Problem:** The `split_info` dictionary used `'test_size'` for both:
- The proportion (0.2 for 20%)
- The count (2000 rows)

This caused the count to overwrite the proportion.

**Fix:** Changed to use separate keys:
- `'test_size'` → Proportion (0.2)
- `'test_size_count'` → Count (2000)

### 2. Database Save Function Issues
**Problem:** The save function was using the wrong key for test_size count.

**Fix:** Updated to use `test_size_count` with fallback for backward compatibility.

### 3. Missing Error Handling
**Problem:** No verification that columns exist or that save succeeded.

**Fix:** Added:
- Column existence check
- Record existence check
- Post-save verification
- Detailed logging

## Files Modified

1. **`train_test_split.py`**
   - Changed `split_info` to use `test_size_count` for count
   - Updated `verify_split_match()` to use correct key
   - Updated display messages

2. **`db.py`**
   - Fixed `save_train_test_split_metadata()` to use `test_size_count`
   - Fixed `get_train_test_split_info()` to return `test_size_count`
   - Added column existence check
   - Added verification logging

3. **`app.py`**
   - Fixed API endpoints to use `test_size_count` correctly
   - Added fallback for backward compatibility

## How to Verify It's Working

### Step 1: Ensure Columns Exist
```bash
# Run migration if needed
cd backend
python3 validate_and_migrate_schema.py
```

### Step 2: Create a Train/Test Split
```bash
curl -X POST http://localhost:5000/api/train-test-split \
  -H "Content-Type: application/json" \
  -d '{"dataset_id": 1, "test_size": 0.2}'
```

### Step 3: Check Backend Logs
You should see:
```
[DB] Saving train/test split for dataset 1:
  Seed: 42
  Test size (proportion): 0.2
  Test size (count): 2000
  Train size: 8000
  Train bad: 160
  Test bad: 40
[DB] ✅ Successfully saved train/test split metadata for dataset 1 (1 row updated)
[DB] ✅ Verified: Saved seed=42, train=8000, test=2000
```

### Step 4: Verify in Database
```sql
SELECT 
    train_test_split_seed,
    train_test_split_size,
    train_test_split_method,
    train_size,
    test_size,
    train_bad_count,
    test_bad_count,
    split_created_at
FROM records
WHERE id = 1;
```

### Step 5: Get via API
```bash
curl http://localhost:5000/api/train-test-split/1
```

Expected response:
```json
{
  "exists": true,
  "split_info": {
    "seed": 42,
    "test_size": 0.2,
    "method": "stratified",
    "train_size": 8000,
    "test_size_count": 2000,
    "train_bad_count": 160,
    "test_bad_count": 40,
    ...
  }
}
```

## Troubleshooting

### Issue: "Train/test split columns do not exist"
**Solution:** Run migration:
```bash
python3 validate_and_migrate_schema.py
```

### Issue: "UPDATE affected 0 rows"
**Solution:** Verify dataset_id exists:
```sql
SELECT id, name FROM records WHERE id = 1;
```

### Issue: Data not appearing in database
**Check:**
1. Backend logs for error messages
2. Database connection is working
3. Columns exist (see Step 1)
4. Dataset ID is correct

## Key Changes Summary

| Before | After |
|--------|-------|
| `split_info['test_size']` = proportion | `split_info['test_size']` = proportion |
| `split_info['test_size']` = count (overwrites!) | `split_info['test_size_count']` = count |
| No column check | Column existence verified |
| No save verification | Post-save verification added |
| Minimal logging | Detailed logging |

## Testing Checklist

- [ ] Columns exist in database
- [ ] Create split via API succeeds
- [ ] Backend logs show save confirmation
- [ ] Database query shows saved data
- [ ] GET endpoint returns correct data
- [ ] Split can be reused (not recalculated)

