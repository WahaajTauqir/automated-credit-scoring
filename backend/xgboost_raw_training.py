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
    
    # Encode categorical variables
    label_encoders = {}
    for col in X.columns:
        if X[col].dtype == 'object' or X[col].dtype.name == 'category':
            le = LabelEncoder()
            X[col] = le.fit_transform(X[col].astype(str))
            label_encoders[col] = le
            print(f"[XGBoost RAW] Encoded categorical variable '{col}' ({len(le.classes_)} categories)")
    
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
    
    # Calculate class imbalance for scale_pos_weight
    n_negative = (y == 0).sum()
    n_positive = (y == 1).sum()
    scale_pos_weight = n_negative / n_positive if n_positive > 0 else 1.0
    print(f"[XGBoost RAW] Class imbalance - Negatives: {n_negative}, Positives: {n_positive}, scale_pos_weight: {scale_pos_weight:.2f}")
    
    # Train XGBoost on RAW features
    xgb_model = xgb.XGBClassifier(
        n_estimators=100,
        max_depth=4,  # Reduced depth for better generalization
        learning_rate=0.1,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        eval_metric='logloss',
        scale_pos_weight=scale_pos_weight,  # Handle class imbalance
        use_label_encoder=False
    )
    
    xgb_model.fit(X, y)
    y_pred_proba = xgb_model.predict_proba(X)[:, 1]  # Probability of class 1 (bad)
    y_pred = xgb_model.predict(X)
    
    # Calculate metrics
    fpr, tpr, thresholds = roc_curve(y, y_pred_proba)
    roc_auc = auc(fpr, tpr)
    gini_coefficient = 2 * roc_auc - 1
    
    print(f"[XGBoost RAW] Model AUC: {roc_auc:.4f}, Gini: {gini_coefficient:.4f}")
    
    # Feature importance (using original variable names)
    feature_importance = []
    for i, col in enumerate(selected_variables):
        feature_importance.append({
            'variable': col,
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
    model_stats = {
        'n_estimators': xgb_model.n_estimators,
        'max_depth': xgb_model.max_depth,
        'learning_rate': float(xgb_model.learning_rate),
        'n_observations': len(X),
        'n_features': len(selected_variables)
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
            'feature_columns': selected_variables,  # Use original features, not WOE
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
    artifact_feature_cols = artifact_data.get('feature_columns', [])
    encoders_serialized = artifact_data.get('label_encoders', {})
    
    # Prepare features same way as training
    X_pred = df_raw[artifact_feature_cols].copy()
    
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
    
    # Encode categorical variables using saved encoders
    for col in X_pred.columns:
        if col in encoders_serialized:
            try:
                encoder = pickle.loads(encoders_serialized[col])
                X_pred[col] = encoder.transform(X_pred[col].astype(str))
            except Exception as enc_err:
                print(f"[XGBoost SCORING] Failed to apply encoder for {col}: {enc_err}")
                # Fallback: simple label encoding
                if X_pred[col].dtype == 'object':
                    le = LabelEncoder()
                    X_pred[col] = le.fit_transform(X_pred[col].astype(str))
        elif X_pred[col].dtype == 'object' or X_pred[col].dtype.name == 'category':
            le = LabelEncoder()
            X_pred[col] = le.fit_transform(X_pred[col].astype(str))
    
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
