# IV Prioritization - Quick Reference

## What Changed?

### BEFORE (Traditional Exhaustive Search)
```
For each possible monotonic binning:
  ├─ Is it monotonic? ✓
  ├─ How many bins? (MORE is better)
  └─ WOE variance? (LOWER is better)

Result: Maximum bins preserved
```

### AFTER (IV-Prioritized Exhaustive Search - DEFAULT)
```
For each possible monotonic binning:
  ├─ Is it monotonic? ✓
  ├─ What's the IV? (HIGHER is better) ← NEW PRIMARY CRITERION
  ├─ How many bins? (MORE is better as tiebreaker)
  └─ WOE variance? (LOWER is better as secondary tiebreaker)

Result: Maximum predictive power
```

## Visual Example

### Scenario: 6 bins need merging to achieve monotonicity

```
Original Bins (Non-monotonic):
┌─────┬─────┬─────┬─────┬─────┬─────┐
│  1  │  2  │  3  │  4  │  5  │  6  │
└─────┴─────┴─────┴─────┴─────┴─────┘
WOE: [2.5, 1.8, 2.1, 0.5, -0.8, -2.0]  ← NOT MONOTONIC!
IV: 2.24
```

### Option A: Traditional (Max Bins)
```
Merged Bins (5 bins):
┌─────┬─────┬───────────┬─────┬─────┐
│  1  │  2  │   3+4     │  5  │  6  │
└─────┴─────┴───────────┴─────┴─────┘
WOE: [2.5, 1.8, 1.2, -0.8, -2.0]  ✓ MONOTONIC
IV: 2.05  ← Lower IV
Bins: 5  ← More bins
```

### Option B: IV-Prioritized (Max IV)
```
Merged Bins (4 bins):
┌─────┬───────────┬───────────┬─────┐
│  1  │   2+3     │   4+5     │  6  │
└─────┴───────────┴───────────┴─────┘
WOE: [2.5, 2.0, -0.2, -2.0]  ✓ MONOTONIC
IV: 2.18  ← Higher IV (BETTER!)
Bins: 4  ← Fewer bins
```

**Result**: Option B has fewer bins but **HIGHER predictive power** (IV = 2.18 vs 2.05)

## Decision Tree

```
                    Which is more important?
                            │
                ┌───────────┴───────────┐
                │                       │
        Predictive Power         Interpretability
        (Model Performance)      (Granularity)
                │                       │
                ▼                       ▼
        prioritize_iv=TRUE     prioritize_iv=FALSE
        (DEFAULT)              (Traditional)
                │                       │
                ▼                       ▼
        Maximize IV            Maximize Bins
```

## Quick Comparison Table

| Criterion | Traditional (prioritize_iv=False) | IV-Prioritized (prioritize_iv=True) |
|-----------|----------------------------------|-------------------------------------|
| **Primary Goal** | Maximum bins | Highest IV |
| **Secondary Goal** | Lower WOE variance | Maximum bins |
| **Best For** | Interpretability | Predictive power |
| **Use Cases** | Regulations, Business rules | Scorecards, ML models |
| **Trade-off** | May lose predictive power | May lose granularity |

## Code Comparison

### Traditional
```python
result = auto_monotonic_binning(
    good, bad, bin_labels,
    method='exhaustive',
    prioritize_iv=False  # Prioritize bin count
)
# Result: More bins, possibly lower IV
```

### IV-Prioritized (Default)
```python
result = auto_monotonic_binning(
    good, bad, bin_labels,
    method='exhaustive',
    prioritize_iv=True  # Prioritize IV (default)
)
# Result: Highest IV, optimal predictive power
```

## Key Insight

> **Before**: "Let's preserve as many bins as possible while achieving monotonicity"
>
> **After**: "Let's find the binning that gives the best predictive power while achieving monotonicity"

## When Does It Matter?

It makes the **most difference** when:
- ✅ Multiple valid monotonic solutions exist
- ✅ Different merging strategies yield different IVs
- ✅ You have 5+ bins initially
- ✅ The variable has good discrimination power

It makes **less difference** when:
- ⚠️ Only one monotonic solution exists
- ⚠️ Original bins are already monotonic
- ⚠️ Very few bins (2-3)
- ⚠️ Variable has weak predictive power

## Bottom Line

**IV Prioritization ensures you get the BEST possible predictive power from your binning, not just the most bins!**

For credit scoring models, this means:
- 🎯 Better risk discrimination
- 📈 Higher model performance (AUC, KS)
- 💪 Stronger scorecards
- ✨ Optimal use of each variable

*Default is `prioritize_iv=True` because predictive power typically matters more than granularity in credit scoring.*
