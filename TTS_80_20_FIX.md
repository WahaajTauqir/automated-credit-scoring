# Train/Test Split 80/20 Fix

## ✅ Issues Fixed

### 1. Split Ratio Fixed to 80/20
**Problem:** Split was creating 60/40 instead of 80/20
**Cause:** Automatic adjustment logic was increasing test_size up to 40%
**Fix:** Removed aggressive adjustment logic, now strictly enforces 80/20 (test_size=0.2)

### 2. Single Split Creation Point
**Problem:** TTS was being created in multiple places
**Fix:** Removed duplicate creation from backend upsert endpoint
**Result:** TTS is now created ONLY when target variable is selected (via frontend)

## 📍 Where TTS is Created (ONLY ONE PLACE)

### Frontend Automatic Creation
**Location:** When user selects target variable
**Files:**
- `src/App.tsx` - Lines 318-350
- `src/components/SelectedColumnsPage.tsx` - Lines 639-671

**Flow:**
```
User selects target variable
    ↓
Frontend useEffect triggers
    ↓
Calls POST /api/train-test-split with test_size=0.2
    ↓
Backend creates 80/20 split
    ↓
Saves to database
```

### Backend API Endpoint
**Location:** `/api/train-test-split` endpoint
**File:** `backend/app.py` - Lines 2260-2350
**Purpose:** Handles the actual split creation (called by frontend)

## ❌ Removed Duplicate Creation

### Backend Upsert Endpoint (REMOVED)
**Was:** `backend/app.py` - Lines 5382-5415
**Action:** Removed automatic TTS creation from `/api/upsert-single-record`
**Reason:** Frontend already handles it, avoiding duplicate creation

## 🔧 Changes Made

### 1. `train_test_split.py`
**Before:**
```python
# Adjust test_size if needed to ensure minimum bad cases
min_test_size = min_test_bad / n_bad if n_bad > 0 else test_size
actual_test_size = max(test_size, min_test_size)
actual_test_size = min(actual_test_size, 0.4)  # Cap at 40% ❌
```

**After:**
```python
# STRICT 80/20 SPLIT: Always use the requested test_size (0.2 for 20%)
actual_test_size = test_size  # Always use the requested size (0.2 for 80/20) ✅
# Only warn if test set will have very few bad cases, but don't adjust
```

### 2. `app.py` - Upsert Endpoint
**Before:**
```python
# CRITICAL: Automatically create train/test split if target variable is set
if target_variable:
    # ... creates TTS here ❌
```

**After:**
```python
# NOTE: Train/test split is created automatically by frontend when target variable is selected
# This happens via the /api/train-test-split endpoint called from frontend
# We do NOT create it here to avoid duplicate creation ✅
```

## ✅ Verification

### Check Split Ratio
```sql
SELECT 
    train_size,
    test_size,
    train_test_split_size,
    ROUND(test_size::numeric / (train_size + test_size)::numeric, 2) as actual_test_ratio
FROM records
WHERE id = 1;
```

**Expected:**
- `train_test_split_size` = 0.2 (20%)
- `actual_test_ratio` = 0.20 (20%)
- `train_size` / `test_size` ≈ 4.0 (80/20 ratio)

### Check Logs
**Backend logs should show:**
```
[SPLIT] Original dataset: 10000 samples
[SPLIT] Training set: 8000 samples (80%)
[SPLIT] Test set: 2000 samples (20%)
✓ Stratification successful
```

### Check API Response
```bash
curl http://localhost:5000/api/train-test-split/1
```

**Expected:**
```json
{
  "split_info": {
    "test_size": 0.2,  // 20% proportion
    "train_size": 8000,
    "test_size_count": 2000,
    ...
  }
}
```

## 🎯 Summary

| Aspect | Before | After |
|--------|--------|-------|
| **Split Ratio** | 60/40 (adjusted) | 80/20 (strict) ✅ |
| **Creation Points** | 2 places (frontend + backend) | 1 place (frontend only) ✅ |
| **Test Size** | Could be adjusted up to 40% | Always 20% (0.2) ✅ |
| **Adjustment Logic** | Aggressive (changes ratio) | Warning only (keeps ratio) ✅ |

## 📝 Notes

1. **Strict 80/20:** Split ratio is now always 80/20, no automatic adjustments
2. **Single Creation Point:** TTS created only when target variable is selected
3. **Warning System:** If test set will have <30 bad cases, system warns but doesn't adjust
4. **Reproducible:** Same seed (42) + same test_size (0.2) = same split every time

## 🚀 Result

- ✅ Always creates 80/20 split
- ✅ Only one place creates the split (when target variable selected)
- ✅ No duplicate creation
- ✅ Consistent and reproducible

