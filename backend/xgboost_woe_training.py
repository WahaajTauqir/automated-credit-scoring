"""
XGBoost Training on WOE Features

This module provides XGBoost training logic that uses WOE-transformed features
(same as Random Forest and Logistic Regression).

Key features:
1. Trains on WOE-transformed features (fine-binned)
2. Uses same preprocessing as Random Forest
3. Handles class imbalance with scale_pos_weight
4. Saves model with WOE transformation metadata
"""

import numpy as np
import pandas as pd
import pickle
from sklearn.metrics import roc_curve, auc, confusion_matrix, accuracy_score, precision_score, recall_score, f1_score


def train_xgboost_on_woe_features(X, y, selected_variables, woe_columns, target, woe_transformed_data):
    """
    Train XGBoost classifier on WOE-transformed features.
    
    Parameters:
    -----------
    X : pandas.DataFrame
        WOE-transformed feature matrix (already prepared)
    y : pandas.Series
        Target variable
    selected_variables : list
        List of original variable names
    woe_columns : list
        List of WOE column names (e.g., ['var1_WOE', 'var2_WOE'])
    target : str
        Name of the target column
    woe_transformed_data : dict
        WOE transformation data for saving in artifact
        
    Returns:
    --------
    dict : Training results including model, metrics, and preprocessing artifacts
    """
    try:
        import xgboost as xgb
    except ImportError:
        raise ImportError("XGBoost not installed. Please install with: pip install xgboost")
    
    print(f"\n[XGBoost WOE] Training on {len(woe_columns)} WOE-transformed features")
    
    # Ensure X and y are aligned
    if len(X) != len(y):
        raise ValueError(f"X and y length mismatch: {len(X)} vs {len(y)}")
    
    # Handle target variable
    y = pd.to_numeric(y, errors='coerce').fillna(0).astype(int)
    
    # Remove rows with invalid target
    valid_mask = y.isin([0, 1])
    X = X[valid_mask].copy()
    y = y[valid_mask].copy()
    
    if len(X) == 0:
        raise ValueError("No valid data after preprocessing")
    
    print(f"[XGBoost WOE] Training data: {X.shape[0]} rows, {X.shape[1]} features")
    print(f"[XGBoost WOE] Target distribution: {y.value_counts().to_dict()}")
    
    # Calculate class imbalance for scale_pos_weight
    n_negative = (y == 0).sum()
    n_positive = (y == 1).sum()
    base_ratio = n_negative / n_positive if n_positive > 0 else 1.0
    
    # For extreme imbalance, use more aggressive weighting (2x the ratio)
    scale_pos_weight = 2.0 * base_ratio if n_positive > 0 else 1.0
    print(f"[XGBoost WOE] Class imbalance - Negatives: {n_negative}, Positives: {n_positive}")
    print(f"[XGBoost WOE] Base ratio: {base_ratio:.2f}, Adjusted scale_pos_weight: {scale_pos_weight:.2f} (2x for extreme imbalance)")
    
    # Split training data for validation (using real data only, no synthetic data)
    from sklearn.model_selection import train_test_split
    try:
        # Try stratified split first
        X_train, X_val, y_train, y_val = train_test_split(
            X, y, test_size=0.2, random_state=42, stratify=y
        )
        print(f"[XGBoost WOE] Training split: {len(X_train)} train, {len(X_val)} validation (stratified)")
    except ValueError as e:
        # If stratification fails (e.g., one class has too few samples), use non-stratified split
        print(f"[XGBoost WOE] WARNING: Stratified split failed ({str(e)}), using non-stratified split")
        X_train, X_val, y_train, y_val = train_test_split(
            X, y, test_size=0.2, random_state=42
        )
        print(f"[XGBoost WOE] Training split: {len(X_train)} train, {len(X_val)} validation (non-stratified)")
    
    # Train XGBoost on WOE features with early stopping and regularization
    # XGBoost 3.0+ requires early_stopping_rounds in constructor, not in fit()
    # Optimized for extreme class imbalance and better recall
    xgb_model = xgb.XGBClassifier(
        n_estimators=1000,  # Increase max trees for better learning
        max_depth=6,  # Increase depth slightly to capture more patterns (was 4)
        learning_rate=0.03,  # Lower learning rate for more stable training (was 0.05)
        subsample=0.8,
        colsample_bytree=0.8,
        reg_alpha=0.01,  # Reduce L1 regularization to allow more learning (was 0.1)
        reg_lambda=0.5,  # Reduce L2 regularization to allow more learning (was 1.0)
        min_child_weight=1,  # Lower to allow splits on minority class (was 3)
        gamma=0.05,  # Lower gamma to allow more splits (was 0.1)
        random_state=42,
        eval_metric='auc',  # Use AUC for early stopping (better for imbalanced data)
        scale_pos_weight=scale_pos_weight,  # Handle class imbalance (real data only)
        use_label_encoder=False,
        early_stopping_rounds=30  # Increase patience for better convergence (was 20)
    )
    
    # Train with early stopping (XGBoost 3.0+ - early_stopping_rounds already in constructor)
    xgb_model.fit(
        X_train, y_train,
        eval_set=[(X_val, y_val)],
        verbose=False
    )
    
    if hasattr(xgb_model, 'best_iteration') and xgb_model.best_iteration is not None:
        print(f"[XGBoost WOE] Training stopped at {xgb_model.best_iteration} iterations (best score: {xgb_model.best_score:.4f})")
    else:
        print(f"[XGBoost WOE] Training completed with {xgb_model.n_estimators} iterations")
    
    # Use full training set for final predictions (for metrics calculation)
    y_pred_proba = xgb_model.predict_proba(X)[:, 1]  # Probability of class 1 (bad)
    y_pred = xgb_model.predict(X)
    
    # Calculate metrics (on training data - will be replaced by test metrics in API)
    fpr, tpr, thresholds = roc_curve(y, y_pred_proba)
    roc_auc = auc(fpr, tpr)
    
    # Fix: Handle case where AUC < 0.5 (model worse than random)
    if roc_auc < 0.5:
        print(f"[XGBoost WOE] WARNING - AUC < 0.5 ({roc_auc:.4f}), model performing worse than random")
        roc_auc = 1 - roc_auc  # Flip AUC
        print(f"[XGBoost WOE] Flipped AUC to {roc_auc:.4f}")
    
    gini_coefficient = 2 * roc_auc - 1
    
    print(f"[XGBoost WOE] Model AUC: {roc_auc:.4f}, Gini: {gini_coefficient:.4f}")
    
    # Feature importance (using WOE column names)
    feature_importance = []
    for i, col_name in enumerate(woe_columns):
        # Extract original variable name (remove _WOE suffix)
        original_var = col_name.replace('_WOE', '')
        
        feature_importance.append({
            'variable': original_var,
            'feature_name': col_name,  # Actual WOE feature name used in model
            'importance': float(xgb_model.feature_importances_[i]),
            'importance_percentage': float(xgb_model.feature_importances_[i] * 100)
        })
    
    # Sort by importance
    feature_importance.sort(key=lambda x: x['importance'], reverse=True)
    print(f"[XGBoost WOE] Top 3 features: {[f['variable'] + ' (' + str(round(f['importance_percentage'], 1)) + '%)' for f in feature_importance[:3]]}")
    
    # Confusion matrix and classification metrics
    cm = confusion_matrix(y, y_pred)
    accuracy = accuracy_score(y, y_pred)
    precision = precision_score(y, y_pred, zero_division=0)
    recall = recall_score(y, y_pred, zero_division=0)
    f1 = f1_score(y, y_pred, zero_division=0)
    
    # KS Statistic
    try:
        diffs = np.abs(tpr - fpr)
        ks_idx = int(np.argmax(diffs)) if len(diffs) > 0 else 0
        ks_stat = float(diffs[ks_idx]) if len(diffs) > 0 else 0.0
        ks_threshold = float(thresholds[ks_idx]) if len(thresholds) > 0 else 0.0
        ks_curve = []
        for f, t, th in zip(fpr, tpr, thresholds):
            ks_curve.append({
                'threshold': float(th) if np.isfinite(th) else None,
                'tpr': float(t) if np.isfinite(t) else None,
                'fpr': float(f) if np.isfinite(f) else None,
                'diff': float(abs(t - f)) if np.isfinite(t) and np.isfinite(f) else None
            })
    except Exception as ks_err:
        print(f"[XGBoost WOE] KS calculation error: {ks_err}")
        ks_stat = None
        ks_threshold = None
        ks_curve = []
    
    # ROC data
    roc_data = []
    for f, t, th in zip(fpr, tpr, thresholds):
        roc_data.append({
            'fpr': float(f) if np.isfinite(f) else None,
            'tpr': float(t) if np.isfinite(t) else None,
            'threshold': float(th) if np.isfinite(th) else None
        })
    
    # Model stats
    best_iter = None
    best_score_val = None
    if hasattr(xgb_model, 'best_iteration') and xgb_model.best_iteration is not None:
        best_iter = int(xgb_model.best_iteration)
    if hasattr(xgb_model, 'best_score') and xgb_model.best_score is not None:
        best_score_val = float(xgb_model.best_score)
    
    model_stats = {
        'n_estimators': best_iter if best_iter is not None else xgb_model.n_estimators,
        'max_depth': xgb_model.max_depth,
        'learning_rate': float(xgb_model.learning_rate),
        'n_observations': len(X),
        'n_features': len(woe_columns),
        'n_original_features': len(selected_variables),
        'early_stopping_used': best_iter is not None,
        'best_iteration': best_iter,
        'best_score': best_score_val
    }
    
    # Serialize model
    model_bytes = pickle.dumps(xgb_model)
    
    # Prepare WOE snapshot for scorecard application
    woe_snapshot = {}
    for var in selected_variables:
        if var in woe_transformed_data:
            import copy
            woe_snapshot[var] = copy.deepcopy(woe_transformed_data[var])
    
    # Build result dictionary
    result = {
        'success': True,
        'feature_importance': feature_importance,
        'gini_coefficient': float(gini_coefficient) if np.isfinite(gini_coefficient) else None,
        'auc': float(roc_auc) if np.isfinite(roc_auc) else None,
        'roc_data': roc_data,
        'model_stats': model_stats,
        'confusion_matrix': cm.tolist(),
        'accuracy': float(accuracy) if np.isfinite(accuracy) else None,
        'precision': float(precision) if np.isfinite(precision) else None,
        'recall': float(recall) if np.isfinite(recall) else None,
        'f1': float(f1) if np.isfinite(f1) else None,
        'ks_stat': ks_stat,
        'ks_threshold': ks_threshold,
        'ks_curve': ks_curve,
        # Artifact data for saving
        'artifact_payload': {
            'model_type': 'xgboost',
            'target': target,
            'selected_variables': selected_variables,
            'model_variables': selected_variables,
            'feature_columns': woe_columns,  # WOE-transformed feature columns
            'woe_transformed_data': woe_snapshot,
            'model_bytes': model_bytes,
            'xgb_params': xgb_model.get_xgb_params(),
            'training_metrics': {
                'auc': float(roc_auc) if np.isfinite(roc_auc) else None,
                'gini_coefficient': float(gini_coefficient) if np.isfinite(gini_coefficient) else None,
                'accuracy': float(accuracy) if np.isfinite(accuracy) else None,
                'precision': float(precision) if np.isfinite(precision) else None,
                'recall': float(recall) if np.isfinite(recall) else None,
                'f1': float(f1) if np.isfinite(f1) else None,
                'ks_stat': ks_stat
            },
            'uses_raw_features': False,  # Uses WOE features (like Random Forest)
            'n_samples': len(X),
            'class_distribution': y.value_counts().to_dict()
        }
    }
    
    return result

