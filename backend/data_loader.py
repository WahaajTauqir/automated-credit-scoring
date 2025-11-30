"""
Data Loader Module

This module provides functions to load the correct dataset (train or test)
based on the pipeline stage to prevent data leakage.

Pipeline Flow:
1. Variable Classification (target selection)
2. Preprocessing: Full dataset is preprocessed (cleaning, missing values, etc.)
3. Train/Test Split: Split happens on preprocessed data
4. Binning: Learn bin boundaries from TRAIN only
5. WOE Calculation: Calculate WOE from TRAIN only
6. Model Training: Train on TRAIN only
7. Model Evaluation: Evaluate on TEST only

Data Leakage Prevention Rules:
- Preprocessing happens on full dataset before split (ensures clean data for split)
- All learning (binning boundaries, WOE values, model training) uses train set only
- Test set is held out until final evaluation

The key principle: TEST SET IS NEVER SEEN until final evaluation!
"""

import pandas as pd
import os
from typing import Tuple, Optional
from db import get_train_test_split_info, get_dataset

# Cache for train/test data to avoid reloading
_tts_cache = {}  # {dataset_id: (train_df, test_df, split_info)}


def get_train_test_data(dataset_id: int) -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame], bool]:
    """
    Load train and test datasets if split exists.
    
    This function first tries to load from saved preprocessed train/test files.
    If those don't exist, it falls back to regenerating from the raw CSV.
    
    Uses caching to avoid reloading the same data multiple times.
    
    Parameters:
    -----------
    dataset_id : int
        Dataset ID
        
    Returns:
    --------
    train_df : DataFrame or None
        Training data if split exists (preprocessed if saved files exist)
    test_df : DataFrame or None
        Test data if split exists (preprocessed if saved files exist)
    split_exists : bool
        Whether split exists
    """
    # Check cache first
    if dataset_id in _tts_cache:
        cached_train, cached_test, cached_info = _tts_cache[dataset_id]
        print(f"[TTS CACHE] ✓ Using cached train/test data for dataset {dataset_id}")
        return cached_train.copy(), cached_test.copy(), True
    
    split_info = get_train_test_split_info(dataset_id)
    
    if not split_info:
        return None, None, False
    
    # Try to load from saved preprocessed files first (if split was created after preprocessing)
    print(f"\n[TTS DEBUG] {'='*80}")
    print(f"[TTS DEBUG] get_train_test_data() - Loading split data")
    print(f"[TTS DEBUG] {'='*80}")
    print(f"[TTS DEBUG] Dataset ID: {dataset_id}")
    
    train_path = split_info.get('train_path')
    test_path = split_info.get('test_path')
    
    print(f"[TTS DEBUG] Checking for saved preprocessed files...")
    print(f"[TTS DEBUG]   Train path: {train_path}")
    print(f"[TTS DEBUG]   Test path: {test_path}")
    
    if train_path and test_path and os.path.exists(train_path) and os.path.exists(test_path):
        # Load from saved preprocessed files
        print(f"[TTS DEBUG] ✓ Saved files found, loading from preprocessed files...")
        print(f"[TTS DEBUG]   Train file exists: {os.path.exists(train_path)}")
        print(f"[TTS DEBUG]   Test file exists: {os.path.exists(test_path)}")
        
        try:
            print(f"[TTS DEBUG] Loading train file: {train_path}")
            train_df = pd.read_csv(train_path)
            print(f"[TTS DEBUG]   ✓ Train loaded: {len(train_df)} rows, {len(train_df.columns)} columns")
            
            print(f"[TTS DEBUG] Loading test file: {test_path}")
            test_df = pd.read_csv(test_path)
            print(f"[TTS DEBUG]   ✓ Test loaded: {len(test_df)} rows, {len(test_df.columns)} columns")
            
            # Verify data appears to be preprocessed
            print(f"[TTS DEBUG] Verifying loaded data is preprocessed...")
            train_duplicates = train_df.duplicated().sum()
            test_duplicates = test_df.duplicated().sum()
            train_missing_pct = train_df.isnull().sum().sum() / (len(train_df) * len(train_df.columns)) * 100 if len(train_df) > 0 else 0
            test_missing_pct = test_df.isnull().sum().sum() / (len(test_df) * len(test_df.columns)) * 100 if len(test_df) > 0 else 0
            
            print(f"[TTS DEBUG]   Train duplicates: {train_duplicates} (0 = preprocessed)")
            print(f"[TTS DEBUG]   Test duplicates: {test_duplicates} (0 = preprocessed)")
            print(f"[TTS DEBUG]   Train missing %: {train_missing_pct:.2f}%")
            print(f"[TTS DEBUG]   Test missing %: {test_missing_pct:.2f}%")
            
            if train_duplicates > 0 or test_duplicates > 0:
                print(f"[TTS DEBUG] ⚠️  WARNING: Loaded files contain duplicates - data may not be preprocessed!")
                print(f"[TTS DEBUG]   Consider recreating split with preprocess_first=true")
            
            # Debug: Show target distribution
            if target in train_df.columns and target in test_df.columns:
                train_dist = train_df[target].value_counts()
                test_dist = test_df[target].value_counts()
                print(f"[TTS DEBUG] Train target distribution: {dict(train_dist)}")
                print(f"[TTS DEBUG] Test target distribution: {dict(test_dist)}")
            
            print(f"[TTS DEBUG] ✓ Successfully loaded from saved files")
        except Exception as e:
            print(f"[TTS DEBUG] ✗ ERROR: Failed to load saved files: {e}")
            print(f"[TTS DEBUG] Falling back to regenerating from raw CSV...")
            import traceback
            traceback.print_exc()
            train_path = None  # Force fallback
            test_path = None
    else:
        print(f"[TTS DEBUG] ✗ Saved files not found or paths missing")
        if not train_path:
            print(f"[TTS DEBUG]   Train path is None")
        elif not os.path.exists(train_path):
            print(f"[TTS DEBUG]   Train file does not exist: {train_path}")
        if not test_path:
            print(f"[TTS DEBUG]   Test path is None")
        elif not os.path.exists(test_path):
            print(f"[TTS DEBUG]   Test file does not exist: {test_path}")
        print(f"[TTS DEBUG] Falling back to regenerating from raw CSV...")
    
    # Fallback: Regenerate from raw CSV (for backward compatibility or if saved files don't exist)
    if not train_path or not test_path:
        print(f"[TTS DEBUG] Regenerating split from raw CSV (saved files not available)")
        print(f"[TTS DEBUG]   ⚠️  IMPORTANT: Preprocessing will be applied before regenerating split")
        print(f"[TTS DEBUG]   This ensures consistency with splits created after preprocessing")
        
        dataset = get_dataset(dataset_id)
        if not dataset:
            print(f"[TTS DEBUG] ✗ ERROR: Dataset not found")
            return None, None, False
        
        # Load full dataset
        from train_test_split import regenerate_split
        # Lazy import to avoid circular dependency (app.py imports from data_loader)
        # preprocess_dataset is defined in app.py
        
        csv_path = get_csv_path(dataset_id)
        print(f"[TTS DEBUG] Loading raw CSV: {csv_path}")
        df = pd.read_csv(csv_path)
        print(f"[TTS DEBUG]   ✓ Raw CSV loaded: {len(df)} rows, {len(df.columns)} columns")
        
        target = dataset.get('target_variable')
        if not target:
            print(f"[TTS DEBUG] ✗ ERROR: Target variable not set")
            return None, None, False
        
        # CRITICAL: Preprocess before regenerating split (same as when creating new split)
        print(f"[TTS DEBUG] Preprocessing data before regenerating split...")
        print(f"[TTS DEBUG]   Original shape: {df.shape}")
        
        try:
            # Lazy import to avoid circular dependency
            import app
            preprocess_dataset = app.preprocess_dataset
            
            df_before = df.copy()
            df, preprocessing_report = preprocess_dataset(
                df,
                target_col=target,
                preprocessing_steps={
                    'detect_types': True,
                    'handle_missing': True,
                    'remove_duplicates': True,
                    'handle_outliers': False,  # Don't handle outliers before split
                    'encode_categorical': True  # Enable label encoding before split (ensures consistent encoding across train/test)
                },
                missing_threshold=0.5,
                treat_negative_one_as_missing=True,
                verbose=False
            )
            
            rows_removed = len(df_before) - len(df)
            print(f"[TTS DEBUG]   ✓ Preprocessing completed")
            print(f"[TTS DEBUG]   After preprocessing shape: {df.shape}")
            print(f"[TTS DEBUG]   Rows removed: {rows_removed} ({rows_removed/len(df_before)*100:.2f}%)")
        except Exception as e:
            print(f"[TTS DEBUG] ✗ WARNING: Preprocessing failed: {e}")
            print(f"[TTS DEBUG] Continuing with raw data (may cause mismatch if split was created with preprocessing)")
            import traceback
            traceback.print_exc()
        
        print(f"[TTS DEBUG] Regenerating split with parameters:")
        print(f"[TTS DEBUG]   Seed: {split_info['seed']}")
        print(f"[TTS DEBUG]   Test size: {split_info['test_size']}")
        print(f"[TTS DEBUG]   Method: {split_info['method']}")
        print(f"[TTS DEBUG]   Using preprocessed data: {df.shape}")
        
        # Regenerate split
        train_df, test_df = regenerate_split(
            df, target,
            seed=split_info['seed'],
            test_size=split_info['test_size'],
            method=split_info['method']
        )
        print(f"[TTS DEBUG] ✓ Split regenerated:")
        print(f"[TTS DEBUG]   Train: {len(train_df)} rows, {len(train_df.columns)} columns")
        print(f"[TTS DEBUG]   Test: {len(test_df)} rows, {len(test_df.columns)} columns")
        
        # Debug: Show target distribution
        if target in train_df.columns and target in test_df.columns:
            train_dist = train_df[target].value_counts()
            test_dist = test_df[target].value_counts()
            print(f"[TTS DEBUG] Train target distribution: {dict(train_dist)}")
            print(f"[TTS DEBUG] Test target distribution: {dict(test_dist)}")
        
        # Cache the loaded data
        _tts_cache[dataset_id] = (train_df.copy(), test_df.copy(), split_info)
        print(f"[TTS CACHE] ✓ Cached train/test data for dataset {dataset_id}")
    
    # Print ASSIGNED_STORE_ID values when split is loaded
    column_name = "ASSIGNED_STORE_ID"
    print(f"\n{'='*80}")
    print(f"[DATA_LOADER] ASSIGNED_STORE_ID Column Values After Loading Train-Test Split")
    print(f"{'='*80}")
    
    if column_name in train_df.columns:
        train_values = train_df[column_name].dropna().unique()
        train_value_counts = train_df[column_name].value_counts()
        print(f"\n[DATA_LOADER] TRAIN SET - ASSIGNED_STORE_ID:")
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
        print(f"\n[DATA_LOADER] TRAIN SET - Column '{column_name}' NOT FOUND")
    
    if column_name in test_df.columns:
        test_values = test_df[column_name].dropna().unique()
        test_value_counts = test_df[column_name].value_counts()
        print(f"\n[DATA_LOADER] TEST SET - ASSIGNED_STORE_ID:")
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
        print(f"\n[DATA_LOADER] TEST SET - Column '{column_name}' NOT FOUND")
    
    print(f"{'='*80}\n")
    
    return train_df, test_df, True


def get_csv_path(dataset_id: int) -> str:
    """
    Get CSV path for a dataset.
    
    Parameters:
    -----------
    dataset_id : int
        Dataset ID
        
    Returns:
    --------
    str : Path to CSV file
    """
    dataset = get_dataset(dataset_id)
    if not dataset:
        raise FileNotFoundError(f"Dataset {dataset_id} not found")
    
    file_path = dataset.get('file_path')
    if not file_path:
        raise FileNotFoundError(f"No file path for dataset {dataset_id}")
    
    # Try different path strategies
    # 1. Relative to backend folder
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    candidate = os.path.join(backend_dir, file_path)
    if os.path.exists(candidate):
        return candidate
    
    # 2. Absolute path
    if os.path.isabs(file_path) and os.path.exists(file_path):
        return file_path
    
    # 3. In uploads folder
    uploads_dir = os.path.join(backend_dir, 'uploads')
    maybe = os.path.join(uploads_dir, os.path.basename(file_path))
    if os.path.exists(maybe):
        return maybe
    
    # 4. Last resort: most recent CSV in uploads
    if os.path.exists(uploads_dir):
        files = [os.path.join(uploads_dir, f) for f in os.listdir(uploads_dir) if f.lower().endswith('.csv')]
        if files:
            files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
            return files[0]
    
    raise FileNotFoundError(f'No CSV found for dataset {dataset_id}')


def get_data_for_stage(dataset_id: int, stage: str) -> pd.DataFrame:
    """
    Get the correct dataset for a pipeline stage to prevent data leakage.
    
    Parameters:
    -----------
    dataset_id : int
        Dataset ID
    stage : str
        Pipeline stage: 'preprocessing', 'binning', 'woe', 'training', 'evaluation'
        
    Returns:
    --------
    DataFrame : The appropriate dataset for this stage
    
    Stage Logic:
    ------------
    - preprocessing: TRAIN only (learn preprocessing parameters)
    - binning: TRAIN only (learn bin boundaries)
    - woe: TRAIN only (calculate WOE values)
    - training: TRAIN only (train model)
    - evaluation: TEST only (evaluate model)
    - full: Full dataset (for initial exploration only)
    """
    train_df, test_df, split_exists = get_train_test_data(dataset_id)
    
    if not split_exists:
        # No split exists - use full dataset
        # This should only happen during initial data exploration
        print(f"[DATA_LOADER] No train/test split exists for dataset {dataset_id}. Using full dataset.")
        print(f"[DATA_LOADER] WARNING: Create train/test split before preprocessing/binning!")
        try:
            csv_path = get_csv_path(dataset_id)
            df = pd.read_csv(csv_path)
            if df.empty:
                raise ValueError(f"Dataset {dataset_id} is empty")
            print(f"[DATA_LOADER] Loaded full dataset: {len(df)} rows, {len(df.columns)} columns")
            return df
        except Exception as e:
            print(f"[DATA_LOADER] ERROR loading full dataset: {str(e)}")
            raise
    
    # Split exists - return appropriate dataset based on stage
    if stage in ['preprocessing', 'binning', 'woe', 'training']:
        if train_df is None:
            raise ValueError(f"Train set is None for dataset {dataset_id}")
        if train_df.empty:
            raise ValueError(f"Train set is empty for dataset {dataset_id} (0 rows)")
        if len(train_df.columns) == 0:
            raise ValueError(f"Train set has no columns for dataset {dataset_id}")
        print(f"[DATA_LOADER] Stage '{stage}': Using TRAIN set ({len(train_df)} rows, {len(train_df.columns)} columns)")
        return train_df
    elif stage == 'evaluation':
        print(f"[DATA_LOADER] Stage 'evaluation': Using TEST set ({len(test_df)} rows)")
        return test_df
    elif stage == 'full':
        # Special case: return full dataset
        print(f"[DATA_LOADER] Stage 'full': Using full dataset")
        csv_path = get_csv_path(dataset_id)
        return pd.read_csv(csv_path)
    else:
        raise ValueError(f"Unknown stage: {stage}. Valid stages: preprocessing, binning, woe, training, evaluation, full")


def apply_learned_transformations_to_test(dataset_id: int, learned_params: dict) -> pd.DataFrame:
    """
    Apply transformations learned from training set to test set.
    
    This function ensures test set uses the SAME transformations
    that were learned from the training set.
    
    Parameters:
    -----------
    dataset_id : int
        Dataset ID
    learned_params : dict
        Parameters learned from training set (bin boundaries, WOE values, etc.)
        
    Returns:
    --------
    DataFrame : Test set with applied transformations
    """
    train_df, test_df, split_exists = get_train_test_data(dataset_id)
    
    if not split_exists:
        raise ValueError(f"No train/test split exists for dataset {dataset_id}")
    
    # Apply transformations based on learned_params
    # This would include:
    # - Applying bin boundaries learned from train
    # - Applying WOE values learned from train
    # - Applying any preprocessing transformations
    
    # For now, return test_df
    # Specific transformation logic would be added based on the params
    return test_df


def check_split_required(dataset_id: int) -> bool:
    """
    Check if train/test split is required before proceeding.
    
    Returns True if split exists, False if it needs to be created.
    """
    split_info = get_train_test_split_info(dataset_id)
    return split_info is not None


def clear_tts_cache(dataset_id: int = None):
    """
    Clear the train/test split cache.
    
    Parameters:
    -----------
    dataset_id : int, optional
        If provided, clears cache for this dataset only.
        If None, clears entire cache.
    """
    global _tts_cache
    if dataset_id is not None:
        if dataset_id in _tts_cache:
            del _tts_cache[dataset_id]
            print(f"[TTS CACHE] Cleared cache for dataset {dataset_id}")
    else:
        _tts_cache.clear()
        print(f"[TTS CACHE] Cleared entire cache")

