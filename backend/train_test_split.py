"""
Train/Test Split Module

This module handles the critical train/test split that must happen
BEFORE any preprocessing, binning, or WOE calculation to prevent data leakage.

Key principles:
1. Split happens immediately after variable classification
2. All learning (binning boundaries, WOE values, model training) uses train set only
3. Test set is held out until final evaluation
4. Stratified split maintains class distribution (critical for imbalanced data)
5. Split is reproducible via random seed
"""

import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from typing import Tuple, Dict, Optional
import hashlib
import os


def calculate_data_hash(df: pd.DataFrame, target: str) -> str:
    """
    Calculate hash of data to detect changes.
    
    Parameters:
    -----------
    df : DataFrame
        The dataset
    target : str
        Target column name
        
    Returns:
    --------
    str : MD5 hash of data
    """
    # Create a stable representation of the data
    # Sort by index to ensure consistency
    df_sorted = df.sort_index()
    
    # Create hash from shape and sample rows
    data_str = f"{df_sorted.shape}_{df_sorted.iloc[:5].to_string()}_{df_sorted.iloc[-5:].to_string()}"
    return hashlib.md5(data_str.encode()).hexdigest()


def create_stratified_split(
    df: pd.DataFrame,
    target: str,
    test_size: float = 0.2,
    random_state: int = 42,
    min_test_bad: int = 30
) -> Tuple[pd.DataFrame, pd.DataFrame, Dict]:
    """
    Create stratified train/test split BEFORE any preprocessing.
    
    Parameters:
    -----------
    df : DataFrame
        Full dataset (raw, unprocessed)
    target : str
        Target column name
    test_size : float
        Proportion for test set (default 0.2 for 20%)
    random_state : int
        Random seed for reproducibility
    min_test_bad : int
        Minimum bad cases required in test set
        
    Returns:
    --------
    train_df : DataFrame
        Training set (80% of data by default)
    test_df : DataFrame
        Test set (20% of data by default) - LOCKED until final evaluation
    split_info : dict
        Information about the split
    """
    # Validate target exists
    if target not in df.columns:
        raise ValueError(f"Target column '{target}' not found in dataset")
    
    # Get target distribution
    y = df[target]
    n_total = len(df)
    n_bad = (y == 1).sum()
    n_good = (y == 0).sum()
    bad_rate = n_bad / n_total if n_total > 0 else 0
    
    print(f"\n[SPLIT] Original dataset: {n_total} samples")
    print(f"[SPLIT] Bad: {n_bad} ({bad_rate:.2%}), Good: {n_good} ({1-bad_rate:.2%})")
    
    # Check if we have enough bad cases
    if n_bad < 10:
        raise ValueError(f"Insufficient bad cases ({n_bad}). Need at least 10 for meaningful split.")
    
    # STRICT 80/20 SPLIT: Always use the requested test_size (0.2 for 20%)
    # Only warn if test set will have very few bad cases, but don't adjust
    actual_test_size = test_size  # Always use the requested size (0.2 for 80/20)
    expected_test_bad = int(n_bad * actual_test_size)
    
    if expected_test_bad < min_test_bad:
        print(f"[SPLIT] ⚠️  WARNING: Test set will have only ~{expected_test_bad} bad cases (recommended: {min_test_bad})")
        print(f"[SPLIT] ⚠️  Consider collecting more data or reducing min_test_bad requirement")
        print(f"[SPLIT] ⚠️  Proceeding with {actual_test_size:.1%} test size as requested (80/20 split)")
    else:
        print(f"[SPLIT] Test set will have ~{expected_test_bad} bad cases (sufficient for evaluation)")
    
    # Perform stratified split
    X = df.drop(columns=[target])
    y_series = df[target]
    
    try:
        X_train, X_test, y_train, y_test = train_test_split(
            X, y_series,
            test_size=actual_test_size,
            random_state=random_state,
            stratify=y_series  # Maintains class distribution
        )
    except Exception as e:
        print(f"[SPLIT] Stratified split failed: {e}")
        print(f"[SPLIT] Falling back to random split")
        X_train, X_test, y_train, y_test = train_test_split(
            X, y_series,
            test_size=actual_test_size,
            random_state=random_state
        )
    
    # Reconstruct dataframes
    train_df = X_train.copy()
    train_df[target] = y_train
    
    test_df = X_test.copy()
    test_df[target] = y_test
    
    # Calculate split statistics
    train_bad = (y_train == 1).sum()
    train_good = (y_train == 0).sum()
    train_bad_rate = train_bad / len(y_train) if len(y_train) > 0 else 0
    
    test_bad = (y_test == 1).sum()
    test_good = (y_test == 0).sum()
    test_bad_rate = test_bad / len(y_test) if len(y_test) > 0 else 0
    
    print(f"\n[SPLIT] Training set: {len(train_df)} samples")
    print(f"  Bad: {train_bad} ({train_bad_rate:.2%}), Good: {train_good} ({1-train_bad_rate:.2%})")
    
    print(f"\n[SPLIT] Test set: {len(test_df)} samples")
    print(f"  Bad: {test_bad} ({test_bad_rate:.2%}), Good: {test_good} ({1-test_bad_rate:.2%})")
    
    # Verify stratification worked
    stratification_success = abs(bad_rate - train_bad_rate) < 0.01 and abs(bad_rate - test_bad_rate) < 0.01
    if not stratification_success:
        print(f"⚠️ Warning: Class distribution differs by >1% between train/test")
    else:
        print(f"✓ Stratification successful: distributions match within 1%")
    
    split_info = {
        'seed': random_state,
        'test_size': float(actual_test_size),  # Proportion (0.2 for 20%)
        'method': 'stratified',
        'train_size': len(train_df),
        'test_size_count': len(test_df),  # Count of test rows
        'train_bad': int(train_bad),
        'train_good': int(train_good),
        'test_bad': int(test_bad),
        'test_good': int(test_good),
        'train_bad_rate': float(train_bad_rate),
        'test_bad_rate': float(test_bad_rate),
        'original_bad_rate': float(bad_rate),
        'stratification_success': stratification_success
    }
    
    return train_df, test_df, split_info


def save_split_files(train_df: pd.DataFrame, test_df: pd.DataFrame, dataset_id: int, uploads_dir: str = 'uploads') -> Tuple[str, str]:
    """
    Save train and test dataframes as separate CSV files.
    
    Parameters:
    -----------
    train_df : DataFrame
        Training data
    test_df : DataFrame
        Test data
    dataset_id : int
        Dataset ID
    uploads_dir : str
        Directory to save files
        
    Returns:
    --------
    train_path : str
        Path to training CSV
    test_path : str
        Path to test CSV
    """
    import datetime
    
    # Create uploads directory if it doesn't exist
    os.makedirs(uploads_dir, exist_ok=True)
    
    # Generate filenames with timestamp
    timestamp = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    train_filename = f"train_set_dataset_{dataset_id}_{timestamp}.csv"
    test_filename = f"test_set_dataset_{dataset_id}_{timestamp}.csv"
    
    train_path = os.path.join(uploads_dir, train_filename)
    test_path = os.path.join(uploads_dir, test_filename)
    
    # Save files
    train_df.to_csv(train_path, index=False)
    test_df.to_csv(test_path, index=False)
    
    print(f"[SPLIT] Saved training set to: {train_path}")
    print(f"[SPLIT] Saved test set to: {test_path}")
    
    return train_path, test_path


def regenerate_split(df: pd.DataFrame, target: str, seed: int, test_size: float, method: str) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Regenerate split using stored parameters.
    
    Parameters:
    -----------
    df : DataFrame
        Full dataset
    target : str
        Target column
    seed : int
        Random seed (from database)
    test_size : float
        Test proportion (from database)
    method : str
        Split method (from database)
        
    Returns:
    --------
    train_df, test_df : DataFrames
        Regenerated split
    """
    X = df.drop(columns=[target])
    y = df[target]
    
    if method == 'stratified':
        try:
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=test_size, random_state=seed, stratify=y
            )
        except:
            # Fallback if stratification fails
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=test_size, random_state=seed
            )
    else:
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=seed
        )
    
    train_df = X_train.copy()
    train_df[target] = y_train
    
    test_df = X_test.copy()
    test_df[target] = y_test
    
    return train_df, test_df


def verify_split_match(train_df: pd.DataFrame, test_df: pd.DataFrame, split_info: Dict, target: str) -> bool:
    """
    Verify regenerated split matches stored info.
    
    Parameters:
    -----------
    train_df : DataFrame
        Training data
    test_df : DataFrame
        Test data
    split_info : dict
        Stored split metadata
    target : str
        Target column
        
    Returns:
    --------
    bool : True if match, False otherwise
    """
    train_size = len(train_df)
    test_size = len(test_df)
    train_bad = (train_df[target] == 1).sum()
    test_bad = (test_df[target] == 1).sum()
    
    matches = (
        train_size == split_info['train_size'] and
        test_size == split_info.get('test_size_count', split_info.get('test_size', 0)) and
        train_bad == split_info['train_bad'] and
        test_bad == split_info['test_bad']
    )
    
    if not matches:
        print(f"⚠️ WARNING: Regenerated split doesn't match stored info!")
        expected_test = split_info.get('test_size_count', split_info.get('test_size', 0))
        print(f"  Expected: train={split_info['train_size']}, test={expected_test}")
        print(f"  Got: train={train_size}, test={test_size}")
        print(f"  Expected bad: train={split_info['train_bad']}, test={split_info['test_bad']}")
        print(f"  Got bad: train={train_bad}, test={test_bad}")
        return False
    else:
        print(f"✓ Split verification passed")
        return True


def get_or_create_train_test_split(
    df: pd.DataFrame,
    target: str,
    dataset_id: int,
    test_size: float = 0.2,
    random_state: int = 42,
    force_recalculate: bool = False,
    check_data_hash: bool = True
) -> Tuple[pd.DataFrame, pd.DataFrame, Dict]:
    """
    Smart split function that reuses existing split or creates new one.
    
    Parameters:
    -----------
    df : DataFrame
        Full dataset
    target : str
        Target column
    dataset_id : int
        Dataset ID
    test_size : float
        Test proportion
    random_state : int
        Random seed
    force_recalculate : bool
        Force new split even if one exists
    check_data_hash : bool
        Check if data changed (by comparing hash)
        
    Returns:
    --------
    train_df, test_df : DataFrames
        Split datasets
    split_info : dict
        Split metadata
    """
    from db import get_train_test_split_info, save_train_test_split_metadata
    
    # Step 1: Check if split exists
    existing_split = get_train_test_split_info(dataset_id)
    
    # Step 2: Check if data changed (optional but recommended)
    data_changed = False
    if check_data_hash and existing_split:
        # Calculate hash of current data
        data_hash = calculate_data_hash(df, target)
        
        # Compare with stored hash
        stored_hash = existing_split.get('data_hash')
        if stored_hash and data_hash != stored_hash:
            print(f"[SPLIT] Data changed - hash mismatch. Recalculating split.")
            data_changed = True
    
    # Step 3: Decision
    if existing_split and not force_recalculate and not data_changed:
        # REUSE EXISTING SPLIT
        print(f"[SPLIT] Reusing existing split:")
        print(f"  - Created: {existing_split.get('split_created_at')}")
        print(f"  - Seed: {existing_split['seed']}")
        print(f"  - Method: {existing_split['method']}")
        test_count = existing_split.get('test_size_count', existing_split.get('test_size', 0))
        print(f"  - Train: {existing_split['train_size']}, Test: {test_count}")
        
        # Regenerate using stored parameters
        train_df, test_df = regenerate_split(
            df, target,
            seed=existing_split['seed'],
            test_size=existing_split['test_size'],
            method=existing_split['method']
        )
        
        # Verify it matches
        verify_split_match(train_df, test_df, existing_split, target)
        
        return train_df, test_df, existing_split
    else:
        # CREATE NEW SPLIT
        reason = "new dataset" if not existing_split else ("forced" if force_recalculate else "data changed")
        print(f"[SPLIT] Creating new split (reason: {reason})")
        
        # Create new split
        train_df, test_df, split_info = create_stratified_split(
            df, target, test_size, random_state
        )
        
        # Calculate data hash for future comparison
        data_hash = calculate_data_hash(df, target)
        split_info['data_hash'] = data_hash
        
        # Save split files
        train_path, test_path = save_split_files(train_df, test_df, dataset_id)
        split_info['train_path'] = train_path
        split_info['test_path'] = test_path
        
        # Save to database
        save_train_test_split_metadata(dataset_id, split_info)
        
        return train_df, test_df, split_info

