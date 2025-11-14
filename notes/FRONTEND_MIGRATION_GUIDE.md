# Frontend Migration Guide - Database Storage Fixes

## 🔥 Quick Reference for Frontend Developers

---

## BREAKING CHANGES

### 1. Column Name Changed: Use `Bin` Instead of Variable-Prefixed Names

**Before:**
```javascript
// Had to handle multiple variants
const binLabel = row[`${variable}_binned`] || 
                 row[`${variable}_fine_binned`] || 
                 row.Bin;
```

**After:**
```javascript
// Single consistent name
const binLabel = row.Bin;  // Always use this
```

---

### 2. Compute Derived Metrics on Frontend

**Metrics NO LONGER in API responses:**
- `Bad Rate`
- `Freq%`
- `Dist_Good_%` (except in WOE/IV results)
- `Dist_Bad_%` (except in WOE/IV results)

**What IS in API responses:**
- `Bin` - Bin label
- `Good` - Count of good cases
- `Bad` - Count of bad cases  
- `Total` - Total count
- `Min` / `Max` - For continuous variables
- `Range` - For discrete variables

**Compute them yourself:**

```javascript
// Helper function to compute all metrics for a bin
function computeBinMetrics(bin, allBins) {
  // Bad Rate
  const badRate = bin.Total > 0 ? (bin.Bad / bin.Total) * 100 : 0;
  
  // Frequency %
  const totalSum = allBins.reduce((sum, b) => sum + b.Total, 0);
  const freqPercent = totalSum > 0 ? (bin.Total / totalSum) * 100 : 0;
  
  // Distribution Good %
  const goodSum = allBins.reduce((sum, b) => sum + b.Good, 0);
  const distGoodPercent = goodSum > 0 ? (bin.Good / goodSum) * 100 : 0;
  
  // Distribution Bad %
  const badSum = allBins.reduce((sum, b) => sum + b.Bad, 0);
  const distBadPercent = badSum > 0 ? (bin.Bad / badSum) * 100 : 0;
  
  return {
    ...bin,
    badRate,
    freqPercent,
    distGoodPercent,
    distBadPercent
  };
}

// Use it when rendering
const enrichedBins = bins.map(bin => computeBinMetrics(bin, bins));
```

---

### 3. New Reset Bins Endpoint

**New API:** `POST /api/reset-bins`

**Usage:**
```javascript
async function resetBins(variable, target, type, recordId) {
  const response = await fetch('/api/reset-bins', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      variable,
      target,
      type,  // 'continuous' or 'discrete'
      record_id: recordId
    })
  });
  
  const result = await response.json();
  
  if (result.success) {
    // result.coarse_stats contains the reset coarse bins
    return result.coarse_stats;
  } else {
    throw new Error(result.error);
  }
}
```

**When to call it:**
- User clicks "Reset Bins" button
- Replaces any manual state clearing you were doing

---

### 4. Fine Binning Now Returns WOE/IV

**Updated Response Structure:**

```javascript
// POST /api/fine-bin
// Response now includes woe_iv
{
  "success": true,
  "stats": [
    {
      "Bin": "Bin_1",
      "Min": 0,
      "Max": 2892,
      "Good": 84,
      "Bad": 1,
      "Total": 85
    }
  ],
  "bin_merges": {...},
  "woe_iv": {  // NEW - automatically calculated
    "iv": 0.0338,
    "stats": [
      {
        "Bin": "Bin_1",
        "Good": 84,
        "Bad": 1,
        "Total": 85,
        "Dist_Good_%": 9.9644,
        "Dist_Bad_%": 14.2857,
        "WOE": -36.0,
        "IV": 1.5567,
        "Range": "0.0 - 2892.0"
      }
    ]
  }
}
```

**Update your code:**
```javascript
const fineBinResult = await fetch('/api/fine-bin', {...});
const data = await fineBinResult.json();

// Now you can immediately use WOE/IV without separate API call
const iv = data.woe_iv.iv;
const woeStats = data.woe_iv.stats;
```

---

## DATA STRUCTURE REFERENCE

### Continuous Variable Bin
```json
{
  "Bin": "Bin_1",
  "Min": 0.0,
  "Max": 2892.0,
  "Good": 84,
  "Bad": 1,
  "Total": 85
}
```

### Discrete Variable Bin
```json
{
  "Bin": "1",
  "Range": "0, 1, 2, 5-10",
  "Good": 84,
  "Bad": 1,
  "Total": 85
}
```

### WOE/IV Stats
```json
{
  "Bin": "Bin_1",
  "Good": 84,
  "Bad": 1,
  "Total": 85,
  "Dist_Good_%": 9.9644,
  "Dist_Bad_%": 14.2857,
  "WOE": -36.0,
  "IV": 1.5567,
  "Range": "0.0 - 2892.0"
}
```

---

## COMPLETE EXAMPLE: Display Binning Table

```javascript
function BinningTable({ variable, bins, woeIvData }) {
  // Compute derived metrics
  const enrichedBins = bins.map(bin => {
    const totalSum = bins.reduce((sum, b) => sum + b.Total, 0);
    const goodSum = bins.reduce((sum, b) => sum + b.Good, 0);
    const badSum = bins.reduce((sum, b) => sum + b.Bad, 0);
    
    return {
      ...bin,
      badRate: bin.Total > 0 ? (bin.Bad / bin.Total) * 100 : 0,
      freqPercent: totalSum > 0 ? (bin.Total / totalSum) * 100 : 0,
      distGoodPercent: goodSum > 0 ? (bin.Good / goodSum) * 100 : 0,
      distBadPercent: badSum > 0 ? (bin.Bad / badSum) * 100 : 0
    };
  });
  
  // Find WOE for this bin (if available)
  const getWoeForBin = (binLabel) => {
    if (!woeIvData?.stats) return null;
    const woeBin = woeIvData.stats.find(s => s.Bin === binLabel);
    return woeBin?.WOE || null;
  };
  
  return (
    <table>
      <thead>
        <tr>
          <th>Bin</th>
          <th>Min</th>
          <th>Max</th>
          <th>Good</th>
          <th>Bad</th>
          <th>Total</th>
          <th>Bad Rate %</th>
          <th>Freq %</th>
          <th>WOE</th>
        </tr>
      </thead>
      <tbody>
        {enrichedBins.map((bin, idx) => (
          <tr key={idx}>
            <td>{bin.Bin}</td>
            <td>{bin.Min}</td>
            <td>{bin.Max}</td>
            <td>{bin.Good}</td>
            <td>{bin.Bad}</td>
            <td>{bin.Total}</td>
            <td>{bin.badRate.toFixed(2)}</td>
            <td>{bin.freqPercent.toFixed(2)}</td>
            <td>{getWoeForBin(bin.Bin)?.toFixed(1) || 'N/A'}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
```

---

## MIGRATION CHECKLIST

### Phase 1: Update Data Access
- [ ] Replace all `row[variable + '_binned']` with `row.Bin`
- [ ] Replace all `row[variable + '_fine_binned']` with `row.Bin`
- [ ] Remove any logic that tries to detect column name variants

### Phase 2: Add Metric Computation
- [ ] Create helper function `computeBinMetrics(bin, allBins)`
- [ ] Update all table/chart components to compute metrics
- [ ] Remove expectations of `Bad Rate`, `Freq%` from API

### Phase 3: Update API Calls
- [ ] Update fine binning handler to extract `woe_iv` from response
- [ ] Implement reset bins using new `/api/reset-bins` endpoint
- [ ] Remove manual state clearing on reset (backend handles it)

### Phase 4: Testing
- [ ] Test coarse binning display
- [ ] Test fine binning and verify WOE/IV updates
- [ ] Test reset bins and verify state clears properly
- [ ] Test multiple variables don't interfere with each other

---

## COMMON PATTERNS

### Pattern 1: Load and Display Bins
```javascript
const fetchBins = async (variable, recordId) => {
  const record = await fetch(`/api/record/${recordId}`).then(r => r.json());
  
  // Check if fine binning exists for this variable
  let bins;
  if (record.finebin_results && record.finebin_results[variable]) {
    bins = record.finebin_results[variable];
  } else if (record.univariate_results && record.univariate_results[variable]) {
    bins = record.univariate_results[variable].stats;
  } else {
    throw new Error('No binning data found');
  }
  
  // Get WOE/IV if available
  let woeIv = null;
  if (record.woe_iv_results && record.woe_iv_results[variable]) {
    woeIv = record.woe_iv_results[variable];
  }
  
  return { bins, woeIv };
};
```

### Pattern 2: Perform Fine Binning
```javascript
const performFineBinning = async (variable, target, type, binMerges, recordId) => {
  const response = await fetch('/api/fine-bin', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      variable,
      target,
      type,
      bin_merges: binMerges,
      recordId
    })
  });
  
  const result = await response.json();
  
  if (result.success) {
    return {
      bins: result.stats,
      binMerges: result.bin_merges,
      woeIv: result.woe_iv  // Now included automatically!
    };
  } else {
    throw new Error(result.error);
  }
};
```

### Pattern 3: Reset to Coarse Bins
```javascript
const resetToCoarseBins = async (variable, target, type, recordId) => {
  const response = await fetch('/api/reset-bins', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      variable,
      target,
      type,
      record_id: recordId
    })
  });
  
  const result = await response.json();
  
  if (result.success) {
    // Backend has cleared fine bins and WOE/IV
    return result.coarse_stats;
  } else {
    throw new Error(result.error);
  }
};
```

---

## TROUBLESHOOTING

### Issue: "Cannot read property 'Bin' of undefined"
**Cause:** Trying to access old column names
**Fix:** Update to use `row.Bin` consistently

### Issue: "Bad Rate is undefined"
**Cause:** Expecting derived metric from API
**Fix:** Compute it: `(bin.Bad / bin.Total) * 100`

### Issue: "WOE/IV not updating after fine binning"
**Cause:** Using old API response structure
**Fix:** Extract from `result.woe_iv` (automatically returned now)

### Issue: "Reset doesn't clear fine bins"
**Cause:** Using old manual clearing approach
**Fix:** Call `/api/reset-bins` endpoint (handles everything)

---

## PERFORMANCE TIPS

1. **Memoize metric computation** if rendering many bins:
```javascript
const enrichedBins = useMemo(
  () => bins.map(bin => computeBinMetrics(bin, bins)),
  [bins]
);
```

2. **Cache computed metrics** if bins don't change frequently:
```javascript
const [enrichedBins, setEnrichedBins] = useState([]);

useEffect(() => {
  setEnrichedBins(bins.map(bin => computeBinMetrics(bin, bins)));
}, [bins]);
```

3. **Compute once, display many times** for tables/charts using same data

---

## QUESTIONS?

If you encounter issues during migration:
1. Check `FIXES_IMPLEMENTED.md` for detailed technical info
2. Verify API endpoint changes in `backend/app.py`
3. Test with small dataset first before deploying to production

**Key Principle:** Backend now stores raw counts only. Frontend computes display metrics. This prevents stale data and inconsistencies.
