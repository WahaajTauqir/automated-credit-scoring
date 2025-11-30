# Quick Testing Guide - Database Migration

## Prerequisites
- Backend running: `python backend/app.py` or `.\start_backend.bat`
- Frontend running: `npm run dev`
- Database: PostgreSQL with new schema

---

## Test Sequence

### 1. Upload & Classification (5 minutes)
**Steps:**
1. Go to home page
2. Upload a CSV file (e.g., `BGFullDataSet.csv`)
3. **CHECK:** Columns appear in "All Columns" panel
4. Click "Send Remaining to Continuous" button
5. Select a target variable
6. Select some columns for analysis
7. Click "Proceed to Selected Columns Page"

**Expected Results:**
- No JavaScript errors in browser console
- Backend logs show arrays: `discrete_columns: ['col1', 'col2']` (NOT strings)
- Record created in database

**Backend Log Check:**
```
[/api/upload-csv] Received file: ...
[/api/upsert-single-record] Creating/updating record...
discrete_columns: ['Gender', 'Education', ...]
continuous_columns: ['Age', 'Income', ...]
```

---

### 2. Admin Panel View (2 minutes)
**Steps:**
1. Click "Admin Panel" in navbar
2. View the list of records
3. Click "View" on the most recent record

**Expected Results:**
- Columns display as readable lists (with commas), NOT as `"col1,col2"`
- "View" button navigates to SelectedColumnsPage with data loaded
- No errors when clicking "View"

**Check:**
- Column lists look like: `Gender, Education, MaritalStatus`
- NOT like: `Gender,Education,MaritalStatus` (no spaces means old format!)

---

### 3. Univariate Analysis (5 minutes)
**Steps:**
1. From SelectedColumnsPage (Step 1 or 2 above)
2. Click on a column card
3. **CHECK:** Binning table appears
4. Verify WOE/IV values display
5. Click another column
6. Click "Save" button

**Expected Results:**
- Binning tables load correctly
- No errors like `Cannot read property 'bins' of undefined`
- Save completes without errors

**Backend Log Check:**
```
[/api/univariate-analysis] Analyzing columns: ['Gender']
[/api/woe-iv] Calculating WOE/IV for: Gender
[/api/upsert-single-record] Updating record...
```

---

### 4. State Restoration (3 minutes)
**Steps:**
1. After completing Step 3 above, refresh the page (F5)
2. Or: Navigate away and come back via Admin Panel → View

**Expected Results:**
- Selected columns reappear in left panel
- Binning data reloads for all columns
- WOE/IV checkmarks show for completed columns
- No `JSON.parse` errors

**Check Browser Console:**
Should see NO errors like:
```
❌ Unexpected token o in JSON at position 1
❌ Cannot read property 'split' of undefined
```

**Backend Log Check:**
```
[/api/record/<id>] Fetching record: 123
[/api/record/<id>] Returning structured binning_data for 5 features
```

---

### 5. Fine Binning (Manual Merge) (5 minutes)
**Steps:**
1. From SelectedColumnsPage with univariate analysis done
2. Click on a column card
3. Select 2 or more bins (checkboxes)
4. Click "Merge Selected Bins"
5. **CHECK:** Bins merge into one row
6. Click "Save"

**Expected Results:**
- Merged bin appears in table
- WOE/IV recalculates
- No errors

**Backend Log Check:**
```
[/api/fine-bin] Processing merge for column: Gender
[/api/finebin-details] Saving merge: [0, 1] -> merged bin
[/api/woe-iv] Recalculating after merge...
```

---

## Common Issues & Solutions

### Issue 1: "Cannot read property 'split' of undefined"
**Cause:** Frontend trying to parse arrays as comma-separated strings  
**Fix:** Check which component is throwing the error and verify it uses array methods, not `.split(',')`

### Issue 2: Backend shows `discrete_columns: "col1,col2"` (string)
**Cause:** Old API endpoint still being used  
**Fix:** Verify `/api/records` and `/api/record/<id>` are returning arrays

### Issue 3: Binning data doesn't load after refresh
**Cause:** `loadSavedData()` not extracting from `binning_data` correctly  
**Check:** Browser console for errors, backend logs for response structure

### Issue 4: "Record not found" errors
**Cause:** Old database tables still being queried  
**Fix:** Ensure `db.py` functions are being called, not `db_old.py`

---

## Success Indicators ✅

### Browser Console (F12 → Console tab)
- **Good:** No red error messages
- **Good:** Network requests return 200 OK
- **Good:** Console logs show arrays: `['col1', 'col2']`

### Backend Terminal
- **Good:** Log lines show structured data
- **Good:** "discrete_columns: ['Gender', 'Education']"
- **Good:** No Python exceptions or tracebacks

### UI Behavior
- **Good:** Data loads instantly on refresh
- **Good:** Columns display with proper formatting
- **Good:** Save/Load cycle works smoothly

---

## If Everything Works

**Congratulations!** 🎉 The migration is successful. You can now:
1. Continue using the application normally
2. Consider removing `db_old.py` (after backup)
3. Update documentation to reflect new API format
4. Train models and generate scorecards

---

## If Issues Occur

1. **Check Browser Console** - What's the error message?
2. **Check Backend Logs** - Look for "ERROR" or Python exceptions
3. **Check Network Tab** (F12 → Network)
   - Click on failed requests
   - View "Response" tab - what did backend return?
4. **Verify Database State**
   - Are records in `datasets` table?
   - Are bins in `bins` and `merged_bins` tables?

---

## Quick Debug Commands

### Backend
```powershell
# View recent logs
python backend/app.py 2>&1 | Select-String "ERROR|discrete_columns|binning_data"

# Check database
psql -U postgres -d your_database -c "SELECT * FROM datasets ORDER BY created_at DESC LIMIT 5;"
```

### Frontend
```javascript
// In browser console:
fetch('http://localhost:5000/api/records')
  .then(r => r.json())
  .then(d => console.log(d))

// Check specific record:
fetch('http://localhost:5000/api/record/1')
  .then(r => r.json())
  .then(d => console.log('binning_data:', d.binning_data))
```

---

**Testing Time:** 20-30 minutes for full workflow  
**Critical Paths:** Upload → Classify → Analyze → Save → Reload  
**Success Rate Expected:** 95%+ (minor issues are cosmetic)
