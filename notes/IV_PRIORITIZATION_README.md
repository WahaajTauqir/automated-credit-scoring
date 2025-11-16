# IV Prioritization in Exhaustive Binning

## Overview

The exhaustive binning algorithm now supports **Information Value (IV) prioritization**. This allows you to optimize binning strategies to maximize predictive power rather than just preserving the maximum number of bins.

## What is Information Value (IV)?

Information Value (IV) is a statistical measure that quantifies the predictive power of an independent variable in relation to the dependent variable (target). It's calculated as:

```
IV = Σ (% of Goods - % of Bads) × WOE
```

Where WOE (Weight of Evidence) is:
```
WOE = ln(% of Goods / % of Bads)
```

### IV Interpretation Guidelines:
- **< 0.02**: Unpredictive
- **0.02 - 0.10**: Weak predictive power
- **0.10 - 0.30**: Medium predictive power
- **0.30 - 0.50**: Strong predictive power
- **> 0.50**: Suspicious (too good to be true, might indicate data leakage)

## How IV Prioritization Works

### Traditional Approach (prioritize_iv=False)
The exhaustive search prioritizes:
1. **Maximum number of bins** (fewer merges)
2. Lower WOE variance (as tiebreaker)

This approach preserves granularity but may not maximize predictive power.

### IV-Prioritized Approach (prioritize_iv=True) - DEFAULT
The exhaustive search prioritizes:
1. **Highest Information Value** 
2. Maximum number of bins (as tiebreaker)
3. Lower WOE variance (as secondary tiebreaker)

This approach finds the monotonic binning configuration that maximizes the variable's predictive power, even if it means having fewer bins.

## Usage

### Python API

```python
from auto_monotonic_binning import auto_monotonic_binning
import numpy as np

good = np.array([100, 95, 70, 50, 30, 10])
bad = np.array([5, 10, 30, 50, 70, 90])
bin_labels = ['Bin_1', 'Bin_2', 'Bin_3', 'Bin_4', 'Bin_5', 'Bin_6']

# With IV prioritization (default)
result = auto_monotonic_binning(
    good=good,
    bad=bad,
    bin_labels=bin_labels,
    variable_type='continuous',
    method='exhaustive',
    prioritize_iv=True  # This is the default
)

print(f"Final IV: {result['iv']:.4f}")
print(f"Number of bins: {result['num_bins_final']}")
print(f"WOE values: {result['woe_values']}")

# Without IV prioritization (traditional approach)
result_traditional = auto_monotonic_binning(
    good=good,
    bad=bad,
    bin_labels=bin_labels,
    variable_type='continuous',
    method='exhaustive',
    prioritize_iv=False
)

print(f"Traditional - IV: {result_traditional['iv']:.4f}")
print(f"Traditional - Bins: {result_traditional['num_bins_final']}")
```

### REST API

```bash
curl -X POST http://localhost:5001/api/auto-monotonic-binning \
  -H "Content-Type: application/json" \
  -d '{
    "variable": "income",
    "target": "default",
    "type": "continuous",
    "method": "exhaustive",
    "prioritize_iv": true,
    "direction": null
  }'
```

**Request Parameters:**
- `variable`: Column name to bin
- `target`: Target column (0/1 for good/bad)
- `type`: "continuous" or "discrete"
- `method`: "greedy" or "exhaustive"
- `prioritize_iv`: `true` or `false` (default: `true`, only applies to exhaustive)
- `direction`: "increasing", "decreasing", or `null` for auto-detect

**Response includes:**
```json
{
  "merged_good": [100, 165, 90, 10],
  "merged_bad": [5, 40, 120, 90],
  "merged_labels": ["Bin_1", "Bin_2_merged_Bin_3", "Bin_4_merged_Bin_5", "Bin_6"],
  "woe_values": [2.6649, 0.8345, -0.7546, -2.5281],
  "iv": 1.9542,
  "is_monotonic": true,
  "direction": "decreasing",
  "num_merges": 2,
  "num_bins_original": 6,
  "num_bins_final": 4
}
```

## When to Use IV Prioritization

### Use `prioritize_iv=True` (default) when:
- **Predictive power is paramount**: Your primary goal is to maximize the variable's ability to discriminate between good and bad cases
- **Model performance matters most**: You're willing to sacrifice some granularity for better IV
- **Building scorecards**: Higher IV variables contribute more to the final score
- **Feature selection**: You want to identify which binning strategy gives the best predictive power

### Use `prioritize_iv=False` when:
- **Interpretability is crucial**: You need maximum granularity to explain decisions to stakeholders
- **Regulatory requirements**: Some regulations require maintaining certain bin structures
- **Business rules**: Domain knowledge suggests certain bins should be preserved
- **Detailed segmentation**: You need fine-grained customer segments regardless of IV

## Example Comparison

Consider a scenario where we have 6 initial bins that are non-monotonic:

### Scenario:
```
Original bins: 6
Original IV: 2.24
Monotonic: No
```

### Results:

**Greedy Algorithm:**
- Bins: 4
- IV: 1.85
- Fast but suboptimal

**Exhaustive with prioritize_iv=True:**
- Bins: 5
- IV: 2.18  ← **Best IV!**
- Found optimal merge that preserves predictive power

**Exhaustive with prioritize_iv=False:**
- Bins: 5
- IV: 2.05
- Maximum bins but lower IV

## Performance Considerations

- **Computational Complexity**: Exhaustive search explores 2^(n-1) combinations for n bins
- **Limits**: 
  - Warning at n > 25 bins
  - Hard limit at n > 30 bins
  - Falls back to greedy for discrete variables
  
- **Recommendation**: For large numbers of bins, consider:
  1. Using coarse binning first to reduce to manageable bin count
  2. Using greedy method for initial pass
  3. Then applying exhaustive with IV prioritization on the reduced set

## Best Practices

1. **Always check the initial IV**: Compare the final IV with the initial (before merging) to understand the trade-off
2. **Compare both approaches**: Run both `prioritize_iv=True` and `prioritize_iv=False` to see the difference
3. **Consider your use case**: Choose based on whether you prioritize predictive power or granularity
4. **Monitor bin population**: Ensure bins have sufficient sample size (typically > 5% of total)
5. **Validate on holdout data**: Check if the IV improvement translates to better out-of-sample performance

## Technical Details

### IV Calculation
```python
def compute_iv(good: np.ndarray, bad: np.ndarray) -> float:
    """
    Compute Information Value (IV) for the binning.
    
    IV = Σ (Dist_Good% - Dist_Bad%) * WOE
    """
    total_good = good.sum()
    total_bad = bad.sum()
    
    good_dist = good / total_good
    bad_dist = bad / total_bad
    
    woe = compute_woe(good, bad)
    iv = np.sum((good_dist - bad_dist) * woe)
    
    return iv
```

### Selection Logic in Exhaustive Search

```python
if prioritize_iv:
    # Prioritize higher IV, then more bins, then lower WOE variance
    is_better = (
        test_iv > best_iv or
        (test_iv == best_iv and test_num_bins > best_num_bins) or
        (test_iv == best_iv and test_num_bins == best_num_bins and 
         np.std(test_woe) < np.std(best_woe))
    )
else:
    # Traditional: prioritize more bins, then lower WOE variance
    is_better = (
        test_num_bins > best_num_bins or
        (test_num_bins == best_num_bins and np.std(test_woe) < np.std(best_woe))
    )
```

## Testing

Run the test script to see IV prioritization in action:

```bash
python test_iv_priority.py
```

This will demonstrate:
- How different merge strategies affect IV
- Comparison between greedy, IV-prioritized, and bin-count prioritized approaches
- Real examples showing when IV prioritization makes a difference

## Summary

IV prioritization is a powerful feature that allows you to optimize binning for predictive power. By default, it's enabled in exhaustive search to help you create better-performing scorecards and models. However, you can always disable it when other considerations (like interpretability or regulatory requirements) take precedence.
