# Train/Test Split - Single Creation Point Verification

## ✅ Confirmed: Only ONE Place Creates TTS

### Creation Point: When Target Variable is Selected

**Location:** Frontend automatically calls API when target variable is set

**Files:**
1. `src/App.tsx` - Lines 318-350
2. `src/components/SelectedColumnsPage.tsx` - Lines 639-671

**API Endpoint:**
- `POST /api/train-test-split` (backend/app.py, lines 2260-2350)

**Flow:**
```
User selects target variable
    ↓
Frontend useEffect (App.tsx or SelectedColumnsPage.tsx)
    ↓
POST /api/train-test-split with test_size=0.2
    ↓
Backend: get_or_create_train_test_split()
    ↓
Backend: create_stratified_split() with test_size=0.2
    ↓
Strict 80/20 split created
    ↓
Saved to database
```

## ❌ Removed Duplicate Creation Points

### 1. Backend Upsert Endpoint (REMOVED)
**Was:** `backend/app.py` - Lines 5382-5415
**Status:** ✅ REMOVED
**Reason:** Frontend already handles TTS creation

## 🔍 Verification: All test_size Values

### ✅ Frontend (0.2)
- `src/App.tsx` line 325: `test_size: 0.2`
- `src/components/SelectedColumnsPage.tsx` line 646: `test_size: 0.2`

### ✅ Backend API (0.2 default)
- `backend/app.py` line 2286: `test_size = data.get('test_size', 0.2)`

### ✅ Backend Function (0.2 default)
- `backend/train_test_split.py` line 50: `test_size: float = 0.2`
- `backend/train_test_split.py` line 319: `test_size: float = 0.2`

### ✅ Split Logic (Strict 0.2)
- `backend/train_test_split.py` line 99: `actual_test_size = test_size` (no adjustment)

## 📊 Split Ratio Verification

### Expected Results
For a dataset with 10,000 rows:
- **Train:** 8,000 rows (80%)
- **Test:** 2,000 rows (20%)
- **Ratio:** 4:1 (train:test)

### Database Check
```sql
SELECT 
    train_size,
    test_size,
    train_test_split_size,
    CASE 
        WHEN train_size + test_size > 0 
        THEN ROUND((test_size::numeric / (train_size + test_size)::numeric) * 100, 1)
        ELSE NULL 
    END as test_percentage
FROM records
WHERE id = 1;
```

**Expected:**
- `train_test_split_size` = 0.2
- `test_percentage` = 20.0%
- `train_size` / `test_size` = 4.0

## 🎯 Summary

| Item | Status |
|------|--------|
| **Creation Points** | ✅ Only 1 (frontend when target selected) |
| **Test Size** | ✅ Always 0.2 (20%) |
| **Split Ratio** | ✅ Always 80/20 |
| **Adjustment Logic** | ✅ Removed (strict 80/20) |
| **Duplicate Creation** | ✅ Removed from backend upsert |

## ✨ Result

- ✅ **Single creation point:** Only when target variable is selected
- ✅ **Strict 80/20:** Always 80% train, 20% test
- ✅ **No duplicates:** Removed from backend upsert endpoint
- ✅ **Consistent:** Same parameters everywhere (test_size=0.2)

