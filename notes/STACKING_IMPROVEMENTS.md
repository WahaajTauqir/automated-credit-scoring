# Stacking Ensemble Improvement Plan

## Current State Analysis

### Performance Summary

**Dataset 1 (Small, 648 train, 279 test, 4 positives):**
- Stacking AUC: **0.7518** vs XGBoost: 0.7409 (+1.5%)
- Stacking Recall: **0.7500** vs XGBoost: 0.2500 (+200%)
- **Issue**: Very low precision (0.0316) with 92 false positives
- Meta-learner: RF dominates (86.7%), XGB minimal (2.2%)

**Dataset 2 (Large, 199K train, 85K test, 148 positives):**
- Stacking AUC: **0.9764** (same as XGBoost - fallback triggered)
- All metrics identical to XGBoost
- Meta-learner: LR dominates (50.2%), balanced distribution

### Industry Standard Comparison

| Metric | Your Model | Industry Standard | Status |
|--------|-----------|------------------|--------|
| **AUC-ROC** | 0.75-0.98 | 0.75-0.85 (good), 0.85+ (excellent) | ✅ Excellent (Dataset 2) |
| **Gini Coefficient** | 0.50-0.95 | 0.50-0.70 (good), 0.70+ (excellent) | ✅ Excellent (Dataset 2) |
| **Recall (Defaults)** | 0.25-0.75 | 0.70-0.85 (typical) | ⚠️ Low (Dataset 1: 0.75 OK, Dataset 2: 0.72 OK) |
| **Precision** | 0.03-0.86 | 0.30-0.50 (typical) | ⚠️ Very low (Dataset 1: 0.03), ✅ Good (Dataset 2: 0.86) |
| **F1-Score** | 0.06-0.78 | 0.40-0.60 (good) | ⚠️ Low (Dataset 1: 0.06), ✅ Good (Dataset 2: 0.78) |

**Verdict**: Your model performs **excellently** on large datasets (Dataset 2) but struggles with **extreme imbalance** on small datasets (Dataset 1).

---

## Critical Issues Identified

### 1. **No Probability Calibration** ⚠️ HIGH PRIORITY
**Problem**: Base models' probabilities aren't calibrated, leading to:
- Different probability scales (LR: 0-1, RF: 0-0.8, XGB: 0.3-0.5)
- Meta-learner can't properly combine uncalibrated probabilities
- Poor threshold selection

**Impact**: Meta-learner weights become unreliable, one model dominates

**Solution**: Apply Platt Scaling or Isotonic Regression to each base model before stacking

### 2. **Meta-Learner Dominance** ⚠️ HIGH PRIORITY
**Problem**: One model dominates (RF 86.7% in Dataset 1, LR 50.2% in Dataset 2)
- XGBoost contribution is minimal (2.2% in Dataset 1)
- Not leveraging the intended "monotonic + non-linear" combination

**Impact**: Stacking becomes essentially a single model, defeating the purpose

**Solution**: 
- Add L1 regularization with constraint on coefficient variance
- Use Elastic Net (L1+L2) to encourage balanced contributions
- Add diversity penalty to meta-learner loss

### 3. **Missing Interaction Features** ⚠️ MEDIUM PRIORITY
**Problem**: Only raw probabilities and logits, no cross-model interactions
- Can't capture "when LR and RF agree but XGB disagrees" patterns
- Missing synergy between monotonic (WOE) and non-linear (raw) models

**Solution**: Add interaction features:
- `LR_prob * RF_prob` (agreement between WOE models)
- `(LR_prob - XGB_prob)^2` (disagreement between WOE and non-linear)
- `max(LR_prob, RF_prob, XGB_prob) - min(...)` (prediction spread)

### 4. **Aggressive Fallback Logic** ⚠️ MEDIUM PRIORITY
**Problem**: Falls back to XGBoost when ensemble AUC < base AUC by even 0.0001
- In Dataset 2, ensemble AUC was 0.9582, fell back to XGBoost (0.9764)
- This prevents learning from ensemble when it's close

**Solution**: 
- Only fallback if AUC difference > 0.01 (1%)
- Consider ensemble if it improves recall/precision even with slightly lower AUC
- Use ensemble if it has better F1 or lower false positives

### 5. **No Diversity Metrics** ⚠️ LOW PRIORITY
**Problem**: Can't measure if models are actually diverse
- Low correlation doesn't guarantee complementary strengths
- No measure of "when does each model excel?"

**Solution**: Add diversity metrics:
- Prediction correlation matrix
- Agreement/disagreement analysis on hard cases
- Per-sample model confidence scores

### 6. **Threshold Selection** ⚠️ MEDIUM PRIORITY
**Problem**: Precision-focused search fails when FP count is already low (17 FPs)
- Requires 10 FP reduction when only 17 exist
- Too strict criteria for small datasets

**Solution**: 
- Adaptive FP reduction threshold: `max(10, current_fp * 0.1)` (10% reduction minimum)
- Relative improvement: Focus on percentage reduction, not absolute
- Consider precision-recall curve optimization

---

## Recommended Improvements (Priority Order)

### **Priority 1: Probability Calibration** 🔴 CRITICAL

**Why**: This is the foundation - uncalibrated probabilities make stacking unreliable.

**Implementation**:
```python
from sklearn.calibration import CalibratedClassifierCV

# For each base model, calibrate probabilities
lr_calibrated = CalibratedClassifierCV(lr_model, method='isotonic', cv=3)
rf_calibrated = CalibratedClassifierCV(rf_model, method='isotonic', cv=3)
xgb_calibrated = CalibratedClassifierCV(xgb_model, method='isotonic', cv=3)

# Use calibrated probabilities for meta-features
lr_oof_calibrated = lr_calibrated.predict_proba(X_val)[:, 1]
```

**Expected Impact**: 
- More balanced meta-learner weights
- Better threshold selection
- 2-5% AUC improvement
- Better precision-recall balance

---

### **Priority 2: Balanced Meta-Learner** 🔴 CRITICAL

**Why**: Current meta-learner lets one model dominate, defeating the ensemble purpose.

**Implementation**:
```python
# Option A: Elastic Net with diversity penalty
from sklearn.linear_model import ElasticNet

meta_learner = SklearnLR(
    penalty='elasticnet',
    l1_ratio=0.5,  # Balance between L1 and L2
    C=1.0,  # Lower C = more regularization
    class_weight='balanced',
    solver='saga'  # Only solver that supports elasticnet
)

# Option B: Constrained coefficients (custom loss)
# Add penalty for coefficient variance to encourage balanced weights
def diversity_penalty(coefs):
    """Penalize when one coefficient is much larger than others"""
    coefs_abs = np.abs(coefs[:3])  # First 3 are model weights
    variance = np.var(coefs_abs)
    return 0.1 * variance  # Penalty weight

# Option C: Minimum contribution constraint
# Ensure each model has at least 10% contribution
```

**Expected Impact**:
- More balanced model contributions (target: 20-40% each)
- Better leverage of monotonic + non-linear patterns
- 1-3% AUC improvement
- More stable across different datasets

---

### **Priority 3: Interaction Features** 🟡 HIGH

**Why**: Captures synergy between WOE-based (monotonic) and raw-feature (non-linear) models.

**Implementation**:
```python
# Add interaction features to meta-features
interactions_train = np.column_stack([
    lr_oof_preds * rf_oof_preds,  # WOE models agreement
    (lr_oof_preds - xgb_oof_preds) ** 2,  # WOE vs non-linear disagreement
    (rf_oof_preds - xgb_oof_preds) ** 2,  # WOE vs non-linear disagreement
    np.maximum.reduce([lr_oof_preds, rf_oof_preds, xgb_oof_preds]) - 
    np.minimum.reduce([lr_oof_preds, rf_oof_preds, xgb_oof_preds]),  # Prediction spread
    (lr_oof_preds + rf_oof_preds) / 2 - xgb_oof_preds,  # WOE average vs XGB
])

meta_features_train_aug = np.hstack([
    meta_features_train,  # Original probabilities
    logit_features_train,  # Logit transforms
    interactions_train  # NEW: Interaction features
])
```

**Expected Impact**:
- Better capture of "when models disagree" patterns
- 1-2% AUC improvement
- More interpretable ensemble (can see which interactions matter)

---

### **Priority 4: Improved Fallback Logic** 🟡 MEDIUM

**Why**: Current fallback is too aggressive, prevents ensemble from learning.

**Implementation**:
```python
# Improved fallback logic
auc_diff = best_base_auc - roc_auc
recall_improvement = ensemble_recall - best_base_recall
precision_improvement = ensemble_precision - best_base_precision

# Only fallback if:
# 1. AUC is significantly worse (>1%), AND
# 2. No improvement in recall/precision/F1
if auc_diff > 0.01 and recall_improvement <= 0 and precision_improvement <= 0:
    fallback_model_used = best_base_entry['model']
    # Use fallback
else:
    # Use ensemble even if AUC slightly lower (if other metrics better)
    print(f"STACKING DEBUG: Using ensemble despite AUC diff ({auc_diff:.4f}) "
          f"due to recall/precision improvements")
```

**Expected Impact**:
- Ensemble used more often (better learning)
- Better balance between AUC and other metrics
- More stable performance

---

### **Priority 5: Adaptive Threshold Selection** 🟡 MEDIUM

**Why**: Current precision-focused search fails on small datasets with low FP counts.

**Implementation**:
```python
# Adaptive FP reduction threshold
min_fp_reduction = max(10, int(current_fp * 0.1))  # 10% minimum reduction
if current_fp < 50:
    min_fp_reduction = max(5, int(current_fp * 0.15))  # 15% for small datasets

# Focus on relative improvement, not absolute
fp_reduction_pct = (fp_reduction / current_fp) * 100
if fp_reduction_pct >= 10:  # 10% relative reduction
    # Accept candidate
```

**Expected Impact**:
- Better threshold selection on small datasets
- More false positives reduced
- Better precision-recall balance

---

### **Priority 6: Diversity Metrics & Analysis** 🟢 LOW

**Why**: Helps understand when ensemble is actually helping vs just averaging.

**Implementation**:
```python
# Calculate diversity metrics
def calculate_diversity_metrics(preds_lr, preds_rf, preds_xgb, y_true):
    """Calculate model diversity and complementarity"""
    # Correlation matrix
    corr_matrix = np.corrcoef([preds_lr, preds_rf, preds_xgb])
    
    # Agreement on hard cases (near threshold)
    threshold = 0.5
    hard_cases = np.abs(preds_lr - threshold) < 0.1
    agreement_on_hard = np.mean(
        (preds_lr[hard_cases] > threshold) == 
        (preds_rf[hard_cases] > threshold) == 
        (preds_xgb[hard_cases] > threshold)
    )
    
    # Per-model performance on different segments
    # (e.g., high-risk vs low-risk customers)
    
    return {
        'correlation_matrix': corr_matrix,
        'agreement_on_hard_cases': agreement_on_hard,
        # ... more metrics
    }
```

**Expected Impact**:
- Better understanding of ensemble behavior
- Identify when to use ensemble vs single model
- Debugging and interpretability

---

## Expected Overall Impact

After implementing all improvements:

| Metric | Current | Expected | Improvement |
|--------|---------|----------|-------------|
| **AUC (Dataset 1)** | 0.7518 | 0.78-0.82 | +3-7% |
| **AUC (Dataset 2)** | 0.9764 | 0.978-0.982 | +0.2-0.6% |
| **Precision (Dataset 1)** | 0.0316 | 0.15-0.25 | +375-690% |
| **Recall (Dataset 1)** | 0.7500 | 0.70-0.85 | Maintained |
| **F1 (Dataset 1)** | 0.0606 | 0.25-0.40 | +312-560% |
| **Model Balance** | RF 86.7% | 25-40% each | Balanced |
| **False Positives (Dataset 1)** | 92 | 40-60 | -35-57% |

---

## Implementation Roadmap

### Phase 1 (Week 1): Foundation
1. ✅ Add probability calibration (Platt/Isotonic)
2. ✅ Implement balanced meta-learner (Elastic Net)
3. ✅ Test on both datasets

### Phase 2 (Week 2): Enhancement
4. ✅ Add interaction features
5. ✅ Improve fallback logic
6. ✅ Adaptive threshold selection

### Phase 3 (Week 3): Analysis
7. ✅ Add diversity metrics
8. ✅ Comprehensive testing
9. ✅ Performance validation

---

## Industry Best Practices You're Already Using ✅

1. ✅ **Stratified K-Fold CV** for out-of-fold predictions (prevents overfitting)
2. ✅ **Hybrid ensemble** (meta-learner + weighted average)
3. ✅ **Logit transformation** of probabilities (better for linear meta-learner)
4. ✅ **Standard scaling** of meta-features
5. ✅ **Class weighting** for imbalanced data
6. ✅ **Regularization** in meta-learner (L2)

## What Top Credit Scoring Models Add

1. **Multi-level stacking** (stack of stacks) - Advanced, may be overkill
2. **Dynamic model weighting** (weights vary by customer segment) - Could add
3. **Feature importance from meta-learner** - Should add for interpretability
4. **Uncertainty quantification** (prediction intervals) - Advanced, nice to have
5. **A/B testing framework** - Operational, not model-related

---

## Conclusion

Your stacking implementation is **solid** and performs **excellently on large datasets**. The main improvements needed are:

1. **Probability calibration** (critical for reliable stacking)
2. **Balanced meta-learner** (to actually leverage all 3 models)
3. **Interaction features** (to capture WOE + non-linear synergy)

These three improvements alone should significantly improve performance, especially on small/imbalanced datasets.

**Current Status vs Industry**: 
- **Large datasets**: ✅ **Exceeds industry standards** (AUC 0.98, Gini 0.95)
- **Small datasets**: ⚠️ **Below industry standards** (Precision 0.03, F1 0.06)

**After improvements**: Expected to meet/exceed industry standards on both.




