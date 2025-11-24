# Automatic Train/Test Split Creation

## ✅ Implementation Complete

Train/Test Split (TTS) is now **automatically created** right after the target variable is selected, ensuring it happens before any preprocessing or binning.

## 🎯 Where TTS is Created

### 1. Frontend (Automatic)
**Files Modified:**
- `src/App.tsx` - Main app component
- `src/components/SelectedColumnsPage.tsx` - Column selection page

**When:** Immediately after user selects target variable

**What Happens:**
```typescript
// User selects target variable
setTargetVariable('default')

// useEffect triggers:
1. Persist target variable to backend
2. Automatically call POST /api/train-test-split
3. Create 80/20 stratified split
4. Log success/failure to console
```

### 2. Backend (Automatic)
**File Modified:**
- `backend/app.py` - `/api/upsert-single-record` endpoint

**When:** When target variable is updated via API

**What Happens:**
```python
# Target variable is set/updated
update_dataset(dataset_id, target_variable='default')

# Automatically:
1. Load dataset CSV
2. Create or get train/test split (80/20)
3. Save split metadata to database
4. Log success/failure
```

## 📋 Workflow

```
1. User uploads CSV
   ↓
2. User classifies variables (discrete/continuous)
   ↓
3. User selects target variable ⚠️
   ↓
4. 🎯 AUTOMATIC: Train/Test Split Created (80/20 stratified)
   ├─ Frontend: Calls POST /api/train-test-split
   └─ Backend: Creates split, saves to database
   ↓
5. User proceeds to binning
   ├─ Binning automatically uses TRAIN set
   └─ No data leakage!
   ↓
6. User trains models
   ├─ Training on TRAIN set
   └─ Evaluation on TEST set
```

## 🔍 Verification

### Check Console Logs

**Frontend (Browser Console):**
```
[TTS] Creating train/test split after target variable selection...
[TTS] ✅ Train/test split created successfully: {train_size: 8000, test_size_count: 2000, ...}
[TTS] Split: 8000 train, 2000 test
```

**Backend (Terminal/Logs):**
```
[TTS] Target variable "default" set - automatically creating train/test split...
[SPLIT] Original dataset: 10000 samples
[SPLIT] Bad: 200 (2.00%), Good: 9800 (98.00%)
[SPLIT] Training set: 8000 samples
  Bad: 160 (2.00%), Good: 7840 (98.00%)
[SPLIT] Test set: 2000 samples
  Bad: 40 (2.00%), Good: 1960 (98.00%)
✓ Stratification successful: distributions match within 1%
[DB] ✅ Successfully saved train/test split metadata for dataset 1
[TTS] ✅ Train/test split created: 8000 train, 2000 test
```

### Check Database

```sql
SELECT 
    train_test_split_seed,
    train_test_split_size,
    train_size,
    test_size,
    train_bad_count,
    test_bad_count,
    split_created_at
FROM records
WHERE id = 1;
```

Expected result:
```
seed: 42
test_size: 0.2
train_size: 8000
test_size: 2000
train_bad_count: 160
test_bad_count: 40
split_created_at: 2024-01-15 14:30:00
```

### Check API

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

## 🎨 User Experience

### Before (Manual)
1. User selects target variable
2. User must remember to create TTS
3. User manually calls TTS endpoint
4. Easy to forget → data leakage risk

### After (Automatic)
1. User selects target variable
2. ✅ TTS automatically created
3. User proceeds with workflow
4. No data leakage risk

## ⚙️ Configuration

### Split Parameters
- **Test Size:** 20% (0.2) - hardcoded
- **Train Size:** 80% (0.8) - automatic
- **Method:** Stratified (maintains class distribution)
- **Seed:** 42 (for reproducibility)

### To Change Test Size
Edit in two places:
1. `src/App.tsx` - line ~2320: `test_size: 0.2`
2. `src/components/SelectedColumnsPage.tsx` - line ~640: `test_size: 0.2`
3. `backend/app.py` - line ~5400: `test_size=0.2`

## 🐛 Troubleshooting

### Issue: TTS not created
**Check:**
1. Browser console for errors
2. Backend logs for errors
3. Target variable is actually set
4. Dataset ID is valid

### Issue: "Target variable not found in dataset"
**Cause:** Target variable name doesn't match CSV column
**Solution:** Verify target variable name matches CSV column exactly

### Issue: "Could not load dataset for TTS"
**Cause:** CSV file path is incorrect or file doesn't exist
**Solution:** Verify dataset was uploaded correctly

### Issue: TTS created but not saved to database
**Check:**
1. Database columns exist (run migration)
2. Backend logs show save confirmation
3. Database connection is working

## 📝 Notes

1. **Idempotent:** If TTS already exists, it's reused (not recreated)
2. **Non-blocking:** TTS creation doesn't block the UI
3. **Error handling:** If TTS creation fails, the request still succeeds
4. **Logging:** All TTS operations are logged for debugging

## ✨ Benefits

1. **Automatic:** No manual step required
2. **Early:** Created before any preprocessing/binning
3. **Consistent:** Same parameters every time
4. **Safe:** Prevents data leakage by default
5. **Transparent:** Logged in console for visibility

## 🎉 Result

Now when users select a target variable, the train/test split is **automatically created** without any manual intervention. This ensures:

- ✅ TTS always exists before binning
- ✅ No data leakage possible
- ✅ Consistent 80/20 split
- ✅ Stratified for imbalanced data
- ✅ Reproducible (seed=42)

The system is now fully automated! 🚀

