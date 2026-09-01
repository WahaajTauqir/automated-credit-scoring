"""
Train/Test Split Module

This module handles the critical train/test split that happens
AFTER preprocessing and BEFORE binning or WOE calculation to prevent data leakage.

Key principles:
1. Preprocessing happens on full dataset first (cleaning, missing value handling)
2. Split happens on preprocessed data (ensures split is on clean data)
3. All learning (binning boundaries, WOE values, model training) uses train set only
4. Test set is held out until final evaluation
5. Stratified split maintains class distribution (critical for imbalanced data)
6. Split is reproducible via random seed
7. Preprocessed train/test files are saved for efficient loading
"""

import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from typing import Tuple, Dict, Optional
import hashlib
import os
from config import DEFAULT_TEST_SIZE, DEFAULT_RANDOM_STATE, MIN_TEST_BAD_CASES


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
    test_size: float = DEFAULT_TEST_SIZE,
    random_state: int = DEFAULT_RANDOM_STATE,
    min_test_bad: int = MIN_TEST_BAD_CASES
) -> Tuple[pd.DataFrame, pd.DataFrame, Dict]:
    """
    Create stratified train/test split on the provided dataset.
    
    Note: This function can be called on either raw or preprocessed data.
    If preprocessing happens before split, this will be called on preprocessed data.
    
    Parameters:
    -----------
    df : DataFrame
        Full dataset (may be raw or preprocessed)
    target : str
        Target column name
    test_size : float
        Proportion for test set (default from config.py: DEFAULT_TEST_SIZE)
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
    print(f"\n[TTS DEBUG] {'='*80}")
    print(f"[TTS DEBUG] create_stratified_split() called")
    print(f"[TTS DEBUG] {'='*80}")
    print(f"[TTS DEBUG] Input DataFrame shape: {df.shape}")
    print(f"[TTS DEBUG] Target column: {target}")
    print(f"[TTS DEBUG] Test size: {test_size} ({test_size*100:.1f}% test, {(1-test_size)*100:.1f}% train)")
    print(f"[TTS DEBUG] Random state: {random_state}")
    print(f"[TTS DEBUG] Min test bad cases: {min_test_bad}")
    
    # Validate target exists
    if target not in df.columns:
        print(f"[TTS DEBUG] ✗ ERROR: Target column '{target}' not found in dataset")
        raise ValueError(f"Target column '{target}' not found in dataset")
    
    # Get target distribution
    y = df[target]
    n_total = len(df)
    n_bad = (y == 1).sum()
    n_good = (y == 0).sum()
    bad_rate = n_bad / n_total if n_total > 0 else 0
    
    print(f"\n[TTS DEBUG] Target distribution analysis:")
    print(f"[TTS DEBUG]   Total samples: {n_total}")
    print(f"[TTS DEBUG]   Bad (class 1): {n_bad} ({bad_rate:.2%})")
    print(f"[TTS DEBUG]   Good (class 0): {n_good} ({(1-bad_rate):.2%})")
    print(f"[TTS DEBUG]   Imbalance ratio: {n_good/n_bad:.2f}:1 (Good:Bad)" if n_bad > 0 else "[TTS DEBUG]   Imbalance ratio: N/A (no bad cases)")
    
    # Check if we have enough bad cases
    if n_bad < 10:
        print(f"[TTS DEBUG] ✗ ERROR: Insufficient bad cases ({n_bad}). Need at least 10 for meaningful split.")
        raise ValueError(f"Insufficient bad cases ({n_bad}). Need at least 10 for meaningful split.")
    
    # STRICT SPLIT: Always use the requested test_size (from config.py by default)
    # Only warn if test set will have very few bad cases, but don't adjust
    actual_test_size = test_size  # Always use the requested size
    expected_test_bad = int(n_bad * actual_test_size)
    expected_test_good = int(n_good * actual_test_size)
    expected_train_bad = n_bad - expected_test_bad
    expected_train_good = n_good - expected_test_good
    
    print(f"\n[TTS DEBUG] Expected split distribution:")
    print(f"[TTS DEBUG]   Train set: ~{int(n_total * (1-actual_test_size))} samples")
    print(f"[TTS DEBUG]     Expected bad: {expected_train_bad} ({expected_train_bad/(n_total*(1-actual_test_size))*100:.2f}%)")
    print(f"[TTS DEBUG]     Expected good: {expected_train_good} ({expected_train_good/(n_total*(1-actual_test_size))*100:.2f}%)")
    print(f"[TTS DEBUG]   Test set: ~{int(n_total * actual_test_size)} samples")
    print(f"[TTS DEBUG]     Expected bad: {expected_test_bad} ({expected_test_bad/(n_total*actual_test_size)*100:.2f}%)")
    print(f"[TTS DEBUG]     Expected good: {expected_test_good} ({expected_test_good/(n_total*actual_test_size)*100:.2f}%)")
    
    if expected_test_bad < min_test_bad:
        print(f"[TTS DEBUG] ⚠️  WARNING: Test set will have only ~{expected_test_bad} bad cases (recommended: {min_test_bad})")
        print(f"[TTS DEBUG] ⚠️  Consider collecting more data or reducing min_test_bad requirement")
        print(f"[TTS DEBUG] ⚠️  Proceeding with {actual_test_size:.1%} test size as requested (80/20 split)")
    else:
        print(f"[TTS DEBUG] ✓ Test set will have ~{expected_test_bad} bad cases (sufficient for evaluation)")
    
    # Perform stratified split
    print(f"\n[TTS DEBUG] Performing stratified split...")
    X = df.drop(columns=[target])
    y_series = df[target]
    
    try:
        print(f"[TTS DEBUG] Attempting stratified split with stratify=True...")
        X_train, X_test, y_train, y_test = train_test_split(
            X, y_series,
            test_size=actual_test_size,
            random_state=random_state,
            stratify=y_series  # Maintains class distribution
        )
        print(f"[TTS DEBUG] ✓ Stratified split succeeded")
    except Exception as e:
        print(f"[TTS DEBUG] ✗ Stratified split failed: {e}")
        print(f"[TTS DEBUG] Falling back to random split (without stratification)")
        X_train, X_test, y_train, y_test = train_test_split(
            X, y_series,
            test_size=actual_test_size,
            random_state=random_state
        )
        print(f"[TTS DEBUG] ✓ Random split completed")
    
    # Reconstruct dataframes
    print(f"[TTS DEBUG] Reconstructing DataFrames...")
    train_df = X_train.copy()
    train_df[target] = y_train
    
    test_df = X_test.copy()
    test_df[target] = y_test
    
    print(f"[TTS DEBUG] ✓ DataFrames reconstructed")
    print(f"[TTS DEBUG]   Train shape: {train_df.shape}")
    print(f"[TTS DEBUG]   Test shape: {test_df.shape}")
    
    # Calculate split statistics
    train_bad = (y_train == 1).sum()
    train_good = (y_train == 0).sum()
    train_total = len(y_train)
    train_bad_rate = train_bad / train_total if train_total > 0 else 0
    
    test_bad = (y_test == 1).sum()
    test_good = (y_test == 0).sum()
    test_total = len(y_test)
    test_bad_rate = test_bad / test_total if test_total > 0 else 0
    
    print(f"\n[TTS DEBUG] Actual split results:")
    print(f"[TTS DEBUG] Training set: {train_total} samples ({train_total/n_total*100:.2f}% of total)")
    print(f"[TTS DEBUG]   Bad: {train_bad} ({train_bad_rate:.2%})")
    print(f"[TTS DEBUG]   Good: {train_good} ({(1-train_bad_rate):.2%})")
    
    print(f"[TTS DEBUG] Test set: {test_total} samples ({test_total/n_total*100:.2f}% of total)")
    print(f"[TTS DEBUG]   Bad: {test_bad} ({test_bad_rate:.2%})")
    print(f"[TTS DEBUG]   Good: {test_good} ({(1-test_bad_rate):.2%})")
    
    # Verify stratification worked
    train_diff = abs(bad_rate - train_bad_rate)
    test_diff = abs(bad_rate - test_bad_rate)
    stratification_success = train_diff < 0.01 and test_diff < 0.01
    
    print(f"\n[TTS DEBUG] Stratification verification:")
    print(f"[TTS DEBUG]   Original bad rate: {bad_rate:.4f}")
    print(f"[TTS DEBUG]   Train bad rate: {train_bad_rate:.4f} (diff: {train_diff:.4f})")
    print(f"[TTS DEBUG]   Test bad rate: {test_bad_rate:.4f} (diff: {test_diff:.4f})")
    
    if not stratification_success:
        print(f"[TTS DEBUG] ⚠️  WARNING: Class distribution differs by >1% between train/test")
        print(f"[TTS DEBUG]   Train difference: {train_diff*100:.2f}%")
        print(f"[TTS DEBUG]   Test difference: {test_diff*100:.2f}%")
    else:
        print(f"[TTS DEBUG] ✓ Stratification successful: distributions match within 1%")
    
    # Additional validation
    print(f"\n[TTS DEBUG] Split validation:")
    print(f"[TTS DEBUG]   Train + Test = {train_total + test_total} (expected: {n_total}) {'✓' if (train_total + test_total) == n_total else '✗ MISMATCH'}")
    print(f"[TTS DEBUG]   Train bad + Test bad = {train_bad + test_bad} (expected: {n_bad}) {'✓' if (train_bad + test_bad) == n_bad else '✗ MISMATCH'}")
    print(f"[TTS DEBUG]   Train good + Test good = {train_good + test_good} (expected: {n_good}) {'✓' if (train_good + test_good) == n_good else '✗ MISMATCH'}")
    
    split_info = {
        'seed': random_state,
        'test_size': float(actual_test_size),  # Proportion from config.py
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
    
    # Print ASSIGNED_STORE_ID values after TTS
    column_name = "ASSIGNED_STORE_ID"
    print(f"\n{'='*80}")
    print(f"[TTS] ASSIGNED_STORE_ID Column Values After Train-Test Split")
    print(f"{'='*80}")
    
    if column_name in train_df.columns:
        train_values = train_df[column_name].dropna().unique()
        train_value_counts = train_df[column_name].value_counts()
        print(f"\n[TTS] TRAIN SET - ASSIGNED_STORE_ID:")
        print(f"  Total rows: {len(train_df)}")
        print(f"  Non-null rows: {train_df[column_name].notna().sum()}")
        print(f"  Null rows: {train_df[column_name].isna().sum()}")
        print(f"  Unique values: {len(train_values)}")
        print(f"  All unique values: {sorted(train_values.tolist())}")
        print(f"  Value counts:")
        for val, count in train_value_counts.head(20).items():
            print(f"    {val}: {count}")
        if len(train_value_counts) > 20:
            print(f"    ... and {len(train_value_counts) - 20} more values")
    else:
        print(f"\n[TTS] TRAIN SET - Column '{column_name}' NOT FOUND")
    
    if column_name in test_df.columns:
        test_values = test_df[column_name].dropna().unique()
        test_value_counts = test_df[column_name].value_counts()
        print(f"\n[TTS] TEST SET - ASSIGNED_STORE_ID:")
        print(f"  Total rows: {len(test_df)}")
        print(f"  Non-null rows: {test_df[column_name].notna().sum()}")
        print(f"  Null rows: {test_df[column_name].isna().sum()}")
        print(f"  Unique values: {len(test_values)}")
        print(f"  All unique values: {sorted(test_values.tolist())}")
        print(f"  Value counts:")
        for val, count in test_value_counts.head(20).items():
            print(f"    {val}: {count}")
        if len(test_value_counts) > 20:
            print(f"    ... and {len(test_value_counts) - 20} more values")
    else:
        print(f"\n[TTS] TEST SET - Column '{column_name}' NOT FOUND")
    
    print(f"{'='*80}\n")
    
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
    
    print(f"\n[TTS DEBUG] save_split_files() called")
    print(f"[TTS DEBUG]   Train shape: {train_df.shape}")
    print(f"[TTS DEBUG]   Test shape: {test_df.shape}")
    print(f"[TTS DEBUG]   Dataset ID: {dataset_id}")
    print(f"[TTS DEBUG]   Uploads directory: {uploads_dir}")
    
    # Create uploads directory if it doesn't exist
    os.makedirs(uploads_dir, exist_ok=True)
    print(f"[TTS DEBUG] ✓ Directory created/verified: {uploads_dir}")
    
    # Generate filenames with timestamp
    timestamp = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    train_filename = f"train_set_dataset_{dataset_id}_{timestamp}.csv"
    test_filename = f"test_set_dataset_{dataset_id}_{timestamp}.csv"
    
    train_path = os.path.join(uploads_dir, train_filename)
    test_path = os.path.join(uploads_dir, test_filename)
    
    print(f"[TTS DEBUG]   Train filename: {train_filename}")
    print(f"[TTS DEBUG]   Test filename: {test_filename}")
    
    # CRITICAL: Verify encoding before saving
    print(f"[TTS DEBUG] Verifying encoding before saving...")
    train_object_cols = [col for col in train_df.columns 
                        if train_df[col].dtype == 'object' or 
                        str(train_df[col].dtype).startswith('string')]
    test_object_cols = [col for col in test_df.columns 
                       if test_df[col].dtype == 'object' or 
                       str(test_df[col].dtype).startswith('string')]
    
    if train_object_cols or test_object_cols:
        print(f"[TTS DEBUG] ⚠️  CRITICAL ERROR: Found unencoded object columns!")
        print(f"[TTS DEBUG]   Train unencoded: {train_object_cols}")
        print(f"[TTS DEBUG]   Test unencoded: {test_object_cols}")
        print(f"[TTS DEBUG]   FORCING ENCODING NOW before saving...")
        
        # Force encode them NOW - import locally to avoid circular imports
        try:
            # Try to import from app module
            import sys
            if 'app' in sys.modules:
                from app import encode_categorical_variables
            else:
                # If app not imported, import it
                import app
                encode_categorical_variables = app.encode_categorical_variables
            
            target_col = None  # We don't know the target here, but it should be encoded already
            
            if train_object_cols:
                print(f"[TTS DEBUG]   Encoding {len(train_object_cols)} train columns: {train_object_cols}")
                train_df, _, _ = encode_categorical_variables(train_df, train_object_cols, target_col)
                print(f"[TTS DEBUG]   ✓ Train columns encoded")
            
            if test_object_cols:
                print(f"[TTS DEBUG]   Encoding {len(test_object_cols)} test columns: {test_object_cols}")
                test_df, _, _ = encode_categorical_variables(test_df, test_object_cols, target_col)
                print(f"[TTS DEBUG]   ✓ Test columns encoded")
        except Exception as e:
            print(f"[TTS DEBUG] ✗ ERROR: Failed to force encode: {str(e)}")
            import traceback
            traceback.print_exc()
        
        # Verify again
        train_object_cols_after = [col for col in train_df.columns 
                                   if train_df[col].dtype == 'object']
        test_object_cols_after = [col for col in test_df.columns 
                                  if test_df[col].dtype == 'object']
        
        if train_object_cols_after or test_object_cols_after:
            print(f"[TTS DEBUG] ✗ ERROR: Still have unencoded columns after forced encoding!")
            print(f"[TTS DEBUG]   This is a critical bug - encoding function is not working!")
        else:
            print(f"[TTS DEBUG] ✓ All object columns encoded successfully")
    else:
        print(f"[TTS DEBUG] ✓ No unencoded object columns found - data is properly encoded")
    
    # Save files
    print(f"[TTS DEBUG] Saving train file...")
    print(f"[TTS DEBUG]   Train DataFrame info before save:")
    print(f"[TTS DEBUG]     Shape: {train_df.shape}")
    print(f"[TTS DEBUG]     Columns: {len(train_df.columns)}")
    print(f"[TTS DEBUG]     Memory usage: {train_df.memory_usage(deep=True).sum() / 1024 / 1024:.2f} MB")
    print(f"[TTS DEBUG]     Sample columns: {list(train_df.columns[:5])}")
    
    # Show sample data to verify encoding
    if len(train_df) > 0:
        print(f"[TTS DEBUG]     Sample row (first 5 columns):")
        for col in train_df.columns[:5]:
            sample_val = train_df[col].iloc[0]
            dtype = train_df[col].dtype
            print(f"[TTS DEBUG]       {col}: {sample_val} (dtype={dtype})")
    
    train_df.to_csv(train_path, index=False)
    train_file_size = os.path.getsize(train_path) / (1024 * 1024)  # Size in MB
    print(f"[TTS DEBUG]   ✓ Train file saved: {train_path} ({train_file_size:.2f} MB)")
    
    print(f"[TTS DEBUG] Saving test file...")
    print(f"[TTS DEBUG]   Test DataFrame info before save:")
    print(f"[TTS DEBUG]     Shape: {test_df.shape}")
    print(f"[TTS DEBUG]     Columns: {len(test_df.columns)}")
    print(f"[TTS DEBUG]     Memory usage: {test_df.memory_usage(deep=True).sum() / 1024 / 1024:.2f} MB")
    print(f"[TTS DEBUG]     Sample columns: {list(test_df.columns[:5])}")
    
    # Show sample data to verify encoding
    if len(test_df) > 0:
        print(f"[TTS DEBUG]     Sample row (first 5 columns):")
        for col in test_df.columns[:5]:
            sample_val = test_df[col].iloc[0]
            dtype = test_df[col].dtype
            print(f"[TTS DEBUG]       {col}: {sample_val} (dtype={dtype})")
    
    test_df.to_csv(test_path, index=False)
    test_file_size = os.path.getsize(test_path) / (1024 * 1024)  # Size in MB
    print(f"[TTS DEBUG]   ✓ Test file saved: {test_path} ({test_file_size:.2f} MB)")
    
    print(f"[TTS DEBUG] ✓ Both files saved successfully")
    print(f"[TTS DEBUG] NOTE: These files contain PREPROCESSED data (duplicates removed, missing handled, etc.)")
    
    # Upload to Cloud Storage if configured
    final_train_path = train_path
    final_test_path = test_path
    
    try:
        from storage import get_storage_manager
        storage_mgr = get_storage_manager()
        if storage_mgr and storage_mgr.uploads_bucket:
            print(f"[TTS DEBUG] Uploading files to Cloud Storage...")
            
            # Upload train file
            train_blob_name = f"train_test_splits/{train_filename}"
            try:
                train_gcs_path = storage_mgr.upload_file(
                    train_path,
                    storage_mgr.uploads_bucket,
                    train_blob_name
                )
                if train_gcs_path.startswith('gs://'):
                    final_train_path = train_gcs_path
                    print(f"[TTS DEBUG]   ✓ Train file uploaded to Cloud Storage: {train_gcs_path}")
                else:
                    print(f"[TTS DEBUG]   ⚠️  Train file upload returned local path (may have failed)")
            except Exception as e:
                print(f"[TTS DEBUG]   ⚠️  Warning: Failed to upload train file to Cloud Storage: {e}")
                # Continue with local path
            
            # Upload test file
            test_blob_name = f"train_test_splits/{test_filename}"
            try:
                test_gcs_path = storage_mgr.upload_file(
                    test_path,
                    storage_mgr.uploads_bucket,
                    test_blob_name
                )
                if test_gcs_path.startswith('gs://'):
                    final_test_path = test_gcs_path
                    print(f"[TTS DEBUG]   ✓ Test file uploaded to Cloud Storage: {test_gcs_path}")
                else:
                    print(f"[TTS DEBUG]   ⚠️  Test file upload returned local path (may have failed)")
            except Exception as e:
                print(f"[TTS DEBUG]   ⚠️  Warning: Failed to upload test file to Cloud Storage: {e}")
                # Continue with local path
            
            if final_train_path.startswith('gs://') and final_test_path.startswith('gs://'):
                print(f"[TTS DEBUG] ✓ Both files successfully uploaded to Cloud Storage")
            elif final_train_path.startswith('gs://') or final_test_path.startswith('gs://'):
                print(f"[TTS DEBUG] ⚠️  Partial Cloud Storage upload (one file failed)")
            else:
                print(f"[TTS DEBUG] ℹ️  Using local file paths (Cloud Storage not configured or upload failed)")
        else:
            print(f"[TTS DEBUG] ℹ️  Cloud Storage not configured, using local file paths")
    except ImportError:
        print(f"[TTS DEBUG] ℹ️  Storage module not available, using local file paths")
    except Exception as e:
        print(f"[TTS DEBUG] ⚠️  Warning: Error checking Cloud Storage: {e}")
        print(f"[TTS DEBUG]   Continuing with local file paths")
    
    return final_train_path, final_test_path


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
    test_size: float = DEFAULT_TEST_SIZE,
    random_state: int = DEFAULT_RANDOM_STATE,
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
    
    print(f"\n[TTS DEBUG] {'='*80}")
    print(f"[TTS DEBUG] get_or_create_train_test_split() called")
    print(f"[TTS DEBUG] {'='*80}")
    print(f"[TTS DEBUG] Dataset ID: {dataset_id}")
    print(f"[TTS DEBUG] Input DataFrame shape: {df.shape}")
    print(f"[TTS DEBUG] Target: {target}")
    print(f"[TTS DEBUG] Test size: {test_size} ({test_size*100:.1f}% test, {(1-test_size)*100:.1f}% train)")
    print(f"[TTS DEBUG] Random state: {random_state}")
    print(f"[TTS DEBUG] Force recalculate: {force_recalculate}")
    print(f"[TTS DEBUG] Check data hash: {check_data_hash}")
    
    # Step 1: Check if split exists
    print(f"\n[TTS DEBUG] Step 1: Checking for existing split...")
    existing_split = get_train_test_split_info(dataset_id)
    
    if existing_split:
        print(f"[TTS DEBUG] ✓ Existing split found in database")
        print(f"[TTS DEBUG]   Created: {existing_split.get('split_created_at')}")
        print(f"[TTS DEBUG]   Seed: {existing_split.get('seed')}")
        print(f"[TTS DEBUG]   Method: {existing_split.get('method')}")
        print(f"[TTS DEBUG]   Train size: {existing_split.get('train_size')}")
        print(f"[TTS DEBUG]   Test size: {existing_split.get('test_size_count', existing_split.get('test_size', 0))}")
        print(f"[TTS DEBUG]   Train bad: {existing_split.get('train_bad')}")
        print(f"[TTS DEBUG]   Test bad: {existing_split.get('test_bad')}")
    else:
        print(f"[TTS DEBUG] ✗ No existing split found")
    
    # Step 2: Check if data changed (optional but recommended)
    data_changed = False
    if check_data_hash and existing_split:
        print(f"\n[TTS DEBUG] Step 2: Checking data hash...")
        # Calculate hash of current data
        data_hash = calculate_data_hash(df, target)
        print(f"[TTS DEBUG]   Current data hash: {data_hash}")
        
        # Compare with stored hash
        stored_hash = existing_split.get('data_hash')
        if stored_hash:
            print(f"[TTS DEBUG]   Stored data hash: {stored_hash}")
            if data_hash != stored_hash:
                print(f"[TTS DEBUG]   ✗ Hash mismatch - data has changed")
                data_changed = True
            else:
                print(f"[TTS DEBUG]   ✓ Hash matches - data unchanged")
        else:
            print(f"[TTS DEBUG]   ⚠️  No stored hash found (old split)")
    else:
        print(f"[TTS DEBUG] Step 2: Skipping data hash check")
    
    # Step 3: Decision
    print(f"\n[TTS DEBUG] Step 3: Decision logic...")
    if existing_split and not force_recalculate and not data_changed:
        # REUSE EXISTING SPLIT
        print(f"[TTS DEBUG] ✓ REUSING EXISTING SPLIT")
        print(f"[TTS DEBUG]   Reason: Split exists, not forced, data unchanged")
        print(f"[TTS DEBUG]   Created: {existing_split.get('split_created_at')}")
        print(f"[TTS DEBUG]   Seed: {existing_split['seed']}")
        print(f"[TTS DEBUG]   Method: {existing_split['method']}")
        test_count = existing_split.get('test_size_count', existing_split.get('test_size', 0))
        print(f"[TTS DEBUG]   Train: {existing_split['train_size']}, Test: {test_count}")
        
        # Try to load from saved files first (these are preprocessed if split was created with preprocessing)
        train_path = existing_split.get('train_path')
        test_path = existing_split.get('test_path')
        
        if train_path and test_path and os.path.exists(train_path) and os.path.exists(test_path):
            print(f"[TTS DEBUG] Loading from saved preprocessed files (preprocessing was done before split)...")
            print(f"[TTS DEBUG]   Train file: {train_path}")
            print(f"[TTS DEBUG]   Test file: {test_path}")
            try:
                train_df = pd.read_csv(train_path)
                test_df = pd.read_csv(test_path)
                print(f"[TTS DEBUG] ✓ Loaded from saved files:")
                print(f"[TTS DEBUG]   Train: {len(train_df)} rows, {len(train_df.columns)} columns")
                print(f"[TTS DEBUG]   Test: {len(test_df)} rows, {len(test_df.columns)} columns")
                
                # Verify it matches stored info
                print(f"[TTS DEBUG] Verifying loaded split matches stored info...")
                verify_split_match(train_df, test_df, existing_split, target)
                
                print(f"[TTS DEBUG] {'='*80}")
                print(f"[TTS DEBUG] Returning existing split (loaded from saved files)")
                print(f"[TTS DEBUG] {'='*80}\n")
                
                return train_df, test_df, existing_split
            except Exception as e:
                print(f"[TTS DEBUG] ✗ WARNING: Failed to load saved files: {e}")
                print(f"[TTS DEBUG] Falling back to regenerating from provided DataFrame...")
                import traceback
                traceback.print_exc()
        
        # Fallback: Regenerate using stored parameters
        # NOTE: If df is raw data but split was created with preprocessing, this will be wrong!
        # We should preprocess df first if saved files don't exist
        print(f"[TTS DEBUG] Regenerating split using stored parameters...")
        print(f"[TTS DEBUG] ⚠️  WARNING: Regenerating from provided DataFrame.")
        print(f"[TTS DEBUG]   If split was created with preprocessing, DataFrame should be preprocessed!")
        print(f"[TTS DEBUG]   Input DataFrame shape: {df.shape}")
        
        train_df, test_df = regenerate_split(
            df, target,
            seed=existing_split['seed'],
            test_size=existing_split['test_size'],
            method=existing_split['method']
        )
        print(f"[TTS DEBUG] ✓ Split regenerated: train={len(train_df)}, test={len(test_df)}")
        
        # Verify it matches
        print(f"[TTS DEBUG] Verifying regenerated split matches stored info...")
        verify_split_match(train_df, test_df, existing_split, target)
        
        print(f"[TTS DEBUG] {'='*80}")
        print(f"[TTS DEBUG] Returning existing split (regenerated)")
        print(f"[TTS DEBUG] {'='*80}\n")
        
        return train_df, test_df, existing_split
    else:
        # CREATE NEW SPLIT
        reason = "new dataset" if not existing_split else ("forced" if force_recalculate else "data changed")
        print(f"[TTS DEBUG] ✗ CREATING NEW SPLIT")
        print(f"[TTS DEBUG]   Reason: {reason}")
        
        # Create new split
        print(f"[TTS DEBUG] Calling create_stratified_split()...")
        train_df, test_df, split_info = create_stratified_split(
            df, target, test_size, random_state
        )
        print(f"[TTS DEBUG] ✓ New split created: train={len(train_df)}, test={len(test_df)}")
        
        # Calculate data hash for future comparison
        print(f"[TTS DEBUG] Calculating data hash for future comparison...")
        data_hash = calculate_data_hash(df, target)
        split_info['data_hash'] = data_hash
        print(f"[TTS DEBUG]   Data hash: {data_hash}")
        
        # Verify data is preprocessed before saving
        # Check for common preprocessing indicators
        print(f"[TTS DEBUG] Verifying data is preprocessed before saving...")
        train_duplicate_count = train_df.duplicated().sum()
        test_duplicate_count = test_df.duplicated().sum()
        train_has_duplicates = train_duplicate_count > 0
        test_has_duplicates = test_duplicate_count > 0
        train_missing_pct = train_df.isnull().sum().sum() / (len(train_df) * len(train_df.columns)) * 100 if len(train_df) > 0 else 0
        test_missing_pct = test_df.isnull().sum().sum() / (len(test_df) * len(test_df.columns)) * 100 if len(test_df) > 0 else 0
        
        # Check for categorical encoding (if discrete columns exist, check if they're encoded)
        train_categorical_cols = train_df.select_dtypes(include=['object']).columns.tolist()
        test_categorical_cols = test_df.select_dtypes(include=['object']).columns.tolist()
        # Remove target from categorical check
        if target in train_categorical_cols:
            train_categorical_cols.remove(target)
        if target in test_categorical_cols:
            test_categorical_cols.remove(target)
        
        print(f"[TTS DEBUG]   Train duplicates: {train_duplicate_count} (0 = preprocessed)")
        print(f"[TTS DEBUG]   Test duplicates: {test_duplicate_count} (0 = preprocessed)")
        print(f"[TTS DEBUG]   Train missing %: {train_missing_pct:.2f}% (should be low if preprocessed)")
        print(f"[TTS DEBUG]   Test missing %: {test_missing_pct:.2f}% (should be low if preprocessed)")
        print(f"[TTS DEBUG]   Train categorical columns (not encoded): {len(train_categorical_cols)}")
        print(f"[TTS DEBUG]   Test categorical columns (not encoded): {len(test_categorical_cols)}")
        if train_categorical_cols or test_categorical_cols:
            print(f"[TTS DEBUG]   ⚠️  Categorical columns found: {train_categorical_cols[:3] if train_categorical_cols else []} (label encoding may not be applied)")
        
        if train_has_duplicates or test_has_duplicates:
            print(f"[TTS DEBUG] ⚠️  WARNING: Data appears to have duplicates - may not be fully preprocessed!")
        
        if train_categorical_cols or test_categorical_cols:
            print(f"[TTS DEBUG] ⚠️  WARNING: Categorical columns are not encoded - label encoding may not be applied!")
        
        # Save split files
        print(f"[TTS DEBUG] Saving train/test files (PREPROCESSED data)...")
        train_path, test_path = save_split_files(train_df, test_df, dataset_id)
        split_info['train_path'] = train_path
        split_info['test_path'] = test_path
        print(f"[TTS DEBUG] ✓ Files saved (containing PREPROCESSED data):")
        print(f"[TTS DEBUG]   Train: {train_path}")
        print(f"[TTS DEBUG]   Test: {test_path}")
        
        # Save to database
        print(f"[TTS DEBUG] Saving split metadata to database...")
        save_train_test_split_metadata(dataset_id, split_info)
        print(f"[TTS DEBUG] ✓ Metadata saved to database")
        
        print(f"[TTS DEBUG] {'='*80}")
        print(f"[TTS DEBUG] Returning new split")
        print(f"[TTS DEBUG] {'='*80}\n")
        
        return train_df, test_df, split_info

