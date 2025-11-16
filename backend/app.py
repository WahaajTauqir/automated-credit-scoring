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
from typing import Optional, Dict, Any

# Import ONLY new database layer functions - NO MORE db_old imports!
from db import (
    get_db_connection, init_db, ensure_final_selected_column, ensure_model_ready_column, sync_model_ready_to_final_selected,
    # Dataset operations
    create_dataset, get_dataset, get_all_datasets, get_all_datasets_with_features,
    get_latest_dataset, update_dataset, delete_dataset,
    # Feature operations
    create_feature, create_features_batch, get_feature, get_features_by_dataset, 
    get_feature_by_name, update_feature, update_features_selection, update_features_final_selection, update_features_model_ready,
    # Binning step operations
    create_binning_step, get_binning_step, get_binning_steps_by_feature, 
    get_binning_step_by_type, delete_binning_step, update_binning_step,
    # Bin operations
    create_bin, create_bins_batch, get_bins_by_step, get_bin,
    # Merged bins operations
    create_merged_bin, get_merged_bins_by_step,
    # Binning totals operations
    create_binning_totals, get_binning_totals, get_all_binning_totals_by_dataset,
    # Helper functions
    get_complete_binning_results, get_dataset_with_all_results,
    delete_all_binning_for_feature
)
import traceback
import logging
from auto_monotonic_binning import auto_monotonic_binning, compute_woe, compute_iv
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

# Ensure database schema is up to date on startup
try:
    ensure_final_selected_column()
    ensure_model_ready_column()
except Exception as e:
    print(f"[APP] Warning: Could not ensure required columns: {e}")
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

        bin_data = {
            'bin_number': idx + 1,
            'bin_label': str(row.get('Bin', f'Bin_{idx+1}')),
            'good_count': good,
            'bad_count': bad,
            'total_count': total
        }

        # Add Min/Max for continuous
        if 'Min' in row and row['Min'] is not None:
            try:
                bin_data['min_value'] = float(row['Min'])
            except Exception:
                bin_data['min_value'] = None
        if 'Max' in row and row['Max'] is not None:
            try:
                bin_data['max_value'] = float(row['Max'])
            except Exception:
                bin_data['max_value'] = None

        # Add Range for discrete
        if 'Range' in row and row['Range']:
            bin_data['range_text'] = str(row['Range'])

        # Calculate distributions and rates
        dist_good = (good / total_good) * 100 if total_good > 0 else None
        dist_bad = (bad / total_bad) * 100 if total_bad > 0 else None
        bin_data['dist_good'] = dist_good
        bin_data['dist_bad'] = dist_bad
        bin_data['bad_rate'] = (bad / total) * 100 if total > 0 else None
        bin_data['freq_percent'] = (total / total_all) * 100 if total_all > 0 else None

        # Odds and ratio (guard divide-by-zero)
        bin_data['odds'] = (good / bad) if bad > 0 else None
        bin_data['good_bad_ratio'] = bin_data['odds']

        # Index metrics: index_value = dist_good / dist_bad, odds_index = odds / overall_odds
        try:
            bin_data['index_value'] = (dist_good / dist_bad) * 100 if (dist_bad and dist_bad > 0) else None
        except Exception:
            bin_data['index_value'] = None
        try:
            bin_data['odds_index'] = (bin_data['odds'] / overall_odds) * 100 if (bin_data['odds'] is not None and overall_odds and overall_odds > 0) else None
        except Exception:
            bin_data['odds_index'] = None

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

    # Create binning step with monotonic_direction
    step_id = create_binning_step(
        feature_id=feature_id,
        step_type='coarse',
        method='qcut' if var_type == 'continuous' else 'bad_rate',
        num_bins=len(bins_df),
        is_monotonic=is_monotonic,
        monotonic_direction=monotonic_dir
    )

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
        rows = []
        for mb in merged:
            # return merged_bins as a list (do NOT stringify)
            rows.append({'group_id': mb.get('merged_bin_number'), 'merged_bins': mb.get('original_bin_ids', [])})
        return rows
    except Exception:
        return []


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
        if isinstance(value, Decimal):
            normalized[key] = float(value)
        elif hasattr(value, 'item'):
            try:
                normalized[key] = value.item()
            except Exception:
                normalized[key] = value
        else:
            normalized[key] = value
    return normalized


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

# ----------- Coarse Binning: Continuous -----------
def coarse_bin_continuous(df, var, target, bins=10):
    try:
        if var not in df.columns or df[var].isna().all():
            raise ValueError(f"Column '{var}' is missing or contains only NaN values")
        if target not in df.columns:
            raise ValueError(f"Target column '{target}' not found")
        
        # Perform qcut to get bin edges and assign labels
        _, bin_edges = pd.qcut(df[var], q=bins, retbins=True, labels=False, duplicates='drop')
        n_bins = len(bin_edges) - 1
        
        if n_bins <= 0:
            raise ValueError(f"No valid bins could be created for '{var}'.")
        
        bin_labels = [f'Bin_{i}' for i in range(1, n_bins + 1)]
        df[f'{var}_binned'] = pd.cut(df[var], bins=bin_edges, labels=bin_labels, include_lowest=True, right=True)
        
        # Compute actual min and max for each bin based on data
        tab = pd.crosstab(df[f'{var}_binned'], df[target])
        tab.columns = ['Good', 'Bad']
        tab['Total'] = tab['Good'] + tab['Bad']
        tab = tab.reset_index()
        
        # Calculate Min and Max from actual data in each bin
        min_max_values = df.groupby(f'{var}_binned')[var].agg(['min', 'max']).reset_index()
        tab = tab.merge(min_max_values, on=f'{var}_binned', how='left')
        
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
    # 2. SORT CATEGORIES BY NUMERIC PART OF LABEL
    # --------------------------------------------------------------
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
    # 3. CREATE BINS (bad-rate similarity) – keep creation order
    # --------------------------------------------------------------
    bin_mapping = {}
    bin_order = []          # first appearance of each bin
    cur_bin = 1

    if not tab.empty:
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

    bin_ranges = {
        b: _compact([v for v, bid in bin_mapping.items() if bid == b])
        for b in final_tab[f"{var}_binned"]
    }
    if -1 in final_tab[f"{var}_binned"].values:
        bin_ranges[-1] = "Missing / Other"

    final_tab["Range"] = final_tab[f"{var}_binned"].map(bin_ranges)

    # --------------------------------------------------------------
    # 7. TIDY-UP & **SORT BY BIN NUMBER**
    # --------------------------------------------------------------
    final_tab = final_tab.rename(columns={f"{var}_binned": "Bin"})
    final_tab = final_tab[
        ["Bin", "Range", "Good", "Bad", "Total", "Freq%", "Bad Rate"]
    ]

    # Clean integer bins
    final_tab["Bin"] = final_tab["Bin"].apply(
        lambda x: int(x) if isinstance(x, (int, float)) and x == int(x) else str(x)
    )

    # Order: 1, 2, 3, …, -1 (Missing) last
    ordered_bins = [b for b in bin_order if b != -1]
    if -1 in final_tab["Bin"].values:
        ordered_bins.append(-1)

    final_tab["Bin"] = pd.Categorical(
        final_tab["Bin"], categories=ordered_bins, ordered=True
    )
    final_tab = final_tab.sort_values("Bin").reset_index(drop=True)

    # Friendly labels
    label_map = {b: f"Bin {i + 1}" for i, b in enumerate(ordered_bins) if b != -1}
    if -1 in label_map:
        label_map[-1] = "Missing / Other"
    final_tab["Bin"] = final_tab["Bin"].astype(str).map(label_map)

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
    try:
        req = request.get_json()
        print("Received request:", req)
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
        
        try:
            csv_path = get_csv_path(dataset_id)
        except FileNotFoundError as fe:
            return jsonify({"error": str(fe)}), 400
        except Exception as e:
            return jsonify({"error": f"Failed to get CSV path: {str(e)}"}), 400
        
        try:
            df = pd.read_csv(csv_path)
        except FileNotFoundError as fe:
            return jsonify({"error": str(fe)}), 400
        except Exception as e:
            return jsonify({"error": f"Failed to read dataset CSV: {str(e)}"}), 500
        df[target] = df[target].fillna(0).astype(int)

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

        # Ensure feature exists in new schema
        feature = get_feature_by_name(dataset_id, var)
        if not feature:
            fid = create_feature(dataset_id, var, var_type, selected=True)
            feature = get_feature(fid)

        # Ensure coarse binning exists (recompute and save if missing)
        try:
            coarse_step = get_binning_step_by_type(feature['id'], 'coarse')
            if not coarse_step:
                # recompute coarse stats and persist
                if var_type == 'continuous':
                    coarse_stats, _ = coarse_bin_continuous(df, var, target)
                else:
                    coarse_stats, _, _ = coarse_bin_discrete(df, var, target)
                save_coarse_binning_to_db(feature['id'], coarse_stats, var_type)
        except Exception:
            pass

        # Create / update fine binning step
        num_bins = len(tab) if hasattr(tab, 'shape') else (len(tab) if isinstance(tab, list) else 0)
        fine_step_id = create_binning_step(feature_id=feature['id'], step_type='fine', method='merged' if adjusted_merges else 'manual', num_bins=num_bins, iv_value=iv)

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

            bin_label = str(row.get('Bin', f'Bin_{idx+1}'))
            bin_item = {
                'bin_number': idx + 1,
                'bin_label': bin_label,
                'good_count': good,
                'bad_count': bad,
                'total_count': total
            }
            
            # For discrete variables, Range contains the actual values (comma-separated)
            # For continuous variables, use Min/Max to construct range
            if 'Range' in row and row.get('Range'):
                range_val = str(row.get('Range'))
                bin_item['range_text'] = range_val
            elif var_type == 'discrete':
                # For discrete, if no Range, use bin_label as range_text
                bin_item['range_text'] = bin_label
            
            # include range/min/max if present (for continuous)
            if 'Min' in row and row.get('Min') is not None:
                try:
                    bin_item['min_value'] = float(row.get('Min'))
                except Exception:
                    pass
            if 'Max' in row and row.get('Max') is not None:
                try:
                    bin_item['max_value'] = float(row.get('Max'))
                except Exception:
                    pass

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
            create_bins_batch(fine_step_id, bins_data)
            create_binning_totals(binning_step_id=fine_step_id, total_good=int(total_good), total_bad=int(total_bad), total_count=int(total_good + total_bad))

        # Persist merged groups (if any)
        try:
            save_finebin_details_db(int(dataset_id), var, adjusted_merges)
        except Exception:
            pass

        print("Fine binning persisted for", var)
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

# ----------- Automated Monotonic Binning API -----------
@app.route('/api/auto-monotonic-binning', methods=['POST'])
def auto_monotonic_binning_api():
    """
    Automatically merge bins to achieve monotonic WOE (Weight of Evidence).
    Uses deterministic algorithms to find the best bin merging strategy.
    
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
        # Load data
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
        df[target] = df[target].fillna(0).astype(int)
        
        # First perform coarse binning to get initial bins
        if var_type == 'continuous':
            coarse_stats, df[f'{var}_binned'] = coarse_bin_continuous(df, var, target)
        else:
            coarse_stats, df[f'{var}_binned'], bin_mapping = coarse_bin_discrete(df, var, target)
        
        # Extract good/bad counts and bin labels from coarse binning
        bin_labels = []
        good_counts = []
        bad_counts = []
        
        for _, row in coarse_stats.iterrows():
            # Get bin label
            if var_type == 'continuous':
                bin_label = row.get(f'{var}_binned', f'Bin_{len(bin_labels)+1}')
            else:
                bin_label = str(row.get(f'{var}_binned', len(bin_labels)+1))
            
            bin_labels.append(str(bin_label))
            good_counts.append(int(row.get('Good', 0)))
            bad_counts.append(int(row.get('Bad', 0)))
        
        # Convert to numpy arrays
        good = np.array(good_counts)
        bad = np.array(bad_counts)
        
        print(f"Auto-binning for {var}: {len(bin_labels)} bins, direction={direction}, method={method}, prioritize_iv={prioritize_iv}")
        print(f"Initial bins: {bin_labels}")
        print(f"Initial Good: {good}")
        print(f"Initial Bad: {bad}")
        print(f"Initial WOE: {compute_woe(good, bad).tolist()}")
        
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
        
        # Convert merge mapping to format expected by fine_bin API
        # merge_mapping maps new labels to list of original labels
        bin_merges = {}
        for merged_label, original_labels in result['merge_mapping'].items():
            if len(original_labels) > 1:  # Only include actual merges
                bin_merges[merged_label] = original_labels
        
        print(f"Bin merges to apply: {bin_merges}")
        
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
            except Exception:
                dataset_id = latest_ds['id'] if latest_ds else None
        else:
            dataset_id = latest_ds['id'] if latest_ds else None

        if dataset_id is None:
            dataset_id = create_dataset(name='Auto Binning', file_path='', total_features=0, discrete_features=0, continuous_features=0, target_variable=target)

        # Ensure feature exists
        feature = get_feature_by_name(dataset_id, var)
        if not feature:
            fid = create_feature(dataset_id, var, var_type, selected=True)
            feature = get_feature(fid)

        # Ensure coarse saved
        try:
            coarse_step = get_binning_step_by_type(feature['id'], 'coarse')
            if not coarse_step:
                if var_type == 'continuous':
                    coarse_stats, _ = coarse_bin_continuous(df, var, target)
                else:
                    coarse_stats, _, _ = coarse_bin_discrete(df, var, target)
                save_coarse_binning_to_db(feature['id'], coarse_stats, var_type)
        except Exception:
            pass

        # Create/update fine step and persist bins/totals
        num_bins = len(tab) if hasattr(tab, 'shape') else (len(tab) if isinstance(tab, list) else 0)
        fine_step_id = create_binning_step(feature_id=feature['id'], step_type='fine', method='merged' if adjusted_merges else 'auto_monotonic', num_bins=num_bins, iv_value=iv)

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

            bin_label = str(row.get('Bin', f'Bin_{idx+1}'))
            bin_item = {
                'bin_number': idx + 1,
                'bin_label': bin_label,
                'good_count': good,
                'bad_count': bad,
                'total_count': total
            }
            
            # For discrete variables, Range contains the actual values (comma-separated)
            # For continuous variables, use Min/Max to construct range
            if 'Range' in row and row.get('Range'):
                range_val = str(row.get('Range'))
                bin_item['range_text'] = range_val
            elif var_type == 'discrete':
                # For discrete, if no Range, use bin_label as range_text
                bin_item['range_text'] = bin_label
            
            # include range/min/max if present (for continuous)
            if 'Min' in row and row.get('Min') is not None:
                try:
                    bin_item['min_value'] = float(row.get('Min'))
                except Exception:
                    pass
            if 'Max' in row and row.get('Max') is not None:
                try:
                    bin_item['max_value'] = float(row.get('Max'))
                except Exception:
                    pass
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
            create_bins_batch(fine_step_id, bins_data)
            create_binning_totals(binning_step_id=fine_step_id, total_good=int(total_good), total_bad=int(total_bad), total_count=int(total_good + total_bad))

        try:
            save_finebin_details_db(int(dataset_id), var, adjusted_merges)
        except Exception:
            pass

        print(f"Auto-binning persisted for {var}")

        return jsonify({
            "success": True,
            "stats": tab.to_dict(orient='records'),
            "bin_merges": adjusted_merges,
            "is_monotonic": result['is_monotonic'],
            "direction": result['direction'],
            "num_merges": result['num_merges'],
            "num_bins_original": result['num_bins_original'],
            "num_bins_final": result['num_bins_final'],
            "woe_iv": {"iv": iv, "stats": woe_stats}
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
    """
    print("\n[API] /api/univariate-analysis (POST) called")
    try:
        req = request.get_json()
        print(f"[univariate_analysis] discrete={len(req.get('discrete', []))}, continuous={len(req.get('continuous', []))}, target={req.get('target')}")
        discrete_cols = req.get('discrete', [])
        continuous_cols = req.get('continuous', [])
        target = req.get('target')
        record_id = req.get('record_id')  # Optional: for persistence
        
        if not target:
            return jsonify({"error": "Missing required field: target"}), 400
        
        try:
            csv_path = get_csv_path(record_id)
        except FileNotFoundError as fe:
            return jsonify({"error": str(fe)}), 400
        
        try:
            df = pd.read_csv(csv_path)
        except FileNotFoundError as fe:
            return jsonify({"error": str(fe)}), 400
        except Exception as e:
            return jsonify({"error": f"Failed to read dataset CSV: {str(e)}"}), 400
        
        if target not in df.columns:
            return jsonify({"error": f"Target column '{target}' not found in dataset"}), 400
        
        # Convert target to binary 0/1
        try:
            df[target] = pd.to_numeric(df[target], errors='coerce').fillna(0).astype(int)
        except Exception as e:
            return jsonify({"error": f"Failed to convert target to numeric: {str(e)}"}), 400
        
        results = {}
        
        # Process discrete columns
        for col in discrete_cols:
            if col != target and col in df.columns:
                try:
                    stats = None
                    stats_dict = None
                    
                    # Try to retrieve from database if record_id is provided
                    from_db = False
                    if record_id:
                        try:
                            dataset_id = int(record_id)
                        except (ValueError, TypeError):
                            dataset_id = None
                        if dataset_id:
                            feature = get_feature_by_name(dataset_id, col)
                            if feature:
                                # Check if coarse binning already exists
                                coarse_step = get_binning_step_by_type(feature['id'], 'coarse')
                                if coarse_step:
                                    # Data exists in database - retrieve it
                                    bins = get_bins_by_step(coarse_step['id'])
                                    if bins:
                                        stats_dict = [_row_to_native_types(dict(row)) for row in bins]
                                        from_db = True
                                        print(f"[univariate_analysis] ✓ Retrieved discrete from DB: {col} ({len(bins)} bins)")
                    
                    # If not in database, calculate fresh
                    if stats_dict is None:
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
                                if feature:
                                    step_id = save_coarse_binning_to_db(feature['id'], stats, 'discrete')
                                    print(f"[univariate_analysis] 💾 Saved discrete to DB: {col}")
                                    bins = get_bins_by_step(step_id)
                                    stats_dict = [_row_to_native_types(dict(row)) for row in bins]
                        if stats_dict is None:
                            stats_dict = stats.to_dict(orient='records')
                    
                    results[col] = {
                        'type': 'discrete',
                        'stats': stats_dict,
                        'from_db': from_db  # Indicate if data was retrieved from DB
                    }
                except Exception as e:
                    print(f"[univariate_analysis] Error processing discrete column {col}: {e}")
                    results[col] = {'type': 'discrete', 'error': str(e)}
        
        # Process continuous columns
        for col in continuous_cols:
            if col != target and col in df.columns:
                try:
                    stats = None
                    stats_dict = None
                    
                    # Try to retrieve from database if record_id is provided
                    from_db = False
                    if record_id:
                        try:
                            dataset_id = int(record_id)
                        except (ValueError, TypeError):
                            dataset_id = None
                        if dataset_id:
                            feature = get_feature_by_name(dataset_id, col)
                            if feature:
                                # Check if coarse binning already exists
                                coarse_step = get_binning_step_by_type(feature['id'], 'coarse')
                                if coarse_step:
                                    # Data exists in database - retrieve it
                                    bins = get_bins_by_step(coarse_step['id'])
                                    if bins:
                                        stats_dict = [_row_to_native_types(dict(row)) for row in bins]
                                        from_db = True
                                        print(f"[univariate_analysis] ✓ Retrieved continuous from DB: {col} ({len(bins)} bins)")
                    
                    # If not in database, calculate fresh
                    if stats_dict is None:
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
                                if feature:
                                    step_id = save_coarse_binning_to_db(feature['id'], stats, 'continuous')
                                    print(f"[univariate_analysis] 💾 Saved continuous to DB: {col}")
                                    bins = get_bins_by_step(step_id)
                                    stats_dict = [_row_to_native_types(dict(row)) for row in bins]
                        if stats_dict is None:
                            stats_dict = stats.to_dict(orient='records')
                    
                    results[col] = {
                        'type': 'continuous',
                        'stats': stats_dict,
                        'from_db': from_db  # Indicate if data was retrieved from DB
                    }
                except Exception as e:
                    print(f"[univariate_analysis] Error processing continuous column {col}: {e}")
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
        
        # Load data and perform coarse binning
        try:
            csv_path = get_csv_path(record_id)
        except FileNotFoundError as fe:
            return jsonify({"error": str(fe)}), 400
        try:
            df = pd.read_csv(csv_path)
        except FileNotFoundError as fe:
            return jsonify({"error": str(fe)}), 400
        except Exception as e:
            return jsonify({"error": f"Failed to read dataset CSV: {str(e)}"}), 400
        
        if target not in df.columns:
            return jsonify({"error": f"Target column '{target}' not found in dataset"}), 400
        
        df[target] = df[target].fillna(0).astype(int)
        
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
        
        # Return the coarse bins for frontend display
        return jsonify({
            "success": True,
            "stats": coarse_stats.to_dict(orient='records')
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
        if not samples:
            return 'discrete' # Default to discrete when no data

        try:
            is_numeric = all(isinstance(x, (int, float)) for x in samples)
            
            if not is_numeric:
                return 'discrete' # Text/Categorical data

            # Check for presence of non-integer/float values
            has_float = any(isinstance(x, float) and not x.is_integer() for x in samples)
            if has_float:
                return 'continuous' # Presence of decimals strongly suggests measurement/continuous

            # Check cardinality for numeric data (e.g., binary or few levels)
            unique_values = len(set(samples))
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

        # Calculate percentages from ACTUAL BINNED TOTALS
        dist_good_pct = (g / total_good * 100.0) if total_good > 0 else 0.0
        dist_bad_pct = (b / total_bad * 100.0) if total_bad > 0 else 0.0

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
        if dist_good_pct > 0.0 and dist_bad_pct > 0.0:
            try:
                ratio = dist_good_pct / dist_bad_pct
                ln_ratio = math.log(ratio)
                if math.isfinite(ln_ratio):
                    # WOE = ROUND(LN(L5/M5) * 100, 1)
                    woe_val = round(ln_ratio * 100.0, 1)
                
                    iv_val = (dist_good_pct - dist_bad_pct) * ln_ratio 
                else:
                    woe_val = 0.0
                    iv_val = 0.0
            except (ValueError, ZeroDivisionError):
                woe_val = 0.0
                iv_val = 0.0
        else:
            # No smoothing - return 0 if either percentage is zero
            woe_val = 0.0
            iv_val = 0.0

        # Accumulate total IV
        if math.isfinite(iv_val):
            iv_total += float(iv_val)/100 # since iv_val is in percentage terms

        bin_label = str(row["final_bin"])
        range_info = bin_ranges.get(bin_label, (None, None) if var_type == "continuous" else [])
        range_str = (f"{range_info[0]} - {range_info[1]}" if var_type == "continuous"
                     else ', '.join(map(str, range_info)))

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
        
        try:
            csv_path = get_csv_path(record_id)
        except FileNotFoundError as fe:
            return jsonify({"error": str(fe)}), 400
        
        try:
            df = pd.read_csv(csv_path)
        except FileNotFoundError as fe:
            return jsonify({"error": str(fe)}), 400
        except Exception as e:
            return jsonify({"error": f"Failed to read dataset CSV: {str(e)}"}), 400
        
        if target not in df.columns:
            return jsonify({"error": f"Target column '{target}' not found in dataset"}), 400
        
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
        for var in variables:
            var_series = df[var]
            is_likely_id = any(k in var.lower() for k in ['id', 'key', 'code', 'no', 'num'])
            unique_cnt = var_series.nunique(dropna=True)

            # Use fresh data copy for each variable
            temp_df = df.copy()
            
            if pd.api.types.is_numeric_dtype(var_series):
                if is_likely_id or unique_cnt <= 50:
                    try:
                        _, temp_df[f"{var}_binned"], _ = coarse_bin_discrete(temp_df, var, target)
                        print(f"WOE/IV DEBUG: Created discrete bins for {var} (numeric with {unique_cnt} unique values)")
                    except Exception as e:
                        print(f"WOE/IV DEBUG: Failed to create discrete bins for {var}: {e}")
                        continue
                else:
                    try:
                        _, temp_df[f"{var}_binned"] = coarse_bin_continuous(temp_df, var, target)
                        print(f"WOE/IV DEBUG: Created continuous bins for {var} (numeric with {unique_cnt} unique values)")
                    except Exception as e:
                        print(f"WOE/IV DEBUG: Failed to create continuous bins for {var}: {e}")
                        continue
            else:
                try:
                    _, temp_df[f"{var}_binned"], _ = coarse_bin_discrete(temp_df, var, target)
                    print(f"WOE/IV DEBUG: Created discrete bins for {var} (non-numeric)")
                except Exception as e:
                    print(f"WOE/IV DEBUG: Failed to create discrete bins for {var}: {e}")
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
                            range_text = s.get('Range') if s.get('Range') is not None else s.get('range', None)
                            min_value = None
                            max_value = None
                            # Attempt to parse continuous range like 'min - max'
                            if isinstance(range_text, str) and '-' in range_text and any(ch.isdigit() for ch in range_text):
                                parts = [p.strip() for p in range_text.split('-', 1)]
                                try:
                                    min_value = float(parts[0])
                                    max_value = float(parts[1])
                                except Exception:
                                    min_value = None
                                    max_value = None

                            freq_percent = (total / total_all) * 100 if total_all > 0 else None
                            odds = (good / bad) if bad > 0 else None
                            good_bad_ratio = odds
                            # CRITICAL FIX: Calculate bad_rate (percentage of bad cases in this bin)
                            bad_rate = (bad / total) * 100 if total > 0 else None
                            try:
                                index_value = ( (dist_good / dist_bad) * 100 ) if (dist_bad and dist_bad > 0) else None
                            except Exception:
                                index_value = None
                            try:
                                odds_index = ( (odds / overall_odds) * 100 ) if (odds is not None and overall_odds and overall_odds > 0) else None
                            except Exception:
                                odds_index = None

                            bin_entry = {
                                'bin_number': bin_number,
                                'bin_label': bin_label,
                                'min_value': min_value,
                                'max_value': max_value,
                                'range_text': range_text,
                                'good_count': good,
                                'bad_count': bad,
                                'total_count': total,
                                'dist_good': dist_good,
                                'dist_bad': dist_bad,
                                'woe': woe,
                                'iv': iv_bin,
                                'freq_percent': freq_percent,
                                'odds': odds,
                                'good_bad_ratio': good_bad_ratio,
                                'bad_rate': bad_rate,
                                'index_value': index_value,
                                'odds_index': odds_index
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
        for col in all_columns:
            if col not in existing_feature_names:
                var_type = 'discrete' if col in discrete_columns else 'continuous'
                is_selected = col in selected_columns
                create_feature(
                    dataset_id=dataset_id,
                    name=col,
                    feature_type=var_type,
                    selected=is_selected
                )
        
        # Update existing features (type and selection)
        for feature in existing_features:
            if feature['name'] in all_columns:
                new_type = 'discrete' if feature['name'] in discrete_columns else 'continuous'
                is_selected = feature['name'] in selected_columns
                if feature['type'] != new_type or feature['selected'] != is_selected:
                    update_feature(feature['id'], type=new_type, selected=is_selected)
        
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
        
        return jsonify({"success": True, "id": dataset_id})
    except Exception as e:
        print(f"[upsert_single_record] ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/api/update-feature-modeling', methods=['POST'])
def update_feature_modeling():
    """
    Update feature's model_ready and is_monotonic when checkbox is checked in Column Selection & Binning.
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
        
        # Update model_ready (handle gracefully if column doesn't exist)
        try:
            update_feature(feature['id'], model_ready=is_selected)
        except Exception as e:
            if 'model_ready' in str(e).lower() or 'does not exist' in str(e).lower():
                # Column doesn't exist, try to add it
                try:
                    ensure_model_ready_column()
                    update_feature(feature['id'], model_ready=is_selected)
                except Exception as e2:
                    print(f"[update_feature_modeling] Could not update model_ready: {e2}")
            else:
                raise
        
        # Update is_monotonic in the latest binning step (prefer fine, fallback to coarse)
        # Only set to True when selected, don't set to False when deselected (preserve existing state)
        if is_selected:
            fine_step = get_binning_step_by_type(feature['id'], 'fine')
            if fine_step:
                update_binning_step(fine_step['id'], is_monotonic=True)
            else:
                coarse_step = get_binning_step_by_type(feature['id'], 'coarse')
                if coarse_step:
                    update_binning_step(coarse_step['id'], is_monotonic=True)
        
        return jsonify({"success": True})
    except Exception as e:
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
    """Get all features for a dataset with their model_ready and final_selected status."""
    try:
        features = get_features_by_dataset(dataset_id)
        return jsonify(features)
    except Exception as e:
        print(f"[get_dataset_features] ERROR: {str(e)}")
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
                feature_binning['coarse'] = {
                    'type': feature.get('type'),
                    'bins': coarse.get('bins', [])
                }
            if fine:
                feature_binning['fine'] = {
                    'bins': fine.get('bins', []),
                    'merged_bins': fine.get('merged_bins', []),
                    'iv': fine.get('iv')
                }
            
            woe_source = fine if fine else coarse
            step_meta = (woe_source or {}).get('step')
            if step_meta and step_meta.get('iv_value') is not None:
                feature_binning['woe_iv'] = {
                    'iv': float(step_meta['iv_value']),
                    'bins': (woe_source or {}).get('bins', [])
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
            'final_selected_columns': final_selected_cols
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
        dataset_id = (
            data.get('record_id')
            or data.get('dataset_id')
            or data.get('recordId')
            or data.get('datasetId')
        )
        dataset_id = (
            data.get('record_id')
            or data.get('dataset_id')
            or data.get('recordId')
            or data.get('datasetId')
        )
        dataset_id = (
            data.get('record_id')
            or data.get('dataset_id')
            or data.get('recordId')
            or data.get('datasetId')
        )

        if not selected_variables or not target:
            return jsonify({"error": "Missing selected_variables or target"}), 400

        # Load CSV into df at the very start
        try:
            df = pd.read_csv(get_csv_path(dataset_id))
        except Exception as e:
            return jsonify({"error": f"Failed to load CSV: {str(e)}"}), 400

        if target not in df.columns:
            return jsonify({"error": f"Target variable '{target}' not found in dataset"}), 400

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
            print("LOGISTIC DEBUG: X sample rows:", sample)
            print(f"LOGISTIC DEBUG: Final rank check - Rank: {rank}, Full: {full_rank}")
        except Exception as _diag:
            print("LOGISTIC DEBUG: diagnostics failed:", str(_diag))

        # Warn if too many variables relative to observations
        n_features = len(selected_variables)
        n_obs = len(X)
        if n_features > n_obs / 10:  # Stricter: 10 obs per feature
            print(f"LOGISTIC DEBUG: Warning - Very high dimensionality: {n_features} features vs {n_obs} observations. Model may be unstable.")

        # Now fit the model with robust optimizer
        logit_model = sm.Logit(y, X_const)
        result = None
        methods_to_try = ['bfgs', 'newton', 'nm']  # Fallback optimizers
        for method in methods_to_try:
            try:
                print(f"LOGISTIC DEBUG: Trying fit with method='{method}'")
                result = logit_model.fit(disp=0, method=method, maxiter=1000)
                print(f"LOGISTIC DEBUG: Fit succeeded with {method}")
                break
            except Exception as fit_err:
                print(f"LOGISTIC DEBUG: Fit failed with {method}: {fit_err}")
                if method == methods_to_try[-1]:  # Last one
                    return jsonify({"error": f"Model fitting failed with all optimizers due to data issues (e.g., perfect separation). Try fewer variables. Error: {str(fit_err)}"}), 400
                continue

        if result is None:
            return jsonify({"error": "Model fitting failed unexpectedly."}), 500

        # VIF on final model
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

        y_pred_proba = result.predict(X_const)
        fpr, tpr, thresholds = roc_curve(y, y_pred_proba)
        roc_auc = auc(fpr, tpr)
        gini_coefficient = 2 * roc_auc - 1

        try:
            y_pred = (y_pred_proba >= 0.5).astype(int)
        except Exception:
            y_pred = (np.array(y_pred_proba) >= 0.5).astype(int)

        try:
            cm = confusion_matrix(y, y_pred)
            accuracy = accuracy_score(y, y_pred)
            precision = precision_score(y, y_pred, zero_division=0)
            recall = recall_score(y, y_pred, zero_division=0)
            f1 = f1_score(y, y_pred, zero_division=0)
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

        roc_data = [{'fpr': _sanitize_number(f), 'tpr': _sanitize_number(t), 'threshold': _sanitize_number(th)}
                    for f, t, th in zip(fpr, tpr, thresholds)]

        try:
            diffs = [abs(t - f) for f, t in zip(fpr, tpr)]
            ks_idx = int(np.argmax(diffs)) if len(diffs) > 0 else 0
            ks_stat_raw = diffs[ks_idx] if len(diffs) > 0 else 0.0
            ks_threshold_raw = thresholds[ks_idx] if len(thresholds) > 0 else 0.0
            ks_stat = float(ks_stat_raw) if np.isfinite(ks_stat_raw) else None
            ks_threshold = float(ks_threshold_raw) if np.isfinite(ks_threshold_raw) else None
            ks_curve = []
            for f, t, th in zip(fpr, tpr, thresholds):
                ks_curve.append({'threshold': _sanitize_number(th), 'tpr': _sanitize_number(t), 'fpr': _sanitize_number(f), 'diff': _sanitize_number(abs(t - f))})
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
            'n_observations': int(result.nobs)
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

        # Train Random Forest
        rf_model = RandomForestClassifier(
            n_estimators=100,
            max_depth=10,
            min_samples_split=5,
            min_samples_leaf=2,
            random_state=42,
            n_jobs=-1
        )
        
        rf_model.fit(X, y)
        y_pred_proba = rf_model.predict_proba(X)[:, 1]
        y_pred = rf_model.predict(X)

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
                'importance': float(rf_model.feature_importances_[i]),
                'importance_percentage': float(rf_model.feature_importances_[i] * 100)
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
            'n_observations': len(X),
            'n_features': len(woe_columns),
            'oob_score': float(getattr(rf_model, 'oob_score_', 0)) if hasattr(rf_model, 'oob_score_') else None
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

        return jsonify(resp)

    except Exception as e:
        print(f"RANDOM FOREST ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Failed to perform Random Forest analysis: {str(e)}"}), 500

# ----------- XGBoost Analysis -----------
@app.route('/api/xgboost', methods=['POST'])
def xgboost_analysis():
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
        
        for var in selected_variables:
            if var not in df.columns:
                print(f"XGB DEBUG: Variable '{var}' not found in dataset columns")
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

        print(f"XGB DEBUG: Final features: {woe_columns}")
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

        return jsonify(resp)

    except Exception as e:
        print(f"XGBOOST ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Failed to perform XGBoost analysis: {str(e)}"}), 500
        
# Helper function for WOE mapping (used by all models)
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
                            original_bin_labels.append(coarse_bins[idx_int].get('bin_label', f'Bin_{idx_int}'))
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
        # Create mappings: bin_id -> bin_label
        bin_id_to_label = {bin_data['id']: bin_data.get('bin_label', f"Bin_{bin_data.get('bin_number', 0)}") for bin_data in coarse_bins}
        
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
                bin_labels = [bin_id_to_label.get(bid, f"Bin_{bid}") for bid in original_ids]
            
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
    Used to hydrate manual binning UI and the new Full Auto Monotonic mode.
    """
    print(f"\n[API] /api/finebin-cache/{record_id}/{column_name} (GET) called")
    try:
        dataset_id = record_id
        feature = get_feature_by_name(dataset_id, column_name)
        if not feature:
            return jsonify({"success": False, "reason": "feature_not_found"})

        fine_step = get_binning_step_by_type(feature['id'], 'fine')
        if not fine_step:
            return jsonify({"success": False, "reason": "fine_step_missing"})

        fine_step_id = fine_step['id']
        bins = get_bins_by_step(fine_step_id)
        if not bins:
            return jsonify({"success": False, "reason": "no_bins"})

        merged_bins = get_merged_bins_by_step(fine_step_id) or []
        totals = get_binning_totals(fine_step_id)

        def _safe_float(value):
            if value is None:
                return None
            try:
                return float(value)
            except (TypeError, ValueError):
                return value

        stats = []
        for row in bins:
            label = row.get('bin_label')
            if not label:
                bin_number = row.get('bin_number')
                label = f"Bin_{bin_number}" if bin_number is not None else str(row.get('id', ''))
            stats.append({
                'Bin': label,
                'Range': row.get('range_text'),
                'Good': int(row.get('good_count') or 0),
                'Bad': int(row.get('bad_count') or 0),
                'Total': int(row.get('total_count') or 0),
                'Bad Rate': _safe_float(row.get('bad_rate')),
                'Freq%': _safe_float(row.get('freq_percent')),
                'WOE': _safe_float(row.get('woe')),
                'IV': _safe_float(row.get('iv')),
                'Min': _safe_float(row.get('min_value')),
                'Max': _safe_float(row.get('max_value')),
            })

        merges_map = {}
        for merged in merged_bins:
            key = str(merged.get('merged_bin_number'))
            labels = merged.get('original_bin_labels')
            if not labels:
                ids = merged.get('original_bin_ids') or []
                labels = [f"Bin_{bid}" for bid in ids]
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

        # Load dataset
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

        # Validate columns
        if target not in df.columns:
            return jsonify({"error": f"Target column '{target}' not found in dataset"}), 400
        missing_vars = [var for var in selected_variables if var not in df.columns]
        if missing_vars:
            return jsonify({"error": f"Variables not found in dataset: {missing_vars}"}), 400
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
        model_df = pd.DataFrame(modeling_data)
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

        # Score card parameters - adjust for different model types
        N = len(selected_variables)
        
        # Adjust parameters based on model type
        if model_type == 'logistic':
            factor = 20 / np.log(2)  # ≈ 28.8539 (standard logistic scoring)
            base_odds = 50
            base_score = 600
            offset = base_score - factor * np.log(base_odds)  # ≈ 427.432
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

        if target not in df.columns:
            return jsonify({"error": f"Target column '{target}' not found in dataset"}), 400

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
            
            if woe_mapping:
                woe_column = [woe_mapping.get(i, 0) for i in range(len(df))]
                modeling_data[var] = woe_column
            else:
                modeling_data[var] = [0] * len(df)

        # Create DataFrame with WOE-transformed variables
        model_df = pd.DataFrame(modeling_data)
        model_df[target] = pd.to_numeric(df[target], errors='coerce').fillna(0).astype(int)

        # Remove rows with missing target
        mask = ~model_df[target].isna()
        X = model_df[selected_variables]
        y = model_df[target][mask]
        X = X[mask]

        if len(X) == 0:
            return jsonify({"error": "No valid data after preprocessing"}), 400

        # Calculate scores based on model type
        scores = []
        
        if model_type == 'logistic' and model_results:
            # Use logistic regression coefficients
            coefficients = {}
            intercept = 0
            
            if 'coefficients' in model_results:
                for coef_info in model_results['coefficients']:
                    var_name = coef_info.get('variable')
                    if var_name and var_name != 'Intercept':
                        coefficients[var_name] = coef_info.get('coefficient', 0)
                    elif var_name == 'Intercept':
                        intercept = coef_info.get('coefficient', 0)
            
            # Score card parameters for logistic regression
            N = len(selected_variables)
            factor = 20 / np.log(2)  # ≈ 28.8539
            base_odds = 50
            base_score = 600
            offset = base_score - factor * np.log(base_odds)  # ≈ 427.432

            # FIXED: Use NEGATIVE coefficients so higher risk = lower score
            for idx in range(len(X)):
                score = 0
                for var in selected_variables:
                    beta = coefficients.get(var, 0)
                    woe = X.iloc[idx][var] if var in X.columns else 0
                    # FIX: Use NEGATIVE beta to ensure higher risk = lower score
                    score += (-beta * woe + intercept / N) * factor + offset / N
                scores.append(round(float(score), 2))
                
        elif model_type in ['random_forest', 'xgboost'] and model_results:
            # For tree-based models, use the actual model predictions
            try:
                if model_type == 'random_forest':
                    from sklearn.ensemble import RandomForestClassifier
                    # Recreate the Random Forest model with the same parameters
                    rf_model = RandomForestClassifier(
                        n_estimators=model_results.get('model_stats', {}).get('n_estimators', 100),
                        max_depth=model_results.get('model_stats', {}).get('max_depth', 10),
                        random_state=42,
                        n_jobs=-1
                    )
                    rf_model.fit(X, y)
                    # Get probability of being BAD (class 1)
                    y_pred_proba_bad = rf_model.predict_proba(X)[:, 1]
                    
                elif model_type == 'xgboost':
                    import xgboost as xgb
                    # Recreate the XGBoost model with the same parameters
                    xgb_model = xgb.XGBClassifier(
                        n_estimators=model_results.get('model_stats', {}).get('n_estimators', 100),
                        max_depth=model_results.get('model_stats', {}).get('max_depth', 6),
                        learning_rate=model_results.get('model_stats', {}).get('learning_rate', 0.1),
                        random_state=42
                    )
                    xgb_model.fit(X, y)
                    # Get probability of being BAD (class 1)
                    y_pred_proba_bad = xgb_model.predict_proba(X)[:, 1]
                
                # FIXED: Convert BAD probabilities to scores where higher risk = lower score
                min_score = 300
                max_score = 850
                
                # FIX: Higher bad probability = Lower score
                # Use inverse relationship: score = max_score - (bad_probability * score_range)
                score_range = max_score - min_score
                scores = max_score - (y_pred_proba_bad * score_range)
                
                scores = [round(float(score), 2) for score in scores]
                
                print(f"DEBUG: Tree model scoring - Bad probabilities range: {np.min(y_pred_proba_bad):.4f} to {np.max(y_pred_proba_bad):.4f}")
                print(f"DEBUG: Tree model scoring - Scores range: {np.min(scores):.2f} to {np.max(scores):.2f}")
                
            except Exception as model_err:
                print(f"DEBUG: Tree model scoring failed: {model_err}")
                # Fallback: use feature importance-based scoring with proper direction
                if 'feature_importance' in model_results:
                    coefficients = {}
                    for feature_info in model_results['feature_importance']:
                        var_name = feature_info.get('variable')
                        importance = feature_info.get('importance', 0)
                        coefficients[var_name] = importance * 100  # Scale factor
                    
                    # FIXED: Simple additive scoring with proper direction
                    for idx in range(len(X)):
                        score = 600  # Base score
                        for var in selected_variables:
                            beta = coefficients.get(var, 0)
                            woe = X.iloc[idx][var] if var in X.columns else 0
                            # FIX: Use negative relationship for risk factors
                            score -= beta * woe
                        scores.append(round(float(score), 2))
                else:
                    return jsonify({"error": f"Failed to calculate scores for {model_type}: {str(model_err)}"}), 500
        else:
            return jsonify({"error": f"Unsupported model type or missing model results: {model_type}"}), 400

        # Prepare results
        results_list = []
        y_true = y.tolist()
        y_score = scores
        
        for idx, score in enumerate(scores):
            results_list.append({
                "index": int(X.index[idx]) if hasattr(X, 'index') else idx,
                "score": score,
                "target": int(y_true[idx])
            })
        
        # Sort descending by score (HIGHEST scores first = LOWEST risk first)
        results_list = sorted(results_list, key=lambda x: x["score"], reverse=True)

        # Calculate KS statistic (separation number)
        try:
            from sklearn.metrics import roc_curve
            fpr, tpr, thresholds = roc_curve(y_true, y_score)
            diffs = np.abs(tpr - fpr)
            ks_stat = float(np.max(diffs)) if len(diffs) > 0 else 0.0
            
            # Get KS threshold
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
            
            # ROC AUC
            roc_auc = auc(fpr, tpr) if 'fpr' in locals() and 'tpr' in locals() else 0.0
            
            # For credit scoring, we typically use a different threshold than 0.5
            # Since scores are now properly scaled, we can use a score threshold
            score_threshold = np.percentile(scores, 50)  # Median score as threshold
            y_pred = [1 if score < score_threshold else 0 for score in scores]  # Lower score = higher risk = predicted bad
            
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

        return jsonify({
            "success": True, 
            "results": results_list, 
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
            "score_range": {
                "min": float(np.min(scores)) if len(scores) > 0 else 0,
                "max": float(np.max(scores)) if len(scores) > 0 else 0,
                "mean": float(np.mean(scores)) if len(scores) > 0 else 0
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
