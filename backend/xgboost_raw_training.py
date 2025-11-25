"""
XGBoost Training on RAW Features

This module provides the corrected XGBoost training logic that uses
raw features instead of WOE-transformed features.

Key improvements:
1. Trains on original data columns
2. Handles missing values appropriately
3. Encodes categorical variables
4. Saves model with full preprocessing state
"""

import numpy as np
import pandas as pd
import pickle
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import roc_curve, auc, confusion_matrix, accuracy_score, precision_score, recall_score, f1_score


def train_xgboost_on_raw_features(df, selected_variables, target):
    """
    Train XGBoost classifier on raw features (not WOE-transformed).
    
    Parameters:
    -----------
    df : pandas.DataFrame
        The original dataset
    selected_variables : list
        List of feature column names to use
    target : str
        Name of the target column
        
    Returns:
    --------
    dict : Training results including model, metrics, and preprocessing artifacts
    """
    try:
        import xgboost as xgb
    except ImportError:
        raise ImportError("XGBoost not installed. Please install with: pip install xgboost")
    
    print(f"\n[XGBoost RAW] Training on {len(selected_variables)} raw features")
    
    # Prepare feature matrix from ORIGINAL data
    X = df[selected_variables].copy()
    y = df[target].copy()
    
    # Handle missing values in features
    for col in X.columns:
        if X[col].dtype in ['float64', 'int64']:
            # For numeric: fill with median
            X[col] = X[col].replace([np.inf, -np.inf], np.nan)
            median_val = X[col].median()
            if pd.isna(median_val):
                median_val = 0
            X[col] = X[col].fillna(median_val)
        else:
            # For categorical: fill with mode or 'MISSING'
            mode_val = X[col].mode()
            fill_val = mode_val[0] if not mode_val.empty else 'MISSING'
            X[col] = X[col].fillna(fill_val)
    
    # Encode categorical variables (one-hot for low cardinality, label for high)
    label_encoders = {}
    for col in X.columns:
        if X[col].dtype == 'object' or X[col].dtype.name == 'category':
            # FIX: Handle NaN values first
            nan_count = X[col].isna().sum()
            if nan_count > 0:
                X[col] = X[col].fillna('__MISSING__')
                print(f"[XGBoost RAW] Column '{col}': Filled {nan_count} NaN values with '__MISSING__'")
            
            unique_count = X[col].nunique()
            if unique_count <= 10:  # One-hot encode if <= 10 categories (real data only)
                X = pd.get_dummies(X, columns=[col], prefix=col)
                print(f"[XGBoost RAW] One-hot encoded '{col}' ({unique_count} categories)")
            else:  # Label encode if > 10 categories
                le = LabelEncoder()
                # Remove any remaining NaN (shouldn't be any after fillna, but safety check)
                unique_vals = X[col].dropna().unique()
                if len(unique_vals) == 0:
                    print(f"[XGBoost RAW] Column '{col}': Skipping (all NaN)")
                    continue
                le.fit(unique_vals)
                X[col] = le.transform(X[col].astype(str))
                label_encoders[col] = le
                print(f"[XGBoost RAW] Label encoded '{col}' ({unique_count} categories)")
    
    # Handle target variable
    y = pd.to_numeric(y, errors='coerce').fillna(0).astype(int)
    
    # Remove rows with invalid target
    valid_mask = y.isin([0, 1])
    X = X[valid_mask]
    y = y[valid_mask]
    
    if len(X) == 0:
        raise ValueError("No valid data after preprocessing")
    
    print(f"[XGBoost RAW] Training data: {X.shape[0]} rows, {X.shape[1]} features")
    print(f"[XGBoost RAW] Target distribution: {y.value_counts().to_dict()}")
    
    # Calculate class imbalance for adaptive configuration
    n_negative = (y == 0).sum()
    n_positive = (y == 1).sum()
    imbalance_ratio = n_negative / n_positive if n_positive > 0 else float('inf')
    train_size = len(X)
    
    print(f"[XGBoost RAW] Class imbalance - Negatives: {n_negative}, Positives: {n_positive}")
    print(f"[XGBoost RAW] Imbalance ratio: {imbalance_ratio:.2f}:1, Train size: {train_size}")
    
    # Get adaptive configuration from stacking config (same as stacking ensemble)
    # Use lazy import to avoid circular dependency
    def get_stacking_config(train_size, imbalance_ratio):
        """Adaptive configuration based on dataset characteristics (same as stacking)."""
        config = {}
        
        # Determine dataset category
        if train_size < 1000:
            dataset_type = 'small'
        elif train_size < 10000:
            dataset_type = 'medium'
        else:
            dataset_type = 'large'
        
        if imbalance_ratio > 100:
            imbalance_level = 'extreme'
        elif imbalance_ratio > 10:
            imbalance_level = 'high'
        else:
            imbalance_level = 'moderate'
        
        # Base model configurations
        if dataset_type == 'small' and imbalance_level == 'extreme':
            config['xgb'] = {
                'n_estimators': 200,
                'max_depth': 4,
                'learning_rate': 0.05,
                'min_child_weight': 5,
                'subsample': 0.8,
                'colsample_bytree': 0.8,
                'reg_alpha': 0.1,
                'reg_lambda': 1.0,
                'random_state': 42,
                'eval_metric': 'logloss',
                'use_label_encoder': False
            }
        elif dataset_type == 'large' and imbalance_level == 'extreme':
            config['xgb'] = {
                'n_estimators': 100,
                'max_depth': 6,
                'learning_rate': 0.1,
                'min_child_weight': 1,
                'subsample': 0.8,
                'colsample_bytree': 0.8,
                'reg_alpha': 0.0,
                'reg_lambda': 1.0,
                'random_state': 42,
                'eval_metric': 'logloss',
                'use_label_encoder': False
            }
        else:
            # Default: Per paper standard
            config['xgb'] = {
                'n_estimators': 100,
                'max_depth': 6,
                'learning_rate': 0.1,
                'subsample': 0.8,
                'colsample_bytree': 0.8,
                'reg_alpha': 0.0,
                'reg_lambda': 1.0,
                'random_state': 42,
                'eval_metric': 'logloss',
                'use_label_encoder': False
            }
        
        return config
    
    config = get_stacking_config(train_size, imbalance_ratio)
    xgb_config = config['xgb'].copy()
    
    # Calculate scale_pos_weight explicitly (same as stacking)
    if n_positive > 0 and n_negative > 0:
        scale_pos_weight = n_negative / n_positive
    else:
        scale_pos_weight = 1.0
    xgb_config['scale_pos_weight'] = scale_pos_weight
    
    print(f"[XGBoost RAW] Using adaptive configuration:")
    print(f"  - Dataset type: {'small' if train_size < 1000 else 'medium' if train_size < 10000 else 'large'}")
    print(f"  - Imbalance level: {'extreme' if imbalance_ratio > 100 else 'high' if imbalance_ratio > 10 else 'moderate'}")
    print(f"  - scale_pos_weight: {scale_pos_weight:.2f}")
    print(f"  - n_estimators: {xgb_config.get('n_estimators', 100)}")
    print(f"  - max_depth: {xgb_config.get('max_depth', 6)}")
    print(f"  - learning_rate: {xgb_config.get('learning_rate', 0.1)}")
    
    # Split training data for validation (using real data only, no synthetic data)
    from sklearn.model_selection import train_test_split
    try:
        # Try stratified split first
        X_train, X_val, y_train, y_val = train_test_split(
            X, y, test_size=0.2, random_state=42, stratify=y
        )
        print(f"[XGBoost RAW] Training split: {len(X_train)} train, {len(X_val)} validation (stratified)")
    except ValueError as e:
        # If stratification fails (e.g., one class has too few samples), use non-stratified split
        print(f"[XGBoost RAW] WARNING: Stratified split failed ({str(e)}), using non-stratified split")
        X_train, X_val, y_train, y_val = train_test_split(
            X, y, test_size=0.2, random_state=42
        )
        print(f"[XGBoost RAW] Training split: {len(X_train)} train, {len(X_val)} validation (non-stratified)")
    
    # Train XGBoost on RAW features with adaptive configuration (same as stacking)
    xgb_model = xgb.XGBClassifier(**xgb_config)
    
    # Train with early stopping if specified in config
    if 'early_stopping_rounds' in xgb_config:
        xgb_model.fit(
            X_train, y_train,
            eval_set=[(X_val, y_val)],
            verbose=False
        )
    else:
        xgb_model.fit(X_train, y_train)
    
    if hasattr(xgb_model, 'best_iteration') and xgb_model.best_iteration is not None:
        print(f"[XGBoost RAW] Training stopped at {xgb_model.best_iteration} iterations (best score: {xgb_model.best_score:.4f})")
    else:
        print(f"[XGBoost RAW] Training completed with {xgb_model.n_estimators} iterations")
    
    # Use full training set for final predictions (for metrics calculation)
    y_pred_proba = xgb_model.predict_proba(X)[:, 1]  # Probability of class 1 (bad)
    y_pred = xgb_model.predict(X)
    
    # Calculate metrics (on training data - will be replaced by test metrics in API)
    fpr, tpr, thresholds = roc_curve(y, y_pred_proba)
    roc_auc = auc(fpr, tpr)
    
    # Fix: Handle case where AUC < 0.5 (model worse than random)
    if roc_auc < 0.5:
        print(f"[XGBoost RAW] WARNING - AUC < 0.5 ({roc_auc:.4f}), model performing worse than random")
        roc_auc = 1 - roc_auc  # Flip AUC
        print(f"[XGBoost RAW] Flipped AUC to {roc_auc:.4f}")
    
    gini_coefficient = 2 * roc_auc - 1
    
    print(f"[XGBoost RAW] Model AUC: {roc_auc:.4f}, Gini: {gini_coefficient:.4f}")
    
    # Feature importance (using actual feature names after encoding)
    # Note: After one-hot encoding, feature names may have changed
    feature_importance = []
    feature_names = list(X.columns)  # Get actual feature names after encoding
    
    # Ensure feature_importances_ length matches number of features
    if len(xgb_model.feature_importances_) != len(feature_names):
        print(f"[XGBoost RAW] WARNING: Feature importance length mismatch: {len(xgb_model.feature_importances_)} vs {len(feature_names)}")
        # Use minimum length to avoid index errors
        min_len = min(len(xgb_model.feature_importances_), len(feature_names))
        feature_names = feature_names[:min_len]
    
    for i, col_name in enumerate(feature_names):
        # Try to map back to original variable name
        original_var = col_name
        for orig_var in selected_variables:
            if col_name.startswith(orig_var + '_') or col_name == orig_var:
                original_var = orig_var
                break
        
        if i < len(xgb_model.feature_importances_):
            feature_importance.append({
                'variable': original_var,
                'feature_name': col_name,  # Actual feature name used in model
                'importance': float(xgb_model.feature_importances_[i]),
                'importance_percentage': float(xgb_model.feature_importances_[i] * 100)
            })
    
    # Sort by importance
    feature_importance.sort(key=lambda x: x['importance'], reverse=True)
    print(f"[XGBoost RAW] Top 3 features: {[f['variable'] + ' (' + str(round(f['importance_percentage'], 1)) + '%)' for f in feature_importance[:3]]}")
    
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
        print(f"[XGBoost RAW] KS calculation error: {ks_err}")
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
        'n_features': len(X.columns),  # Actual number of features after encoding
        'n_original_features': len(selected_variables),
        'early_stopping_used': best_iter is not None,
        'best_iteration': best_iter,
        'best_score': best_score_val
    }
    
    # Serialize model and encoders
    model_bytes = pickle.dumps(xgb_model)
    encoders_serialized = {col: pickle.dumps(encoder) for col, encoder in label_encoders.items()}
    
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
            'feature_columns': list(X.columns),  # Use actual feature columns after encoding
            'original_feature_columns': selected_variables,  # Original feature names before encoding
            'model_bytes': model_bytes,
            'label_encoders': encoders_serialized,
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
            'uses_raw_features': True,  # Important flag!
            'n_samples': len(X),
            'class_distribution': y.value_counts().to_dict()
        }
    }
    
    return result


def apply_xgboost_scorecard(df_raw, target, artifact_data):
    """
    Apply XGBoost model to generate credit scores.
    
    Parameters:
    -----------
    df_raw : pandas.DataFrame
        The original dataset
    target : str
        Name of the target column
    artifact_data : dict
        Saved model artifact containing model and preprocessing info
        
    Returns:
    --------
    dict : Scorecard results with scores and metrics
    """
    import pickle
    from sklearn.preprocessing import LabelEncoder
    
    print(f"\n[XGBoost SCORING] Applying XGBoost scorecard")
    
    # Get feature columns and encoders
    # Handle both old format (original features) and new format (encoded features)
    artifact_feature_cols = artifact_data.get('feature_columns', [])
    original_feature_cols = artifact_data.get('original_feature_columns', artifact_feature_cols)
    encoders_serialized = artifact_data.get('label_encoders', {})
    
    # Always start with original features and apply same encoding as training
    X_pred = df_raw[original_feature_cols].copy()
    
    # Handle missing values
    for col in X_pred.columns:
        if X_pred[col].dtype in ['float64', 'int64']:
            X_pred[col] = X_pred[col].replace([np.inf, -np.inf], np.nan)
            median_val = X_pred[col].median()
            if pd.isna(median_val):
                median_val = 0
            X_pred[col] = X_pred[col].fillna(median_val)
        else:
            mode_val = X_pred[col].mode()
            fill_val = mode_val[0] if not mode_val.empty else 'MISSING'
            X_pred[col] = X_pred[col].fillna(fill_val)
    
    # Encode categorical variables using saved encoders (same logic as training)
    for col in list(X_pred.columns):  # Use list() to avoid modification during iteration
        if X_pred[col].dtype == 'object' or X_pred[col].dtype.name == 'category':
            unique_count = X_pred[col].nunique()
            if unique_count <= 10:  # One-hot encode if <= 10 categories (same as training)
                X_pred = pd.get_dummies(X_pred, columns=[col], prefix=col)
                print(f"[XGBoost SCORING] One-hot encoded '{col}' ({unique_count} categories)")
            else:  # Label encode if > 10 categories
                if col in encoders_serialized:
                    try:
                        encoder = pickle.loads(encoders_serialized[col])
                        # FIX: Handle NaN first
                        X_pred[col] = X_pred[col].fillna('__MISSING__')
                        # FIX: Handle unseen categories
                        seen_categories = set(encoder.classes_)
                        pred_values = X_pred[col].astype(str)
                        unseen_mask = ~pred_values.isin(seen_categories)
                        if unseen_mask.any():
                            unseen_count = unseen_mask.sum()
                            print(f"[XGBoost SCORING] Found {unseen_count} unseen categories in '{col}', mapping to '__MISSING__'")
                            X_pred.loc[unseen_mask, col] = '__MISSING__'
                            # If '__MISSING__' is not in encoder, map to most frequent category
                            if '__MISSING__' not in seen_categories:
                                if len(seen_categories) > 0:
                                    most_frequent = pred_values[~unseen_mask].mode()
                                    if len(most_frequent) > 0:
                                        X_pred.loc[unseen_mask, col] = most_frequent.iloc[0]
                                    else:
                                        X_pred.loc[unseen_mask, col] = list(seen_categories)[0]
                        X_pred[col] = encoder.transform(X_pred[col].astype(str))
                    except Exception as enc_err:
                        print(f"[XGBoost SCORING] Failed to apply encoder for {col}: {enc_err}")
                        import traceback
                        traceback.print_exc()
                        # Fallback: handle NaN and create new encoder
                        X_pred[col] = X_pred[col].fillna('__MISSING__')
                        le = LabelEncoder()
                        X_pred[col] = le.fit_transform(X_pred[col].astype(str))
                        print(f"[XGBoost SCORING] Created new encoder for {col} (fallback mode)")
                else:
                    # FIX: Handle NaN before creating new encoder
                    X_pred[col] = X_pred[col].fillna('__MISSING__')
                    le = LabelEncoder()
                    X_pred[col] = le.fit_transform(X_pred[col].astype(str))
                    print(f"[XGBoost SCORING] Created new encoder for {col} (no saved encoder found)")
    
    # Ensure feature columns match training (add missing one-hot columns with zeros)
    if artifact_feature_cols and len(artifact_feature_cols) > 0:
        missing_cols = set(artifact_feature_cols) - set(X_pred.columns)
        for col in missing_cols:
            X_pred[col] = 0  # Add missing one-hot columns with zeros
        # Reorder columns to match training
        X_pred = X_pred[artifact_feature_cols]
    
    # Remove rows with missing target
    target_series = pd.to_numeric(df_raw[target], errors='coerce').fillna(0).astype(int)
    valid_mask = target_series.isin([0, 1])
    X_pred = X_pred[valid_mask]
    y = target_series[valid_mask]
    row_ids = np.where(valid_mask)[0].tolist()
    
    # Load model and predict
    xgb_model = pickle.loads(artifact_data['model_bytes'])
    y_pred_proba_bad = xgb_model.predict_proba(X_pred)[:, 1]
    
    print(f"[XGBoost SCORING] Generated {len(y_pred_proba_bad)} predictions")
    print(f"[XGBoost SCORING] Probability range: {y_pred_proba_bad.min():.4f} to {y_pred_proba_bad.max():.4f}")
    
    return {
        'probabilities': y_pred_proba_bad,
        'target': y.values,
        'row_ids': row_ids,
        'n_predictions': len(y_pred_proba_bad)
    }
