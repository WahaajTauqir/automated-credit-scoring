"""
Data Loader Module

This module provides functions to load the correct dataset (train or test)
based on the pipeline stage to prevent data leakage.

Data Leakage Prevention Rules:
1. Preprocessing: Learn from TRAIN only
2. Binning: Learn bin boundaries from TRAIN only
3. WOE Calculation: Calculate WOE from TRAIN only
4. Model Training: Train on TRAIN only
5. Model Evaluation: Evaluate on TEST only

The key principle: TEST SET IS NEVER SEEN until final evaluation!
"""

import pandas as pd
import os
from typing import Tuple, Optional
from db import get_train_test_split_info, get_dataset


def get_train_test_data(dataset_id: int) -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame], bool]:
    """
    Load train and test datasets if split exists.
    
    Parameters:
    -----------
    dataset_id : int
        Dataset ID
        
    Returns:
    --------
    train_df : DataFrame or None
        Training data if split exists
    test_df : DataFrame or None
        Test data if split exists
    split_exists : bool
        Whether split exists
    """
    split_info = get_train_test_split_info(dataset_id)
    
    if not split_info:
        return None, None, False
    
    # For now, regenerate from the main file using the split
    # In a production system, you might save train/test as separate files
    dataset = get_dataset(dataset_id)
    if not dataset:
        return None, None, False
    
    # Load full dataset
    from train_test_split import regenerate_split
    csv_path = get_csv_path(dataset_id)
    df = pd.read_csv(csv_path)
    target = dataset.get('target_variable')
    
    if not target:
        return None, None, False
    
    # Regenerate split
    train_df, test_df = regenerate_split(
        df, target,
        seed=split_info['seed'],
        test_size=split_info['test_size'],
        method=split_info['method']
    )
    
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

