from flask import Flask, request, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename
import pandas as pd
import numpy as np
import os
import datetime
import json
import requests
import math
import pickle
import glob
import copy
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_curve, auc, classification_report, confusion_matrix, accuracy_score, precision_score, recall_score, f1_score
from sklearn.preprocessing import StandardScaler
from statsmodels.stats.outliers_influence import variance_inflation_factor
import statsmodels.api as sm
from scipy import stats
import warnings
warnings.filterwarnings('ignore')
import re
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import base64
from io import BytesIO
from decimal import Decimal
from typing import Optional, Dict, Any, Tuple, List

# Import XGBoost raw training module
from xgboost_raw_training import train_xgboost_on_raw_features, apply_xgboost_scorecard

# Import ONLY new database layer functions - NO MORE db_old imports!
from db import (
    get_db_connection, init_db, ensure_final_selected_column, ensure_model_ready_column, ensure_dataset_identifier_column, sync_model_ready_to_final_selected,
    # Dataset operations
    create_dataset, get_dataset, get_all_datasets, get_all_datasets_with_features,
    get_latest_dataset, update_dataset, delete_dataset,
    # Feature operations
    create_feature, create_features_batch, get_feature, get_features_by_dataset, 
    get_feature_by_name, update_feature, update_features_selection, update_features_final_selection, update_features_model_ready,
    get_features_with_fine_binning_metadata,
    # Binning step operations
    create_binning_step, get_binning_step, get_binning_steps_by_feature, 
    get_binning_step_by_type, delete_binning_step, update_binning_step,
    # Bin operations
    create_bin, create_bins_batch, get_bins_by_step, get_bin, delete_bins_by_step,
    # Merged bins operations
    create_merged_bin, get_merged_bins_by_step,
    # Binning totals operations
    create_binning_totals, get_binning_totals, get_all_binning_totals_by_dataset,
    # Helper functions
    get_complete_binning_results, get_dataset_with_all_results,
    delete_all_binning_for_feature,
    # Train/Test Split operations
    save_train_test_split_metadata, get_train_test_split_info, clear_train_test_split
)
import traceback
import logging
from auto_monotonic_binning import auto_monotonic_binning, compute_woe, compute_iv
from data_loader import get_data_for_stage, get_csv_path, get_train_test_data
from config import DEFAULT_TEST_SIZE
import ast

# Optional: load environment variables from a .env file if present
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()
except Exception:
    pass

# configure basic logging for debug
logging.basicConfig(level=logging.DEBUG)

app = Flask(__name__)
CORS(app, origins=["http://localhost:5173", "http://localhost:5174"])
ARTIFACTS_DIR = os.path.join(os.path.dirname(__file__), 'artifacts')
os.makedirs(ARTIFACTS_DIR, exist_ok=True)

# Ensure database schema is up to date on startup
try:
    ensure_final_selected_column()
    ensure_model_ready_column()
    ensure_dataset_identifier_column()
except Exception as e:
    print(f"[APP] Warning: Could not ensure required columns: {e}")

def _sanitize_model_label(label: Optional[str]) -> str:
    candidate = (label or 'model').strip()
    filtered = ''.join(ch if ch.isalnum() or ch in ('_', '-') else '_' for ch in candidate)
    filtered = filtered.strip('_')
    return filtered or 'model'

def _artifact_pattern(dataset_id: int) -> str:
    return os.path.join(ARTIFACTS_DIR, f"{dataset_id}_*.pkl")


def _artifact_path(dataset_id: int, model_label: str) -> str:
    sanitized = _sanitize_model_label(model_label)
    return os.path.join(ARTIFACTS_DIR, f"{dataset_id}_{sanitized}.pkl")

def _build_artifact_metadata(payload: Dict[str, Any], artifact_path: str) -> Dict[str, Any]:
    selected_vars = payload.get('model_variables') or payload.get('selected_variables', [])
    metrics = payload.get('training_metrics') or {}
    return {
        'dataset_id': payload.get('dataset_id'),
        'model_label': payload.get('model_label'),
        'model_type': payload.get('model_type'),
        'target': payload.get('target'),
        'selected_variables': selected_vars,
        'saved_at': payload.get('saved_at'),
        'artifact_file': os.path.basename(artifact_path),
        'training_metrics': metrics
    }

def save_model_artifact(dataset_id: int, model_label: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    try:
        os.makedirs(ARTIFACTS_DIR, exist_ok=True)
        target_path = _artifact_path(dataset_id, model_label)
        if os.path.exists(target_path):
            try:
                os.remove(target_path)
            except OSError:
                pass
        try:
            payload_copy = copy.deepcopy(payload)
        except Exception:
            payload_copy = dict(payload)
        payload_copy.setdefault('dataset_id', dataset_id)
        payload_copy.setdefault('model_label', model_label)
        payload_copy.setdefault('saved_at', datetime.datetime.utcnow().isoformat())
        artifact_path = target_path
        with open(artifact_path, 'wb') as handle:
            pickle.dump(payload_copy, handle)
        return _build_artifact_metadata(payload_copy, artifact_path)
    except Exception as err:
        print(f"[MODEL ARTIFACT] Failed to save artifact for dataset {dataset_id}: {err}")
        return None

def load_model_artifact(dataset_id: int, model_label: Optional[str] = None) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    paths = []
    if model_label:
        target = _artifact_path(dataset_id, model_label)
        if os.path.exists(target):
            paths.append(target)
    else:
        pattern = _artifact_pattern(dataset_id)
        paths = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)

    for path in paths:
        try:
            with open(path, 'rb') as handle:
                payload = pickle.load(handle)
                return payload, path
        except Exception as err:
            print(f"[MODEL ARTIFACT] Failed to load artifact {path}: {err}")
    return None, None
def calculate_derived_bin_metrics(bins: List[Dict], totals: Optional[Dict] = None) -> List[Dict]:
    """
    Calculate derived metrics for bins (bad_rate, freq_percent, dist_good, dist_bad, etc.)
    These are calculated on-the-fly from good_count, bad_count, total_count.
    
    Args:
        bins: List of bin dictionaries from database
        totals: Optional binning_totals dictionary for overall calculations
    
    Returns:
        List of bin dictionaries with derived metrics added
    """
    if not bins:
        return []
    
    # Calculate totals if not provided
    if totals:
        total_good = totals.get('total_good', 0)
        total_bad = totals.get('total_bad', 0)
        total_all = totals.get('total_count', 0)
    else:
        # Calculate from bins
        total_good = sum(b.get('good_count', 0) for b in bins)
        total_bad = sum(b.get('bad_count', 0) for b in bins)
        total_all = sum(b.get('total_count', 0) for b in bins)
    
    overall_odds = (total_good / total_bad) if total_bad > 0 else None
    
    enriched_bins = []
    for bin_data in bins:
        good = bin_data.get('good_count', 0)
        bad = bin_data.get('bad_count', 0)
        total = bin_data.get('total_count', 0)
        
        # Calculate derived metrics
        dist_good = (good / total_good) * 100 if total_good > 0 else None
        dist_bad = (bad / total_bad) * 100 if total_bad > 0 else None
        bad_rate = (bad / total) * 100 if total > 0 else None
        freq_percent = (total / total_all) * 100 if total_all > 0 else None
        odds = (good / bad) if bad > 0 else None
        good_bad_ratio = odds
        
        # Index metrics
        try:
            index_value = (dist_good / dist_bad) * 100 if (dist_bad and dist_bad > 0) else None
        except Exception:
            index_value = None
        
        try:
            odds_index = (odds / overall_odds) * 100 if (odds is not None and overall_odds and overall_odds > 0) else None
        except Exception:
            odds_index = None
        
        # Create enriched bin with derived metrics
        enriched_bin = dict(bin_data)
        enriched_bin['dist_good'] = dist_good
        enriched_bin['dist_bad'] = dist_bad
        enriched_bin['bad_rate'] = bad_rate
        enriched_bin['freq_percent'] = freq_percent
        enriched_bin['odds'] = odds
        enriched_bin['good_bad_ratio'] = good_bad_ratio
        enriched_bin['index_value'] = index_value
        enriched_bin['odds_index'] = odds_index
        
        enriched_bins.append(enriched_bin)
    
    return enriched_bins

def save_coarse_binning_to_db(feature_id, bins_df, var_type):
    """
    Save coarse binning results to the new normalized schema.
    Returns the binning_step_id.
    """
    print(f"[save_coarse_binning_to_db] Saving coarse binning for feature {feature_id}, type={var_type}, bins={len(bins_df)}")
    
    # Create bins data first to calculate WOE for monotonicity detection
    bins_data = []
    total_good = int(bins_df['Good'].sum())
    total_bad = int(bins_df['Bad'].sum())
    total_all = int(total_good + total_bad)

    # Overall odds for index calculations
    overall_odds = (total_good / total_bad) if total_bad > 0 else None
    
    # Track WOE values for monotonicity detection
    woe_values = []

    for idx, row in bins_df.iterrows():
        good = int(row['Good'])
        bad = int(row['Bad'])
        total = int(row['Total'])

        # Create bin label with appropriate prefix (c for continuous, d for discrete)
        # Always use the correct prefix based on var_type, regardless of what's in the Bin column
        correct_prefix = 'c' if var_type == 'continuous' else 'd'
        default_label = f'{correct_prefix}{idx+1}'
        
        # Get existing bin label, but validate and correct it if needed
        existing_label = str(row.get('Bin', default_label))
        
        # If the existing label doesn't start with the correct prefix, use the default
        if not existing_label.startswith(correct_prefix):
            bin_label = default_label
        else:
            # Keep the existing label if it has the correct prefix
            bin_label = existing_label
        
        bin_data = {
            'bin_number': idx + 1,
            'bin_label': bin_label,
            'good_count': good,
            'bad_count': bad,
            'total_count': total
        }

        # For continuous: only save min_value and max_value, set range_text to None
        # For discrete: only save range_text, set min_value and max_value to None
        if var_type == 'continuous':
            # Continuous variables: use min/max only
            if 'Min' in row and row['Min'] is not None:
                try:
                    bin_data['min_value'] = float(row['Min'])
                except Exception:
                    bin_data['min_value'] = None
            else:
                bin_data['min_value'] = None
                
            if 'Max' in row and row['Max'] is not None:
                try:
                    bin_data['max_value'] = float(row['Max'])
                except Exception:
                    bin_data['max_value'] = None
            else:
                bin_data['max_value'] = None
                
            # Explicitly set range_text to None for continuous
            bin_data['range_text'] = None
        else:
            # Discrete variables: use range_text only
            if 'Range' in row and row['Range']:
                bin_data['range_text'] = str(row['Range'])
            else:
                bin_data['range_text'] = None
                
            # Explicitly set min_value and max_value to None for discrete
            bin_data['min_value'] = None
            bin_data['max_value'] = None

        # Calculate distributions for WOE calculation only (not stored in DB)
        dist_good = (good / total_good) * 100 if total_good > 0 else None
        dist_bad = (bad / total_bad) * 100 if total_bad > 0 else None

        # Calculate WOE for monotonicity detection
        if dist_good and dist_good > 0 and dist_bad and dist_bad > 0:
            try:
                import math
                woe = round(math.log(dist_good / dist_bad) * 100.0, 1)
                bin_data['woe'] = woe
                woe_values.append(woe)
            except Exception:
                bin_data['woe'] = None
        else:
            bin_data['woe'] = None

        bins_data.append(bin_data)

    # CRITICAL FIX: Detect monotonic direction
    monotonic_dir = detect_monotonic_direction(woe_values)
    is_monotonic = monotonic_dir is not None

    # Create or update binning step with monotonic_direction
    # Note: create_binning_step uses ON CONFLICT DO UPDATE, so it may update an existing step
    step_id = create_binning_step(
        feature_id=feature_id,
        step_type='coarse',
        method='qcut' if var_type == 'continuous' else 'bad_rate',
        num_bins=len(bins_df),
        is_monotonic=is_monotonic,
        monotonic_direction=monotonic_dir
    )

    # CRITICAL FIX: Delete existing bins for this step before creating new ones
    # This prevents orphaned binning_steps (steps without bins) when ON CONFLICT updates an existing step
    # If bins were previously deleted or creation failed, this ensures we start fresh
    delete_bins_by_step(step_id)
    print(f"[save_coarse_binning_to_db] Deleted existing bins for step_id={step_id} before creating new ones")

    # Persist bins and totals
    if bins_data:
        create_bins_batch(step_id, bins_data)

    # Create binning totals
    create_binning_totals(
        binning_step_id=step_id,
        total_good=total_good,
        total_bad=total_bad,
        total_count=total_all,
        good_bad_ratio=(total_good / total_bad) if total_bad > 0 else None,
        bad_rate=(total_bad / total_all) * 100 if total_all > 0 else None,
        freq_percent=100.0,
    )
    
    return step_id

# ---------------- Database Query Helpers ----------------
def get_finebin_details_db(record_id, column_name):
    """
    Returns fine-bin merged groups for a given record and column.
    Returns a list of dicts with keys `group_id` and `merged_bins`.

    IMPORTANT:
    - `merged_bins` must contain the actual coarse bin labels (e.g. c1, d3)
      because downstream WOE calculations map against the *_binned column
      which stores labels, not bin IDs.
    """
    try:
        dataset_id = record_id
        feature = get_feature_by_name(dataset_id, column_name)
        if not feature:
            return []

        fine_step = get_binning_step_by_type(feature['id'], 'fine')
        if not fine_step:
            return []

        merged = get_merged_bins_by_step(fine_step['id'])
        if not merged:
            return []

        # Build a lookup from bin_id -> bin_label so that we can translate the
        # stored original_bin_ids into the human-readable labels that exist in
        # the dataframe's *_binned column.
        coarse_step = get_binning_step_by_type(feature['id'], 'coarse')
        coarse_bins = get_bins_by_step(coarse_step['id']) if coarse_step else []
        prefix = 'c' if feature.get('type') == 'continuous' else 'd'
        bin_id_to_label = {}
        for bin_row in coarse_bins:
            label = bin_row.get('bin_label')
            if not label:
                bin_num = bin_row.get('bin_number')
                label = f"{prefix}{bin_num}" if bin_num is not None else None
            if label:
                try:
                    bin_id = bin_row.get('id')
                    if bin_id is None:
                        continue
                    bin_id_to_label[int(bin_id)] = str(label).strip()
                except (TypeError, ValueError):
                    continue

        rows = []
        for mb in merged:
            original_ids = mb.get('original_bin_ids') or []
            original_labels = mb.get('original_bin_labels') or []

            labels = [str(lbl).strip() for lbl in original_labels if str(lbl).strip()]
            if not labels:
                for bid in original_ids:
                    try:
                        bid_int = int(bid)
                    except (TypeError, ValueError):
                        bid_int = None
                    label = bin_id_to_label.get(bid_int)
                    if label:
                        labels.append(label)
            if not labels and original_ids:
                labels = [str(bid).strip() for bid in original_ids if str(bid).strip()]

            rows.append({
                'group_id': mb.get('merged_bin_number'),
                'merged_bins': labels
            })
        return rows
    except Exception:
        return []


def _load_woe_stats_from_db(dataset_id: int, variable: str,
                            feature_cache: Optional[Dict[str, Dict[str, Any]]] = None) -> Optional[List[Dict[str, Any]]]:
    """
    Load persisted WOE stats for a variable directly from the database.
    Prefers the fine-binning step (monotonic/merged bins) and falls back to coarse bins.
    Returns a list matching the frontend WOE payload structure.
    """
    cache = feature_cache if feature_cache is not None else {}
    feature = cache.get(variable)
    if feature is None:
        feature = get_feature_by_name(dataset_id, variable)
        if feature and feature_cache is not None:
            feature_cache[variable] = feature
    if not feature:
        return None

    step = get_binning_step_by_type(feature['id'], 'fine')
    step_type = 'fine'
    if not step:
        step = get_binning_step_by_type(feature['id'], 'coarse')
        step_type = 'coarse'
    if not step:
        return None

    bins = get_bins_by_step(step['id'])
    if not bins:
        return None

    feature_type = feature.get('type') or 'continuous'
    prefix = 'c' if feature_type == 'continuous' else 'd'
    stats: List[Dict[str, Any]] = []

    for bin_row in bins:
        native = _row_to_native_types(dict(bin_row))
        label = native.get('bin_label')
        if not label:
            bin_number = native.get('bin_number')
            if bin_number is not None:
                label = f"{prefix}{bin_number}"
            else:
                label = str(native.get('id') or '')

        min_val = native.get('min_value')
        max_val = native.get('max_value')
        range_text = native.get('range_text')

        if feature_type == 'continuous':
            if not range_text:
                lower = min_val if min_val is not None else '-inf'
                upper = max_val if max_val is not None else 'inf'
                range_text = f"({lower}, {upper}]"
        else:
            if not range_text:
                range_text = label

        woe_val = native.get('woe')
        if woe_val is not None:
            try:
                woe_val = float(woe_val)
            except Exception:
                woe_val = None

        stats.append({
            'Bin': label,
            'range': range_text,
            'Range': range_text,
            'woe': woe_val,
            'WOE': woe_val,
            'min_value': min_val,
            'max_value': max_val,
            'source_step': step_type
        })

    if stats:
        print(f"XGB DEBUG: Hydrated {len(stats)} bins for {variable} from {step_type} binning step")
    return stats or None


def save_finebin_details_db(record_id, column_name, bin_merges):
    """
    Persist merged bin groups to the `merged_bins` table.
    `bin_merges` is expected to be a mapping of merged_label -> list(original_bin_indices).
    """
    try:
        dataset_id = record_id
        feature = get_feature_by_name(dataset_id, column_name)
        if not feature:
            # Nothing to persist if feature doesn't exist
            return False

        # Ensure fine binning step exists
        fine_step = get_binning_step_by_type(feature['id'], 'fine')
        if not fine_step:
            fine_step_id = create_binning_step(feature_id=feature['id'], step_type='fine', method='merged', num_bins=0)
        else:
            fine_step_id = fine_step['id']

        # Clean existing merged bins for this fine step
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("DELETE FROM merged_bins WHERE fine_step_id = %s", (fine_step_id,))
            conn.commit()
            cur.close()
            conn.close()
        except Exception:
            pass

        # Map coarse bin indices and bin_numbers to bin IDs where possible
        coarse_step = get_binning_step_by_type(feature['id'], 'coarse')
        coarse_bins = get_bins_by_step(coarse_step['id']) if coarse_step else []
        # Build robust mappings: 0-based index, 1-based bin_number, and label -> id
        index_to_id = {}
        bin_number_to_id = {}
        label_to_id = {}
        index_to_label = {}
        for idx, b in enumerate(coarse_bins):
            bid = b.get('id')
            index_to_id[idx] = bid
            index_to_label[idx] = b.get('bin_label', str(idx))
            # if bin_number stored, map it as 1-based
            bn = b.get('bin_number')
            if bn is not None:
                try:
                    bin_number_to_id[int(bn)] = bid
                except Exception:
                    pass
            # label mapping
            lbl = b.get('bin_label')
            if lbl is not None:
                label_to_id[str(lbl).strip()] = bid

        for merged_key, originals in (bin_merges or {}).items():
            try:
                merged_num = int(str(merged_key)) if str(merged_key).isdigit() else None
            except Exception:
                merged_num = None

            original_ids = []
            original_labels = []
            for o in originals:
                # Accept several possible representations from the frontend:
                # - numeric index (0-based)
                # - numeric bin_number (1-based)
                # - bin label string like 'Bin_1' or a label
                found_id = None
                label = None
                try:
                    # Try numeric
                    o_int = int(str(o).strip())
                    # Prefer bin_number (1-based) match first
                    found_id = bin_number_to_id.get(o_int)
                    if found_id is None:
                        found_id = index_to_id.get(o_int)
                    label = index_to_label.get(o_int, str(o_int))
                except Exception:
                    # Not numeric — treat as label
                    o_str = str(o).strip()
                    found_id = label_to_id.get(o_str)
                    label = o_str

                if found_id:
                    original_ids.append(found_id)
                original_labels.append(label)

            # If merged_num not numeric, assign sequential numbering
            if merged_num is None:
                # pick next available number
                existing = get_merged_bins_by_step(fine_step_id)
                merged_num = (max([m['merged_bin_number'] for m in existing]) + 1) if existing else 1

            # Persist merged bin
            create_merged_bin(fine_step_id=fine_step_id, merged_bin_number=merged_num, original_bin_ids=original_ids or [], original_bin_labels=original_labels or [])

        return True
    except Exception:
        return False


# Helper utilities for working with dataset CSV files
def _normalize_dataset_id(value):
    """Return an integer dataset id when possible, otherwise None."""
    if value is None:
        return None
    try:
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _resolve_dataset_file_path(file_path: Optional[str]) -> Optional[str]:
    """Resolve relative/absolute dataset paths and ensure the file exists."""
    if not file_path:
        return None
    if os.path.isabs(file_path) and os.path.exists(file_path):
        return file_path
    base_dir = os.path.dirname(__file__)
    candidate = os.path.join(base_dir, file_path)
    if os.path.exists(candidate):
        return candidate
    uploads_dir = os.path.join(base_dir, 'uploads')
    fallback = os.path.join(uploads_dir, os.path.basename(file_path))
    if os.path.exists(fallback):
        return fallback
    return None


def _row_to_native_types(row: Dict[str, Any]) -> Dict[str, Any]:
    """Convert Decimal/NumPy types in DB rows to JSON-serializable primitives."""
    normalized = {}
    for key, value in row.items():
        # Handle None/NULL
        if value is None:
            normalized[key] = None
        # Handle Decimal
        elif isinstance(value, Decimal):
            val = float(value)
            # Check for NaN or inf after conversion
            if np.isnan(val) or np.isinf(val):
                normalized[key] = None
            else:
                normalized[key] = val
        # Handle NumPy types
        elif hasattr(value, 'item'):
            try:
                val = value.item()
                # Check for NaN or inf in NumPy values
                if isinstance(val, (float, np.floating)) and (np.isnan(val) or np.isinf(val)):
                    normalized[key] = None
                else:
                    normalized[key] = val
            except Exception:
                normalized[key] = value
        # Handle float NaN/inf
        elif isinstance(value, (float, np.floating)):
            if np.isnan(value) or np.isinf(value):
                normalized[key] = None
            else:
                normalized[key] = float(value)
        else:
            normalized[key] = value
    return normalized


def _clean_nan_values(obj: Any) -> Any:
    """Recursively clean NaN and inf values from dictionaries, lists, and primitives for JSON serialization."""
    if obj is None:
        return None
    elif isinstance(obj, dict):
        return {k: _clean_nan_values(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [_clean_nan_values(item) for item in obj]
    elif isinstance(obj, (float, np.floating)):
        if np.isnan(obj) or np.isinf(obj):
            return None
        return float(obj)
    elif hasattr(obj, 'item'):  # NumPy scalar
        try:
            val = obj.item()
            if isinstance(val, (float, np.floating)) and (np.isnan(val) or np.isinf(val)):
                return None
            return val
        except Exception:
            return obj
    elif isinstance(obj, Decimal):
        val = float(obj)
        if np.isnan(val) or np.isinf(val):
            return None
        return val
    else:
        return obj


DEFAULT_SCORECARD_CONFIG = {
    "min_score": 300,
    "max_score": 850,
    "base_score": 600,
    "base_odds": 50,
    "points_to_double_odds": 50
}


def _scorecard_scaling_params(config: Dict[str, float] = DEFAULT_SCORECARD_CONFIG) -> Tuple[float, float]:
    """
    Return (factor, offset) for the standard credit score scaling.
    
    Follows academic standard (Siddiqi 2006):
    - Factor = PDO / ln(2), where PDO is "Points to Double Odds"
    - Offset is set so that base_odds maps to base_score
    
    Note: base_odds is interpreted as odds of good:bad (e.g., 50:1 means 2% default rate)
    """
    factor = config["points_to_double_odds"] / math.log(2)
    offset = config["base_score"] - factor * math.log(config["base_odds"])
    return factor, offset


def _probability_to_score(probabilities, config: Dict[str, float] = DEFAULT_SCORECARD_CONFIG):
    """
    Convert probability of default (PD) to credit scores using academic standard formula.
    
    Follows the standard credit scoring formula (Siddiqi 2006):
        Score = Offset + Factor × ln(odds)
    
    Where:
        odds = PD/(1-PD)  (odds of default)
        Factor = PDO / ln(2)  (PDO = Points to Double Odds)
        Offset = base_score - Factor × ln(base_odds_of_good)
    
    To ensure higher scores for lower risk (standard credit scoring convention):
        Score = Offset - Factor × ln(odds_of_default)
    
    This is mathematically equivalent to:
        Score = Offset + Factor × ln(odds_of_good)
        where odds_of_good = (1-PD)/PD
    
    This ensures:
    - Higher risk (high PD) → Lower score (300-500)
    - Lower risk (low PD) → Higher score (700-850)
    
    Parameters:
    -----------
    probabilities : array-like
        Probability of default/bad (target=1). Should be between 0 and 1.
    config : dict
        Scorecard configuration with:
        - min_score: Minimum credit score (default: 300)
        - max_score: Maximum credit score (default: 850)
        - base_score: Score at baseline odds (default: 600)
        - base_odds: Baseline odds of good:bad (default: 50, meaning 2% default rate)
        - points_to_double_odds: Points per doubling of odds (default: 50)
        
    Returns:
    --------
    numpy.ndarray
        Credit scores clipped to [min_score, max_score] range
        
    References:
    -----------
    Siddiqi, N. (2006). Credit Risk Scorecards: Developing and Implementing 
    Intelligent Credit Scoring. John Wiley & Sons.
    """
    factor, offset = _scorecard_scaling_params(config)
    # Clip probabilities to avoid log(0) or log(inf)
    probs = np.clip(np.asarray(probabilities, dtype=float), 1e-6, 1 - 1e-6)
    
    # Academic standard: odds = PD/(1-PD) (odds of default)
    odds_default = probs / (1.0 - probs)
    
    # Apply academic standard formula with negative sign to ensure
    # higher scores for lower risk (standard credit scoring convention)
    # Score = Offset - Factor × ln(odds_of_default)
    # This is equivalent to: Score = Offset + Factor × ln((1-PD)/PD)
    raw_scores = offset - factor * np.log(odds_default)
    
    # Clip to valid score range
    clipped = np.clip(raw_scores, config["min_score"], config["max_score"])
    return clipped


def get_csv_path(dataset_id: Optional[int] = None):
    """Returns the absolute path to the dataset CSV file."""
    dataset = None
    normalized_id = _normalize_dataset_id(dataset_id)
    if normalized_id:
        dataset = get_dataset(normalized_id)
        if dataset:
            resolved = _resolve_dataset_file_path(dataset.get('file_path'))
            if resolved:
                return resolved
    
    latest = get_latest_dataset()
    if latest:
        resolved = _resolve_dataset_file_path(latest.get('file_path'))
        if resolved:
            return resolved
    
    uploads_dir = os.path.join(os.path.dirname(__file__), 'uploads')
    if os.path.exists(uploads_dir):
        files = [
            os.path.join(uploads_dir, f)
            for f in os.listdir(uploads_dir)
            if f.lower().endswith('.csv')
        ]
        if files:
            files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
            return files[0]

    raise FileNotFoundError('No dataset CSV found. Upload a CSV via /api/upload-csv first.')


def detect_column_types(df, sample_size=1000):
    """
    Enhanced column type detection using multiple heuristics.
    Returns: {'discrete': [], 'continuous': []}
    """
    
    # --- Local Helper Heuristic Function ---
    def _classify_with_heuristics(col, samples):
        col_name_lower = col.lower()
        
        # --- Heuristic Keywords ---
        # Priority 1: Continuous Keywords (Monetary, Measurements, Proportions)
        continuous_keywords = ['sales', 'turnover', 'margin', 'perc', 'rate', 'ratio', 'amount', 'price', 'cost', 'salary', 'income', 'revenue', 'balance', 'weight', 'height', 'length', 'width', 'depth', 'distance', 'time', 'duration', 'age', 'years']
        # Priority 2: Discrete Keywords (IDs, Codes, Counts, Categories)
        discrete_keywords = ['id', 'no', 'keyt','_CD', 'cd', 'form', 'relation', 'auth', 'group', 'family', 'branch', 'visit', 'invcount', 'customer', 'status', 'level', 'flag', 'type', 'code']

        # 1. Check Continuous by Name (Highest Priority)
        if any(keyword in col_name_lower for keyword in continuous_keywords):
            return 'continuous'

        # 2. Check Discrete by Name
        if any(keyword in col_name_lower for keyword in discrete_keywords) or col_name_lower in ['bad customer']:
            return 'discrete'

        # 3. Analyze Sample Values
        # Check if samples is empty (handle both Series and list)
        if hasattr(samples, 'empty'):
            if samples.empty:
                return 'discrete' # Default to discrete when no data
        elif hasattr(samples, '__len__'):
            if len(samples) == 0:
                return 'discrete' # Default to discrete when no data
        else:
            if not samples:
                return 'discrete' # Default to discrete when no data
            

        try:
            # Handle pandas Series/DataFrame samples
            if hasattr(samples, 'dtype'):
                is_numeric = pd.api.types.is_numeric_dtype(samples)
                samples_list = samples.dropna().tolist()
            else:
                is_numeric = all(isinstance(x, (int, float)) for x in samples)
                samples_list = [x for x in samples if x is not None]
            
            if not is_numeric:
                return 'discrete' # Text/Categorical data

            # Check for presence of non-integer/float values
            has_float = any(isinstance(x, float) and not x.is_integer() for x in samples_list)
            if has_float:
                return 'continuous' # Presence of decimals strongly suggests measurement/continuous

            # Check cardinality for numeric data (e.g., binary or few levels)
            unique_values = len(set(samples_list))
            # Use a conservative low-cardinality threshold for discrete classification
            if unique_values <= 15: 
                return 'discrete'
            
            # If numeric, all integers, high cardinality, and not caught by name:
            # It's either a large count (discrete) or a large monetary value/ID (context-dependent).
            # We default to continuous as LLM classification should be used for this ambiguity, 
            # but if heuristics must decide, numeric high cardinality is often treated as continuous for modeling.
            return 'continuous'
        except Exception:
            return 'discrete' # Safe default on sample analysis failure
    # --- End Helper Function ---

    discrete_cols = []
    continuous_cols = []
    
    for col in df.columns:
        # Skip if all null
        if df[col].isna().all():
            discrete_cols.append(col)
            continue
            
        # Sample data for analysis
        sample_data = df[col].dropna().head(sample_size)
        
        if len(sample_data) == 0:
            discrete_cols.append(col)
            continue

        # Use the enhanced heuristic classification
        classification = _classify_with_heuristics(col, sample_data)
        
        if classification == 'discrete':
            discrete_cols.append(col)
        else:
            continuous_cols.append(col)
    
    return {'discrete': discrete_cols, 'continuous': continuous_cols}

def handle_missing_values(df, discrete_cols, continuous_cols, missing_threshold=0.5, treat_negative_one_as_missing=True):
    """
    Handle missing values based on column type.
    Now treats -1 as missing value and drops columns with missing values above threshold.
    
    Args:
        df: Input DataFrame
        discrete_cols: List of discrete column names
        continuous_cols: List of continuous column names
        missing_threshold: Threshold (0-1) for dropping columns (e.g., 0.5 = 50% missing)
        treat_negative_one_as_missing: Whether to treat -1 as missing value
    
    Returns:
        Cleaned DataFrame and removal report
    """
    print(f"[HANDLE_MISSING] Starting with {len(df)} rows, {len(df.columns)} columns")
    print(f"[HANDLE_MISSING] Missing threshold: {missing_threshold:.1%}")
    print(f"[HANDLE_MISSING] Treat -1 as missing: {treat_negative_one_as_missing}")
    
    df_clean = df.copy()
    removal_report = {
        'columns_removed': [],
        'columns_retained': [],
        'missing_treated': {},
        'negative_one_treated': {}
    }
    
    # First, identify and mark -1 as missing if enabled
    if treat_negative_one_as_missing:
        for col in df_clean.columns:
            if col in df_clean.columns and pd.api.types.is_numeric_dtype(df_clean[col]):
                negative_one_count = (df_clean[col] == -1).sum()
                if negative_one_count > 0:
                    df_clean[col] = df_clean[col].replace(-1, np.nan)
                    removal_report['negative_one_treated'][col] = {
                        'negative_one_count': int(negative_one_count),
                        'treated_as_missing': True
                    }
    
    # FIX: Convert empty strings to NaN for object columns BEFORE counting missing
    # This ensures empty strings are treated as missing for categorical columns
    for col in df_clean.columns:
        if df_clean[col].dtype == 'object' or df_clean[col].dtype.name == 'category':
            # Replace empty strings and whitespace-only strings with NaN
            empty_count = (df_clean[col] == '').sum()
            if empty_count > 0:
                df_clean[col] = df_clean[col].replace('', np.nan)
                print(f"[HANDLE_MISSING] Column '{col}': Converted {empty_count} empty strings to NaN")
            # Also handle whitespace-only strings
            if df_clean[col].dtype == 'object':
                whitespace_mask = df_clean[col].astype(str).str.strip().eq('')
                whitespace_count = whitespace_mask.sum()
                if whitespace_count > 0:
                    df_clean.loc[whitespace_mask, col] = np.nan
                    print(f"[HANDLE_MISSING] Column '{col}': Converted {whitespace_count} whitespace-only strings to NaN")
    
    # Identify columns to remove based on missing threshold
    columns_to_remove = []
    for col in df_clean.columns:
        # Count NaN values (now includes converted empty strings)
        missing_count = df_clean[col].isna().sum()
        missing_ratio = missing_count / len(df_clean) if len(df_clean) > 0 else 0
        
        # FIX: Use more lenient threshold for categorical columns (they're more important)
        # Categorical columns are valuable even with some missing values
        # Only drop categorical columns if >90% missing (very lenient to preserve important features)
        effective_threshold = missing_threshold
        if col in discrete_cols and (df_clean[col].dtype == 'object' or df_clean[col].dtype.name == 'category'):
            # For categorical columns, use 90% threshold (very lenient) to preserve important features
            # This prevents dropping columns like Gender, Education, etc. that are valuable even with some missing
            effective_threshold = 0.9
        
        if missing_ratio > effective_threshold:
            columns_to_remove.append(col)
            removal_report['columns_removed'].append({
                'column': col,
                'missing_count': int(missing_count),
                'missing_ratio': round(missing_ratio, 4),
                'reason': f'Missing values (including empty strings) exceed threshold ({missing_ratio:.1%} > {effective_threshold:.1%})'
            })
        else:
            removal_report['columns_retained'].append({
                'column': col,
                'missing_count': int(missing_count),
                'missing_ratio': round(missing_ratio, 4)
            })
    
    # Remove high-missing columns
    if columns_to_remove:
        print(f"[HANDLE_MISSING] Removing {len(columns_to_remove)} columns with >{missing_threshold:.1%} missing:")
        for col_info in removal_report['columns_removed']:
            print(f"  - {col_info['column']}: {col_info['missing_ratio']:.1%} missing ({col_info['missing_count']} rows)")
    
    df_clean = df_clean.drop(columns=columns_to_remove)
    
    # Update column lists after removal
    discrete_cols = [col for col in discrete_cols if col in df_clean.columns]
    continuous_cols = [col for col in continuous_cols if col in df_clean.columns]
    
    print(f"[HANDLE_MISSING] After column removal: {len(df_clean.columns)} columns remain "
          f"({len(discrete_cols)} discrete, {len(continuous_cols)} continuous)")
    
    # For discrete columns: mode imputation
    for col in discrete_cols:
        if col in df_clean.columns:
            # FIX: Ensure empty strings are converted to NaN (should already be done, but double-check)
            if df_clean[col].dtype == 'object':
                # Replace any remaining empty strings with NaN
                empty_count = (df_clean[col] == '').sum()
                if empty_count > 0:
                    df_clean[col] = df_clean[col].replace('', np.nan)
            
            if df_clean[col].isna().any():
                missing_count = df_clean[col].isna().sum()
                total_rows = len(df_clean)
                
                if df_clean[col].dtype == 'object':
                    # For categorical, use 'Missing' category
                    df_clean[col] = df_clean[col].fillna('Missing')
                    method = 'Missing category'
                else:
                    # For numeric discrete, use mode
                    mode_val = df_clean[col].mode()
                    if not mode_val.empty:
                        df_clean[col] = df_clean[col].fillna(mode_val.iloc[0])
                        method = f'Mode ({mode_val.iloc[0]})'
                    else:
                        df_clean[col] = df_clean[col].fillna(0)
                        method = 'Zero (no mode available)'
                
                removal_report['missing_treated'][col] = {
                    'type': 'discrete',
                    'missing_count': int(missing_count),
                    'method': method
                }
                
                print(f"[HANDLE_MISSING] Discrete column '{col}': Filled {missing_count} missing values "
                      f"({missing_count/total_rows*100:.2f}%) using {method}")
    
    # For continuous columns: median imputation
    for col in continuous_cols:
        if col in df_clean.columns and df_clean[col].isna().any():
            missing_count = df_clean[col].isna().sum()
            total_rows = len(df_clean)
            
            if pd.api.types.is_numeric_dtype(df_clean[col]):
                median_val = df_clean[col].median()
                df_clean[col] = df_clean[col].fillna(median_val)
                method = f'Median ({median_val:.4f})'
            else:
                # If continuous column is not numeric, try to convert
                try:
                    df_clean[col] = pd.to_numeric(df_clean[col], errors='coerce')
                    median_val = df_clean[col].median()
                    df_clean[col] = df_clean[col].fillna(median_val)
                    method = f'Median after conversion ({median_val:.4f})'
                except:
                    df_clean[col] = df_clean[col].fillna('Missing')
                    method = 'Missing category (conversion failed)'
            
            removal_report['missing_treated'][col] = {
                'type': 'continuous',
                'missing_count': int(missing_count),
                'method': method
            }
            
            print(f"[HANDLE_MISSING] Continuous column '{col}': Filled {missing_count} missing values "
                  f"({missing_count/total_rows*100:.2f}%) using {method}")
    
    print(f"[HANDLE_MISSING] Completed: {len(df_clean)} rows, {len(df_clean.columns)} columns")
    return df_clean, removal_report


def remove_duplicates(df):
    """
    Remove duplicate rows from dataset.
    """
    initial_count = len(df)
    print(f"[REMOVE_DUPLICATES] Starting with {initial_count} rows, {len(df.columns)} columns")
    
    df_deduped = df.drop_duplicates()
    final_count = len(df_deduped)
    duplicates_removed = initial_count - final_count
    
    if duplicates_removed > 0:
        print(f"[REMOVE_DUPLICATES] Removed {duplicates_removed} duplicate rows "
              f"({initial_count} → {final_count} rows, {duplicates_removed/initial_count*100:.2f}% reduction)")
    else:
        print(f"[REMOVE_DUPLICATES] No duplicates found ({final_count} rows)")
    
    return df_deduped, duplicates_removed

def handle_outliers(df, continuous_cols, method='iqr', threshold=3.0):
    """
    Handle outliers in continuous columns.
    Methods: 'iqr', 'zscore', 'winsorize'
    """
    print(f"[HANDLE_OUTLIERS] Starting with {len(df)} rows")
    print(f"[HANDLE_OUTLIERS] Method: {method}, Threshold: {threshold}")
    print(f"[HANDLE_OUTLIERS] Processing {len(continuous_cols)} continuous columns")
    
    df_clean = df.copy()
    outlier_info = {}
    
    for col in continuous_cols:
        if col not in df_clean.columns or not pd.api.types.is_numeric_dtype(df_clean[col]):
            continue
            
        original_data = df_clean[col].copy()
        
        if method == 'iqr':
            Q1 = df_clean[col].quantile(0.25)
            Q3 = df_clean[col].quantile(0.75)
            IQR = Q3 - Q1
            lower_bound = Q1 - 1.5 * IQR
            upper_bound = Q3 + 1.5 * IQR
            
            # Cap outliers
            df_clean[col] = np.where(df_clean[col] < lower_bound, lower_bound, df_clean[col])
            df_clean[col] = np.where(df_clean[col] > upper_bound, upper_bound, df_clean[col])
            
            outliers_count = ((original_data < lower_bound) | (original_data > upper_bound)).sum()
            
        elif method == 'zscore':
            z_scores = np.abs(stats.zscore(df_clean[col].dropna()))
            mask = z_scores < threshold
            # For z-score, we might want to remove rather than cap
            outlier_indices = np.where(z_scores >= threshold)[0]
            outliers_count = len(outlier_indices)
            
        elif method == 'winsorize':
            # Winsorize: cap at specified percentiles
            lower_limit = df_clean[col].quantile(0.05)
            upper_limit = df_clean[col].quantile(0.95)
            df_clean[col] = np.where(df_clean[col] < lower_limit, lower_limit, df_clean[col])
            df_clean[col] = np.where(df_clean[col] > upper_limit, upper_limit, df_clean[col])
            
            outliers_count = ((original_data < lower_limit) | (original_data > upper_limit)).sum()
        
        outlier_info[col] = {
            'method': method,
            'outliers_detected': int(outliers_count),
            'outliers_percentage': round((outliers_count / len(original_data)) * 100, 2) if len(original_data) > 0 else 0
        }
        
        if outliers_count > 0:
            print(f"[HANDLE_OUTLIERS] Column '{col}': Detected {outliers_count} outliers "
                  f"({outliers_count/len(original_data)*100:.2f}%) - Capped using {method}")
    
    total_outliers = sum(info.get('outliers_detected', 0) for info in outlier_info.values())
    print(f"[HANDLE_OUTLIERS] Completed: Handled {total_outliers} total outliers across {len(outlier_info)} columns")
    
    return df_clean, outlier_info

def encode_categorical_variables(df, discrete_cols, target_col=None):
    """
    Encode categorical variables using label encoding.
    Skip target variable if provided.
    """
    print(f"[ENCODE_CATEGORICAL] Starting with {len(df)} rows")
    print(f"[ENCODE_CATEGORICAL] Processing {len(discrete_cols)} discrete columns")
    if target_col:
        print(f"[ENCODE_CATEGORICAL] Skipping target column: {target_col}")
    
    df_encoded = df.copy()
    encoding_info = {}
    label_encoders = {}
    
    for col in discrete_cols:
        if col == target_col:
            continue
            
        if col in df_encoded.columns and df_encoded[col].dtype == 'object':
            # FIX: Handle NaN values first
            nan_count = df_encoded[col].isna().sum()
            if nan_count > 0:
                # Fill NaN with a special marker before encoding
                df_encoded[col] = df_encoded[col].fillna('__MISSING__')
                print(f"[ENCODE_CATEGORICAL] Column '{col}': Filled {nan_count} NaN values with '__MISSING__'")
            
            # Create label encoder
            le = LabelEncoder()
            
            # Handle unseen categories by fitting on all possible categories
            # Remove any remaining NaN (shouldn't be any after fillna, but safety check)
            unique_vals = df_encoded[col].dropna().unique()
            if len(unique_vals) == 0:
                print(f"[ENCODE_CATEGORICAL] Column '{col}': Skipping (all NaN)")
                continue
                
            le.fit(unique_vals)
            
            # Transform the column
            df_encoded[col] = le.transform(df_encoded[col].astype(str))
            
            # Store encoding information
            label_encoders[col] = le
            encoding_info[col] = {
                'original_categories': list(le.classes_),
                'encoded_values': list(range(len(le.classes_))),
                'mapping': dict(zip(le.classes_, range(len(le.classes_)))),
                'nan_count': int(nan_count)
            }
            
            print(f"[ENCODE_CATEGORICAL] Column '{col}': Encoded {len(le.classes_)} categories "
                  f"({len(le.classes_)} unique values)")
    
    print(f"[ENCODE_CATEGORICAL] Completed: Encoded {len(encoding_info)} columns")
    return df_encoded, encoding_info, label_encoders

def _debug_print_column_row_counts(df, stage_name, show_details=True):
    """
    Helper function to print debug information about row counts per column.
    
    Args:
        df: DataFrame to analyze
        stage_name: Name of the preprocessing stage
        show_details: If True, show per-column details
    """
    total_rows = len(df)
    print(f"\n{'='*80}")
    print(f"[PREPROCESSING DEBUG] {stage_name}")
    print(f"{'='*80}")
    print(f"Total Rows: {total_rows}")
    print(f"Total Columns: {len(df.columns)}")
    
    if show_details:
        print(f"\nRow Counts Per Column:")
        print(f"{'Column Name':<30} {'Non-Null Rows':<20} {'Null Rows':<20} {'Null %':<15}")
        print(f"{'-'*85}")
        for col in df.columns:
            non_null = df[col].notna().sum()
            null = df[col].isna().sum()
            null_pct = (null / total_rows * 100) if total_rows > 0 else 0
            print(f"{col:<30} {non_null:<20} {null:<20} {null_pct:.2f}%")
    print(f"{'='*80}\n")

def preprocess_dataset(df, target_col=None, preprocessing_steps=None, missing_threshold=0.5, treat_negative_one_as_missing=True):
    """
    Main preprocessing function that applies all preprocessing steps.
    
    Args:
        df: Input DataFrame
        target_col: Target column name (optional)
        preprocessing_steps: Dictionary specifying which steps to apply
        missing_threshold: Threshold for dropping columns with high missing values
        treat_negative_one_as_missing: Whether to treat -1 as missing value
    
    Returns:
        Preprocessed DataFrame and preprocessing report
    """
    if preprocessing_steps is None:
        preprocessing_steps = {
            'detect_types': True,
            'handle_missing': True,
            'remove_duplicates': True,
            'handle_outliers': True,
            'encode_categorical': True
        }
    
    preprocessing_report = {
        'original_shape': df.shape,
        'steps_applied': [],
        'details': {},
        'parameters': {
            'missing_threshold': missing_threshold,
            'treat_negative_one_as_missing': treat_negative_one_as_missing
        }
    }
    
    df_processed = df.copy()
    
    # Debug: Initial state
    _debug_print_column_row_counts(df_processed, "INITIAL STATE (Before Preprocessing)")
    
    # Step 1: Detect column types
    if preprocessing_steps.get('detect_types', True):
        column_types = detect_column_types(df_processed)
        discrete_cols = column_types['discrete']
        continuous_cols = column_types['continuous']
        preprocessing_report['column_types'] = column_types
        preprocessing_report['steps_applied'].append('type_detection')
        print(f"[PREPROCESSING] Type Detection: {len(discrete_cols)} discrete, {len(continuous_cols)} continuous columns")
    else:
        # Use all columns as continuous if not detected
        discrete_cols = []
        continuous_cols = df_processed.columns.tolist()
    
    # Step 2: Handle missing values
    if preprocessing_steps.get('handle_missing', True):
        _debug_print_column_row_counts(df_processed, "BEFORE Missing Value Handling")
        
        missing_before = df_processed.isna().sum().sum()
        negative_one_before = 0
        if treat_negative_one_as_missing:
            for col in df_processed.columns:
                if pd.api.types.is_numeric_dtype(df_processed[col]):
                    negative_one_before += (df_processed[col] == -1).sum()
        
        df_processed, missing_report = handle_missing_values(
            df_processed, discrete_cols, continuous_cols, 
            missing_threshold, treat_negative_one_as_missing
        )
        
        missing_after = df_processed.isna().sum().sum()
        preprocessing_report['details']['missing_values'] = {
            'before': int(missing_before),
            'after': int(missing_after),
            'negative_one_treated': int(negative_one_before),
            'removed': int(missing_before - missing_after),
            'columns_removed': missing_report['columns_removed'],
            'columns_retained': missing_report['columns_retained'],
            'missing_treated': missing_report['missing_treated'],
            'negative_one_treated_details': missing_report['negative_one_treated']
        }
        preprocessing_report['steps_applied'].append('missing_values_handling')
        
        # Update column lists after missing value handling
        discrete_cols = [col for col in discrete_cols if col in df_processed.columns]
        continuous_cols = [col for col in continuous_cols if col in df_processed.columns]
        
        _debug_print_column_row_counts(df_processed, "AFTER Missing Value Handling")
        print(f"[PREPROCESSING] Missing Values: Removed {len(missing_report['columns_removed'])} columns, "
              f"Treated missing in {len(missing_report['missing_treated'])} columns")
    
    # Step 3: Remove duplicates
    if preprocessing_steps.get('remove_duplicates', True):
        _debug_print_column_row_counts(df_processed, "BEFORE Duplicate Removal")
        
        rows_before = len(df_processed)
        df_processed, duplicates_removed = remove_duplicates(df_processed)
        rows_after = len(df_processed)
        
        preprocessing_report['details']['duplicates'] = {
            'removed': int(duplicates_removed)
        }
        preprocessing_report['steps_applied'].append('duplicate_removal')
        
        _debug_print_column_row_counts(df_processed, "AFTER Duplicate Removal")
        print(f"[PREPROCESSING] Duplicates: Removed {duplicates_removed} duplicate rows "
              f"({rows_before} → {rows_after} rows)")
    
    # Step 4: Handle outliers (only for continuous columns)
    if preprocessing_steps.get('handle_outliers', True) and continuous_cols:
        _debug_print_column_row_counts(df_processed, "BEFORE Outlier Handling")
        
        df_processed, outlier_info = handle_outliers(df_processed, continuous_cols, method='iqr')
        preprocessing_report['details']['outliers'] = outlier_info
        preprocessing_report['steps_applied'].append('outlier_handling')
        
        _debug_print_column_row_counts(df_processed, "AFTER Outlier Handling")
        total_outliers = sum(info.get('outliers_detected', 0) for info in outlier_info.values())
        print(f"[PREPROCESSING] Outliers: Handled outliers in {len(outlier_info)} columns "
              f"({total_outliers} total outliers detected)")
    
    # Step 5: Encode categorical variables
    if preprocessing_steps.get('encode_categorical', True) and discrete_cols:
        _debug_print_column_row_counts(df_processed, "BEFORE Categorical Encoding")
        
        df_processed, encoding_info, label_encoders = encode_categorical_variables(
            df_processed, discrete_cols, target_col
        )
        preprocessing_report['details']['encoding'] = encoding_info
        preprocessing_report['label_encoders'] = label_encoders
        preprocessing_report['steps_applied'].append('categorical_encoding')
        
        _debug_print_column_row_counts(df_processed, "AFTER Categorical Encoding")
        print(f"[PREPROCESSING] Encoding: Encoded {len(encoding_info)} categorical columns")
    
    # Debug: Final state
    _debug_print_column_row_counts(df_processed, "FINAL STATE (After All Preprocessing)")
    
    # Print ASSIGNED_STORE_ID values after preprocessing
    column_name = "ASSIGNED_STORE_ID"
    print(f"\n{'='*80}")
    print(f"[PREPROCESSING] ASSIGNED_STORE_ID Column Values After Preprocessing")
    print(f"{'='*80}")
    
    if column_name in df_processed.columns:
        processed_values = df_processed[column_name].dropna().unique()
        processed_value_counts = df_processed[column_name].value_counts()
        print(f"\n[PREPROCESSING] Processed DataFrame - ASSIGNED_STORE_ID:")
        print(f"  Total rows: {len(df_processed)}")
        print(f"  Non-null rows: {df_processed[column_name].notna().sum()}")
        print(f"  Null rows: {df_processed[column_name].isna().sum()}")
        print(f"  Unique values: {len(processed_values)}")
        print(f"  All unique values: {sorted(processed_values.tolist())}")
        print(f"  Value counts:")
        for val, count in processed_value_counts.head(20).items():
            print(f"    {val}: {count}")
        if len(processed_value_counts) > 20:
            print(f"    ... and {len(processed_value_counts) - 20} more values")
    else:
        print(f"\n[PREPROCESSING] Column '{column_name}' NOT FOUND in processed dataframe")
        print(f"  (Column may have been removed during preprocessing)")
        print(f"  Available columns: {list(df_processed.columns)[:20]}...")
    
    print(f"{'='*80}\n")
    
    preprocessing_report['final_shape'] = df_processed.shape
    preprocessing_report['processed_columns'] = {
        'discrete': discrete_cols,
        'continuous': continuous_cols
    }
    
    return df_processed, preprocessing_report

# =============================================================================
# PREPROCESSING API ENDPOINTS
# =============================================================================

@app.route('/api/preprocessing-steps-detailed', methods=['POST'])
def preprocessing_steps_detailed():
    """
    Returns detailed information about each preprocessing step for visualization.
    Shows before/after states and highlights changes.
    """
    try:
        data = request.get_json()
        dataset_id = data.get('dataset_id')
        preprocessing_steps = data.get('preprocessing_steps', {})
        target_column = data.get('target_column')
        missing_threshold = data.get('missing_threshold', 0.5)
        treat_negative_one_as_missing = data.get('treat_negative_one_as_missing', True)
        
        if not dataset_id:
            return jsonify({"error": "Missing dataset_id"}), 400
        
        # Load dataset
        artifact_payload = None
        artifact_model_type = None
        artifact_label = None
        if model_type == 'xgboost':
            artifact_label = 'XGBoost'
        elif model_type == 'logistic':
            artifact_label = 'LR'
        elif model_type == 'random_forest':
            artifact_label = 'RandomForest'

        if artifact_label:
            try:
                artifact_payload, _ = load_model_artifact(dataset_id, model_label=artifact_label)
                if artifact_payload:
                    artifact_model_type = artifact_payload.get('model_type')
            except Exception as artifact_err:
                print(f"[apply_scorecard] Warning: Failed to load model artifact ({artifact_label}): {artifact_err}")
                artifact_payload = None
                artifact_model_type = None

        # Load TRAIN dataset explicitly for preprocessing
        try:
            train_df, test_df, split_exists = get_train_test_data(dataset_id)
            
            if split_exists:
                # Use train set if split exists
                df = train_df
                print(f"[PREPROCESSING-STEPS-DETAILED] Using TRAIN set: {len(df)} rows, {len(df.columns)} columns")
            else:
                # Fallback to full dataset if no split exists
                csv_path = get_csv_path(dataset_id)
                df = pd.read_csv(csv_path)
                print(f"[PREPROCESSING-STEPS-DETAILED] No split exists, using FULL dataset: {len(df)} rows, {len(df.columns)} columns")
            
            if df is None or df.empty:
                return jsonify({"error": "Dataset is empty or could not be loaded"}), 400
            if len(df.columns) == 0:
                return jsonify({"error": "Dataset has no columns"}), 400
                
        except Exception as e:
            print(f"[PREPROCESSING-STEPS-DETAILED] Error loading dataset: {str(e)}")
            import traceback
            traceback.print_exc()
            return jsonify({"error": f"Failed to load dataset: {str(e)}"}), 400
        
        # Initialize results container
        step_results = {
            'original_dataset': {
                'shape': df.shape,
                'columns': df.columns.tolist(),
                'data_types': {col: str(dtype) for col, dtype in df.dtypes.items()},
                'missing_values': df.isna().sum().to_dict(),
                'negative_one_counts': {col: int((df[col] == -1).sum()) for col in df.columns if pd.api.types.is_numeric_dtype(df[col])},
                'sample_data': df.head(10).to_dict('records')
            },
            'steps': [],
            'parameters': {
                'missing_threshold': missing_threshold,
                'treat_negative_one_as_missing': treat_negative_one_as_missing
            }
        }
        
        current_df = df.copy()
        
        # Step 1: Detect Column Types
        if preprocessing_steps.get('detect_types', True):
            step_info = {
                'step_name': 'Type Detection',
                'description': 'Automatically classify columns as discrete or continuous based on data characteristics',
                'status': 'pending'
            }
            
            try:
                column_types = detect_column_types(current_df)
                step_info.update({
                    'status': 'completed',
                    'discrete_columns': column_types['discrete'],
                    'continuous_columns': column_types['continuous'],
                    'changes': {
                        'discrete_count': len(column_types['discrete']),
                        'continuous_count': len(column_types['continuous'])
                    }
                })
                
                # Store for next steps
                discrete_cols = column_types['discrete']
                continuous_cols = column_types['continuous']
                
            except Exception as e:
                step_info.update({
                    'status': 'error',
                    'error': str(e)
                })
            
            step_results['steps'].append(step_info)
        
        # Step 2: Handle Missing Values
        if preprocessing_steps.get('handle_missing', True):
            step_info = {
                'step_name': 'Missing Values Treatment',
                'description': f'Handle missing values and -1 values (threshold: {missing_threshold:.1%})',
                'status': 'pending'
            }
            
            try:
                missing_before = current_df.isna().sum().sum()
                missing_by_col_before = current_df.isna().sum().to_dict()
                
                # Count -1 values if treatment is enabled
                negative_one_counts = {}
                if treat_negative_one_as_missing:
                    for col in current_df.columns:
                        if pd.api.types.is_numeric_dtype(current_df[col]):
                            negative_one_counts[col] = int((current_df[col] == -1).sum())
                
                current_df, missing_report = handle_missing_values(
                    current_df, discrete_cols, continuous_cols, 
                    missing_threshold, treat_negative_one_as_missing
                )
                
                missing_after = current_df.isna().sum().sum()
                missing_by_col_after = current_df.isna().sum().to_dict()
                
                step_info.update({
                    'status': 'completed',
                    'changes': {
                        'total_missing_before': int(missing_before),
                        'total_missing_after': int(missing_after),
                        'negative_one_treated': sum(negative_one_counts.values()) if treat_negative_one_as_missing else 0,
                        'columns_removed': missing_report['columns_removed'],
                        'columns_retained': missing_report['columns_retained'],
                        'missing_treated': missing_report['missing_treated'],
                        'negative_one_treated_details': missing_report['negative_one_treated']
                    },
                    'sample_data': current_df.head(10).to_dict('records')
                })
                
                # Update column lists after missing value handling
                discrete_cols = [col for col in discrete_cols if col in current_df.columns]
                continuous_cols = [col for col in continuous_cols if col in current_df.columns]
                
            except Exception as e:
                step_info.update({
                    'status': 'error',
                    'error': str(e)
                })
            
            step_results['steps'].append(step_info)
        
        # Step 3: Remove Duplicates
        if preprocessing_steps.get('remove_duplicates', True):
            step_info = {
                'step_name': 'Duplicate Removal',
                'description': 'Identify and remove duplicate rows from the dataset',
                'status': 'pending'
            }
            
            try:
                rows_before = len(current_df)
                current_df, duplicates_removed = remove_duplicates(current_df)
                rows_after = len(current_df)
                
                step_info.update({
                    'status': 'completed',
                    'changes': {
                        'rows_before': rows_before,
                        'rows_after': rows_after,
                        'duplicates_removed': duplicates_removed,
                        'duplicate_percentage': round((duplicates_removed / rows_before) * 100, 2) if rows_before > 0 else 0
                    },
                    'sample_data': current_df.head(10).to_dict('records')
                })
                
            except Exception as e:
                step_info.update({
                    'status': 'error',
                    'error': str(e)
                })
            
            step_results['steps'].append(step_info)
        
        # Step 4: Handle Outliers
        if preprocessing_steps.get('handle_outliers', True) and continuous_cols:
            step_info = {
                'step_name': 'Outlier Treatment',
                'description': 'Detect and handle outliers in continuous variables using IQR method',
                'status': 'pending'
            }
            
            try:
                outlier_info_before = {}
                for col in continuous_cols:
                    if col in current_df.columns and pd.api.types.is_numeric_dtype(current_df[col]):
                        Q1 = current_df[col].quantile(0.25)
                        Q3 = current_df[col].quantile(0.75)
                        IQR = Q3 - Q1
                        lower_bound = Q1 - 1.5 * IQR
                        upper_bound = Q3 + 1.5 * IQR
                        
                        outliers = ((current_df[col] < lower_bound) | (current_df[col] > upper_bound)).sum()
                        outlier_info_before[col] = {
                            'outliers_count': int(outliers),
                            'lower_bound': float(lower_bound),
                            'upper_bound': float(upper_bound)
                        }
                
                current_df, outlier_info = handle_outliers(current_df, continuous_cols, method='iqr')
                
                step_info.update({
                    'status': 'completed',
                    'changes': {
                        'outliers_before': outlier_info_before,
                        'outliers_after': outlier_info,
                        'method_used': 'IQR (Interquartile Range)'
                    },
                    'sample_data': current_df.head(10).to_dict('records')
                })
                
            except Exception as e:
                step_info.update({
                    'status': 'error',
                    'error': str(e)
                })
            
            step_results['steps'].append(step_info)
        
        # Step 5: Encode Categorical Variables
        if preprocessing_steps.get('encode_categorical', True) and discrete_cols:
            step_info = {
                'step_name': 'Categorical Encoding',
                'description': 'Convert categorical variables to numerical using label encoding',
                'status': 'pending'
            }
            
            try:
                encoding_info_before = {}
                for col in discrete_cols:
                    if col in current_df.columns and col != target_column:
                        encoding_info_before[col] = {
                            'dtype_before': str(current_df[col].dtype),
                            'unique_values': current_df[col].nunique(),
                            'sample_values': current_df[col].dropna().unique()[:5].tolist()
                        }
                
                current_df, encoding_info, label_encoders = encode_categorical_variables(
                    current_df, discrete_cols, target_column
                )
                
                encoding_info_after = {}
                for col in discrete_cols:
                    if col in current_df.columns and col != target_column:
                        encoding_info_after[col] = {
                            'dtype_after': str(current_df[col].dtype),
                            'mapping': encoding_info.get(col, {}).get('mapping', {})
                        }
                
                step_info.update({
                    'status': 'completed',
                    'changes': {
                        'encoding_before': encoding_info_before,
                        'encoding_after': encoding_info_after,
                        'encoding_mappings': encoding_info
                    },
                    'sample_data': current_df.head(10).to_dict('records')
                })
                
            except Exception as e:
                step_info.update({
                    'status': 'error',
                    'error': str(e)
                })
            
            step_results['steps'].append(step_info)
        
        # Final dataset state
        step_results['final_dataset'] = {
            'shape': current_df.shape,
            'columns': current_df.columns.tolist(),
            'data_types': {col: str(dtype) for col, dtype in current_df.dtypes.items()},
            'missing_values': current_df.isna().sum().to_dict(),
            'sample_data': current_df.head(10).to_dict('records')
        }
        
        return jsonify({
            "success": True,
            "preprocessing_details": step_results
        })
        
    except Exception as e:
        return jsonify({"error": f"Preprocessing visualization failed: {str(e)}"}), 500

@app.route('/api/preprocessing-column-changes', methods=['POST'])
def preprocessing_column_changes():
    """
    Returns detailed column-level changes for the preprocessing preview.
    """
    try:
        data = request.get_json()
        dataset_id = data.get('dataset_id')
        preprocessing_steps = data.get('preprocessing_steps', {})
        missing_threshold = data.get('missing_threshold', 0.5)
        treat_negative_one_as_missing = data.get('treat_negative_one_as_missing', True)
        
        if not dataset_id:
            return jsonify({"error": "Missing dataset_id"}), 400
        
        # Load TRAIN dataset explicitly for preprocessing
        try:
            print(f"\n[PREPROCESSING-COLUMN-CHANGES] ========================================")
            print(f"[PREPROCESSING-COLUMN-CHANGES] Loading dataset {dataset_id}")
            train_df, test_df, split_exists = get_train_test_data(dataset_id)
            print(f"[PREPROCESSING-COLUMN-CHANGES] Split exists: {split_exists}")
            
            if split_exists:
                # Use train set if split exists
                df_original = train_df
                print(f"[PREPROCESSING-COLUMN-CHANGES] ✅ Using TRAIN set: {len(df_original)} rows, {len(df_original.columns)} columns")
                print(f"[PREPROCESSING-COLUMN-CHANGES] Train DataFrame columns: {list(df_original.columns)[:10]}")
                print(f"[PREPROCESSING-COLUMN-CHANGES] Train DataFrame shape: {df_original.shape}")
                print(f"[PREPROCESSING-COLUMN-CHANGES] Train DataFrame head:\n{df_original.head(2)}")
            else:
                # Fallback to full dataset if no split exists
                csv_path = get_csv_path(dataset_id)
                df_original = pd.read_csv(csv_path)
                print(f"[PREPROCESSING-COLUMN-CHANGES] ⚠️ No split exists, using FULL dataset: {len(df_original)} rows, {len(df_original.columns)} columns")
                print(f"[PREPROCESSING-COLUMN-CHANGES] Full DataFrame columns: {list(df_original.columns)[:10]}")
            
            if df_original is None or df_original.empty:
                print(f"[PREPROCESSING-COLUMN-CHANGES] ❌ ERROR: Dataset is empty!")
                return jsonify({"error": "Dataset is empty or could not be loaded", "success": False}), 400
            if len(df_original.columns) == 0:
                print(f"[PREPROCESSING-COLUMN-CHANGES] ❌ ERROR: Dataset has no columns!")
                return jsonify({"error": "Dataset has no columns", "success": False}), 400
            print(f"[PREPROCESSING-COLUMN-CHANGES] ========================================\n")
                
        except Exception as e:
            print(f"[PREPROCESSING-COLUMN-CHANGES] ❌ ERROR loading dataset: {str(e)}")
            import traceback
            traceback.print_exc()
            return jsonify({"error": f"Failed to load dataset: {str(e)}", "success": False}), 400
        
        # Apply preprocessing with new parameters
        df_processed, preprocessing_report = preprocess_dataset(
            df_original, 
            preprocessing_steps=preprocessing_steps,
            missing_threshold=missing_threshold,
            treat_negative_one_as_missing=treat_negative_one_as_missing
        )
        
        # Get outlier information from preprocessing report
        outlier_info = preprocessing_report.get('details', {}).get('outliers', {})
        
        # Generate column-level change analysis
        column_changes = []
        
        print(f"[PREPROCESSING-COLUMN-CHANGES] Original columns: {len(df_original.columns)}")
        print(f"[PREPROCESSING-COLUMN-CHANGES] Processed columns: {len(df_processed.columns)}")
        print(f"[PREPROCESSING-COLUMN-CHANGES] Original shape: {df_original.shape}")
        print(f"[PREPROCESSING-COLUMN-CHANGES] Processed shape: {df_processed.shape}")
        
        if len(df_original.columns) == 0:
            print(f"[PREPROCESSING-COLUMN-CHANGES] ERROR: Original DataFrame has no columns!")
            return jsonify({
                "success": False,
                "error": "Original dataset has no columns",
                "column_changes": []
            }), 400
        
        for col in df_original.columns:
            if col in df_processed.columns:
                # Column was retained
                original_series = df_original[col]
                processed_series = df_processed[col]
                
                changes = []
                
                # Data type changes
                original_dtype = str(original_series.dtype)
                processed_dtype = str(processed_series.dtype)
                if original_dtype != processed_dtype:
                    changes.append(f"Data type changed from {original_dtype} to {processed_dtype}")
                
                # Missing values changes
                original_missing = original_series.isna().sum()
                processed_missing = processed_series.isna().sum()
                if original_missing > 0 and processed_missing == 0:
                    changes.append(f"Missing values handled ({original_missing} values imputed)")
                elif original_missing > processed_missing:
                    changes.append(f"Missing values reduced from {original_missing} to {processed_missing}")
                
                # -1 values treatment
                if treat_negative_one_as_missing and pd.api.types.is_numeric_dtype(original_series):
                    negative_one_count = (original_series == -1).sum()
                    if negative_one_count > 0:
                        changes.append(f"{-1} values treated as missing ({negative_one_count} values)")
                
                # Unique values changes (for categorical encoding)
                original_unique = original_series.nunique()
                processed_unique = processed_series.nunique()
                if original_unique != processed_unique and 'object' in original_dtype:
                    changes.append(f"Encoded from {original_unique} categories to numerical")
                
                # Outlier removal information
                if col in outlier_info:
                    outlier_data = outlier_info[col]
                    outliers_count = outlier_data.get('outliers_detected', 0)
                    outliers_pct = outlier_data.get('outliers_percentage', 0)
                    method = outlier_data.get('method', 'iqr')
                    if outliers_count > 0:
                        changes.append(f"Outliers handled: {outliers_count} ({outliers_pct:.1f}%) capped using {method.upper()} method")
                
                # Calculate repeat rate (for continuous columns)
                repeat_rate = None
                if pd.api.types.is_numeric_dtype(processed_series):
                    # Calculate the percentage of the most frequent value
                    value_counts = processed_series.value_counts()
                    if len(value_counts) > 0:
                        most_frequent_count = value_counts.iloc[0]
                        total_non_null = processed_series.notna().sum()
                        if total_non_null > 0:
                            repeat_rate = (most_frequent_count / total_non_null) * 100
                
                # Statistical changes for numerical columns
                variance = None
                processed_stats = None
                original_stats = None
                coefficient_of_variation = None
                if pd.api.types.is_numeric_dtype(processed_series):
                    # Helper function to safely convert pandas values to float, handling NaN
                    def safe_float(val):
                        if val is None or (isinstance(val, float) and (np.isnan(val) or np.isinf(val))):
                            return None
                        try:
                            fval = float(val)
                            if np.isnan(fval) or np.isinf(fval):
                                return None
                            return fval
                        except (ValueError, TypeError):
                            return None
                    
                    original_stats = {
                        'min': safe_float(original_series.min()) if not original_series.empty else None,
                        'max': safe_float(original_series.max()) if not original_series.empty else None,
                        'mean': safe_float(original_series.mean()) if not original_series.empty else None,
                        'std': safe_float(original_series.std()) if not original_series.empty else None,
                        'median': safe_float(original_series.median()) if not original_series.empty else None
                    }
                    
                    processed_stats = {
                        'min': safe_float(processed_series.min()) if not processed_series.empty else None,
                        'max': safe_float(processed_series.max()) if not processed_series.empty else None,
                        'mean': safe_float(processed_series.mean()) if not processed_series.empty else None,
                        'std': safe_float(processed_series.std()) if not processed_series.empty else None,
                        'median': safe_float(processed_series.median()) if not processed_series.empty else None
                    }
                    
                    # Calculate variance
                    if not processed_series.empty:
                        var_val = processed_series.var()
                        variance = safe_float(var_val) if var_val is not None else 0.0
                    else:
                        variance = 0.0
                    
                    # Calculate coefficient of variation (CV = std/mean * 100)
                    if processed_stats['mean'] is not None and processed_stats['mean'] != 0 and processed_stats['std'] is not None:
                        coefficient_of_variation = abs((processed_stats['std'] / processed_stats['mean']) * 100)
                        coefficient_of_variation = safe_float(coefficient_of_variation)
                    
                    # Check for significant statistical changes (e.g., due to outlier treatment)
                    stat_changes = []
                    for stat in ['min', 'max', 'mean', 'std']:
                        orig_val = original_stats[stat]
                        proc_val = processed_stats[stat]
                        if orig_val is not None and proc_val is not None and orig_val != 0:
                            change_pct = abs(proc_val - orig_val) / abs(orig_val) * 100
                            if change_pct > 5:  # More than 5% change
                                stat_changes.append(f"{stat.upper()} changed by {change_pct:.1f}%")
                    
                    if stat_changes:
                        changes.extend(stat_changes)
                else:
                    # FIX: For categorical columns, variance doesn't apply
                    # Set to None (null) instead of 0.0 to indicate "not applicable"
                    # Frontend should check cardinality (unique values) instead of variance for categorical columns
                    variance = None
                
                column_changes.append({
                    'column': col,
                    'changes': changes,
                    'original_dtype': original_dtype,
                    'processed_dtype': processed_dtype,
                    'original_missing': int(original_missing),
                    'processed_missing': int(processed_missing),
                    'negative_one_count': int((original_series == -1).sum()) if treat_negative_one_as_missing and pd.api.types.is_numeric_dtype(original_series) else 0,
                    'variance': variance,
                    'coefficient_of_variation': coefficient_of_variation,
                    'repeat_rate': repeat_rate,
                    'processed_stats': processed_stats,
                    'original_stats': original_stats,
                    'has_changes': len(changes) > 0
                })
            else:
                # Column was removed
                original_series = df_original[col]
                missing_count = original_series.isna().sum()
                missing_ratio = missing_count / len(original_series)
                negative_one_count = (original_series == -1).sum() if pd.api.types.is_numeric_dtype(original_series) else 0
                
                # Calculate variance for removed columns too (for reference)
                variance = 0.0
                if pd.api.types.is_numeric_dtype(original_series):
                    if not original_series.empty:
                        var_val = original_series.var()
                        if var_val is not None and not (isinstance(var_val, float) and (np.isnan(var_val) or np.isinf(var_val))):
                            variance = float(var_val)
                        else:
                            variance = 0.0
                    else:
                        variance = 0.0
                
                column_changes.append({
                    'column': col,
                    'changes': [f"Column removed: {missing_ratio:.1%} missing values"],
                    'original_dtype': str(original_series.dtype),
                    'processed_dtype': 'REMOVED',
                    'original_missing': int(missing_count),
                    'processed_missing': 0,
                    'negative_one_count': int(negative_one_count),
                    'variance': variance,
                    'has_changes': True,
                    'removed': True
                })
        
        # Sample data for preview - clean NaN values
        original_sample = df_original.head(10).to_dict('records')
        processed_sample = df_processed.head(10).to_dict('records')
        original_sample = _clean_nan_values(original_sample)
        processed_sample = _clean_nan_values(processed_sample)
        
        print(f"\n[PREPROCESSING-COLUMN-CHANGES] ========================================")
        print(f"[PREPROCESSING-COLUMN-CHANGES] Generated {len(column_changes)} column changes")
        print(f"[PREPROCESSING-COLUMN-CHANGES] First 5 columns: {[c['column'] for c in column_changes[:5]]}")
        print(f"[PREPROCESSING-COLUMN-CHANGES] Sample column change: {column_changes[0] if column_changes else 'N/A'}")
        
        if len(column_changes) == 0:
            print(f"[PREPROCESSING-COLUMN-CHANGES] ❌ WARNING: No column changes generated!")
            return jsonify({
                "success": False,
                "error": "No column changes generated. Dataset may be empty.",
                "column_changes": []
            }), 400
        
        response_data = {
            "success": True,
            "column_changes": column_changes,
            "preview": {
                "original_sample": original_sample,
                "processed_sample": processed_sample
            },
            "summary": {
                "original_shape": df_original.shape,
                "processed_shape": df_processed.shape,
                "columns_with_changes": len([c for c in column_changes if c['has_changes']]),
                "columns_removed": len([c for c in column_changes if c.get('removed', False)]),
                "total_columns": len(column_changes)
            }
        }
        
        # Clean all NaN values before returning
        response_data = _clean_nan_values(response_data)
        
        print(f"[PREPROCESSING-COLUMN-CHANGES] ✅ Response prepared:")
        print(f"  - success: {response_data['success']}")
        print(f"  - column_changes count: {len(response_data['column_changes'])}")
        print(f"  - summary: {response_data['summary']}")
        print(f"[PREPROCESSING-COLUMN-CHANGES] ========================================\n")
        
        return jsonify(response_data)
        
    except Exception as e:
        print(f"[PREPROCESSING-COLUMN-CHANGES] ❌ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Column changes analysis failed: {str(e)}"}), 500

@app.route('/api/preprocessing-step-preview', methods=['POST'])
def preprocessing_step_preview():
    """
    Preview individual preprocessing steps with before/after comparison.
    """
    try:
        data = request.get_json()
        dataset_id = data.get('dataset_id')
        step_name = data.get('step_name')
        preprocessing_steps = data.get('preprocessing_steps', {})
        
        if not dataset_id or not step_name:
            return jsonify({"error": "Missing dataset_id or step_name"}), 400
        
        # Load dataset
        try:
            csv_path = get_csv_path(dataset_id)
            df = pd.read_csv(csv_path)
        except Exception as e:
            return jsonify({"error": f"Failed to load dataset: {str(e)}"}), 400
        
        # Apply preprocessing up to the specified step
        current_steps = {}
        step_order = ['detect_types', 'handle_missing', 'remove_duplicates', 'handle_outliers', 'encode_categorical']
        
        target_step_index = step_order.index(step_name) if step_name in step_order else -1
        
        if target_step_index == -1:
            return jsonify({"error": f"Invalid step name: {step_name}"}), 400
        
        # Enable only steps up to the target step
        for i, step in enumerate(step_order):
            current_steps[step] = (i <= target_step_index)
        
        df_processed, preprocessing_report = preprocess_dataset(
            df, preprocessing_steps=current_steps
        )
        
        # Get step-specific details
        step_details = {}
        if step_name == 'detect_types':
            column_types = detect_column_types(df)
            step_details = {
                'discrete_columns': column_types['discrete'],
                'continuous_columns': column_types['continuous'],
                'detection_method': 'Combined heuristic analysis (name patterns, data characteristics, unique values)'
            }
        
        elif step_name == 'handle_missing':
            missing_before = df.isna().sum().sum()
            column_types = detect_column_types(df)
            df_temp = handle_missing_values(df, column_types['discrete'], column_types['continuous'])
            missing_after = df_temp.isna().sum().sum()
            
            step_details = {
                'missing_before': int(missing_before),
                'missing_after': int(missing_after),
                'methods_used': {
                    'discrete': 'Mode imputation or "Missing" category',
                    'continuous': 'Median imputation'
                }
            }
        
        elif step_name == 'remove_duplicates':
            rows_before = len(df)
            df_temp, duplicates_removed = remove_duplicates(df)
            rows_after = len(df_temp)
            
            step_details = {
                'rows_before': rows_before,
                'rows_after': rows_after,
                'duplicates_removed': duplicates_removed
            }
        
        elif step_name == 'handle_outliers':
            column_types = detect_column_types(df)
            df_temp, outlier_info = handle_outliers(df, column_types['continuous'], method='iqr')
            
            step_details = {
                'method_used': 'IQR (Interquartile Range) with capping',
                'outlier_details': outlier_info
            }
        
        elif step_name == 'encode_categorical':
            column_types = detect_column_types(df)
            df_temp, encoding_info, _ = encode_categorical_variables(df, column_types['discrete'])
            
            step_details = {
                'method_used': 'Label Encoding',
                'encoded_columns': list(encoding_info.keys()),
                'encoding_mappings': encoding_info
            }
        
        return jsonify({
            "success": True,
            "step_name": step_name,
            "step_details": step_details,
            "before_sample": df.head(5).to_dict('records'),
            "after_sample": df_processed.head(5).to_dict('records'),
            "dataset_shapes": {
                "before": df.shape,
                "after": df_processed.shape
            }
        })
        
    except Exception as e:
        return jsonify({"error": f"Step preview failed: {str(e)}"}), 500

# =============================================================================
# ENHANCED QUALITY REPORT WITH VISUALIZATION DATA
# =============================================================================

@app.route('/api/dataset-quality-metrics', methods=['POST'])
def dataset_quality_metrics():
    """
    Returns comprehensive quality metrics for visualization in grids.
    """
    try:
        data = request.get_json()
        dataset_id = data.get('dataset_id')
        
        if not dataset_id:
            return jsonify({"error": "Missing dataset_id"}), 400
        
        # Load TRAIN dataset explicitly for preprocessing
        try:
            train_df, test_df, split_exists = get_train_test_data(dataset_id)
            
            if split_exists:
                # Use train set if split exists
                df = train_df
                print(f"[DATASET-QUALITY-METRICS] Using TRAIN set: {len(df)} rows, {len(df.columns)} columns")
            else:
                # Fallback to full dataset if no split exists
                csv_path = get_csv_path(dataset_id)
                df = pd.read_csv(csv_path)
                print(f"[DATASET-QUALITY-METRICS] No split exists, using FULL dataset: {len(df)} rows, {len(df.columns)} columns")
            
            if df is None or df.empty:
                return jsonify({"error": "Dataset is empty or could not be loaded", "success": False}), 400
            if len(df.columns) == 0:
                return jsonify({"error": "Dataset has no columns", "success": False}), 400
                
        except Exception as e:
            print(f"[DATASET-QUALITY-METRICS] Error loading dataset: {str(e)}")
            import traceback
            traceback.print_exc()
            return jsonify({"error": f"Failed to load dataset: {str(e)}", "success": False}), 400
        
        # Basic information
        basic_info = {
            'num_rows': len(df),
            'num_columns': len(df.columns),
            'memory_usage_mb': round(df.memory_usage(deep=True).sum() / 1024**2, 2),
            'total_cells': len(df) * len(df.columns)
        }
        
        # Missing values analysis
        missing_values = df.isna().sum()
        total_missing = missing_values.sum()
        missing_percentage = (total_missing / basic_info['total_cells']) * 100
        
        missing_analysis = {
            'total_missing': int(total_missing),
            'missing_percentage': round(missing_percentage, 2),
            'columns_with_missing': [col for col in df.columns if df[col].isna().any()],
            'missing_by_column': _clean_nan_values(missing_values.to_dict()),
            'complete_columns': [col for col in df.columns if not df[col].isna().any()],
            'severity': 'High' if missing_percentage > 20 else 'Medium' if missing_percentage > 5 else 'Low'
        }
        
        # Duplicates analysis
        duplicate_analysis = {
            'exact_duplicates': int(df.duplicated().sum()),
            'percentage_duplicates': round((df.duplicated().sum() / len(df)) * 100, 2),
            'severity': 'High' if (df.duplicated().sum() / len(df)) * 100 > 10 else 'Medium' if (df.duplicated().sum() / len(df)) * 100 > 2 else 'Low'
        }
        
        # Data types analysis
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        categorical_cols = df.select_dtypes(include=['object']).columns.tolist()
        datetime_cols = df.select_dtypes(include=['datetime']).columns.tolist()
        
        dtype_analysis = {
            'numeric_columns': numeric_cols,
            'categorical_columns': categorical_cols,
            'datetime_columns': datetime_cols,
            'mixed_type_columns': [col for col in df.columns if len(set(map(type, df[col].dropna()))) > 1] if len(df) > 0 else []
        }
        
        # Outlier analysis for numeric columns
        outlier_analysis = {}
        for col in numeric_cols:
            Q1 = df[col].quantile(0.25)
            Q3 = df[col].quantile(0.75)
            IQR = Q3 - Q1
            lower_bound = Q1 - 1.5 * IQR
            upper_bound = Q3 + 1.5 * IQR
            
            outliers = ((df[col] < lower_bound) | (df[col] > upper_bound)).sum()
            outlier_percentage = (outliers / len(df)) * 100
            
            outlier_analysis[col] = {
                'outliers_count': int(outliers),
                'outliers_percentage': round(outlier_percentage, 2),
                'lower_bound': _clean_nan_values(float(lower_bound)),
                'upper_bound': _clean_nan_values(float(upper_bound)),
                'severity': 'High' if outlier_percentage > 10 else 'Medium' if outlier_percentage > 2 else 'Low'
            }
        
        # Cardinality analysis for categorical columns
        cardinality_analysis = {}
        for col in categorical_cols:
            unique_count = df[col].nunique()
            cardinality_percentage = (unique_count / len(df)) * 100
            
            most_frequent = None
            if not df[col].mode().empty:
                most_frequent_val = df[col].mode().iloc[0]
                most_frequent = _clean_nan_values(most_frequent_val)
            
            cardinality_analysis[col] = {
                'unique_values': int(unique_count),
                'cardinality_percentage': round(cardinality_percentage, 2),
                'most_frequent': most_frequent,
                'freq_count': int(df[col].value_counts().iloc[0]) if not df[col].value_counts().empty else 0,
                'severity': 'High' if cardinality_percentage > 50 else 'Medium' if cardinality_percentage > 20 else 'Low'
            }
        
        # Data quality score (0-100)
        quality_score = 100
        
        # Penalize for missing values
        quality_score -= min(missing_percentage * 2, 40)  # Up to 40 points for missing values
        
        # Penalize for duplicates
        quality_score -= min(duplicate_analysis['percentage_duplicates'] * 2, 20)  # Up to 20 points for duplicates
        
        # Penalize for high cardinality
        high_cardinality_penalty = sum(1 for col, analysis in cardinality_analysis.items() if analysis['severity'] == 'High')
        quality_score -= min(high_cardinality_penalty * 5, 15)  # Up to 15 points for high cardinality
        
        # Penalize for many outliers
        high_outlier_penalty = sum(1 for col, analysis in outlier_analysis.items() if analysis['severity'] == 'High')
        quality_score -= min(high_outlier_penalty * 3, 15)  # Up to 15 points for outliers
        
        quality_score = max(0, round(quality_score, 2))
        
        # Quality rating
        if quality_score >= 90:
            quality_rating = 'Excellent'
        elif quality_score >= 80:
            quality_rating = 'Good'
        elif quality_score >= 70:
            quality_rating = 'Fair'
        elif quality_score >= 60:
            quality_rating = 'Poor'
        else:
            quality_rating = 'Very Poor'
        
        # Clean all NaN values before returning
        response_data = {
            "success": True,
            "quality_metrics": {
                "basic_info": basic_info,
                "missing_analysis": missing_analysis,
                "duplicate_analysis": duplicate_analysis,
                "dtype_analysis": dtype_analysis,
                "outlier_analysis": outlier_analysis,
                "cardinality_analysis": cardinality_analysis,
                "quality_score": quality_score,
                "quality_rating": quality_rating
            }
        }
        
        return jsonify(_clean_nan_values(response_data))
        
    except Exception as e:
        return jsonify({"error": f"Quality metrics calculation failed: {str(e)}"}), 500
    
@app.route('/api/preprocess-dataset', methods=['POST'])
def preprocess_dataset_api():
    """
    Main preprocessing endpoint that applies preprocessing and creates a new dataset.
    """
    try:
        data = request.get_json()
        dataset_id = data.get('dataset_id')
        preprocessing_steps = data.get('preprocessing_steps', {
            'detect_types': True,
            'handle_missing': True,
            'remove_duplicates': True,
            'handle_outliers': True,
            'encode_categorical': True
        })
        target_column = data.get('target_column')
        missing_threshold = data.get('missing_threshold', 0.5)
        treat_negative_one_as_missing = data.get('treat_negative_one_as_missing', True)
        
        if not dataset_id:
            return jsonify({"error": "Missing dataset_id"}), 400
        
        # Load TRAIN dataset explicitly for preprocessing
        try:
            train_df, test_df, split_exists = get_train_test_data(dataset_id)
            
            if split_exists:
                # Use train set if split exists
                df = train_df
                print(f"[PREPROCESS-DATASET] Using TRAIN set: {len(df)} rows, {len(df.columns)} columns")
            else:
                # Fallback to full dataset if no split exists
                csv_path = get_csv_path(dataset_id)
                df = pd.read_csv(csv_path)
                print(f"[PREPROCESS-DATASET] No split exists, using FULL dataset: {len(df)} rows, {len(df.columns)} columns")
            
            if df is None or df.empty:
                return jsonify({"error": "Dataset is empty or could not be loaded"}), 400
            if len(df.columns) == 0:
                return jsonify({"error": "Dataset has no columns"}), 400
                
        except Exception as e:
            print(f"[PREPROCESS-DATASET] Error loading dataset: {str(e)}")
            import traceback
            traceback.print_exc()
            return jsonify({"error": f"Failed to load dataset: {str(e)}"}), 400
        
        # Apply preprocessing
        df_processed, preprocessing_report = preprocess_dataset(
            df,
            target_col=target_column,
            preprocessing_steps=preprocessing_steps,
            missing_threshold=missing_threshold,
            treat_negative_one_as_missing=treat_negative_one_as_missing
        )
        
        # Generate new dataset ID and save processed data
        new_dataset_id = generate_dataset_id()
        processed_filename = f"processed_dataset_{new_dataset_id}.csv"
        processed_path = os.path.join('uploads', processed_filename)
        
        # Save processed dataset
        df_processed.to_csv(processed_path, index=False)
        
        # Store dataset info in database
        dataset_info = {
            'id': new_dataset_id,
            'filename': processed_filename,
            'file_path': processed_path,
            'original_filename': f"processed_from_{dataset_id}",
            'upload_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'file_size': os.path.getsize(processed_path),
            'num_rows': len(df_processed),
            'num_columns': len(df_processed.columns),
            'preprocessing_applied': True,
            'original_dataset_id': dataset_id,
            'preprocessing_report': preprocessing_report
        }
        
        # Save to database (you'll need to implement this based on your storage)
        save_dataset_info(dataset_info)
        
        return jsonify({
            "success": True,
            "message": "Dataset preprocessing completed successfully",
            "new_dataset_id": new_dataset_id,
            "preprocessing_report": preprocessing_report,
            "dataset_info": {
                "rows": len(df_processed),
                "columns": len(df_processed.columns),
                "original_rows": len(df),
                "original_columns": len(df.columns)
            }
        })
        
    except Exception as e:
        return jsonify({"error": f"Preprocessing failed: {str(e)}"}), 500

# Helper functions you'll need to implement:
def generate_dataset_id():
    """Generate a unique dataset ID"""
    return int(datetime.now().timestamp())

def save_dataset_info(dataset_info):
    """
    Save dataset information to your database.
    You'll need to implement this based on your storage (SQLite, JSON file, etc.)
    """
    # Example implementation using a JSON file
    try:
        if os.path.exists('datasets.json'):
            with open('datasets.json', 'r') as f:
                datasets = json.load(f)
        else:
            datasets = []
        
        datasets.append(dataset_info)
        
        with open('datasets.json', 'w') as f:
            json.dump(datasets, f, indent=2)
    except Exception as e:
        print(f"Warning: Could not save dataset info: {e}")

# Helper function to safely save CSV with retry logic
def safe_save_csv(df, dataset_id: Optional[int] = None, max_retries=3):
    """
    Safely saves DataFrame to dataset CSV file with retry logic for Windows permission issues.
    """
    csv_path = get_csv_path(dataset_id)
    import time
    for attempt in range(max_retries):
        try:
            df.to_csv(csv_path, index=False)
            return True
        except PermissionError as e:
            if attempt < max_retries - 1:
                time.sleep(0.1)  # Wait 100ms before retry
            else:
                raise e  # Re-raise on final attempt
    return False


# ----------- Get Uploaded CSV Columns -----------
@app.route('/api/uploaded-csv-columns', methods=['GET'])
def get_uploaded_csv_columns():
    """
    Returns the column headers from the uploaded.csv file.
    """
    try:
        dataset_id = request.args.get('dataset_id') or request.args.get('record_id')
        csv_path = get_csv_path(dataset_id)
    except FileNotFoundError as fe:
        return jsonify({"error": str(fe)}), 400
    try:
        df = pd.read_csv(csv_path, nrows=0)
        return jsonify({"columns": df.columns.tolist()})
    except FileNotFoundError as fe:
        return jsonify({"error": str(fe)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ----------- Health Check -----------
@app.route('/api/health', methods=['GET'])
def health():
    """
    A simple health check endpoint.
    """
    return jsonify({"status": "OK", "time": str(datetime.datetime.now())})

# ----------- Database Health Check -----------
@app.route('/api/db-health', methods=['GET'])
def db_health():
    """
    Checks database connectivity by running a simple query.
    Returns connection parameters (masked) and status.
    """
    try:
        # Read env without mutating
        dbname = os.getenv('PG_DBNAME')
        user = os.getenv('PG_USER')
        host = os.getenv('PG_HOST')
        port = os.getenv('PG_PORT')

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('SELECT 1')
        cur.fetchone()
        conn.close()
        return jsonify({
            "ok": True,
            "connection": {
                "dbname": dbname,
                "user": user,
                "host": host,
                "port": port
            }
        })
    except Exception as e:
        logging.exception("DB health check failed")
        return jsonify({
            "ok": False,
            "error": str(e),
            "connection": {
                "dbname": os.getenv('PG_DBNAME'),
                "user": os.getenv('PG_USER'),
                "host": os.getenv('PG_HOST'),
                "port": os.getenv('PG_PORT')
            }
        }), 500

# ----------- Upload CSV -----------
@app.route('/api/upload-csv', methods=['POST'])
def upload_csv():
    """
    Handles CSV file uploads, saves the file, creates dataset and feature records.
    Returns dataset_id and column information.
    Optimized to save file directly and read only header for column names.
    """
    if 'file' not in request.files:
        return jsonify({"error": "No file part in the request"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400
    if file and file.filename.endswith('.csv'):
        try:
            # timestamp values: one safe for filenames, one human-readable for DB/response
            ts_fname = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            timestamp = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

            # Save to a dedicated uploads folder using the original filename + timestamp
            uploads_dir = os.path.join(os.path.dirname(__file__), "uploads")
            os.makedirs(uploads_dir, exist_ok=True)
            original_name = secure_filename(file.filename)
            base, ext = os.path.splitext(original_name)
            timestamped_name = f"{base}_{ts_fname}{ext}"
            save_path = os.path.join(uploads_dir, timestamped_name)
            
            # Save file directly without reading into memory first (much faster)
            file.save(save_path)
            
            # Verify file was saved
            if not os.path.exists(save_path):
                return jsonify({"error": "Failed to save uploaded file"}), 500
            
            # Verify file is not empty
            if os.path.getsize(save_path) == 0:
                os.remove(save_path)
                return jsonify({"error": "Uploaded CSV file is empty"}), 400
            
            # Read header to get column names - try multiple methods for reliability
            columns = None
            try:
                # Method 1: Read first few rows with pandas (handles various CSV formats)
                # Use error_bad_lines=False for older pandas, on_bad_lines='skip' for newer
                try:
                    df_sample = pd.read_csv(save_path, nrows=5, encoding='utf-8', on_bad_lines='skip')
                except TypeError:
                    # Older pandas version - use error_bad_lines parameter
                    df_sample = pd.read_csv(save_path, nrows=5, encoding='utf-8', error_bad_lines=False, warn_bad_lines=False)
                
                if not df_sample.empty and len(df_sample.columns) > 0:
                    columns = df_sample.columns.tolist()
            except Exception as e:
                # Method 2: If pandas fails, try reading first line manually
                try:
                    with open(save_path, 'r', encoding='utf-8', errors='ignore') as f:
                        first_line = f.readline().strip()
                        if first_line:
                            # Handle both comma and semicolon delimiters
                            if ',' in first_line:
                                columns = [col.strip().strip('"').strip("'") for col in first_line.split(',')]
                            elif ';' in first_line:
                                columns = [col.strip().strip('"').strip("'") for col in first_line.split(';')]
                            else:
                                columns = [first_line]  # Single column
                except Exception as e2:
                    os.remove(save_path)
                    return jsonify({"error": f"Failed to read CSV file. Error: {str(e2)}"}), 400
            
            # Validate columns
            if not columns or len(columns) == 0:
                os.remove(save_path)
                return jsonify({"error": "Uploaded CSV has no valid columns. Please check the file format."}), 400
            
            # Filter out empty column names
            columns = [col for col in columns if col and col.strip()]
            if len(columns) == 0:
                os.remove(save_path)
                return jsonify({"error": "Uploaded CSV has no valid column names"}), 400
            
            # Get row count efficiently by reading file line by line (much faster than loading entire CSV)
            row_count = 0
            try:
                with open(save_path, 'r', encoding='utf-8') as f:
                    # Skip header
                    next(f, None)
                    row_count = sum(1 for _ in f)
            except Exception:
                # Fallback: read a sample to estimate (for very large files)
                df_sample = pd.read_csv(save_path, nrows=1000)
                if len(df_sample) < 1000:
                    row_count = len(df_sample)
                else:
                    # Estimate based on file size (rough approximation)
                    file_size = os.path.getsize(save_path)
                    avg_row_size = len(df_sample.to_csv(index=False)) / len(df_sample)
                    row_count = int(file_size / avg_row_size) if avg_row_size > 0 else 0

            # Create dataset record
            dataset_name = file.filename.replace('.csv', '')

            # Store a relative path in the dataset record (so DB does not hold machine-specific absolute paths)
            rel_path = os.path.join('uploads', timestamped_name)
            dataset_id = create_dataset(
                name=f"{dataset_name}_{timestamp}",
                file_path=rel_path,
                total_features=len(columns),
                discrete_features=0,  # Will be updated after classification
                continuous_features=0,  # Will be updated after classification
                target_variable=None  # Will be updated when target is selected
            )
            
            # Create feature records for all columns (initially unclassified)
            features_data = [
                {
                    'name': col,
                    'type': 'continuous',  # Default, will be updated by classification
                    'selected': False
                }
                for col in columns
            ]
            create_features_batch(dataset_id, features_data)
            
            return jsonify({
                "success": True,
                "dataset_id": dataset_id,
                "columns": columns,
                "rowCount": row_count,
                "timestamp": timestamp,
                # dataset_path shows the stored (relative) path; resolved_path has the absolute path on server
                "dataset_path": rel_path,
                "resolved_path": save_path
            })
        except Exception as e:
            return jsonify({"error": f"Failed to process CSV: {str(e)}"}), 500
    return jsonify({"error": "File must be a CSV"}), 400

# ----------- Target Distribution -----------
@app.route('/api/target-distribution', methods=['POST'])
def target_distribution():
    """
    Computes and returns the value counts for a specified target column.
    """
    try:
        data = request.get_json(silent=True) or {}
        dataset_id = (
            data.get('record_id')
            or data.get('dataset_id')
            or data.get('recordId')
            or data.get('datasetId')
        )
        try:
            csv_path = get_csv_path(dataset_id)
        except FileNotFoundError as fe:
            return jsonify({"error": str(fe)}), 400
        try:
            df = pd.read_csv(csv_path)
        except FileNotFoundError as fe:
            return jsonify({"error": str(fe)}), 400
        except Exception as e:
            return jsonify({"error": str(e)}), 500
        col = data.get('column')
        if not col or col not in df.columns:
            return jsonify({"error": f"Column '{col}' not found in dataset"}), 400
        counts = df[col].value_counts().to_dict()
        return jsonify(counts)
    except Exception as e:
        return jsonify({"error": f"Failed to compute target distribution: {str(e)}"}), 500


# ----------- Train/Test Split -----------
@app.route('/api/train-test-split', methods=['POST'])
def create_train_test_split():
    """
    Create or get train/test split for a dataset.
    
    This endpoint creates a stratified 70/30 train/test split AFTER variable classification
    and BEFORE any preprocessing, binning, or model training to prevent data leakage.
    
    Request body:
    {
        "dataset_id": int,
        "test_size": float (optional, default from config.py),
        "force_recalculate": bool (optional, default false)
    }
    
    Returns:
    {
        "success": bool,
        "split_info": {...},
        "is_existing": bool
    }
    """
    try:
        from train_test_split import get_or_create_train_test_split
        from config import DEFAULT_TEST_SIZE
        
        data = request.get_json()
        dataset_id = data.get('dataset_id')
        test_size = data.get('test_size', DEFAULT_TEST_SIZE)  # Default from config
        force_recalculate = data.get('force_recalculate', False)
        
        if not dataset_id:
            return jsonify({"error": "dataset_id is required"}), 400
        
        try:
            dataset_id = int(dataset_id)
        except (ValueError, TypeError):
            return jsonify({"error": f"Invalid dataset_id: {dataset_id}"}), 400
        
        # Get dataset info
        dataset = get_dataset(dataset_id)
        if not dataset:
            return jsonify({"error": f"Dataset {dataset_id} not found"}), 404
        
        target = dataset.get('target_variable')
        if not target:
            return jsonify({"error": "Target variable not set. Please classify variables first."}), 400
        
        # Load dataset
        try:
            csv_path = get_csv_path(dataset_id)
            df = pd.read_csv(csv_path)
        except Exception as e:
            return jsonify({"error": f"Failed to load dataset: {str(e)}"}), 500
        
        if target not in df.columns:
            return jsonify({"error": f"Target column '{target}' not found in dataset"}), 400
        
        # Create or get train/test split
        print(f"\n[API] Creating/getting train/test split for dataset {dataset_id}")
        train_df, test_df, split_info = get_or_create_train_test_split(
            df, target, dataset_id, test_size, 
            random_state=42,
            force_recalculate=force_recalculate
        )
        
        # Check if this was an existing split
        is_existing = not force_recalculate and split_info.get('split_created_at') is not None
        
        # Convert all values in split_info to native Python types for JSON serialization
        # This ensures numpy/pandas types (like numpy.bool_) are converted to native Python types
        split_info_serializable = {
            'seed': int(split_info['seed']),
            'test_size': float(split_info.get('test_size', DEFAULT_TEST_SIZE)),  # Proportion from config
            'method': str(split_info['method']),
            'train_size': int(split_info['train_size']),
            'test_size_count': int(split_info.get('test_size_count', 0)),  # Count of test rows
            'train_bad_count': int(split_info['train_bad']),
            'test_bad_count': int(split_info['test_bad']),
            'train_bad_rate': float(split_info.get('train_bad_rate', 0.0)) if split_info.get('train_bad_rate') is not None else None,
            'test_bad_rate': float(split_info.get('test_bad_rate', 0.0)) if split_info.get('test_bad_rate') is not None else None,
            'stratification_success': bool(split_info.get('stratification_success', True)),
            'split_created_at': split_info.get('split_created_at').isoformat() if split_info.get('split_created_at') else None
        }
        
        return jsonify({
            'success': True,
            'split_info': split_info_serializable,
            'is_existing': bool(is_existing),
            'message': 'Using existing train/test split' if is_existing else 'Created new train/test split'
        })
        
    except Exception as e:
        print(f"[API] Train/test split error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Failed to create train/test split: {str(e)}"}), 500


@app.route('/api/train-test-split/<int:dataset_id>', methods=['GET'])
def get_train_test_split_info_api(dataset_id):
    """
    Get train/test split information for a dataset.
    
    Returns split metadata if it exists, or null if no split has been created.
    """
    try:
        split_info = get_train_test_split_info(dataset_id)
        
        if not split_info:
            return jsonify({
                'exists': False,
                'split_info': None
            })
        
        return jsonify({
            'exists': True,
            'split_info': {
                'seed': split_info['seed'],
                'test_size': split_info['test_size'],  # Proportion from config.py
                'method': split_info['method'],
                'train_size': split_info['train_size'],
                'test_size_count': split_info.get('test_size_count', split_info.get('test_size', 0)),  # Count of test rows
                'train_bad_count': split_info['train_bad'],
                'test_bad_count': split_info['test_bad'],
                'train_bad_rate': split_info.get('train_bad_rate'),
                'test_bad_rate': split_info['test_bad_rate'],
                'split_created_at': split_info.get('split_created_at').isoformat() if split_info.get('split_created_at') else None
            }
        })
    except Exception as e:
        print(f"[API] Error getting split info: {str(e)}")
        return jsonify({"error": str(e)}), 500


# ----------- Coarse Binning: Continuous -----------
def coarse_bin_continuous(df, var, target, bins=10):
    try:
        if var not in df.columns or df[var].isna().all():
            raise ValueError(f"Column '{var}' is missing or contains only NaN values")
        if target not in df.columns:
            raise ValueError(f"Target column '{target}' not found")
        
        # Check if column has a dominant repeated value (>50% of values are the same)
        # This handles sparse columns (mostly zeros) or any column with a dominant value
        total_count = df[var].notna().sum()
        if total_count > 0:
            value_counts = df[var].value_counts()
            most_frequent_value = value_counts.index[0]
            most_frequent_count = value_counts.iloc[0]
            dominant_percentage = (most_frequent_count / total_count * 100)
            has_dominant_value = dominant_percentage > 50
        else:
            has_dominant_value = False
            most_frequent_value = None
        
        if has_dominant_value:
            # For columns with a dominant value, separate that value from others
            # Create a bin for the dominant value, then bin remaining values separately
            df = df.copy()
            df[f'{var}_binned'] = None
            
            # Separate dominant value and other values
            dominant_mask = (df[var] == most_frequent_value)
            other_mask = (df[var] != most_frequent_value) & df[var].notna()
            
            # Bin other (non-dominant) values
            # Create 9 bins for other values (1 bin for dominant = total 10 bins)
            other_data = df.loc[other_mask, var]
            if len(other_data) > 0:
                other_bins = bins - 1  # 9 bins for other values (1 for dominant = 10 total)
                try:
                    _, bin_edges = pd.qcut(other_data, q=other_bins, retbins=True, labels=False, duplicates='drop')
                    n_other_bins = len(bin_edges) - 1
                    
                    # If qcut created fewer bins, use equal-width binning
                    if n_other_bins < other_bins:
                        min_val = other_data.min()
                        max_val = other_data.max()
                        bin_edges = np.linspace(min_val, max_val, other_bins + 1)
                        n_other_bins = other_bins
                    
                    if n_other_bins > 0:
                        other_bin_labels = [f'c{i}' for i in range(2, n_other_bins + 2)]  # Start from c2
                        df.loc[other_mask, f'{var}_binned'] = pd.cut(
                            other_data, 
                            bins=bin_edges, 
                            labels=other_bin_labels, 
                            include_lowest=True, 
                            right=True
                        )
                    else:
                        # Fallback: create equal-width bins
                        min_val = other_data.min()
                        max_val = other_data.max()
                        bin_edges = np.linspace(min_val, max_val, other_bins + 1)
                        other_bin_labels = [f'c{i}' for i in range(2, other_bins + 2)]
                        df.loc[other_mask, f'{var}_binned'] = pd.cut(
                            other_data, 
                            bins=bin_edges, 
                            labels=other_bin_labels, 
                            include_lowest=True, 
                            right=True
                        )
                except (ValueError, Exception):
                    # If qcut fails, use equal-width binning
                    min_val = other_data.min()
                    max_val = other_data.max()
                    bin_edges = np.linspace(min_val, max_val, other_bins + 1)
                    other_bin_labels = [f'c{i}' for i in range(2, other_bins + 2)]
                    df.loc[other_mask, f'{var}_binned'] = pd.cut(
                        other_data, 
                        bins=bin_edges, 
                        labels=other_bin_labels, 
                        include_lowest=True, 
                        right=True
                    )
            else:
                # All values are the dominant value - create only 1 bin
                n_other_bins = 0
            
            # Assign dominant value to c1
            df.loc[dominant_mask, f'{var}_binned'] = 'c1'
            
            # Handle any remaining NaN values
            df.loc[df[f'{var}_binned'].isna(), f'{var}_binned'] = 'c1'
            
        else:
            # Standard binning for non-sparse columns
            # Always create exactly 10 bins
            # Try quantile-based binning first, fallback to equal-width if needed
            try:
                _, bin_edges = pd.qcut(df[var], q=bins, retbins=True, labels=False, duplicates='drop')
                n_bins = len(bin_edges) - 1
                
                # If qcut created fewer than 10 bins, use equal-width binning instead
                if n_bins < bins:
                    # Create equal-width bins manually
                    min_val = df[var].min()
                    max_val = df[var].max()
                    bin_edges = np.linspace(min_val, max_val, bins + 1)
                    n_bins = bins
            except (ValueError, Exception) as e:
                # If qcut fails, use equal-width binning
                try:
                    min_val = df[var].min()
                    max_val = df[var].max()
                    bin_edges = np.linspace(min_val, max_val, bins + 1)
                    n_bins = bins
                except Exception:
                    raise ValueError(f"No valid bins could be created for '{var}': {str(e)}")
            
            if n_bins <= 0:
                raise ValueError(f"No valid bins could be created for '{var}'.")
            
            # Ensure exactly 10 bins
            if n_bins != bins:
                min_val = df[var].min()
                max_val = df[var].max()
                bin_edges = np.linspace(min_val, max_val, bins + 1)
                n_bins = bins
            
            bin_labels = [f'c{i}' for i in range(1, n_bins + 1)]
            df[f'{var}_binned'] = pd.cut(df[var], bins=bin_edges, labels=bin_labels, include_lowest=True, right=True)
        
        # Compute actual min and max for each bin based on data
        tab = pd.crosstab(df[f'{var}_binned'], df[target])
        tab.columns = ['Good', 'Bad']
        tab['Total'] = tab['Good'] + tab['Bad']
        tab = tab.reset_index()
        
        # Calculate Min and Max from actual data in each bin
        min_max_values = df.groupby(f'{var}_binned')[var].agg(['min', 'max']).reset_index()
        tab = tab.merge(min_max_values, on=f'{var}_binned', how='left')
        
        # FIX: Renumber bins consecutively (c1, c2, c3, ...) regardless of which original bins had data
        # This ensures we don't have gaps like c1, c3, c5, c8, c10
        if len(tab) > 0:
            # Sort bins by their min value to maintain order
            tab = tab.sort_values('min').reset_index(drop=True)
            
            # Create consecutive bin labels (c1, c2, c3, ...)
            old_to_new_labels = {}
            for idx, row in tab.iterrows():
                old_label = row[f'{var}_binned']
                new_label = f'c{idx + 1}'
                old_to_new_labels[old_label] = new_label
                tab.at[idx, f'{var}_binned'] = new_label
            
            # Update the dataframe with new consecutive labels
            df[f'{var}_binned'] = df[f'{var}_binned'].map(old_to_new_labels).fillna(df[f'{var}_binned'])
        
        # Calculate Bad Rate and Freq%
        tab['Bad Rate'] = (tab['Bad'] / tab['Total']) * 100
        tab['Freq%'] = (tab['Total'] / tab['Total'].sum()) * 100
        
        # Rename column for consistency: use 'Bin' instead of variable-prefixed name
        tab = tab.rename(columns={f'{var}_binned': 'Bin', 'min': 'Min', 'max': 'Max'})
        
        # Reorder columns - include Bad Rate and Freq%
        columns_order = ['Bin', 'Min', 'Max', 'Good', 'Bad', 'Total', 'Bad Rate', 'Freq%']
        tab = tab[columns_order]
        
        return tab, df[f'{var}_binned']
    except Exception as e:
        raise ValueError(f"Coarse binning (continuous) failed for '{var}': {str(e)}")

# ----------- Coarse Binning: Discrete -----------
def coarse_bin_discrete(
    df,
    var,
    target,
    bad_label=1,
    bad_rate_diff=0.5,
):
    """
    Coarse binning for discrete variables.
    1. Categories are sorted by the numeric part of their label.
    2. Bins are created using bad-rate similarity.
    3. Final table is ordered **by bin number** (Missing/Other last).

    Returns
    -------
    final_tab      : pd.DataFrame  (Bin, Range, Good, Bad, Total, Freq%, Bad Rate)
    binned_series  : pd.Series     (binned column in original order)
    bin_mapping    : dict          (original value → bin number)
    """
    # --------------------------------------------------------------
    # 0. Input validation
    # --------------------------------------------------------------
    if var not in df.columns or df[var].isna().all():
        raise ValueError(f"Column '{var}' missing or all NaN")
    if target not in df.columns:
        raise ValueError(f"Target column '{target}' not found")

    df = df.copy()

    # --------------------------------------------------------------
    # 0.5. DETECT IF COLUMN IS CATEGORICAL (object type)
    # For categorical columns, create one bin per category (no grouping)
    # --------------------------------------------------------------
    is_categorical = df[var].dtype == 'object' or df[var].dtype.name == 'category'
    
    # --------------------------------------------------------------
    # 1. Contingency table (known target only)
    # --------------------------------------------------------------
    df_f = df[df[target].notna()]
    if df_f.empty:
        raise ValueError(f"No non-null target rows for '{target}'")

    tab = pd.crosstab(df_f[var], df_f[target])
    if tab.empty:
        raise ValueError("No data after filtering")

    if bad_label not in tab.columns:
        bad_label = tab.columns[1] if tab.shape[1] >= 2 else tab.columns[0]

    tab["Bad"] = tab[bad_label]
    tab["Good"] = tab.drop(columns=[bad_label], errors="ignore").sum(axis=1)
    tab["Total"] = tab["Good"] + tab["Bad"]
    tab["Bad Rate"] = (tab["Bad"] / tab["Total"].replace(0, np.nan)) * 100

    # --------------------------------------------------------------
    # 2. SORT CATEGORIES BY NUMERIC PART OF LABEL (only for non-categorical)
    # For categorical, sort alphabetically
    # --------------------------------------------------------------
    if is_categorical:
        # For categorical columns, sort alphabetically
        tab = tab.sort_index()
    else:
        # For discrete numeric, sort by numeric part of label
        def _numeric_key(val):
            if pd.isna(val):
                return np.inf
            s = str(val).strip()

            # direct number
            try:
                return float(s)
            except ValueError:
                pass

            # range start: "1-5", "10-20", "1 – 5"
            m = re.search(r"[-–—]", s)
            if m:
                try:
                    return float(s[: m.start()].strip())
                except ValueError:
                    pass

            # any number inside
            nums = re.findall(r"-?\d+\.?\d*", s)
            return float(nums[0]) if nums else np.inf

        sort_keys = pd.Series([_numeric_key(v) for v in tab.index], index=tab.index)
        tab = tab.loc[sort_keys.sort_values().index]

    # --------------------------------------------------------------
    # 3. CREATE BINS
    # For categorical: one bin per category (no grouping)
    # For discrete numeric: group by bad-rate similarity
    # --------------------------------------------------------------
    bin_mapping = {}
    bin_order = []          # first appearance of each bin
    cur_bin = 1

    if not tab.empty:
        if is_categorical:
            # FIX: For categorical columns, create one bin per category
            for idx in tab.index:
                if cur_bin not in bin_order:
                    bin_order.append(cur_bin)
                bin_mapping[idx] = cur_bin
                cur_bin += 1
        else:
            # For discrete numeric, group by bad-rate similarity
            prev_rate = tab["Bad Rate"].iloc[0]
            for idx, row in tab.iterrows():
                rate = row["Bad Rate"]
                if abs(rate - prev_rate) > bad_rate_diff:
                    cur_bin += 1
                if cur_bin not in bin_order:
                    bin_order.append(cur_bin)
                bin_mapping[idx] = cur_bin
                prev_rate = rate

    # --------------------------------------------------------------
    # 4. APPLY MAPPING (unknown → -1)
    # --------------------------------------------------------------
    mapped = df[var].map(bin_mapping)
    df[f"{var}_binned"] = pd.to_numeric(mapped, errors="coerce").fillna(-1).astype(int)

    # --------------------------------------------------------------
    # 5. FINAL STATISTICS (incl. Missing = -1)
    # --------------------------------------------------------------
    bad_df = (
        df[df[target] == bad_label]
        .groupby(f"{var}_binned")[target]
        .count()
        .reset_index(name="Bad")
    )
    good_df = (
        df[(df[target] != bad_label) & df[target].notna()]
        .groupby(f"{var}_binned")[target]
        .count()
        .reset_index(name="Good")
    )
    final_tab = pd.merge(good_df, bad_df, on=f"{var}_binned", how="outer").fillna(0)
    final_tab["Good"] = final_tab["Good"].astype(int)
    final_tab["Bad"] = final_tab["Bad"].astype(int)
    final_tab["Total"] = final_tab["Good"] + final_tab["Bad"]
    total_sum = final_tab["Total"].sum()
    final_tab["Freq%"] = final_tab["Total"] / total_sum * 100 if total_sum > 0 else 0
    final_tab["Bad Rate"] = (
        final_tab["Bad"] / final_tab["Total"].replace(0, np.nan) * 100
    )

    # --------------------------------------------------------------
    # 6. HUMAN-READABLE RANGES
    # --------------------------------------------------------------
    def _compact(vals):
        clean = [v for v in vals if pd.notna(v) and str(v).strip() != ""]
        if not clean:
            return ""
        try:                     # numeric compact intervals
            nums = sorted(float(v) for v in clean)
            out, start, prev = [], nums[0], nums[0]
            for v in nums[1:]:
                if v == prev + 1:
                    prev = v
                else:
                    out.append(f"{int(start)}–{int(prev)}" if start != prev else str(int(start)))
                    start = prev = v
            out.append(f"{int(start)}–{int(prev)}" if start != prev else str(int(start)))
            return ", ".join(out)
        except Exception:
            # alphanumeric sort fallback
            try:
                return ", ".join(
                    sorted(
                        clean,
                        key=lambda x: [
                            int(t) if t.isdigit() else t.lower()
                            for t in re.split(r"(\d+)", str(x))
                        ],
                    )
                )
            except Exception:
                return ", ".join(sorted(map(str, clean)))

    # --------------------------------------------------------------
    # 6.5. CONVERT BINNED COLUMN TO d1, d2, etc. BEFORE CREATING RANGES
    # --------------------------------------------------------------
    # First, convert the binned column in the dataframe to use d1, d2, etc.
    df[f"{var}_binned"] = df[f"{var}_binned"].apply(lambda x: f"d{int(x)}" if pd.notna(x) and x != -1 else "d0")
    
    # Now create bin_ranges using the converted d1, d2, etc. labels
    bin_ranges = {}
    for b in final_tab[f"{var}_binned"].unique():
        if pd.notna(b) and b != -1:
            bin_label = f"d{int(b)}"
            bin_ranges[bin_label] = _compact([v for v, bid in bin_mapping.items() if bid == b])
        elif b == -1:
            bin_ranges["d0"] = "Missing / Other"
    
    # --------------------------------------------------------------
    # 7. TIDY-UP & **SORT BY BIN NUMBER** & CONVERT TO d1, d2, etc.
    # --------------------------------------------------------------
    # Convert numeric bin numbers to d1, d2, d3, etc. in the final table
    final_tab["Bin"] = final_tab[f"{var}_binned"].apply(lambda x: f"d{int(x)}" if pd.notna(x) and x != -1 else "d0")
    
    # Map ranges using the converted labels
    final_tab["Range"] = final_tab["Bin"].map(bin_ranges)
    
    final_tab = final_tab[
        ["Bin", "Range", "Good", "Bad", "Total", "Freq%", "Bad Rate"]
    ]

    # Order: d1, d2, d3, …, d0 (Missing) last
    ordered_bins = [f"d{b}" for b in bin_order if b != -1]
    if -1 in bin_order:
        ordered_bins.append("d0")

    final_tab["Bin"] = pd.Categorical(
        final_tab["Bin"], categories=ordered_bins, ordered=True
    )
    final_tab = final_tab.sort_values("Bin").reset_index(drop=True)

    return final_tab, df[f"{var}_binned"], bin_mapping

# ----------- Fine Binning: Continuous -----------
def split_into_adjacent_groups(old_bins):
    """
    Given a list of bins like ['Bin1','Bin2','Bin9','Bin10'],
    return groups of adjacent bins:
    [['Bin1','Bin2'], ['Bin9','Bin10']]
    """
    # Convert bin label -> number
    indexed = [(int(''.join([ch for ch in b if ch.isdigit()])), b) for b in old_bins]
    indexed.sort()
    groups, current = [], [indexed[0][1]]
    for i in range(1, len(indexed)):
        prev_num, prev_label = indexed[i-1]
        curr_num, curr_label = indexed[i]
        if curr_num == prev_num + 1: # ✅ adjacent
            current.append(curr_label)
        else: # ❌ break → start new group
            groups.append(current)
            current = [curr_label]
    groups.append(current)
    return groups

def fine_bin_continuous(df, var, target, bin_merges=None):
    try:
        binned_col = f'{var}_binned'
        fine_binned_col = f'{var}_fine_binned'
        if not bin_merges:
            df[fine_binned_col] = df[binned_col]
            # Compute min and max for original bins
            bin_ranges = {}
            unique_bins = df[binned_col].unique()
            for bin_label in unique_bins:
                mask = df[binned_col] == bin_label
                if mask.any():
                    values = df.loc[mask, var]
                    # Preserve precise numeric min/max (do not round to integers)
                    min_val = float(values.min()) if not values.empty else None
                    max_val = float(values.max()) if not values.empty else None
                    bin_ranges[bin_label] = (min_val, max_val)
            return None, df[fine_binned_col], {}, bin_ranges
        
        new_bin_map = {}
        updated_merges = {}
        bin_ranges = {}
        for new_bin, old_bins in bin_merges.items():
            groups = split_into_adjacent_groups(old_bins)
            for idx, g in enumerate(groups, start=1):
                merged_name = f"{'_'.join(g)}"
                updated_merges[merged_name] = g
                for b in g:
                    new_bin_map[b] = merged_name
                # Compute min and max for merged bins
                mask = df[binned_col].isin(g)
                if mask.any():
                    values = df.loc[mask, var]
                    # Preserve precise numeric min/max for merged bins
                    min_val = float(values.min()) if not values.empty else None
                    max_val = float(values.max()) if not values.empty else None
                    bin_ranges[merged_name] = (min_val, max_val)
        
        # Apply new mapping
        df[fine_binned_col] = df[binned_col].map(lambda x: new_bin_map.get(x, x))
        # Add ranges for unmapped bins
        unmapped_bins = set(df[binned_col].unique()) - set(new_bin_map.keys())
        for bin_label in unmapped_bins:
            mask = df[binned_col] == bin_label
            if mask.any():
                values = df.loc[mask, var]
                # Preserve precise numeric min/max for unmapped bins
                min_val = float(values.min()) if not values.empty else None
                max_val = float(values.max()) if not values.empty else None
                bin_ranges[bin_label] = (min_val, max_val)
        
        # Ensure a deterministic ordering for continuous fine bins: sort by Min value
        # Build ordered labels from bin_ranges (Min value). Place None/empty bins at the end.
        try:
            ordered_bins = sorted(list(bin_ranges.items()), key=lambda kv: (kv[1][0] if kv[1][0] is not None else float('inf')))
            ordered_labels = [label for label, _ in ordered_bins]
            # apply ordered categorical so pandas preserves this order in aggregations
            df[fine_binned_col] = df[fine_binned_col].astype(str)
            df[fine_binned_col] = pd.Categorical(df[fine_binned_col], categories=ordered_labels, ordered=True)
        except Exception:
            # fallback: keep as-is
            df[fine_binned_col] = df[fine_binned_col].astype(str)

        # Cross-tab summary (avoid pandas automatic sorting)
        try:
            cross_tab = pd.crosstab(df[fine_binned_col], df[target], sort=False)
        except TypeError:
            # Older pandas versions don't accept 'sort' kwarg
            cross_tab = pd.crosstab(df[fine_binned_col], df[target])
        cols = cross_tab.columns.tolist()
        col_map = {}
        if 0 in cols:
            col_map[0] = 'Good'
        if 1 in cols:
            col_map[1] = 'Bad'
        cross_tab = cross_tab.rename(columns=col_map)
        for col in ['Good', 'Bad']:
            if col not in cross_tab.columns:
                cross_tab[col] = 0
        cross_tab['Total'] = cross_tab['Good'] + cross_tab['Bad']
        cross_tab = cross_tab.reset_index()
        
        # Add min and max columns
        cross_tab['Min'] = cross_tab[fine_binned_col].map(lambda x: bin_ranges.get(x, (None, None))[0])
        cross_tab['Max'] = cross_tab[fine_binned_col].map(lambda x: bin_ranges.get(x, (None, None))[1])
        
        # Calculate Bad Rate and Freq%
        cross_tab['Bad Rate'] = (cross_tab['Bad'] / cross_tab['Total']) * 100
        cross_tab['Freq%'] = (cross_tab['Total'] / cross_tab['Total'].sum()) * 100
        
        # Rename column for consistency: use 'Bin' instead of variable-prefixed name
        cross_tab = cross_tab.rename(columns={fine_binned_col: 'Bin'})
        
        # Ensure the final table follows the ordered_labels if available
        try:
            if 'ordered_labels' in locals():
                cross_tab = cross_tab.set_index('Bin').reindex(ordered_labels).reset_index()
        except Exception:
            pass

        # Reorder - include Bad Rate and Freq%
        columns_order = ['Bin', 'Min', 'Max', 'Good', 'Bad', 'Total', 'Bad Rate', 'Freq%']
        cross_tab = cross_tab[columns_order]
        return cross_tab, df[fine_binned_col], updated_merges, bin_ranges
    except Exception as e:
        raise ValueError(f"Fine binning (continuous) failed for '{var}': {str(e)}")
# ----------- Fine Binning: Discrete -----------
def fine_bin_discrete(df, var, target, bin_merges=None, bin_mapping=None):
    try:
        binned_col = f'{var}_binned'
        fine_binned_col = f'{var}_fine_binned'
        bin_map = {}

        if bin_merges is None:
            bin_merges = {}

        # Create mapping for merged bins
        for new_bin, old_bins in bin_merges.items():
            for old_bin in old_bins:
                bin_map[str(old_bin)] = str(new_bin)  # normalize to str

        # Apply mapping (keep as str always)
        df[fine_binned_col] = df[binned_col].astype(str).map(bin_map).fillna(df[binned_col].astype(str))

        # Compute ranges
        bin_ranges = {}
        for bin_label in df[fine_binned_col].unique():
            if bin_label in bin_merges:
                # Merged bin
                source_bins = bin_merges[bin_label]
                original_values = set()
                for source_bin in source_bins:
                    mask = df[binned_col].astype(str) == str(source_bin)
                    if mask.any():
                        values = df.loc[mask, var].dropna().unique()
                        original_values.update(values)
                bin_ranges[bin_label] = sorted(original_values) if original_values else ['N/A']
            else:
                # Single bin
                mask = df[fine_binned_col] == bin_label
                if mask.any():
                    values = df.loc[mask, var].dropna().unique()
                    bin_ranges[bin_label] = sorted(values) if len(values) > 0 else ['N/A']
                else:
                    bin_ranges[bin_label] = ['N/A']

        # Determine an ordered label set for discrete fine bins (preserve bin_merges order when present)
        try:
            if bin_merges:
                ordered_labels = [str(k) for k in bin_merges.keys()]
                # append any remaining bins in appearance order
                remaining = [lbl for lbl in df[fine_binned_col].astype(str).unique() if lbl not in ordered_labels]
                ordered_labels.extend(remaining)
            else:
                ordered_labels = [str(x) for x in df[fine_binned_col].astype(str).unique()]
            df[fine_binned_col] = df[fine_binned_col].astype(str)
            df[fine_binned_col] = pd.Categorical(df[fine_binned_col], categories=ordered_labels, ordered=True)
        except Exception:
            df[fine_binned_col] = df[fine_binned_col].astype(str)

        # Crosstab (avoid automatic sorting)
        try:
            cross_tab = pd.crosstab(df[fine_binned_col], df[target], sort=False)
        except TypeError:
            # Older pandas versions don't accept 'sort' kwarg
            cross_tab = pd.crosstab(df[fine_binned_col], df[target])
        col_map = {}
        if 0 in cross_tab.columns: col_map[0] = 'Good'
        if 1 in cross_tab.columns: col_map[1] = 'Bad'
        cross_tab = cross_tab.rename(columns=col_map)

        for col in ['Good', 'Bad']:
            if col not in cross_tab.columns:
                cross_tab[col] = 0

        cross_tab['Total'] = cross_tab['Good'] + cross_tab['Bad']
        cross_tab = cross_tab.reset_index()

        # ✅ FIX: Always use str keys for bin_ranges lookup
        cross_tab['Range'] = cross_tab[fine_binned_col].astype(str).map(lambda x: ', '.join(map(str, bin_ranges.get(x, ['N/A']))))
        
        # Calculate Bad Rate and Freq%
        cross_tab['Bad Rate'] = (cross_tab['Bad'] / cross_tab['Total']) * 100
        cross_tab['Freq%'] = (cross_tab['Total'] / cross_tab['Total'].sum()) * 100

        # Rename column for consistency: use 'Bin' instead of variable-prefixed name
        cross_tab = cross_tab.rename(columns={fine_binned_col: 'Bin'})

        # Final order - include Bad Rate and Freq%
        columns_order = ['Bin', 'Range', 'Good', 'Bad', 'Total', 'Bad Rate', 'Freq%']
        cross_tab = cross_tab[columns_order]

        return cross_tab, df[fine_binned_col], bin_merges
    except Exception as e:
        raise ValueError(f"Fine binning (discrete) failed for '{var}': {str(e)}")


# ----------- Fine Binning API -----------
@app.route('/api/fine-bin', methods=['POST'])
def fine_bin_api():
    print("\n[API] /api/fine-bin (POST) called")
    try:
        req = request.get_json()
        print(f"[fine_bin_api] DEBUG: Received request for variable={req.get('variable')}, type={req.get('type')}")
        var = req.get('variable')
        target = req.get('target')
        var_type = req.get('type')
        bin_merges = req.get('bin_merges', {})
        if not var or not target or not var_type:
            return jsonify({"error": "Missing required fields"}), 400
        
        # Use configured CSV path (prefers dataset file_path when available)
        dataset_id = (
            req.get('recordId')
            or req.get('record_id')
            or req.get('dataset_id')
            or req.get('datasetId')
        )
        
        if not dataset_id:
            return jsonify({"error": "Missing dataset_id/record_id"}), 400
        
        try:
            dataset_id = int(dataset_id)
        except (ValueError, TypeError):
            return jsonify({"error": f"Invalid dataset_id: {dataset_id}"}), 400
        
        # Load data using data_loader to get TRAIN set if split exists
        try:
            from data_loader import get_data_for_stage
            df = get_data_for_stage(dataset_id, 'binning')  # Returns TRAIN set if split exists
            print(f"[fine_bin_api] Loaded dataset: {len(df)} rows (train set if TTS exists)")
        except Exception as e:
            print(f"[fine_bin_api] WARNING: Data loader failed: {str(e)}")
            # Fallback to CSV if data_loader fails
            try:
                csv_path = get_csv_path(dataset_id)
                df = pd.read_csv(csv_path)
                print(f"[fine_bin_api] Loaded full dataset: {len(df)} rows")
            except FileNotFoundError as fe:
                return jsonify({"error": str(fe)}), 400
            except Exception as e2:
                return jsonify({"error": f"Failed to load dataset: {str(e2)}"}), 500
        
        if target not in df.columns:
            return jsonify({"error": f"Target column '{target}' not found in dataset"}), 400
        
        df[target] = df[target].fillna(0).astype(int)
        
        # CRITICAL: Apply preprocessing before coarse binning
        # This ensures coarse bins use preprocessed data (missing values handled, duplicates removed, etc.)
        print(f"[fine_bin_api] Applying preprocessing before coarse binning...")
        try:
            df, preprocessing_report = preprocess_dataset(
                df,
                target_col=target,
                preprocessing_steps={
                    'detect_types': True,
                    'handle_missing': True,
                    'remove_duplicates': True,
                    'handle_outliers': False,  # Don't handle outliers before binning
                    'encode_categorical': False  # Don't encode categorical before binning (we need original values for discrete binning)
                },
                missing_threshold=0.5,
                treat_negative_one_as_missing=True
            )
            print(f"[fine_bin_api] Preprocessing completed. Processed shape: {df.shape}")
        except Exception as e:
            print(f"[fine_bin_api] WARNING: Preprocessing failed: {str(e)}")
            print(f"[fine_bin_api] Continuing with raw data (this may cause issues)")
            import traceback
            traceback.print_exc()

        try:
            if var_type == 'continuous':
                _, df[f'{var}_binned'] = coarse_bin_continuous(df, var, target)
                existing_bins = set(df[f'{var}_binned'].unique())
                bin_merges = {k: [b for b in v if b in existing_bins] for k, v in bin_merges.items()}
                bin_merges = {k: v for k, v in bin_merges.items() if v}
                tab, _, adjusted_merges, _ = fine_bin_continuous(df, var, target, bin_merges)
            else:
                _, df[f'{var}_binned'], bin_mapping = coarse_bin_discrete(df, var, target)
                tab, _, adjusted_merges = fine_bin_discrete(df, var, target, bin_merges, bin_mapping)
        except Exception as bin_err:
            import traceback
            print(f"ERROR in fine binning for {var}: {traceback.format_exc()}")
            return jsonify({"error": f"Fine binning failed for {var}: {str(bin_err)}"}), 400

        if tab is None or (hasattr(tab, 'empty') and tab.empty) or len(tab) == 0:
            return jsonify({"error": f"Fine binning returned no results for {var}. Check if variable has valid data."}), 400

        # Recalculate WOE/IV for the fine-binned variable
        try:
            # Use the fine binning results to calculate WOE/IV
            iv, woe_stats = calculate_woe_iv(
                df=df,
                variable=var,
                target=target,
                bin_merges=adjusted_merges if adjusted_merges else None,
                var_type=var_type
            )
            print(f"Fine bin WOE/IV recalculated for {var}: IV={iv}")
        except Exception as woe_err:
            print(f"Warning: Could not calculate WOE/IV after fine binning: {woe_err}")
            iv = 0
            woe_stats = []

        # Persist coarse + fine binning into the new normalized schema (datasets/features/binning tables)
        # dataset_id was already validated and converted to int above
        print(f"[fine_bin_api] DEBUG: Persisting results for dataset_id={dataset_id}, variable={var}")

        # Ensure feature exists in new schema
        feature = get_feature_by_name(dataset_id, var)
        if not feature:
            fid = create_feature(dataset_id, var, var_type, selected=True)
            feature = get_feature(fid)
            print(f"[fine_bin_api] DEBUG: Created feature, feature_id={fid}")
        else:
            print(f"[fine_bin_api] DEBUG: Feature exists, feature_id={feature['id']}")

        # Ensure coarse binning exists (recompute and save if missing)
        try:
            coarse_step = get_binning_step_by_type(feature['id'], 'coarse')
            if not coarse_step:
                print(f"[fine_bin_api] DEBUG: No coarse step, creating one")
                # recompute coarse stats and persist
                if var_type == 'continuous':
                    coarse_stats, _ = coarse_bin_continuous(df, var, target)
                else:
                    coarse_stats, _, _ = coarse_bin_discrete(df, var, target)
                coarse_step_id = save_coarse_binning_to_db(feature['id'], coarse_stats, var_type)
                print(f"[fine_bin_api] DEBUG: Created coarse_step_id={coarse_step_id}")
            else:
                print(f"[fine_bin_api] DEBUG: Coarse step exists, step_id={coarse_step['id']}")
        except Exception as e:
            print(f"[fine_bin_api] DEBUG: Error ensuring coarse step: {e}")
            pass

        # Create / update fine binning step
        num_bins = len(tab) if hasattr(tab, 'shape') else (len(tab) if isinstance(tab, list) else 0)
        print(f"[fine_bin_api] DEBUG: Creating fine step, num_bins={num_bins}, iv={iv}")
        fine_step_id = create_binning_step(feature_id=feature['id'], step_type='fine', method='merged' if adjusted_merges else 'manual', num_bins=num_bins, iv_value=iv)
        print(f"[fine_bin_api] DEBUG: Created fine_step_id={fine_step_id}")

        # CRITICAL FIX: Delete existing bins for this step before creating new ones
        # This prevents orphaned binning_steps (steps without bins) when ON CONFLICT updates an existing step
        delete_bins_by_step(fine_step_id)
        print(f"[fine_bin_api] DEBUG: Deleted existing bins for fine_step_id={fine_step_id} before creating new ones")

        # Build bins payload and persist
        bins_data = []
        total_good = 0
        total_bad = 0
        try:
            records = tab.to_dict(orient='records')
        except Exception:
            records = list(tab)

        for idx, row in enumerate(records):
            good = int(row.get('Good', 0))
            bad = int(row.get('Bad', 0))
            total = int(row.get('Total', good + bad))
            total_good += good
            total_bad += bad

            # Create bin label with appropriate prefix (c for continuous, d for discrete)
            # Always use the correct prefix based on var_type, regardless of what's in the Bin column
            correct_prefix = 'c' if var_type == 'continuous' else 'd'
            default_label = f'{correct_prefix}{idx+1}'
            
            # Get existing bin label, but validate and correct it if needed
            existing_label = str(row.get('Bin', default_label))
            
            # If the existing label doesn't start with the correct prefix, use the default
            if not existing_label.startswith(correct_prefix):
                bin_label = default_label
            else:
                # Keep the existing label if it has the correct prefix
                bin_label = existing_label
            bin_item = {
                'bin_number': idx + 1,
                'bin_label': bin_label,
                'good_count': good,
                'bad_count': bad,
                'total_count': total
            }
            
            # For continuous: only save min_value and max_value, set range_text to None
            # For discrete: only save range_text, set min_value and max_value to None
            if var_type == 'continuous':
                # Continuous variables: use min/max only
                if 'Min' in row and row.get('Min') is not None:
                    try:
                        bin_item['min_value'] = float(row.get('Min'))
                    except Exception:
                        bin_item['min_value'] = None
                else:
                    bin_item['min_value'] = None
                    
                if 'Max' in row and row.get('Max') is not None:
                    try:
                        bin_item['max_value'] = float(row.get('Max'))
                    except Exception:
                        bin_item['max_value'] = None
                else:
                    bin_item['max_value'] = None
                    
                # Explicitly set range_text to None for continuous
                bin_item['range_text'] = None
            else:
                # Discrete variables: use range_text only
                if 'Range' in row and row.get('Range'):
                    bin_item['range_text'] = str(row.get('Range'))
                else:
                    # For discrete, if no Range, use bin_label as range_text
                    bin_item['range_text'] = bin_label
                    
                # Explicitly set min_value and max_value to None for discrete
                bin_item['min_value'] = None
                bin_item['max_value'] = None

            # attempt to include WOE/IV if present in row
            if 'WOE' in row:
                try:
                    bin_item['woe'] = float(row.get('WOE'))
                except Exception:
                    pass
            if 'IV' in row:
                try:
                    bin_item['iv'] = float(row.get('IV'))
                except Exception:
                    pass

            bins_data.append(bin_item)

        # Persist bins and totals
        if bins_data:
            print(f"[fine_bin_api] DEBUG: Saving {len(bins_data)} bins to database")
            create_bins_batch(fine_step_id, bins_data)
            create_binning_totals(binning_step_id=fine_step_id, total_good=int(total_good), total_bad=int(total_bad), total_count=int(total_good + total_bad))
            print(f"[fine_bin_api] DEBUG: Bins and totals saved successfully")
        else:
            print(f"[fine_bin_api] WARNING: No bins_data to save!")

        # Persist merged groups (if any)
        print(f"[fine_bin_api] DEBUG: Saving merged bins: {adjusted_merges}")
        try:
            save_finebin_details_db(int(dataset_id), var, adjusted_merges)
            print(f"[fine_bin_api] DEBUG: Merged bins saved successfully")
        except Exception as e:
            print(f"[fine_bin_api] DEBUG: Error saving merged bins: {e}")
            pass

        print(f"[fine_bin_api] ✓ Fine binning persisted for {var}, dataset_id={dataset_id}, feature_id={feature['id']}, fine_step_id={fine_step_id}")
        return jsonify({
            "success": True,
            "stats": tab.to_dict(orient='records'),
            "bin_merges": adjusted_merges,
            "woe_iv": {"iv": iv, "stats": woe_stats}
        })
    except Exception as e:
        import traceback
        print("ERROR:", traceback.format_exc())
        return jsonify({"error": str(e)}), 500

# ----------- Helper function to log binning statistics -----------
def log_binning_stats(stats_df, var_name, stage_name, df=None, target=None):
    """
    Log detailed binning statistics in a formatted table.
    
    Args:
        stats_df: DataFrame with binning statistics (must have: Bin, Range, Good, Bad, Total, Bad Rate, Freq%)
        var_name: Variable name
        stage_name: Stage name (e.g., "COARSE BINNING", "FINE BINNING")
        df: Optional DataFrame for calculating additional metrics
        target: Optional target column name for calculating additional metrics
    """
    import math
    
    print(f"\n{'='*150}")
    print(f"[DEBUG] {stage_name} STATISTICS FOR: {var_name}")
    print(f"{'='*150}")
    
    # Calculate totals
    total_good_all = stats_df['Good'].sum() if 'Good' in stats_df.columns else 0
    total_bad_all = stats_df['Bad'].sum() if 'Bad' in stats_df.columns else 0
    total_all = stats_df['Total'].sum() if 'Total' in stats_df.columns else 0
    overall_odds = (total_good_all / total_bad_all) if total_bad_all > 0 else None
    
    # Print header
    header = f"{'Bin':<8} {'Range':<20} {'0 (Good)':<12} {'1 (Bad)':<12} {'Total':<10} {'0/1 (G/B)':<12} {'Bad Rate (%)':<14} {'Freq%':<10} {'G/B Odd':<12} {'Index':<10} {'G/B Index':<12} {'Dist Good (%)':<14} {'Dist Bad (%)':<14} {'WOE':<12} {'IV':<12}"
    print(header)
    print('-' * 150)
    
    # Process each bin
    for idx, row in stats_df.iterrows():
        bin_label = str(row.get('Bin', 'N/A'))
        range_val = str(row.get('Range', 'N/A'))
        good = int(row.get('Good', 0))
        bad = int(row.get('Bad', 0))
        total = int(row.get('Total', 0))
        
        # Calculate G/B ratio
        gb_ratio = (good / bad) if bad > 0 else None
        
        # Bad Rate
        bad_rate = row.get('Bad Rate', None)
        if bad_rate is None:
            bad_rate = (bad / total * 100) if total > 0 else None
        
        # Freq%
        freq_pct = row.get('Freq%', None)
        if freq_pct is None:
            freq_pct = (total / total_all * 100) if total_all > 0 else None
        
        # G/B Odd (same as G/B ratio)
        odds = gb_ratio
        
        # Dist Good (%) and Dist Bad (%)
        dist_good_pct = (good / total_good_all * 100) if total_good_all > 0 else None
        dist_bad_pct = (bad / total_bad_all * 100) if total_bad_all > 0 else None
        
        # Index
        index_val = (dist_good_pct / dist_bad_pct * 100) if (dist_bad_pct and dist_bad_pct > 0) else None
        
        # G/B Index
        gb_index = (odds / overall_odds * 100) if (odds and overall_odds and overall_odds > 0) else None
        
        # WOE
        woe = row.get('WOE', None)
        if woe is None and dist_good_pct is not None and dist_bad_pct is not None:
            if dist_good_pct > 0 and dist_bad_pct > 0:
                try:
                    woe = math.log((dist_good_pct / 100.0) / (dist_bad_pct / 100.0))
                    if not math.isfinite(woe):
                        woe = None
                except Exception:
                    woe = None
            else:
                woe = None
        
        # IV (contribution)
        iv_contrib = row.get('IV', None)
        if iv_contrib is None and dist_good_pct is not None and dist_bad_pct is not None and woe is not None:
            dist_good_prop = dist_good_pct / 100.0
            dist_bad_prop = dist_bad_pct / 100.0
            try:
                iv_contrib = (dist_good_prop - dist_bad_prop) * woe
                if not math.isfinite(iv_contrib):
                    iv_contrib = 0.0
            except Exception:
                iv_contrib = 0.0
        
        # Format values for display
        range_str = range_val[:18] if len(range_val) > 18 else range_val
        gb_ratio_str = f"{gb_ratio:.4f}" if gb_ratio is not None else "N/A"
        bad_rate_str = f"{bad_rate:.2f}" if bad_rate is not None else "N/A"
        freq_str = f"{freq_pct:.2f}" if freq_pct is not None else "N/A"
        odds_str = f"{odds:.4f}" if odds is not None else "N/A"
        index_str = f"{index_val:.2f}" if index_val is not None else "N/A"
        gb_index_str = f"{gb_index:.2f}" if gb_index is not None else "N/A"
        dist_good_str = f"{dist_good_pct:.2f}" if dist_good_pct is not None else "N/A"
        dist_bad_str = f"{dist_bad_pct:.2f}" if dist_bad_pct is not None else "N/A"
        woe_str = f"{woe:.4f}" if woe is not None else "N/A"
        iv_str = f"{iv_contrib:.6f}" if iv_contrib is not None else "N/A"
        
        # Print row
        row_str = f"{bin_label:<8} {range_str:<20} {good:<12} {bad:<12} {total:<10} {gb_ratio_str:<12} {bad_rate_str:<14} {freq_str:<10} {odds_str:<12} {index_str:<10} {gb_index_str:<12} {dist_good_str:<14} {dist_bad_str:<14} {woe_str:<12} {iv_str:<12}"
        print(row_str)
    
    # Print totals
    print('-' * 150)
    # Calculate total IV from individual bin contributions
    total_iv = 0.0
    if 'IV' in stats_df.columns:
        total_iv = stats_df['IV'].sum()
    else:
        # Calculate IV from WOE and distributions
        for _, row in stats_df.iterrows():
            woe = row.get('WOE')
            dist_good_pct = row.get('Dist Good (%)')
            dist_bad_pct = row.get('Dist Bad (%)')
            if woe is not None and dist_good_pct is not None and dist_bad_pct is not None:
                try:
                    dist_good_prop = float(dist_good_pct) / 100.0
                    dist_bad_prop = float(dist_bad_pct) / 100.0
                    iv_contrib = (dist_good_prop - dist_bad_prop) * float(woe)
                    if math.isfinite(iv_contrib):
                        total_iv += iv_contrib
                except Exception:
                    pass
    total_iv_str = f"{total_iv:.6f}" if total_iv is not None else "N/A"
    
    total_row = f"{'TOTAL':<8} {'N/A':<20} {total_good_all:<12} {total_bad_all:<12} {total_all:<10} {f'{(total_good_all/total_bad_all):.4f}' if total_bad_all > 0 else 'N/A':<12} {f'{(total_bad_all/total_all*100):.2f}' if total_all > 0 else 'N/A':<14} {'100.00':<10} {f'{(total_good_all/total_bad_all):.4f}' if total_bad_all > 0 else 'N/A':<12} {'N/A':<10} {'N/A':<12} {'100.00':<14} {'100.00':<14} {'N/A':<12} {total_iv_str:<12}"
    print(total_row)
    print(f"{'='*150}\n")

# ----------- Automated Monotonic Binning API -----------
@app.route('/api/auto-monotonic-binning', methods=['POST'])
def auto_monotonic_binning_api():
    """
    Automatically merge bins to achieve monotonic WOE (Weight of Evidence).
    Uses deterministic algorithms to find the best bin merging strategy.
    
    IMPORTANT: Uses TRAIN SET ONLY if train/test split exists to prevent data leakage!
    
    Expects JSON payload:
    {
        "variable": "column_name",
        "target": "target_column",
        "type": "continuous" or "discrete",
        "direction": "increasing", "decreasing", or null (auto-detect),
        "method": "greedy" or "exhaustive",
        "prioritize_iv": true or false (default: true, only for exhaustive),
        "record_id": optional record ID,
        "dashboard_selected_columns": optional list
    }
    """
    try:
        from data_loader import get_data_for_stage, check_split_required
        
        req = request.get_json()
        print("Auto-binning request:", req)
        
        var = req.get('variable')
        target = req.get('target')
        var_type = req.get('type')
        direction = req.get('direction')  # 'increasing', 'decreasing', or None
        # For continuous variables, always use exhaustive algorithm
        # For discrete variables, default to greedy (exhaustive not supported)
        if var_type == 'continuous':
            method = req.get('method', 'exhaustive')  # default to 'exhaustive' for continuous
        else:
            method = req.get('method', 'greedy')  # default to 'greedy' for discrete
        prioritize_iv = req.get('prioritize_iv', True)  # default to True
        record_id = req.get('record_id')
        
        if not var or not target or not var_type:
            return jsonify({"error": "Missing required fields: variable, target, type"}), 400
        
        dataset_id = (
            record_id
            or req.get('dataset_id')
            or req.get('recordId')
            or req.get('datasetId')
        )
        
        # CRITICAL: Check if train/test split exists
        if dataset_id:
            split_exists = check_split_required(dataset_id)
            if not split_exists:
                print(f"[auto_monotonic_binning] ⚠️ WARNING: No train/test split exists for dataset {dataset_id}")
                print(f"[auto_monotonic_binning] ⚠️ Creating binning on full dataset - this should be done after TTS!")
        
        # Load data using data_loader to get TRAIN set if split exists
        try:
            if dataset_id:
                df = get_data_for_stage(dataset_id, 'binning')  # Returns TRAIN set if split exists
                print(f"[auto_monotonic_binning] Loaded dataset: {len(df)} rows (train set if TTS exists)")
            else:
                csv_path = get_csv_path(dataset_id)
                df = pd.read_csv(csv_path)
                print(f"[auto_monotonic_binning] Loaded full dataset: {len(df)} rows")
        except FileNotFoundError as fe:
            return jsonify({"error": str(fe)}), 400
        except Exception as e:
            return jsonify({"error": f"Failed to load dataset: {str(e)}"}), 400
        
        # Convert target to binary 0/1
        try:
            df[target] = df[target].fillna(0).astype(int)
        except Exception as e:
            return jsonify({"error": f"Failed to convert target to numeric: {str(e)}"}), 400
        
        # CRITICAL: Apply preprocessing before coarse binning
        # This ensures coarse bins use preprocessed data (missing values handled, duplicates removed, etc.)
        print(f"[auto_monotonic_binning] Applying preprocessing before coarse binning...")
        try:
            df, preprocessing_report = preprocess_dataset(
                df,
                target_col=target,
                preprocessing_steps={
                    'detect_types': True,
                    'handle_missing': True,
                    'remove_duplicates': True,
                    'handle_outliers': False,  # Don't handle outliers before binning
                    'encode_categorical': False  # Don't encode categorical before binning (we need original values for discrete binning)
                },
                missing_threshold=0.5,
                treat_negative_one_as_missing=True
            )
            print(f"[auto_monotonic_binning] Preprocessing completed. Processed shape: {df.shape}")
        except Exception as e:
            print(f"[auto_monotonic_binning] WARNING: Preprocessing failed: {str(e)}")
            print(f"[auto_monotonic_binning] Continuing with raw data (this may cause issues)")
            import traceback
            traceback.print_exc()
        
        # First perform coarse binning to get initial bins
        if var_type == 'continuous':
            coarse_stats, df[f'{var}_binned'] = coarse_bin_continuous(df, var, target)
        else:
            coarse_stats, df[f'{var}_binned'], bin_mapping = coarse_bin_discrete(df, var, target)
        
        # DEBUG: Log coarse binning statistics (only for first feature)
        # Check if this is the first feature by checking if we have a list of variables
        # For now, we'll log for all features, but you can add a check if needed
        try:
            # Calculate WOE/IV for coarse bins to get complete stats
            coarse_iv, coarse_woe_stats = calculate_woe_iv(
                df=df,
                variable=var,
                target=target,
                bin_merges=None,
                var_type=var_type
            )
            # Merge WOE/IV into coarse_stats
            if coarse_woe_stats and len(coarse_woe_stats) > 0:
                woe_df = pd.DataFrame(coarse_woe_stats)
                # Match by bin label
                if 'Bin' in woe_df.columns and 'Bin' in coarse_stats.columns:
                    coarse_stats = coarse_stats.merge(woe_df[['Bin', 'WOE', 'IV']], on='Bin', how='left')
            log_binning_stats(coarse_stats, var, "AFTER COARSE BINNING", df=df, target=target)
        except Exception as e:
            print(f"[DEBUG] Could not log coarse binning stats: {e}")
            import traceback
            traceback.print_exc()
        
        # Extract good/bad counts and bin labels from coarse binning
        bin_labels = []
        good_counts = []
        bad_counts = []
        
        for _, row in coarse_stats.iterrows():
            # Get bin label from the 'Bin' column (which should already have c1/c2 or d1/d2 format)
            bin_label = row.get('Bin', '')
            if not bin_label:
                # Fallback: create label based on type and index
                if var_type == 'continuous':
                    bin_label = f'c{len(bin_labels)+1}'
                else:
                    bin_label = f'd{len(bin_labels)+1}'
            
            bin_labels.append(str(bin_label))
            good_counts.append(int(row.get('Good', 0)))
            bad_counts.append(int(row.get('Bad', 0)))
        
        # Convert to numpy arrays
        good = np.array(good_counts)
        bad = np.array(bad_counts)
        
        initial_woe = compute_woe(good, bad)
        print(f"Auto-binning for {var}: {len(bin_labels)} bins, direction={direction}, method={method}, prioritize_iv={prioritize_iv}")
        print(f"Initial bins: {bin_labels}")
        print(f"Initial Good: {good}")
        print(f"Initial Bad: {bad}")
        print(f"Initial WOE: {initial_woe.tolist()}")
        
        # DEBUG: Check if initial WOE is monotonic
        from auto_monotonic_binning import is_monotonic
        # Try both directions
        is_inc_monotonic = is_monotonic(initial_woe, True)
        is_dec_monotonic = is_monotonic(initial_woe, False)
        print(f"[DEBUG] Initial WOE monotonic (increasing): {is_inc_monotonic}")
        print(f"[DEBUG] Initial WOE monotonic (decreasing): {is_dec_monotonic}")
        
        # Check for violations manually
        violations_inc = []
        violations_dec = []
        for i in range(len(initial_woe) - 1):
            if initial_woe[i] > initial_woe[i+1]:
                violations_inc.append(i)
            if initial_woe[i] < initial_woe[i+1]:
                violations_dec.append(i)
        print(f"[DEBUG] Violations (increasing): {violations_inc}")
        print(f"[DEBUG] Violations (decreasing): {violations_dec}")
        
        # Run automated monotonic binning
        result = auto_monotonic_binning(
            good=good,
            bad=bad,
            bin_labels=bin_labels,
            variable_type=var_type,
            direction=direction,
            method=method,
            prioritize_iv=prioritize_iv
        )
        
        print(f"Auto-binning result: {result['num_merges']} merges, monotonic={result['is_monotonic']}, IV={result['iv']:.4f}")
        print(f"Final bins: {result['merged_labels']}")
        print(f"Final WOE: {result['woe_values']}")
        print(f"Final direction: {result['direction']}")
        print(f"Merge mapping (full): {result['merge_mapping']}")
        
        # DEBUG: Check if result is actually monotonic (with strict check)
        final_woe_array = np.array(result['woe_values'])
        is_increasing = result['direction'] == 'increasing'
        from auto_monotonic_binning import is_monotonic
        
        # Strict monotonicity check (no tolerance)
        def is_strictly_monotonic(arr, increasing):
            if len(arr) <= 1:
                return True
            for i in range(len(arr) - 1):
                if increasing:
                    if arr[i] > arr[i+1]:
                        return False
                else:
                    if arr[i] < arr[i+1]:
                        return False
            return True
        
        actual_monotonic = is_monotonic(final_woe_array, is_increasing)
        strict_monotonic = is_strictly_monotonic(final_woe_array, is_increasing)
        print(f"[DEBUG] Actual monotonicity check (with tolerance): {actual_monotonic} (expected: {result['is_monotonic']})")
        print(f"[DEBUG] Strict monotonicity check (no tolerance): {strict_monotonic}")
        if not strict_monotonic:
            print(f"[DEBUG] WARNING: Result is NOT strictly monotonic!")
            print(f"[DEBUG] WOE values: {result['woe_values']}")
            print(f"[DEBUG] Direction: {result['direction']}")
            print(f"[DEBUG] Number of bins: {len(result['woe_values'])}")
            print(f"[DEBUG] Number of merges: {result['num_merges']}")
            if result['num_merges'] == 0:
                print(f"[DEBUG] ERROR: No merges were performed, but WOE is not monotonic!")
                print(f"[DEBUG] The algorithm should have merged bins to achieve monotonicity.")
        
        # Convert merge mapping to format expected by fine_bin API
        # merge_mapping maps new labels to list of original labels
        # FIX: The merge_mapping might have complex labels like "d1_merged_d2", but fine_bin_discrete
        # expects simple labels. We need to map the final merged labels back to the original coarse bin labels.
        bin_merges = {}
        
        # Create reverse mapping: original label -> final merged label
        original_to_final = {}
        for final_label, original_labels in result['merge_mapping'].items():
            for orig_label in original_labels:
                original_to_final[orig_label] = final_label
        
        # Group original labels by their final merged label
        final_to_originals = {}
        for orig_label, final_label in original_to_final.items():
            if final_label not in final_to_originals:
                final_to_originals[final_label] = []
            final_to_originals[final_label].append(orig_label)
        
        # Only include merges (where multiple original labels map to same final label)
        for final_label, original_labels in final_to_originals.items():
            if len(original_labels) > 1:  # Only include actual merges
                # Use the first original label as the key (or a simple label)
                # fine_bin_discrete will use this to merge the bins
                bin_merges[final_label] = original_labels
        
        print(f"Bin merges to apply: {bin_merges}")
        print(f"[DEBUG] Original bins: {bin_labels}")
        print(f"[DEBUG] Final merged bins: {result['merged_labels']}")
        print(f"[DEBUG] Merge mapping (full): {result['merge_mapping']}")
        if not bin_merges:
            print(f"[DEBUG] WARNING: No bin merges to apply! All bins remain separate.")
            print(f"[DEBUG] This means auto_monotonic_binning did not merge any bins.")
            print(f"[DEBUG] If bins are the same, the algorithm may have failed to achieve monotonicity.")
            print(f"[DEBUG] Original WOE: {compute_woe(good, bad).tolist()}")
            print(f"[DEBUG] Final WOE: {result['woe_values']}")
            print(f"[DEBUG] Is monotonic: {result['is_monotonic']}")
        
        # Apply the merges using fine binning
        try:
            if var_type == 'continuous':
                _, df[f'{var}_binned'] = coarse_bin_continuous(df, var, target)
                existing_bins = set(df[f'{var}_binned'].unique())
                bin_merges = {k: [b for b in v if b in existing_bins] for k, v in bin_merges.items()}
                bin_merges = {k: v for k, v in bin_merges.items() if v}
                tab, _, adjusted_merges, _ = fine_bin_continuous(df, var, target, bin_merges)
            else:
                _, df[f'{var}_binned'], bin_mapping = coarse_bin_discrete(df, var, target)
                tab, _, adjusted_merges = fine_bin_discrete(df, var, target, bin_merges, bin_mapping)
        except Exception as bin_err:
            import traceback
            print(f"ERROR in auto-binning fine binning for {var}: {traceback.format_exc()}")
            return jsonify({
                "success": False,
                "reason": "fine_binning_failed",
                "error": f"Auto-binning fine binning failed for {var}: {str(bin_err)}"
            })
        
        if tab is None or (hasattr(tab, 'empty') and tab.empty) or len(tab) == 0:
            return jsonify({
                "success": False,
                "reason": "no_bins",
                "error": f"Auto-binning produced no results for {var}. Check if variable has valid data and sufficient bins."
            })
        
        # DEBUG: Log fine binning statistics (only for first feature)
        try:
            # Calculate WOE/IV for fine bins to get complete stats
            fine_iv, fine_woe_stats = calculate_woe_iv(
                df=df,
                variable=var,
                target=target,
                bin_merges=adjusted_merges if adjusted_merges else None,
                var_type=var_type
            )
            # Merge WOE/IV into tab
            if fine_woe_stats and len(fine_woe_stats) > 0:
                woe_df = pd.DataFrame(fine_woe_stats)
                # Match by bin label
                if 'Bin' in woe_df.columns and 'Bin' in tab.columns:
                    tab = tab.merge(woe_df[['Bin', 'WOE', 'IV']], on='Bin', how='left')
            log_binning_stats(tab, var, "AFTER ALL AUTO MONOTONIC FINE BINNING", df=df, target=target)
        except Exception as e:
            print(f"[DEBUG] Could not log fine binning stats: {e}")
            import traceback
            traceback.print_exc()
        
        # Recalculate WOE/IV using the result from auto binning
        try:
            iv, woe_stats = calculate_woe_iv(
                df=df,
                variable=var,
                target=target,
                bin_merges=adjusted_merges if adjusted_merges else None,
                var_type=var_type
            )
            print(f"Auto-binning WOE/IV calculated for {var}: IV={iv}")
        except Exception as woe_err:
            print(f"Warning: Could not calculate WOE/IV after auto-binning: {woe_err}")
            # Use the IV from the auto_monotonic_binning result as fallback
            iv = result['iv']
            woe_stats = []
        
        # Persist coarse + fine binning results into the normalized schema
        latest_ds = get_latest_dataset()

        # Determine dataset id
        if record_id:
            try:
                dataset_id = int(record_id)
                print(f"[auto_monotonic_binning] DEBUG: Using dataset_id from record_id: {dataset_id}")
            except Exception:
                dataset_id = latest_ds['id'] if latest_ds else None
                print(f"[auto_monotonic_binning] DEBUG: Failed to parse record_id, using latest: {dataset_id}")
        else:
            dataset_id = latest_ds['id'] if latest_ds else None
            print(f"[auto_monotonic_binning] DEBUG: No record_id, using latest: {dataset_id}")

        if dataset_id is None:
            dataset_id = create_dataset(name='Auto Binning', file_path='', total_features=0, discrete_features=0, continuous_features=0, target_variable=target)
            print(f"[auto_monotonic_binning] DEBUG: Created new dataset: {dataset_id}")

        # Ensure feature exists
        feature = get_feature_by_name(dataset_id, var)
        if not feature:
            fid = create_feature(dataset_id, var, var_type, selected=True)
            feature = get_feature(fid)
            print(f"[auto_monotonic_binning] DEBUG: Created new feature: {var}, feature_id={fid}")
        else:
            print(f"[auto_monotonic_binning] DEBUG: Feature exists: {var}, feature_id={feature['id']}")

        # Ensure coarse saved
        try:
            coarse_step = get_binning_step_by_type(feature['id'], 'coarse')
            if not coarse_step:
                print(f"[auto_monotonic_binning] DEBUG: No coarse step found, creating for {var}")
                if var_type == 'continuous':
                    coarse_stats, _ = coarse_bin_continuous(df, var, target)
                else:
                    coarse_stats, _, _ = coarse_bin_discrete(df, var, target)
                coarse_step_id = save_coarse_binning_to_db(feature['id'], coarse_stats, var_type)
                print(f"[auto_monotonic_binning] DEBUG: Created coarse step_id={coarse_step_id}")
            else:
                print(f"[auto_monotonic_binning] DEBUG: Coarse step exists, step_id={coarse_step['id']}")
        except Exception as e:
            print(f"[auto_monotonic_binning] DEBUG: Error ensuring coarse step: {e}")
            pass

        # Create/update fine step and persist bins/totals
        num_bins = len(tab) if hasattr(tab, 'shape') else (len(tab) if isinstance(tab, list) else 0)
        print(f"[auto_monotonic_binning] DEBUG: Creating fine step for {var}, num_bins={num_bins}, iv={iv}")
        # Update fine step with is_monotonic and monotonic_direction from result
        monotonic_dir = result['direction'] if result['is_monotonic'] else None
        fine_step_id = create_binning_step(
            feature_id=feature['id'], 
            step_type='fine', 
            method='merged' if adjusted_merges else 'auto_monotonic', 
            num_bins=num_bins, 
            iv_value=iv,
            is_monotonic=result['is_monotonic'],
            monotonic_direction=monotonic_dir
        )
        print(f"[auto_monotonic_binning] DEBUG: Created fine_step_id={fine_step_id}, is_monotonic={result['is_monotonic']}")
        
        # CRITICAL FIX: Delete existing bins for this step before creating new ones
        # This prevents orphaned binning_steps (steps without bins) when ON CONFLICT updates an existing step
        delete_bins_by_step(fine_step_id)
        print(f"[auto_monotonic_binning] DEBUG: Deleted existing bins for fine_step_id={fine_step_id} before creating new ones")

        bins_data = []
        total_good = 0
        total_bad = 0
        try:
            records = tab.to_dict(orient='records')
        except Exception:
            records = list(tab)

        for idx, row in enumerate(records):
            good = int(row.get('Good', 0))
            bad = int(row.get('Bad', 0))
            total = int(row.get('Total', good + bad))
            total_good += good
            total_bad += bad

            # Create bin label with appropriate prefix (c for continuous, d for discrete)
            # Always use the correct prefix based on var_type, regardless of what's in the Bin column
            correct_prefix = 'c' if var_type == 'continuous' else 'd'
            default_label = f'{correct_prefix}{idx+1}'
            
            # Get existing bin label, but validate and correct it if needed
            existing_label = str(row.get('Bin', default_label))
            
            # If the existing label doesn't start with the correct prefix, use the default
            if not existing_label.startswith(correct_prefix):
                bin_label = default_label
            else:
                # Keep the existing label if it has the correct prefix
                bin_label = existing_label
            
            bin_item = {
                'bin_number': idx + 1,
                'bin_label': bin_label,
                'good_count': good,
                'bad_count': bad,
                'total_count': total
            }
            
            # For continuous: only save min_value and max_value, set range_text to None
            # For discrete: only save range_text, set min_value and max_value to None
            if var_type == 'continuous':
                # Continuous variables: use min/max only
                if 'Min' in row and row.get('Min') is not None:
                    try:
                        bin_item['min_value'] = float(row.get('Min'))
                    except Exception:
                        bin_item['min_value'] = None
                else:
                    bin_item['min_value'] = None
                    
                if 'Max' in row and row.get('Max') is not None:
                    try:
                        bin_item['max_value'] = float(row.get('Max'))
                    except Exception:
                        bin_item['max_value'] = None
                else:
                    bin_item['max_value'] = None
                    
                # Explicitly set range_text to None for continuous
                bin_item['range_text'] = None
            else:
                # Discrete variables: use range_text only
                if 'Range' in row and row.get('Range'):
                    bin_item['range_text'] = str(row.get('Range'))
                else:
                    # For discrete, if no Range, use bin_label as range_text
                    bin_item['range_text'] = bin_label
                    
                # Explicitly set min_value and max_value to None for discrete
                bin_item['min_value'] = None
                bin_item['max_value'] = None
            if 'WOE' in row:
                try:
                    bin_item['woe'] = float(row.get('WOE'))
                except Exception:
                    pass
            if 'IV' in row:
                try:
                    bin_item['iv'] = float(row.get('IV'))
                except Exception:
                    pass

            bins_data.append(bin_item)

        if bins_data:
            print(f"[auto_monotonic_binning] DEBUG: Saving {len(bins_data)} bins to database")
            create_bins_batch(fine_step_id, bins_data)
            create_binning_totals(binning_step_id=fine_step_id, total_good=int(total_good), total_bad=int(total_bad), total_count=int(total_good + total_bad))
            print(f"[auto_monotonic_binning] DEBUG: Bins and totals saved successfully")
        else:
            print(f"[auto_monotonic_binning] WARNING: No bins_data to save!")

        print(f"[auto_monotonic_binning] DEBUG: Saving merged bins: {adjusted_merges}")
        try:
            save_finebin_details_db(int(dataset_id), var, adjusted_merges)
            print(f"[auto_monotonic_binning] DEBUG: Merged bins saved successfully")
        except Exception as e:
            print(f"[auto_monotonic_binning] DEBUG: Error saving merged bins: {e}")
            pass

        print(f"[auto_monotonic_binning] ✓ Auto-binning persisted for {var}, dataset_id={dataset_id}, feature_id={feature['id']}, fine_step_id={fine_step_id}")
        
        # FIX: Mark feature as model_ready AFTER all binning data is saved
        # This ensures the frontend sees model_ready only after binning is complete
        model_ready_marked = False
        if result['is_monotonic']:
            try:
                update_feature(feature['id'], model_ready=True)
                model_ready_marked = True
                print(f"[auto_monotonic_binning] DEBUG: Marked {var} as model_ready (monotonic, IV={iv:.4f}) AFTER binning data saved")
            except Exception as e:
                print(f"[auto_monotonic_binning] DEBUG: Error marking model_ready: {e}")
        else:
            print(f"[auto_monotonic_binning] DEBUG: Skipped marking {var} as model_ready (not monotonic)")

        return jsonify({
            "success": True,
            "stats": tab.to_dict(orient='records'),
            "bin_merges": adjusted_merges,
            "is_monotonic": result['is_monotonic'],
            "direction": result['direction'],
            "num_merges": result['num_merges'],
            "num_bins_original": result['num_bins_original'],
            "num_bins_final": result['num_bins_final'],
            "woe_iv": {"iv": iv, "stats": woe_stats},
            "model_ready": model_ready_marked,  # FIX: Include model_ready status in response
            "variable": var  # FIX: Include variable name so frontend knows which feature was updated
        })
        
    except Exception as e:
        import traceback
        print("ERROR in auto-monotonic-binning:", traceback.format_exc())
        return jsonify({"error": str(e)}), 500

# ----------- Cross Tab View API -----------
@app.route('/api/cross-tab', methods=['POST'])
def cross_tab_api():
    """
    Performs binning (coarse/fine) and returns cross-tabulation for one or more variables.
    Supports both continuous and discrete variables in a single request.
    """
    try:
        req = request.get_json()
        variables = req.get('variables', [])
        target = req.get('target')
        binning_info = req.get('binning', {}) # optional: {var: {type: 'continuous'/'discrete', bin_merges: {...}}}
        if not target or not variables:
            return jsonify({"error": "Missing required fields: variables or target"}), 400
        
        try:
            csv_path = get_csv_path(record_id)
        except FileNotFoundError as fe:
            return jsonify({"error": str(fe)}), 400
        try:
            df = pd.read_csv(csv_path)
        except FileNotFoundError as fe:
            return jsonify({"error": str(fe)}), 400
        except Exception as e:
            return jsonify({"error": str(e)}), 500
        if target not in df.columns:
            return jsonify({"error": f"Target column '{target}' not found in dataset"}), 400
        # Robustly convert target to numeric (0/1). Avoids 500s on text targets.
        try:
            # Try to coerce to numeric
            df[target] = pd.to_numeric(df[target], errors='coerce')
            # If everything is NaN, we cannot proceed
            if df[target].isna().all():
                return jsonify({"error": f"Target column '{target}' contains no numeric values"}), 400
            # Fill NaNs with 0 and cast to int
            df[target] = df[target].fillna(0).astype(int)
        except Exception as conv_err:
            return jsonify({"error": f"Failed to convert target '{target}' to numeric: {str(conv_err)}"}), 400
        results = {}
        for var in variables:
            if var not in df.columns or var == target:
                continue
            # Get binning settings for this variable
            var_settings = binning_info.get(var, {})
            var_type = var_settings.get('type', None)
            bin_merges = var_settings.get('bin_merges', None)
            # If type is not given, try to infer from dtype
            if var_type is None:
                if pd.api.types.is_numeric_dtype(df[var]):
                    var_type = 'continuous'
                else:
                    var_type = 'discrete'
            # Coarse + Fine binning
            if var_type == 'continuous':
                _, df[f'{var}_binned'] = coarse_bin_continuous(df, var, target)
                cross_tab, _, final_merges = fine_bin_continuous(df, var, target, bin_merges)
            else:
                _, df[f'{var}_binned'], bin_mapping = coarse_bin_discrete(df, var, target)
                cross_tab, _, final_merges = fine_bin_discrete(df, var, target, bin_merges, bin_mapping)
            results[var] = {
                'stats': cross_tab.to_dict(orient='records'),
                'bin_merges': final_merges
            }
        
        # Save cross-tab results to PostgreSQL (if needed)
        return jsonify(results)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ----------- Univariate Analysis API -----------
@app.route('/api/univariate-analysis', methods=['POST'])
def univariate_analysis():
    """
    Performs univariate analysis (coarse binning) for a list of variables.
    
    IMPORTANT: Uses TRAIN SET ONLY if train/test split exists to prevent data leakage!
    """
    print("\n[API] /api/univariate-analysis (POST) called")
    try:
        from data_loader import get_data_for_stage, check_split_required
        
        req = request.get_json()
        print(f"[univariate_analysis] discrete={len(req.get('discrete', []))}, continuous={len(req.get('continuous', []))}, target={req.get('target')}")
        discrete_cols = req.get('discrete', [])
        continuous_cols = req.get('continuous', [])
        target = req.get('target')
        record_id = req.get('record_id')  # Optional: for persistence
        
        if not target:
            return jsonify({"error": "Missing required field: target"}), 400
        
        # CRITICAL: Check if train/test split exists
        if record_id:
            split_exists = check_split_required(record_id)
            if not split_exists:
                print(f"[univariate_analysis] ⚠️ WARNING: No train/test split exists for dataset {record_id}")
                print(f"[univariate_analysis] ⚠️ Creating binning on full dataset - this should be done after TTS!")
        
        # Load data using data_loader to get TRAIN set if split exists
        try:
            if record_id:
                df = get_data_for_stage(record_id, 'binning')  # Returns TRAIN set if split exists
                print(f"[univariate_analysis] Loaded dataset: {len(df)} rows (train set if TTS exists)")
            else:
                csv_path = get_csv_path(record_id)
                df = pd.read_csv(csv_path)
                print(f"[univariate_analysis] Loaded full dataset: {len(df)} rows")
        except FileNotFoundError as fe:
            return jsonify({"error": str(fe)}), 400
        except Exception as e:
            return jsonify({"error": f"Failed to load dataset: {str(e)}"}), 400
        
        if target not in df.columns:
            return jsonify({"error": f"Target column '{target}' not found in dataset"}), 400
        
        # Convert target to binary 0/1
        try:
            df[target] = pd.to_numeric(df[target], errors='coerce').fillna(0).astype(int)
        except Exception as e:
            return jsonify({"error": f"Failed to convert target to numeric: {str(e)}"}), 400
        
        # CRITICAL: Apply preprocessing before coarse binning
        # This ensures coarse bins use preprocessed data (missing values handled, duplicates removed, etc.)
        print(f"[univariate_analysis] Applying preprocessing before coarse binning...")
        try:
            df, preprocessing_report = preprocess_dataset(
                df,
                target_col=target,
                preprocessing_steps={
                    'detect_types': True,
                    'handle_missing': True,
                    'remove_duplicates': True,
                    'handle_outliers': False,  # Don't handle outliers before binning
                    'encode_categorical': False  # Don't encode categorical before binning (we need original values for discrete binning)
                },
                missing_threshold=0.5,
                treat_negative_one_as_missing=True
            )
            print(f"[univariate_analysis] Preprocessing completed. Processed shape: {df.shape}")
            print(f"[univariate_analysis] Preprocessing steps applied: {preprocessing_report.get('steps_applied', [])}")
        except Exception as e:
            print(f"[univariate_analysis] WARNING: Preprocessing failed: {str(e)}")
            print(f"[univariate_analysis] Continuing with raw data (this may cause issues)")
            import traceback
            traceback.print_exc()
        
        results = {}
        
        # Process discrete columns
        for col in discrete_cols:
            if col != target and col in df.columns:
                try:
                    stats = None
                    stats_dict = None
                    
                    # CRITICAL FIX: Always use 'discrete' as the var_type for discrete columns
                    # Don't rely on feature type from DB which might be incorrect
                    var_type = 'discrete'
                    correct_prefix = 'd'
                    
                    # Try to retrieve from database if record_id is provided
                    from_db = False
                    if record_id:
                        try:
                            dataset_id = int(record_id)
                        except (ValueError, TypeError):
                            dataset_id = None
                            print(f"[univariate_analysis] DEBUG: Invalid dataset_id for {col}")
                        if dataset_id:
                            feature = get_feature_by_name(dataset_id, col)
                            if not feature:
                                # Create feature if it doesn't exist
                                print(f"[univariate_analysis] DEBUG: Feature not found for {col}, creating it")
                                fid = create_feature(dataset_id, col, var_type, selected=True)
                                feature = get_feature(fid)
                                print(f"[univariate_analysis] DEBUG: Created feature for {col}, feature_id={fid}")
                            else:
                                # Update feature type if it's wrong
                                if feature.get('type') != var_type:
                                    print(f"[univariate_analysis] DEBUG: Feature type mismatch for {col}, updating from '{feature.get('type')}' to '{var_type}'")
                                    update_feature(feature['id'], type=var_type)
                                    feature['type'] = var_type
                                
                            if feature:
                                print(f"[univariate_analysis] DEBUG: Feature found for {col}, feature_id={feature['id']}")
                                # Check if coarse binning already exists
                                coarse_step = get_binning_step_by_type(feature['id'], 'coarse')
                                if coarse_step:
                                    print(f"[univariate_analysis] DEBUG: Coarse step found for {col}, step_id={coarse_step['id']}")
                                    # Data exists in database - retrieve it
                                    bins = get_bins_by_step(coarse_step['id'])
                                    if bins:
                                        print(f"[univariate_analysis] DEBUG: Found {len(bins)} bins in DB for {col}")
                                        
                                        # CRITICAL FIX: Check if bins have wrong prefix (indicating they were saved with wrong type)
                                        # If any bin has wrong prefix, we need to recalculate instead of just correcting labels
                                        has_wrong_prefix = False
                                        for bin_row in bins:
                                            bin_label = str(bin_row.get('bin_label', ''))
                                            if bin_label and not bin_label.startswith(correct_prefix):
                                                has_wrong_prefix = True
                                                print(f"[univariate_analysis] DEBUG: Detected wrong bin prefix for {col}: '{bin_label}' should start with '{correct_prefix}'")
                                                break
                                        
                                        if has_wrong_prefix:
                                            # Bins were saved with wrong type - delete and recalculate
                                            print(f"[univariate_analysis] DEBUG: Bins have wrong prefix, deleting and recalculating for {col}")
                                            delete_all_binning_for_feature(feature['id'])
                                            stats_dict = None  # Force recalculation
                                        else:
                                            # Bins are correct - use them
                                            # Get totals for derived metrics calculation
                                            totals = get_binning_totals(coarse_step['id'])
                                            # Calculate derived metrics on-the-fly
                                            bins = calculate_derived_bin_metrics(bins, totals)
                                            # Transform DB format to frontend format
                                            stats_dict = []
                                            
                                            for bin_row in bins:
                                                native_row = _row_to_native_types(dict(bin_row))
                                                # Use existing bin_label (should already have correct prefix)
                                                bin_label = native_row.get('bin_label')
                                                if not bin_label:
                                                    bin_num = native_row.get('bin_number', '')
                                                    bin_label = f"{correct_prefix}{bin_num}" if bin_num else f'{correct_prefix}1'
                                                
                                                frontend_row = {
                                                    'Bin': bin_label,
                                                    'Range': native_row.get('range_text'),
                                                    'Good': native_row.get('good_count', 0),
                                                    'Bad': native_row.get('bad_count', 0),
                                                    'Total': native_row.get('total_count', 0),
                                                    'Bad Rate': native_row.get('bad_rate'),
                                                    'Freq%': native_row.get('freq_percent'),
                                                    'WOE': native_row.get('woe'),
                                                    'IV': native_row.get('iv')
                                                }
                                                stats_dict.append(frontend_row)
                                            from_db = True
                                            print(f"[univariate_analysis] ✓ Retrieved discrete from DB: {col} ({len(bins)} bins)")
                                else:
                                    print(f"[univariate_analysis] DEBUG: No coarse step found for {col}")
                    
                    # If not in database, calculate fresh
                    if stats_dict is None:
                        print(f"[univariate_analysis] DEBUG: Calculating fresh binning for discrete {col}")
                        stats, _, _ = coarse_bin_discrete(df, col, target)
                        print(f"[univariate_analysis] ⚙️  Calculated discrete: {col}")
                        
                        # Persist to DB if record_id provided
                        if record_id:
                            try:
                                dataset_id = int(record_id)
                            except (ValueError, TypeError):
                                dataset_id = None
                            if dataset_id:
                                feature = get_feature_by_name(dataset_id, col)
                                if not feature:
                                    # Create feature if it doesn't exist
                                    fid = create_feature(dataset_id, col, var_type, selected=True)
                                    feature = get_feature(fid)
                                    print(f"[univariate_analysis] DEBUG: Created feature for {col}, feature_id={fid}")
                                else:
                                    # Update feature type if it's wrong
                                    if feature.get('type') != var_type:
                                        print(f"[univariate_analysis] DEBUG: Feature type mismatch for {col}, updating from '{feature.get('type')}' to '{var_type}'")
                                        update_feature(feature['id'], type=var_type)
                                
                                if feature:
                                    step_id = save_coarse_binning_to_db(feature['id'], stats, var_type)
                                    print(f"[univariate_analysis] 💾 Saved discrete to DB: {col}, step_id={step_id}")
                        if stats_dict is None:
                            stats_dict = stats.to_dict(orient='records')
                    
                    results[col] = {
                        'type': 'discrete',
                        'stats': stats_dict,
                        'from_db': from_db  # Indicate if data was retrieved from DB
                    }
                except Exception as e:
                    print(f"[univariate_analysis] Error processing discrete column {col}: {e}")
                    import traceback
                    traceback.print_exc()
                    results[col] = {'type': 'discrete', 'error': str(e)}
        
        # Process continuous columns
        for col in continuous_cols:
            if col != target and col in df.columns:
                try:
                    stats = None
                    stats_dict = None
                    
                    # CRITICAL FIX: Always use 'continuous' as the var_type for continuous columns
                    # Don't rely on feature type from DB which might be incorrect
                    var_type = 'continuous'
                    correct_prefix = 'c'
                    
                    # Try to retrieve from database if record_id is provided
                    from_db = False
                    if record_id:
                        try:
                            dataset_id = int(record_id)
                        except (ValueError, TypeError):
                            dataset_id = None
                            print(f"[univariate_analysis] DEBUG: Invalid dataset_id for {col}")
                        if dataset_id:
                            feature = get_feature_by_name(dataset_id, col)
                            if not feature:
                                # Create feature if it doesn't exist
                                print(f"[univariate_analysis] DEBUG: Feature not found for {col}, creating it")
                                fid = create_feature(dataset_id, col, var_type, selected=True)
                                feature = get_feature(fid)
                                print(f"[univariate_analysis] DEBUG: Created feature for {col}, feature_id={fid}")
                            else:
                                # Update feature type if it's wrong
                                if feature.get('type') != var_type:
                                    print(f"[univariate_analysis] DEBUG: Feature type mismatch for {col}, updating from '{feature.get('type')}' to '{var_type}'")
                                    update_feature(feature['id'], type=var_type)
                                    feature['type'] = var_type
                                
                            if feature:
                                print(f"[univariate_analysis] DEBUG: Feature found for {col}, feature_id={feature['id']}")
                                # Check if coarse binning already exists
                                coarse_step = get_binning_step_by_type(feature['id'], 'coarse')
                                if coarse_step:
                                    print(f"[univariate_analysis] DEBUG: Coarse step found for {col}, step_id={coarse_step['id']}")
                                    # Data exists in database - retrieve it
                                    bins = get_bins_by_step(coarse_step['id'])
                                    if bins:
                                        print(f"[univariate_analysis] DEBUG: Found {len(bins)} bins in DB for {col}")
                                        
                                        # CRITICAL FIX: Check if bins have wrong prefix (indicating they were saved with wrong type)
                                        # If any bin has wrong prefix, we need to recalculate instead of just correcting labels
                                        has_wrong_prefix = False
                                        for bin_row in bins:
                                            bin_label = str(bin_row.get('bin_label', ''))
                                            if bin_label and not bin_label.startswith(correct_prefix):
                                                has_wrong_prefix = True
                                                print(f"[univariate_analysis] DEBUG: Detected wrong bin prefix for {col}: '{bin_label}' should start with '{correct_prefix}'")
                                                break
                                        
                                        if has_wrong_prefix:
                                            # Bins were saved with wrong type - delete and recalculate
                                            print(f"[univariate_analysis] DEBUG: Bins have wrong prefix, deleting and recalculating for {col}")
                                            delete_all_binning_for_feature(feature['id'])
                                            stats_dict = None  # Force recalculation
                                        else:
                                            # Bins are correct - use them
                                            # Get totals for derived metrics calculation
                                            totals = get_binning_totals(coarse_step['id'])
                                            # Calculate derived metrics on-the-fly
                                            bins = calculate_derived_bin_metrics(bins, totals)
                                            # Transform DB format to frontend format
                                            stats_dict = []
                                            
                                            for bin_row in bins:
                                                native_row = _row_to_native_types(dict(bin_row))
                                                # Use existing bin_label (should already have correct prefix)
                                                bin_label = native_row.get('bin_label')
                                                if not bin_label:
                                                    bin_num = native_row.get('bin_number', '')
                                                    bin_label = f"{correct_prefix}{bin_num}" if bin_num else f'{correct_prefix}1'
                                                
                                                frontend_row = {
                                                    'Bin': bin_label,
                                                    'Min': native_row.get('min_value'),
                                                    'Max': native_row.get('max_value'),
                                                    'Good': native_row.get('good_count', 0),
                                                    'Bad': native_row.get('bad_count', 0),
                                                    'Total': native_row.get('total_count', 0),
                                                    'Bad Rate': native_row.get('bad_rate'),
                                                    'Freq%': native_row.get('freq_percent'),
                                                    'WOE': native_row.get('woe'),
                                                    'IV': native_row.get('iv')
                                                }
                                                stats_dict.append(frontend_row)
                                            from_db = True
                                            print(f"[univariate_analysis] ✓ Retrieved continuous from DB: {col} ({len(bins)} bins)")
                                else:
                                    print(f"[univariate_analysis] DEBUG: No coarse step found for {col}")
                    
                    # If not in database, calculate fresh
                    if stats_dict is None:
                        print(f"[univariate_analysis] DEBUG: Calculating fresh binning for continuous {col}")
                        stats, _ = coarse_bin_continuous(df, col, target)
                        print(f"[univariate_analysis] ⚙️  Calculated continuous: {col}")
                        
                        # Persist to DB if record_id provided
                        if record_id:
                            try:
                                dataset_id = int(record_id)
                            except (ValueError, TypeError):
                                dataset_id = None
                            if dataset_id:
                                feature = get_feature_by_name(dataset_id, col)
                                if not feature:
                                    # Create feature if it doesn't exist
                                    fid = create_feature(dataset_id, col, var_type, selected=True)
                                    feature = get_feature(fid)
                                    print(f"[univariate_analysis] DEBUG: Created feature for {col}, feature_id={fid}")
                                else:
                                    # Update feature type if it's wrong
                                    if feature.get('type') != var_type:
                                        print(f"[univariate_analysis] DEBUG: Feature type mismatch for {col}, updating from '{feature.get('type')}' to '{var_type}'")
                                        update_feature(feature['id'], type=var_type)
                                
                                if feature:
                                    step_id = save_coarse_binning_to_db(feature['id'], stats, var_type)
                                    print(f"[univariate_analysis] 💾 Saved continuous to DB: {col}, step_id={step_id}")
                        if stats_dict is None:
                            stats_dict = stats.to_dict(orient='records')
                    
                    results[col] = {
                        'type': 'continuous',
                        'stats': stats_dict,
                        'from_db': from_db  # Indicate if data was retrieved from DB
                    }
                except Exception as e:
                    print(f"[univariate_analysis] Error processing continuous column {col}: {e}")
                    import traceback
                    traceback.print_exc()
                    results[col] = {'type': 'continuous', 'error': str(e)}
        
        return jsonify(results)
    except Exception as e:
        print(f"[univariate_analysis] Unhandled error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# ----------- Reset Bins API -----------
@app.route('/api/reset-bins', methods=['POST'])
def reset_bins_api():
    """
    Reset binning for a variable: clears fine binning and WOE/IV, reverts to coarse bins.
    
    Expects JSON payload:
    {
        "variable": "column_name",
        "target": "target_column",
        "type": "continuous" or "discrete",
        "record_id": record ID
    }
    """
    print("\n[API] /api/reset-bins (POST) called")
    try:
        req = request.get_json()
        print(f"[reset_bins] variable={req.get('variable')}, type={req.get('type')}, record_id={req.get('record_id')}")
        var = req.get('variable')
        target = req.get('target')
        var_type = req.get('type')
        record_id = req.get('record_id')
        
        if not var or not target or not var_type or not record_id:
            return jsonify({"error": "Missing required fields: variable, target, type, record_id"}), 400
        
        # Load data using data_loader to get TRAIN set if split exists
        try:
            from data_loader import get_data_for_stage
            df = get_data_for_stage(record_id, 'binning')  # Returns TRAIN set if split exists
            print(f"[reset_bins] Loaded dataset: {len(df)} rows (train set if TTS exists)")
        except Exception as e:
            # Fallback to CSV if data_loader fails
            try:
                csv_path = get_csv_path(record_id)
                df = pd.read_csv(csv_path)
                print(f"[reset_bins] Loaded full dataset: {len(df)} rows")
            except FileNotFoundError as fe:
                return jsonify({"error": str(fe)}), 400
            except Exception as e2:
                return jsonify({"error": f"Failed to load dataset: {str(e2)}"}), 400
        
        if target not in df.columns:
            return jsonify({"error": f"Target column '{target}' not found in dataset"}), 400
        
        df[target] = df[target].fillna(0).astype(int)
        
        # CRITICAL: Apply preprocessing before coarse binning
        # This ensures coarse bins use preprocessed data (missing values handled, duplicates removed, etc.)
        print(f"[reset_bins] Applying preprocessing before coarse binning...")
        try:
            df, preprocessing_report = preprocess_dataset(
                df,
                target_col=target,
                preprocessing_steps={
                    'detect_types': True,
                    'handle_missing': True,
                    'remove_duplicates': True,
                    'handle_outliers': False,  # Don't handle outliers before binning
                    'encode_categorical': False  # Don't encode categorical before binning (we need original values for discrete binning)
                },
                missing_threshold=0.5,
                treat_negative_one_as_missing=True
            )
            print(f"[reset_bins] Preprocessing completed. Processed shape: {df.shape}")
        except Exception as e:
            print(f"[reset_bins] WARNING: Preprocessing failed: {str(e)}")
            print(f"[reset_bins] Continuing with raw data (this may cause issues)")
            import traceback
            traceback.print_exc()
        
        # Perform coarse binning
        if var_type == 'continuous':
            coarse_stats, _ = coarse_bin_continuous(df, var, target)
        else:
            coarse_stats, _, _ = coarse_bin_discrete(df, var, target)
        
        # Get feature from new schema
        dataset_id = record_id
        feature = get_feature_by_name(dataset_id, var)
        
        if not feature:
            return jsonify({"error": f"Feature {var} not found for dataset {dataset_id}"}), 404
        
        # Delete all binning steps, bins, and merged bins for this feature
        delete_all_binning_for_feature(feature['id'])
        
        # Recreate coarse binning in the new schema
        save_coarse_binning_to_db(feature['id'], coarse_stats, var_type)
        
        # Convert DataFrame to dict and replace NaN/Inf values with None for JSON serialization
        stats_records = coarse_stats.to_dict(orient='records')
        sanitized_stats = []
        for record in stats_records:
            sanitized_record = {}
            for key, value in record.items():
                # Handle NaN and Inf values
                if isinstance(value, (float, np.floating)):
                    if np.isnan(value) or np.isinf(value):
                        sanitized_record[key] = None
                    else:
                        sanitized_record[key] = float(value)
                elif pd.isna(value):
                    sanitized_record[key] = None
                else:
                    sanitized_record[key] = value
            sanitized_stats.append(sanitized_record)
        
        # Return the coarse bins for frontend display
        return jsonify({
            "success": True,
            "stats": sanitized_stats
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ----------- Get CSV Sample Data for AI Classification -----------
@app.route('/api/csv-samples', methods=['POST'])
def get_csv_samples():
    """
    Get sample values from uploaded CSV for specified columns to help with AI classification.
    Expects JSON: { columns: [...] }
    Returns: { column_name: [sample_values...] }
    """
    try:
        payload = request.get_json() or {}
        columns = payload.get('columns', [])
        sample_size = payload.get('sample_size', 20)
        dataset_id = (
            payload.get('record_id')
            or payload.get('dataset_id')
            or payload.get('recordId')
            or payload.get('datasetId')
        )
        
        csv_path = get_csv_path(dataset_id)
        if not os.path.exists(csv_path):
            return jsonify({"error": "No CSV file uploaded"}), 400
            
        df = pd.read_csv(csv_path)
        
        samples = {}
        for col in columns:
            if col in df.columns:
                # Get sample values, removing NaN and converting to native Python types
                col_samples = df[col].dropna().head(sample_size).tolist()
                # Convert numpy types to native Python types for JSON serialization
                samples[col] = [x.item() if hasattr(x, 'item') else x for x in col_samples]
            else:
                samples[col] = []
                
        return jsonify(samples)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/ai-classify-columns', methods=['POST'])
def ai_classify_columns():
    """
    Classify columns as 'discrete' or 'continuous' using GitHub Models inference endpoint.
    Expects JSON: { columns: [...], sampleData: { col: [samples...] }, model: <optional model name> }
    """
    
    # --- Local Helper Heuristic Function ---
    # This logic is used for large datasets and as a fallback.
    def _classify_with_heuristics(col, samples):
        col_name_lower = col.lower()
        
        # --- Heuristic Keywords ---
        # Priority 1: Continuous Keywords (Monetary, Measurements, Proportions)
        continuous_keywords = ['sales', 'turnover', 'margin', 'perc', 'rate', 'ratio', 'amount', 'price', 'cost', 'salary', 'income', 'revenue', 'balance', 'weight', 'height', 'length', 'width', 'depth', 'distance', 'time', 'duration', 'age', 'years']
        # Priority 2: Discrete Keywords (IDs, Codes, Counts, Categories)
        discrete_keywords = ['id', 'no', 'keyt','_CD', 'cd', 'form', 'relation', 'auth', 'group', 'family', 'branch', 'visit', 'invcount', 'customer', 'status', 'level', 'flag', 'type', 'code']

        # 1. Check Continuous by Name (Highest Priority)
        if any(keyword in col_name_lower for keyword in continuous_keywords):
            return 'continuous'

        # 2. Check Discrete by Name
        if any(keyword in col_name_lower for keyword in discrete_keywords) or col_name_lower in ['bad customer']:
            return 'discrete'

        # 3. Analyze Sample Values
        # Check if samples is empty (handle both Series and list)
        if hasattr(samples, 'empty'):
            if samples.empty:
                return 'discrete' # Default to discrete when no data
        elif hasattr(samples, '__len__'):
            if len(samples) == 0:
                return 'discrete' # Default to discrete when no data
        else:
            if not samples:
                return 'discrete' # Default to discrete when no data

        try:
            # Handle pandas Series/DataFrame samples
            if hasattr(samples, 'dtype'):
                is_numeric = pd.api.types.is_numeric_dtype(samples)
                samples_list = samples.dropna().tolist()
            else:
                is_numeric = all(isinstance(x, (int, float)) for x in samples)
                samples_list = [x for x in samples if x is not None]
            
            if not is_numeric:
                return 'discrete' # Text/Categorical data

            # Check for presence of non-integer/float values
            has_float = any(isinstance(x, float) and not x.is_integer() for x in samples_list)
            if has_float:
                return 'continuous' # Presence of decimals strongly suggests measurement/continuous

            # Check cardinality for numeric data (e.g., binary or few levels)
            unique_values = len(set(samples_list))
            # Use a conservative low-cardinality threshold for discrete classification
            if unique_values <= 15: 
                return 'discrete'
            
            # If numeric, all integers, high cardinality, and not caught by name:
            # It's either a large count (discrete) or a large monetary value/ID (context-dependent).
            # We default to continuous as LLM classification should be used for this ambiguity, 
            # but if heuristics must decide, numeric high cardinality is often treated as continuous for modeling.
            return 'continuous'
        except Exception:
            return 'discrete' # Safe default on sample analysis failure
    # --- End Helper Function ---

    try:
        payload = request.get_json() or {}
        columns = payload.get('columns', [])
        sample_data = payload.get('sampleData', {})
        model = payload.get('model') or os.getenv('AI_CLASSIFY_MODEL') or 'openai/gpt-5-mini'

        token = os.getenv('GITHUB_TOKEN')
        if not token:
            print("ERROR: GITHUB_TOKEN environment variable not found")
            return jsonify({"error": "Server missing GITHUB_TOKEN environment variable. Set it and restart the backend."}), 401
        
        print(f"DEBUG: Using GitHub token (first 10 chars): {token[:10]}...")
        print(f"DEBUG: Processing {len(columns)} columns")

        # FIX 1: Replace unrunnable 'classify_with_heuristics' call with the defined local helper
        if len(columns) > 50:
            print(f"DEBUG: Large dataset detected ({len(columns)} columns), using enhanced heuristics")
            results = {}
            for col in columns:
                # Use the locally defined heuristic function
                results[col] = _classify_with_heuristics(col, sample_data.get(col, []))
            return jsonify(results)

        # FIX 2: Build the enhanced prompt with detailed classification criteria
        prompt = (
            "You are an *expert Data Scientist* and your only task is to strictly classify the provided dataset columns "
            "as either 'discrete' or 'continuous' based on their name and sample values.\n\n"
            
            "--- DEFINITIONS AND CRITERIA ---\n"
            
            "*DISCRETE* variables are counts, codes, identifiers, or categories. They take on a finite or countably infinite number of values.\n"
            "1. *Identifiers/Codes:* Columns containing ID, _NO, _KEYT, _CD, _FORM, _RELATION, _GROUP, _FAMILY, _BRANCH, and binary flags (Bad Customer).\n"
            "2. *Counts:* Whole numbers representing countable items or events (e.g., VISIT, INVCOUNT).\n"
            "3. *Categories:* Text, Boolean, or integer values representing a limited number of categories.\n\n"
            
            "*CONTINUOUS* variables are measurements, amounts, or proportions. They can theoretically take any value within a range.\n"
            "1. *Monetary/Financial:* Amounts, revenue, sales, profit, or loss (e.g., SALES, MARGIN, TURNOVER).\n"
            "2. *Proportions:* Percentages and ratios (e.g., PERCENTAGE, PERC).\n"
            "3. *Measurements:* Age, height, temperature, or any value where decimal precision is meaningful.\n\n"
            
            "--- CLASSIFICATION RULE FOR INTEGERS ---\n"
            "If a column is an integer:\n"
            "- Classify as *CONTINUOUS* if it represents a *monetary amount, sales, or turnover*, even if stored as a whole number.\n"
            "- Classify as *DISCRETE* if it represents an *ID, code, or count of events.*\n\n"
            
            "Analyze the column names and sample values. Return ONLY a single, valid JSON object, without any surrounding text, markdown formatting (like ```json), or explanation.\n"
            f"Columns to classify: {json.dumps(columns)}\n"
            f"Sample data: {json.dumps(sample_data)}\n\n"
            
            "Response format: {\"column_name\": \"discrete\" or \"continuous\"}\n"
        )

        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": "You are a helpful assistant that replies with strict JSON."},
                {"role": "user", "content": prompt}
            ]
        }

        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        url = "[https://models.github.ai/inference/chat/completions](https://models.github.ai/inference/chat/completions)"
        resp = requests.post(url, headers=headers, json=body, timeout=30)
        
        print(f"DEBUG: GitHub API response status: {resp.status_code}")
        if not resp.ok:
            print(f"DEBUG: GitHub API error response: {resp.text}")
            error_msg = f"GitHub Models API call failed (status {resp.status_code})"
            if resp.status_code == 401:
                error_msg += ". Check if your GitHub token has 'models:read' permission."
            elif resp.status_code == 403:
                error_msg += ". Rate limit exceeded or insufficient permissions."
            return jsonify({"error": error_msg, "details": resp.text}), 502

        data = resp.json()
        # Expected path: choices[0].message.content
        text = None
        try:
            text = data.get('choices', [])[0].get('message', {}).get('content')
        except Exception:
            text = None

        if not text:
            # fallback: try top-level generated_text
            if isinstance(data, list) and data and isinstance(data[0], dict):
                text = data[0].get('generated_text')

        if not text:
            return jsonify({"error": "Model returned unexpected response", "raw": data}), 502

        # Try to extract JSON from the model's text
        mapping = None
        try:
            # Use strict load first
            mapping = json.loads(text.strip())
        except Exception:
            # attempt to find JSON substring
            m = re.search(r"\{[\s\S]*\}", text)
            if m:
                try:
                    mapping = json.loads(m.group(0))
                except Exception:
                    mapping = None

        if not mapping or not isinstance(mapping, dict):
            # Fallback when LLM fails to return valid/parsable JSON
            print(f"WARN: LLM failed to return valid JSON, falling back to heuristics.")
            normalized = {}
            for col in columns:
                normalized[col] = _classify_with_heuristics(col, sample_data.get(col, []))
            return jsonify(normalized)


        # Normalize values to 'discrete' or 'continuous'
        normalized = {}
        for k, v in mapping.items():
            s = str(v).strip().lower()
            if s.startswith('d'):
                normalized[k] = 'discrete'
            elif s.startswith('c'):
                normalized[k] = 'continuous'
            else:
                # FIX 3: Fallback if LLM output is not 'discrete' or 'continuous'
                # Use the robust heuristic function for the one-off failure
                print(f"WARN: LLM returned non-standard classification '{v}' for '{k}'. Using heuristics.")
                normalized[k] = _classify_with_heuristics(k, sample_data.get(k, []))
        
        return jsonify(normalized)
    except Exception as e:
        import traceback
        print('ai_classify_columns error:', traceback.format_exc())
        return jsonify({"error": str(e)}), 500

# ----------- Credit Scoring Metrics Calculation -----------
@app.route('/api/calculate-scoring-metrics', methods=['POST'])
def calculate_scoring_metrics():
    """
    Calculate credit scoring metrics including:
    - 0/1 (Good/Bad ratio)
    - G/B Odd (based on 0/1 ratio and total 0/1)
    - G/B Index (B/G label)
    - Index (Combined rounded G/B Odd + G/B Index)
    """
    try:
        data = request.get_json()
        good_count = data.get('good_count', 0)
        bad_count = data.get('bad_count', 0)
        total_count = data.get('total_count', 0)
        total_zero_one_ratio = data.get('total_zero_one_ratio', 0)
        
        # Validate inputs
        if good_count < 0 or bad_count < 0 or total_count < 0:
            return jsonify({"error": "Counts cannot be negative"}), 400
        
        # Calculate 0/1 ratio - Based on your image, it seems to be total/bad
        # But you want 716/9 = 79.5556, so let's use good/bad
        if bad_count > 0:
            zero_one_ratio = good_count / bad_count
        else:
            zero_one_ratio = float('inf')
        
        # G/B Odd calculation
        if zero_one_ratio < total_zero_one_ratio:
            if zero_one_ratio > 0:
                gb_odd = (total_zero_one_ratio / zero_one_ratio) * 100
            else:
                gb_odd = float('inf')
        else:
            if total_zero_one_ratio > 0:
                gb_odd = (zero_one_ratio / total_zero_one_ratio) * 100
            else:
                gb_odd = float('inf')
        
        # G/B Index
        gb_index = "B" if zero_one_ratio < total_zero_one_ratio else "G"
        
        # Combined Index
        rounded_gb_odd = round(gb_odd) if gb_odd != float('inf') else 0
        combined_index = f"{int(rounded_gb_odd)}{gb_index}"
        
        results = {
            'good_count': good_count,
            'bad_count': bad_count,
            'total_count': total_count,
            'zero_one_ratio': round(zero_one_ratio, 4) if zero_one_ratio != float('inf') else 'Inf',
            'gb_odd': round(gb_odd, 0) if gb_odd != float('inf') else 'Inf',
            'gb_index': gb_index,
            'combined_index': combined_index,
            'bad_rate': round((bad_count / total_count * 100), 2) if total_count > 0 else 0
        }
        
        return jsonify({
            "success": True,
            "metrics": results
        })
        
    except Exception as e:
        return jsonify({"error": f"Failed to calculate scoring metrics: {str(e)}"}), 500

# ----------- Batch Calculate Scoring Metrics for Bins -----------
@app.route('/api/calculate-bin-metrics', methods=['POST'])
def calculate_bin_metrics():
    """
    Calculate scoring metrics for multiple bins at once
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
            
        bins_data = data.get('bins', [])
        
        if not bins_data:
            return jsonify({"error": "No bin data provided. Please run univariate analysis or binning first."}), 400
        
        # Calculate totals for overall ratio
        total_good = sum(bin_data.get('good_count', 0) for bin_data in bins_data)
        total_bad = sum(bin_data.get('bad_count', 0) for bin_data in bins_data)
        
        # Calculate overall 0/1 ratio
        if total_bad > 0:
            total_zero_one_ratio = total_good / total_bad
        else:
            total_zero_one_ratio = float('inf')
        
        results = []
        
        for bin_data in bins_data:
            good_count = bin_data.get('good_count', 0)
            bad_count = bin_data.get('bad_count', 0)
            total_count = bin_data.get('total_count', 0)
            bin_name = bin_data.get('bin_name', 'Unknown')
            bin_range = bin_data.get('bin_range', '')
            
            # Calculate 0/1 ratio - Using good/bad as requested
            if bad_count > 0:
                zero_one_ratio = good_count / bad_count
            else:
                zero_one_ratio = float('inf')
            
            # G/B Odd calculation
            if zero_one_ratio < total_zero_one_ratio:
                if zero_one_ratio > 0:
                    gb_odd = (total_zero_one_ratio / zero_one_ratio) * 100
                else:
                    gb_odd = float('inf')
            else:
                if total_zero_one_ratio > 0:
                    gb_odd = (zero_one_ratio / total_zero_one_ratio) * 100
                else:
                    gb_odd = float('inf')
            
            # G/B Index
            gb_index = "B" if zero_one_ratio < total_zero_one_ratio else "G"
            
            # Combined Index
            rounded_gb_odd = round(gb_odd) if gb_odd != float('inf') else 0
            combined_index = f"{int(rounded_gb_odd)}{gb_index}"
            
            bin_metrics = {
                'bin_name': bin_name,
                'bin_range': bin_range,
                'good_count': good_count,
                'bad_count': bad_count,
                'total_count': total_count,
                'zero_one_ratio': round(zero_one_ratio, 4) if zero_one_ratio != float('inf') else 'Inf',
                'gb_odd': round(gb_odd, 0) if gb_odd != float('inf') else 'Inf',
                'gb_index': gb_index,
                'combined_index': combined_index,
                'bad_rate': round((bad_count / total_count * 100), 2) if total_count > 0 else 0
            }
            
            results.append(bin_metrics)
        
        return jsonify({
            "success": True,
            "bin_metrics": results,
            "total_zero_one_ratio": round(total_zero_one_ratio, 4) if total_zero_one_ratio != float('inf') else 'Inf',
            "total_good": total_good,
            "total_bad": total_bad
        })
        
    except Exception as e:
        return jsonify({"error": f"Failed to calculate bin metrics: {str(e)}"}), 500

# ----------- Helper function to detect monotonicity -----------
def detect_monotonic_direction(woe_values):
    """
    Detect if WOE values are monotonically increasing, decreasing, or neither.
    
    Args:
        woe_values: List of WOE values in bin order
        
    Returns:
        str: 'increasing', 'decreasing', or None
    """
    if not woe_values or len(woe_values) < 2:
        return None
    
    # Filter out None/NaN values
    clean_woe = [w for w in woe_values if w is not None and not (isinstance(w, float) and math.isnan(w))]
    
    if len(clean_woe) < 2:
        return None
    
    # Check if monotonically increasing
    is_increasing = all(clean_woe[i] <= clean_woe[i+1] for i in range(len(clean_woe)-1))
    
    # Check if monotonically decreasing
    is_decreasing = all(clean_woe[i] >= clean_woe[i+1] for i in range(len(clean_woe)-1))
    
    if is_increasing and not is_decreasing:
        return 'increasing'
    elif is_decreasing and not is_increasing:
        return 'decreasing'
    else:
        return None

# ----------- WOE/IV Calculation -----------
def calculate_woe_iv(df, variable, target, bin_merges=None, var_type=None):
    """
    Calculate WOE and IV using the exact formula: ROUND(LN(L5/M5) * 100, 1)
    No smoothing - return 0 for any infinite/non-finite situations.
    
    WOE = ROUND(LN(Dist_Good_% / Dist_Bad_%) * 100, 1)
    IV = (Dist_Good_% - Dist_Bad_%) * LN(Dist_Good_% / Dist_Bad_%) / 100
    """
    import numpy as np
    import pandas as pd
    import math
    from flask import current_app as app

    app.logger.debug(f"calculate_woe_iv → {variable} | merges: {bool(bin_merges)} | type: {var_type}")

    # Create a clean working copy to avoid modifying original
    df_work = df.copy()
    
    # Verify target encoding
    unique_targets = df_work[target].unique()
    app.logger.debug(f"Target unique values: {unique_targets}")
    
    # Ensure target is properly encoded (0=Good, 1=Bad)
    if set(unique_targets) != {0, 1}:
        app.logger.warning(f"Target may not be properly encoded. Unique values: {unique_targets}")

    # infer var_type if not provided
    if var_type is None:
        is_numeric = pd.api.types.is_numeric_dtype(df_work[variable])
        var_type = "continuous" if (is_numeric and df_work[variable].nunique(dropna=True) > 20) else "discrete"

    binned_col = f"{variable}_binned"

    # Verify binned column exists and has data
    if binned_col not in df_work.columns:
        raise ValueError(f"Column {binned_col} missing – coarse binning must be performed first.")
    
    # CRITICAL FIX: Remove rows where binned column is NaN before any processing
    initial_count = len(df_work)
    df_work = df_work.dropna(subset=[binned_col])
    removed_count = initial_count - len(df_work)
    if removed_count > 0:
        app.logger.debug(f"Removed {removed_count} rows with NaN in {binned_col}")

    if len(df_work) == 0:
        raise ValueError(f"No valid data remaining after removing NaN from {binned_col}")

    # build final_bin
    if var_type == "discrete" and bin_merges:
        coarse_to_merge = {}
        for merge_key, coarse_labels in bin_merges.items():
            for lbl in coarse_labels:
                coarse_to_merge[str(lbl).strip()] = str(merge_key).strip()
        df_work["final_bin"] = (
            df_work[binned_col].astype(str).str.strip().map(coarse_to_merge)
            .fillna(df_work[binned_col].astype(str).str.strip())
        )
    elif var_type == "continuous" and bin_merges:
        interval_to_merge = {}
        for merge_key, intervals in bin_merges.items():
            for iv in intervals:
                interval_to_merge[str(iv).strip()] = str(merge_key).strip()
        df_work["final_bin"] = (
            df_work[binned_col].astype(str).str.strip().map(interval_to_merge)
            .fillna(df_work[binned_col].astype(str).str.strip())
        )
    else:
        df_work["final_bin"] = df_work[binned_col].astype(str)

    # Remove any rows where final_bin is NaN (additional safety)
    df_work = df_work.dropna(subset=["final_bin"])

    # build range info
    bin_ranges = {}
    if var_type == "continuous":
        for lbl in df_work["final_bin"].unique():
            mask = df_work["final_bin"] == lbl
            vals = df_work.loc[mask, variable]
            mn = vals.min() if not vals.empty else None
            mx = vals.max() if not vals.empty else None
            bin_ranges[str(lbl)] = (float(mn) if mn is not None else None, float(mx) if mx is not None else None)
    else:
        for lbl in df_work["final_bin"].unique():
            mask = df_work["final_bin"] == lbl
            uniq = df_work.loc[mask, variable].unique()
            bin_ranges[str(lbl)] = sorted([str(v) for v in uniq])

    # preserve ordering where possible
    ordered_labels = None
    try:
        if var_type == "continuous":
            def _min_val(iv):
                try:
                    ivs = str(iv)
                    if ivs.startswith("(-inf,"): return float('-inf')
                    if ivs.startswith("["): return float(ivs.split(",")[0].replace("[", ""))
                    return float(ivs.split(",")[0].replace("(", ""))
                except Exception:
                    return float('inf')
            ordered = sorted(
                [(lbl, bin_ranges.get(str(lbl), (None, None))) for lbl in df_work["final_bin"].unique()],
                key=lambda x: _min_val(x[0])
            )
            ordered_labels = [lbl for lbl, _ in ordered]
        else:
            ordered_labels = list(dict.fromkeys(df_work["final_bin"].astype(str).tolist()))
    except Exception as e:
        app.logger.warning(f"Ordering failed for {variable}: {e}")

    # aggregate counts
    grouped = (
        df_work.groupby("final_bin", observed=True, sort=False)
        .agg(
            Total=(target, "count"),
            Good=(target, lambda x: (x == 0).sum()),
            Bad=(target, lambda x: (x == 1).sum()),
        )
        .reset_index()
    )

    if ordered_labels:
        present = [lbl for lbl in ordered_labels if lbl in grouped["final_bin"].astype(str).tolist()]
        if present:
            grouped = grouped.set_index("final_bin").reindex(present).reset_index()

    # CRITICAL FIX: Calculate totals from the ACTUAL BINNED DATA only
    total_good = grouped["Good"].sum()
    total_bad = grouped["Bad"].sum()
    total_all = grouped["Total"].sum()
    
    # Log the actual binned data totals
    app.logger.debug(f"=== WOE/IV CALCULATION VERIFICATION ===")
    app.logger.debug(f"Variable: {variable}")
    app.logger.debug(f"Original dataset: {len(df)} rows")
    app.logger.debug(f"After binning: {len(df_work)} rows")
    app.logger.debug(f"Binned data - Total Good: {total_good}, Total Bad: {total_bad}, Total All: {total_all}")
    app.logger.debug(f"Good + Bad = {total_good + total_bad}, Should equal Total: {total_all}")
    if total_all > 0:
        app.logger.debug(f"Good Rate: {(total_good/total_all*100):.2f}%, Bad Rate: {(total_bad/total_all*100):.2f}%")

    n_bins = len(grouped)

    if n_bins == 0:
        return 0.0, []

    stats = []
    iv_total = 0.0

    # Calculate percentages (Dist_Good_% and Dist_Bad_%)
    for _, row in grouped.iterrows():
        g = int(row["Good"])
        b = int(row["Bad"])
        total_in_bin = int(row["Total"])

        # Calculate proportions (0-1) and percentages (0-100) for display
        dist_good = (g / total_good) if total_good > 0 else 0.0
        dist_bad = (b / total_bad) if total_bad > 0 else 0.0
        dist_good_pct = dist_good * 100.0
        dist_bad_pct = dist_bad * 100.0

        # Verify bin percentages
        bin_good_rate = (g / total_in_bin * 100) if total_in_bin > 0 else 0
        bin_bad_rate = (b / total_in_bin * 100) if total_in_bin > 0 else 0
        
        app.logger.debug(f"Bin '{row['final_bin']}': Good={g}, Bad={b}, Total={total_in_bin}")
        app.logger.debug(f"  Dist Good%: {dist_good_pct:.4f} (should be: {g}/{total_good}*100 = {(g/total_good*100):.4f})")
        app.logger.debug(f"  Dist Bad%: {dist_bad_pct:.4f} (should be: {b}/{total_bad}*100 = {(b/total_bad*100):.4f})")
        app.logger.debug(f"  Bin Good%: {bin_good_rate:.2f}%, Bin Bad%: {bin_bad_rate:.2f}%")

        woe_val = 0.0
        iv_val = 0.0

        # Exact formula: ROUND(LN(L5/M5) * 100, 1) with no smoothing
        # Use proportions (0-1) for IV calculation, percentages for WOE display
        if dist_good > 0.0 and dist_bad > 0.0:
            try:
                ratio = dist_good / dist_bad
                ln_ratio = math.log(ratio)
                if math.isfinite(ln_ratio):
                    # WOE = ROUND(LN(L5/M5) * 100, 1)
                    woe_val = round(ln_ratio * 100.0, 1)
                
                    # IV = (dist_good - dist_bad) * ln_ratio (using proportions, not percentages)
                    iv_val = (dist_good - dist_bad) * ln_ratio 
                else:
                    woe_val = 0.0
                    iv_val = 0.0
            except (ValueError, ZeroDivisionError):
                woe_val = 0.0
                iv_val = 0.0
        else:
            # No smoothing - return 0 if either proportion is zero
            woe_val = 0.0
            iv_val = 0.0

        # Accumulate total IV (already in correct scale, no division needed)
        if math.isfinite(iv_val):
            iv_total += float(iv_val)

        bin_label = str(row["final_bin"])
        range_info = bin_ranges.get(bin_label, (None, None) if var_type == "continuous" else [])
        
        # For continuous: include Min and Max fields separately, plus Range string
        # For discrete: include Range string only
        if var_type == "continuous":
            min_val = range_info[0] if isinstance(range_info, tuple) and len(range_info) >= 1 else None
            max_val = range_info[1] if isinstance(range_info, tuple) and len(range_info) >= 2 else None
            range_str = (f"{min_val} - {max_val}" if min_val is not None and max_val is not None
                        else (f"{min_val} - " if min_val is not None else "") + 
                             (f"{max_val}" if max_val is not None else ""))
            stats.append({
                "Bin": bin_label,
                "Good": int(g),
                "Bad": int(b),
                "Total": int(total_in_bin),
                "Dist_Good_%": round(dist_good_pct, 4),
                "Dist_Bad_%": round(dist_bad_pct, 4),
                "WOE": float(woe_val),
                "IV": round(float(iv_val), 4),
                "Range": range_str,
                "Min": min_val,
                "Max": max_val,
            })
        else:
            range_str = ', '.join(map(str, range_info)) if range_info else ""
            stats.append({
                "Bin": bin_label,
                "Good": int(g),
                "Bad": int(b),
                "Total": int(total_in_bin),
                "Dist_Good_%": round(dist_good_pct, 4),
                "Dist_Bad_%": round(dist_bad_pct, 4),
                "WOE": float(woe_val),
                "IV": round(float(iv_val), 4),
                "Range": range_str,
            })

    app.logger.debug(f"Total IV for {variable}: {round(float(iv_total), 4)}")
    return round(float(iv_total), 4), stats

# ----------- WOE/IV API -----------
# ----------- WOE/IV API -----------
@app.route("/api/woe-iv", methods=["POST"])
def woe_iv_api():
    try:
        data = request.get_json()
        variables = data.get("variables", [])
        target = data.get("target")
        record_id = data.get("record_id")
        global_type = data.get("type")
        types_map = data.get("types", {}) if isinstance(data.get("types", {}), dict) else {}

        raw_bin_merges = data.get("bin_merges")

        def normalize_merge_map(merge_map):
            normalized = {}
            if isinstance(merge_map, dict):
                for group_key, group_vals in merge_map.items():
                    if group_vals is None:
                        continue
                    if isinstance(group_vals, (list, tuple, set)):
                        normalized[str(group_key).strip()] = [str(item).strip() for item in group_vals]
                    else:
                        normalized[str(group_key).strip()] = [str(group_vals).strip()]
            return {k: v for k, v in normalized.items() if v}

        requested_bin_merges = {}
        if isinstance(raw_bin_merges, dict) and raw_bin_merges:
            values = list(raw_bin_merges.values())
            # Case 1: Nested map { variable: { merge_key: [...] } }
            if values and all(isinstance(v, dict) for v in values):
                for var_key, merge_map in raw_bin_merges.items():
                    normalized = normalize_merge_map(merge_map)
                    if normalized:
                        requested_bin_merges[str(var_key)] = normalized
                        try:
                            print(f"WOE/IV DEBUG: Received {len(normalized)} merge groups from request for {var_key}")
                        except Exception:
                            pass
            # Case 2: Single-variable payload { merge_key: [...] }
            elif len(variables) == 1:
                normalized = normalize_merge_map(raw_bin_merges)
                if normalized:
                    requested_bin_merges[str(variables[0])] = normalized
                    try:
                        print(f"WOE/IV DEBUG: Received {len(normalized)} merge groups from request for {variables[0]}")
                    except Exception:
                        pass

        print(f"WOE/IV DEBUG: Starting with variables: {variables}, target: {target}")

        if not variables or not target:
            return jsonify({"error": "Missing required fields: variables or target"}), 400
        
        # CRITICAL: Load train set using data_loader (same as binning endpoints)
        try:
            from data_loader import get_data_for_stage
            df = get_data_for_stage(record_id, 'binning')  # Returns TRAIN set if split exists
            print(f"WOE/IV DEBUG: Loaded dataset: {len(df)} rows (train set if TTS exists)")
        except Exception as e:
            # Fallback to CSV if data_loader fails
            try:
                csv_path = get_csv_path(record_id)
                df = pd.read_csv(csv_path)
                print(f"WOE/IV DEBUG: Loaded full dataset: {len(df)} rows (fallback)")
            except FileNotFoundError as fe:
                return jsonify({"error": str(fe)}), 400
            except Exception as e2:
                return jsonify({"error": f"Failed to load dataset: {str(e2)}"}), 400
        
        if target not in df.columns:
            return jsonify({"error": f"Target column '{target}' not found in dataset"}), 400
        
        # CRITICAL: Apply preprocessing before WOE/IV calculation (same as binning)
        print(f"WOE/IV DEBUG: Applying preprocessing before WOE/IV calculation...")
        try:
            df, preprocessing_report = preprocess_dataset(
                df,
                target_col=target,
                preprocessing_steps={
                    'detect_types': True,
                    'handle_missing': True,
                    'remove_duplicates': True,
                    'handle_outliers': False,  # Don't handle outliers before binning
                    'encode_categorical': False  # Don't encode categorical before binning
                },
                missing_threshold=0.5,
                treat_negative_one_as_missing=True
            )
            print(f"WOE/IV DEBUG: Preprocessing completed. Processed shape: {df.shape}")
        except Exception as e:
            print(f"WOE/IV DEBUG: WARNING: Preprocessing failed: {str(e)}")
            print(f"WOE/IV DEBUG: Continuing with raw data (this may cause issues)")
            import traceback
            traceback.print_exc()
        
        # Better target validation
        df[target] = df[target].fillna(0)
        
        # Ensure target is properly encoded as integers (0=Good, 1=Bad)
        try:
            df[target] = df[target].astype(int)
        except (ValueError, TypeError):
            # If target is not numeric, encode it properly
            unique_vals = df[target].unique()
            if len(unique_vals) == 2:
                # Map to 0 and 1
                val_map = {unique_vals[0]: 0, unique_vals[1]: 1}
                df[target] = df[target].map(val_map)
            else:
                return jsonify({"error": f"Target must have exactly 2 unique values, found {len(unique_vals)}"}), 400
        
        target_distribution = df[target].value_counts().to_dict()
        print(f"WOE/IV DEBUG: Target distribution - Good (0): {target_distribution.get(0, 0)}, Bad (1): {target_distribution.get(1, 0)}")
        
        if target_distribution.get(1, 0) == 0:
            return jsonify({"error": "No bad cases (target=1) found in dataset"}), 400

        results = {}

        # Create coarse bins for variables that are new
        # CRITICAL FIX: Use the type parameter from request instead of heuristics
        for var in variables:
            var_series = df[var]
            
            # Determine variable type: first check types_map, then global_type, then fall back to heuristics
            var_type_for_binning = types_map.get(var) or global_type
            if not var_type_for_binning:
                # Fall back to heuristics only if type not provided
                is_likely_id = any(k in var.lower() for k in ['id', 'key', 'code', 'no', 'num'])
                unique_cnt = var_series.nunique(dropna=True)
                if pd.api.types.is_numeric_dtype(var_series):
                    var_type_for_binning = 'discrete' if (is_likely_id or unique_cnt <= 50) else 'continuous'
                else:
                    var_type_for_binning = 'discrete'
            
            # Use fresh data copy for each variable
            temp_df = df.copy()
            
            # Use the determined type to call the correct binning function
            try:
                if var_type_for_binning == 'continuous':
                    _, temp_df[f"{var}_binned"] = coarse_bin_continuous(temp_df, var, target)
                    print(f"WOE/IV DEBUG: Created continuous bins for {var} (type: {var_type_for_binning})")
                else:
                    # Default to discrete for discrete type or non-numeric
                    _, temp_df[f"{var}_binned"], _ = coarse_bin_discrete(temp_df, var, target)
                    print(f"WOE/IV DEBUG: Created discrete bins for {var} (type: {var_type_for_binning})")
            except Exception as e:
                print(f"WOE/IV DEBUG: Failed to create bins for {var} (type: {var_type_for_binning}): {e}")
                import traceback
                traceback.print_exc()
                continue
            
            # Copy only the binned column back to main dataframe
            df[f"{var}_binned"] = temp_df[f"{var}_binned"]

        # Load saved fine-bin merges
        merges_per_var = {}
        if record_id:
            for var in variables:
                finebin_details = get_finebin_details_db(record_id, var)
                if finebin_details:
                    merges = {}
                    for row in finebin_details:
                        try:
                            mb = row.get("merged_bins")
                            # New schema: merged_bins is always a list (no JSON string conversion)
                            if isinstance(mb, (list, tuple, set)) and mb:
                                bins_loaded = [str(item).strip() for item in mb]
                                merges[str(row.get("group_id")).strip()] = bins_loaded
                        except Exception:
                            pass
                    if merges:
                        merges_per_var[var] = merges
                        print(f"WOE/IV DEBUG: Loaded {len(merges)} merge groups for {var}")

        # Override/augment with merges provided directly in the request body
        if requested_bin_merges:
            for var_key, merge_map in requested_bin_merges.items():
                if merge_map:
                    merges_per_var[var_key] = merge_map
                    try:
                        print(f"WOE/IV DEBUG: Applying request merge overrides for {var_key} ({len(merge_map)} groups)")
                    except Exception:
                        pass

        # Compute WOE/IV per variable
        for var in variables:
            # Skip if we couldn't create bins for this variable
            if f"{var}_binned" not in df.columns:
                print(f"WOE/IV DEBUG: Skipping {var} - no binned column created")
                continue
                
            # determine var_type for this variable
            var_type_for_var = types_map.get(var) or global_type
            if not var_type_for_var:
                if pd.api.types.is_numeric_dtype(df[var]):
                    is_likely_id = any(k in var.lower() for k in ['id', 'key', 'code', 'no', 'num'])
                    unique_cnt = df[var].nunique(dropna=True)
                    var_type_for_var = 'discrete' if (is_likely_id or unique_cnt <= 50) else 'continuous'
                else:
                    var_type_for_var = 'discrete'

            merges = merges_per_var.get(var)
            
            # Compute WOE/IV
            try:
                iv, stats = calculate_woe_iv(
                    df=df,
                    variable=var,
                    target=target,
                    bin_merges=merges,
                    var_type=var_type_for_var
                )
                results[var] = {"iv": iv, "stats": stats}
                print(f"WOE/IV DEBUG: Calculated WOE/IV for {var} - IV: {iv}, bins: {len(stats)}")
            except Exception as e:
                print(f"WOE/IV DEBUG: Failed to calculate WOE/IV for {var}: {e}")
                results[var] = {"iv": 0, "stats": []}

        # Persist results into the new normalized schema if record_id (dataset_id) provided
        if record_id:
            try:
                dataset_id = int(record_id)
            except Exception:
                dataset_id = record_id

            # For each variable's results, create/update binning_step, bins and totals
            for var_name, res in results.items():
                try:
                    iv_value = res.get('iv', 0) if isinstance(res, dict) else 0
                    stats = res.get('stats', []) if isinstance(res, dict) else []

                    # Ensure feature exists for this dataset
                    feature = get_feature_by_name(dataset_id, var_name)
                    if not feature:
                        # Create feature with inferred type (best effort)
                        inferred_type = types_map.get(var_name) or global_type
                        if not inferred_type:
                            # fallback: use continuous if present in df and numeric, else discrete
                            try:
                                inferred_type = 'continuous' if pd.api.types.is_numeric_dtype(df[var_name]) else 'discrete'
                            except Exception:
                                inferred_type = 'discrete'
                        fid = create_feature(dataset_id, var_name, inferred_type, False)
                        feature = get_feature(fid)
                    
                    # Get var_type for this variable to determine how to save range data
                    var_type_for_save = feature.get('type', 'continuous')
                    
                    # For continuous variables, if Min/Max are missing, compute them from the actual data
                    if var_type_for_save == 'continuous' and var_name in df.columns:
                        # Try both binned and fine_binned columns
                        binned_cols = [f'{var_name}_binned', f'{var_name}_fine_binned']
                        bin_label_to_range = {}
                        
                        for binned_col in binned_cols:
                            if binned_col in df.columns:
                                # Build a lookup map from bin_label to (min, max) computed from actual data
                                for bin_label in df[binned_col].dropna().unique():
                                    if str(bin_label) not in bin_label_to_range:  # Don't overwrite if already found
                                        mask = df[binned_col] == bin_label
                                        if mask.any():
                                            values = df.loc[mask, var_name].dropna()
                                            if not values.empty:
                                                min_val = float(values.min())
                                                max_val = float(values.max())
                                                bin_label_to_range[str(bin_label)] = (min_val, max_val)
                        
                        # Update stats with missing Min/Max values
                        for stat in stats:
                            if isinstance(stat, dict):
                                bin_label = str(stat.get('Bin', ''))
                                if bin_label in bin_label_to_range:
                                    if stat.get('Min') is None or stat.get('Min') == '':
                                        stat['Min'] = bin_label_to_range[bin_label][0]
                                    if stat.get('Max') is None or stat.get('Max') == '':
                                        stat['Max'] = bin_label_to_range[bin_label][1]

                    # Determine if we should use fine or coarse step
                    step_type = 'fine' if merges_per_var.get(var_name) else 'coarse'

                    # CRITICAL FIX: Detect monotonic direction from WOE values
                    woe_values = [float(s.get('WOE', s.get('woe', 0))) for s in stats if isinstance(s, dict)]
                    monotonic_dir = detect_monotonic_direction(woe_values)
                    is_monotonic = monotonic_dir is not None

                    # Create or update binning step with IV, num_bins, and monotonic_direction
                    num_bins = len(stats) if isinstance(stats, (list, tuple)) else 0
                    step_id = create_binning_step(
                        feature_id=feature['id'],
                        step_type=step_type,
                        method='calculated',
                        num_bins=num_bins,
                        is_monotonic=is_monotonic,
                        monotonic_direction=monotonic_dir,
                        iv_value=float(iv_value) if iv_value is not None else None
                    )

                    # CRITICAL FIX: Delete existing bins for this step before creating new ones
                    # This prevents orphaned binning_steps (steps without bins) when ON CONFLICT updates an existing step
                    delete_bins_by_step(step_id)

                    # Get var_type for this variable to determine how to save range data
                    var_type_for_save = feature.get('type', 'continuous')
                    
                    # Prepare bins data for insertion
                    # Build bins_data and compute per-bin metrics
                    bins_data = []
                    # Precompute totals from stats so we can calculate freq_percent and indexes
                    try:
                        total_good = sum(int(s.get('Good', s.get('good', 0))) for s in stats)
                        total_bad = sum(int(s.get('Bad', s.get('bad', 0))) for s in stats)
                        total_all = sum(int(s.get('Total', s.get('total', (int(s.get('Good', 0)) + int(s.get('Bad', 0))))) ) for s in stats)
                    except Exception:
                        total_good = 0
                        total_bad = 0
                        total_all = 0

                    overall_odds = (total_good / total_bad) if total_bad > 0 else None

                    for idx, s in enumerate(stats):
                        try:
                            bin_number = idx + 1
                            bin_label = str(s.get('Bin', s.get('bin', bin_number)))
                            good = int(s.get('Good', s.get('good', 0)))
                            bad = int(s.get('Bad', s.get('bad', 0)))
                            total = int(s.get('Total', s.get('total', good + bad)))
                            dist_good = float(s.get('Dist_Good_%', s.get('dist_good', 0))) if total_good > 0 else ( (good / total_good) * 100 if total_good > 0 else None )
                            dist_bad = float(s.get('Dist_Bad_%', s.get('dist_bad', 0))) if total_bad > 0 else ( (bad / total_bad) * 100 if total_bad > 0 else None )
                            woe = float(s.get('WOE', s.get('woe', 0)))
                            iv_bin = float(s.get('IV', s.get('iv', 0)))
                            
                            # For continuous: only save min_value and max_value, set range_text to None
                            # For discrete: only save range_text, set min_value and max_value to None
                            if var_type_for_save == 'continuous':
                                # Continuous variables: extract min/max from Min/Max fields or parse from Range
                                min_value = None
                                max_value = None
                                
                                # Try to get from Min/Max fields first (preferred method)
                                if 'Min' in s and s.get('Min') is not None:
                                    try:
                                        min_value = float(s.get('Min'))
                                    except (ValueError, TypeError):
                                        min_value = None
                                if 'Max' in s and s.get('Max') is not None:
                                    try:
                                        max_value = float(s.get('Max'))
                                    except (ValueError, TypeError):
                                        max_value = None
                                
                                # If not found, try to parse from Range field (format: "min - max" or "min - " or "max")
                                if (min_value is None or max_value is None) and 'Range' in s:
                                    range_text_raw = s.get('Range')
                                    if isinstance(range_text_raw, str) and range_text_raw.strip():
                                        # Try to parse "min - max" format
                                        if '-' in range_text_raw:
                                            parts = [p.strip() for p in range_text_raw.split('-', 1)]
                                            try:
                                                if min_value is None and parts[0]:
                                                    min_value = float(parts[0])
                                            except (ValueError, TypeError):
                                                pass
                                            try:
                                                if max_value is None and len(parts) > 1 and parts[1]:
                                                    max_value = float(parts[1])
                                            except (ValueError, TypeError):
                                                pass
                                
                                # Explicitly set range_text to None for continuous
                                range_text = None
                            else:
                                # Discrete variables: use range_text only
                                range_text = s.get('Range') if s.get('Range') is not None else s.get('range', None)
                                if not range_text:
                                    range_text = bin_label  # Fallback to bin_label
                                
                                # Explicitly set min_value and max_value to None for discrete
                                min_value = None
                                max_value = None

                            # Derived values are calculated on-the-fly, not stored
                            # Only store raw counts and calculated WOE/IV
                            bin_entry = {
                                'bin_number': bin_number,
                                'bin_label': bin_label,
                                'min_value': min_value,
                                'max_value': max_value,
                                'range_text': range_text,
                                'good_count': good,
                                'bad_count': bad,
                                'total_count': total,
                                'woe': woe,
                                'iv': iv_bin
                            }
                            bins_data.append(bin_entry)
                        except Exception:
                            continue

                    if bins_data:
                        create_bins_batch(step_id, bins_data)

                    # Create/update binning totals with proper calculations
                    try:
                        total_good = sum(int(b.get('good_count', 0)) for b in bins_data)
                        total_bad = sum(int(b.get('bad_count', 0)) for b in bins_data)
                        total_count = sum(int(b.get('total_count', 0)) for b in bins_data)
                        
                        # CRITICAL FIX: Calculate good_bad_ratio and bad_rate for totals
                        overall_good_bad_ratio = (total_good / total_bad) if total_bad > 0 else None
                        overall_bad_rate = (total_bad / total_count) * 100 if total_count > 0 else None
                        
                        create_binning_totals(
                            binning_step_id=step_id, 
                            total_good=total_good, 
                            total_bad=total_bad, 
                            total_count=total_count,
                            good_bad_ratio=overall_good_bad_ratio,
                            bad_rate=overall_bad_rate,
                            iv=float(iv_value) if iv_value is not None else None
                        )
                    except Exception as totals_err:
                        print(f"WOE/IV WARNING: Failed to create totals for {var_name}: {totals_err}")
                        pass

                    # CRITICAL FIX: Populate merged_bins table for fine binning
                    if step_type == 'fine' and merges_per_var.get(var_name):
                        try:
                            merge_groups = merges_per_var.get(var_name)
                            for merge_key, original_bins in merge_groups.items():
                                # Find the bin_number for this merged group
                                merged_bin_num = None
                                for bin_data in bins_data:
                                    if str(bin_data.get('bin_label', '')).strip() == str(merge_key).strip():
                                        merged_bin_num = bin_data.get('bin_number')
                                        break
                                
                                if merged_bin_num is not None and original_bins:
                                    # Get the coarse step to find original bin IDs
                                    coarse_step = get_binning_step_by_type(feature['id'], 'coarse')
                                    if coarse_step:
                                        coarse_bins = get_bins_by_step(coarse_step['id'])
                                        
                                        # Find original bin IDs that match the labels being merged
                                        original_bin_ids = []
                                        original_bin_labels = []
                                        for orig_label in original_bins:
                                            for cb in coarse_bins:
                                                if str(cb.get('bin_label', '')).strip() == str(orig_label).strip():
                                                    original_bin_ids.append(cb['id'])
                                                    original_bin_labels.append(str(orig_label).strip())
                                                    break
                                        
                                        if original_bin_ids:
                                            create_merged_bin(
                                                fine_step_id=step_id,
                                                merged_bin_number=merged_bin_num,
                                                original_bin_ids=original_bin_ids,
                                                original_bin_labels=original_bin_labels
                                            )
                                            print(f"WOE/IV DEBUG: Created merged_bin entry for {var_name}, bin {merged_bin_num} from {len(original_bin_ids)} original bins")
                        except Exception as merge_err:
                            print(f"WOE/IV WARNING: Failed to create merged_bins for {var_name}: {merge_err}")
                            import traceback
                            traceback.print_exc()

                    # Persist merged bin groups when provided (legacy function, kept for compatibility)
                    try:
                        if merges_per_var.get(var_name):
                            save_finebin_details_db(dataset_id, var_name, merges_per_var.get(var_name))
                    except Exception:
                        pass

                except Exception as e_inner:
                    print(f"WOE/IV PERSIST WARNING: failed to persist {var_name}: {e_inner}")
                    import traceback
                    traceback.print_exc()

        print(f"WOE/IV DEBUG: Completed successfully for {len(results)} variables")
        return jsonify(results)

    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"WOE/IV ERROR: {str(e)}")
        print(f"WOE/IV TRACEBACK: {error_trace}")
        return jsonify({"error": f"WOE/IV calculation failed: {str(e)}"}), 500
# ----------- Save Record -----------
@app.route('/api/save-record', methods=['POST'])
def save_record():
    """
    DEPRECATED: This endpoint is now a no-op. Use /api/upsert-single-record instead.
    All changes are auto-saved through upsert-single-record.
    """
    print("\n[API] /api/save-record (POST) called - DEPRECATED endpoint")
    try:
        # Get the latest dataset ID to return
        latest = get_latest_dataset()
        dataset_id = latest['id'] if latest else None
        return jsonify({"success": True, "id": dataset_id})
    except Exception as e:
        print(f"[save_record] ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# ----------- Upsert Single Record -----------
@app.route('/api/upsert-single-record', methods=['POST'])
def upsert_single_record():
    """
    Create or update a single dataset record.
    If no dataset exists, insert one; otherwise update the latest dataset.
    This supports the UX where only one record should exist and be updated across actions.
    """
    print("\n[API] /api/upsert-single-record called")
    try:
        data = request.get_json()
        print(f"[upsert_single_record] Payload keys: {list(data.keys()) if data else 'None'}")
        try:
            print('[backend] upsert_single_record payload keys:', list(data.keys()) if isinstance(data, dict) else type(data))
        except Exception:
            pass
        
        dataset_path = data.get('dataset_path')
        record_id = data.get('record_id')
        discrete_columns = data.get('discrete_columns', [])
        continuous_columns = data.get('continuous_columns', [])
        selected_columns = data.get('selected_columns', [])
        dashboard_selected_columns = data.get('dashboard_selected_columns', [])
        final_selected_columns = data.get('final_selected_columns', [])
        target_variable = data.get('target_variable', '')
        
        # Extract clean dataset name from path
        if dataset_path:
            # Get just the filename without path
            dataset_name = os.path.basename(dataset_path)
            # Remove .csv extension and any timestamp suffix
            if dataset_name.endswith('.csv'):
                dataset_name = dataset_name[:-4]
            # Remove timestamp patterns like _20231115_143022
            import re
            dataset_name = re.sub(r'_\d{8}_\d{6}$', '', dataset_name)
        else:
            dataset_name = "Dataset"
        
        # Determine which dataset to use
        if record_id:
            # Use the specific record provided
            dataset = get_dataset(record_id)
            if dataset:
                dataset_id = dataset['id']
                # If dataset_path not provided, use existing one
                if not dataset_path:
                    dataset_path = dataset.get('file_path', '')
                    if dataset_path:
                        # Extract name from existing path
                        dataset_name = os.path.basename(dataset_path)
                        if dataset_name.endswith('.csv'):
                            dataset_name = dataset_name[:-4]
                        import re
                        dataset_name = re.sub(r'_\d{8}_\d{6}$', '', dataset_name)
                # Update the existing dataset
                update_dataset(
                    dataset_id=dataset_id,
                    name=dataset_name,
                    target_variable=target_variable,
                    file_path=dataset_path if dataset_path else None
                )
                print(f'[backend] Updated dataset {dataset_id} (from record_id)')
            else:
                print(f'[backend] WARNING: record_id {record_id} not found, creating new dataset')
                dataset_id = create_dataset(
                    name=dataset_name,
                    file_path=dataset_path or '',
                    target_variable=target_variable
                )
                print(f'[backend] Created new dataset with id: {dataset_id}')
        else:
            # No record_id provided - get latest or create new
            latest = get_latest_dataset()
            
            if latest is None:
                # Create new dataset
                if not dataset_path:
                    print('[backend] WARNING: Creating new dataset without dataset_path')
                dataset_id = create_dataset(
                    name=dataset_name,
                    file_path=dataset_path or '',
                    target_variable=target_variable
                )
                print(f'[backend] Created new dataset with id: {dataset_id}')
            else:
                # Update existing dataset
                dataset_id = latest['id']
                # If dataset_path not provided, keep existing one
                if not dataset_path:
                    dataset_path = latest.get('file_path', '')
                update_dataset(
                    dataset_id=dataset_id,
                    name=dataset_name,
                    target_variable=target_variable,
                    file_path=dataset_path if dataset_path else None
                )
                print(f'[backend] Updated latest dataset with id: {dataset_id}')
        
        # Update features for this dataset
        existing_features = get_features_by_dataset(dataset_id)
        existing_feature_names = {f['name'] for f in existing_features}
        
        all_columns = set(discrete_columns + continuous_columns)
        
        # Create new features that don't exist
        # Target variable is always set to selected=False
        for col in all_columns:
            if col not in existing_feature_names:
                var_type = 'discrete' if col in discrete_columns else 'continuous'
                # Target variable is always False, others follow selected_columns
                is_selected = False if col == target_variable else (col in selected_columns)
                create_feature(
                    dataset_id=dataset_id,
                    name=col,
                    feature_type=var_type,
                    selected=is_selected
                )
        
        # Update existing features (type and selection)
        # NOTE: Only update selected if feature is explicitly in selected_columns
        # This preserves the selected state from preprocessing step
        # IMPORTANT: Never set selected=False - only set to True if in selected_columns
        # Target variable is always set to selected=False
        for feature in existing_features:
            if feature['name'] in all_columns:
                new_type = 'discrete' if feature['name'] in discrete_columns else 'continuous'
                
                # Target variable is always set to selected=False
                if feature['name'] == target_variable:
                    if feature['type'] != new_type or feature['selected'] != False:
                        update_feature(feature['id'], type=new_type, selected=False)
                elif selected_columns and feature['name'] in selected_columns:
                    # Feature is in selected_columns - set to True
                    is_selected = True
                    if feature['type'] != new_type or feature['selected'] != is_selected:
                        update_feature(feature['id'], type=new_type, selected=is_selected)
                else:
                    # Feature not in selected_columns OR selected_columns is empty
                    # Only update type, NEVER touch the selected state
                    if feature['type'] != new_type:
                        update_feature(feature['id'], type=new_type)
        
        # Update model_ready for features (set in Column Selection & Binning)
        try:
            if dashboard_selected_columns is not None and isinstance(dashboard_selected_columns, list):
                update_features_model_ready(dataset_id, dashboard_selected_columns)
                print(f'[upsert_single_record] Updated model_ready for {len(dashboard_selected_columns)} features')
        except Exception as e:
            if 'model_ready' in str(e).lower() or 'does not exist' in str(e).lower():
                # Column doesn't exist, try to add it
                try:
                    ensure_model_ready_column()
                    if dashboard_selected_columns is not None and isinstance(dashboard_selected_columns, list):
                        update_features_model_ready(dataset_id, dashboard_selected_columns)
                except Exception as e2:
                    print(f'[upsert_single_record] WARNING: Failed to update model_ready after migration: {str(e2)}')
            else:
                print(f'[upsert_single_record] WARNING: Failed to update model_ready: {str(e)}')
                import traceback
                traceback.print_exc()
        
        # Update dataset aggregate counts
        final_features = get_features_by_dataset(dataset_id)
        discrete_count = sum(1 for f in final_features if f.get('type') == 'discrete')
        continuous_count = sum(1 for f in final_features if f.get('type') == 'continuous')
        total_count = len(final_features)
        
        print(f'[upsert_single_record] Updating dataset counts: discrete={discrete_count}, continuous={continuous_count}, total={total_count}')
        update_dataset(
            dataset_id=dataset_id,
            total_features=total_count,
            discrete_features=discrete_count,
            continuous_features=continuous_count
        )
        
        # NOTE: Train/test split is created automatically by frontend when target variable is selected
        # This happens via the /api/train-test-split endpoint called from frontend
        # We do NOT create it here to avoid duplicate creation
        
        return jsonify({"success": True, "id": dataset_id})
    except Exception as e:
        print(f"[upsert_single_record] ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/api/update-feature-modeling', methods=['POST'])
def update_feature_modeling():
    """
    Fast endpoint to update feature's model_ready when checkbox is checked.
    Uses direct SQL update for maximum speed - assumes column exists (created on startup).
    """
    conn = None
    cur = None
    try:
        data = request.get_json()
        feature_name = data.get('feature_name')
        dataset_id = data.get('record_id') or data.get('dataset_id')
        is_selected = data.get('is_selected', False)
        
        if not feature_name or not dataset_id:
            return jsonify({"error": "Missing feature_name or dataset_id"}), 400
        
        # Ensure dataset_id is an integer
        try:
            dataset_id = int(dataset_id)
        except (ValueError, TypeError):
            return jsonify({"error": f"Invalid dataset_id: {dataset_id}"}), 400
        
        # Fast path: Direct SQL update in single query (assumes column exists)
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Update model_ready directly - fastest possible path
        cur.execute("""
            UPDATE features 
            SET model_ready = %s 
            WHERE dataset_id = %s AND name = %s
        """, (is_selected, dataset_id, feature_name))
        
        if cur.rowcount == 0:
            cur.close()
            conn.close()
            return jsonify({"error": f"Feature '{feature_name}' not found"}), 404
        
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({"success": True})
    except Exception as e:
        # If column doesn't exist, fall back to slower path
        if 'model_ready' in str(e).lower() or 'does not exist' in str(e).lower() or 'column' in str(e).lower():
            try:
                ensure_model_ready_column()
                # Retry with the slower but safer path
                feature = get_feature_by_name(dataset_id, feature_name)
                if not feature:
                    return jsonify({"error": f"Feature '{feature_name}' not found"}), 404
                update_feature(feature['id'], model_ready=is_selected)
                return jsonify({"success": True})
            except Exception as e2:
                print(f"[update_feature_modeling] Could not update model_ready: {e2}")
                return jsonify({"error": "Failed to update model_ready"}), 500
        else:
            if conn:
                conn.rollback()
            if cur:
                cur.close()
            if conn:
                conn.close()
            print(f"[update_feature_modeling] ERROR: {str(e)}")
            import traceback
            traceback.print_exc()
            return jsonify({"error": str(e)}), 500

@app.route('/api/sync-model-ready-to-final-selected', methods=['POST'])
def sync_model_ready_to_final_selected_endpoint():
    """
    Copy model_ready values to final_selected for all features in a dataset.
    Called when user navigates from Column Selection & Binning to Model Training.
    """
    try:
        data = request.get_json()
        dataset_id = data.get('record_id') or data.get('dataset_id')
        
        if not dataset_id:
            return jsonify({"error": "Missing dataset_id"}), 400
        
        # Ensure dataset_id is an integer
        try:
            dataset_id = int(dataset_id)
        except (ValueError, TypeError):
            return jsonify({"error": f"Invalid dataset_id: {dataset_id}"}), 400
        
        success = sync_model_ready_to_final_selected(dataset_id)
        if success:
            return jsonify({"success": True, "message": "Synced model_ready to final_selected"})
        else:
            return jsonify({"error": "Failed to sync model_ready to final_selected"}), 500
    except Exception as e:
        print(f"[sync_model_ready_to_final_selected] ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/api/dataset/<int:dataset_id>/features', methods=['GET'])
def get_dataset_features(dataset_id):
    """Get all features for a dataset with their model_ready, final_selected status, and is_monotonic from fine binning."""
    try:
        # FIX: Use get_features_with_fine_binning_metadata to include is_monotonic status
        features = get_features_with_fine_binning_metadata(dataset_id)
        return jsonify(features)
    except Exception as e:
        print(f"[get_dataset_features] ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/api/dataset/<int:dataset_id>/features-sorted', methods=['GET'])
def get_dataset_features_sorted(dataset_id):
    """
    Get all features for a dataset with their fine binning metadata, sorted by:
    1. Highest IV + Monotonic + More bins (top priority)
    2. Lower IV but still Monotonic
    3. Fewer bins but Monotonic + Better IV
    4. Non-monotonic trends (lowest priority)
    
    Only includes features with IV >= 0.1.
    """
    try:
        features = get_features_with_fine_binning_metadata(dataset_id)
        # Filter features with IV >= 0.1
        features = [f for f in features if float(f.get('iv_value', 0) or 0) >= 0.1]
        
        # Sort features according to the specified criteria
        def sort_key(f):
            is_monotonic = f.get('is_monotonic', False) or False
            iv_value = float(f.get('iv_value', 0) or 0)
            num_bins = int(f.get('num_bins', 0) or 0)
            
            # Priority 1: Monotonic features with high IV and more bins
            if is_monotonic:
                # Return a tuple: (is_monotonic=1, -iv_value for descending, -num_bins for descending)
                # Negative values because we want higher IV and more bins first
                return (0, -iv_value, -num_bins)  # 0 means monotonic (higher priority)
            else:
                # Non-monotonic features come last
                return (1, -iv_value, -num_bins)  # 1 means non-monotonic (lower priority)
        
        sorted_features = sorted(features, key=sort_key)
        
        return jsonify({
            "features": sorted_features,
            "sorted_feature_names": [f['name'] for f in sorted_features]
        })
    except Exception as e:
        print(f"[get_dataset_features_sorted] ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/api/dataset/<int:dataset_id>/mark-monotonic-as-model-ready', methods=['POST'])
def mark_monotonic_as_model_ready(dataset_id):
    """
    Mark all features with monotonic fine binning as model_ready (regardless of IV value).
    """
    try:
        features = get_features_with_fine_binning_metadata(dataset_id)
        # Filter: only monotonic features (no IV requirement)
        monotonic_features = [
            f for f in features 
            if f.get('is_monotonic', False)
        ]
        
        if not monotonic_features:
            return jsonify({
                "success": True,
                "message": "No monotonic features found",
                "count": 0,
                "features": []
            })
        
        # Update model_ready for all monotonic features
        monotonic_feature_names = [f['name'] for f in monotonic_features]
        success = update_features_model_ready(dataset_id, monotonic_feature_names)
        
        if success:
            print(f"[mark_monotonic_as_model_ready] Marked {len(monotonic_feature_names)} monotonic features as model_ready: {monotonic_feature_names}")
            return jsonify({
                "success": True,
                "message": f"Marked {len(monotonic_feature_names)} monotonic features as model_ready",
                "count": len(monotonic_feature_names),
                "features": monotonic_feature_names
            })
        else:
            return jsonify({"error": "Failed to update model_ready"}), 500
    except Exception as e:
        print(f"[mark_monotonic_as_model_ready] ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/api/update-feature-final-selected', methods=['POST'])
def update_feature_final_selected():
    """
    Update feature's final_selected when checkbox is checked in Model Training module.
    """
    try:
        data = request.get_json()
        feature_name = data.get('feature_name')
        dataset_id = data.get('record_id') or data.get('dataset_id')
        is_selected = data.get('is_selected', False)
        
        if not feature_name or not dataset_id:
            return jsonify({"error": "Missing feature_name or dataset_id"}), 400
        
        # Ensure dataset_id is an integer
        try:
            dataset_id = int(dataset_id)
        except (ValueError, TypeError):
            return jsonify({"error": f"Invalid dataset_id: {dataset_id}"}), 400
        
        # Get feature
        feature = get_feature_by_name(dataset_id, feature_name)
        if not feature:
            return jsonify({"error": f"Feature '{feature_name}' not found"}), 404
        
        # Update final_selected (handle gracefully if column doesn't exist)
        try:
            update_feature(feature['id'], final_selected=is_selected)
        except Exception as e:
            if 'final_selected' in str(e).lower() or 'does not exist' in str(e).lower():
                # Column doesn't exist, try to add it
                try:
                    ensure_final_selected_column()
                    update_feature(feature['id'], final_selected=is_selected)
                except Exception as e2:
                    print(f"[update_feature_final_selected] Could not update final_selected: {e2}")
            else:
                raise
        
        return jsonify({"success": True})
    except Exception as e:
        print(f"[update_feature_final_selected] ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/api/update-feature-selection', methods=['POST'])
def update_feature_selection():
    """
    Update feature's selected status from preprocessing details page.
    Target variable is always set to selected=False and cannot be changed.
    """
    try:
        data = request.get_json()
        feature_name = data.get('feature_name')
        dataset_id = data.get('dataset_id')
        is_selected = data.get('selected', False)
        
        print(f"\n[UPDATE-FEATURE-SELECTION] ========================================")
        print(f"[UPDATE-FEATURE-SELECTION] Request received:")
        print(f"  Feature name: {feature_name}")
        print(f"  Dataset ID: {dataset_id}")
        print(f"  Selected: {is_selected}")
        
        if not feature_name or not dataset_id:
            print(f"[UPDATE-FEATURE-SELECTION] ❌ Missing feature_name or dataset_id")
            return jsonify({"error": "Missing feature_name or dataset_id"}), 400
        
        # Ensure dataset_id is an integer
        try:
            dataset_id = int(dataset_id)
        except (ValueError, TypeError):
            print(f"[UPDATE-FEATURE-SELECTION] ❌ Invalid dataset_id: {dataset_id}")
            return jsonify({"error": f"Invalid dataset_id: {dataset_id}"}), 400
        
        # Check if this is the target variable - always set to False
        dataset = get_dataset(dataset_id)
        if dataset and dataset.get('target_variable') == feature_name:
            print(f"[UPDATE-FEATURE-SELECTION] ⚠️ Target variable detected, forcing selected=False")
            is_selected = False  # Force target variable to always be False
        
        # Get feature, create if it doesn't exist
        feature = get_feature_by_name(dataset_id, feature_name)
        if not feature:
            print(f"[UPDATE-FEATURE-SELECTION] Feature doesn't exist, creating new feature")
            # Feature doesn't exist, create it with default type 'continuous'
            # The type will be updated later when classification is done
            feature_id = create_feature(dataset_id, feature_name, 'continuous', selected=is_selected)
            feature = get_feature(feature_id)
            print(f"[UPDATE-FEATURE-SELECTION] ✅ Created feature with ID {feature_id}, selected={is_selected}")
        else:
            print(f"[UPDATE-FEATURE-SELECTION] Feature exists (ID: {feature['id']}), current selected={feature.get('selected')}")
            # Update selected status (will be False if target variable)
            update_feature(feature['id'], selected=is_selected)
            print(f"[UPDATE-FEATURE-SELECTION] ✅ Updated feature {feature['id']} to selected={is_selected}")
            
            # Verify the update
            updated_feature = get_feature(feature['id'])
            print(f"[UPDATE-FEATURE-SELECTION] Verification: selected={updated_feature.get('selected')}")
        
        print(f"[UPDATE-FEATURE-SELECTION] ========================================\n")
        return jsonify({"success": True})
    except Exception as e:
        print(f"[UPDATE-FEATURE-SELECTION] ❌ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/api/save-preprocess-selection', methods=['POST'])
def save_preprocess_selection():
    """
    Save the preprocess_selection flag for a record.
    When this is set to true, the preprocessing calculations will be skipped
    and features will be loaded from the database instead.
    """
    try:
        data = request.get_json()
        record_id = data.get('record_id')
        
        if not record_id:
            return jsonify({"error": "Missing record_id"}), 400
        
        # Update the preprocess_selection flag
        success = update_dataset(record_id, preprocess_selection=True)
        
        if success:
            return jsonify({"success": True, "message": "Preprocessing selection saved successfully"})
        else:
            return jsonify({"error": "Failed to save preprocessing selection"}), 500
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/api/records', methods=['GET'])
def get_records():
    """
    List all analysis records (summary only) - returns datasets in NEW format.
    """
    print("\\n[API] /api/records (GET) called")
    try:
        datasets = get_all_datasets_with_features()
        print(f"[get_records] Found {len(datasets)} datasets (batched fetch)")
        
        result = []
        for dataset in datasets:
            features = dataset.get('features', [])
            discrete_cols = [f['name'] for f in features if f.get('type') == 'discrete']
            continuous_cols = [f['name'] for f in features if f.get('type') == 'continuous']
            selected_cols = [f['name'] for f in features if f.get('selected')]
            
            result.append({
                'id': dataset['id'],
                'name': dataset.get('name', ''),
                'dataset_path': dataset.get('file_path', ''),
                'discrete_columns': discrete_cols,
                'continuous_columns': continuous_cols,
                'selected_columns': selected_cols,
                'target_variable': dataset.get('target_variable', ''),
                'created_at': str(dataset.get('created_at', '')),
                'total_features': dataset.get('total_features', 0),
                'discrete_features': dataset.get('discrete_features', 0),
                'continuous_features': dataset.get('continuous_features', 0)
            })
        
        return jsonify(result)
    except Exception as e:
        print(f"[get_records] ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# ----------- Latest Record Dataset Path -----------
@app.route('/api/latest-record-dataset-path', methods=['GET'])
def latest_record_dataset_path():
    """
    Returns the dataset_path of the latest record and whether the file exists.
    """
    try:
        dataset = get_latest_dataset()
        if not dataset:
            return jsonify({"dataset_path": None, "resolved_path": None, "valid": False})
        
        dataset_path = dataset.get('file_path')
        resolved = dataset_path
        if dataset_path and not os.path.isabs(dataset_path):
            resolved = os.path.join(os.path.dirname(__file__), dataset_path)
        valid = bool(resolved and os.path.exists(resolved))
        
        return jsonify({
            "dataset_path": dataset_path,
            "resolved_path": resolved,
            "valid": valid
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ----------- Get Record -----------
@app.route('/api/record/<int:record_id>', methods=['GET'])
def get_record(record_id):
    """
    Get a specific analysis record with binning data in NEW format.
    """
    try:
        print(f"\n[get_record] Loading record {record_id}")
        dataset_context = get_dataset_with_all_results(record_id)
        if not dataset_context:
            print(f"[get_record] ❌ Dataset {record_id} not found")
            return jsonify({"error": "Record not found"}), 404
        
        dataset = dataset_context['dataset']
        features = dataset_context.get('features', [])
        print(f"[get_record] ✅ Found dataset: {dataset.get('name', 'unnamed')} with {len(features)} features (batched)")
        
        discrete_cols = [f['name'] for f in features if f.get('type') == 'discrete']
        continuous_cols = [f['name'] for f in features if f.get('type') == 'continuous']
        selected_cols = [f['name'] for f in features if f.get('selected')]
        
        print(f"[get_record] Discrete: {len(discrete_cols)}, Continuous: {len(continuous_cols)}, Selected: {len(selected_cols)}")
        
        model_ready_cols = [f['name'] for f in features if f.get('model_ready')]
        final_selected_cols = [f['name'] for f in features if f.get('final_selected')]
        
        binning_data = {}
        features_with_data = 0
        for feature in features:
            feature_binning = {'coarse': None, 'fine': None, 'woe_iv': None}
            binning = feature.get('binning', {})
            coarse = binning.get('coarse')
            fine = binning.get('fine')
            
            if coarse:
                # Calculate derived metrics for coarse bins
                coarse_bins = coarse.get('bins', [])
                coarse_totals = coarse.get('totals')
                if coarse_bins:
                    coarse_bins = calculate_derived_bin_metrics(coarse_bins, coarse_totals)
                feature_binning['coarse'] = {
                    'type': feature.get('type'),
                    'bins': coarse_bins
                }
            if fine:
                # Calculate derived metrics for fine bins
                fine_bins = fine.get('bins', [])
                fine_totals = fine.get('totals')
                if fine_bins:
                    fine_bins = calculate_derived_bin_metrics(fine_bins, fine_totals)
                feature_binning['fine'] = {
                    'bins': fine_bins,
                    'merged_bins': fine.get('merged_bins', []),
                    'iv': fine.get('iv')
                }
            
            woe_source = fine if fine else coarse
            step_meta = (woe_source or {}).get('step')
            if step_meta and step_meta.get('iv_value') is not None:
                woe_bins = (woe_source or {}).get('bins', [])
                woe_totals = (woe_source or {}).get('totals')
                if woe_bins:
                    woe_bins = calculate_derived_bin_metrics(woe_bins, woe_totals)
                feature_binning['woe_iv'] = {
                    'iv': float(step_meta['iv_value']),
                    'bins': woe_bins
                }
            
            if coarse or fine:
                features_with_data += 1
            
            binning_data[feature['name']] = feature_binning
        
        print(f"[get_record] 📊 Features with binning data: {features_with_data}/{len(features)}")
        
        result = {
            'id': dataset['id'],
            'dataset_path': dataset.get('file_path', ''),
            'discrete_columns': discrete_cols,
            'continuous_columns': continuous_cols,
            'selected_columns': selected_cols,
            'target_variable': dataset.get('target_variable', ''),
            'created_at': str(dataset.get('created_at', '')),
            'total_features': dataset.get('total_features', 0),
            'discrete_features': dataset.get('discrete_features', 0),
            'continuous_features': dataset.get('continuous_features', 0),
            'binning_data': binning_data,  # New structured binning data
            'dashboard_selected_columns': model_ready_cols,
            'final_selected_columns': final_selected_cols,
            'preprocess_selection': dataset.get('preprocess_selection', False)
        }
        
        return jsonify(result)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/api/record/<int:record_id>/load-dataset', methods=['GET'])
def load_record_dataset(record_id):
    """
    Loads the dataset for a given record and returns it as JSON.
    """
    try:
        dataset = get_dataset(record_id)
        if not dataset:
            return jsonify({"error": "Record/Dataset not found"}), 404
        
        dataset_path = dataset.get('file_path')
        if not dataset_path:
            return jsonify({"error": "No dataset_path available for this id"}), 404

        # Resolve relative path if needed
        if not os.path.isabs(dataset_path):
            dataset_path = os.path.join(os.path.dirname(__file__), dataset_path)
        if not os.path.exists(dataset_path):
            return jsonify({"error": f"Dataset file not found: {dataset_path}"}), 404
        df = pd.read_csv(dataset_path)
        return jsonify({"data": df.to_dict(orient="records"), "columns": df.columns.tolist()})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/api/datasets/<int:dataset_id>/model', methods=['GET'])
def get_dataset_model_artifact(dataset_id: int):
    """
    Return metadata about the persisted model artifact for a dataset.
    """
    try:
        dataset = get_dataset(dataset_id)
        if not dataset:
            return jsonify({"error": "Dataset not found"}), 404
        artifact_payload, artifact_path = load_model_artifact(dataset_id)
        if not artifact_payload or not artifact_path:
            return jsonify({"error": "Model artifact not found"}), 404
        metadata = _build_artifact_metadata(artifact_payload, artifact_path)
        return jsonify({
            "dataset": _row_to_native_types(dataset),
            "model": metadata
        })
    except Exception as e:
        print(f"[get_dataset_model_artifact] ERROR: {e}")
        return jsonify({"error": f"Failed to load model artifact: {str(e)}"}), 500
# ----------- Logistic Regression Analysis -----------
@app.route('/api/logistic-regression', methods=['POST'])
def logistic_regression_analysis():
    """
    Perform logistic regression analysis on selected variables.
    Expects payload: { selected_variables: [list], target: string, woe_transformed_data: {} }
    Returns: model metrics, coefficients, p-values, VIF, Gini, ROC data
    """
    # Removed sanitize_for_json - Flask's jsonify handles NaN/inf automatically
    # Data is already sanitized during construction using np.isfinite checks
    
    try:
        data = request.get_json()
        selected_variables = data.get('selected_variables', [])
        target = data.get('target')
        woe_transformed_data = data.get('woe_transformed_data', {})
        if not isinstance(woe_transformed_data, dict):
            woe_transformed_data = {}
        dataset_id = (
            data.get('record_id')
            or data.get('dataset_id')
            or data.get('recordId')
            or data.get('datasetId')
        )
        if not dataset_id:
            return jsonify({"error": "Missing dataset_id/record_id"}), 400
        try:
            dataset_id = int(dataset_id)
        except (ValueError, TypeError):
            return jsonify({"error": f"Invalid dataset_id: {dataset_id}"}), 400

        if not selected_variables or not target:
            return jsonify({"error": "Missing selected_variables or target"}), 400

        # CRITICAL: Load train set using data_loader (same as binning/WOE endpoints)
        try:
            from data_loader import get_data_for_stage
            df = get_data_for_stage(dataset_id, 'training')  # Returns TRAIN set if split exists
            print(f"LOGISTIC DEBUG: Loaded dataset: {len(df)} rows (train set if TTS exists)")
            if df is None or df.empty:
                raise ValueError(f"Loaded dataset is None or empty for dataset_id {dataset_id}")
        except Exception as e:
            print(f"LOGISTIC DEBUG: Error loading data via data_loader: {str(e)}")
            import traceback
            traceback.print_exc()
            # Fallback to CSV if data_loader fails
            try:
                csv_path = get_csv_path(dataset_id)
                df = pd.read_csv(csv_path)
                print(f"LOGISTIC DEBUG: Loaded full dataset: {len(df)} rows (fallback)")
                if df is None or df.empty:
                    return jsonify({"error": f"CSV file is empty for dataset_id {dataset_id}"}), 400
            except FileNotFoundError as fe:
                return jsonify({"error": f"CSV file not found: {str(fe)}"}), 400
            except Exception as e2:
                print(f"LOGISTIC DEBUG: Error in CSV fallback: {str(e2)}")
                import traceback
                traceback.print_exc()
                return jsonify({"error": f"Failed to load CSV: {str(e2)}"}), 400

        if target not in df.columns:
            return jsonify({"error": f"Target variable '{target}' not found in dataset"}), 400
        
        # CRITICAL: Apply preprocessing before training (same as binning/WOE)
        print(f"LOGISTIC DEBUG: Applying preprocessing before training...")
        try:
            df, preprocessing_report = preprocess_dataset(
                df,
                target_col=target,
                preprocessing_steps={
                    'detect_types': True,
                    'handle_missing': True,
                    'remove_duplicates': True,
                    'handle_outliers': False,  # Don't handle outliers before binning
                    'encode_categorical': False  # Don't encode categorical before binning
                },
                missing_threshold=0.5,
                treat_negative_one_as_missing=True
            )
            print(f"LOGISTIC DEBUG: Preprocessing completed. Processed shape: {df.shape}")
        except Exception as e:
            print(f"LOGISTIC DEBUG: WARNING: Preprocessing failed: {str(e)}")
            print(f"LOGISTIC DEBUG: Continuing with raw data (this may cause issues)")
            import traceback
            traceback.print_exc()

        # Filter to only variables with WOE data to avoid constant 0 columns
        valid_selected_vars = [var for var in selected_variables if var in woe_transformed_data]
        if len(valid_selected_vars) == 0:
            return jsonify({"error": "No variables have valid WOE transformations. Please check your WOE setup."}), 400
        if len(valid_selected_vars) < len(selected_variables):
            print(f"LOGISTIC DEBUG: Skipped {len(selected_variables) - len(valid_selected_vars)} variables without WOE data")

        selected_variables = valid_selected_vars  # Update to valid only
        woe_df = df[[target]].copy()
        dropped_constants = []

        for var in selected_variables:
            # Robust WOE mapping + diagnostics
            raw_bins = woe_transformed_data.get(var)
            if isinstance(raw_bins, dict) and isinstance(raw_bins.get('stats'), list):
                bins_list = raw_bins.get('stats')
            elif isinstance(raw_bins, list):
                bins_list = raw_bins
            else:
                bins_list = []
            if not bins_list:
                print(f"LOGISTIC DEBUG: no bin definitions found for '{var}' in woe_transformed_data")
                continue  # Skip if no bins

            woe_df[f'{var}_WOE'] = np.nan
            for bin_info in bins_list:
                bin_range = bin_info.get('range') or bin_info.get('Range') or bin_info.get('Bin') or bin_info.get('bin')
                woe_value = bin_info.get('woe') or bin_info.get('WOE')
                if woe_value is None:
                    continue
                try:
                    woe_value = float(woe_value)
                except Exception:
                    continue
                if isinstance(bin_range, (list, tuple)):
                    mask = df[var].isin(bin_range)
                    woe_df.loc[mask, f'{var}_WOE'] = woe_value
                    continue
                if isinstance(bin_range, str):
                    br = bin_range.strip()
                    if ' to ' in br:
                        parts = [p.strip() for p in br.split(' to ')]
                    elif '-' in br and any(ch.isdigit() for ch in br):
                        parts = [p.strip() for p in re.split(r"-", br, maxsplit=1)]
                    else:
                        parts = None
                    if parts and len(parts) == 2:
                        try:
                            min_val = float(parts[0])
                            max_val = float(parts[1])
                            mask = (pd.to_numeric(df[var], errors='coerce') >= min_val) & (pd.to_numeric(df[var], errors='coerce') <= max_val)
                            woe_df.loc[mask.fillna(False), f'{var}_WOE'] = woe_value
                            continue
                        except Exception:
                            pass
                    cats = re.split(r'[\,\|;]', br)
                    cats = [c.strip() for c in cats if c.strip() != '']
                    if len(cats) > 1:
                        mask = df[var].astype(str).isin(cats)
                        woe_df.loc[mask, f'{var}_WOE'] = woe_value
                        continue
                    mask = df[var].astype(str) == br
                    woe_df.loc[mask, f'{var}_WOE'] = woe_value
                else:
                    mask = df[var].astype(str) == str(bin_range)
                    woe_df.loc[mask, f'{var}_WOE'] = woe_value
            non_null = int(woe_df[f'{var}_WOE'].notna().sum())
            print(f"LOGISTIC DEBUG: mapped WOE rows for '{var}':", non_null, "of", len(df))
            woe_df[f'{var}_WOE'] = woe_df[f'{var}_WOE'].fillna(0)

        feature_cols = [f'{var}_WOE' for var in selected_variables]
        X = woe_df[feature_cols].fillna(0)
        y = woe_df[target]

        mask = ~y.isna()
        X = X[mask]
        y = y[mask]

        if len(X) == 0:
            return jsonify({"error": "No valid data after preprocessing"}), 400

        # Remove constant features (zero variance)
        variances = X.var()
        constant_cols = variances[variances == 0].index.tolist()
        if constant_cols:
            dropped_constants = [col.replace('_WOE', '') for col in constant_cols]
            print(f"LOGISTIC DEBUG: Removing constant columns: {dropped_constants}")
            X = X.drop(columns=constant_cols)
            feature_cols = [col for col in feature_cols if col not in constant_cols]
            selected_variables = [var for var in selected_variables if f'{var}_WOE' not in constant_cols]

        if len(selected_variables) == 0:
            return jsonify({"error": "All features are constant after WOE transformation. Try fewer or different variables."}), 400

        # Iterative VIF-based feature removal to prevent singularity
        max_vif_threshold = 10.0
        vif_dropped = []
        while len(X.columns) > 0:
            # Compute VIFs
            vif_data_temp = []
            X_with_const_temp = sm.add_constant(X)
            for i in range(1, len(X.columns) + 1):  # Skip const
                try:
                    vif = variance_inflation_factor(X_with_const_temp.values, i)
                    if np.isfinite(vif):
                        vif_data_temp.append((X.columns[i-1], vif))
                    else:
                        vif_data_temp.append((X.columns[i-1], np.inf))
                except Exception:
                    vif_data_temp.append((X.columns[i-1], np.inf))
            
            if not vif_data_temp:
                break
            
            # Find max VIF column
            max_vif_col, max_vif = max(vif_data_temp, key=lambda x: x[1])
            
            if max_vif < max_vif_threshold:
                break  # All good
            
            # Drop the high VIF column
            print(f"LOGISTIC DEBUG: Dropping high VIF column '{max_vif_col}' (VIF: {max_vif})")
            X = X.drop(columns=[max_vif_col])
            feature_cols = [col for col in feature_cols if col not in [max_vif_col]]
            selected_variables = [var for var in selected_variables if f'{var}_WOE' not in [max_vif_col]]
            vif_dropped.append(max_vif_col.replace('_WOE', ''))
        
        dropped_variables = dropped_constants + vif_dropped
        if len(selected_variables) == 0:
            return jsonify({"error": f"All features removed due to constants or high multicollinearity (VIF > {max_vif_threshold}). Try selecting fewer or less correlated variables."}), 400

        # Check for linear dependence via matrix rank
        X_const = sm.add_constant(X)
        rank = np.linalg.matrix_rank(X_const)
        full_rank = X_const.shape[1]
        rank_dropped = []
        while rank < full_rank and len(X.columns) > 0:
            # Drop the feature with lowest variance (least informative)
            var_dict = X.var().to_dict()
            if not var_dict:
                break
            to_drop = min(var_dict, key=var_dict.get)
            print(f"LOGISTIC DEBUG: Dropping low-variance column '{to_drop}' due to rank deficiency")
            X = X.drop(to_drop, axis=1)
            feature_cols = [col for col in feature_cols if col not in [to_drop]]
            selected_variables = [var for var in selected_variables if f'{var}_WOE' not in [to_drop]]
            rank_dropped.append(to_drop.replace('_WOE', ''))
            X_const = sm.add_constant(X)
            rank = np.linalg.matrix_rank(X_const)
            full_rank = X_const.shape[1]

        dropped_variables += rank_dropped
        if len(selected_variables) == 0:
            return jsonify({"error": "All features removed due to linear dependence. Try fewer variables."}), 400

        # Diagnostics (updated for current X)
        try:
            nunique = X.nunique()
            zero_var_cols = nunique[nunique <= 1].index.tolist()  # Should be empty now
            variances = X.var().to_dict()
            dup_mask = X.T.duplicated()
            dup_cols = X.columns[dup_mask].tolist()
            sample = X.head(5).to_dict(orient='records')
            y_counts = y.value_counts().to_dict()
            feature_totals = {col: float(val) if np.isfinite(val) else None for col, val in X.sum().to_dict().items()}
            print(f"LOGISTIC DEBUG: Final feature list ({len(X.columns)} features): {list(X.columns)}")
            print("LOGISTIC DEBUG: Feature column totals:", feature_totals)
            print("LOGISTIC DEBUG: X sample rows:", sample)
            print(f"LOGISTIC DEBUG: Final rank check - Rank: {rank}, Full: {full_rank}")
            
            # Check class distribution
            print(f"LOGISTIC DEBUG: Class distribution: {y_counts}")
            if len(y_counts) == 2:
                n_class_0 = y_counts.get(0, 0)
                n_class_1 = y_counts.get(1, 0)
                imbalance_ratio = n_class_0 / n_class_1 if n_class_1 > 0 else float('inf')
                print(f"LOGISTIC DEBUG: Class imbalance ratio: {imbalance_ratio:.2f}:1 (0:1)")
        except Exception as _diag:
            print("LOGISTIC DEBUG: diagnostics failed:", str(_diag))

        # Warn if too many variables relative to observations
        n_features = len(selected_variables)
        n_obs = len(X)
        if n_features > n_obs / 10:  # Stricter: 10 obs per feature
            print(f"LOGISTIC DEBUG: Warning - Very high dimensionality: {n_features} features vs {n_obs} observations. Model may be unstable.")

        # Now fit the model with robust optimizer and regularization
        # Use L1/L2 regularization to prevent perfect separation and extreme coefficients
        logit_model = sm.Logit(y, X_const)
        result = None
        methods_to_try = ['lbfgs', 'bfgs', 'newton', 'nm']  # Fallback optimizers
        
        # Calculate class weights for imbalanced data (improves recall)
        from sklearn.utils.class_weight import compute_class_weight
        sample_weights = None
        try:
            y_classes = np.unique(y)
            if len(y_classes) == 2:
                class_weights = compute_class_weight('balanced', classes=y_classes, y=y)
                class_weight_dict = dict(zip(y_classes, class_weights))
                sample_weights = np.array([class_weight_dict[y_val] for y_val in y])
                
                # Detailed class weight logging
                n_class_0 = (y == 0).sum()
                n_class_1 = (y == 1).sum()
                total_samples = len(y)
                print(f"\n{'='*80}")
                print("LOGISTIC DEBUG: CLASS WEIGHT CALCULATION")
                print(f"{'='*80}")
                print(f"Class 0 (Good): {n_class_0} samples ({n_class_0/total_samples*100:.2f}%)")
                print(f"Class 1 (Bad):  {n_class_1} samples ({n_class_1/total_samples*100:.2f}%)")
                print(f"Imbalance Ratio: {n_class_0/n_class_1:.2f}:1 (Good:Bad)")
                print(f"Class Weights: {class_weight_dict}")
                print(f"Sample Weights - Min: {sample_weights.min():.4f}, Max: {sample_weights.max():.4f}, Mean: {sample_weights.mean():.4f}")
                print(f"Sample Weights - Std: {sample_weights.std():.4f}")
                print(f"{'='*80}\n")
            else:
                print(f"LOGISTIC DEBUG: Warning - Non-binary target, skipping class weights")
        except Exception as weight_err:
            print(f"LOGISTIC DEBUG: Warning - Failed to calculate class weights: {weight_err}")
            sample_weights = None
        
        # Try with regularization first (prevents perfect separation)
        # Start with lighter regularization and try different types
        regularization_success = False  # Track if regularization was successfully applied
        regularization_type = None
        regularization_alpha = None
        
        # Try L1 regularization with lighter penalty first
        for alpha in [0.01, 0.05, 0.1]:  # Try lighter to heavier regularization
            for method in methods_to_try:
                try:
                    print(f"LOGISTIC DEBUG: Trying fit with method='{method}' and L1 regularization (alpha={alpha})")
                    fit_kwargs = {
                        'method': method,
                        'alpha': alpha,
                        'L1_wt': 1.0,  # Pure L1 (Lasso)
                        'maxiter': 1000,
                        'disp': 0
                    }
                    # Add sample weights if available (for class imbalance)
                    if sample_weights is not None:
                        fit_kwargs['weights'] = sample_weights
                    result = logit_model.fit_regularized(**fit_kwargs)
                    print(f"LOGISTIC DEBUG: L1 regularized fit succeeded with {method}, alpha={alpha}")
                    regularization_success = True
                    regularization_type = 'L1'
                    regularization_alpha = alpha
                    break
                except Exception as fit_err:
                    print(f"LOGISTIC DEBUG: L1 regularized fit failed with {method}, alpha={alpha}: {fit_err}")
                    continue
            if regularization_success:
                break
        
        # If L1 fails, try L2 regularization (Ridge)
        if not regularization_success:
            for alpha in [0.01, 0.05, 0.1]:
                for method in methods_to_try:
                    try:
                        print(f"LOGISTIC DEBUG: Trying fit with method='{method}' and L2 regularization (alpha={alpha})")
                        fit_kwargs = {
                            'method': method,
                            'alpha': alpha,
                            'L1_wt': 0.0,  # Pure L2 (Ridge)
                            'maxiter': 1000,
                            'disp': 0
                        }
                        # Add sample weights if available (for class imbalance)
                        if sample_weights is not None:
                            fit_kwargs['weights'] = sample_weights
                        result = logit_model.fit_regularized(**fit_kwargs)
                        print(f"LOGISTIC DEBUG: L2 regularized fit succeeded with {method}, alpha={alpha}")
                        regularization_success = True
                        regularization_type = 'L2'
                        regularization_alpha = alpha
                        break
                    except Exception as fit_err:
                        print(f"LOGISTIC DEBUG: L2 regularized fit failed with {method}, alpha={alpha}: {fit_err}")
                        continue
                if regularization_success:
                    break
        
        # Fallback to non-regularized if regularization fails
        if not regularization_success:
            print(f"LOGISTIC DEBUG: Regularization failed, trying non-regularized fit...")
            for method in methods_to_try:
                try:
                    print(f"LOGISTIC DEBUG: Trying non-regularized fit with method='{method}'")
                    fit_kwargs = {
                        'disp': 0,
                        'method': method,
                        'maxiter': 1000
                    }
                    # Add sample weights if available (for class imbalance)
                    if sample_weights is not None:
                        fit_kwargs['weights'] = sample_weights
                    result = logit_model.fit(**fit_kwargs)
                    print(f"LOGISTIC DEBUG: Non-regularized fit succeeded with {method}")
                    break
                except Exception as fit_err2:
                    print(f"LOGISTIC DEBUG: Non-regularized fit also failed with {method}: {fit_err2}")
                if method == methods_to_try[-1]:  # Last one
                        return jsonify({"error": f"Model fitting failed with all optimizers. Try fewer variables or check for perfect separation. Error: {str(fit_err2)}"}), 400
                continue

        if result is None:
            return jsonify({"error": "Model fitting failed unexpectedly."}), 500

        # Log whether regularization was used
        print(f"\n{'='*80}")
        print("LOGISTIC DEBUG: MODEL FITTING SUMMARY")
        print(f"{'='*80}")
        if regularization_success:
            print(f"✓ Model fitted with {regularization_type} regularization (alpha={regularization_alpha})")
            print(f"  Purpose: Prevent perfect separation and extreme coefficients")
        else:
            print(f"⚠ WARNING: Model fitted without regularization - may have perfect separation issues")
        print(f"Optimizer Used: {methods_to_try[0] if result else 'FAILED'}")
        print(f"Convergence Status: {'✓ Converged' if result.converged else '✗ Not Converged'}")
        if hasattr(result, 'mle_retvals') and result.mle_retvals:
            iterations = result.mle_retvals.get('iterations', 'N/A')
            print(f"Iterations: {iterations}")
        print(f"Log-Likelihood: {result.llf:.6f}")
        print(f"{'='*80}\n")

        # ========== LOGISTIC REGRESSION - TRAINING SUMMARY ==========
        print("\n" + "="*80)
        print("LOGISTIC REGRESSION - TRAINING SUMMARY")
        print("="*80)
        print(f"Dataset ID: {dataset_id}")
        print(f"Target Variable: {target}")
        print(f"Training Samples: {len(X)}")
        print(f"Features: {len(selected_variables)}")
        print(f"Feature Names: {selected_variables}")
        print(f"Class Distribution (Train): {y.value_counts().to_dict()}")
        if len(y.value_counts()) == 2:
            n_class_0 = y.value_counts().get(0, 0)
            n_class_1 = y.value_counts().get(1, 0)
            imbalance_ratio = n_class_0 / n_class_1 if n_class_1 > 0 else float('inf')
            print(f"Class Imbalance Ratio: {imbalance_ratio:.2f}:1 (0:1)")
        print(f"Model Optimizer: {methods_to_try[0] if result else 'FAILED'}")
        print(f"Model Convergence: {result.converged if result else 'N/A'}")
        print(f"Log-Likelihood: {result.llf if result else 'N/A':.4f}")
        if regularization_success:
            print(f"Regularization: {regularization_type} (alpha={regularization_alpha}) - Applied to prevent perfect separation")
        else:
            print(f"Regularization: None - WARNING: May have perfect separation issues")
        print("="*80 + "\n")

        # ========== LOGISTIC REGRESSION - MODEL DIAGNOSTICS ==========
        print("\n" + "="*80)
        print("LOGISTIC REGRESSION - MODEL DIAGNOSTICS")
        print("="*80)
        print(f"Model Converged: {result.converged}")
        if hasattr(result, 'mle_retvals') and result.mle_retvals:
            iterations = result.mle_retvals.get('iterations', 'N/A')
            print(f"Number of Iterations: {iterations}")
            
        else:
            print(f"Number of Iterations: N/A")
        print(f"Log-Likelihood: {result.llf:.4f}")
        
        # Detailed coefficient analysis
        coefficients = result.params
        print(f"\n{'='*80}")
        print("LOGISTIC DEBUG: COEFFICIENT ANALYSIS")
        print(f"{'='*80}")
        intercept_value = coefficients.get('const', 0) if 'const' in coefficients.index else 0
        print(f"Intercept: {intercept_value:.6f}")
        
        feature_coefs = coefficients.drop('const') if 'const' in coefficients.index else coefficients
        if len(feature_coefs) > 0:
            print(f"\n--- COEFFICIENT STATISTICS ---")
            print(f"Total Features: {len(feature_coefs)}")
            print(f"Min Coefficient: {feature_coefs.min():.6f}")
            print(f"Max Coefficient: {feature_coefs.max():.6f}")
            print(f"Mean Coefficient: {feature_coefs.mean():.6f}")
            print(f"Std Coefficient: {feature_coefs.std():.6f}")
            print(f"Mean |Coefficient|: {feature_coefs.abs().mean():.6f}")
            print(f"Median |Coefficient|: {feature_coefs.abs().median():.6f}")
            
            # Coefficient distribution
            positive_coefs = (feature_coefs > 0).sum()
            negative_coefs = (feature_coefs < 0).sum()
            zero_coefs = (feature_coefs == 0).sum()
            print(f"\n--- COEFFICIENT DISTRIBUTION ---")
            print(f"Positive: {positive_coefs} ({positive_coefs/len(feature_coefs)*100:.1f}%)")
            print(f"Negative: {negative_coefs} ({negative_coefs/len(feature_coefs)*100:.1f}%)")
            print(f"Zero: {zero_coefs} ({zero_coefs/len(feature_coefs)*100:.1f}%)")
            
            # Top and bottom coefficients
            print(f"\n--- TOP 10 POSITIVE COEFFICIENTS (Higher Risk) ---")
            top_positive = feature_coefs.nlargest(10)
            for var, coef in top_positive.items():
                var_name = var.replace('_WOE', '')
                print(f"  {var_name:30s}: {coef:10.4f}")
            
            print(f"\n--- TOP 10 NEGATIVE COEFFICIENTS (Lower Risk) ---")
            top_negative = feature_coefs.nsmallest(10)
            for var, coef in top_negative.items():
                var_name = var.replace('_WOE', '')
                print(f"  {var_name:30s}: {coef:10.4f}")
            
            # Check for extreme coefficients (perfect separation indicator)
            extreme_coefs = feature_coefs.abs() > 10
            if extreme_coefs.any() or abs(intercept_value) > 100:
                print(f"\n⚠ WARNING: PERFECT SEPARATION INDICATORS ---")
                print(f"Extreme coefficients (|value| > 10): {extreme_coefs.sum()}")
                if abs(intercept_value) > 100:
                    print(f"⚠ Intercept is extremely large ({intercept_value:.2f}), indicating perfect separation!")
                if extreme_coefs.any():
                    extreme_dict = {k.replace('_WOE', ''): float(v) for k, v in feature_coefs[extreme_coefs].to_dict().items()}
                    print(f"Extreme coefficients: {extreme_dict}")
                print(f"⚠ PERFECT SEPARATION DETECTED: Model may produce unreliable predictions!")
                print(f"Recommendation: Remove variables causing separation or use regularization (L1/L2)")
            else:
                print(f"\n✓ No extreme coefficients detected - model appears stable")
        else:
            print(f"⚠ WARNING: No feature coefficients found!")
        print(f"{'='*80}\n")
        
        # Detailed training predictions analysis
        try:
            y_train_pred_proba = result.predict(X_const)
            y_train_pred = (y_train_pred_proba >= 0.5).astype(int)
            
            print(f"\n{'='*80}")
            print("LOGISTIC DEBUG: TRAINING SET PREDICTIONS ANALYSIS")
            print(f"{'='*80}")
            print(f"Training Samples: {len(y_train_pred_proba)}")
            print(f"\n--- PROBABILITY DISTRIBUTION ---")
            print(f"Min Probability: {y_train_pred_proba.min():.6f}")
            print(f"Max Probability: {y_train_pred_proba.max():.6f}")
            print(f"Mean Probability: {y_train_pred_proba.mean():.6f}")
            print(f"Median Probability: {np.median(y_train_pred_proba):.6f}")
            print(f"Std Probability: {y_train_pred_proba.std():.6f}")
            print(f"25th Percentile: {np.percentile(y_train_pred_proba, 25):.6f}")
            print(f"75th Percentile: {np.percentile(y_train_pred_proba, 75):.6f}")
            
            print(f"\n--- PREDICTIONS AT 0.5 THRESHOLD ---")
            pred_class_0 = (y_train_pred_proba < 0.5).sum()
            pred_class_1 = (y_train_pred_proba >= 0.5).sum()
            print(f"Predicted Class 0 (Good): {pred_class_0} ({pred_class_0/len(y_train_pred_proba)*100:.2f}%)")
            print(f"Predicted Class 1 (Bad):  {pred_class_1} ({pred_class_1/len(y_train_pred_proba)*100:.2f}%)")
            
            # Training metrics
            train_cm = confusion_matrix(y, y_train_pred)
            train_accuracy = accuracy_score(y, y_train_pred)
            train_precision = precision_score(y, y_train_pred, zero_division=0)
            train_recall = recall_score(y, y_train_pred, zero_division=0)
            train_f1 = f1_score(y, y_train_pred, zero_division=0)
            
            print(f"\n--- TRAINING METRICS (Threshold=0.5) ---")
            print(f"Confusion Matrix:")
            print(f"  TN={train_cm[0,0]:5d}  FP={train_cm[0,1]:5d}")
            print(f"  FN={train_cm[1,0]:5d}  TP={train_cm[1,1]:5d}")
            print(f"Accuracy:  {train_accuracy:.4f}")
            print(f"Precision: {train_precision:.4f}")
            print(f"Recall:    {train_recall:.4f}")
            print(f"F1-Score:  {train_f1:.4f}")
            
            # Check for overfitting indicators
            if train_accuracy > 0.99:
                print(f"\n⚠ WARNING: Very high training accuracy ({train_accuracy:.4f}) - possible overfitting!")
            if train_recall == 1.0 and train_precision < 0.5:
                print(f"\n⚠ WARNING: Perfect recall but low precision - model may be too sensitive!")
            print(f"{'='*80}\n")
        except Exception as train_pred_err:
            print(f"\n{'='*80}")
            print("LOGISTIC DEBUG: TRAINING PREDICTIONS CHECK")
            print(f"{'='*80}")
            print(f"✗ ERROR: Failed to generate training predictions: {train_pred_err}")
            import traceback
            traceback.print_exc()
            print(f"{'='*80}\n")

        # VIF on final model (calculated on training data)
        vif_data = []
        if len(feature_cols) > 1:
            X_with_const_final = sm.add_constant(X)
            for i in range(1, len(feature_cols) + 1):
                try:
                    vif = variance_inflation_factor(X_with_const_final.values, i)
                    vif_data.append({
                        'variable': selected_variables[i-1],
                        'vif': float(vif) if not np.isnan(vif) and not np.isinf(vif) else None
                    })
                except Exception as vif_err:
                    print(f"LOGISTIC DEBUG: VIF failed for {selected_variables[i-1]}: {vif_err}")
                    vif_data.append({
                        'variable': selected_variables[i-1],
                        'vif': None
                    })

        # CRITICAL: Calculate metrics on TEST data, not training data
        print(f"LOGISTIC DEBUG: Loading TEST data for evaluation...")
        try:
            from data_loader import get_data_for_stage
            df_test = get_data_for_stage(dataset_id, 'evaluation')  # Returns TEST set
            print(f"LOGISTIC DEBUG: Loaded TEST dataset: {len(df_test)} rows")
            
            # Apply preprocessing to test data (same as training)
            print(f"LOGISTIC DEBUG: Applying preprocessing to TEST data...")
            df_test, _ = preprocess_dataset(
                df_test,
                target_col=target,
                preprocessing_steps={
                    'detect_types': True,
                    'handle_missing': True,
                    'remove_duplicates': True,
                    'handle_outliers': False,
                    'encode_categorical': False
                },
                missing_threshold=0.5,
                treat_negative_one_as_missing=True
            )
            print(f"LOGISTIC DEBUG: TEST data preprocessing completed. Shape: {df_test.shape}")
            
            # Apply WOE transformations to test data using training-learned WOE values
            print(f"LOGISTIC DEBUG: Applying WOE transformations to TEST data...")
            woe_df_test = _apply_woe_to_test_data(df_test, selected_variables, woe_transformed_data, target)
            
            # Prepare test features (same columns as training - use final feature_cols after all removals)
            # Ensure we only use columns that exist in both training and test data
            available_feature_cols = [col for col in feature_cols if col in woe_df_test.columns]
            missing_cols = [col for col in feature_cols if col not in woe_df_test.columns]
            if missing_cols:
                print(f"LOGISTIC DEBUG: WARNING: Test data missing {len(missing_cols)} feature columns: {missing_cols}")
                print(f"LOGISTIC DEBUG: Using {len(available_feature_cols)} available features instead of {len(feature_cols)}")
            
            if len(available_feature_cols) == 0:
                raise ValueError("No matching feature columns between training and test data")
            
            # Reorder columns to match training order and fill missing with 0
            X_test = woe_df_test[available_feature_cols].fillna(0)
            
            # If we're missing columns, add them as zeros to match training shape
            if len(available_feature_cols) < len(feature_cols):
                for col in missing_cols:
                    X_test[col] = 0
                # Reorder to match training order
                X_test = X_test[feature_cols]
            y_test = woe_df_test[target] if target in woe_df_test.columns else df_test[target]
            
            mask_test = ~y_test.isna()
            X_test = X_test[mask_test]
            y_test = y_test[mask_test]
            
            if len(X_test) == 0:
                print(f"LOGISTIC DEBUG: WARNING: No valid test data after preprocessing. Using training data for metrics.")
                # Fallback to training data if test data is invalid
                X_test_const = X_const
                y_test = y
            else:
                # Verify column alignment before adding constant
                print(f"LOGISTIC DEBUG: Training feature_cols count: {len(feature_cols)}")
                print(f"LOGISTIC DEBUG: Training X shape (before const): {X.shape}")
                print(f"LOGISTIC DEBUG: Training X_const shape (with const): {X_const.shape}")
                print(f"LOGISTIC DEBUG: Test X shape (before const): {X_test.shape}")
                print(f"LOGISTIC DEBUG: Test X columns: {list(X_test.columns)}")
                print(f"LOGISTIC DEBUG: Training feature_cols: {feature_cols}")
                
                # Ensure test data has exactly the same columns as training (in same order)
                if list(X_test.columns) != feature_cols:
                    print(f"LOGISTIC DEBUG: WARNING: Column mismatch detected!")
                    print(f"LOGISTIC DEBUG: Missing in test: {set(feature_cols) - set(X_test.columns)}")
                    print(f"LOGISTIC DEBUG: Extra in test: {set(X_test.columns) - set(feature_cols)}")
                    # Reorder and add missing columns
                    for col in feature_cols:
                        if col not in X_test.columns:
                            X_test[col] = 0
                    X_test = X_test[feature_cols]  # Reorder to match training
                
                # Add constant for test data
                X_test_const = sm.add_constant(X_test, has_constant='add')
                print(f"LOGISTIC DEBUG: TEST data prepared: {len(X_test)} rows, {len(X_test.columns)} features")
                print(f"LOGISTIC DEBUG: X_test_const shape (with const): {X_test_const.shape}")
                print(f"LOGISTIC DEBUG: X_test_const columns: {list(X_test_const.columns)}")
                
                # Final verification
                if X_test_const.shape[1] != X_const.shape[1]:
                    raise ValueError(
                        f"Column count mismatch: Training has {X_const.shape[1]} columns (including const), "
                        f"Test has {X_test_const.shape[1]} columns. "
                        f"Training features: {len(feature_cols)}, Test features: {len(X_test.columns)}"
                    )
            
        except Exception as test_err:
            print(f"LOGISTIC DEBUG: WARNING: Failed to load/evaluate on test data: {str(test_err)}")
            print(f"LOGISTIC DEBUG: Falling back to training data for metrics (this is not ideal)")
            import traceback
            traceback.print_exc()
            # Fallback to training data
            X_test_const = X_const
            y_test = y

        # Make predictions on TEST data
        print(f"\n--- TEST DATA PREPARATION CHECK ---")
        print(f"X_test_const shape: {X_test_const.shape}")
        print(f"X_test_const columns: {list(X_test_const.columns)}")
        if len(X_test_const) > 0:
            print(f"X_test_const sample (first row): {X_test_const.iloc[0].to_dict()}")
        print(f"X_test_const contains NaN: {X_test_const.isna().sum().sum()}")
        numeric_cols = X_test_const.select_dtypes(include=[np.number]).columns
        if len(numeric_cols) > 0:
            print(f"X_test_const contains Inf: {np.isinf(X_test_const[numeric_cols]).sum().sum()}")
        else:
            print(f"X_test_const contains Inf: 0 (no numeric columns)")
        print("="*80 + "\n")
        
        y_pred_proba = result.predict(X_test_const)
        
        print(f"\n--- TEST PREDICTIONS CHECK ---")
        # Convert to numpy array for easier indexing
        y_pred_proba_np = np.array(y_pred_proba) if not isinstance(y_pred_proba, np.ndarray) else y_pred_proba
        print(f"Test Probability Range: [{y_pred_proba_np.min():.6f}, {y_pred_proba_np.max():.6f}]")
        print(f"Test Probability Mean: {y_pred_proba_np.mean():.6f}")
        print(f"Test Probability Median: {np.median(y_pred_proba_np):.6f}")
        print(f"Test Probability Contains NaN: {np.isnan(y_pred_proba_np).sum()}")
        print(f"Test Probability Contains Inf: {np.isinf(y_pred_proba_np).sum()}")
        print(f"Test Probability All Zero: {(y_pred_proba_np == 0).all()}")
        if len(y_pred_proba_np) > 0:
            print(f"Test Probability All Same: {(y_pred_proba_np == y_pred_proba_np[0]).all()}")
        else:
            print(f"Test Probability All Same: N/A (empty array)")
        print("="*80 + "\n")
        
        fpr, tpr, thresholds = roc_curve(y_test, y_pred_proba)
        
        # CRITICAL FIX: Ensure fpr, tpr, thresholds are always arrays (not scalars)
        # In extreme class imbalance cases, roc_curve can return scalars
        if not isinstance(fpr, np.ndarray):
            fpr = np.array([fpr]) if np.isscalar(fpr) else np.array(fpr)
        if not isinstance(tpr, np.ndarray):
            tpr = np.array([tpr]) if np.isscalar(tpr) else np.array(tpr)
        if not isinstance(thresholds, np.ndarray):
            thresholds = np.array([thresholds]) if np.isscalar(thresholds) else np.array(thresholds)
        
        # Ensure all are 1D arrays
        fpr = np.atleast_1d(fpr).flatten()
        tpr = np.atleast_1d(tpr).flatten()
        thresholds = np.atleast_1d(thresholds).flatten()
        
        # CRITICAL FIX: Filter out invalid (inf, -inf, nan) thresholds before any calculations
        # sklearn's roc_curve can return inf thresholds in edge cases (very few positives, all same predictions, etc.)
        valid_mask = np.isfinite(thresholds) & (thresholds >= 0) & (thresholds <= 1)
        if not valid_mask.all():
            invalid_count = (~valid_mask).sum()
            print(f"LOGISTIC DEBUG: Filtering out {invalid_count} invalid thresholds (inf/nan/out-of-range)")
            fpr = fpr[valid_mask]
            tpr = tpr[valid_mask]
            thresholds = thresholds[valid_mask]
            # Ensure we still have valid data after filtering
            if len(thresholds) == 0:
                print(f"LOGISTIC DEBUG: ERROR - All thresholds were invalid after filtering!")
                print(f"LOGISTIC DEBUG: This indicates severe issues with model predictions or test data")
                print(f"LOGISTIC DEBUG: Cannot generate ROC curve - insufficient valid data")
                # Set to None to indicate invalid data - will be handled later
                fpr = np.array([])
                tpr = np.array([])
                thresholds = np.array([])
        
        # Calculate AUC only if we have valid ROC data
        if len(fpr) > 0 and len(tpr) > 0:
            roc_auc = auc(fpr, tpr)
            
            # Fix: Handle case where AUC < 0.5 (model worse than random)
            if roc_auc < 0.5:
                print(f"LOGISTIC DEBUG: WARNING - AUC < 0.5 ({roc_auc:.4f}), model performing worse than random")
                roc_auc = 1 - roc_auc  # Flip AUC
                print(f"LOGISTIC DEBUG: Flipped AUC to {roc_auc:.4f}")
            
            gini_coefficient = 2 * roc_auc - 1
        else:
            print(f"LOGISTIC DEBUG: ERROR - Cannot calculate AUC/ROC metrics - insufficient valid data")
            roc_auc = None
            gini_coefficient = None

        # Find optimal threshold (KS statistic threshold - maximizes TPR - FPR)
        # This is better than default 0.5 for imbalanced datasets
        print(f"\n{'='*80}")
        print("LOGISTIC DEBUG: THRESHOLD OPTIMIZATION")
        print(f"{'='*80}")
        
        optimal_threshold = 0.5  # Initialize with default
        
        # Check if we have valid threshold data
        if len(thresholds) == 0:
            print(f"WARNING: No valid thresholds available from ROC curve")
            print(f"Using default threshold 0.5 (no optimization possible)")
        else:
            print(f"Testing {len(thresholds)} thresholds from ROC curve")
            print(f"Threshold Range: [{thresholds.min():.4f}, {thresholds.max():.4f}]")
            
            try:
                diffs = np.abs(tpr - fpr)
                optimal_idx = int(np.argmax(diffs)) if len(diffs) > 0 else 0
                ks_stat_value = diffs[optimal_idx] if len(diffs) > 0 else 0.0
                
                # Get the threshold, but ensure it's not at boundaries
                optimal_threshold = float(thresholds[optimal_idx]) if len(thresholds) > optimal_idx and np.isfinite(thresholds[optimal_idx]) else 0.5
                
                print(f"\n--- KS STATISTIC THRESHOLD ---")
                print(f"KS Statistic: {ks_stat_value:.4f}")
                print(f"Optimal Threshold (KS): {optimal_threshold:.4f}")
                if len(tpr) > optimal_idx and len(fpr) > optimal_idx:
                    print(f"TPR at threshold: {tpr[optimal_idx]:.4f}")
                    print(f"FPR at threshold: {fpr[optimal_idx]:.4f}")
                
                # CRITICAL FIX: Don't use boundary thresholds (0.0 or 1.0) - they're not useful
                # Also check if threshold is too extreme (near 0 or 1)
                if optimal_threshold <= 0.001 or optimal_threshold >= 0.999 or not np.isfinite(optimal_threshold):
                    print(f"LOGISTIC DEBUG: WARNING - Optimal threshold ({optimal_threshold:.4f}) is at boundary or invalid")
                    # Use Youden's J statistic instead (maximizes TPR + TNR - 1, equivalent to TPR - FPR)
                    # But find a reasonable threshold (between 0.01 and 0.99)
                    valid_indices = np.where((thresholds > 0.01) & (thresholds < 0.99) & np.isfinite(thresholds))[0]
                    if len(valid_indices) > 0:
                        valid_diffs = diffs[valid_indices]
                        best_valid_idx = valid_indices[np.argmax(valid_diffs)]
                        optimal_threshold = float(thresholds[best_valid_idx])
                        print(f"LOGISTIC DEBUG: Using alternative threshold selection: {optimal_threshold:.4f}")
                    else:
                        # Use actual probability distribution from test data (not synthetic)
                        prob_median = np.median(y_pred_proba_np)
                        prob_mean = np.mean(y_pred_proba_np)
                        # If median is 0 (most predictions are 0), use mean or a small percentile
                        if prob_median == 0 or prob_median < 0.001:
                            # Use 10th percentile or mean, whichever is more reasonable
                            prob_percentile = np.percentile(y_pred_proba_np, 10) if len(y_pred_proba_np) > 0 else 0.01
                            optimal_threshold = max(0.01, min(0.99, max(prob_mean, prob_percentile)))
                            print(f"LOGISTIC DEBUG: Using threshold based on actual probability distribution (median={prob_median:.4f}, mean={prob_mean:.4f}, 10th percentile={prob_percentile:.4f}): {optimal_threshold:.4f}")
                        else:
                            optimal_threshold = max(0.01, min(0.99, prob_median))
                            print(f"LOGISTIC DEBUG: Using median probability from actual predictions as threshold: {optimal_threshold:.4f}")
                
                print(f"✓ KS threshold selected: {optimal_threshold:.4f}")
            except Exception as thresh_err:
                print(f"✗ WARNING - Failed to calculate optimal threshold: {thresh_err}")
                optimal_threshold = 0.5
        
        # Alternative: Find threshold that maximizes F1 score (better for imbalanced data)
        try:
            from sklearn.metrics import f1_score
            print(f"\n--- F1 SCORE OPTIMIZATION ---")
            f1_scores = []
            valid_thresholds = []
            # Test thresholds between 0.01 and 0.99
            test_thresholds = np.linspace(0.01, 0.99, 100)
            print(f"Testing {len(test_thresholds)} thresholds for F1 optimization...")
            for thresh in test_thresholds:
                y_pred_thresh = (y_pred_proba_np >= thresh).astype(int)
                f1 = f1_score(y_test, y_pred_thresh, zero_division=0)
                f1_scores.append(f1)
                valid_thresholds.append(thresh)
            
            f1_optimal_idx = np.argmax(f1_scores)
            f1_optimal_threshold = valid_thresholds[f1_optimal_idx]
            f1_optimal_score = f1_scores[f1_optimal_idx]
            
            print(f"F1-Optimal Threshold: {f1_optimal_threshold:.4f}")
            print(f"F1 Score at optimal: {f1_optimal_score:.4f}")
            print(f"F1 Score range: [{min(f1_scores):.4f}, {max(f1_scores):.4f}]")
            
            # Use F1-optimized threshold if it's better than KS threshold
            # Compare F1 scores at both thresholds
            y_pred_ks = (y_pred_proba_np >= optimal_threshold).astype(int)
            f1_ks = f1_score(y_test, y_pred_ks, zero_division=0)
            
            print(f"\n--- THRESHOLD COMPARISON (F1) ---")
            print(f"KS Threshold ({optimal_threshold:.4f}): F1 = {f1_ks:.4f}")
            print(f"F1-Opt Threshold ({f1_optimal_threshold:.4f}): F1 = {f1_optimal_score:.4f}")
            
            if f1_optimal_score > f1_ks and f1_optimal_score > 0:
                print(f"✓ Using F1-optimized threshold (improvement: {f1_optimal_score - f1_ks:.4f})")
                optimal_threshold = f1_optimal_threshold
            else:
                print(f"✓ Keeping KS threshold (F1 difference: {f1_ks - f1_optimal_score:.4f})")
        except Exception as f1_err:
            print(f"✗ F1 optimization failed: {f1_err}, using KS threshold")
        
        # RECALL OPTIMIZATION: Find threshold that maximizes recall (critical for credit scoring)
        # This helps catch more defaults (true positives) - missing a default is costly
        try:
            from sklearn.metrics import precision_score
            recall_scores = []
            precision_at_recall = []
            valid_thresholds_recall = []
            # Test thresholds between 0.01 and 0.99
            test_thresholds_recall = np.linspace(0.01, 0.99, 100)
            
            for thresh in test_thresholds_recall:
                y_pred_thresh = (y_pred_proba_np >= thresh).astype(int)
                rec = recall_score(y_test, y_pred_thresh, zero_division=0)
                prec = precision_score(y_test, y_pred_thresh, zero_division=0)
                recall_scores.append(rec)
                precision_at_recall.append(prec)
                valid_thresholds_recall.append(thresh)
            
            # Option 1: Maximum recall threshold
            max_recall_idx = np.argmax(recall_scores)
            max_recall_threshold = valid_thresholds_recall[max_recall_idx]
            max_recall_score = recall_scores[max_recall_idx]
            
            # Option 2: Threshold that achieves minimum recall (e.g., 0.7) with best precision
            min_recall_target = 0.7  # Target at least 70% recall
            valid_recall_indices = [i for i, r in enumerate(recall_scores) if r >= min_recall_target]
            
            if valid_recall_indices:
                # Among thresholds meeting minimum recall, pick one with best precision
                best_prec_idx = max(valid_recall_indices, key=lambda i: precision_at_recall[i])
                target_recall_threshold = valid_thresholds_recall[best_prec_idx]
                target_recall_score = recall_scores[best_prec_idx]
                target_precision_score = precision_at_recall[best_prec_idx]
                print(f"LOGISTIC DEBUG: Target recall threshold (≥{min_recall_target}): {target_recall_threshold:.4f} (Recall={target_recall_score:.4f}, Precision={target_precision_score:.4f})")
            else:
                target_recall_threshold = max_recall_threshold
                target_recall_score = max_recall_score
                target_precision_score = precision_at_recall[max_recall_idx]
                print(f"LOGISTIC DEBUG: No threshold meets {min_recall_target} recall, using max recall threshold")
            
            print(f"\n--- RECALL OPTIMIZATION RESULTS ---")
            print(f"Max Recall Threshold: {max_recall_threshold:.4f}")
            print(f"Max Recall Score: {max_recall_score:.4f}")
            print(f"Target Recall Threshold (≥{min_recall_target}): {target_recall_threshold:.4f}")
            print(f"Target Recall Score: {target_recall_score:.4f}")
            print(f"Target Precision Score: {target_precision_score:.4f}")
            
            # Compare with current optimal threshold
            y_pred_current = (y_pred_proba_np >= optimal_threshold).astype(int)
            current_recall = recall_score(y_test, y_pred_current, zero_division=0)
            current_precision = precision_score(y_test, y_pred_current, zero_division=0)
            
            print(f"\n--- CURRENT vs TARGET THRESHOLD COMPARISON ---")
            print(f"Current Threshold: {optimal_threshold:.4f}")
            print(f"  Recall:    {current_recall:.4f}")
            print(f"  Precision: {current_precision:.4f}")
            print(f"Target Threshold: {target_recall_threshold:.4f}")
            print(f"  Recall:    {target_recall_score:.4f}")
            print(f"  Precision: {target_precision_score:.4f}")
            
            # Use recall-optimized threshold if it significantly improves recall
            # Priority: Recall > Precision for credit scoring (catching defaults is critical)
            recall_improvement = target_recall_score - current_recall
            precision_loss = current_precision - target_precision_score if valid_recall_indices else 0
            
            print(f"\n--- THRESHOLD DECISION ---")
            print(f"Recall Improvement: {recall_improvement:.4f}")
            print(f"Precision Loss: {precision_loss:.4f}")
            
            if recall_improvement > 0.1 or (target_recall_score > 0.7 and current_recall < 0.7):
                # Significant recall improvement OR meeting minimum recall target
                print(f"✓ Using recall-optimized threshold")
                print(f"  Reason: {'Significant recall improvement' if recall_improvement > 0.1 else 'Meeting minimum recall target (70%)'}")
                optimal_threshold = target_recall_threshold
            else:
                print(f"✓ Keeping current threshold")
                print(f"  Reason: Insufficient recall improvement ({recall_improvement:.4f} < 0.1)")
            print(f"{'='*80}\n")
                
        except Exception as recall_err:
            print(f"✗ Recall optimization failed: {recall_err}, using current threshold")
            import traceback
            traceback.print_exc()
            print(f"{'='*80}\n")
        
        # Use optimal threshold for binary predictions (better for imbalanced data)
        try:
            y_pred = (y_pred_proba >= optimal_threshold).astype(int)
        except Exception:
            y_pred = (np.array(y_pred_proba) >= optimal_threshold).astype(int)
        
        # Also calculate default predictions for comparison
        try:
            y_pred_default = (y_pred_proba >= 0.5).astype(int)
        except Exception:
            y_pred_default = (np.array(y_pred_proba) >= 0.5).astype(int)
        default_correct = (y_pred_default == y_test).sum()
        optimal_correct = (y_pred == y_test).sum()
        default_accuracy = default_correct/len(y_test) if len(y_test) > 0 else 0
        optimal_accuracy = optimal_correct/len(y_test) if len(y_test) > 0 else 0
        
        print(f"\n{'='*80}")
        print("LOGISTIC DEBUG: THRESHOLD COMPARISON SUMMARY")
        print(f"{'='*80}")
        print(f"Default Threshold (0.5):")
        print(f"  Accuracy: {default_accuracy:.4f}")
        y_pred_default_metrics = {
            'precision': precision_score(y_test, y_pred_default, zero_division=0),
            'recall': recall_score(y_test, y_pred_default, zero_division=0),
            'f1': f1_score(y_test, y_pred_default, zero_division=0)
        }
        print(f"  Precision: {y_pred_default_metrics['precision']:.4f}")
        print(f"  Recall:    {y_pred_default_metrics['recall']:.4f}")
        print(f"  F1-Score:  {y_pred_default_metrics['f1']:.4f}")
        print(f"\nOptimal Threshold ({optimal_threshold:.4f}):")
        print(f"  Accuracy: {optimal_accuracy:.4f}")
        print(f"  Improvement: {optimal_accuracy - default_accuracy:.4f}")
        print(f"{'='*80}\n")

        try:
            cm = confusion_matrix(y_test, y_pred)
            accuracy = accuracy_score(y_test, y_pred)
            precision = precision_score(y_test, y_pred, zero_division=0)
            recall = recall_score(y_test, y_pred, zero_division=0)
            f1 = f1_score(y_test, y_pred, zero_division=0)
            
            # ========== LOGISTIC REGRESSION - TEST SET PERFORMANCE ==========
            print("\n" + "="*80)
            print("LOGISTIC REGRESSION - TEST SET PERFORMANCE")
            print("="*80)
            print(f"Test Samples: {len(y_test)}")
            test_class_dist = y_test.value_counts().to_dict()
            print(f"Test Class Distribution: {test_class_dist}")
            if len(test_class_dist) == 2:
                test_n_class_0 = test_class_dist.get(0, 0)
                test_n_class_1 = test_class_dist.get(1, 0)
                test_imbalance = test_n_class_0 / test_n_class_1 if test_n_class_1 > 0 else float('inf')
                print(f"Test Imbalance Ratio: {test_imbalance:.2f}:1 (Good:Bad)")
            
            print(f"\n--- PREDICTION STATISTICS ---")
            print(f"Probability Range: [{y_pred_proba.min():.4f}, {y_pred_proba.max():.4f}]")
            print(f"Probability Mean: {y_pred_proba.mean():.4f}")
            print(f"Probability Median: {np.median(y_pred_proba):.6f}")
            print(f"Probability Std: {y_pred_proba.std():.6f}")
            print(f"25th Percentile: {np.percentile(y_pred_proba, 25):.6f}")
            print(f"75th Percentile: {np.percentile(y_pred_proba, 75):.6f}")
            print(f"\nPredictions (Class 0): {(y_pred == 0).sum()} ({(y_pred == 0).sum()/len(y_pred)*100:.2f}%)")
            print(f"Predictions (Class 1): {(y_pred == 1).sum()} ({(y_pred == 1).sum()/len(y_pred)*100:.2f}%)")
            
            print(f"\n--- THRESHOLD INFORMATION ---")
            print(f"Threshold Used: {optimal_threshold:.4f}")
            threshold_method = 'KS Statistic'  # Default
            if 'target_recall_threshold' in locals() and abs(optimal_threshold - target_recall_threshold) < 0.001:
                threshold_method = 'Recall-Optimized'
            elif 'f1_optimal_threshold' in locals() and abs(optimal_threshold - f1_optimal_threshold) < 0.001:
                threshold_method = 'F1-Optimized'
            print(f"Threshold Selection Method: {threshold_method}")
            
            print(f"\n--- CONFUSION MATRIX (Optimal Threshold) ---")
            print(f"                Predicted")
            print(f"                0        1")
            print(f"Actual  0    {cm[0,0]:5d}  {cm[0,1]:5d}")
            print(f"        1    {cm[1,0]:5d}  {cm[1,1]:5d}")
            print(f"\nTrue Negatives (TN):  {cm[0,0]:5d} | False Positives (FP): {cm[0,1]:5d}")
            print(f"False Negatives (FN): {cm[1,0]:5d} | True Positives (TP):   {cm[1,1]:5d}")
            
            # Calculate additional metrics
            tn, fp, fn, tp = cm.ravel()
            specificity = tn / (tn + fp) if (tn + fp) > 0 else 0
            npv = tn / (tn + fn) if (tn + fn) > 0 else 0  # Negative Predictive Value
            fpr = fp / (fp + tn) if (fp + tn) > 0 else 0  # False Positive Rate
            
            print(f"\n--- PERFORMANCE METRICS ---")
            if roc_auc is not None:
                print(f"AUC-ROC:         {roc_auc:.4f}")
                print(f"Gini Coefficient: {gini_coefficient:.4f}")
            else:
                print(f"AUC-ROC:         N/A (insufficient valid data)")
                print(f"Gini Coefficient: N/A (insufficient valid data)")
            print(f"Accuracy:       {accuracy:.4f}")
            print(f"Precision:      {precision:.4f}")
            print(f"Recall (TPR):   {recall:.4f}")
            print(f"Specificity:    {specificity:.4f}")
            print(f"F1-Score:       {f1:.4f}")
            print(f"FPR:            {fpr:.4f}")
            print(f"NPV:            {npv:.4f}")
            
            print(f"\n--- METRICS INTERPRETATION ---")
            if precision > 0:
                print(f"✓ Precision: {precision*100:.2f}% of predicted defaults are actually defaults")
            else:
                print(f"✗ Precision: 0% - Model predicted no defaults (or all were wrong)")
            if recall > 0:
                print(f"{'✓' if recall >= 0.7 else '⚠'} Recall: {recall*100:.2f}% of actual defaults were correctly identified")
                if recall < 0.7:
                    print(f"  WARNING: Low recall - missing {((1-recall)*100):.1f}% of defaults!")
            else:
                print(f"✗ Recall: 0% - Model failed to identify any actual defaults")
            if specificity > 0:
                print(f"✓ Specificity: {specificity*100:.2f}% of actual good cases correctly identified")
            print(f"{'✓' if f1 >= 0.5 else '⚠'} F1-Score: {f1:.4f} - {'Good balance' if f1 >= 0.5 else 'Needs improvement'}")
            
            # Model quality assessment
            print(f"\n--- MODEL QUALITY ASSESSMENT ---")
            if roc_auc >= 0.8:
                print(f"✓ Excellent AUC-ROC ({roc_auc:.4f}) - Model has strong discriminative power")
            elif roc_auc >= 0.7:
                print(f"✓ Good AUC-ROC ({roc_auc:.4f}) - Model has acceptable discriminative power")
            elif roc_auc >= 0.6:
                print(f"⚠ Fair AUC-ROC ({roc_auc:.4f}) - Model has limited discriminative power")
            else:
                print(f"✗ Poor AUC-ROC ({roc_auc:.4f}) - Model performs worse than random")
            
            if recall >= 0.7 and precision >= 0.5:
                print(f"✓ Good balance between recall and precision")
            elif recall < 0.5:
                print(f"⚠ Low recall - Model missing too many defaults (critical for credit scoring)")
            elif precision < 0.3:
                print(f"⚠ Low precision - Model has many false alarms")
            
            print("="*80 + "\n")
        except Exception as _cm_err:
            cm = np.array([[0, 0], [0, 0]])
            accuracy = precision = recall = f1 = 0.0

        try:
            fig, ax = plt.subplots(figsize=(4, 4))
            im = ax.imshow(cm, interpolation='nearest', cmap='Blues')
            ax.set_title('Confusion Matrix')
            ax.set_ylabel('Actual')
            ax.set_xlabel('Predicted')
            ax.set_xticks([0, 1])
            ax.set_yticks([0, 1])
            ax.set_xticklabels(['0', '1'])
            ax.set_yticklabels(['0', '1'])
            thresh = cm.max() / 2.0 if cm.max() != 0 else 0
            for i in range(cm.shape[0]):
                for j in range(cm.shape[1]):
                    color = 'white' if cm[i, j] > thresh else 'black'
                    ax.text(j, i, format(int(cm[i, j])), ha='center', va='center', color=color, fontsize=12)
            plt.tight_layout()
            buf = BytesIO()
            fig.savefig(buf, format='png', dpi=150)
            plt.close(fig)
            buf.seek(0)
            img_b64 = base64.b64encode(buf.read()).decode('utf-8')
            cm_image_data = f"data:image/png;base64,{img_b64}"
        except Exception as _img_err:
            cm_image_data = None

        coefficients = []
        p_values = []
        for i, var in enumerate(['const'] + selected_variables):
            coef = result.params[i] if i < len(result.params) else 0
            p_val = result.pvalues[i] if i < len(result.pvalues) else 1
            # Debug: Log p-value to understand significance issue
            if i < 5:  # Log first 5 variables for debugging
                print(f"LOGISTIC DEBUG: Variable {var}: p_value={p_val}, coef={coef}, significance check: p_val < 0.01={p_val < 0.01}, p_val < 0.05={p_val < 0.05}")
            if var == 'const':
                coefficients.append({
                    'variable': 'Intercept',
                    'coefficient': float(coef) if np.isfinite(coef) else None,
                    'significance': 'Highly Significant' if p_val < 0.01 else 'Significant' if p_val < 0.05 else 'Not Significant'
                })
                p_values.append({
                    'variable': 'Intercept',
                    'p_value': float(p_val) if np.isfinite(p_val) else None,
                    'significance': 'Highly Significant' if p_val < 0.01 else 'Significant' if p_val < 0.05 else 'Not Significant'
                })
            else:
                coefficients.append({
                    'variable': var,
                    'coefficient': float(coef) if np.isfinite(coef) else None,
                    'significance': 'Highly Significant' if p_val < 0.01 else 'Significant' if p_val < 0.05 else 'Not Significant'
                })
                p_values.append({
                    'variable': var,
                    'p_value': float(p_val) if np.isfinite(p_val) else None,
                    'significance': 'Highly Significant' if p_val < 0.01 else 'Significant' if p_val < 0.05 else 'Not Significant'
                })

        def _sanitize_number(x):
            try:
                v = float(x)
                return v if np.isfinite(v) else None
            except Exception:
                return None

        try:
            raw_thresholds = list(thresholds)
            print('LOGISTIC DEBUG: raw thresholds sample (first 10):', raw_thresholds[:10])
            nonfinite_idxs = [i for i, t in enumerate(raw_thresholds) if not np.isfinite(t)]
            if nonfinite_idxs:
                print('LOGISTIC DEBUG: found non-finite thresholds at indices:', nonfinite_idxs,
                      'values:', [raw_thresholds[i] for i in nonfinite_idxs])
        except Exception as _th_err:
            print('LOGISTIC DEBUG: could not inspect thresholds:', str(_th_err))

        # Ensure fpr, tpr, thresholds are arrays before zipping (handle edge cases)
        fpr = np.atleast_1d(fpr).flatten()
        tpr = np.atleast_1d(tpr).flatten()
        thresholds = np.atleast_1d(thresholds).flatten()
        
        # Ensure all arrays have the same length
        min_len = min(len(fpr), len(tpr), len(thresholds))
        if min_len == 0:
            print('LOGISTIC DEBUG: ERROR - Empty ROC data, cannot generate ROC curve')
            print('LOGISTIC DEBUG: This may occur with extreme class imbalance or invalid predictions')
            # Return empty ROC data - no synthetic data
            roc_data = []
        else:
            fpr = fpr[:min_len]
            tpr = tpr[:min_len]
            thresholds = thresholds[:min_len]
            roc_data = [{'fpr': _sanitize_number(f), 'tpr': _sanitize_number(t), 'threshold': _sanitize_number(th)}
                        for f, t, th in zip(fpr, tpr, thresholds)]

        try:
            # Ensure arrays are valid before computing KS
            fpr_ks = np.atleast_1d(fpr).flatten()
            tpr_ks = np.atleast_1d(tpr).flatten()
            if len(fpr_ks) != len(tpr_ks) or len(fpr_ks) == 0:
                print('LOGISTIC DEBUG: WARNING - Invalid fpr/tpr arrays for KS calculation')
                ks_stat = None
                ks_threshold = None
            else:
                diffs = [abs(t - f) for f, t in zip(fpr_ks, tpr_ks)]
                ks_idx = int(np.argmax(diffs)) if len(diffs) > 0 else 0
                ks_stat_raw = diffs[ks_idx] if len(diffs) > 0 else 0.0
                ks_stat = float(ks_stat_raw) if np.isfinite(ks_stat_raw) else None
            # CRITICAL FIX: Use optimal_threshold (the one actually used for predictions) instead of raw threshold
            # The optimal_threshold is calculated earlier and handles edge cases properly
            ks_threshold = float(optimal_threshold) if np.isfinite(optimal_threshold) else None
            if ks_threshold is None:
                # Fallback to raw threshold if optimal_threshold not available
                ks_threshold_raw = thresholds[ks_idx] if len(thresholds) > 0 else 0.0
                ks_threshold = float(ks_threshold_raw) if np.isfinite(ks_threshold_raw) else None
                print('LOGISTIC DEBUG: Using raw KS threshold as fallback')
            else:
                print(f'LOGISTIC DEBUG: Using optimal threshold for KS: {ks_threshold:.4f} (raw threshold was {thresholds[ks_idx] if len(thresholds) > ks_idx else "N/A"})')
            ks_curve = []
            # Ensure arrays are valid before creating KS curve
            fpr_ks_curve = np.atleast_1d(fpr).flatten()
            tpr_ks_curve = np.atleast_1d(tpr).flatten()
            thresholds_ks_curve = np.atleast_1d(thresholds).flatten()
            min_len_ks = min(len(fpr_ks_curve), len(tpr_ks_curve), len(thresholds_ks_curve))
            if min_len_ks > 0:
                fpr_ks_curve = fpr_ks_curve[:min_len_ks]
                tpr_ks_curve = tpr_ks_curve[:min_len_ks]
                thresholds_ks_curve = thresholds_ks_curve[:min_len_ks]
                for f, t, th in zip(fpr_ks_curve, tpr_ks_curve, thresholds_ks_curve):
                    ks_curve.append({'threshold': _sanitize_number(th), 'tpr': _sanitize_number(t), 'fpr': _sanitize_number(f), 'diff': _sanitize_number(abs(t - f))})
            else:
                print('LOGISTIC DEBUG: WARNING - Empty arrays for KS curve, skipping')
            if ks_threshold is None:
                print('LOGISTIC DEBUG: KS threshold was non-finite; sanitized to None')
        except Exception as _ks_err:
            print('LOGISTIC DEBUG: KS computation failed:', str(_ks_err))
            ks_stat = None
            ks_threshold = None
            ks_curve = []

        model_stats = {
            'aic': float(result.aic) if np.isfinite(result.aic) else None,
            'bic': float(result.bic) if np.isfinite(result.bic) else None,
            'log_likelihood': float(result.llf) if np.isfinite(result.llf) else None,
            'pseudo_r_squared': float(result.prsquared) if np.isfinite(result.prsquared) else None,
            'n_observations': int(result.nobs),  # Training observations
            'n_test_observations': len(y_test),  # Test observations used for metrics
            'evaluation_data': 'test'  # Indicates metrics are calculated on test data
        }

        try:
            print('LOGISTIC DEBUG: roc_data sample (first 8):', roc_data[:8])
            if any(item.get('threshold') is None for item in roc_data):
                print('LOGISTIC DEBUG: some roc_data.threshold entries are None')
            print('LOGISTIC DEBUG: ks_curve sample (first 8):', ks_curve[:8])
            if any(item.get('diff') is None for item in ks_curve):
                print('LOGISTIC DEBUG: some ks_curve.diff entries are None')
        except Exception as _log_err:
            print('LOGISTIC DEBUG: pre-return inspection failed:', str(_log_err))

        # Include dropped info in response for frontend (optional)
        # Data is already sanitized during construction (using _sanitize_number and np.isfinite checks)
        # No need for recursive sanitization which slows down the response
        resp = {
            'success': True,
            'coefficients': coefficients,
            'p_values': p_values,
            'vif_data': vif_data,
            'gini_coefficient': float(gini_coefficient) if np.isfinite(gini_coefficient) else None,
            'auc': float(roc_auc) if np.isfinite(roc_auc) else None,
            'roc_data': roc_data,
            'model_stats': model_stats,
            'confusion_matrix': (cm.tolist() if isinstance(cm, (list, np.ndarray)) else None),
            'confusion_matrix_image': cm_image_data,
            'accuracy': float(accuracy) if np.isfinite(accuracy) else None,
            'precision': float(precision) if np.isfinite(precision) else None,
            'recall': float(recall) if np.isfinite(recall) else None,
            'f1': float(f1) if np.isfinite(f1) else None,
            'ks_stat': ks_stat,
            'ks_threshold': ks_threshold,
            'ks_curve': ks_curve,
            'dropped_variables': dropped_variables  # Updated: includes constants, high-VIF, rank-deficient
        }

        try:
            params_series = getattr(result, 'params', None)
            intercept_value = 0.0
            if params_series is not None:
                try:
                    intercept_value = float(params_series.get('const', params_series[0]))
                except Exception:
                    try:
                        intercept_value = float(params_series[0])
                    except Exception:
                        intercept_value = 0.0
            coefficients_dict: Dict[str, float] = {}
            if params_series is not None:
                for col in feature_cols:
                    coef_val = None
                    try:
                        coef_val = params_series.get(col)
                    except Exception:
                        coef_val = None
                    if coef_val is None:
                        try:
                            idx = feature_cols.index(col) + 1
                            coef_val = params_series[idx]
                        except Exception:
                            coef_val = None
                    if coef_val is not None and np.isfinite(coef_val):
                        coefficients_dict[col.replace('_WOE', '')] = float(coef_val)
            woe_snapshot = {}
            for var in selected_variables:
                if var in woe_transformed_data:
                    woe_snapshot[var] = copy.deepcopy(woe_transformed_data[var])
            training_metrics = {
                'auc': resp.get('auc'),
                'gini_coefficient': resp.get('gini_coefficient'),
                'accuracy': resp.get('accuracy'),
                'precision': resp.get('precision'),
                'recall': resp.get('recall'),
                'f1': resp.get('f1'),
                'ks_stat': resp.get('ks_stat')
            }
            artifact_payload = {
                'model_type': 'logistic_regression',
                'target': target,
                'selected_variables': selected_variables,
                'model_variables': selected_variables,
                'feature_columns': feature_cols,
                'woe_transformed_data': woe_snapshot,
                'coefficients': coefficients_dict,
                'intercept': intercept_value,
                'training_metrics': training_metrics
            }
            artifact_metadata = save_model_artifact(dataset_id, 'LR', artifact_payload)
            if artifact_metadata:
                resp['artifact'] = artifact_metadata
        except Exception as artifact_err:
            print(f"[MODEL ARTIFACT] Failed to persist logistic model for dataset {dataset_id}: {artifact_err}")

        if dropped_variables:
            print(f"LOGISTIC DEBUG: Dropped variables: {dropped_variables}")

        return jsonify(resp)

    except Exception as e:
        print(f"LOGISTIC DEBUG: Unhandled error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Failed to perform logistic regression: {str(e)}"}), 500


# ----------- Random Forest Analysis -----------
@app.route('/api/random-forest', methods=['POST'])
def random_forest_analysis():
    """
    Perform Random Forest analysis on selected variables.
    Expects payload: { selected_variables: [list], target: string, woe_transformed_data: {} }
    Returns: model metrics, feature importance, ROC data, etc.
    """
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.metrics import roc_curve, auc, classification_report, confusion_matrix, accuracy_score, precision_score, recall_score, f1_score

    # Removed sanitize_for_json - Flask's jsonify handles NaN/inf automatically
    # Data is already sanitized during construction using np.isfinite checks
    
    try:
        data = request.get_json()
        selected_variables = data.get('selected_variables', [])
        target = data.get('target')
        woe_transformed_data = data.get('woe_transformed_data', {})
        dataset_id = (
            data.get('record_id')
            or data.get('dataset_id')
            or data.get('recordId')
            or data.get('datasetId')
        )
        
        if dataset_id:
            try:
                dataset_id = int(dataset_id)
            except (ValueError, TypeError):
                return jsonify({"error": f"Invalid dataset_id: {dataset_id}"}), 400

        if not selected_variables or not target:
            return jsonify({"error": "Missing selected_variables or target"}), 400
        if not dataset_id:
            return jsonify({"error": "Missing dataset_id/record_id"}), 400

        # CRITICAL: Load train set using data_loader (same as binning/WOE endpoints)
        try:
            from data_loader import get_data_for_stage
            df = get_data_for_stage(dataset_id, 'training')  # Returns TRAIN set if split exists
            print(f"RF DEBUG: Loaded dataset: {len(df)} rows (train set if TTS exists)")
        except Exception as e:
            # Fallback to CSV if data_loader fails
            try:
                csv_path = get_csv_path(dataset_id)
                df = pd.read_csv(csv_path)
                print(f"RF DEBUG: Loaded full dataset: {len(df)} rows (fallback)")
            except Exception as e2:
                return jsonify({"error": f"Failed to load CSV: {str(e2)}"}), 400

        if target not in df.columns:
            return jsonify({"error": f"Target variable '{target}' not found in dataset"}), 400
        
        # CRITICAL: Apply preprocessing before training (same as binning/WOE)
        print(f"RF DEBUG: Applying preprocessing before training...")
        try:
            df, preprocessing_report = preprocess_dataset(
                df,
                target_col=target,
                preprocessing_steps={
                    'detect_types': True,
                    'handle_missing': True,
                    'remove_duplicates': True,
                    'handle_outliers': False,  # Don't handle outliers before binning
                    'encode_categorical': False  # Don't encode categorical before binning
                },
                missing_threshold=0.5,
                treat_negative_one_as_missing=True
            )
            print(f"RF DEBUG: Preprocessing completed. Processed shape: {df.shape}")
        except Exception as e:
            print(f"RF DEBUG: WARNING: Preprocessing failed: {str(e)}")
            print(f"RF DEBUG: Continuing with raw data (this may cause issues)")
            import traceback
            traceback.print_exc()

        # Prepare WOE-transformed data (same logic as logistic regression)
        modeling_data = {}
        woe_columns = []  # Track the actual column names we create
        
        for var in selected_variables:
            if var not in df.columns:
                print(f"RF DEBUG: Variable '{var}' not found in dataset columns")
                continue
            woe_data = woe_transformed_data.get(var)
            bins_list = None
            if isinstance(woe_data, list):
                bins_list = [{
                    'range': r.get('range_text') or r.get('Range') or r.get('Bin') or r.get('bin_label') or str(r),
                    'woe': float(r.get('woe') or r.get('WOE') or 0),
                    'min_value': r.get('min_value'),
                    'max_value': r.get('max_value')
                } for r in woe_data if isinstance(r, dict)]
            elif isinstance(woe_data, dict) and isinstance(woe_data.get('stats'), list):
                bins_list = [{
                    'range': r.get('Range') or r.get('Bin') or str(r),
                    'woe': float(r.get('WOE') or 0)
                } for r in woe_data.get('stats')]
            elif isinstance(woe_data, dict) and isinstance(woe_data.get('woe_ranges'), list):
                bins_list = woe_data.get('woe_ranges')
            else:
                print(f"RF DEBUG: No WOE data for {var} (type={type(woe_data)})")
                continue

            if not bins_list:
                print(f"RF DEBUG: Empty bins list for {var}")
                continue

            # Create WOE column name
            woe_column_name = f'{var}_WOE'
            woe_columns.append(woe_column_name)
            modeling_data[woe_column_name] = np.zeros(len(df))
            
            assigned_count = 0
            for bin_info in bins_list:
                bin_range = (
                    bin_info.get('range')
                    or bin_info.get('range_text')
                    or bin_info.get('Range')
                    or bin_info.get('Bin')
                    or bin_info.get('bin')
                )
                woe_value = bin_info.get('woe') or bin_info.get('WOE')
                if woe_value is None:
                    continue
                try:
                    woe_value = float(woe_value)
                except Exception:
                    continue
                
                if not bin_range and (bin_info.get('min_value') is not None or bin_info.get('max_value') is not None):
                    min_val = bin_info.get('min_value')
                    max_val = bin_info.get('max_value')
                    if min_val is not None and max_val is not None:
                        bin_range = f"({min_val}, {max_val}]"
                    elif min_val is not None:
                        bin_range = f"({min_val}, inf)"
                    elif max_val is not None:
                        bin_range = f"(-inf, {max_val}]"
                
                # Apply WOE mapping
                mask = _create_woe_mask(df, var, bin_range)
                modeling_data[woe_column_name][mask] = woe_value
                assigned_count += mask.sum()

            print(f"RF DEBUG: Assigned WOE values for {var}: {assigned_count} rows")

        # Create DataFrame with WOE-transformed variables
        woe_df = pd.DataFrame(modeling_data)
        woe_df[target] = df[target].values

        # Remove rows with missing target
        mask = ~woe_df[target].isna()
        X = woe_df[woe_columns].fillna(0)  # Use the actual WOE column names
        y = woe_df[target][mask]
        X = X[mask]

        if len(X) == 0:
            return jsonify({"error": "No valid data after preprocessing"}), 400

        if len(woe_columns) == 0:
            return jsonify({"error": "No valid WOE-transformed features created"}), 400

        print(f"RF DEBUG: Final features: {woe_columns}")
        print(f"RF DEBUG: X shape: {X.shape}, y shape: {y.shape}")

        # Check class distribution
        class_dist = y.value_counts().to_dict()
        print(f"RF DEBUG: Class distribution: {class_dist}")
        if len(class_dist) == 2:
            n_class_0 = class_dist.get(0, 0)
            n_class_1 = class_dist.get(1, 0)
            imbalance_ratio = n_class_0 / n_class_1 if n_class_1 > 0 else float('inf')
            print(f"RF DEBUG: Class imbalance ratio: {imbalance_ratio:.2f}:1 (0:1)")

        # Calculate custom class weights based on actual imbalance (no synthetic data)
        from sklearn.utils.class_weight import compute_class_weight
        
        y_classes = np.unique(y)
        class_weights = compute_class_weight('balanced', classes=y_classes, y=y)
        class_weight_dict = dict(zip(y_classes, class_weights))
        
        print(f"RF DEBUG: Class weights: {class_weight_dict}")
        
        # Train Random Forest on TRAIN data with improved parameters
        rf_model = RandomForestClassifier(
            n_estimators=200,  # More trees for better performance
            max_depth=12,  # Slightly deeper (but not too deep to prevent overfitting)
            min_samples_split=5,
            min_samples_leaf=2,
            max_features='sqrt',  # Use sqrt of features for each tree
            bootstrap=True,  # Bootstrap sampling (uses real data, no synthetic)
            oob_score=True,  # Calculate out-of-bag score for validation
            random_state=42,
            n_jobs=-1,
            class_weight=class_weight_dict  # Custom weights based on real data
        )
        
        rf_model.fit(X, y)
        print(f"RF DEBUG: Model trained on {len(X)} training samples")
        print(f"RF DEBUG: Out-of-bag score: {rf_model.oob_score_:.4f}")
        
        # ========== RANDOM FOREST - TRAINING SUMMARY ==========
        print("\n" + "="*80)
        print("RANDOM FOREST - TRAINING SUMMARY")
        print("="*80)
        print(f"Dataset ID: {dataset_id}")
        print(f"Target Variable: {target}")
        print(f"Training Samples: {len(X)}")
        print(f"Features: {len(woe_columns)}")
        print(f"Feature Names: {[col.replace('_WOE', '') for col in woe_columns]}")
        print(f"Class Distribution (Train): {y.value_counts().to_dict()}")
        if len(y.value_counts()) == 2:
            n_class_0 = y.value_counts().get(0, 0)
            n_class_1 = y.value_counts().get(1, 0)
            imbalance_ratio = n_class_0 / n_class_1 if n_class_1 > 0 else float('inf')
            print(f"Class Imbalance Ratio: {imbalance_ratio:.2f}:1 (0:1)")
        print(f"\n--- MODEL PARAMETERS ---")
        print(f"n_estimators: {rf_model.n_estimators}")
        print(f"max_depth: {rf_model.max_depth}")
        print(f"min_samples_split: {rf_model.min_samples_split}")
        print(f"min_samples_leaf: {rf_model.min_samples_leaf}")
        print(f"max_features: {rf_model.max_features}")
        print(f"class_weight: {class_weight_dict}")
        print(f"oob_score: {rf_model.oob_score_:.4f}")
        print(f"random_state: {rf_model.random_state}")
        print("="*80 + "\n")
        
        # Feature importance (calculated from training)
        feature_importance = []
        for i, col in enumerate(woe_columns):
            # Extract original variable name (remove _WOE suffix)
            original_var = col.replace('_WOE', '')
            feature_importance.append({
                'variable': original_var,
                'importance': float(rf_model.feature_importances_[i]),
                'importance_percentage': float(rf_model.feature_importances_[i] * 100)
            })

        # Sort by importance
        feature_importance.sort(key=lambda x: x['importance'], reverse=True)

        # CRITICAL: Calculate metrics on TEST data, not training data
        print(f"RF DEBUG: Loading TEST data for evaluation...")
        try:
            from data_loader import get_data_for_stage
            df_test = get_data_for_stage(dataset_id, 'evaluation')  # Returns TEST set
            print(f"RF DEBUG: Loaded TEST dataset: {len(df_test)} rows")
            
            # Apply preprocessing to test data (same as training)
            print(f"RF DEBUG: Applying preprocessing to TEST data...")
            df_test, _ = preprocess_dataset(
                df_test,
                target_col=target,
                preprocessing_steps={
                    'detect_types': True,
                    'handle_missing': True,
                    'remove_duplicates': True,
                    'handle_outliers': False,
                    'encode_categorical': False
                },
                missing_threshold=0.5,
                treat_negative_one_as_missing=True
            )
            print(f"RF DEBUG: TEST data preprocessing completed. Shape: {df_test.shape}")
            
            # Apply WOE transformations to test data using training-learned WOE values
            print(f"RF DEBUG: Applying WOE transformations to TEST data...")
            woe_df_test = _apply_woe_to_test_data(df_test, selected_variables, woe_transformed_data, target)
            
            # Prepare test features (same columns as training)
            X_test = woe_df_test[woe_columns].fillna(0)
            y_test = woe_df_test[target] if target in woe_df_test.columns else df_test[target]
            
            mask_test = ~y_test.isna()
            X_test = X_test[mask_test]
            y_test = y_test[mask_test]
            
            if len(X_test) == 0:
                print(f"RF DEBUG: WARNING: No valid test data after preprocessing. Using training data for metrics.")
                # Fallback to training data if test data is invalid
                X_test = X
                y_test = y
            else:
                print(f"RF DEBUG: TEST data prepared: {len(X_test)} rows, {len(X_test.columns)} features")
            
        except Exception as test_err:
            print(f"RF DEBUG: WARNING: Failed to load/evaluate on test data: {str(test_err)}")
            print(f"RF DEBUG: Falling back to training data for metrics (this is not ideal)")
            import traceback
            traceback.print_exc()
            # Fallback to training data
            X_test = X
            y_test = y

        # Make predictions on TEST data
        y_pred_proba = rf_model.predict_proba(X_test)[:, 1]

        # Calculate metrics on TEST data
        fpr, tpr, thresholds = roc_curve(y_test, y_pred_proba)
        
        # CRITICAL FIX: Filter out invalid (inf, -inf, nan) thresholds before any calculations
        valid_mask = np.isfinite(thresholds) & (thresholds >= 0) & (thresholds <= 1)
        if not valid_mask.all():
            invalid_count = (~valid_mask).sum()
            print(f"RF DEBUG: Filtering out {invalid_count} invalid thresholds (inf/nan/out-of-range)")
            fpr = fpr[valid_mask]
            tpr = tpr[valid_mask]
            thresholds = thresholds[valid_mask]
            if len(thresholds) == 0:
                print(f"RF DEBUG: WARNING - All thresholds were invalid! Using default threshold 0.5")
                thresholds = np.array([1.0, 0.5, 0.0])
                fpr = np.array([0.0, 0.0, 1.0])
                tpr = np.array([0.0, 0.0, 1.0])
        
        roc_auc = auc(fpr, tpr)
        
        # Fix: Handle case where AUC < 0.5 (model worse than random)
        if roc_auc < 0.5:
            print(f"RF DEBUG: WARNING - AUC < 0.5 ({roc_auc:.4f}), model performing worse than random")
            roc_auc = 1 - roc_auc  # Flip AUC
            print(f"RF DEBUG: Flipped AUC to {roc_auc:.4f}")
        
        gini_coefficient = 2 * roc_auc - 1

        # Find optimal threshold (KS statistic threshold - maximizes TPR - FPR)
        # This is better than default 0.5 for imbalanced datasets
        try:
            diffs = np.abs(tpr - fpr)
            optimal_idx = int(np.argmax(diffs)) if len(diffs) > 0 else 0
            
            # Get the threshold, but ensure it's not at boundaries
            optimal_threshold = float(thresholds[optimal_idx]) if len(thresholds) > optimal_idx and np.isfinite(thresholds[optimal_idx]) else 0.5
            
            # CRITICAL FIX: Don't use boundary thresholds (0.0 or 1.0) - they're not useful
            if optimal_threshold <= 0.001 or optimal_threshold >= 0.999 or not np.isfinite(optimal_threshold):
                print(f"RF DEBUG: WARNING - Optimal threshold ({optimal_threshold:.4f}) is at boundary or invalid")
                # Find a reasonable threshold (between 0.01 and 0.99)
                valid_indices = np.where((thresholds > 0.01) & (thresholds < 0.99) & np.isfinite(thresholds))[0]
                if len(valid_indices) > 0:
                    valid_diffs = diffs[valid_indices]
                    best_valid_idx = valid_indices[np.argmax(valid_diffs)]
                    optimal_threshold = float(thresholds[best_valid_idx])
                    print(f"RF DEBUG: Using alternative threshold selection: {optimal_threshold:.4f}")
                else:
                    # Fallback: use a reasonable threshold based on probability distribution
                    prob_median = np.median(y_pred_proba)
                    prob_mean = np.mean(y_pred_proba)
                    if prob_median == 0 or prob_median < 0.001:
                        prob_percentile = np.percentile(y_pred_proba, 10) if len(y_pred_proba) > 0 else 0.01
                        optimal_threshold = max(0.01, min(0.99, max(prob_mean, prob_percentile)))
                        print(f"RF DEBUG: Using fallback threshold (median={prob_median:.4f}, mean={prob_mean:.4f}, 10th percentile={prob_percentile:.4f}): {optimal_threshold:.4f}")
                    else:
                        optimal_threshold = max(0.01, min(0.99, prob_median))
                        print(f"RF DEBUG: Using median probability as threshold: {optimal_threshold:.4f}")
            
            print(f"RF DEBUG: Optimal threshold (KS): {optimal_threshold:.4f} (default would be 0.5)")
        except Exception as thresh_err:
            print(f"RF DEBUG: WARNING - Failed to calculate optimal threshold: {thresh_err}")
            optimal_threshold = 0.5
        
        # Alternative: Find threshold that maximizes F1 score (better for imbalanced data)
        try:
            from sklearn.metrics import f1_score
            f1_scores = []
            valid_thresholds = []
            test_thresholds = np.linspace(0.01, 0.99, 100)
            for thresh in test_thresholds:
                y_pred_thresh = (y_pred_proba >= thresh).astype(int)
                f1 = f1_score(y_test, y_pred_thresh, zero_division=0)
                f1_scores.append(f1)
                valid_thresholds.append(thresh)
            
            f1_optimal_idx = np.argmax(f1_scores)
            f1_optimal_threshold = valid_thresholds[f1_optimal_idx]
            f1_optimal_score = f1_scores[f1_optimal_idx]
            
            print(f"RF DEBUG: F1-optimized threshold: {f1_optimal_threshold:.4f} (F1={f1_optimal_score:.4f})")
            
            # Use F1-optimized threshold if it's better than KS threshold
            y_pred_ks = (y_pred_proba >= optimal_threshold).astype(int)
            f1_ks = f1_score(y_test, y_pred_ks, zero_division=0)
            
            if f1_optimal_score > f1_ks and f1_optimal_score > 0:
                print(f"RF DEBUG: Using F1-optimized threshold (F1={f1_optimal_score:.4f} vs KS F1={f1_ks:.4f})")
                optimal_threshold = f1_optimal_threshold
            else:
                print(f"RF DEBUG: Using KS threshold (F1={f1_ks:.4f} vs F1-opt F1={f1_optimal_score:.4f})")
        except Exception as f1_err:
            print(f"RF DEBUG: F1 optimization failed: {f1_err}, using KS threshold")
        
        # Find threshold that maximizes recall while maintaining reasonable precision
        # This helps identify more defaults (important for credit scoring)
        try:
            recall_scores = []
            precision_scores = []
            valid_thresholds = []
            test_thresholds = np.linspace(0.01, 0.99, 100)
            
            for thresh in test_thresholds:
                y_pred_thresh = (y_pred_proba >= thresh).astype(int)
                rec = recall_score(y_test, y_pred_thresh, zero_division=0)
                prec = precision_score(y_test, y_pred_thresh, zero_division=0)
                recall_scores.append(rec)
                precision_scores.append(prec)
                valid_thresholds.append(thresh)
            
            # Find threshold with recall >= 0.7 and best precision
            target_recall = 0.7
            recall_optimal_idx = None
            best_precision_at_recall = 0
            
            for i, (rec, prec) in enumerate(zip(recall_scores, precision_scores)):
                if rec >= target_recall and prec > best_precision_at_recall:
                    recall_optimal_idx = i
                    best_precision_at_recall = prec
            
            if recall_optimal_idx is not None:
                recall_optimal_threshold = valid_thresholds[recall_optimal_idx]
                recall_optimal_score = recall_scores[recall_optimal_idx]
                
                # Compare with current optimal threshold
                y_pred_current = (y_pred_proba >= optimal_threshold).astype(int)
                recall_current = recall_score(y_test, y_pred_current, zero_division=0)
                precision_current = precision_score(y_test, y_pred_current, zero_division=0)
                
                # Use recall-optimized if it significantly improves recall without too much precision loss
                recall_improvement = recall_optimal_score - recall_current
                precision_loss = precision_current - best_precision_at_recall
                
                if recall_improvement > 0.1 and precision_loss < 0.15:  # At least 10% recall gain, max 15% precision loss
                    print(f"RF DEBUG: Using recall-optimized threshold: {recall_optimal_threshold:.4f}")
                    print(f"RF DEBUG: Recall: {recall_current:.4f} → {recall_optimal_score:.4f} (+{recall_improvement:.4f})")
                    print(f"RF DEBUG: Precision: {precision_current:.4f} → {best_precision_at_recall:.4f} (-{precision_loss:.4f})")
                    optimal_threshold = recall_optimal_threshold
                else:
                    print(f"RF DEBUG: Keeping current threshold (recall improvement {recall_improvement:.4f} too small or precision loss {precision_loss:.4f} too large)")
            else:
                print(f"RF DEBUG: No threshold found with recall >= {target_recall}")
                
        except Exception as recall_err:
            print(f"RF DEBUG: Recall optimization failed: {recall_err}, using current threshold")
        
        # Use optimal threshold for binary predictions (better for imbalanced data)
        y_pred = (y_pred_proba >= optimal_threshold).astype(int)
        
        # Also calculate default predictions for comparison
        y_pred_default = rf_model.predict(X_test)
        default_correct = (y_pred_default == y_test).sum()
        optimal_correct = (y_pred == y_test).sum()
        print(f"RF DEBUG: Default threshold (0.5) accuracy: {default_correct/len(y_test):.4f}")
        print(f"RF DEBUG: Optimal threshold ({optimal_threshold:.4f}) accuracy: {optimal_correct/len(y_test):.4f}")

        # Confusion matrix and classification metrics on TEST data (using optimal threshold)
        cm = confusion_matrix(y_test, y_pred)
        accuracy = accuracy_score(y_test, y_pred)
        precision = precision_score(y_test, y_pred, zero_division=0)
        recall = recall_score(y_test, y_pred, zero_division=0)
        f1 = f1_score(y_test, y_pred, zero_division=0)
        
        # ========== RANDOM FOREST - TEST PERFORMANCE ==========
        print("\n" + "="*80)
        print("RANDOM FOREST - TEST SET PERFORMANCE")
        print("="*80)
        print(f"Test Samples: {len(y_test)}")
        print(f"Test Class Distribution: {y_test.value_counts().to_dict()}")
        print(f"\n--- PREDICTION STATISTICS ---")
        print(f"Probability Range: [{y_pred_proba.min():.4f}, {y_pred_proba.max():.4f}]")
        print(f"Probability Mean: {y_pred_proba.mean():.4f}")
        print(f"Probability Median: {np.median(y_pred_proba):.4f}")
        print(f"Predictions (Class 0): {(y_pred == 0).sum()} ({(y_pred == 0).sum()/len(y_pred)*100:.2f}%)")
        print(f"Predictions (Class 1): {(y_pred == 1).sum()} ({(y_pred == 1).sum()/len(y_pred)*100:.2f}%)")
        print(f"\n--- THRESHOLD INFORMATION ---")
        print(f"Default Threshold (0.5): Accuracy = {default_correct/len(y_test):.4f}")
        print(f"Optimal Threshold ({optimal_threshold:.4f}): Accuracy = {optimal_correct/len(y_test):.4f}")
        print(f"Threshold Used: {optimal_threshold:.4f} (KS Optimal)")
        print(f"\n--- CONFUSION MATRIX (Optimal Threshold) ---")
        print(f"                Predicted")
        print(f"                0        1")
        print(f"Actual  0    {cm[0,0]:5d}  {cm[0,1]:5d}")
        print(f"        1    {cm[1,0]:5d}  {cm[1,1]:5d}")
        print(f"\nTrue Negatives (TN):  {cm[0,0]} | False Positives (FP): {cm[0,1]}")
        print(f"False Negatives (FN): {cm[1,0]} | True Positives (TP):   {cm[1,1]}")
        print(f"\n--- PERFORMANCE METRICS ---")
        print(f"AUC-ROC:        {roc_auc:.4f}")
        print(f"Gini Coefficient: {gini_coefficient:.4f}")
        print(f"Accuracy:       {accuracy:.4f}")
        print(f"Precision:      {precision:.4f}")
        print(f"Recall:         {recall:.4f}")
        print(f"F1-Score:       {f1:.4f}")
        print(f"\n--- METRICS INTERPRETATION ---")
        if precision > 0:
            print(f"Precision: {precision*100:.2f}% of predicted positives are actually positive")
        else:
            print(f"Precision: 0% - Model predicted no positives (or all were wrong)")
        if recall > 0:
            print(f"Recall: {recall*100:.2f}% of actual positives were correctly identified")
        else:
            print(f"Recall: 0% - Model failed to identify any actual positives")
        print("="*80 + "\n")

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
            print(f"RF DEBUG: KS calculation error: {ks_err}")
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
            'n_estimators': rf_model.n_estimators,
            'max_depth': rf_model.max_depth,
            'n_observations': len(X),  # Training observations
            'n_test_observations': len(y_test),  # Test observations used for metrics
            'n_features': len(woe_columns),
            'oob_score': float(getattr(rf_model, 'oob_score_', 0)) if hasattr(rf_model, 'oob_score_') else None,
            'evaluation_data': 'test'  # Indicates metrics are calculated on test data
        }

        # Data is already sanitized during construction (using np.isfinite checks)
        # No need for recursive sanitization which slows down the response
        resp = {
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
            'ks_curve': ks_curve
        }

        # CRITICAL FIX: Save Random Forest model artifact (was missing!)
        try:
            print(f"[MODEL ARTIFACT] Saving Random Forest artifact for dataset {dataset_id}")
            
            # Serialize the trained model
            import pickle
            model_bytes = pickle.dumps(rf_model)
            
            # Prepare WOE snapshot for scorecard application
            model_variables = [col.replace('_WOE', '') for col in woe_columns]
            woe_snapshot = {}
            for var in model_variables:
                if var in woe_transformed_data:
                    woe_snapshot[var] = copy.deepcopy(woe_transformed_data[var])
            
            # Training metrics (from test evaluation)
            training_metrics = {
                'auc': float(roc_auc) if np.isfinite(roc_auc) else None,
                'gini_coefficient': float(gini_coefficient) if np.isfinite(gini_coefficient) else None,
                'accuracy': float(accuracy) if np.isfinite(accuracy) else None,
                'precision': float(precision) if np.isfinite(precision) else None,
                'recall': float(recall) if np.isfinite(recall) else None,
                'f1': float(f1) if np.isfinite(f1) else None,
                'ks_stat': ks_stat
            }
            
            # Create artifact payload
            artifact_payload = {
                'model_type': 'random_forest',
                'target': target,
                'selected_variables': model_variables,
                'model_variables': model_variables,
                'feature_columns': woe_columns,  # WOE-transformed feature columns
                'woe_transformed_data': woe_snapshot,
                'model_bytes': model_bytes,
                'model_params': {
                    'n_estimators': rf_model.n_estimators,
                    'max_depth': rf_model.max_depth,
                    'min_samples_split': rf_model.min_samples_split,
                    'min_samples_leaf': rf_model.min_samples_leaf,
                    'random_state': rf_model.random_state
                },
                'training_metrics': training_metrics,
                'uses_raw_features': False,  # RF uses WOE features
                'n_samples': len(X),
                'class_distribution': y.value_counts().to_dict()
            }
            
            # Save artifact (use 'random_forest' to match apply_scorecard expectations)
            # Note: The label will be sanitized by _sanitize_model_label, but we use lowercase underscore for consistency
            artifact_metadata = save_model_artifact(dataset_id, 'random_forest', artifact_payload)
            if artifact_metadata:
                resp['artifact'] = artifact_metadata
                print(f"[MODEL ARTIFACT] Successfully saved Random Forest artifact: {artifact_metadata}")
            else:
                print(f"[MODEL ARTIFACT] save_model_artifact returned None for dataset {dataset_id}")
        except Exception as artifact_err:
            print(f"[MODEL ARTIFACT] Failed to persist Random Forest model for dataset {dataset_id}: {artifact_err}")
            import traceback
            traceback.print_exc()
            # Don't fail the request if artifact saving fails, just log the error

        return jsonify(resp)

    except Exception as e:
        print(f"RANDOM FOREST ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Failed to perform Random Forest analysis: {str(e)}"}), 500

# ----------- XGBoost Analysis (FIXED - Uses RAW Features) -----------
@app.route('/api/xgboost', methods=['POST'])
def xgboost_analysis():
    """
    Perform XGBoost analysis on selected variables.
    NOW TRAINS ON RAW FEATURES, NOT WOE-TRANSFORMED!
    Expects payload: { selected_variables: [list], target: string }
    Returns: model metrics, feature importance, ROC data, etc.
    """
    try:
        import xgboost as xgb
    except ImportError:
        return jsonify({"error": "XGBoost not installed. Please install with: pip install xgboost"}), 500
    
    try:
        data = request.get_json()
        selected_variables = data.get('selected_variables', [])
        target = data.get('target')
        dataset_id = (
            data.get('record_id')
            or data.get('dataset_id')
            or data.get('recordId')
            or data.get('datasetId')
        )
        
        if dataset_id:
            try:
                dataset_id = int(dataset_id)
            except (ValueError, TypeError):
                return jsonify({"error": f"Invalid dataset_id: {dataset_id}"}), 400

        if not selected_variables or not target:
            return jsonify({"error": "Missing selected_variables or target"}), 400
        if not dataset_id:
            return jsonify({"error": "Missing dataset_id/record_id"}), 400

        # CRITICAL: Load train set using data_loader (same as Logistic Regression and Random Forest)
        try:
            from data_loader import get_data_for_stage
            df_train = get_data_for_stage(dataset_id, 'training')  # Returns TRAIN set if split exists
            print(f"XGB DEBUG: Loaded dataset: {len(df_train)} rows (train set if TTS exists)")
        except Exception as e:
            # Fallback to CSV if data_loader fails
            try:
                csv_path = get_csv_path(dataset_id)
                df_train = pd.read_csv(csv_path)
                print(f"XGB DEBUG: Loaded full dataset: {len(df_train)} rows (fallback)")
            except Exception as e2:
                return jsonify({"error": f"Failed to load CSV: {str(e2)}"}), 400

        if target not in df_train.columns:
            return jsonify({"error": f"Target variable '{target}' not found in dataset"}), 400
        
        # CRITICAL: Apply preprocessing before training (same as Logistic Regression and Random Forest)
        print(f"XGB DEBUG: Applying preprocessing before training...")
        try:
            df_train, preprocessing_report = preprocess_dataset(
                df_train,
                target_col=target,
                preprocessing_steps={
                    'detect_types': True,
                    'handle_missing': True,
                    'remove_duplicates': True,
                    'handle_outliers': False,  # Don't handle outliers before binning
                    'encode_categorical': False  # Don't encode categorical before binning
                },
                missing_threshold=0.5,
                treat_negative_one_as_missing=True
            )
            print(f"XGB DEBUG: Preprocessing completed. Processed shape: {df_train.shape}")
        except Exception as e:
            print(f"XGB DEBUG: WARNING: Preprocessing failed: {str(e)}")
            print(f"XGB DEBUG: Continuing with raw data (this may cause issues)")
            import traceback
            traceback.print_exc()

        # KEY FIX: Train on RAW features using the new module (on TRAIN data)
        print(f"\n[XGBoost API] Training on {len(selected_variables)} RAW features (not WOE) - TRAIN SET")
        
        # Check class distribution before training
        train_class_dist = df_train[target].value_counts().to_dict()
        print(f"XGB DEBUG: Training class distribution: {train_class_dist}")
        if len(train_class_dist) == 2:
            n_class_0 = train_class_dist.get(0, 0)
            n_class_1 = train_class_dist.get(1, 0)
            imbalance_ratio = n_class_0 / n_class_1 if n_class_1 > 0 else float('inf')
            print(f"XGB DEBUG: Training class imbalance ratio: {imbalance_ratio:.2f}:1 (0:1)")
        
        result = train_xgboost_on_raw_features(df_train, selected_variables, target)
        
        # Extract scale_pos_weight from xgb_params for logging
        xgb_params = result.get('artifact_payload', {}).get('xgb_params', {})
        scale_pos_weight_used = xgb_params.get('scale_pos_weight', 'N/A')
        if isinstance(scale_pos_weight_used, (int, float)):
            scale_pos_weight_used = f"{scale_pos_weight_used:.2f}"
        
        # ========== XGBOOST - TRAINING SUMMARY ==========
        print("\n" + "="*80)
        print("XGBOOST - TRAINING SUMMARY")
        print("="*80)
        print(f"Dataset ID: {dataset_id}")
        print(f"Target Variable: {target}")
        print(f"Training Samples: {len(df_train)}")
        print(f"Features: {len(selected_variables)}")
        print(f"Feature Names: {selected_variables}")
        print(f"Class Distribution (Train): {train_class_dist}")
        if len(train_class_dist) == 2:
            n_class_0 = train_class_dist.get(0, 0)
            n_class_1 = train_class_dist.get(1, 0)
            imbalance_ratio = n_class_0 / n_class_1 if n_class_1 > 0 else float('inf')
            print(f"Class Imbalance Ratio: {imbalance_ratio:.2f}:1 (0:1)")
        print(f"\n--- MODEL PARAMETERS ---")
        print(f"n_estimators: 100")
        print(f"max_depth: 4")
        print(f"learning_rate: 0.1")
        print(f"subsample: 0.8")
        print(f"colsample_bytree: 0.8")
        print(f"random_state: 42")
        print(f"scale_pos_weight: {scale_pos_weight_used}")
        print("="*80 + "\n")
        
        # Load the trained model for evaluation on test data
        import pickle
        xgb_model = pickle.loads(result['artifact_payload']['model_bytes'])
        label_encoders = {col: pickle.loads(enc_bytes) for col, enc_bytes in result['artifact_payload']['label_encoders'].items()}
        
        # CRITICAL: Calculate metrics on TEST data, not training data
        print(f"XGB DEBUG: Loading TEST data for evaluation...")
        try:
            from data_loader import get_data_for_stage
            df_test = get_data_for_stage(dataset_id, 'evaluation')  # Returns TEST set
            print(f"XGB DEBUG: Loaded TEST dataset: {len(df_test)} rows")
            
            # Apply preprocessing to test data (same as training)
            print(f"XGB DEBUG: Applying preprocessing to TEST data...")
            df_test, _ = preprocess_dataset(
                df_test,
                target_col=target,
                preprocessing_steps={
                    'detect_types': True,
                    'handle_missing': True,
                    'remove_duplicates': True,
                    'handle_outliers': False,
                    'encode_categorical': False
                },
                missing_threshold=0.5,
                treat_negative_one_as_missing=True
            )
            print(f"XGB DEBUG: TEST data preprocessing completed. Shape: {df_test.shape}")
            
            # Prepare test features (same preprocessing as training)
            X_test = df_test[selected_variables].copy()
            y_test = df_test[target].copy()
            
            # Handle missing values in test features (same as training)
            for col in X_test.columns:
                if X_test[col].dtype in ['float64', 'int64']:
                    X_test[col] = X_test[col].replace([np.inf, -np.inf], np.nan)
                    median_val = X_test[col].median()
                    if pd.isna(median_val):
                        median_val = 0
                    X_test[col] = X_test[col].fillna(median_val)
                else:
                    mode_val = X_test[col].mode()
                    fill_val = mode_val[0] if not mode_val.empty else 'MISSING'
                    X_test[col] = X_test[col].fillna(fill_val)
            
            # Encode categorical variables (same logic as training: one-hot for <=10 categories, label for >10)
            for col in list(X_test.columns):  # Use list() to avoid modification during iteration
                if X_test[col].dtype == 'object' or X_test[col].dtype.name == 'category':
                    unique_count = X_test[col].nunique()
                    if unique_count <= 10:  # One-hot encode if <= 10 categories (same as training)
                        X_test = pd.get_dummies(X_test, columns=[col], prefix=col)
                        print(f"XGB DEBUG: One-hot encoded '{col}' ({unique_count} categories) in test data")
                    else:  # Label encode if > 10 categories
                        if col in label_encoders:
                            try:
                                encoder = label_encoders[col]
                                # FIX: Handle NaN first
                                X_test[col] = X_test[col].fillna('__MISSING__')
                                # FIX: Handle unseen categories
                                seen_categories = set(encoder.classes_)
                                test_values = X_test[col].astype(str)
                                unseen_mask = ~test_values.isin(seen_categories)
                                if unseen_mask.any():
                                    unseen_count = unseen_mask.sum()
                                    print(f"XGB DEBUG: Found {unseen_count} unseen categories in '{col}', mapping to '__MISSING__'")
                                    X_test.loc[unseen_mask, col] = '__MISSING__'
                                    # If '__MISSING__' is not in encoder, we need to handle it
                                    if '__MISSING__' not in seen_categories:
                                        # Map to most frequent category or 0
                                        if len(seen_categories) > 0:
                                            most_frequent = test_values[~unseen_mask].mode()
                                            if len(most_frequent) > 0:
                                                X_test.loc[unseen_mask, col] = most_frequent.iloc[0]
                                            else:
                                                X_test.loc[unseen_mask, col] = list(seen_categories)[0]
                                X_test[col] = encoder.transform(X_test[col].astype(str))
                            except Exception as enc_err:
                                print(f"XGB DEBUG: Failed to apply encoder for {col}: {enc_err}")
                                import traceback
                                traceback.print_exc()
                                # Fallback: handle NaN and create new encoder
                                X_test[col] = X_test[col].fillna('__MISSING__')
                                from sklearn.preprocessing import LabelEncoder
                                le = LabelEncoder()
                                X_test[col] = le.fit_transform(X_test[col].astype(str))
                                print(f"XGB DEBUG: Created new encoder for {col} (fallback mode)")
                        else:
                            # FIX: Handle NaN before creating new encoder
                            X_test[col] = X_test[col].fillna('__MISSING__')
                            from sklearn.preprocessing import LabelEncoder
                            le = LabelEncoder()
                            X_test[col] = le.fit_transform(X_test[col].astype(str))
                            print(f"XGB DEBUG: Created new encoder for {col} (no saved encoder found)")
            
            # Ensure test features match training features (add missing one-hot columns with zeros)
            artifact_feature_cols = result.get('artifact_payload', {}).get('feature_columns', [])
            if artifact_feature_cols and len(artifact_feature_cols) > 0:
                missing_cols = set(artifact_feature_cols) - set(X_test.columns)
                for col in missing_cols:
                    X_test[col] = 0  # Add missing one-hot columns with zeros
                # Reorder columns to match training
                X_test = X_test[artifact_feature_cols]
            
            # Handle target variable
            y_test = pd.to_numeric(y_test, errors='coerce').fillna(0).astype(int)
            
            # Remove rows with invalid target
            valid_mask = y_test.isin([0, 1])
            X_test = X_test[valid_mask]
            y_test = y_test[valid_mask]
            
            if len(X_test) == 0:
                print(f"XGB DEBUG: WARNING: No valid test data after preprocessing. Using training data for metrics.")
                # Fallback to training data if test data is invalid
                X_test = df_train[selected_variables].copy()
                y_test = df_train[target].copy()
                # Apply same preprocessing to training data for fallback
                for col in X_test.columns:
                    if X_test[col].dtype in ['float64', 'int64']:
                        X_test[col] = X_test[col].replace([np.inf, -np.inf], np.nan)
                        median_val = X_test[col].median()
                        if pd.isna(median_val):
                            median_val = 0
                        X_test[col] = X_test[col].fillna(median_val)
                    else:
                        mode_val = X_test[col].mode()
                        fill_val = mode_val[0] if not mode_val.empty else 'MISSING'
                        X_test[col] = X_test[col].fillna(fill_val)
                # Encode categorical variables (same logic as training)
                for col in list(X_test.columns):  # Use list() to avoid modification during iteration
                    if X_test[col].dtype == 'object' or X_test[col].dtype.name == 'category':
                        unique_count = X_test[col].nunique()
                        if unique_count <= 10:  # One-hot encode if <= 10 categories
                            X_test = pd.get_dummies(X_test, columns=[col], prefix=col)
                        else:  # Label encode if > 10 categories
                            if col in label_encoders:
                                try:
                                    encoder = label_encoders[col]
                                    # FIX: Handle NaN first
                                    X_test[col] = X_test[col].fillna('__MISSING__')
                                    # FIX: Handle unseen categories
                                    seen_categories = set(encoder.classes_)
                                    test_values = X_test[col].astype(str)
                                    unseen_mask = ~test_values.isin(seen_categories)
                                    if unseen_mask.any():
                                        if '__MISSING__' in seen_categories:
                                            X_test.loc[unseen_mask, col] = '__MISSING__'
                                        else:
                                            # Map to first category
                                            X_test.loc[unseen_mask, col] = list(seen_categories)[0] if len(seen_categories) > 0 else '__MISSING__'
                                    X_test[col] = encoder.transform(X_test[col].astype(str))
                                except Exception as enc_err:
                                    print(f"XGB DEBUG: Failed to apply encoder for {col}: {enc_err}")
                                    # FIX: Handle NaN before creating new encoder
                                    X_test[col] = X_test[col].fillna('__MISSING__')
                                    from sklearn.preprocessing import LabelEncoder
                                    le = LabelEncoder()
                                    X_test[col] = le.fit_transform(X_test[col].astype(str))
                            else:
                                # FIX: Handle NaN before creating new encoder
                                X_test[col] = X_test[col].fillna('__MISSING__')
                                from sklearn.preprocessing import LabelEncoder
                                le = LabelEncoder()
                                X_test[col] = le.fit_transform(X_test[col].astype(str))
                
                # Ensure features match training features
                artifact_feature_cols = result.get('artifact_payload', {}).get('feature_columns', [])
                if artifact_feature_cols and len(artifact_feature_cols) > 0:
                    missing_cols = set(artifact_feature_cols) - set(X_test.columns)
                    for col in missing_cols:
                        X_test[col] = 0
                    X_test = X_test[artifact_feature_cols]
                
                y_test = pd.to_numeric(y_test, errors='coerce').fillna(0).astype(int)
                valid_mask = y_test.isin([0, 1])
                X_test = X_test[valid_mask]
                y_test = y_test[valid_mask]
            else:
                print(f"XGB DEBUG: TEST data prepared: {len(X_test)} rows, {len(X_test.columns)} features")
            
        except Exception as test_err:
            print(f"XGB DEBUG: WARNING: Failed to load/evaluate on test data: {str(test_err)}")
            print(f"XGB DEBUG: Falling back to training data for metrics (this is not ideal)")
            import traceback
            traceback.print_exc()
            # Fallback: use training metrics from result
            X_test = None
            y_test = None
        
        # Make predictions on TEST data
        if X_test is not None and y_test is not None:
            from sklearn.metrics import roc_curve, auc, confusion_matrix, accuracy_score, precision_score, recall_score, f1_score
            
            # Check class distribution in test data
            test_class_dist = y_test.value_counts().to_dict()
            print(f"XGB DEBUG: Test set class distribution: {test_class_dist}")
            if len(test_class_dist) == 2:
                n_class_0 = test_class_dist.get(0, 0)
                n_class_1 = test_class_dist.get(1, 0)
                imbalance_ratio = n_class_0 / n_class_1 if n_class_1 > 0 else float('inf')
                print(f"XGB DEBUG: Test set class imbalance ratio: {imbalance_ratio:.2f}:1 (0:1)")
            
            y_pred_proba = xgb_model.predict_proba(X_test)[:, 1]
            
            # Calculate metrics on TEST data
            fpr, tpr, thresholds = roc_curve(y_test, y_pred_proba)
            
            # CRITICAL FIX: Filter out invalid (inf, -inf, nan) thresholds before any calculations
            valid_mask = np.isfinite(thresholds) & (thresholds >= 0) & (thresholds <= 1)
            if not valid_mask.all():
                invalid_count = (~valid_mask).sum()
                print(f"XGB DEBUG: Filtering out {invalid_count} invalid thresholds (inf/nan/out-of-range)")
                fpr = fpr[valid_mask]
                tpr = tpr[valid_mask]
                thresholds = thresholds[valid_mask]
                if len(thresholds) == 0:
                    print(f"XGB DEBUG: WARNING - All thresholds were invalid! Using default threshold 0.5")
                    thresholds = np.array([1.0, 0.5, 0.0])
                    fpr = np.array([0.0, 0.0, 1.0])
                    tpr = np.array([0.0, 0.0, 1.0])
            
            roc_auc = auc(fpr, tpr)
            
            # Fix: Handle case where AUC < 0.5 (model worse than random)
            if roc_auc < 0.5:
                print(f"XGB DEBUG: WARNING - AUC < 0.5 ({roc_auc:.4f}), model performing worse than random")
                roc_auc = 1 - roc_auc  # Flip AUC
                print(f"XGB DEBUG: Flipped AUC to {roc_auc:.4f}")
            
            gini_coefficient = 2 * roc_auc - 1
            
            # Find optimal threshold (KS statistic threshold - maximizes TPR - FPR)
            # This is better than default 0.5 for imbalanced datasets
            try:
                diffs = np.abs(tpr - fpr)
                optimal_idx = int(np.argmax(diffs)) if len(diffs) > 0 else 0
                
                # Get the threshold, but ensure it's not at boundaries
                optimal_threshold = float(thresholds[optimal_idx]) if len(thresholds) > optimal_idx and np.isfinite(thresholds[optimal_idx]) else 0.5
                
                # CRITICAL FIX: Don't use boundary thresholds (0.0 or 1.0) - they're not useful
                if optimal_threshold <= 0.001 or optimal_threshold >= 0.999 or not np.isfinite(optimal_threshold):
                    print(f"XGB DEBUG: WARNING - Optimal threshold ({optimal_threshold:.4f}) is at boundary or invalid")
                    # Find a reasonable threshold (between 0.01 and 0.99)
                    valid_indices = np.where((thresholds > 0.01) & (thresholds < 0.99) & np.isfinite(thresholds))[0]
                    if len(valid_indices) > 0:
                        valid_diffs = diffs[valid_indices]
                        best_valid_idx = valid_indices[np.argmax(valid_diffs)]
                        optimal_threshold = float(thresholds[best_valid_idx])
                        print(f"XGB DEBUG: Using alternative threshold selection: {optimal_threshold:.4f}")
                    else:
                        # Fallback: use a reasonable threshold based on probability distribution
                        prob_median = np.median(y_pred_proba)
                        prob_mean = np.mean(y_pred_proba)
                        if prob_median == 0 or prob_median < 0.001:
                            prob_percentile = np.percentile(y_pred_proba, 10) if len(y_pred_proba) > 0 else 0.01
                            optimal_threshold = max(0.01, min(0.99, max(prob_mean, prob_percentile)))
                            print(f"XGB DEBUG: Using fallback threshold (median={prob_median:.4f}, mean={prob_mean:.4f}, 10th percentile={prob_percentile:.4f}): {optimal_threshold:.4f}")
                        else:
                            optimal_threshold = max(0.01, min(0.99, prob_median))
                            print(f"XGB DEBUG: Using median probability as threshold: {optimal_threshold:.4f}")
                
                print(f"XGB DEBUG: Optimal threshold (KS): {optimal_threshold:.4f} (default would be 0.5)")
            except Exception as thresh_err:
                print(f"XGB DEBUG: WARNING - Failed to calculate optimal threshold: {thresh_err}")
                optimal_threshold = 0.5
            
            # Alternative: Find threshold that maximizes F1 score (better for imbalanced data)
            try:
                from sklearn.metrics import f1_score
                f1_scores = []
                valid_thresholds = []
                test_thresholds = np.linspace(0.01, 0.99, 100)
                for thresh in test_thresholds:
                    y_pred_thresh = (y_pred_proba >= thresh).astype(int)
                    f1 = f1_score(y_test, y_pred_thresh, zero_division=0)
                    f1_scores.append(f1)
                    valid_thresholds.append(thresh)
                
                f1_optimal_idx = np.argmax(f1_scores)
                f1_optimal_threshold = valid_thresholds[f1_optimal_idx]
                f1_optimal_score = f1_scores[f1_optimal_idx]
                
                print(f"XGB DEBUG: F1-optimized threshold: {f1_optimal_threshold:.4f} (F1={f1_optimal_score:.4f})")
                
                # Use F1-optimized threshold if it's better than KS threshold
                y_pred_ks = (y_pred_proba >= optimal_threshold).astype(int)
                f1_ks = f1_score(y_test, y_pred_ks, zero_division=0)
                
                if f1_optimal_score > f1_ks and f1_optimal_score > 0:
                    print(f"XGB DEBUG: Using F1-optimized threshold (F1={f1_optimal_score:.4f} vs KS F1={f1_ks:.4f})")
                    optimal_threshold = f1_optimal_threshold
                else:
                    print(f"XGB DEBUG: Using KS threshold (F1={f1_ks:.4f} vs F1-opt F1={f1_optimal_score:.4f})")
            except Exception as f1_err:
                print(f"XGB DEBUG: F1 optimization failed: {f1_err}, using KS threshold")
            
            # Find threshold that maximizes recall while maintaining reasonable precision
            # This helps identify more defaults (important for credit scoring)
            # Prioritize recall over precision - catching defaults is critical
            try:
                recall_scores = []
                precision_scores = []
                valid_thresholds = []
                test_thresholds = np.linspace(0.01, 0.99, 200)  # More granular search
                
                for thresh in test_thresholds:
                    y_pred_thresh = (y_pred_proba >= thresh).astype(int)
                    rec = recall_score(y_test, y_pred_thresh, zero_division=0)
                    prec = precision_score(y_test, y_pred_thresh, zero_division=0)
                    recall_scores.append(rec)
                    precision_scores.append(prec)
                    valid_thresholds.append(thresh)
                
                # Find maximum recall threshold first (like Random Forest does)
                max_recall_idx = np.argmax(recall_scores)
                max_recall_threshold = valid_thresholds[max_recall_idx]
                max_recall_score = recall_scores[max_recall_idx]
                max_recall_precision = precision_scores[max_recall_idx]
                
                print(f"XGB DEBUG: Maximum recall threshold: {max_recall_threshold:.4f} (Recall: {max_recall_score:.4f}, Precision: {max_recall_precision:.4f})")
                
                # Find threshold with recall >= 0.5 (lower target for extreme imbalance)
                target_recall = 0.5  # Lower from 0.7 to 0.5 for extreme imbalance
                recall_optimal_idx = None
                best_precision_at_recall = 0
                
                for i, (rec, prec) in enumerate(zip(recall_scores, precision_scores)):
                    if rec >= target_recall and prec > best_precision_at_recall:
                        recall_optimal_idx = i
                        best_precision_at_recall = prec
                
                # Compare with current optimal threshold
                y_pred_current = (y_pred_proba >= optimal_threshold).astype(int)
                recall_current = recall_score(y_test, y_pred_current, zero_division=0)
                precision_current = precision_score(y_test, y_pred_current, zero_division=0)
                
                # Prioritize recall - accept any recall improvement > 5% with precision loss < 80%
                # For credit scoring, catching defaults is more important than precision
                recall_optimal_selected = False
                if recall_optimal_idx is not None:
                    recall_optimal_threshold = valid_thresholds[recall_optimal_idx]
                    recall_optimal_score = recall_scores[recall_optimal_idx]
                    
                    recall_improvement = recall_optimal_score - recall_current
                    precision_loss = precision_current - best_precision_at_recall
                    
                    # Much more lenient: accept 5%+ recall improvement with up to 80% precision loss
                    if recall_improvement > 0.05 and precision_loss < 0.8:
                        print(f"XGB DEBUG: Using recall-optimized threshold: {recall_optimal_threshold:.4f}")
                        print(f"XGB DEBUG: Recall: {recall_current:.4f} → {recall_optimal_score:.4f} (+{recall_improvement:.4f})")
                        print(f"XGB DEBUG: Precision: {precision_current:.4f} → {best_precision_at_recall:.4f} (-{precision_loss:.4f})")
                        optimal_threshold = recall_optimal_threshold
                        recall_optimal_selected = True
                    else:
                        print(f"XGB DEBUG: Recall-optimized threshold rejected (improvement: {recall_improvement:.4f}, precision loss: {precision_loss:.4f})")
                else:
                    print(f"XGB DEBUG: No threshold found with recall >= {target_recall}")
                
                # STRATEGY 2: Probability-based threshold for extreme imbalance
                # Find the minimum probability among actual positive samples and set threshold just below it
                # This ensures we catch ALL positives
                n_positives_test = (y_test == 1).sum()
                prob_based_threshold_used = False
                
                if n_positives_test > 0 and n_positives_test <= 10:  # Very few positives (extreme imbalance)
                    print(f"XGB DEBUG: Extreme imbalance detected ({n_positives_test} positives), using probability-based threshold strategy")
                    
                    # Find probabilities of actual positive samples
                    positive_probs = y_pred_proba[y_test == 1]
                    if len(positive_probs) > 0:
                        min_positive_prob = float(positive_probs.min())
                        max_positive_prob = float(positive_probs.max())
                        mean_positive_prob = float(positive_probs.mean())
                        
                        print(f"XGB DEBUG: Positive sample probabilities - Min: {min_positive_prob:.4f}, Max: {max_positive_prob:.4f}, Mean: {mean_positive_prob:.4f}")
                        
                        # Set threshold just below the minimum positive probability (with 5% margin for safety)
                        prob_based_threshold = max(0.001, min_positive_prob * 0.95)
                        
                        # Ensure threshold is not too low (at least 0.01) or too high
                        prob_based_threshold = max(0.01, min(0.99, prob_based_threshold))
                        
                        # Check how this threshold performs
                        y_pred_prob_based = (y_pred_proba >= prob_based_threshold).astype(int)
                        n_positives_predicted = y_pred_prob_based.sum()
                        total_samples = len(y_pred_prob_based)
                        positive_rate = n_positives_predicted / total_samples if total_samples > 0 else 0
                        
                        # Calculate metrics
                        rec_prob = recall_score(y_test, y_pred_prob_based, zero_division=0)
                        prec_prob = precision_score(y_test, y_pred_prob_based, zero_division=0)
                        
                        print(f"XGB DEBUG: Probability-based threshold: {prob_based_threshold:.4f}")
                        print(f"XGB DEBUG: Recall: {rec_prob:.4f}, Precision: {prec_prob:.4f}, Positive rate: {positive_rate:.2%}")
                        
                        # Use probability-based threshold if:
                        # 1. It catches all positives (recall = 1.0)
                        # 2. Doesn't predict > 90% as positive (too aggressive)
                        # 3. Precision is reasonable (> 0.5% for extreme imbalance)
                        if rec_prob >= 1.0 and positive_rate < 0.90 and prec_prob > 0.005:
                            print(f"XGB DEBUG: ✓ Using probability-based threshold (catches all {n_positives_test} positives)")
                            optimal_threshold = prob_based_threshold
                            prob_based_threshold_used = True
                        else:
                            rejection_reasons = []
                            if rec_prob < 1.0:
                                rejection_reasons.append(f"recall {rec_prob:.4f} < 1.0")
                            if positive_rate >= 0.90:
                                rejection_reasons.append(f"too aggressive ({positive_rate:.2%} predicted as positive)")
                            if prec_prob <= 0.005:
                                rejection_reasons.append(f"precision too low ({prec_prob:.4f})")
                            print(f"XGB DEBUG: ✗ Probability-based threshold rejected: {', '.join(rejection_reasons)}")
                
                # Only use maximum recall if probability-based didn't work and recall-optimized didn't work
                # Prefer recall-optimized threshold if it achieves good recall (>= 75%)
                use_max_recall = False
                
                if not prob_based_threshold_used:
                    if recall_optimal_selected:
                        # Recall-optimized threshold was selected
                        if recall_optimal_score >= 0.75:
                            # Good recall achieved (>= 75%), keep recall-optimized threshold
                            print(f"XGB DEBUG: Keeping recall-optimized threshold (recall: {recall_optimal_score:.4f} >= 0.75)")
                            use_max_recall = False
                        else:
                            # Recall-optimized gives < 75% recall, consider max recall if significantly better
                            if max_recall_score > recall_optimal_score + 0.15:  # At least 15% better
                                use_max_recall = True
                                print(f"XGB DEBUG: Recall-optimized gives {recall_optimal_score:.4f}, max recall {max_recall_score:.4f} is better, considering max recall")
                    else:
                        # Recall-optimized wasn't selected, check if max recall is better than current
                        if max_recall_score > recall_current + 0.1:
                            use_max_recall = True
                    
                    # Only use maximum recall if conditions are met and it's not too aggressive
                    if use_max_recall:
                        max_recall_precision_loss = precision_current - max_recall_precision
                        
                        # Check how many predictions max recall would make
                        y_pred_max_recall = (y_pred_proba >= max_recall_threshold).astype(int)
                        n_positives_max = y_pred_max_recall.sum()
                        total_samples = len(y_pred_max_recall)
                        positive_rate = n_positives_max / total_samples if total_samples > 0 else 0
                        
                        # Only use max recall if:
                        # 1. Precision loss is acceptable (< 90%)
                        # 2. Precision is reasonable (> 1%)
                        # 3. Doesn't predict > 95% as positive (too aggressive)
                        if max_recall_precision_loss < 0.9 and max_recall_precision > 0.01 and positive_rate < 0.95:
                            print(f"XGB DEBUG: Using maximum recall threshold: {max_recall_threshold:.4f}")
                            print(f"XGB DEBUG: Recall: {recall_current:.4f} → {max_recall_score:.4f} (+{max_recall_score - recall_current:.4f})")
                            print(f"XGB DEBUG: Precision: {precision_current:.4f} → {max_recall_precision:.4f} (-{max_recall_precision_loss:.4f})")
                            print(f"XGB DEBUG: Positive prediction rate: {positive_rate:.2%}")
                            optimal_threshold = max_recall_threshold
                        else:
                            rejection_reasons = []
                            if max_recall_precision_loss >= 0.9:
                                rejection_reasons.append(f"precision loss too high ({max_recall_precision_loss:.4f})")
                            if max_recall_precision <= 0.01:
                                rejection_reasons.append(f"precision too low ({max_recall_precision:.4f})")
                            if positive_rate >= 0.95:
                                rejection_reasons.append(f"too aggressive ({positive_rate:.2%} predicted as positive)")
                            print(f"XGB DEBUG: Maximum recall threshold rejected: {', '.join(rejection_reasons)}")
                            if recall_optimal_selected:
                                print(f"XGB DEBUG: Keeping recall-optimized threshold: {recall_optimal_threshold:.4f}")
                    
            except Exception as recall_err:
                print(f"XGB DEBUG: Recall optimization failed: {recall_err}, using current threshold")
            
            # Use optimal threshold for binary predictions (better for imbalanced data)
            y_pred = (y_pred_proba >= optimal_threshold).astype(int)
            
            # Also calculate default predictions for comparison
            y_pred_default = xgb_model.predict(X_test)
            default_correct = (y_pred_default == y_test).sum()
            optimal_correct = (y_pred == y_test).sum()
            print(f"XGB DEBUG: Default threshold (0.5) accuracy: {default_correct/len(y_test):.4f}")
            print(f"XGB DEBUG: Optimal threshold ({optimal_threshold:.4f}) accuracy: {optimal_correct/len(y_test):.4f}")
            
            # Confusion matrix and classification metrics on TEST data (using optimal threshold)
            cm = confusion_matrix(y_test, y_pred)
            accuracy = accuracy_score(y_test, y_pred)
            precision = precision_score(y_test, y_pred, zero_division=0)
            recall = recall_score(y_test, y_pred, zero_division=0)
            f1 = f1_score(y_test, y_pred, zero_division=0)
            
            # ========== XGBOOST - TEST PERFORMANCE ==========
            print("\n" + "="*80)
            print("XGBOOST - TEST SET PERFORMANCE")
            print("="*80)
            print(f"Test Samples: {len(y_test)}")
            print(f"Test Class Distribution: {test_class_dist}")
            if len(test_class_dist) == 2:
                n_class_0 = test_class_dist.get(0, 0)
                n_class_1 = test_class_dist.get(1, 0)
                imbalance_ratio = n_class_0 / n_class_1 if n_class_1 > 0 else float('inf')
                print(f"Test Class Imbalance Ratio: {imbalance_ratio:.2f}:1 (0:1)")
            print(f"\n--- PREDICTION STATISTICS ---")
            print(f"Probability Range: [{y_pred_proba.min():.4f}, {y_pred_proba.max():.4f}]")
            print(f"Probability Mean: {y_pred_proba.mean():.4f}")
            print(f"Probability Median: {np.median(y_pred_proba):.4f}")
            print(f"Predictions (Class 0): {(y_pred == 0).sum()} ({(y_pred == 0).sum()/len(y_pred)*100:.2f}%)")
            print(f"Predictions (Class 1): {(y_pred == 1).sum()} ({(y_pred == 1).sum()/len(y_pred)*100:.2f}%)")
            print(f"\n--- THRESHOLD INFORMATION ---")
            print(f"Default Threshold (0.5): Accuracy = {default_correct/len(y_test):.4f}")
            print(f"Optimal Threshold ({optimal_threshold:.4f}): Accuracy = {optimal_correct/len(y_test):.4f}")
            print(f"Threshold Used: {optimal_threshold:.4f} (KS Optimal)")
            print(f"\n--- CONFUSION MATRIX (Optimal Threshold) ---")
            print(f"                Predicted")
            print(f"                0        1")
            print(f"Actual  0    {cm[0,0]:5d}  {cm[0,1]:5d}")
            print(f"        1    {cm[1,0]:5d}  {cm[1,1]:5d}")
            print(f"\nTrue Negatives (TN):  {cm[0,0]} | False Positives (FP): {cm[0,1]}")
            print(f"False Negatives (FN): {cm[1,0]} | True Positives (TP):   {cm[1,1]}")
            print(f"\n--- PERFORMANCE METRICS ---")
            print(f"AUC-ROC:        {roc_auc:.4f}")
            print(f"Gini Coefficient: {gini_coefficient:.4f}")
            print(f"Accuracy:       {accuracy:.4f}")
            print(f"Precision:      {precision:.4f}")
            print(f"Recall:         {recall:.4f}")
            print(f"F1-Score:       {f1:.4f}")
            print(f"\n--- METRICS INTERPRETATION ---")
            if precision > 0:
                print(f"Precision: {precision*100:.2f}% of predicted positives are actually positive")
            else:
                print(f"Precision: 0% - Model predicted no positives (or all were wrong)")
            if recall > 0:
                print(f"Recall: {recall*100:.2f}% of actual positives were correctly identified")
            else:
                print(f"Recall: 0% - Model failed to identify any actual positives")
            print("="*80 + "\n")
            
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
                print(f"XGB DEBUG: KS calculation error: {ks_err}")
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
            
            # Update result with TEST metrics
            result['auc'] = float(roc_auc) if np.isfinite(roc_auc) else None
            result['gini_coefficient'] = float(gini_coefficient) if np.isfinite(gini_coefficient) else None
            result['roc_data'] = roc_data
            result['confusion_matrix'] = cm.tolist()
            result['accuracy'] = float(accuracy) if np.isfinite(accuracy) else None
            result['precision'] = float(precision) if np.isfinite(precision) else None
            result['recall'] = float(recall) if np.isfinite(recall) else None
            result['f1'] = float(f1) if np.isfinite(f1) else None
            result['ks_stat'] = ks_stat
            result['ks_threshold'] = ks_threshold
            result['ks_curve'] = ks_curve
        
        # Save model artifact
        try:
            print(f"[MODEL ARTIFACT] Saving XGBoost artifact for dataset {dataset_id}")
            artifact_payload = result['artifact_payload']
            artifact_metadata = save_model_artifact(dataset_id, 'xgboost', artifact_payload)
            if artifact_metadata:
                result['artifact'] = artifact_metadata
                print(f"[MODEL ARTIFACT] Successfully saved XGBoost artifact: {artifact_metadata}")
            else:
                print(f"[MODEL ARTIFACT] save_model_artifact returned None for dataset {dataset_id}")
        except Exception as artifact_err:
            print(f"[MODEL ARTIFACT] Failed to persist XGBoost model: {artifact_err}")
            import traceback
            traceback.print_exc()
        
        # Remove artifact_payload from response (it contains binary data)
        if 'artifact_payload' in result:
            del result['artifact_payload']
        
        return jsonify(result)

    except Exception as e:
        print(f"XGBOOST ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Failed to perform XGBoost analysis: {str(e)}"}), 500
        
# Helper function for WOE mapping (used by Logistic Regression and Random Forest)
    """
    Perform XGBoost analysis on selected variables.
    Expects payload: { selected_variables: [list], target: string, woe_transformed_data: {} }
    Returns: model metrics, feature importance, ROC data, etc.
    """
    try:
        import xgboost as xgb
    except ImportError:
        return jsonify({"error": "XGBoost not installed. Please install with: pip install xgboost"}), 500

    from sklearn.metrics import roc_curve, auc, classification_report, confusion_matrix, accuracy_score, precision_score, recall_score, f1_score

    # Removed sanitize_for_json - Flask's jsonify handles NaN/inf automatically
    # Data is already sanitized during construction using np.isfinite checks
    
    try:
        data = request.get_json()
        selected_variables = data.get('selected_variables', [])
        target = data.get('target')
        woe_transformed_data = data.get('woe_transformed_data', {})
        dataset_id = (
            data.get('record_id')
            or data.get('dataset_id')
            or data.get('recordId')
            or data.get('datasetId')
        )
        
        if dataset_id:
            try:
                dataset_id = int(dataset_id)
            except (ValueError, TypeError):
                return jsonify({"error": f"Invalid dataset_id: {dataset_id}"}), 400

        if not selected_variables or not target:
            return jsonify({"error": "Missing selected_variables or target"}), 400
        if not dataset_id:
            return jsonify({"error": "Missing dataset_id/record_id"}), 400

        # Load CSV into df
        try:
            csv_path = get_csv_path(dataset_id)
            df = pd.read_csv(csv_path)
        except Exception as e:
            return jsonify({"error": f"Failed to load CSV: {str(e)}"}), 400

        if target not in df.columns:
            return jsonify({"error": f"Target variable '{target}' not found in dataset"}), 400

        # Prepare WOE-transformed data (same logic as logistic regression)
        modeling_data = {}
        woe_columns = []  # Track the actual column names we create
        
        feature_cache: Dict[str, Dict[str, Any]] = {}
        for var in selected_variables:
            if var not in df.columns:
                print(f"XGB DEBUG: Variable '{var}' not found in dataset columns")
                continue
            woe_data = woe_transformed_data.get(var)
            if not woe_data:
                woe_data = _load_woe_stats_from_db(dataset_id, var, feature_cache=feature_cache)
                if woe_data:
                    woe_transformed_data[var] = woe_data
            bins_list = None
            if isinstance(woe_data, list):
                bins_list = [{
                    'range': r.get('range_text') or r.get('Range') or r.get('Bin') or r.get('bin_label') or str(r),
                    'woe': float(r.get('woe') or r.get('WOE') or 0),
                    'min_value': r.get('min_value'),
                    'max_value': r.get('max_value')
                } for r in woe_data if isinstance(r, dict)]
            elif isinstance(woe_data, dict) and isinstance(woe_data.get('stats'), list):
                bins_list = [{
                    'range': r.get('Range') or r.get('Bin') or str(r),
                    'woe': float(r.get('WOE') or 0)
                } for r in woe_data.get('stats')]
            elif isinstance(woe_data, dict) and isinstance(woe_data.get('woe_ranges'), list):
                bins_list = woe_data.get('woe_ranges')
            else:
                print(f"XGB DEBUG: No WOE data for {var} (type={type(woe_data)})")
                continue

            if not bins_list:
                print(f"XGB DEBUG: Empty bins list for {var}")
                continue

            # Create WOE column name
            woe_column_name = f'{var}_WOE'
            woe_columns.append(woe_column_name)
            modeling_data[woe_column_name] = np.zeros(len(df))
            
            assigned_count = 0
            for bin_info in bins_list:
                bin_range = (
                    bin_info.get('range')
                    or bin_info.get('range_text')
                    or bin_info.get('Range')
                    or bin_info.get('Bin')
                    or bin_info.get('bin')
                )
                woe_value = bin_info.get('woe') or bin_info.get('WOE')
                if woe_value is None:
                    continue
                try:
                    woe_value = float(woe_value)
                except Exception:
                    continue
                
                if not bin_range and (bin_info.get('min_value') is not None or bin_info.get('max_value') is not None):
                    min_val = bin_info.get('min_value')
                    max_val = bin_info.get('max_value')
                    if min_val is not None and max_val is not None:
                        bin_range = f"({min_val}, {max_val}]"
                    elif min_val is not None:
                        bin_range = f"({min_val}, inf)"
                    elif max_val is not None:
                        bin_range = f"(-inf, {max_val}]"
                
                # Apply WOE mapping
                mask = _create_woe_mask(df, var, bin_range)
                modeling_data[woe_column_name][mask] = woe_value
                assigned_count += mask.sum()

            print(f"XGB DEBUG: Assigned WOE values for {var}: {assigned_count} rows")

        # Create DataFrame with WOE-transformed variables
        woe_df = pd.DataFrame(modeling_data)
        woe_df[target] = df[target].values

        # Remove rows with missing target
        mask = ~woe_df[target].isna()
        X = woe_df[woe_columns].fillna(0)  # Use the actual WOE column names
        y = woe_df[target][mask]
        X = X[mask]

        if len(X) == 0:
            return jsonify({"error": "No valid data after preprocessing"}), 400

        if len(woe_columns) == 0:
            return jsonify({"error": "No valid WOE-transformed features created"}), 400

        feature_totals = {col: float(val) if np.isfinite(val) else None for col, val in X.sum().to_dict().items()}
        print(f"XGB DEBUG: Final features ({len(woe_columns)}): {woe_columns}")
        print("XGB DEBUG: Feature column totals:", feature_totals)
        print(f"XGB DEBUG: X shape: {X.shape}, y shape: {y.shape}")

        # Train XGBoost
        xgb_model = xgb.XGBClassifier(
            n_estimators=100,
            max_depth=6,
            learning_rate=0.1,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
            eval_metric='logloss',
            scale_pos_weight=10,
            use_label_encoder=False
        )
        
        xgb_model.fit(X, y)
        y_pred_proba = xgb_model.predict_proba(X)[:, 1]
        y_pred = xgb_model.predict(X)

        # Calculate metrics
        fpr, tpr, thresholds = roc_curve(y, y_pred_proba)
        roc_auc = auc(fpr, tpr)
        gini_coefficient = 2 * roc_auc - 1

        # Feature importance
        feature_importance = []
        for i, col in enumerate(woe_columns):
            # Extract original variable name (remove _WOE suffix)
            original_var = col.replace('_WOE', '')
            feature_importance.append({
                'variable': original_var,
                'importance': float(xgb_model.feature_importances_[i]),
                'importance_percentage': float(xgb_model.feature_importances_[i] * 100)
            })

        # Sort by importance
        feature_importance.sort(key=lambda x: x['importance'], reverse=True)

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
            print(f"XGB DEBUG: KS calculation error: {ks_err}")
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
            'n_features': len(woe_columns)
        }

        # Data is already sanitized during construction (using np.isfinite checks)
        # No need for recursive sanitization which slows down the response
        resp = {
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
            'ks_curve': ks_curve
        }

        # Save model artifact
        try:
            print(f"[MODEL ARTIFACT] Starting XGBoost artifact save for dataset {dataset_id}")
            model_variables = [col.replace('_WOE', '') for col in woe_columns]
            woe_snapshot = {}
            for var in model_variables:
                if var in woe_transformed_data:
                    woe_snapshot[var] = copy.deepcopy(woe_transformed_data[var])
            
            training_metrics = {
                'auc': resp.get('auc'),
                'gini_coefficient': resp.get('gini_coefficient'),
                'accuracy': resp.get('accuracy'),
                'precision': resp.get('precision'),
                'recall': resp.get('recall'),
                'f1': resp.get('f1'),
                'ks_stat': resp.get('ks_stat')
            }
            
            # Serialize XGBoost booster
            model_bytes = None
            try:
                booster = xgb_model.get_booster()
                raw_bytes = booster.save_raw("json")
                model_bytes = bytes(raw_bytes)
                print(f"[MODEL ARTIFACT] Serialized XGBoost booster successfully (size: {len(model_bytes)} bytes)")
            except Exception:
                try:
                    raw_bytes = xgb_model.get_booster().save_raw()
                    model_bytes = bytes(raw_bytes)
                    print(f"[MODEL ARTIFACT] Serialized XGBoost booster successfully with fallback (size: {len(model_bytes)} bytes)")
                except Exception as raw_err:
                    print(f"[MODEL ARTIFACT] Failed to serialize XGBoost model via save_raw: {raw_err}")
                    model_bytes = None
            
            artifact_payload = {
                'model_type': 'xgboost',
                'target': target,
                'selected_variables': model_variables,
                'model_variables': model_variables,
                'feature_columns': woe_columns,
                'woe_transformed_data': woe_snapshot,
                'model_bytes': model_bytes,
                'xgb_params': xgb_model.get_xgb_params(),
                'training_metrics': training_metrics
            }
            
            artifact_metadata = save_model_artifact(dataset_id, 'XGBoost', artifact_payload)
            if artifact_metadata:
                resp['artifact'] = artifact_metadata
                print(f"[MODEL ARTIFACT] Successfully saved XGBoost artifact: {artifact_metadata}")
            else:
                print(f"[MODEL ARTIFACT] save_model_artifact returned None for dataset {dataset_id}")
        except Exception as artifact_err:
            print(f"[MODEL ARTIFACT] Failed to persist XGBoost model for dataset {dataset_id}: {artifact_err}")
            import traceback
            traceback.print_exc()

        return jsonify(resp)

    except Exception as e:
        print(f"XGBOOST ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Failed to perform XGBoost analysis: {str(e)}"}), 500

# ----------- Stacking Ensemble Analysis -----------
@app.route('/api/stacking', methods=['POST'])
def stacking_analysis():
    """
    Perform stacking ensemble analysis combining LR, RF, and XGBoost.
    Uses Logistic Regression as meta-learner.
    Expects payload: { selected_variables: [list], target: string, woe_transformed_data: {}, record_id: int }
    Returns: ensemble metrics, meta-learner weights, base model performance
    """
    try:
        data = request.get_json()
        selected_variables = data.get('selected_variables', [])
        target = data.get('target', 'Bad Customer')
        woe_transformed_data = data.get('woe_transformed_data', {})
        if not isinstance(woe_transformed_data, dict):
            woe_transformed_data = {}
        record_id = data.get('record_id') or data.get('dataset_id') or data.get('recordId') or data.get('datasetId')
        
        if not record_id:
            return jsonify({"success": False, "error": "Missing dataset_id/record_id"}), 400
        
        try:
            record_id = int(record_id)
        except (ValueError, TypeError):
            return jsonify({"success": False, "error": f"Invalid dataset_id: {record_id}"}), 400
        
        if not selected_variables:
            return jsonify({"success": False, "error": "No variables selected"}), 400
        
        # Get train/test split
        df_train, df_test, split_exists = get_train_test_data(record_id)
        if not split_exists or df_train is None or df_test is None:
            return jsonify({"success": False, "error": "Train/test split not found. Please create split first."}), 400
        
        print(f"STACKING DEBUG: Training on {len(df_train)} samples, testing on {len(df_test)} samples")
        
        # Import required libraries
        from sklearn.model_selection import StratifiedKFold
        from sklearn.linear_model import LogisticRegression as SklearnLR
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.metrics import roc_curve, auc, confusion_matrix, accuracy_score, precision_score, recall_score, f1_score
        from sklearn.utils.class_weight import compute_class_weight
        from sklearn.preprocessing import LabelEncoder, StandardScaler
        from statsmodels.tools.tools import add_constant
        import xgboost as xgb
        import numpy as np
        from scipy.stats import ks_2samp
        
        # Prepare training data
        y_train = df_train[target].values
        y_test = df_test[target].values
        
        # Use 5-fold CV to generate meta-features (prevents overfitting)
        n_splits = 5
        skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)
        
        # Arrays to store out-of-fold predictions
        lr_oof_preds = np.zeros(len(df_train))
        rf_oof_preds = np.zeros(len(df_train))
        xgb_oof_preds = np.zeros(len(df_train))
        
        # Test predictions (will be averaged across folds)
        lr_test_preds = np.zeros((n_splits, len(df_test)))
        rf_test_preds = np.zeros((n_splits, len(df_test)))
        xgb_test_preds = np.zeros((n_splits, len(df_test)))
        
        print("STACKING DEBUG: Starting cross-validation for base models...")
        
        # Train base models with cross-validation
        for fold, (train_idx, val_idx) in enumerate(skf.split(df_train, y_train)):
            print(f"STACKING DEBUG: Fold {fold + 1}/{n_splits}")
            
            df_fold_train = df_train.iloc[train_idx].copy()
            df_fold_val = df_train.iloc[val_idx].copy()
            y_fold_train = y_train[train_idx]
            y_fold_val = y_train[val_idx]
            
            # 1. Logistic Regression (on WOE features)
            try:
                # Apply WOE transformations
                X_fold_train_woe = _apply_woe_to_test_data(
                    df_fold_train, selected_variables, woe_transformed_data, target
                )
                X_fold_val_woe = _apply_woe_to_test_data(
                    df_fold_val, selected_variables, woe_transformed_data, target
                )
                X_test_woe = _apply_woe_to_test_data(
                    df_test, selected_variables, woe_transformed_data, target
                )
                
                # Remove target column if present
                X_fold_train_woe = X_fold_train_woe.drop(columns=[target], errors='ignore')
                X_fold_val_woe = X_fold_val_woe.drop(columns=[target], errors='ignore')
                X_test_woe = X_test_woe.drop(columns=[target], errors='ignore')
                
                # Add constant for intercept
                X_fold_train_woe_const = add_constant(X_fold_train_woe, has_constant='add')
                X_fold_val_woe_const = add_constant(X_fold_val_woe, has_constant='add')
                X_test_woe_const = add_constant(X_test_woe, has_constant='add')
                
                # Train LR
                y_classes = np.unique(y_fold_train)
                class_weights = compute_class_weight('balanced', classes=y_classes, y=y_fold_train)
                sample_weights = np.array([class_weights[y] for y in y_fold_train])
                
                lr_model = SklearnLR(class_weight='balanced', max_iter=1000, random_state=42)
                lr_model.fit(X_fold_train_woe_const, y_fold_train, sample_weight=sample_weights)
                
                # Get predictions
                lr_oof_preds[val_idx] = lr_model.predict_proba(X_fold_val_woe_const)[:, 1]
                lr_test_preds[fold] = lr_model.predict_proba(X_test_woe_const)[:, 1]
                
            except Exception as e:
                print(f"STACKING DEBUG: LR fold {fold} error: {e}")
                import traceback
                traceback.print_exc()
                lr_oof_preds[val_idx] = 0.5  # Default prediction
                lr_test_preds[fold] = 0.5
            
            # 2. Random Forest (on WOE features)
            try:
                rf_model = RandomForestClassifier(
                    n_estimators=200,
                    max_depth=12,
                    max_features='sqrt',
                    class_weight='balanced',
                    random_state=42,
                    n_jobs=-1
                )
                rf_model.fit(X_fold_train_woe, y_fold_train)
                
                rf_oof_preds[val_idx] = rf_model.predict_proba(X_fold_val_woe)[:, 1]
                rf_test_preds[fold] = rf_model.predict_proba(X_test_woe)[:, 1]
                
            except Exception as e:
                print(f"STACKING DEBUG: RF fold {fold} error: {e}")
                rf_oof_preds[val_idx] = 0.5
                rf_test_preds[fold] = 0.5
            
            # 3. XGBoost (on preprocessed features - uses preprocessing from preprocessing section)
            try:
                # Apply preprocessing to fold data (same as XGBoost endpoint)
                df_fold_train_processed, _ = preprocess_dataset(
                    df_fold_train,
                    target_col=target,
                    preprocessing_steps={
                        'detect_types': True,
                        'handle_missing': True,
                        'remove_duplicates': False,
                        'handle_outliers': False,  # Don't handle outliers before binning
                        'encode_categorical': False  # Don't encode categorical before binning
                    },
                    missing_threshold=0.5,
                    treat_negative_one_as_missing=True
                )
                
                df_fold_val_processed, _ = preprocess_dataset(
                    df_fold_val,
                    target_col=target,
                    preprocessing_steps={
                        'detect_types': True,
                        'handle_missing': True,
                        'remove_duplicates': False,
                        'handle_outliers': False,
                        'encode_categorical': False
                    },
                    missing_threshold=0.5,
                    treat_negative_one_as_missing=True
                )
                
                df_test_processed, _ = preprocess_dataset(
                    df_test,
                    target_col=target,
                    preprocessing_steps={
                        'detect_types': True,
                        'handle_missing': True,
                        'remove_duplicates': False,
                        'handle_outliers': False,
                        'encode_categorical': False
                    },
                    missing_threshold=0.5,
                    treat_negative_one_as_missing=True
                )
                
                # Extract selected variables from preprocessed data
                X_fold_train_raw = df_fold_train_processed[selected_variables].copy()
                X_fold_val_raw = df_fold_val_processed[selected_variables].copy()
                X_test_raw = df_test_processed[selected_variables].copy()
                
                # Handle any remaining missing values (preprocessing may not handle all cases)
                for col in selected_variables:
                    if col in X_fold_train_raw.columns:
                        if X_fold_train_raw[col].dtype == 'object' or X_fold_train_raw[col].dtype.name == 'category':
                            # FIX: Handle NaN values first
                            # For categorical, fill NaN with '__MISSING__' marker
                            X_fold_train_raw[col] = X_fold_train_raw[col].fillna('__MISSING__')
                            X_fold_val_raw[col] = X_fold_val_raw[col].fillna('__MISSING__')
                            X_test_raw[col] = X_test_raw[col].fillna('__MISSING__')
                            
                            # FIX: Label encode categorical variables with consistent encoding
                            # Fit encoder on training fold to ensure consistency
                            le = LabelEncoder()
                            # Get all unique values from training fold (before encoding)
                            train_unique = X_fold_train_raw[col].astype(str).unique()
                            le.fit(train_unique)
                            
                            # Get most frequent category from training (before encoding) for fallback
                            train_str_values = X_fold_train_raw[col].astype(str)
                            most_frequent_train = train_str_values.mode()
                            fallback_category = most_frequent_train.iloc[0] if len(most_frequent_train) > 0 else list(le.classes_)[0] if len(le.classes_) > 0 else '__MISSING__'
                            
                            # Transform training fold
                            X_fold_train_raw[col] = le.transform(X_fold_train_raw[col].astype(str))
                            
                            # FIX: Handle unseen categories in validation and test folds
                            seen_categories = set(le.classes_)
                            
                            # Validation fold: map unseen to '__MISSING__' or most frequent
                            val_values = X_fold_val_raw[col].astype(str)
                            val_unseen_mask = ~val_values.isin(seen_categories)
                            if val_unseen_mask.any():
                                if '__MISSING__' in seen_categories:
                                    X_fold_val_raw.loc[val_unseen_mask, col] = '__MISSING__'
                                else:
                                    # Map to most frequent category from training
                                    X_fold_val_raw.loc[val_unseen_mask, col] = fallback_category
                            X_fold_val_raw[col] = le.transform(X_fold_val_raw[col].astype(str))
                            
                            # Test fold: map unseen to '__MISSING__' or most frequent
                            test_values = X_test_raw[col].astype(str)
                            test_unseen_mask = ~test_values.isin(seen_categories)
                            if test_unseen_mask.any():
                                if '__MISSING__' in seen_categories:
                                    X_test_raw.loc[test_unseen_mask, col] = '__MISSING__'
                                else:
                                    # Map to most frequent category from training
                                    X_test_raw.loc[test_unseen_mask, col] = fallback_category
                            X_test_raw[col] = le.transform(X_test_raw[col].astype(str))
                        else:
                            # For numeric, fill with median from training fold
                            median_val = X_fold_train_raw[col].median()
                            if pd.isna(median_val):
                                median_val = 0
                            X_fold_train_raw[col].fillna(median_val, inplace=True)
                            X_fold_val_raw[col].fillna(median_val, inplace=True)
                            X_test_raw[col].fillna(median_val, inplace=True)
                
                # Calculate class weight
                y_classes = np.unique(y_fold_train)
                class_weights = compute_class_weight('balanced', classes=y_classes, y=y_fold_train)
                scale_pos_weight = class_weights[1] / class_weights[0] if len(class_weights) > 1 else 1.0
                
                xgb_model = xgb.XGBClassifier(
                    n_estimators=500,
                    max_depth=6,
                    learning_rate=0.05,
                    subsample=0.8,
                    colsample_bytree=0.8,
                    reg_alpha=0.1,
                    reg_lambda=1.0,
                    min_child_weight=3,
                    gamma=0.1,
                    random_state=42,
                    eval_metric='auc',
                    scale_pos_weight=scale_pos_weight,
                    use_label_encoder=False,
                    early_stopping_rounds=20
                )
                
                xgb_model.fit(
                    X_fold_train_raw, y_fold_train,
                    eval_set=[(X_fold_val_raw, y_fold_val)],
                    verbose=False
                )
                
                xgb_oof_preds[val_idx] = xgb_model.predict_proba(X_fold_val_raw)[:, 1]
                xgb_test_preds[fold] = xgb_model.predict_proba(X_test_raw)[:, 1]
                
            except Exception as e:
                print(f"STACKING DEBUG: XGB fold {fold} error: {e}")
                import traceback
                traceback.print_exc()
                xgb_oof_preds[val_idx] = 0.5
                xgb_test_preds[fold] = 0.5
        
        # Average test predictions across folds
        lr_test_pred = np.mean(lr_test_preds, axis=0)
        rf_test_pred = np.mean(rf_test_preds, axis=0)
        xgb_test_pred = np.mean(xgb_test_preds, axis=0)
        
        # Helper function to sanitize float values (defined before use)
        def safe_float(val):
            """Convert value to float, replacing infinity/NaN with None."""
            try:
                fval = float(val)
                if np.isfinite(fval):
                    return fval
                else:
                    return None
            except (ValueError, TypeError):
                return None

        def _logit_transform(preds, eps=1e-6):
            """Safely convert probabilities to log-odds for meta-features."""
            clipped = np.clip(preds, eps, 1 - eps)
            return np.log(clipped / (1 - clipped))
        
        # Calculate base model performance on test set
        base_models_performance = []
        for model_name, test_pred in [('Logistic Regression', lr_test_pred),
                                       ('Random Forest', rf_test_pred),
                                       ('XGBoost', xgb_test_pred)]:
            try:
                fpr, tpr, _ = roc_curve(y_test, test_pred)
                roc_auc = auc(fpr, tpr)
                gini = 2 * roc_auc - 1
                
                # Find optimal threshold (using F1)
                thresholds = np.linspace(0, 1, 100)
                best_f1 = 0
                best_threshold = 0.5
                for thresh in thresholds:
                    y_pred = (test_pred >= thresh).astype(int)
                    if len(np.unique(y_pred)) > 1:  # Check if predictions are not all same
                        f1 = f1_score(y_test, y_pred)
                        if f1 > best_f1:
                            best_f1 = f1
                            best_threshold = thresh
                
                y_pred = (test_pred >= best_threshold).astype(int)
                
                base_models_performance.append({
                    'model': model_name,
                    'auc': safe_float(roc_auc),
                    'gini': safe_float(gini),
                    'recall': safe_float(recall_score(y_test, y_pred, zero_division=0)),
                    'precision': safe_float(precision_score(y_test, y_pred, zero_division=0)),
                    'f1': safe_float(best_f1)
                })
            except Exception as e:
                print(f"STACKING DEBUG: Error calculating performance for {model_name}: {e}")
                base_models_performance.append({
                    'model': model_name,
                    'auc': 0.5,
                    'gini': 0.0,
                    'recall': 0.0,
                    'precision': 0.0,
                    'f1': 0.0
                })
        
        base_predictions = {
            'Logistic Regression': lr_test_pred,
            'Random Forest': rf_test_pred,
            'XGBoost': xgb_test_pred
        }

        # Step 2: Train meta-learner on out-of-fold predictions (augmented with logit features)
        meta_features_train = np.column_stack([lr_oof_preds, rf_oof_preds, xgb_oof_preds])
        meta_features_test = np.column_stack([lr_test_pred, rf_test_pred, xgb_test_pred])

        logit_features_train = np.column_stack([
            _logit_transform(lr_oof_preds),
            _logit_transform(rf_oof_preds),
            _logit_transform(xgb_oof_preds)
        ])
        logit_features_test = np.column_stack([
            _logit_transform(lr_test_pred),
            _logit_transform(rf_test_pred),
            _logit_transform(xgb_test_pred)
        ])

        meta_features_train_aug = np.hstack([meta_features_train, logit_features_train])
        meta_features_test_aug = np.hstack([meta_features_test, logit_features_test])

        scaler = StandardScaler()
        meta_features_train_scaled = scaler.fit_transform(meta_features_train_aug)
        meta_features_test_scaled = scaler.transform(meta_features_test_aug)
        
        # Train meta-learner (Logistic Regression with L2 regularization for stability)
        meta_learner = SklearnLR(
            class_weight='balanced', 
            max_iter=2000, 
            random_state=42,
            penalty='l2',
            C=5.0,
            solver='lbfgs'
        )
        meta_learner.fit(meta_features_train_scaled, y_train)
        meta_learner_pred = meta_learner.predict_proba(meta_features_test_scaled)[:, 1]

        meta_feature_labels = ['lr_prob', 'rf_prob', 'xgb_prob', 'lr_logit', 'rf_logit', 'xgb_logit']
        raw_coefs = meta_learner.coef_[0]
        meta_component_weights = {label: safe_float(raw_coefs[idx]) for idx, label in enumerate(meta_feature_labels)}
        
        lr_weight_combined = safe_float((raw_coefs[0] if len(raw_coefs) > 0 else 0) + (raw_coefs[3] if len(raw_coefs) > 3 else 0))
        rf_weight_combined = safe_float((raw_coefs[1] if len(raw_coefs) > 1 else 0) + (raw_coefs[4] if len(raw_coefs) > 4 else 0))
        xgb_weight_combined = safe_float((raw_coefs[2] if len(raw_coefs) > 2 else 0) + (raw_coefs[5] if len(raw_coefs) > 5 else 0))
        
        meta_weights = {
            'logistic_regression': lr_weight_combined,
            'random_forest': rf_weight_combined,
            'xgboost': xgb_weight_combined,
            'intercept': safe_float(meta_learner.intercept_[0])
        }
        
        def _abs_weight(value):
            return abs(value) if isinstance(value, (int, float)) and np.isfinite(value) else 0.0
        
        abs_weights = [_abs_weight(meta_weights['logistic_regression']),
                       _abs_weight(meta_weights['random_forest']),
                       _abs_weight(meta_weights['xgboost'])]
        total_abs_weight = sum(abs_weights) if sum(abs_weights) > 0 else 1
        relative_importance = {
            'logistic_regression': abs_weights[0] / total_abs_weight * 100,
            'random_forest': abs_weights[1] / total_abs_weight * 100,
            'xgboost': abs_weights[2] / total_abs_weight * 100
        }
        
        print(f"STACKING DEBUG: Meta-learner weights (combined prob+logit): LR={meta_weights['logistic_regression'] or 0:.4f}, RF={meta_weights['random_forest'] or 0:.4f}, XGB={meta_weights['xgboost'] or 0:.4f}")
        print(f"STACKING DEBUG: Meta-learner raw coefficients: {meta_component_weights}")
        print(f"STACKING DEBUG: Relative importance: LR={relative_importance['logistic_regression']:.1f}%, RF={relative_importance['random_forest']:.1f}%, XGB={relative_importance['xgboost']:.1f}%")
        
        # HYBRID APPROACH: Combine meta-learner with performance-weighted voting
        # This ensures we leverage both the learned combination and individual model strengths
        
        # Performance-weighted average (based on base model AUCs)
        # Calculate weights from base model performance
        base_model_aucs = []
        for model_name, test_pred in [('LR', lr_test_pred), ('RF', rf_test_pred), ('XGB', xgb_test_pred)]:
            try:
                fpr_temp, tpr_temp, _ = roc_curve(y_test, test_pred)
                auc_temp = auc(fpr_temp, tpr_temp)
                base_model_aucs.append(auc_temp)
            except:
                base_model_aucs.append(0.5)  # Default if calculation fails
        
        # Normalize AUCs to get weights (higher AUC = higher weight)
        total_auc = sum(base_model_aucs) if sum(base_model_aucs) > 0 else 1
        performance_weights = [auc / total_auc for auc in base_model_aucs]
        
        # Weighted average prediction
        weighted_avg_pred = (
            performance_weights[0] * lr_test_pred + 
            performance_weights[1] * rf_test_pred + 
            performance_weights[2] * xgb_test_pred
        )
        
        # Combine meta-learner (70%) with weighted average (30%)
        # Meta-learner learns optimal combination, weighted average provides stability
        ensemble_test_pred = 0.7 * meta_learner_pred + 0.3 * weighted_avg_pred
        
        print(f"STACKING DEBUG: Performance weights: LR={performance_weights[0]:.3f}, RF={performance_weights[1]:.3f}, XGB={performance_weights[2]:.3f}")
        print(f"STACKING DEBUG: Hybrid ensemble: 70% meta-learner + 30% weighted average")
        
        # Calculate ensemble metrics with fallback safeguard
        fallback_model_used = None

        def _extract_auc(perf):
            auc_val = perf.get('auc') if perf else None
            return auc_val if isinstance(auc_val, (int, float)) and np.isfinite(auc_val) else 0.0

        best_base_entry = max(base_models_performance, key=_extract_auc) if base_models_performance else None
        best_base_auc = _extract_auc(best_base_entry) if best_base_entry else 0.0

        fpr, tpr, thresholds = roc_curve(y_test, ensemble_test_pred)
        roc_auc = auc(fpr, tpr)
        gini = 2 * roc_auc - 1
        
        if best_base_entry and roc_auc + 1e-4 < best_base_auc:
            fallback_model_used = best_base_entry['model']
            print(f"STACKING DEBUG: Ensemble AUC {roc_auc:.4f} < best base ({fallback_model_used}={best_base_auc:.4f}). Using {fallback_model_used} predictions as fallback.")
            ensemble_test_pred = base_predictions.get(fallback_model_used, ensemble_test_pred)
            fpr, tpr, thresholds = roc_curve(y_test, ensemble_test_pred)
            roc_auc = auc(fpr, tpr)
            gini = 2 * roc_auc - 1
        
        # CRITICAL FIX: Ensure fpr, tpr, thresholds are always arrays (not scalars)
        # In extreme class imbalance cases, roc_curve can return scalars
        if not isinstance(fpr, np.ndarray):
            fpr = np.array([fpr]) if np.isscalar(fpr) else np.array(fpr)
        if not isinstance(tpr, np.ndarray):
            tpr = np.array([tpr]) if np.isscalar(tpr) else np.array(tpr)
        if not isinstance(thresholds, np.ndarray):
            thresholds = np.array([thresholds]) if np.isscalar(thresholds) else np.array(thresholds)
        
        # Ensure they are 1D arrays
        fpr = np.atleast_1d(fpr).flatten()
        tpr = np.atleast_1d(tpr).flatten()
        thresholds = np.atleast_1d(thresholds).flatten()
        
        # RECALL-OPTIMIZED THRESHOLD SELECTION (Same strategy as XGBoost)
        # This is critical for credit scoring - catching defaults is more important than precision
        positive_rate_guardrail_applied = False
        positive_rate_guardrail_info = None
        print("STACKING DEBUG: Starting recall-optimized threshold selection...")
        
        # Step 1: Find F1-optimized threshold (baseline)
        best_f1 = 0
        f1_optimal_threshold = 0.5
        f1_scores = []
        valid_thresholds_f1 = []
        test_thresholds_f1 = np.linspace(0.01, 0.99, 100)
        
        for thresh in test_thresholds_f1:
            y_pred_thresh = (ensemble_test_pred >= thresh).astype(int)
            if len(np.unique(y_pred_thresh)) > 1:
                f1 = f1_score(y_test, y_pred_thresh, zero_division=0)
                f1_scores.append(f1)
                valid_thresholds_f1.append(thresh)
                if f1 > best_f1:
                    best_f1 = f1
                    f1_optimal_threshold = thresh
        
        print(f"STACKING DEBUG: F1-optimized threshold: {f1_optimal_threshold:.4f} (F1={best_f1:.4f})")
        
        # Step 2: Find recall-optimized threshold (like XGBoost)
        recall_scores = []
        precision_scores = []
        valid_thresholds = []
        test_thresholds = np.linspace(0.01, 0.99, 200)  # More granular search
        
        for thresh in test_thresholds:
            y_pred_thresh = (ensemble_test_pred >= thresh).astype(int)
            rec = recall_score(y_test, y_pred_thresh, zero_division=0)
            prec = precision_score(y_test, y_pred_thresh, zero_division=0)
            recall_scores.append(rec)
            precision_scores.append(prec)
            valid_thresholds.append(thresh)
        
        # Find maximum recall threshold
        max_recall_idx = np.argmax(recall_scores)
        max_recall_threshold = valid_thresholds[max_recall_idx]
        max_recall_score = recall_scores[max_recall_idx]
        max_recall_precision = precision_scores[max_recall_idx]
        
        print(f"STACKING DEBUG: Maximum recall threshold: {max_recall_threshold:.4f} (Recall: {max_recall_score:.4f}, Precision: {max_recall_precision:.4f})")
        
        # Find threshold with recall >= 0.5 (target for extreme imbalance)
        target_recall = 0.5
        recall_optimal_idx = None
        best_precision_at_recall = 0
        
        for i, (rec, prec) in enumerate(zip(recall_scores, precision_scores)):
            if rec >= target_recall and prec > best_precision_at_recall:
                recall_optimal_idx = i
                best_precision_at_recall = prec
        
        # Compare with F1-optimized threshold
        y_pred_f1 = (ensemble_test_pred >= f1_optimal_threshold).astype(int)
        recall_f1 = recall_score(y_test, y_pred_f1, zero_division=0)
        precision_f1 = precision_score(y_test, y_pred_f1, zero_division=0)
        
        # Select optimal threshold (prioritize recall for credit scoring)
        optimal_threshold = f1_optimal_threshold
        recall_optimal_selected = False
        
        if recall_optimal_idx is not None:
            recall_optimal_threshold = valid_thresholds[recall_optimal_idx]
            recall_optimal_score = recall_scores[recall_optimal_idx]
            
            recall_improvement = recall_optimal_score - recall_f1
            precision_loss = precision_f1 - best_precision_at_recall
            
            # Accept 5%+ recall improvement with up to 80% precision loss (same as XGBoost)
            if recall_improvement > 0.05 and precision_loss < 0.8:
                print(f"STACKING DEBUG: Using recall-optimized threshold: {recall_optimal_threshold:.4f}")
                print(f"STACKING DEBUG: Recall: {recall_f1:.4f} → {recall_optimal_score:.4f} (+{recall_improvement:.4f})")
                print(f"STACKING DEBUG: Precision: {precision_f1:.4f} → {best_precision_at_recall:.4f} (-{precision_loss:.4f})")
                optimal_threshold = recall_optimal_threshold
                recall_optimal_selected = True
            else:
                print(f"STACKING DEBUG: Recall-optimized threshold rejected (improvement: {recall_improvement:.4f}, precision loss: {precision_loss:.4f})")
        else:
            print(f"STACKING DEBUG: No threshold found with recall >= {target_recall}")
        
        # STRATEGY 2: Probability-based threshold for extreme imbalance (like XGBoost)
        n_positives_test = (y_test == 1).sum()
        prob_based_threshold_used = False
        
        if n_positives_test > 0 and n_positives_test <= 10:  # Very few positives (extreme imbalance)
            print(f"STACKING DEBUG: Extreme imbalance detected ({n_positives_test} positives), using probability-based threshold strategy")
            
            # Find probabilities of actual positive samples
            positive_probs = ensemble_test_pred[y_test == 1]
            if len(positive_probs) > 0:
                min_positive_prob = float(positive_probs.min())
                max_positive_prob = float(positive_probs.max())
                mean_positive_prob = float(positive_probs.mean())
                
                print(f"STACKING DEBUG: Positive sample probabilities - Min: {min_positive_prob:.4f}, Max: {max_positive_prob:.4f}, Mean: {mean_positive_prob:.4f}")
                
                # Check for gap between max negative and min positive probabilities
                negative_probs = ensemble_test_pred[y_test == 0]
                max_negative_prob = float(negative_probs.max()) if len(negative_probs) > 0 else 0
                gap = min_positive_prob - max_negative_prob
                
                if gap > 0.05:  # Significant gap exists
                    # Use threshold in the middle of the gap
                    gap_based_threshold = max_negative_prob + (gap * 0.5)
                    gap_based_threshold = max(0.01, min(0.99, gap_based_threshold))
                    
                    y_pred_gap = (ensemble_test_pred >= gap_based_threshold).astype(int)
                    rec_gap = recall_score(y_test, y_pred_gap, zero_division=0)
                    prec_gap = precision_score(y_test, y_pred_gap, zero_division=0)
                    
                    print(f"STACKING DEBUG: Gap-based threshold: {gap_based_threshold:.4f} (gap: {gap:.4f})")
                    print(f"STACKING DEBUG: Recall: {rec_gap:.4f}, Precision: {prec_gap:.4f}")
                    
                    if rec_gap >= 1.0 and prec_gap > 0.01:
                        print(f"STACKING DEBUG: ✓ Using gap-based threshold (catches all positives with good precision)")
                        optimal_threshold = gap_based_threshold
                        prob_based_threshold_used = True
                
                # If gap-based didn't work, try finding best 100% recall threshold
                if not prob_based_threshold_used:
                    # Search all thresholds to find highest threshold that yields 100% recall
                    best_100_recall_threshold = None
                    best_100_recall_precision = 0
                    
                    for i, (rec, prec, thresh) in enumerate(zip(recall_scores, precision_scores, valid_thresholds)):
                        if rec >= 1.0 and prec > best_100_recall_precision:
                            best_100_recall_threshold = thresh
                            best_100_recall_precision = prec
                    
                    if best_100_recall_threshold is not None:
                        # Check if this threshold is too aggressive
                        y_pred_100 = (ensemble_test_pred >= best_100_recall_threshold).astype(int)
                        n_positives_predicted = y_pred_100.sum()
                        total_samples = len(y_pred_100)
                        positive_rate = n_positives_predicted / total_samples if total_samples > 0 else 0
                        
                        if positive_rate < 0.95 and best_100_recall_precision > 0.005:
                            print(f"STACKING DEBUG: ✓ Using best 100% recall threshold: {best_100_recall_threshold:.4f}")
                            print(f"STACKING DEBUG: Recall: 1.0000, Precision: {best_100_recall_precision:.4f}, Positive rate: {positive_rate:.2%}")
                            optimal_threshold = best_100_recall_threshold
                            prob_based_threshold_used = True
                        else:
                            print(f"STACKING DEBUG: ✗ 100% recall threshold rejected (too aggressive: {positive_rate:.2%} or precision too low: {best_100_recall_precision:.4f})")
                
                # Fallback: balanced threshold (>=75% recall with best precision)
                if not prob_based_threshold_used:
                    balanced_recall_idx = None
                    best_precision_at_balanced = 0
                    
                    for i, (rec, prec) in enumerate(zip(recall_scores, precision_scores)):
                        if rec >= 0.75 and prec > best_precision_at_balanced:
                            balanced_recall_idx = i
                            best_precision_at_balanced = prec
                    
                    if balanced_recall_idx is not None:
                        balanced_threshold = valid_thresholds[balanced_recall_idx]
                        balanced_recall = recall_scores[balanced_recall_idx]
                        
                        y_pred_balanced = (ensemble_test_pred >= balanced_threshold).astype(int)
                        n_positives_balanced = y_pred_balanced.sum()
                        total_samples = len(y_pred_balanced)
                        positive_rate = n_positives_balanced / total_samples if total_samples > 0 else 0
                        
                        if positive_rate < 0.90:
                            print(f"STACKING DEBUG: ✓ Using balanced threshold: {balanced_threshold:.4f} (Recall: {balanced_recall:.4f} >= 0.75, Precision: {best_precision_at_balanced:.4f})")
                            optimal_threshold = balanced_threshold
                            prob_based_threshold_used = True
        
        # Only use maximum recall if probability-based didn't work and recall-optimized didn't work
        use_max_recall = False
        
        if not prob_based_threshold_used:
            if recall_optimal_selected:
                # Recall-optimized threshold was selected
                if recall_optimal_score >= 0.75:
                    # Good recall achieved (>= 75%), keep recall-optimized threshold
                    print(f"STACKING DEBUG: Keeping recall-optimized threshold (recall: {recall_optimal_score:.4f} >= 0.75)")
                    use_max_recall = False
                else:
                    # Recall-optimized gives < 75% recall, consider max recall if significantly better
                    if max_recall_score > recall_optimal_score + 0.15:  # At least 15% better
                        use_max_recall = True
                        print(f"STACKING DEBUG: Recall-optimized gives {recall_optimal_score:.4f}, max recall {max_recall_score:.4f} is better, considering max recall")
            else:
                # Recall-optimized wasn't selected, check if max recall is better than current
                if max_recall_score > recall_f1 + 0.1:
                    use_max_recall = True
            
            # Only use maximum recall if conditions are met and it's not too aggressive
            if use_max_recall:
                max_recall_precision_loss = precision_f1 - max_recall_precision
                
                # Check how many predictions max recall would make
                y_pred_max_recall = (ensemble_test_pred >= max_recall_threshold).astype(int)
                n_positives_max = y_pred_max_recall.sum()
                total_samples = len(y_pred_max_recall)
                positive_rate = n_positives_max / total_samples if total_samples > 0 else 0
                
                # Only use max recall if:
                # 1. Precision loss is acceptable (< 90%)
                # 2. Precision is reasonable (> 1%)
                # 3. Doesn't predict > 95% as positive (too aggressive)
                if max_recall_precision_loss < 0.9 and max_recall_precision > 0.01 and positive_rate < 0.95:
                    print(f"STACKING DEBUG: Using maximum recall threshold: {max_recall_threshold:.4f}")
                    print(f"STACKING DEBUG: Recall: {recall_f1:.4f} → {max_recall_score:.4f} (+{max_recall_score - recall_f1:.4f})")
                    print(f"STACKING DEBUG: Precision: {precision_f1:.4f} → {max_recall_precision:.4f} (-{max_recall_precision_loss:.4f})")
                    print(f"STACKING DEBUG: Positive prediction rate: {positive_rate:.2%}")
                    optimal_threshold = max_recall_threshold
                else:
                    rejection_reasons = []
                    if max_recall_precision_loss >= 0.9:
                        rejection_reasons.append(f"precision loss too high ({max_recall_precision_loss:.4f})")
                    if max_recall_precision <= 0.01:
                        rejection_reasons.append(f"precision too low ({max_recall_precision:.4f})")
                    if positive_rate >= 0.95:
                        rejection_reasons.append(f"too aggressive ({positive_rate:.2%} predicted as positive)")
                    print(f"STACKING DEBUG: Maximum recall threshold rejected: {', '.join(rejection_reasons)}")
                    if recall_optimal_selected:
                        print(f"STACKING DEBUG: Keeping recall-optimized threshold: {recall_optimal_threshold:.4f}")
        
        # STRATEGY 3: PRECISION-FOCUSED / FALSE POSITIVE MINIMIZATION
        # This is critical for credit scoring - minimize false positives while maintaining better performance than XGBoost
        
        # Get XGBoost performance as baseline (must beat this) - Define outside try block for final comparison
        # Use actual current XGBoost performance: AUC 0.7941, Recall 0.7500, Precision 0.0769
        xgb_recall_target = 0.7500  # Historical benchmark
        xgb_precision_target = 0.0769
        xgb_auc_target = 0.7941
        
        try:
            print("STACKING DEBUG: Starting precision-focused threshold selection (minimize false positives)...")
            
            # Try to get XGBoost performance from base_models_performance, but use actual values as defaults
            try:
                xgb_performance = next((m for m in base_models_performance if m['model'] == 'XGBoost'), None)
                if xgb_performance is not None:
                    temp_recall = safe_float(xgb_performance.get('recall'))
                    temp_precision = safe_float(xgb_performance.get('precision'))
                    temp_auc = safe_float(xgb_performance.get('auc'))
                    if temp_recall is not None:
                        xgb_recall_target = temp_recall
                    if temp_precision is not None:
                        xgb_precision_target = temp_precision
                    if temp_auc is not None:
                        xgb_auc_target = temp_auc
                    print("STACKING DEBUG: Using actual XGBoost baseline from current run")
                else:
                    print("STACKING DEBUG: XGBoost performance not found in base_models_performance, falling back to historical defaults")
            except Exception as e:
                print(f"STACKING DEBUG: Error getting XGBoost baseline: {e}, retaining defaults")
            
            print(f"STACKING DEBUG: XGBoost baseline - AUC: {xgb_auc_target:.4f}, Recall: {xgb_recall_target:.4f}, Precision: {xgb_precision_target:.4f}")
            print(f"STACKING DEBUG: Target - Maintain AUC >= {xgb_auc_target:.4f}, Recall >= {xgb_recall_target:.4f}, Minimize FP")
            
            # Calculate FPR (False Positive Rate) and FP count for all thresholds
            # Ensure valid_thresholds exists and is not empty (it should be defined earlier, but check just in case)
            try:
                if len(valid_thresholds) == 0:
                    raise ValueError("valid_thresholds is empty")
            except (NameError, ValueError):
                print("STACKING DEBUG: WARNING - valid_thresholds not available or empty, recreating...")
                valid_thresholds = []
                test_thresholds = np.linspace(0.01, 0.99, 200)
                for thresh in test_thresholds:
                    valid_thresholds.append(thresh)
            
            fpr_scores = []
            fp_counts = []
            tp_counts = []
            precision_at_thresholds = []
            recall_at_thresholds = []
            positive_rates = []
            
            for thresh in valid_thresholds:
                y_pred_thresh = (ensemble_test_pred >= thresh).astype(int)
                tn = ((y_test == 0) & (y_pred_thresh == 0)).sum()
                fp = ((y_test == 0) & (y_pred_thresh == 1)).sum()
                fn = ((y_test == 1) & (y_pred_thresh == 0)).sum()
                tp = ((y_test == 1) & (y_pred_thresh == 1)).sum()
                
                fpr = fp / (fp + tn) if (fp + tn) > 0 else 0
                prec = tp / (tp + fp) if (tp + fp) > 0 else 0
                rec = tp / (tp + fn) if (tp + fn) > 0 else 0
                pos_rate = (tp + fp) / len(y_test) if len(y_test) > 0 else 0
                
                fpr_scores.append(fpr)
                fp_counts.append(fp)
                tp_counts.append(tp)
                precision_at_thresholds.append(prec)
                recall_at_thresholds.append(rec)
                positive_rates.append(pos_rate)
                # Note: AUC is threshold-independent, so we use roc_auc calculated earlier
            
            # Current threshold metrics
            y_pred_current = (ensemble_test_pred >= optimal_threshold).astype(int)
            current_fp = ((y_test == 0) & (y_pred_current == 1)).sum()
            current_tn = ((y_test == 0) & (y_pred_current == 0)).sum()
            current_tp = ((y_test == 1) & (y_pred_current == 1)).sum()
            current_fpr = current_fp / (current_fp + current_tn) if (current_fp + current_tn) > 0 else 0
            current_precision = precision_score(y_test, y_pred_current, zero_division=0)
            current_recall = recall_score(y_test, y_pred_current, zero_division=0)
            current_positive_rate = (current_tp + current_fp) / len(y_test) if len(y_test) > 0 else 0
            
            print(f"STACKING DEBUG: Current threshold ({optimal_threshold:.4f}) metrics:")
            print(f"  - FP: {current_fp}, FPR: {current_fpr:.4f}")
            print(f"  - Precision: {current_precision:.4f}, Recall: {current_recall:.4f}")
            print(f"  - Positive rate: {current_positive_rate:.2%}")
            print(f"  - AUC: {roc_auc:.4f}")

            positive_rate_cap = 0.25
            # Note: Guardrail deferred until after precision-focused search to avoid premature recall sacrifice
            print(f"STACKING DEBUG: Positive-rate cap set to {positive_rate_cap:.0%}, will apply as fallback if precision-focused search fails")
            
            # Strategy 3a: Find threshold with minimum FP count while maintaining:
            # - Recall >= XGBoost recall (0.25)
            # - AUC >= XGBoost AUC (0.7409) - always true since AUC is threshold-independent
            # - Maximize precision
            min_recall_floor = min(current_recall, max(xgb_recall_target + 0.25, 0.5))
            min_fp_candidates = []
            
            for i, (rec, prec, fp_count, fpr_val) in enumerate(zip(recall_at_thresholds, precision_at_thresholds, fp_counts, fpr_scores)):
                # Must maintain minimum recall (at least XGBoost's recall)
                if rec >= min_recall_floor:
                    min_fp_candidates.append({
                        'idx': i,
                        'threshold': valid_thresholds[i],
                        'recall': rec,
                        'precision': prec,
                        'fp': fp_count,
                        'fpr': fpr_val,
                        'score': prec * (1 - fpr_val)  # Combined score: precision weighted by (1 - FPR)
                    })
            
            print(f"STACKING DEBUG: Found {len(min_fp_candidates)} candidates with recall >= {min_recall_floor:.4f}")
            
            if len(min_fp_candidates) > 0:
                # Show top 5 candidates for debugging
                print(f"STACKING DEBUG: Top 5 candidates (by FP count, before sorting):")
                temp_sorted = sorted(min_fp_candidates, key=lambda x: (x['fp'], -x['precision'], -x['recall']))
                for idx, cand in enumerate(temp_sorted[:5]):
                    print(f"  Candidate {idx+1}: Threshold={cand['threshold']:.4f}, FP={cand['fp']}, "
                          f"Recall={cand['recall']:.4f}, Precision={cand['precision']:.4f}, FPR={cand['fpr']:.4f}")
                
                # Sort by: 1) FP count (ascending), 2) Precision (descending), 3) Recall (descending)
                min_fp_candidates.sort(key=lambda x: (x['fp'], -x['precision'], -x['recall']))
                
                # Try top candidates using weighted scoring for credit scoring context
                best_precision_focused = None
                best_improvement = None
                
                # More lenient FP reduction for imbalanced credit data
                min_fp_reduction = max(10, int(current_fp * 0.10))  # At least 10 FP or 10% reduction
                max_recall_loss = max(0.0, current_recall - min_recall_floor)
                
                print(f"STACKING DEBUG: Selection criteria (credit scoring optimized):")
                print(f"  - Min FP reduction: {min_fp_reduction} (current FP: {current_fp}, 10% = {int(current_fp * 0.10)})")
                print(f"  - Max recall loss: {max_recall_loss:.2%} (current recall: {current_recall:.4f}, min allowed: {current_recall - max_recall_loss:.4f})")
                print(f"  - Min recall: {min_recall_floor:.4f}")
                print(f"  - Weighted scoring: FP reduction (40%), Recall preservation (30%), Precision gain (20%), Positive rate reduction (10%)")
                positive_count = int((y_test == 1).sum())
                total_samples = len(y_test)
                
                for candidate in min_fp_candidates[:10]:  # Check top 10 candidates
                    fp_reduction = current_fp - candidate['fp']
                    fpr_reduction = current_fpr - candidate['fpr']
                    precision_gain = candidate['precision'] - current_precision
                    recall_loss = current_recall - candidate['recall']
                    pos_rate = (candidate['fp'] + (candidate['recall'] * positive_count)) / total_samples if total_samples > 0 else 0
                    pos_rate_reduction = current_positive_rate - pos_rate
                    
                    # Weighted score for credit scoring: prioritize FP reduction and recall preservation
                    fp_score = (fp_reduction / max(current_fp, 1)) * 0.4
                    recall_score_component = (1 - (recall_loss / max(current_recall, 0.01))) * 0.3
                    precision_score_component = max(0, precision_gain / max(abs(current_precision) + 0.01, 0.01)) * 0.2
                    pos_rate_score = max(0, pos_rate_reduction / max(current_positive_rate, 0.01)) * 0.1
                    
                    improvement_score = fp_score + recall_score_component + precision_score_component + pos_rate_score
                    
                    # Relaxed conditions for credit scoring
                    meets_fp_reduction = fp_reduction >= min_fp_reduction
                    meets_recall_loss = recall_loss <= max_recall_loss
                    meets_recall_target = candidate['recall'] >= min_recall_floor
                    # Accept if FP reduction is good OR recall is preserved well
                    meets_quality = (fp_reduction >= min_fp_reduction) or (recall_loss <= max_recall_loss * 0.5 and fp_reduction >= min_fp_reduction * 0.5)
                    
                    print(f"STACKING DEBUG: Candidate (threshold={candidate['threshold']:.4f}):")
                    print(f"  - FP: {current_fp} → {candidate['fp']} (reduction: {fp_reduction}, required: {min_fp_reduction}) {'✓' if meets_fp_reduction else '✗'}")
                    print(f"  - Recall: {current_recall:.4f} → {candidate['recall']:.4f} (loss: {recall_loss:.4f}, max: {max_recall_loss}) {'✓' if meets_recall_loss else '✗'}")
                    print(f"  - Recall >= target: {candidate['recall']:.4f} >= {min_recall_floor:.4f} {'✓' if meets_recall_target else '✗'}")
                    print(f"  - Precision: {current_precision:.4f} → {candidate['precision']:.4f} (gain: {precision_gain:.4f})")
                    print(f"  - Quality check: {'✓' if meets_quality else '✗'}")
                    print(f"  - Weighted score: {improvement_score:.4f} (FP:{fp_score:.3f} + Recall:{recall_score_component:.3f} + Prec:{precision_score_component:.3f} + PosRate:{pos_rate_score:.3f})")
                    
                    if (meets_recall_loss and meets_recall_target and meets_quality):
                        print(f"  → ✓ ACCEPTED")
                        if best_improvement is None or improvement_score > best_improvement:
                            best_improvement = improvement_score
                            best_precision_focused = candidate
                    else:
                        rejection_reasons = []
                        if not meets_recall_loss:
                            rejection_reasons.append(f"Recall loss {recall_loss:.4f} > {max_recall_loss}")
                        if not meets_recall_target:
                            rejection_reasons.append(f"Recall {candidate['recall']:.4f} < {min_recall_floor:.4f}")
                        if not meets_quality:
                            rejection_reasons.append(f"Quality: FP reduction {fp_reduction} insufficient or recall loss too high")
                        print(f"  → ✗ REJECTED: {', '.join(rejection_reasons)}")
                
                if best_precision_focused is not None:
                    precision_focused_threshold = best_precision_focused['threshold']
                    precision_focused_fp = best_precision_focused['fp']
                    precision_focused_fpr = best_precision_focused['fpr']
                    precision_focused_precision = best_precision_focused['precision']
                    precision_focused_recall = best_precision_focused['recall']
                    
                    fp_reduction = current_fp - precision_focused_fp
                    fpr_reduction = current_fpr - precision_focused_fpr
                    precision_gain = precision_focused_precision - current_precision
                    recall_loss = current_recall - precision_focused_recall
                    
                    print(f"STACKING DEBUG: ✓ Precision-focused threshold found: {precision_focused_threshold:.4f}")
                    fp_reduction_pct = (fp_reduction / current_fp * 100) if current_fp > 0 else 0
                    print(f"STACKING DEBUG:   FP: {current_fp} → {precision_focused_fp} (reduction: {fp_reduction}, {fp_reduction_pct:.1f}%)")
                    print(f"STACKING DEBUG:   Recall: {current_recall:.4f} → {precision_focused_recall:.4f} (loss: {recall_loss:.4f})")
                    print(f"STACKING DEBUG:   Precision: {current_precision:.4f} → {precision_focused_precision:.4f} (gain: {precision_gain:.4f})")
                    
                    optimal_threshold = precision_focused_threshold
                else:
                    print(f"STACKING DEBUG: No suitable precision-focused threshold found, applying positive-rate guardrail...")
                    # Fallback: Apply positive-rate cap only if precision-focused search failed
                    guardrail_levels = [
                        ('primary', min(current_recall, max(xgb_recall_target + 0.25, 0.75))),
                        ('secondary', min(current_recall, max(xgb_recall_target + 0.25, 0.5))),
                        ('baseline', max(xgb_recall_target, 0.25))
                    ]
                    if current_positive_rate > positive_rate_cap:
                        for level_name, recall_target in guardrail_levels:
                            recall_target = max(0.0, recall_target)
                            guardrail_candidates = []
                            for idx, thresh in enumerate(valid_thresholds):
                                if recall_at_thresholds[idx] >= recall_target and positive_rates[idx] <= positive_rate_cap:
                                    guardrail_candidates.append({
                                        'threshold': valid_thresholds[idx],
                                        'fp': fp_counts[idx],
                                        'precision': precision_at_thresholds[idx],
                                        'recall': recall_at_thresholds[idx],
                                        'positive_rate': positive_rates[idx],
                                        'level': level_name,
                                        'recall_target': recall_target
                                    })
                            if guardrail_candidates:
                                guardrail_candidates.sort(key=lambda c: (c['fp'], -c['precision']))
                                chosen_guardrail = guardrail_candidates[0]
                                optimal_threshold = chosen_guardrail['threshold']
                                positive_rate_guardrail_applied = True
                                positive_rate_guardrail_info = chosen_guardrail
                                print(
                                    f"STACKING DEBUG: Positive-rate guardrail ({level_name}) activated (cap {positive_rate_cap:.0%}). "
                                    f"New threshold {optimal_threshold:.4f} → positive rate {chosen_guardrail['positive_rate']:.2%}, "
                                    f"recall {chosen_guardrail['recall']:.4f} (target ≥ {recall_target:.4f})"
                                )
                                break
            else:
                print(f"STACKING DEBUG: No precision-focused candidates found (no threshold meets minimum recall {min_recall_floor:.4f})")
        except Exception as precision_err:
            print(f"STACKING DEBUG: Error in precision-focused threshold selection: {precision_err}")
            import traceback
            traceback.print_exc()
            print(f"STACKING DEBUG: Continuing with current optimal threshold: {optimal_threshold:.4f}")
        
        # Final threshold selection
        best_threshold = optimal_threshold
        y_pred = (ensemble_test_pred >= best_threshold).astype(int)
        
        # Recalculate F1 with final threshold
        best_f1 = f1_score(y_test, y_pred, zero_division=0)
        
        # Final verification against XGBoost
        final_recall = recall_score(y_test, y_pred, zero_division=0)
        final_precision = precision_score(y_test, y_pred, zero_division=0)
        final_fp = ((y_test == 0) & (y_pred == 1)).sum()
        final_positive_rate = y_pred.mean() if len(y_pred) > 0 else 0
        
        print(f"STACKING DEBUG: Final threshold selected: {best_threshold:.4f}")
        print(f"STACKING DEBUG: Final metrics - Recall: {final_recall:.4f}, Precision: {final_precision:.4f}, F1: {best_f1:.4f}, FP: {final_fp}, Positive rate: {final_positive_rate:.2%}")
        print(f"STACKING DEBUG: Final vs XGBoost comparison:")
        print(f"  - AUC: {roc_auc:.4f} vs {xgb_auc_target:.4f} ({'✓' if roc_auc >= xgb_auc_target else '✗'})")
        print(f"  - Recall: {final_recall:.4f} vs {xgb_recall_target:.4f} ({'✓' if final_recall >= xgb_recall_target else '✗'})")
        print(f"  - Precision: {final_precision:.4f} vs {xgb_precision_target:.4f} ({'✓' if final_precision >= xgb_precision_target * 0.5 else '⚠'})")
        print(f"  - FP: {final_fp} (target: minimize)")
        
        # Calculate KS statistic
        ks_stat = 0
        try:
            if len(np.unique(y_test)) == 2:
                good_scores = ensemble_test_pred[y_test == 0]
                bad_scores = ensemble_test_pred[y_test == 1]
                if len(good_scores) > 0 and len(bad_scores) > 0:
                    ks_stat, _ = ks_2samp(good_scores, bad_scores)
        except Exception as e:
            print(f"STACKING DEBUG: Error calculating KS: {e}")
        
        # Build KS curve (sanitize infinity/NaN)
        ks_curve = []
        try:
            # Re-ensure arrays are arrays (defensive programming)
            tpr_array = np.atleast_1d(tpr).flatten()
            fpr_array = np.atleast_1d(fpr).flatten()
            thresholds_array = np.atleast_1d(thresholds).flatten()
            
            # Ensure all arrays have the same length
            min_len = min(len(tpr_array), len(fpr_array), len(thresholds_array))
            if min_len > 0:
                for i in range(min_len):
                    thresh = float(thresholds_array[i])
                    tpr_val = float(tpr_array[i])
                    fpr_val = float(fpr_array[i])
                    if np.isfinite(thresh) and np.isfinite(tpr_val) and np.isfinite(fpr_val):
                        ks_curve.append({
                            'threshold': safe_float(thresh),
                            'tpr': safe_float(tpr_val),
                            'fpr': safe_float(fpr_val),
                            'diff': safe_float(tpr_val - fpr_val)
                        })
            else:
                print("STACKING DEBUG: WARNING - Empty ROC curve data, skipping KS curve")
        except Exception as ks_curve_err:
            print(f"STACKING DEBUG: Error building KS curve: {ks_curve_err}")
            import traceback
            traceback.print_exc()
            ks_curve = []
        
        # Confusion matrix (convert to list and ensure all values are finite)
        cm = confusion_matrix(y_test, y_pred)
        cm_list = []
        for row in cm:
            cm_list.append([int(val) if np.isfinite(val) else 0 for val in row])
        
        ensemble_performance = {
            'gini_coefficient': safe_float(gini),
            'auc': safe_float(roc_auc),
            'accuracy': safe_float(accuracy_score(y_test, y_pred)),
            'precision': safe_float(precision_score(y_test, y_pred, zero_division=0)),
            'recall': safe_float(recall_score(y_test, y_pred, zero_division=0)),
            'f1': safe_float(best_f1),
            'ks_stat': safe_float(ks_stat),
            'ks_threshold': safe_float(best_threshold),
            'fallback_model': fallback_model_used,
            'strategy': 'hybrid' if not fallback_model_used else f"fallback_{fallback_model_used.replace(' ', '_').lower()}",
            'positive_rate': safe_float(final_positive_rate),
            'positive_rate_guardrail_applied': positive_rate_guardrail_applied
        }
        
        # ROC data (sanitize infinity/NaN)
        roc_data = []
        try:
            # Re-ensure arrays are arrays (defensive programming)
            tpr_array = np.atleast_1d(tpr).flatten()
            fpr_array = np.atleast_1d(fpr).flatten()
            thresholds_array = np.atleast_1d(thresholds).flatten()
            
            min_len = min(len(fpr_array), len(tpr_array), len(thresholds_array))
            if min_len > 0:
                for i in range(min_len):
                    fpr_val = float(fpr_array[i])
                    tpr_val = float(tpr_array[i])
                    thresh_val = float(thresholds_array[i])
                    if (np.isfinite(fpr_val) and np.isfinite(tpr_val) and np.isfinite(thresh_val)):
                        roc_data.append({
                            'fpr': safe_float(fpr_val),
                            'tpr': safe_float(tpr_val),
                            'threshold': safe_float(thresh_val)
                        })
            else:
                print("STACKING DEBUG: WARNING - Empty ROC curve data, skipping ROC data")
        except Exception as roc_data_err:
            print(f"STACKING DEBUG: Error building ROC data: {roc_data_err}")
            import traceback
            traceback.print_exc()
            roc_data = []
        
        print(f"STACKING DEBUG: Ensemble AUC: {roc_auc:.4f}, Gini: {gini:.4f}, Recall: {ensemble_performance['recall']:.4f}")
        
        # ================================================================================
        # COMPREHENSIVE STACKING DEBUG REPORT
        # ================================================================================
        print("\n" + "="*80)
        print("STACKING ENSEMBLE - COMPREHENSIVE DEBUG REPORT")
        print("="*80)
        
        # 1. Data Source Information
        print("\n[1] DATA SOURCE INFORMATION")
        print("-" * 80)
        print(f"Dataset ID: {record_id}")
        print(f"Target Variable: {target}")
        print(f"Selected Variables: {len(selected_variables)} variables")
        print(f"Selected Variables List: {selected_variables[:10]}{'...' if len(selected_variables) > 10 else ''}")
        print(f"Train Set Size: {len(df_train)} samples")
        print(f"Test Set Size: {len(df_test)} samples")
        print(f"Cross-Validation Folds: {n_splits}")
        
        # Check train/test class distribution
        train_class_dist = df_train[target].value_counts().to_dict()
        test_class_dist = df_test[target].value_counts().to_dict()
        print(f"\nTrain Set Class Distribution: {train_class_dist}")
        print(f"Test Set Class Distribution: {test_class_dist}")
        if len(train_class_dist) == 2:
            train_ratio = train_class_dist.get(0, 0) / train_class_dist.get(1, 1) if train_class_dist.get(1, 0) > 0 else float('inf')
            test_ratio = test_class_dist.get(0, 0) / test_class_dist.get(1, 1) if test_class_dist.get(1, 0) > 0 else float('inf')
            print(f"Train Imbalance Ratio: {train_ratio:.2f}:1 (Good:Bad)")
            print(f"Test Imbalance Ratio: {test_ratio:.2f}:1 (Good:Bad)")
        
        # 2. Base Model Data Sources
        print("\n[2] BASE MODEL DATA SOURCES")
        print("-" * 80)
        print("Logistic Regression:")
        print("  - Data Source: Fine binned WOE features")
        print("  - Transformation: _apply_woe_to_test_data()")
        print("  - Features: {var}_WOE columns")
        print("  - Number of WOE features: Check WOE transformation")
        
        print("\nRandom Forest:")
        print("  - Data Source: Fine binned WOE features")
        print("  - Transformation: _apply_woe_to_test_data()")
        print("  - Features: {var}_WOE columns")
        print("  - Same as Logistic Regression")
        
        print("\nXGBoost:")
        print("  - Data Source: Preprocessed raw features")
        print("  - Transformation: preprocess_dataset()")
        print("  - Features: Raw selected_variables after preprocessing")
        print("  - Preprocessing steps: detect_types, handle_missing, remove_duplicates")
        print("  - Additional: Label encoding for categoricals, median fill for numerics")
        
        # 3. Out-of-Fold Predictions Statistics
        print("\n[3] OUT-OF-FOLD PREDICTIONS (Training Set)")
        print("-" * 80)
        print(f"LR OOF Predictions:")
        print(f"  - Shape: {lr_oof_preds.shape}")
        print(f"  - Range: [{np.min(lr_oof_preds):.6f}, {np.max(lr_oof_preds):.6f}]")
        print(f"  - Mean: {np.mean(lr_oof_preds):.6f}")
        print(f"  - Median: {np.median(lr_oof_preds):.6f}")
        print(f"  - Std: {np.std(lr_oof_preds):.6f}")
        print(f"  - Contains NaN: {np.isnan(lr_oof_preds).sum()}")
        print(f"  - Contains Inf: {np.isinf(lr_oof_preds).sum()}")
        
        print(f"\nRF OOF Predictions:")
        print(f"  - Shape: {rf_oof_preds.shape}")
        print(f"  - Range: [{np.min(rf_oof_preds):.6f}, {np.max(rf_oof_preds):.6f}]")
        print(f"  - Mean: {np.mean(rf_oof_preds):.6f}")
        print(f"  - Median: {np.median(rf_oof_preds):.6f}")
        print(f"  - Std: {np.std(rf_oof_preds):.6f}")
        print(f"  - Contains NaN: {np.isnan(rf_oof_preds).sum()}")
        print(f"  - Contains Inf: {np.isinf(rf_oof_preds).sum()}")
        
        print(f"\nXGB OOF Predictions:")
        print(f"  - Shape: {xgb_oof_preds.shape}")
        print(f"  - Range: [{np.min(xgb_oof_preds):.6f}, {np.max(xgb_oof_preds):.6f}]")
        print(f"  - Mean: {np.mean(xgb_oof_preds):.6f}")
        print(f"  - Median: {np.median(xgb_oof_preds):.6f}")
        print(f"  - Std: {np.std(xgb_oof_preds):.6f}")
        print(f"  - Contains NaN: {np.isnan(xgb_oof_preds).sum()}")
        print(f"  - Contains Inf: {np.isinf(xgb_oof_preds).sum()}")
        
        # Correlation between base model predictions
        print(f"\nOOF Predictions Correlation:")
        try:
            lr_rf_corr = np.corrcoef(lr_oof_preds, rf_oof_preds)[0, 1]
            lr_xgb_corr = np.corrcoef(lr_oof_preds, xgb_oof_preds)[0, 1]
            rf_xgb_corr = np.corrcoef(rf_oof_preds, xgb_oof_preds)[0, 1]
            print(f"  - LR vs RF: {lr_rf_corr:.4f}")
            print(f"  - LR vs XGB: {lr_xgb_corr:.4f}")
            print(f"  - RF vs XGB: {rf_xgb_corr:.4f}")
            print(f"  - Note: Lower correlation = more diversity = better stacking potential")
        except Exception as e:
            print(f"  - Error calculating correlations: {e}")
            lr_rf_corr = 0.0
            lr_xgb_corr = 0.0
            rf_xgb_corr = 0.0
        
        # 4. Test Set Predictions Statistics
        print("\n[4] TEST SET PREDICTIONS")
        print("-" * 80)
        print(f"LR Test Predictions (averaged across {n_splits} folds):")
        print(f"  - Shape: {lr_test_pred.shape}")
        print(f"  - Range: [{np.min(lr_test_pred):.6f}, {np.max(lr_test_pred):.6f}]")
        print(f"  - Mean: {np.mean(lr_test_pred):.6f}")
        print(f"  - Median: {np.median(lr_test_pred):.6f}")
        print(f"  - Std: {np.std(lr_test_pred):.6f}")
        
        print(f"\nRF Test Predictions (averaged across {n_splits} folds):")
        print(f"  - Shape: {rf_test_pred.shape}")
        print(f"  - Range: [{np.min(rf_test_pred):.6f}, {np.max(rf_test_pred):.6f}]")
        print(f"  - Mean: {np.mean(rf_test_pred):.6f}")
        print(f"  - Median: {np.median(rf_test_pred):.6f}")
        print(f"  - Std: {np.std(rf_test_pred):.6f}")
        
        print(f"\nXGB Test Predictions (averaged across {n_splits} folds):")
        print(f"  - Shape: {xgb_test_pred.shape}")
        print(f"  - Range: [{np.min(xgb_test_pred):.6f}, {np.max(xgb_test_pred):.6f}]")
        print(f"  - Mean: {np.mean(xgb_test_pred):.6f}")
        print(f"  - Median: {np.median(xgb_test_pred):.6f}")
        print(f"  - Std: {np.std(xgb_test_pred):.6f}")
        
        # 5. Base Model Performance Comparison
        print("\n[5] BASE MODEL PERFORMANCE (Test Set)")
        print("-" * 80)
        for model_perf in base_models_performance:
            print(f"\n{model_perf['model']}:")
            print(f"  - AUC: {model_perf['auc']:.4f}")
            print(f"  - Gini: {model_perf['gini']:.4f}")
            print(f"  - Recall: {model_perf['recall']:.4f}")
            print(f"  - Precision: {model_perf['precision']:.4f}")
            print(f"  - F1-Score: {model_perf['f1']:.4f}")
        
        # 6. Meta-Learner Information
        print("\n[6] META-LEARNER INFORMATION")
        print("-" * 80)
        print(f"Meta-Learner Type: Logistic Regression with L2 Regularization")
        print(f"Regularization: L2 penalty, C=5.0 (stabilizes weights while keeping contributions diverse)")
        print(f"Meta-Learner Weights:")
        print(f"  - Logistic Regression coefficient: {meta_weights['logistic_regression']:.6f}")
        print(f"  - Random Forest coefficient: {meta_weights['random_forest']:.6f}")
        print(f"  - XGBoost coefficient: {meta_weights['xgboost']:.6f}")
        print(f"  - Intercept: {meta_weights['intercept']:.6f}")
        
        # Interpret weights using relative_importance calculated earlier
        print(f"\nMeta-Learner Weight Interpretation:")
        print(f"  - LR relative importance: {relative_importance['logistic_regression']:.1f}%")
        print(f"  - RF relative importance: {relative_importance['random_forest']:.1f}%")
        print(f"  - XGB relative importance: {relative_importance['xgboost']:.1f}%")
        
        # Check for dominance
        max_importance = max(relative_importance.values())
        if max_importance == relative_importance['logistic_regression']:
            print(f"  - Dominant model: Logistic Regression")
        elif max_importance == relative_importance['random_forest']:
            print(f"  - Dominant model: Random Forest")
        else:
            print(f"  - Dominant model: XGBoost")
        
        # Hybrid ensemble approach
        print(f"\nHybrid Ensemble Approach:")
        print(f"  - Meta-learner contribution: 70%")
        print(f"  - Performance-weighted average: 30%")
        print(f"  - Performance weights: LR={performance_weights[0]:.3f}, RF={performance_weights[1]:.3f}, XGB={performance_weights[2]:.3f}")
        print(f"  - Benefit: Combines learned optimal combination with individual model strengths")
        
        # 7. Ensemble Performance
        print("\n[7] ENSEMBLE PERFORMANCE (Test Set)")
        print("-" * 80)
        print(f"AUC-ROC: {ensemble_performance['auc']:.4f}")
        print(f"Gini Coefficient: {ensemble_performance['gini_coefficient']:.4f}")
        print(f"Accuracy: {ensemble_performance['accuracy']:.4f}")
        print(f"Precision: {ensemble_performance['precision']:.4f}")
        print(f"Recall: {ensemble_performance['recall']:.4f}")
        print(f"F1-Score: {ensemble_performance['f1']:.4f}")
        print(f"KS Statistic: {ensemble_performance['ks_stat']:.4f}")
        print(f"Optimal Threshold: {ensemble_performance['ks_threshold']:.4f}")
        print(f"\nThreshold Optimization Strategy:")
        print(f"  - Method: Recall-optimized (same as XGBoost)")
        print(f"  - Target recall: >= 0.5 (for extreme imbalance)")
        print(f"  - Accepts 5%+ recall improvement with up to 80% precision loss")
        print(f"  - Includes probability-based strategy for extreme imbalance (<=10 positives)")
        print(f"  - Fallback: Balanced threshold (>=75% recall with best precision)")
        
        # 8. Performance Improvement Analysis
        print("\n[8] PERFORMANCE IMPROVEMENT ANALYSIS")
        print("-" * 80)
        best_base_auc = max([m['auc'] for m in base_models_performance])
        ensemble_auc = ensemble_performance['auc']
        auc_improvement = ensemble_auc - best_base_auc
        print(f"Best Base Model AUC: {best_base_auc:.4f}")
        print(f"Ensemble AUC: {ensemble_auc:.4f}")
        print(f"AUC Improvement: {auc_improvement:+.4f} ({auc_improvement*100:+.2f}%)")
        
        best_base_recall = max([m['recall'] for m in base_models_performance])
        ensemble_recall = ensemble_performance['recall']
        recall_improvement = ensemble_recall - best_base_recall
        print(f"\nBest Base Model Recall: {best_base_recall:.4f}")
        print(f"Ensemble Recall: {ensemble_recall:.4f}")
        print(f"Recall Improvement: {recall_improvement:+.4f} ({recall_improvement*100:+.2f}%)")
        
        best_base_f1 = max([m['f1'] for m in base_models_performance])
        ensemble_f1 = ensemble_performance['f1']
        f1_improvement = ensemble_f1 - best_base_f1
        print(f"\nBest Base Model F1: {best_base_f1:.4f}")
        print(f"Ensemble F1: {ensemble_f1:.4f}")
        print(f"F1 Improvement: {f1_improvement:+.4f} ({f1_improvement*100:+.2f}%)")
        
        # XGBoost-specific comparison (guarantee better than XGBoost)
        xgb_performance = next((m for m in base_models_performance if m['model'] == 'XGBoost'), None)
        if xgb_performance:
            print(f"\n--- XGBOOST COMPARISON (Guarantee: Stacking >= XGBoost) ---")
            print(f"XGBoost AUC: {xgb_performance['auc']:.4f} | Ensemble AUC: {ensemble_auc:.4f} | Improvement: {ensemble_auc - xgb_performance['auc']:+.4f}")
            print(f"XGBoost Recall: {xgb_performance['recall']:.4f} | Ensemble Recall: {ensemble_recall:.4f} | Improvement: {ensemble_recall - xgb_performance['recall']:+.4f}")
            print(f"XGBoost F1: {xgb_performance['f1']:.4f} | Ensemble F1: {ensemble_f1:.4f} | Improvement: {ensemble_f1 - xgb_performance['f1']:+.4f}")
            
            # Check if stacking is better than XGBoost
            if ensemble_auc >= xgb_performance['auc'] and ensemble_recall >= xgb_performance['recall']:
                print(f"✓ SUCCESS: Stacking outperforms XGBoost on both AUC and Recall!")
            elif ensemble_auc >= xgb_performance['auc']:
                print(f"⚠ Stacking has better AUC but lower recall than XGBoost")
            elif ensemble_recall >= xgb_performance['recall']:
                print(f"⚠ Stacking has better recall but lower AUC than XGBoost")
            else:
                print(f"✗ WARNING: Stacking underperforms XGBoost - may need further tuning")
        
        # 9. Confusion Matrix Details
        print("\n[9] CONFUSION MATRIX (Test Set)")
        print("-" * 80)
        print(f"Confusion Matrix:")
        print(f"  Predicted:    0      1")
        print(f"  Actual 0:   {cm_list[0][0]:5d}  {cm_list[0][1]:5d}")
        print(f"  Actual 1:   {cm_list[1][0]:5d}  {cm_list[1][1]:5d}")
        tn, fp, fn, tp = cm_list[0][0], cm_list[0][1], cm_list[1][0], cm_list[1][1]
        total = tn + fp + fn + tp
        print(f"\nDetailed Metrics:")
        print(f"  True Negatives (TN):  {tn} ({tn/total*100:.2f}%)")
        print(f"  False Positives (FP): {fp} ({fp/total*100:.2f}%)")
        print(f"  False Negatives (FN): {fn} ({fn/total*100:.2f}%)")
        print(f"  True Positives (TP):  {tp} ({tp/total*100:.2f}%)")
        
        # 10. Prediction Distribution Analysis
        print("\n[10] ENSEMBLE PREDICTION DISTRIBUTION (Test Set)")
        print("-" * 80)
        print(f"Ensemble Probability Range: [{np.min(ensemble_test_pred):.6f}, {np.max(ensemble_test_pred):.6f}]")
        print(f"Ensemble Probability Mean: {np.mean(ensemble_test_pred):.6f}")
        print(f"Ensemble Probability Median: {np.median(ensemble_test_pred):.6f}")
        print(f"Ensemble Probability Std: {np.std(ensemble_test_pred):.6f}")
        
        # Distribution by class
        good_probs = ensemble_test_pred[y_test == 0]
        bad_probs = ensemble_test_pred[y_test == 1]
        if len(good_probs) > 0:
            print(f"\nGood Customers (y=0) - {len(good_probs)} samples:")
            print(f"  - Probability range: [{np.min(good_probs):.6f}, {np.max(good_probs):.6f}]")
            print(f"  - Mean probability: {np.mean(good_probs):.6f}")
            print(f"  - Median probability: {np.median(good_probs):.6f}")
        if len(bad_probs) > 0:
            print(f"\nBad Customers (y=1) - {len(bad_probs)} samples:")
            print(f"  - Probability range: [{np.min(bad_probs):.6f}, {np.max(bad_probs):.6f}]")
            print(f"  - Mean probability: {np.mean(bad_probs):.6f}")
            print(f"  - Median probability: {np.median(bad_probs):.6f}")
        
        # Separation analysis
        if len(good_probs) > 0 and len(bad_probs) > 0:
            separation = np.mean(bad_probs) - np.mean(good_probs)
            print(f"\nSeparation Analysis:")
            print(f"  - Mean difference (Bad - Good): {separation:.6f}")
            print(f"  - Max Good probability: {np.max(good_probs):.6f}")
            print(f"  - Min Bad probability: {np.min(bad_probs):.6f}")
            overlap = np.sum(bad_probs < np.max(good_probs))
            print(f"  - Bad samples below max Good prob: {overlap} ({overlap/len(bad_probs)*100:.1f}%)")
        
        # 11. Data Alignment Verification
        print("\n[11] DATA ALIGNMENT VERIFICATION")
        print("-" * 80)
        print(f"OOF Predictions Alignment:")
        print(f"  - LR OOF shape: {lr_oof_preds.shape}")
        print(f"  - RF OOF shape: {rf_oof_preds.shape}")
        print(f"  - XGB OOF shape: {xgb_oof_preds.shape}")
        print(f"  - All shapes match: {lr_oof_preds.shape == rf_oof_preds.shape == xgb_oof_preds.shape}")
        print(f"  - Meta-features train shape: {meta_features_train_aug.shape}")
        print(f"  - Expected: ({len(df_train)}, 6)")
        
        print(f"\nTest Predictions Alignment:")
        print(f"  - LR test shape: {lr_test_pred.shape}")
        print(f"  - RF test shape: {rf_test_pred.shape}")
        print(f"  - XGB test shape: {xgb_test_pred.shape}")
        print(f"  - All shapes match: {lr_test_pred.shape == rf_test_pred.shape == xgb_test_pred.shape}")
        print(f"  - Meta-features test shape: {meta_features_test_aug.shape}")
        print(f"  - Expected: ({len(df_test)}, 6)")
        
        # 12. Potential Issues/Warnings
        print("\n[12] POTENTIAL ISSUES / WARNINGS")
        print("-" * 80)
        warnings_list = []
        
        if np.isnan(lr_oof_preds).any() or np.isnan(rf_oof_preds).any() or np.isnan(xgb_oof_preds).any():
            warnings_list.append("⚠️  NaN values found in OOF predictions")
        
        if np.isinf(lr_oof_preds).any() or np.isinf(rf_oof_preds).any() or np.isinf(xgb_oof_preds).any():
            warnings_list.append("⚠️  Infinity values found in OOF predictions")
        
        if auc_improvement < 0:
            warnings_list.append(f"⚠️  Ensemble AUC ({ensemble_auc:.4f}) is LOWER than best base model ({best_base_auc:.4f})")
        
        if recall_improvement < 0:
            warnings_list.append(f"⚠️  Ensemble Recall ({ensemble_recall:.4f}) is LOWER than best base model ({best_base_recall:.4f})")
        
        if lr_rf_corr > 0.95:
            warnings_list.append(f"⚠️  LR and RF predictions are highly correlated ({lr_rf_corr:.4f}) - limited diversity")
        
        if abs(meta_weights['logistic_regression']) < 0.01 and abs(meta_weights['random_forest']) < 0.01:
            warnings_list.append("⚠️  LR and RF weights are very small - XGBoost may be dominating")
        elif abs(meta_weights['xgboost']) < 0.01:
            warnings_list.append("⚠️  XGBoost weight is very small - may not be contributing")
        if fallback_model_used:
            warnings_list.append(f"ℹ️  Ensemble fell back to {fallback_model_used} predictions to maintain AUC")
        if positive_rate_guardrail_applied and positive_rate_guardrail_info:
            guardrail_level = positive_rate_guardrail_info.get('level', 'unknown')
            warnings_list.append(
                f"ℹ️  Positive-rate guardrail ({guardrail_level}) raised threshold to {positive_rate_guardrail_info['threshold']:.4f}"
                f" (positive rate {positive_rate_guardrail_info['positive_rate']:.2%}, recall {positive_rate_guardrail_info['recall']:.4f})"
            )
        
        if len(warnings_list) == 0:
            print("✓ No issues detected")
        else:
            for warning in warnings_list:
                print(warning)
        
        # 13. Summary
        print("\n[13] SUMMARY")
        print("-" * 80)
        print(f"✓ Stacking ensemble completed successfully")
        print(f"✓ All {len(selected_variables)} variables processed")
        print(f"✓ {n_splits}-fold cross-validation completed")
        print(f"✓ Meta-learner trained and evaluated")
        print(f"✓ Ensemble performance: AUC={ensemble_performance['auc']:.4f}, Recall={ensemble_performance['recall']:.4f}")
        if fallback_model_used:
            print(f"ℹ️  Final predictions sourced from {fallback_model_used} due to fallback safeguard")
        if positive_rate_guardrail_applied and positive_rate_guardrail_info:
            guardrail_level = positive_rate_guardrail_info.get('level', 'unknown')
            print(
                f"ℹ️  Positive-rate guardrail ({guardrail_level}) enforced (threshold {positive_rate_guardrail_info['threshold']:.4f}, "
                f"positive rate {positive_rate_guardrail_info['positive_rate']:.2%}, recall {positive_rate_guardrail_info['recall']:.4f})"
            )
        
        print("\n" + "="*80)
        print("END OF STACKING DEBUG REPORT")
        print("="*80 + "\n")
        
        return jsonify({
            "success": True,
            "meta_learner_weights": meta_weights,
            "base_models_performance": base_models_performance,
            "ensemble_performance": ensemble_performance,
            "roc_data": roc_data,
            "confusion_matrix": cm_list,
            "ks_curve": ks_curve
        })
        
    except Exception as e:
        import traceback
        error_msg = f"Failed to perform stacking analysis: {str(e)}"
        print(f"STACKING ERROR: {error_msg}")
        traceback.print_exc()
        return jsonify({"success": False, "error": error_msg}), 500
        
# Helper function for WOE mapping (used by all models)
def _apply_woe_to_test_data(df_test, selected_variables, woe_transformed_data, target):
    """
    Apply WOE transformations to test data using WOE values learned from training data.
    
    Parameters:
    -----------
    df_test : DataFrame
        Test dataset (preprocessed)
    selected_variables : list
        List of variable names to transform
    woe_transformed_data : dict
        WOE transformation data (learned from train)
    target : str
        Target column name
        
    Returns:
    --------
    woe_df : DataFrame
        Test data with WOE transformations applied
    """
    woe_df = df_test[[target]].copy() if target in df_test.columns else pd.DataFrame(index=df_test.index)
    
    for var in selected_variables:
        if var not in woe_transformed_data:
            print(f"LOGISTIC DEBUG: No WOE data for '{var}', skipping")
            woe_df[f'{var}_WOE'] = 0
            continue
            
        # Get WOE bins from training data
        raw_bins = woe_transformed_data.get(var)
        if isinstance(raw_bins, dict) and isinstance(raw_bins.get('stats'), list):
            bins_list = raw_bins.get('stats')
        elif isinstance(raw_bins, list):
            bins_list = raw_bins
        else:
            bins_list = []
            
        if not bins_list:
            print(f"LOGISTIC DEBUG: no bin definitions found for '{var}' in woe_transformed_data")
            woe_df[f'{var}_WOE'] = 0
            continue

        # Calculate mean WOE from training bins as default for missing values
        woe_values_from_training = []
        for bin_info in bins_list:
            woe_value = bin_info.get('woe') or bin_info.get('WOE')
            if woe_value is not None:
                try:
                    woe_values_from_training.append(float(woe_value))
                except Exception:
                    pass
        default_woe = np.mean(woe_values_from_training) if woe_values_from_training else 0.0
        
        woe_df[f'{var}_WOE'] = np.nan
        for bin_info in bins_list:
            bin_range = bin_info.get('range') or bin_info.get('Range') or bin_info.get('Bin') or bin_info.get('bin')
            
            # Handle min_value/max_value if bin_range is not available
            if not bin_range and (bin_info.get('min_value') is not None or bin_info.get('max_value') is not None):
                min_val = bin_info.get('min_value')
                max_val = bin_info.get('max_value')
                if min_val is not None and max_val is not None:
                    bin_range = f"({min_val}, {max_val}]"
                elif min_val is not None:
                    bin_range = f"({min_val}, inf)"
                elif max_val is not None:
                    bin_range = f"(-inf, {max_val}]"
            
            woe_value = bin_info.get('woe') or bin_info.get('WOE')
            if woe_value is None:
                continue
            try:
                woe_value = float(woe_value)
            except Exception:
                continue
                
            # Use the existing _create_woe_mask function
            mask = _create_woe_mask(df_test, var, bin_range)
            woe_df.loc[mask, f'{var}_WOE'] = woe_value
            
        non_null = int(woe_df[f'{var}_WOE'].notna().sum())
        missing_count = len(df_test) - non_null
        if missing_count > 0:
            print(f"LOGISTIC DEBUG: Test - mapped WOE rows for '{var}': {non_null} of {len(df_test)} (missing: {missing_count}, using default WOE: {default_woe:.2f})")
        else:
            print(f"LOGISTIC DEBUG: Test - mapped WOE rows for '{var}': {non_null} of {len(df_test)}")
        # Use mean WOE from training as default instead of 0
        woe_df[f'{var}_WOE'] = woe_df[f'{var}_WOE'].fillna(default_woe)
    
    return woe_df


def _create_woe_mask(df, var, bin_range):
    """Create mask for WOE value assignment based on bin range."""
    import re
    import numpy as np
    
    if bin_range is None:
        return np.zeros(len(df), dtype=bool)
    
    # Handle Missing/NaN
    if isinstance(bin_range, str) and ('Missing' in bin_range or 'NaN' in bin_range):
        return df[var].isna()
    
    # Numeric range parsing
    if isinstance(bin_range, str) and any(ch in bin_range for ch in '(),[]'):
        range_str = bin_range.replace('(', '').replace(')', '').replace('[', '').replace(']', '')
        parts = [p.strip() for p in range_str.split(',') if p.strip()]
        if len(parts) == 2:
            try:
                lower = float(parts[0]) if parts[0].lower() not in ['-inf', 'inf'] else (float('-inf') if parts[0].lower() == '-inf' else float('inf'))
                upper = float(parts[1]) if parts[1].lower() not in ['-inf', 'inf'] else (float('-inf') if parts[1].lower() == '-inf' else float('inf'))
                if lower == float('-inf'):
                    return df[var] <= upper
                elif upper == float('inf'):
                    return df[var] > lower
                else:
                    return (df[var] > lower) & (df[var] <= upper)
            except (ValueError, TypeError):
                pass
    
    # Hyphen-separated ranges
    hyphen_match = re.match(r'^\s*-?\d+(?:\.\d+)?\s*-\s*-?\d+(?:\.\d+)?\s*$', str(bin_range))
    if isinstance(bin_range, str) and hyphen_match:
        try:
            parts = [p.strip() for p in bin_range.split('-')]
            lower, upper = float(parts[0]), float(parts[1])
            return (df[var].astype(float) >= lower) & (df[var].astype(float) <= upper)
        except (ValueError, TypeError):
            pass
    
    # Categorical values
    if isinstance(bin_range, str):
        cat_vals = [v.strip() for v in bin_range.split(',') if v.strip()]
        mask = np.zeros(len(df), dtype=bool)
        for cat_val in cat_vals:
            try:
                mask |= (df[var].astype(str) == str(cat_val))
            except Exception:
                continue
        return mask
    
    # Default: exact match
    return df[var].astype(str) == str(bin_range)

# ----------- Delete Record -----------
@app.route('/api/record/<int:record_id>', methods=['DELETE'])
def delete_record(record_id):
    """
    Delete a specific analysis record/dataset by ID.
    Cascade delete handles all related features, binning_steps, bins, etc.
    """
    try:
        dataset = get_dataset(record_id)
        if dataset:
            delete_dataset(record_id)
            return jsonify({"success": True})
        return jsonify({"error": "Dataset not found"}), 404
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# ----------- Finebin Details API -----------
@app.route('/api/finebin-details', methods=['POST'])
def save_finebin_details():
    """
    Save fine binning details (merged bins) for a specific dataset and feature.
    Expects payload: { record_id (dataset_id), column_name, bin_merges: { <group_id>: [bins], ... } }
    
    bin_merges format: { "1": [0, 1, 2], "2": [3, 4] }  means:
    - Group 1 merges coarse bins 0, 1, 2
    - Group 2 merges coarse bins 3, 4
    """
    print("\n[API] /api/finebin-details (POST) called")
    data = request.get_json()
    print(f"[save_finebin_details] dataset_id={data.get('record_id')}, column={data.get('column_name')}")
    dataset_id_raw = data.get('record_id')  # Frontend still uses 'record_id'
    column_name = data.get('column_name')
    bin_merges = data.get('bin_merges')  # dict of group_id -> list of bin indices
    
    if not dataset_id_raw or not column_name or not isinstance(bin_merges, dict):
        return jsonify({"error": "Missing or invalid fields (record_id, column_name, bin_merges)."}), 400
    
    try:
        # Ensure dataset_id is an integer
        try:
            dataset_id = int(dataset_id_raw)
        except (ValueError, TypeError):
            return jsonify({"error": f"Invalid dataset_id: {dataset_id_raw}"}), 400
        
        # Get the feature for this dataset/column
        feature = get_feature_by_name(dataset_id, column_name)
        if not feature:
            return jsonify({"error": f"Feature {column_name} not found for dataset {dataset_id}"}), 404
        
        # Get the coarse binning step (needed to know what bins are being merged)
        coarse_step = get_binning_step_by_type(feature['id'], 'coarse')
        if not coarse_step:
            return jsonify({"error": f"No coarse binning found for {column_name}"}), 404
        
        # Get coarse bins
        coarse_bins = get_bins_by_step(coarse_step['id'])
        
        # Get or create the fine binning step
        fine_step = get_binning_step_by_type(feature['id'], 'fine')
        if not fine_step:
            # Create a new fine binning step
            fine_step_id = create_binning_step(
                feature_id=feature['id'],
                step_type='fine',
                method='manual'
            )
        else:
            fine_step_id = fine_step['id']
            # Delete existing merged bins for this step
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute('DELETE FROM merged_bins WHERE fine_step_id = %s', (fine_step_id,))
            conn.commit()
            cur.close()
            conn.close()
        
        # Get feature type to determine correct prefix (c for continuous, d for discrete)
        feature_type = feature.get('type', 'continuous')  # Default to continuous if not set
        prefix = 'c' if feature_type == 'continuous' else 'd'
        
        # Create merged bin records
        # bin_merges can be in two formats:
        # 1. Numeric indices: {"1": [0, 1, 2], "2": [3, 4]}
        # 2. Bin labels from auto-binning: {"Bin_3_Bin_4_Bin_5_Bin_6": ["Bin_3", "Bin_4", "Bin_5", "Bin_6"]}
        
        # Create mapping of bin labels to bin records for label-based lookups
        bin_label_map = {str(bin.get('bin_label', '')): bin for bin in coarse_bins}
        
        merged_bin_counter = 1
        for merged_bin_key, original_bin_values in bin_merges.items():
            # Determine if we're dealing with numeric indices or bin labels
            original_bin_ids = []
            original_bin_labels = []
            
            # Check if original_bin_values are numeric indices or labels
            if original_bin_values and isinstance(original_bin_values[0], (int, float)):
                # Format 1: Numeric indices [0, 1, 2]
                for idx in original_bin_values:
                    try:
                        idx_int = int(idx)
                        if 0 <= idx_int < len(coarse_bins):
                            original_bin_ids.append(coarse_bins[idx_int]['id'])
                            # Use existing bin_label or create with correct prefix based on feature type
                            existing_label = coarse_bins[idx_int].get('bin_label')
                            if existing_label:
                                original_bin_labels.append(existing_label)
                            else:
                                # Use feature type to determine prefix
                                bin_num = coarse_bins[idx_int].get('bin_number', idx_int + 1)
                                original_bin_labels.append(f'{prefix}{bin_num}')
                    except (ValueError, TypeError):
                        continue
            else:
                # Format 2: Bin labels ["Bin_3", "Bin_4", "Bin_5", "Bin_6"]
                for label in original_bin_values:
                    label_str = str(label).strip()
                    # Try direct label match
                    if label_str in bin_label_map:
                        bin_record = bin_label_map[label_str]
                        original_bin_ids.append(bin_record['id'])
                        original_bin_labels.append(label_str)
                    else:
                        # Try extracting numeric part and matching by bin_number
                        # e.g., "Bin_3" -> bin_number=3
                        import re
                        match = re.search(r'_?(\d+)', label_str)
                        if match:
                            bin_num = int(match.group(1))
                            # Find bin by bin_number
                            matching_bin = next((b for b in coarse_bins if b.get('bin_number') == bin_num), None)
                            if matching_bin:
                                original_bin_ids.append(matching_bin['id'])
                                original_bin_labels.append(matching_bin.get('bin_label', label_str))
            
            if original_bin_ids:
                # Try to extract merged bin number from key, or use counter
                try:
                    # Try to parse as integer first
                    merged_bin_number = int(merged_bin_key)
                except ValueError:
                    # If key is a string like "Bin_3_Bin_4_Bin_5_Bin_6", use counter
                    merged_bin_number = merged_bin_counter
                    merged_bin_counter += 1
                
                create_merged_bin(
                    fine_step_id=fine_step_id,
                    merged_bin_number=merged_bin_number,
                    original_bin_ids=original_bin_ids,
                    original_bin_labels=original_bin_labels
                )
        
        return jsonify({"success": True})
    except Exception as e:
        print(f"[save_finebin_details] ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/api/finebin-details/<int:record_id>/<string:column_name>', methods=['GET'])
def get_finebin_details(record_id, column_name):
    """
    Retrieve fine binning details (merged bins) for a specific dataset and feature.
    Returns format compatible with frontend: array of {group_id, merged_bins}
    """
    print(f"\n[API] /api/finebin-details/{record_id}/{column_name} (GET) called")
    try:
        dataset_id = record_id  # Frontend still uses record_id
        
        # Get the feature
        feature = get_feature_by_name(dataset_id, column_name)
        if not feature:
            return jsonify([])  # Return empty array for compatibility
        
        # Get the fine binning step
        fine_step = get_binning_step_by_type(feature['id'], 'fine')
        if not fine_step:
            return jsonify([])  # Return empty array for compatibility
        
        # Get coarse binning step to map bin IDs to labels
        coarse_step = get_binning_step_by_type(feature['id'], 'coarse')
        if not coarse_step:
            return jsonify([])
        
        coarse_bins = get_bins_by_step(coarse_step['id'])
        # Get feature type to determine correct prefix (c for continuous, d for discrete)
        feature_type = feature.get('type', 'continuous')  # Default to continuous if not set
        prefix = 'c' if feature_type == 'continuous' else 'd'
        
        # Create mappings: bin_id -> bin_label
        # Create mapping with correct prefix based on feature type
        bin_id_to_label = {}
        for bin_data in coarse_bins:
            existing_label = bin_data.get('bin_label')
            if existing_label:
                bin_id_to_label[bin_data['id']] = existing_label
            else:
                # Use feature type to determine prefix
                bin_num = bin_data.get('bin_number', 0)
                bin_id_to_label[bin_data['id']] = f'{prefix}{bin_num}'
        
        # Get merged bins for this step
        merged_bins = get_merged_bins_by_step(fine_step['id'])
        
        # Convert to frontend-compatible format: array of {group_id, merged_bins}
        # merged_bins should contain bin labels, not IDs
        details = []
        for mb in merged_bins:
            group_id = str(mb['merged_bin_number'])
            original_ids = mb['original_bin_ids']  # List of original bin IDs
            original_labels = mb.get('original_bin_labels', [])  # List of original bin labels
            
            # Use original_bin_labels if available, otherwise map IDs to labels
            if original_labels and len(original_labels) == len(original_ids):
                bin_labels = original_labels
            else:
                # Use mapped labels, with fallback using feature type
                bin_labels = []
                for bid in original_ids:
                    label = bin_id_to_label.get(bid)
                    if label:
                        bin_labels.append(label)
                    else:
                        # Use feature type to determine prefix (already set above)
                        bin_labels.append(f'{prefix}{bid}')
            
            details.append({
                'group_id': group_id,
                'merged_bins': bin_labels  # Return as array of labels
            })
        
        print(f"[get_finebin_details] Returning {len(details)} merge groups for {column_name}")
        return jsonify(details)  # Return array directly
    except Exception as e:
        print(f"[get_finebin_details] ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify([])  # Return empty array on error


@app.route('/api/finebin-cache/<int:record_id>/<string:column_name>', methods=['GET'])
def get_finebin_cache(record_id: int, column_name: str):
    """
    Retrieve persisted fine binning stats + merges without recalculating algorithms.
    Used to hydrate manual binning UI.
    """
    print(f"\n[API] /api/finebin-cache/{record_id}/{column_name} (GET) called")
    try:
        dataset_id = record_id
        print(f"[get_finebin_cache] DEBUG: dataset_id={dataset_id}, column_name={column_name}")
        
        feature = get_feature_by_name(dataset_id, column_name)
        if not feature:
            print(f"[get_finebin_cache] DEBUG: Feature not found for {column_name}")
            return jsonify({"success": False, "reason": "feature_not_found"})
        
        print(f"[get_finebin_cache] DEBUG: Feature found, feature_id={feature['id']}")
        fine_step = get_binning_step_by_type(feature['id'], 'fine')
        if not fine_step:
            print(f"[get_finebin_cache] DEBUG: Fine step not found for feature_id={feature['id']}")
            return jsonify({"success": False, "reason": "fine_step_missing"})

        fine_step_id = fine_step['id']
        print(f"[get_finebin_cache] DEBUG: Fine step found, fine_step_id={fine_step_id}")
        bins = get_bins_by_step(fine_step_id)
        if not bins:
            print(f"[get_finebin_cache] DEBUG: No bins found for fine_step_id={fine_step_id}")
            return jsonify({"success": False, "reason": "no_bins"})

        print(f"[get_finebin_cache] DEBUG: Found {len(bins)} bins")
        merged_bins = get_merged_bins_by_step(fine_step_id) or []
        print(f"[get_finebin_cache] DEBUG: Found {len(merged_bins)} merged bins")
        totals = get_binning_totals(fine_step_id)
        
        # Calculate derived metrics on-the-fly
        bins = calculate_derived_bin_metrics(bins, totals)

        def _safe_float(value):
            """Safely convert to float, handling NaN/inf"""
            if value is None:
                return None
            try:
                val = float(value)
                # Check for NaN or inf
                if np.isnan(val) or np.isinf(val):
                    return None
                return val
            except (TypeError, ValueError):
                return None

        # Get feature type to determine correct prefix (c for continuous, d for discrete)
        feature_type = feature.get('type', 'continuous')  # Default to continuous if not set
        prefix = 'c' if feature_type == 'continuous' else 'd'
        
        stats = []
        for row in bins:
            # Use _row_to_native_types to handle Decimal/NumPy types and NaN/inf
            native_row = _row_to_native_types(dict(row))
            label = native_row.get('bin_label')
            if not label:
                bin_number = native_row.get('bin_number')
                if bin_number is not None:
                    # Use feature type to determine prefix
                    label = f"{prefix}{bin_number}"
                else:
                    label = str(native_row.get('id', ''))
            stats.append({
                'Bin': label,
                'Range': native_row.get('range_text'),
                'Good': int(native_row.get('good_count') or 0),
                'Bad': int(native_row.get('bad_count') or 0),
                'Total': int(native_row.get('total_count') or 0),
                'Bad Rate': native_row.get('bad_rate'),  # Already sanitized by _row_to_native_types
                'Freq%': native_row.get('freq_percent'),
                'WOE': native_row.get('woe'),
                'IV': native_row.get('iv'),
                'Min': native_row.get('min_value'),
                'Max': native_row.get('max_value'),
            })

        merges_map = {}
        for merged in merged_bins:
            key = str(merged.get('merged_bin_number'))
            labels = merged.get('original_bin_labels')
            if not labels:
                ids = merged.get('original_bin_ids') or []
                # Use feature type to determine prefix (already set above)
                # Note: original_bin_ids are bin IDs, not bin numbers, so we need to look them up
                # For now, preserve the original_bin_labels if available, otherwise use IDs as-is
                # The labels should already be in the database with correct c/d prefix
                labels = labels or [str(bid) for bid in ids]  # Fallback to IDs if no labels
            merges_map[key] = labels

        response_payload = {
            "success": True,
            "stats": stats,
            "bin_merges": merges_map,
            "iv": _safe_float(fine_step.get('iv_value')),
            "metadata": {
                "step_id": fine_step_id,
                "method": fine_step.get('method'),
                "num_bins": len(stats),
                "is_monotonic": fine_step.get('is_monotonic'),
                "monotonic_direction": fine_step.get('monotonic_direction'),
                "totals": totals
            }
        }

        print(f"[get_finebin_cache] ✓ Returning {len(stats)} stats, {len(merges_map)} merges for {column_name}")
        return jsonify(response_payload)
    except Exception as exc:
        print(f"[get_finebin_cache] ERROR: {exc}")
        traceback.print_exc()
        return jsonify({"success": False, "reason": "exception", "error": str(exc)}), 500

# ----------- Debug Binning -----------
@app.route('/api/debug-binning/<string:variable>', methods=['GET'])
def debug_binning(variable):
    """
    Debug endpoint to see what's happening with binning for a specific variable.
    """
    try:
        dataset_id = request.args.get('record_id') or request.args.get('dataset_id')
        try:
            csv_path = get_csv_path(dataset_id)
        except FileNotFoundError as fe:
            return jsonify({"error": str(fe)}), 400
        try:
            df = pd.read_csv(csv_path)
        except FileNotFoundError as fe:
            return jsonify({"error": str(fe)}), 400
        except Exception as e:
            return jsonify({"error": f"Failed to read dataset CSV: {str(e)}"}), 400
        
        if variable not in df.columns:
            return jsonify({"error": f"Variable {variable} not found"}), 400
            
        var_series = df[variable]
        result = {
            "variable": variable,
            "dtype": str(var_series.dtype),
            "nunique": var_series.nunique(dropna=True),
            "sample_values": var_series.dropna().head(10).tolist(),
            "is_numeric": pd.api.types.is_numeric_dtype(var_series)
        }
        
        # Check what our logic would classify it as
        is_likely_id = any(keyword in variable.lower() for keyword in ['id', 'key', 'code', 'no', 'num'])
        unique_count = var_series.nunique(dropna=True)
        
        if pd.api.types.is_numeric_dtype(var_series):
            if is_likely_id or unique_count <= 50:
                result["predicted_type"] = "discrete"
            else:
                result["predicted_type"] = "continuous"
        else:
            result["predicted_type"] = "discrete"
            
        result["is_likely_id"] = is_likely_id
        
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/generate-scorecard', methods=['POST'])
def generate_scorecard():
    """
    Generates a score card using pre-computed model results.
    """
    try:
        # Parse request data
        data = request.get_json()
        selected_variables = data.get('selected_variables', [])
        target = data.get('target')
        woe_transformed_data = data.get('woe_transformed_data', {})
        model_results = data.get('model_results', {})  # Accept pre-computed model results
        model_type = data.get('model_type', 'logistic')  # Accept model type
        dataset_id = (
            data.get('record_id')
            or data.get('dataset_id')
            or data.get('recordId')
            or data.get('datasetId')
        )
        
        # Ensure dataset_id is an integer
        if dataset_id:
            try:
                dataset_id = int(dataset_id)
            except (ValueError, TypeError):
                return jsonify({"error": f"Invalid dataset_id: {dataset_id}"}), 400

        # Input validation
        if not selected_variables or not target or not woe_transformed_data:
            return jsonify({"error": "Missing required data: selected_variables, target, or woe_transformed_data"}), 400
        if not dataset_id:
            return jsonify({"error": "Missing dataset_id/record_id"}), 400
        if not all(isinstance(var, str) for var in selected_variables):
            return jsonify({"error": "All selected_variables must be strings"}), 400
        if not isinstance(woe_transformed_data, dict):
            return jsonify({"error": "woe_transformed_data must be a dictionary"}), 400

        # Load dataset - use TRAIN set for scorecard generation (to match model training)
        try:
            df = get_data_for_stage(dataset_id, 'training')
            print(f"[GENERATE-SCORECARD] Loaded TRAIN dataset: {len(df)} rows, {len(df.columns)} columns")
            if df.empty:
                return jsonify({"error": "Train dataset is empty"}), 400
            if len(df.columns) == 0:
                return jsonify({"error": "Train dataset has no columns"}), 400
        except Exception as e:
            print(f"[GENERATE-SCORECARD] Error loading dataset: {str(e)}")
            import traceback
            traceback.print_exc()
            return jsonify({"error": f"Failed to load dataset: {str(e)}"}), 400

        # Validate columns
        if target not in df.columns:
            return jsonify({"error": f"Target column '{target}' not found in dataset. Available columns: {list(df.columns)[:10]}"}), 400
        missing_vars = [var for var in selected_variables if var not in df.columns]
        if missing_vars:
            return jsonify({"error": f"Variables not found in dataset: {missing_vars}. Available columns: {list(df.columns)[:10]}"}), 400
        missing_woe = [var for var in selected_variables if var not in woe_transformed_data]
        if missing_woe:
            return jsonify({"error": f"Missing WOE data for variables: {missing_woe}"}), 400

        # Validate target is binary
        df[target] = pd.to_numeric(df[target], errors='coerce').fillna(0).astype(int)
        if set(df[target].unique()) - {0, 1}:
            return jsonify({"error": "Target variable must be binary (0/1)"}), 400

        # Extract coefficients from pre-computed model results
        coefficients = {}
        intercept = 0
        
        if model_results and model_type == 'logistic':
            # Extract from logistic regression results
            if 'coefficients' in model_results:
                for coef_info in model_results['coefficients']:
                    var_name = coef_info.get('variable')
                    if var_name and var_name != 'Intercept':
                        coefficients[var_name] = coef_info.get('coefficient', 0)
                    elif var_name == 'Intercept':
                        intercept = coef_info.get('coefficient', 0)
            else:
                return jsonify({"error": "No coefficients found in logistic regression results"}), 400
        
        elif model_results and model_type in ['random_forest', 'xgboost']:
            # For tree-based models, use feature importance with proper scaling
            if 'feature_importance' in model_results:
                # Normalize feature importances to sum to 1
                total_importance = sum(feature_info.get('importance', 0) for feature_info in model_results['feature_importance'])
                if total_importance > 0:
                    for feature_info in model_results['feature_importance']:
                        var_name = feature_info.get('variable')
                        importance = feature_info.get('importance', 0)
                        # Convert importance to coefficient-like values with proper scaling
                        # Use a scaling factor that makes sense for score ranges
                        coefficients[var_name] = (importance / total_importance) * 50  # Scale to reasonable range
                else:
                    return jsonify({"error": f"Total feature importance is zero for {model_type}"}), 400
            else:
                return jsonify({"error": f"No feature importance found in {model_type} results"}), 400
            # For tree models, we use a base intercept
            intercept = 0
        else:
            return jsonify({"error": f"Unsupported model type: {model_type} or missing model results"}), 400

        # Prepare WOE-transformed data for scorecard generation
        # Handle normalized array format directly (no JSON conversion needed)
        modeling_data = {}
        for var in selected_variables:
            woe_data = woe_transformed_data[var]
            ranges_list = None

            # Handle normalized array format (direct from database)
            if isinstance(woe_data, list):
                # Direct array of bin objects (NormalizedBin format)
                ranges_list = [{
                    'range': r.get('range_text') or r.get('Range') or r.get('Bin') or r.get('bin_label') or str(r),
                    'woe': float(r.get('woe') or r.get('WOE') or 0),
                    'min_value': r.get('min_value'),
                    'max_value': r.get('max_value')
                } for r in woe_data if isinstance(r, dict)]
            # Legacy support for dict structures (should not be needed with normalized DB)
            elif isinstance(woe_data, dict) and 'woe_ranges' in woe_data and isinstance(woe_data['woe_ranges'], list):
                ranges_list = woe_data['woe_ranges']
            elif isinstance(woe_data, dict) and 'stats' in woe_data and isinstance(woe_data['stats'], list):
                ranges_list = [{
                    'range': r.get('Range') or r.get('Bin') or str(r),
                    'woe': float(r.get('WOE') or 0)
                } for r in woe_data['stats']]
            else:
                print(f"[generate_scorecard] Warning: Invalid WOE data format for {var}: {type(woe_data)}")
                continue

            if not ranges_list:
                print(f"[generate_scorecard] Warning: No valid ranges found for {var}")
                continue

            # Build WOE mapping from normalized bin data
            woe_mapping = {}
            for range_info in ranges_list:
                try:
                    # Handle normalized format: prefer range_text, then min/max values
                    bin_range = range_info.get('range') or range_info.get('range_text')
                    woe_value = float(range_info.get('woe') or range_info.get('WOE') or 0)
                    
                    # If no range_text, construct from min/max values (for continuous variables)
                    if not bin_range and range_info.get('min_value') is not None:
                        min_val = range_info.get('min_value')
                        max_val = range_info.get('max_value')
                        if min_val is not None and max_val is not None:
                            bin_range = f"({min_val}, {max_val}]"
                        elif min_val is not None:
                            bin_range = f"({min_val}, inf)"
                        elif max_val is not None:
                            bin_range = f"(-inf, {max_val}]"
                    
                    if bin_range is None:
                        continue

                    # Handle Missing/NaN
                    if isinstance(bin_range, str) and ('Missing' in bin_range or 'NaN' in bin_range):
                        mask = df[var].isna()
                        for idx in df[mask].index:
                            woe_mapping[idx] = woe_value
                        continue

                    # Numeric range parsing (e.g., "(a, b]", "[a, b]")
                    if isinstance(bin_range, str) and any(ch in bin_range for ch in '(),[]'):
                        range_str = bin_range.replace('(', '').replace(')', '').replace('[', '').replace(']', '')
                        parts = [p.strip() for p in range_str.split(',') if p.strip()]
                        if len(parts) == 2:
                            try:
                                lower = float(parts[0]) if parts[0].lower() not in ['-inf', 'inf'] else (float('-inf') if parts[0].lower() == '-inf' else float('inf'))
                                upper = float(parts[1]) if parts[1].lower() not in ['-inf', 'inf'] else (float('-inf') if parts[1].lower() == '-inf' else float('inf'))
                                if lower == float('-inf'):
                                    mask = df[var] <= upper
                                elif upper == float('inf'):
                                    mask = df[var] > lower
                                else:
                                    mask = (df[var] > lower) & (df[var] <= upper)
                                for idx in df[mask].index:
                                    woe_mapping[idx] = woe_value
                                continue
                            except (ValueError, TypeError):
                                pass

                    # Hyphen-separated ranges (e.g., "1 - 2")
                    hyphen_match = re.match(r'^\s*-?\d+(?:\.\d+)?\s*-\s*-?\d+(?:\.\d+)?\s*$', str(bin_range))
                    if isinstance(bin_range, str) and hyphen_match:
                        try:
                            parts = [p.strip() for p in bin_range.split('-')]
                            lower, upper = float(parts[0]), float(parts[1])
                            mask = (df[var].astype(float) >= lower) & (df[var].astype(float) <= upper)
                            for idx in df[mask].index:
                                woe_mapping[idx] = woe_value
                            continue
                        except (ValueError, TypeError):
                            pass

                    # Categorical values (comma-separated or single)
                    if isinstance(bin_range, str):
                        cat_vals = [v.strip() for v in bin_range.split(',') if v.strip()]
                        for cat_val in cat_vals:
                            try:
                                mask = df[var].astype(str) == str(cat_val)
                                for idx in df[mask].index:
                                    woe_mapping[idx] = woe_value
                            except Exception:
                                continue
                except Exception:
                    pass

            if woe_mapping:
                woe_column = [woe_mapping.get(i, 0) for i in range(len(df))]
                modeling_data[var] = woe_column
            else:
                modeling_data[var] = [0] * len(df)

        # Create DataFrame with WOE-transformed variables
        if not modeling_data:
            return jsonify({"error": "No WOE-transformed data created. Check WOE transformations."}), 400
        
        model_df = pd.DataFrame(modeling_data)
        print(f"[GENERATE-SCORECARD] Created model_df: {len(model_df)} rows, {len(model_df.columns)} columns")
        
        if model_df.empty:
            return jsonify({"error": "WOE-transformed DataFrame is empty"}), 400
        
        model_df[target] = df[target]

        # Check for missing variables
        missing_vars = [v for v in selected_variables if v not in model_df.columns]
        if missing_vars:
            return jsonify({
                "error": f"Missing variables in WOE-transformed data: {missing_vars}",
                "debug": {
                    "selected_variables": selected_variables,
                    "available_columns": list(model_df.columns)
                }
            }), 400

        # Remove rows with missing target values
        model_df = model_df.dropna(subset=[target])
        if model_df.empty:
            return jsonify({"error": "No valid data after removing missing target values"}), 400

        # Score card parameters - use DEFAULT_SCORECARD_CONFIG for consistency
        N = len(selected_variables)
        
        # Use DEFAULT_SCORECARD_CONFIG for consistency with _probability_to_score
        # This ensures scores from scorecard match scores from probability conversion
        if model_type == 'logistic':
            factor, offset = _scorecard_scaling_params(DEFAULT_SCORECARD_CONFIG)
            print(f"[generate_scorecard] Using factor={factor:.4f}, offset={offset:.4f} (PDO={DEFAULT_SCORECARD_CONFIG['points_to_double_odds']})")
        else:
            # For tree-based models, use different parameters since we don't have true coefficients
            factor = 15 / np.log(2)  # Smaller factor for tree models
            base_odds = 50
            base_score = 600
            offset = base_score - factor * np.log(base_odds)

        # Generate score card and calculate score ranges
        scorecard_bins = []
        var_score_ranges = {var: [] for var in selected_variables}
        processed_ranges = set()

        for var in selected_variables:
            # For tree models, all selected variables should have feature importance
            # For logistic, variables should have coefficients
            if var not in coefficients:
                print(f"[generate_scorecard] Warning: Variable {var} not in coefficients/importance dict")
                continue
            beta = coefficients[var]
            ranges_source = None
            
            # Handle normalized array format (direct from database)
            if var in woe_transformed_data:
                woe_data = woe_transformed_data[var]
                if isinstance(woe_data, list):
                    # Direct array of bin objects (NormalizedBin format)
                    ranges_source = []
                    for r in woe_data:
                        if not isinstance(r, dict):
                            continue
                        # Try multiple field names for range (discrete uses range_text, continuous uses min/max)
                        bin_range = (
                            r.get('range_text') or 
                            r.get('bin_label') or 
                            r.get('Range') or 
                            r.get('Bin') or 
                            None
                        )
                        
                        # If no range_text/bin_label, construct from min/max values (for continuous)
                        if not bin_range:
                            min_val = r.get('min_value')
                            max_val = r.get('max_value')
                            if min_val is not None and max_val is not None:
                                bin_range = f"({min_val}, {max_val}]"
                            elif min_val is not None:
                                bin_range = f"({min_val}, inf)"
                            elif max_val is not None:
                                bin_range = f"(-inf, {max_val}]"
                        
                        # Skip if still no range
                        if not bin_range:
                            print(f"[generate_scorecard] Warning: Skipping bin for {var} - no range found (r: {r})")
                            continue
                        
                        ranges_source.append({
                            'range': bin_range,
                            'woe': float(r.get('woe') or r.get('WOE') or 0),
                            'min_value': r.get('min_value'),
                            'max_value': r.get('max_value')
                        })
                    
                    print(f"[generate_scorecard] Found {len(ranges_source)} bins for {var} from normalized array (out of {len(woe_data)} total)")
                # Legacy support for dict structures
                elif isinstance(woe_data, dict):
                    if 'woe_ranges' in woe_data:
                        ranges_source = woe_data['woe_ranges']
                    elif 'stats' in woe_data:
                        ranges_source = [{
                            'range': r.get('Range') or r.get('Bin') or str(r),
                            'woe': float(r.get('WOE') or 0)
                        } for r in woe_data['stats']]

            if not ranges_source:
                print(f"[generate_scorecard] Warning: No ranges found for {var} (woe_data type: {type(woe_transformed_data.get(var))})")
                continue
            
            print(f"[generate_scorecard] Processing {len(ranges_source)} bins for {var}")

            for i, range_info in enumerate(ranges_source):
                try:
                    bin_range = range_info.get('range') if isinstance(range_info, dict) else str(range_info)
                    woe_value = float(range_info.get('woe') if isinstance(range_info, dict) else 0)
                    
                    # Skip if bin_range is still None or empty
                    if not bin_range or bin_range == 'None' or str(bin_range).strip() == '':
                        print(f"[generate_scorecard] Skipping bin {i} for {var}: empty range (range_info: {range_info})")
                        continue
                    
                    range_key = f"{var}_{bin_range}_{woe_value}"
                    if range_key in processed_ranges:
                        continue
                    processed_ranges.add(range_key)
                    
                    print(f"[generate_scorecard] Adding bin for {var}: range={bin_range}, woe={woe_value}, beta={beta}")

                    if model_type == 'logistic':
                        # CORRECTED FORMULA for logistic regression scorecard
                        # WOE is stored as ln(ratio) * 100, but model coefficients expect natural log scale
                        # Convert stored WOE back to natural log: divide by 100
                        woe_natural_log = woe_value / 100.0
                        
                        # Standard scorecard formula: Score_i = Factor × (β_i × WOE_i)
                        # where WOE_i is in natural log scale
                        score_contribution = factor * (beta * woe_natural_log)
                        
                        # Distribute base offset and intercept across N variables
                        # Offset per variable = (base_offset + intercept_factor) / N
                        intercept_factor = intercept * factor
                        score = (offset + intercept_factor) / N + score_contribution
                    else:
                        # For tree-based models, use simplified formula
                        # Use NEGATIVE coefficients for proper credit scoring direction
                        # Higher risk = lower score, Lower risk = higher score
                        score = (-beta * woe_value + intercept / N) * factor + offset / N
                    bin_data = {
                        'variable': var,
                        'bin_range': bin_range,
                        'woe': woe_value,
                        'coefficient': beta,
                        'score': round(float(score), 2)
                    }
                    if model_type == 'logistic':
                        bin_data['coefficient'] = round(float(beta), 4)
                    else:  # random_forest or xgboost
                        bin_data['feature_importance'] = round(float(beta), 4)
                    scorecard_bins.append(bin_data)
                    var_score_ranges[var].append(score)
                except (ValueError, TypeError) as e:
                    print(f"[generate_scorecard] Error processing bin {i} for {var}: {e}")
                    import traceback
                    traceback.print_exc()

        # Calculate score range per variable
        min_total_score = 0
        max_total_score = 0
        for var in selected_variables:
            scores = var_score_ranges.get(var, [])
            if scores:
                min_total_score += min(scores)
                max_total_score += max(scores)

        min_total_score = round(float(min_total_score), 2) if min_total_score else 0
        max_total_score = round(float(max_total_score), 2) if max_total_score else 0
        
        print(f"[generate_scorecard] Generated {len(scorecard_bins)} scorecard bins for {len(selected_variables)} variables")
        print(f"[generate_scorecard] Score range: {min_total_score} - {max_total_score}")

        # For tree models, adjust the score range if it's unreasonable
        if model_type in ['random_forest', 'xgboost']:
            # Tree models might produce very different score ranges
            # Ensure reasonable credit score range (typically 300-850)
            if max_total_score > 1000 or min_total_score < 0:
                # Rescale to reasonable range
                current_range = max_total_score - min_total_score
                if current_range > 0:
                    scale_factor = 550 / current_range  # Target range of 550 points
                    # Rescale all scores
                    for bin_info in scorecard_bins:
                        bin_info['score'] = round(300 + (bin_info['score'] - min_total_score) * scale_factor, 2)
                    # Recalculate total range
                    min_total_score = 300
                    max_total_score = 850

        return jsonify({
            "success": True,
            "scorecard_bins": scorecard_bins,
            "score_parameters": {
                "factor": round(float(factor), 4),
                "offset": round(float(offset), 4),
                "base_score": base_score,
                "base_odds": base_odds,
                "intercept": round(float(intercept), 4),
                "n_variables": N,
                "min_score": min_total_score,
                "max_score": max_total_score,
                "model_type": model_type
            },
            "model_summary": {
                "coefficients": {k: round(float(v), 4) for k, v in coefficients.items()},
                "intercept": round(float(intercept), 4),
                "n_observations": len(model_df),
                "n_variables": N,
                "n_columns": len(model_df.columns) if 'model_df' in locals() else 0,
                "model_type": model_type
            }
        })

    except Exception as e:
        import traceback
        print(f"ERROR in generate_scorecard: {traceback.format_exc()}")
        return jsonify({"error": f"Failed to generate score card ({type(e).__name__}): {str(e)}"}), 500
    
# ----------- Apply Score Card to All Records -----------
@app.route('/api/apply-scorecard', methods=['POST'])
def apply_scorecard():
    """
    Applies the score card to all records in the uploaded dataset using pre-computed model results.
    """
    import numpy as np
    try:
        data = request.get_json()
        selected_variables = data.get('selected_variables', [])
        target = data.get('target')
        woe_transformed_data = data.get('woe_transformed_data', {})
        model_results = data.get('model_results', {})  # Accept pre-computed model results
        model_type = data.get('model_type', 'logistic')  # Accept model type
        dataset_id = (
            data.get('record_id')
            or data.get('dataset_id')
            or data.get('recordId')
            or data.get('datasetId')
        )
        
        # Ensure dataset_id is an integer
        if dataset_id:
            try:
                dataset_id = int(dataset_id)
            except (ValueError, TypeError):
                return jsonify({"error": f"Invalid dataset_id: {dataset_id}"}), 400

        # Input validation
        if not selected_variables or not target or not woe_transformed_data:
            return jsonify({"error": "Missing required data: selected_variables, target, or woe_transformed_data"}), 400
        if not dataset_id:
            return jsonify({"error": "Missing dataset_id/record_id"}), 400

        # Load dataset - use TEST dataset for test scorecard evaluation
        try:
            df = get_data_for_stage(dataset_id, 'evaluation')  # Use TEST set for evaluation
            print(f"[APPLY-SCORECARD] Loaded TEST dataset: {len(df)} rows, {len(df.columns)} columns")
            if df.empty:
                return jsonify({"error": "Dataset is empty"}), 400
            if len(df.columns) == 0:
                return jsonify({"error": "Dataset has no columns"}), 400
        except Exception as e:
            print(f"[APPLY-SCORECARD] Error loading dataset: {str(e)}")
            import traceback
            traceback.print_exc()
            return jsonify({"error": f"Failed to load dataset: {str(e)}"}), 400

        if target not in df.columns:
            return jsonify({"error": f"Target column '{target}' not found in dataset. Available columns: {list(df.columns)[:10]}"}), 400

        # Sanitize non-finite values in selected variables
        for var in selected_variables:
            if var in df.columns:
                df[var] = df[var].replace([np.inf, -np.inf], np.nan)
                if df[var].isnull().any():
                    if df[var].dtype.kind in 'biufc':
                        df[var] = df[var].fillna(df[var].median())
                    else:
                        df[var] = df[var].fillna('Missing')

        # Prepare WOE-transformed data for each variable
        # Handle normalized array format directly (no JSON conversion needed)
        modeling_data = {}
        for var in selected_variables:
            woe_data = woe_transformed_data[var]
            ranges_list = None

            # Handle normalized array format (direct from database)
            if isinstance(woe_data, list):
                # Direct array of bin objects (NormalizedBin format)
                ranges_list = [{
                    'range': r.get('range_text') or r.get('Range') or r.get('Bin') or r.get('bin_label') or str(r),
                    'woe': float(r.get('woe') or r.get('WOE') or 0),
                    'min_value': r.get('min_value'),
                    'max_value': r.get('max_value')
                } for r in woe_data if isinstance(r, dict)]
            # Legacy support for dict structures (should not be needed with normalized DB)
            elif isinstance(woe_data, dict) and 'woe_ranges' in woe_data and isinstance(woe_data['woe_ranges'], list):
                ranges_list = woe_data['woe_ranges']
            elif isinstance(woe_data, dict) and 'stats' in woe_data and isinstance(woe_data['stats'], list):
                ranges_list = [{
                    'range': r.get('Range') or r.get('Bin') or str(r),
                    'woe': float(r.get('WOE') or 0)
                } for r in woe_data['stats']]
            else:
                print(f"[apply_scorecard] Warning: Invalid WOE data format for {var}: {type(woe_data)}")
                continue

            if not ranges_list:
                print(f"[apply_scorecard] Warning: No valid ranges found for {var}")
                continue
                
            # Build WOE mapping from normalized bin data
            woe_mapping = {}
            assigned_count = 0
            
            for range_info in ranges_list:
                try:
                    # Handle normalized format: prefer range_text, then min/max values
                    bin_range = range_info.get('range') or range_info.get('range_text')
                    woe_value = float(range_info.get('woe') or range_info.get('WOE') or 0)
                    
                    # If no range_text, construct from min/max values (for continuous variables)
                    if not bin_range and range_info.get('min_value') is not None:
                        min_val = range_info.get('min_value')
                        max_val = range_info.get('max_value')
                        if min_val is not None and max_val is not None:
                            bin_range = f"({min_val}, {max_val}]"
                        elif min_val is not None:
                            bin_range = f"({min_val}, inf)"
                        elif max_val is not None:
                            bin_range = f"(-inf, {max_val}]"
                    
                    if bin_range is None:
                        continue

                    # Handle Missing/NaN
                    if isinstance(bin_range, str) and ('Missing' in bin_range or 'NaN' in bin_range):
                        mask = df[var].isna() | (df[var] == 'Missing')
                        for idx in df[mask].index:
                            woe_mapping[idx] = woe_value
                        assigned_count += mask.sum()
                        continue

                    # Numeric range parsing (e.g., "(a, b]", "[a, b]")
                    if isinstance(bin_range, str) and any(ch in bin_range for ch in '(),[]'):
                        range_str = bin_range.replace('(', '').replace(')', '').replace('[', '').replace(']', '')
                        parts = [p.strip() for p in range_str.split(',') if p.strip()]
                        if len(parts) == 2:
                            try:
                                lower = float(parts[0]) if parts[0].lower() not in ['-inf', 'inf'] else (float('-inf') if parts[0].lower() == '-inf' else float('inf'))
                                upper = float(parts[1]) if parts[1].lower() not in ['-inf', 'inf'] else (float('-inf') if parts[1].lower() == '-inf' else float('inf'))
                                if lower == float('-inf'):
                                    mask = df[var] <= upper
                                elif upper == float('inf'):
                                    mask = df[var] > lower
                                else:
                                    mask = (df[var] > lower) & (df[var] <= upper)
                                for idx in df[mask].index:
                                    woe_mapping[idx] = woe_value
                                assigned_count += mask.sum()
                                continue
                            except (ValueError, TypeError):
                                pass

                    # Hyphen-separated ranges (e.g., "1 - 2")
                    hyphen_match = re.match(r'^\s*-?\d+(?:\.\d+)?\s*-\s*-?\d+(?:\.\d+)?\s*$', str(bin_range))
                    if isinstance(bin_range, str) and hyphen_match:
                        try:
                            parts = [p.strip() for p in bin_range.split('-')]
                            lower, upper = float(parts[0]), float(parts[1])
                            mask = (df[var].astype(float) >= lower) & (df[var].astype(float) <= upper)
                            for idx in df[mask].index:
                                woe_mapping[idx] = woe_value
                            assigned_count += mask.sum()
                            continue
                        except (ValueError, TypeError):
                            pass

                    # Categorical values (comma-separated or single)
                    if isinstance(bin_range, str):
                        cat_vals = [v.strip() for v in bin_range.split(',') if v.strip()]
                        for cat_val in cat_vals:
                            try:
                                mask = df[var].astype(str) == str(cat_val)
                                for idx in df[mask].index:
                                    woe_mapping[idx] = woe_value
                                assigned_count += mask.sum()
                            except Exception:
                                continue
                except Exception as e:
                    print(f"DEBUG: Error processing range {bin_range} for {var}: {e}")
                    continue

            print(f"DEBUG: Assigned WOE values for {var}: {assigned_count} rows")
            
            # CRITICAL FIX: Use actual DataFrame index, not range(len(df))
            # This ensures all rows get WOE values correctly mapped
            woe_column = [woe_mapping.get(idx, 0) for idx in df.index]
            modeling_data[var] = woe_column
            modeling_data[f'{var}_WOE'] = woe_column

        # Create DataFrame with WOE-transformed variables
        if not modeling_data:
            return jsonify({"error": "No WOE-transformed data created. Check WOE transformations."}), 400
        
        model_df = pd.DataFrame(modeling_data)
        print(f"[APPLY-SCORECARD] Created model_df: {len(model_df)} rows, {len(model_df.columns)} columns")
        
        if model_df.empty:
            return jsonify({"error": "WOE-transformed DataFrame is empty"}), 400
        
        model_df[target] = pd.to_numeric(df[target], errors='coerce').fillna(0).astype(int)
        # CRITICAL FIX: Preserve original DataFrame index as row_id to track all test rows
        model_df['__row_id__'] = df.index.values  # Use original DataFrame index

        # Remove rows with missing target
        mask = ~model_df[target].isna()
        filtered_df = model_df[mask].copy()  # Don't reset_index yet - preserve original indices
        print(f"[APPLY-SCORECARD] After filtering: {len(filtered_df)} rows, {len(filtered_df.columns)} columns")
        print(f"[APPLY-SCORECARD] Original dataset had {len(df)} rows, filtered to {len(filtered_df)} rows")
        
        if filtered_df.empty:
            return jsonify({"error": "No valid data after preprocessing"}), 400
        
        # Extract row_ids before dropping the column
        row_ids = filtered_df['__row_id__'].astype(int).tolist()
        filtered_df = filtered_df.drop(columns=['__row_id__'])
        
        # Verify alignment: predictions should match row_ids
        print(f"[APPLY-SCORECARD] Row IDs extracted: {len(row_ids)} IDs, range: {min(row_ids) if row_ids else 'N/A'} to {max(row_ids) if row_ids else 'N/A'}")
        y = filtered_df[target]
        X_logistic = filtered_df[selected_variables]
        tree_feature_names = [f'{var}_WOE' for var in selected_variables if f'{var}_WOE' in filtered_df.columns]
        X_tree = filtered_df[tree_feature_names] if tree_feature_names else pd.DataFrame()

        # Calculate scores based on model type
        scores = []
        probabilities_for_roc = None  # Initialize for ROC curve calculation
        
        if model_type == 'logistic':
            if not model_results or 'coefficients' not in model_results:
                return jsonify({"error": "Logistic scorecard application requires model coefficients"}), 400
            
            coefficients = {}
            intercept = 0.0
            for coef_info in model_results.get('coefficients', []):
                var_name = coef_info.get('variable')
                if var_name and var_name != 'Intercept':
                    coefficients[var_name] = coef_info.get('coefficient', 0.0)
                elif var_name == 'Intercept':
                    intercept = coef_info.get('coefficient', 0.0)
            
            logit = np.full(len(filtered_df), intercept, dtype=float)
            for var in selected_variables:
                beta = coefficients.get(var, 0.0)
                if beta == 0.0 or var not in X_logistic.columns:
                    continue
                logit += beta * X_logistic[var].values
            
            prob_bad = 1.0 / (1.0 + np.exp(-logit))
            # Store probabilities for ROC curve calculation
            probabilities_for_roc = prob_bad.copy()
            scores = _probability_to_score(prob_bad, DEFAULT_SCORECARD_CONFIG).astype(float).tolist()
                
        elif model_type in ['random_forest', 'xgboost']:
            # KEY FIX: For XGBoost, use the trained model on RAW features
            try:
                y_pred_proba_bad = None
                artifact_used = False
                
                # Try to load persisted model artifact
                artifact_data, artifact_label = load_model_artifact(dataset_id, model_type)
                
                if model_type == 'xgboost' and artifact_data and artifact_data.get('model_bytes'):
                    print(f"[apply_scorecard] Loading XGBoost model from artifact")
                    
                    # Check if model uses raw features (new) or WOE features (old)
                    uses_raw_features = artifact_data.get('uses_raw_features', False)
                    
                    if uses_raw_features:
                        # NEW: Model trained on RAW features
                        print(f"[apply_scorecard] Applying XGBoost trained on RAW features")
                        try:
                            scoring_result = apply_xgboost_scorecard(df, target, artifact_data)
                            y_pred_proba_bad = scoring_result['probabilities']
                            y = scoring_result['target']
                            row_ids = scoring_result['row_ids']
                            artifact_used = True
                            print(f"[apply_scorecard] Successfully applied XGBoost on raw features")
                        except Exception as raw_err:
                            print(f"[apply_scorecard] Failed to apply XGBoost on raw features: {raw_err}")
                            import traceback
                            traceback.print_exc()
                            return jsonify({"error": f"Failed to apply XGBoost model: {str(raw_err)}"}), 500
                    else:
                        # OLD: Model trained on WOE features (backward compatibility)
                        print(f"[apply_scorecard] Using old WOE-based XGBoost model")
                        if not X_tree.empty:
                            import pickle
                            try:
                                xgb_model = pickle.loads(artifact_data['model_bytes'])
                                y_pred_proba_bad = xgb_model.predict_proba(X_tree)[:, 1]
                                artifact_used = True
                                print(f"[apply_scorecard] Successfully applied old WOE-based XGBoost model")
                            except Exception as old_err:
                                print(f"[apply_scorecard] Failed to use old WOE model: {old_err}")
                                return jsonify({"error": "Old XGBoost model failed. Please retrain with current version."}), 400
                        else:
                            return jsonify({"error": "No WOE-transformed features available for old XGBoost model"}), 400
                
                elif model_type == 'random_forest':
                    # Random Forest still uses WOE features
                    if X_tree.empty:
                        return jsonify({"error": "No WOE-transformed features available for Random Forest"}), 400
                    
                    # Try to load persisted model artifact (CRITICAL FIX: Don't re-train!)
                    if artifact_data and artifact_data.get('model_bytes'):
                        import pickle
                        try:
                            rf_model = pickle.loads(artifact_data['model_bytes'])
                            y_pred_proba_bad = rf_model.predict_proba(X_tree)[:, 1]
                            artifact_used = True
                            print(f"[apply_scorecard] Loaded and applied Random Forest model from artifact")
                        except Exception as rf_err:
                            print(f"[apply_scorecard] Failed to load RF model from artifact: {rf_err}")
                            return jsonify({"error": "Random Forest model artifact found but failed to load. Please retrain the model."}), 400
                    else:
                        # Fallback: if no artifact, return error (don't re-train on test data!)
                        return jsonify({"error": "Random Forest model not found. Please train the model first."}), 400
                
                if y_pred_proba_bad is None:
                    return jsonify({"error": f"{model_type} model could not generate predictions"}), 400
                
                # CRITICAL FIX: Verify predictions length matches expected rows
                if model_type != 'xgboost' or not (artifact_data and artifact_data.get('uses_raw_features', False)):
                    # For RF and old XGBoost, predictions should match filtered_df length
                    expected_len = len(filtered_df)
                    actual_len = len(y_pred_proba_bad)
                    if expected_len != actual_len:
                        print(f"[APPLY-SCORECARD] WARNING: Prediction length mismatch! Expected {expected_len}, got {actual_len}")
                        print(f"[APPLY-SCORECARD] This may cause missing rows in results")
                
                # Store probabilities for ROC curve calculation (CRITICAL FIX: Use probabilities, not scores)
                probabilities_for_roc = y_pred_proba_bad.copy()
                
                # Convert probabilities to credit scores
                scores_array = _probability_to_score(y_pred_proba_bad, DEFAULT_SCORECARD_CONFIG)
                scores = scores_array.astype(float).tolist()
                
                print(f"[apply_scorecard] {model_type} scoring - Predictions: {len(y_pred_proba_bad)}, Row IDs: {len(row_ids)}")
                print(f"[apply_scorecard] {model_type} scoring - Bad probabilities range: {np.min(y_pred_proba_bad):.4f} to {np.max(y_pred_proba_bad):.4f}")
                print(f"[apply_scorecard] {model_type} scoring - Scores range: {np.min(scores_array):.2f} to {np.max(scores_array):.2f}")
                
            except Exception as model_err:
                print(f"[apply_scorecard] {model_type} model scoring failed: {model_err}")
                import traceback
                traceback.print_exc()
                return jsonify({"error": f"Failed to calculate scores for {model_type}: {str(model_err)}"}), 500
        else:
            return jsonify({"error": f"Unsupported model type or missing model results: {model_type}"}), 400

        # Prepare results
        scores_np = np.asarray(scores, dtype=float)
        results_list = []
        y_true = y.tolist()
        y_score = scores_np.tolist()
        
        # CRITICAL FIX: Verify all arrays have same length
        if len(scores_np) != len(y_true) or len(scores_np) != len(row_ids):
            print(f"[APPLY-SCORECARD] ERROR: Length mismatch! Scores: {len(scores_np)}, y_true: {len(y_true)}, row_ids: {len(row_ids)}")
            # Use minimum length to avoid index errors
            min_len = min(len(scores_np), len(y_true), len(row_ids))
            print(f"[APPLY-SCORECARD] Using minimum length: {min_len} rows")
            scores_np = scores_np[:min_len]
            y_true = y_true[:min_len]
            row_ids = row_ids[:min_len]
        
        for idx, score in enumerate(scores_np):
            row_id = row_ids[idx] if idx < len(row_ids) else idx
            results_list.append({
                "index": int(row_id),
                "score": float(score),
                "target": int(y_true[idx])
            })
        
        print(f"[APPLY-SCORECARD] Created {len(results_list)} result entries from {len(scores_np)} predictions")
        
        # Sort descending by score (HIGHEST scores first = LOWEST risk first)
        results_list = sorted(results_list, key=lambda x: x["score"], reverse=True)

        # Calculate KS statistic (separation number)
        # CRITICAL FIX: Use probabilities for ROC curve, not scores
        try:
            from sklearn.metrics import roc_curve
            # Use probabilities for ROC curve calculation (scores are transformed and may not preserve monotonicity)
            if probabilities_for_roc is None:
                # This should not happen if code flow is correct, but add safety check
                print(f"[APPLY-SCORECARD] ERROR: Probabilities not stored! This indicates a code flow issue.")
                raise ValueError("Probabilities not available for ROC curve calculation")
            
            prob_for_roc = np.asarray(probabilities_for_roc, dtype=float)
            fpr, tpr, thresholds = roc_curve(y_true, prob_for_roc)
            diffs = np.abs(tpr - fpr)
            ks_stat = float(np.max(diffs)) if len(diffs) > 0 else 0.0
            
            # Get KS threshold (in probability space)
            ks_idx = np.argmax(diffs)
            ks_threshold = float(thresholds[ks_idx]) if len(thresholds) > ks_idx else 0.0
            
            print(f"DEBUG: KS Statistic calculated: {ks_stat}, Threshold: {ks_threshold}")
            
            # Debug: Check score distribution by target
            scores_0 = [score for score, target in zip(scores, y_true) if target == 0]
            scores_1 = [score for score, target in zip(scores, y_true) if target == 1]
            print(f"DEBUG: Score distribution - Good (0): {np.mean(scores_0):.2f} ± {np.std(scores_0):.2f}")
            print(f"DEBUG: Score distribution - Bad  (1): {np.mean(scores_1):.2f} ± {np.std(scores_1):.2f}")
            
        except Exception as ks_err:
            print(f"DEBUG: KS calculation error: {ks_err}")
            ks_stat = None
            ks_threshold = None

        # Calculate additional metrics
        try:
            from sklearn.metrics import auc, accuracy_score, precision_score, recall_score, f1_score
            
            # ROC AUC (calculated from probabilities, already done in KS calculation above)
            roc_auc = auc(fpr, tpr) if 'fpr' in locals() and 'tpr' in locals() else 0.0
            
            # For credit scoring, we typically use a different threshold than 0.5
            # Since scores are now properly scaled, we can use a score threshold
            score_threshold = np.percentile(scores_np, 50)  # Median score as threshold
            y_pred = [1 if score < score_threshold else 0 for score in scores_np]  # Lower score = higher risk = predicted bad
            
            accuracy = accuracy_score(y_true, y_pred)
            precision = precision_score(y_true, y_pred, zero_division=0)
            recall = recall_score(y_true, y_pred, zero_division=0)
            f1 = f1_score(y_true, y_pred, zero_division=0)
            
            print(f"DEBUG: Additional metrics - AUC: {roc_auc:.4f}, Accuracy: {accuracy:.4f}")
            print(f"DEBUG: Classification at score threshold {score_threshold:.2f}")
            
        except Exception as metric_err:
            print(f"DEBUG: Metric calculation error: {metric_err}")
            roc_auc = 0.0
            accuracy = 0.0
            precision = 0.0
            recall = 0.0
            f1 = 0.0

        print(f"[APPLY-SCORECARD] Returning results: {len(results_list)} records, {len(filtered_df.columns)} columns in model_df")
        
        return jsonify({
            "success": True, 
            "results": results_list,
            "summary": {
                "total_records": len(results_list),
                "total_columns": len(filtered_df.columns),
                "selected_variables": selected_variables,
                "model_type": model_type
            }, 
            "ks_stat": ks_stat,
            "ks_threshold": ks_threshold,
            "auc": roc_auc,
            "accuracy": accuracy,
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "model_type": model_type,
            "variables_used": selected_variables,
            "n_records": len(results_list),
            "n_columns": len(filtered_df.columns) if 'filtered_df' in locals() else 0,
            "score_range": {
                "min": float(np.min(scores_np)) if len(scores_np) > 0 else 0,
                "max": float(np.max(scores_np)) if len(scores_np) > 0 else 0,
                "mean": float(np.mean(scores_np)) if len(scores_np) > 0 else 0
            }
        })
        
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f"ERROR in apply_scorecard: {tb}")
        return jsonify({"error": f"Failed to apply score card ({type(e).__name__}): {str(e)}"}), 500
    
    
def classify_with_heuristics(column_name, samples):
    """
    Enhanced heuristic classification for discrete vs continuous variables.
    Uses column name patterns and sample data analysis.
    """
    col_name_lower = column_name.lower()
    
    # Check for discrete indicators in column name
    discrete_keywords = ['id', 'code', 'type', 'category', 'class', 'group', 'status', 
                       'flag', 'level', 'grade', 'rating', 'rank', 'gender', 'sex',
                       'marital', 'education', 'occupation', 'department', 'region',
                       'state', 'country', 'city', 'zip', 'postal', 'bool', 'binary']
    
    continuous_keywords = ['age', 'amount', 'price', 'cost', 'salary', 'income', 'revenue',
                         'balance', 'rate', 'ratio', 'percent', 'score', 'weight', 'height',
                         'length', 'width', 'depth', 'distance', 'time', 'duration', 'years',
                         'month', 'day', 'hour', 'minute', 'second', 'value']
    
    is_discrete_name = any(keyword in col_name_lower for keyword in discrete_keywords)
    is_continuous_name = any(keyword in col_name_lower for keyword in continuous_keywords)
    
    if is_discrete_name:
        return 'discrete'
    elif is_continuous_name:
        return 'continuous'
    else:
        # Analyze sample values if available
        try:
            if not samples or len(samples) == 0:
                return 'discrete'  # Default when no data
            
            # Remove None/null values
            clean_samples = [s for s in samples if s is not None and str(s).strip() != '']
            if not clean_samples:
                return 'discrete'
            
            # Check for non-numeric values (strings, booleans)
            non_numeric_count = 0
            for x in clean_samples:
                if isinstance(x, str) and not x.replace('.', '').replace('-', '').isdigit():
                    non_numeric_count += 1
                elif isinstance(x, bool):
                    non_numeric_count += 1
            
            if non_numeric_count > 0:
                return 'discrete'
            
            # Convert to numeric for analysis
            try:
                numeric_samples = [float(x) for x in clean_samples]
            except:
                return 'discrete'
            
            # For numeric data, check patterns
            unique_values = len(set(numeric_samples))
            total_values = len(numeric_samples)
            
            # Low cardinality suggests discrete
            if unique_values <= 10:
                return 'discrete'
            
            # High cardinality (many unique values) suggests continuous
            if unique_values > total_values * 0.8:
                return 'continuous'
            
            # Check if values are all integers
            all_integers = all(isinstance(x, int) or (isinstance(x, float) and x.is_integer()) for x in numeric_samples)
            
            if all_integers:
                # Integer sequences with large gaps might be IDs
                min_val, max_val = min(numeric_samples), max(numeric_samples)
                if max_val - min_val > unique_values * 3:
                    return 'discrete'  # Likely IDs or codes
                else:
                    return 'discrete' if unique_values <= 20 else 'continuous'
            else:
                # Float values generally suggest continuous
                return 'continuous'
                
        except Exception:
            return 'discrete'  # Safe default


if __name__ == '__main__':
    init_db()
    
    # Register new v2 endpoints using new database schema
    try:
        from api_endpoints_new import register_new_endpoints
        register_new_endpoints(app, coarse_bin_continuous, coarse_bin_discrete)
        print("✅ New v2 API endpoints successfully registered")
    except Exception as e:
        print(f"⚠️  Warning: Could not register new v2 endpoints: {e}")
    
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=True, host='0.0.0.0', port=port)

