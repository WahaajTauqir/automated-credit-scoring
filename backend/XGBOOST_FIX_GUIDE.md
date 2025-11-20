# XGBoost Performance Fix Guide

## Problem Analysis

### Root Causes
1. **Wrong Feature Type**: XGBoost was trained on WOE-transformed features instead of raw features
2. **Information Loss**: WOE transformation collapses continuous variables into bins, losing granularity
3. **Scoring Method**: Tried to use feature importance as coefficients for linear scoring formula
4. **Score Direction**: Bad customers (target=1) should get LOW scores, good customers (target=0) should get HIGH scores

### Why XGBoost Performed Poorly
- Tree-based models like XGBoost work best with raw numerical and categorical features
- WOE transformation is designed specifically for linear models (Logistic Regression)
- Using WOE values removes the natural relationships and distributions that trees can exploit

### Why Scorecard Didn't Cluster 1s Properly
- Feature importance values were incorrectly used as linear coefficients
- The probability-to-score conversion expects proper model probabilities
- Need to use actual XGBoost model predictions, not reconstruct from importance

## Solution Overview

### 1. Train XGBoost on RAW Features
- Use original dataset columns, not WOE-transformed versions
- Handle missing values with median/mode imputation
- Encode categorical variables with LabelEncoder
- Save label encoders for consistent prediction

### 2. Use Model Predictions for Scoring
- Save trained XGBoost model using pickle
- Load model for scorecard application
- Use `predict_proba()` for probability estimates
- Convert probabilities to credit scores using standard formula

### 3. Ensure Proper Score Direction
- High probability of bad (1) → LOW credit score
- Low probability of bad (0) → HIGH credit score
- Formula: `score = base_score - factor * ln(prob_bad / (1 - prob_bad))`

## Implementation Changes

### File: `backend/app.py`

#### Change 1: Modify /api/xgboost endpoint

**Location**: Line ~6461

**What to change**:
- Remove WOE transformation logic
- Train on original features from `df[selected_variables]`
- Add preprocessing: missing value handling + label encoding
- Save model with `pickle.dumps(xgb_model)`
- Save preprocessing metadata (encoders, feature list)

**Key code pattern**:
```python
# OLD (WRONG):
woe_df = create_woe_transformed_dataframe(...)
X = woe_df[[f'{var}_WOE' for var in selected_variables]]

# NEW (CORRECT):
X = df[selected_variables].copy()
# ... handle missing values and encode categoricals ...
xgb_model.fit(X, y)
```

#### Change 2: Modify /api/apply-scorecard for XGBoost

**Location**: Line ~7835

**What to change**:
- Load saved XGBoost model artifact
- Check if model uses raw features (`uses_raw_features=True`)
- If yes: prepare raw features same way as training
- Use `model.predict_proba()` for predictions
- Convert probabilities to scores

**Key code pattern**:
```python
# Load artifact
artifact_data, _ = load_model_artifact(dataset_id, 'xgboost')
if artifact_data and artifact_data.get('uses_raw_features'):
    # Prepare raw features
    X_pred = prepare_raw_features(df, artifact_data)
    # Load model
    model = pickle.loads(artifact_data['model_bytes'])
    # Get predictions
    y_pred_proba = model.predict_proba(X_pred)[:, 1]
    # Convert to scores
    scores = probability_to_score(y_pred_proba)
```

#### Change 3: Score Direction Formula

**Location**: `_probability_to_score()` function

**Verify this formula**:
```python
def _probability_to_score(probabilities, config):
    \"\"\"
    Convert probability of default to credit score.
    Higher risk (high prob_bad) = LOWER score
    Lower risk (low prob_bad) = HIGHER score
    \"\"\"
    factor, offset = _scorecard_scaling_params(config)
    odds = probabilities / (1 - probabilities + 1e-10)
    scores = offset - factor * np.log(odds + 1e-10)
    scores = np.clip(scores, config['min_score'], config['max_score'])
    return scores
```

## Testing Checklist

### After Implementing Fixes:

1. **Train XGBoost Model**
   - Navigate to Model Training tab
   - Select variables for modeling
   - Click "Run XGBoost"
   - Verify: AUC > 0.7, Gini > 0.4

2. **Generate Scorecard**
   - Click "Generate Score Card (XGBoost)"
   - Verify: Scorecard shows reasonable score ranges (300-850)

3. **Apply to Test Data**
   - Click "Test Score Card"
   - **CRITICAL CHECK**: Sort by score and verify:
     - Top scores (800+): Mostly target=0 (good customers)
     - Bottom scores (300-500): Mostly target=1 (bad customers)
     - KS Statistic > 0.3 (good separation)

4. **Visual Verification**
   - Plot score distribution by target class
   - Should see clear separation between 0s and 1s
   - Mean score for target=0 should be significantly higher than target=1

## Expected Results

### Before Fix:
- XGBoost AUC: ~0.55-0.60 (barely better than random)
- Scorecard: 1s and 0s mixed together
- KS Statistic: < 0.1 (poor separation)

### After Fix:
- XGBoost AUC: > 0.75 (good predictive power)
- Scorecard: Clear clustering - 1s on low-score side, 0s on high-score side
- KS Statistic: > 0.35 (strong separation)

## Rollback Plan

If issues occur:
```bash
cd backend
git restore app.py
# Restart backend server
```

## Additional Notes

- Logistic Regression continues to use WOE features (that's correct for LR)
- Only XGBoost changes to use raw features
- Random Forest could also benefit from raw features if implemented later
- The `uses_raw_features` flag in artifact helps distinguish old/new models

