# Automated Monotonic Binning

## Overview

This module provides automated bin merging algorithms to achieve **monotonic Weight of Evidence (WOE)** trends in credit scoring and risk modeling.

## What is Monotonic WOE?

In credit scoring, bins should ideally show a monotonic (strictly increasing or decreasing) relationship between WOE and the predictor variable. This ensures:
- **Interpretability**: Easy to explain to stakeholders
- **Model Stability**: Better generalization to new data
- **Regulatory Compliance**: Meets Basel II/III requirements

## Features

### 1. Deterministic Algorithms
- **Greedy Algorithm**: Fast, merges bins one violation at a time
- **Exhaustive Algorithm**: Explores more possibilities for optimal solution

### 2. Variable Type Support
- **Continuous Variables**: Only adjacent bins can merge (preserves ordering)
- **Discrete Variables**: Any bins can merge

### 3. Auto-Detection
- Automatically detects whether WOE should increase or decrease
- Can also manually specify direction

## Algorithm Details

### Greedy Algorithm

```python
while not monotonic:
    1. Calculate WOE for all bins
    2. Find first violation of monotonicity
    3. Merge violating bin with:
       - Adjacent bin (continuous)
       - Best matching bin (discrete)
    4. Repeat until monotonic
```

**Pros**: Fast, simple, always finds a solution
**Cons**: May not be optimal (more merges than necessary)

### Exhaustive Algorithm

```python
1. Start with greedy solution as baseline
2. Try multiple merge strategies
3. Select strategy with:
   - Fewest merges
   - Best WOE distribution
   - Maintains monotonicity
```

**Pros**: Better solutions with fewer merges
**Cons**: Slower for large numbers of bins

## API Usage

### Endpoint
```
POST /api/auto-monotonic-binning
```

### Request Body
```json
{
  "variable": "age",
  "target": "default",
  "type": "continuous",
  "direction": null,
  "method": "greedy",
  "record_id": 123,
  "dashboard_selected_columns": ["age", "income"]
}
```

### Parameters
- `variable` (required): Column name to bin
- `target` (required): Binary target variable (0/1)
- `type` (required): "continuous" or "discrete"
- `direction` (optional): "increasing", "decreasing", or null (auto-detect)
- `method` (optional): "greedy" (default) or "exhaustive"
- `record_id` (optional): Database record ID
- `dashboard_selected_columns` (optional): List of selected columns

### Response
```json
{
  "success": true,
  "stats": [...],
  "bin_merges": {...},
  "is_monotonic": true,
  "direction": "decreasing",
  "num_merges": 2,
  "num_bins_original": 10,
  "num_bins_final": 8
}
```

## Frontend Usage

The "Auto Monotonic Binning" button automatically:
1. Fetches current bin statistics
2. Runs the algorithm
3. Applies the optimal merges
4. Updates WOE/IV calculations
5. Refreshes the display

No manual bin selection required!

## Example Scenarios

### Scenario 1: Age Variable (Continuous)
- **Before**: 10 bins with non-monotonic WOE
- **After**: 7 bins with strictly decreasing WOE
- **Result**: 3 adjacent bins merged

### Scenario 2: Education Level (Discrete)
- **Before**: 5 categories with mixed WOE
- **After**: 3 categories with monotonic WOE
- **Result**: Similar education levels grouped

## Mathematical Foundation

### WOE Calculation
```
WOE = ln(Dist_Good% / Dist_Bad%)

where:
Dist_Good% = (Good in bin / Total Good) × 100
Dist_Bad% = (Bad in bin / Total Bad) × 100
```

### Monotonicity Check
For increasing trend: WOE[i] ≤ WOE[i+1] for all i
For decreasing trend: WOE[i] ≥ WOE[i+1] for all i

## Best Practices

1. **Start with Coarse Binning**: Use 10-20 initial bins
2. **Choose Method**:
   - Use "greedy" for quick results (< 5 seconds)
   - Use "exhaustive" for optimal solutions (may take longer)
3. **Review Results**: Always check the final binning makes business sense
4. **Adjust if Needed**: Can still manually merge/unmerge after auto-binning

## Performance

- **Greedy**: O(n²) where n = number of bins
- **Exhaustive**: O(n² × k) where k = exploration attempts

Typical execution times:
- 10 bins: < 1 second
- 20 bins: 1-2 seconds
- 50 bins: 3-5 seconds

## Limitations

1. **Single Bin**: If all bins must merge into one, WOE becomes 0
2. **Perfect Separation**: Cannot fix bins where all records are Good or Bad
3. **Small Sample**: Requires sufficient data in each bin

## Future Enhancements

- [ ] Support for ordinal encoding preservation
- [ ] Multi-objective optimization (IV, interpretability, business rules)
- [ ] Constraint-based merging (min/max bins, min sample size)
- [ ] Interactive visualization of merge suggestions
