"""
Flask Backend for Automated Credit Scoring Application
Fully migrated to use the new normalized database schema (db.py)
NO dependencies on db_old.py or old JSON-based storage
"""

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

# Import ONLY new database layer functions
from db import (
    get_db_connection, init_db,
    # Dataset operations
    create_dataset, get_dataset, get_all_datasets, get_latest_dataset, update_dataset, delete_dataset,
    # Feature operations
    create_feature, create_features_batch, get_feature, get_features_by_dataset, 
    get_feature_by_name, update_feature, update_features_selection,
    # Binning step operations
    create_binning_step, get_binning_step, get_binning_steps_by_feature, 
    get_binning_step_by_type, delete_binning_step,
    # Bin operations
    create_bin, create_bins_batch, get_bins_by_step, get_bin,
    # Merged bins operations
    create_merged_bin, get_merged_bins_by_step,
    # Binning totals operations
    create_binning_totals, get_binning_totals, get_all_binning_totals_by_dataset,
    # Helper functions
    get_complete_binning_results, get_dataset_with_all_results, delete_all_binning_for_feature
)
import traceback
import logging
from auto_monotonic_binning import auto_monotonic_binning, compute_woe, compute_iv

# Optional: load environment variables from a .env file if present
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()
except Exception:
    pass

# configure basic logging for debug
logging.basicConfig(level=logging.DEBUG)

app = Flask(__name__)
CORS(app, origins=["http://localhost:5173"])

# =====================================================================
# HELPER FUNCTIONS
# =====================================================================

def get_csv_path():
    """Returns the absolute path to the most recent uploaded CSV file."""
    try:
        dataset = get_latest_dataset()
        if dataset and dataset.get('file_path'):
            candidate = os.path.join(os.path.dirname(__file__), dataset.get('file_path'))
            if os.path.exists(candidate):
                return candidate
            fp = dataset.get('file_path')
            if fp and os.path.isabs(fp) and os.path.exists(fp):
                return fp
    except Exception:
        pass
    # Fallback to uploaded.csv
    return os.path.join(os.path.dirname(__file__), "uploaded.csv")


def safe_save_csv(df, max_retries=3):
    """Safely saves DataFrame to CSV with retry logic for Windows permission issues."""
    csv_path = get_csv_path()
    import time
    for attempt in range(max_retries):
        try:
            df.to_csv(csv_path, index=False)
            return True
        except PermissionError as e:
            if attempt < max_retries - 1:
                time.sleep(0.1)
            else:
                raise e
    return False


def format_dataset_to_record(dataset_dict):
    """
    Convert a dataset dictionary (from new schema) to the old record format
    for backward compatibility with frontend expectations.
    """
    features = get_features_by_dataset(dataset_dict['id'])
    
    discrete_cols = [f['name'] for f in features if f.get('type') == 'discrete']
    continuous_cols = [f['name'] for f in features if f.get('type') == 'continuous']
    selected_cols = [f['name'] for f in features if f.get('selected') is True]
    
    # Build univariate_results from binning_steps (coarse binning)
    univariate_results = {}
    for feature in features:
        coarse_step = get_binning_step_by_type(feature['id'], 'coarse')
        if coarse_step:
            bins = get_bins_by_step(coarse_step['id'])
            univariate_results[feature['name']] = {
                'type': feature['type'],
                'stats': [format_bin_to_dict(b) for b in bins]
            }
    
    # Build finebin_results from binning_steps (fine binning)
    finebin_results = {}
    for feature in features:
        fine_step = get_binning_step_by_type(feature['id'], 'fine')
        if fine_step:
            bins = get_bins_by_step(fine_step['id'])
            finebin_results[feature['name']] = [format_bin_to_dict(b) for b in bins]
    
    # Build woe_iv_results from binning_steps (IV values)
    woe_iv_results = {}
    for feature in features:
        # Use fine binning if available, otherwise coarse
        fine_step = get_binning_step_by_type(feature['id'], 'fine')
        step = fine_step if fine_step else get_binning_step_by_type(feature['id'], 'coarse')
        if step and step.get('iv_value') is not None:
            bins = get_bins_by_step(step['id'])
            woe_iv_results[feature['name']] = {
                'iv': float(step['iv_value']),
                'stats': [format_bin_to_woe_dict(b) for b in bins]
            }
    
    return {
        'id': dataset_dict['id'],
        'dataset_path': dataset_dict.get('file_path', ''),
        'discrete_columns': discrete_cols,
        'continuous_columns': continuous_cols,
        'selected_columns': selected_cols,
        'dashboard_selected_columns': selected_cols,  # Same as selected for now
        'target_variable': dataset_dict.get('target_variable', ''),
        'created_at': dataset_dict.get('created_at', ''),
        # Return structured objects (do NOT serialize to JSON strings)
        'univariate_results': univariate_results,
        'finebin_results': finebin_results,
        'crosstab_results': [],  # Not used in new schema
        'woe_iv_results': woe_iv_results
    }


def format_bin_to_dict(bin_record):
    """Convert a bin database record to dictionary format expected by frontend."""
    result = {
        'Bin': bin_record.get('bin_label', ''),
        'Good': bin_record.get('good_count', 0),
        'Bad': bin_record.get('bad_count', 0),
        'Total': bin_record.get('total_count', 0)
    }
    
    # Add Min/Max for continuous, Range for discrete
    if bin_record.get('min_value') is not None:
        result['Min'] = bin_record['min_value']
    if bin_record.get('max_value') is not None:
        result['Max'] = bin_record['max_value']
    if bin_record.get('range_text'):
        result['Range'] = bin_record['range_text']
    
    return result


def format_bin_to_woe_dict(bin_record):
    """Convert a bin database record to WOE/IV format."""
    return {
        'Bin': bin_record.get('bin_label', ''),
        'Good': bin_record.get('good_count', 0),
        'Bad': bin_record.get('bad_count', 0),
        'Total': bin_record.get('total_count', 0),
        'Dist_Good_%': bin_record.get('dist_good', 0),
        'Dist_Bad_%': bin_record.get('dist_bad', 0),
        'WOE': bin_record.get('woe', 0),
        'IV': bin_record.get('iv', 0),
        'Range': bin_record.get('range_text', bin_record.get('bin_label', ''))
    }


# =====================================================================
# BASIC API ENDPOINTS
# =====================================================================

@app.route('/api/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({"status": "OK", "time": str(datetime.datetime.now())})


@app.route('/api/db-health', methods=['GET'])
def db_health():
    """Database connectivity check."""
    try:
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


@app.route('/api/uploaded-csv-columns', methods=['GET'])
def get_uploaded_csv_columns():
    """Returns the column headers from the uploaded CSV file."""
    try:
        csv_path = get_csv_path()
        df = pd.read_csv(csv_path, nrows=0)
        return jsonify({"columns": df.columns.tolist()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# =====================================================================
# CSV UPLOAD & DATASET MANAGEMENT
# =====================================================================

@app.route('/api/upload-csv', methods=['POST'])
def upload_csv():
    """
    Handles CSV file uploads, saves the file, creates dataset and feature records.
    Returns dataset_id and column information.
    """
    if 'file' not in request.files:
        return jsonify({"error": "No file part in the request"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400
    if file and file.filename.endswith('.csv'):
        try:
            df = pd.read_csv(file)
            if df.empty:
                return jsonify({"error": "Uploaded CSV is empty"}), 400

            ts_fname = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            timestamp = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

            # Save to uploads folder
            uploads_dir = os.path.join(os.path.dirname(__file__), "uploads")
            os.makedirs(uploads_dir, exist_ok=True)
            original_name = secure_filename(file.filename)
            base, ext = os.path.splitext(original_name)
            timestamped_name = f"{base}_{ts_fname}{ext}"
            save_path = os.path.join(uploads_dir, timestamped_name)
            df.to_csv(save_path, index=False)

            # Create dataset record
            dataset_name = file.filename.replace('.csv', '')
            rel_path = os.path.join('uploads', timestamped_name)
            
            dataset_id = create_dataset(
                name=f"{dataset_name}_{timestamp}",
                file_path=rel_path,
                total_features=len(df.columns),
                discrete_features=0,
                continuous_features=0,
                target_variable=None
            )
            
            # Create feature records for all columns
            features_data = [
                {
                    'name': col,
                    'type': 'continuous',  # Default, will be updated
                    'selected': False
                }
                for col in df.columns
            ]
            create_features_batch(dataset_id, features_data)
            
            return jsonify({
                "success": True,
                "dataset_id": dataset_id,
                "columns": df.columns.tolist(),
                "rowCount": len(df),
                "timestamp": timestamp,
                "dataset_path": rel_path,
                "resolved_path": save_path
            })
        except Exception as e:
            return jsonify({"error": f"Failed to process CSV: {str(e)}"}), 500
    return jsonify({"error": "File must be a CSV"}), 400


@app.route('/api/target-distribution', methods=['POST'])
def target_distribution():
    """Computes and returns the value counts for a specified target column."""
    try:
        csv_path = get_csv_path()
        df = pd.read_csv(csv_path)
        data = request.get_json()
        col = data.get('column')
        if not col or col not in df.columns:
            return jsonify({"error": f"Column '{col}' not found in dataset"}), 400
        counts = df[col].value_counts().to_dict()
        return jsonify(counts)
    except Exception as e:
        return jsonify({"error": f"Failed to compute target distribution: {str(e)}"}), 500


# =====================================================================
# RECORDS/DATASETS MANAGEMENT
# =====================================================================

@app.route('/api/records', methods=['GET'])
def get_records():
    """
    List all analysis records (datasets) - now fetches from datasets table.
    Returns data in old format for frontend compatibility.
    """
    try:
        datasets = get_all_datasets()
        records = [format_dataset_to_record(d) for d in datasets]
        return jsonify(records)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route('/api/record/<int:record_id>', methods=['GET'])
def get_record(record_id):
    """
    Get a specific analysis record (full details).
    Converts dataset to old record format for compatibility.
    """
    try:
        dataset = get_dataset(record_id)
        if dataset:
            record = format_dataset_to_record(dataset)
            return jsonify(record)
        return jsonify({"error": "Record not found"}), 404
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route('/api/record/<int:record_id>', methods=['DELETE'])
def delete_record(record_id):
    """
    Delete a specific analysis record/dataset by ID.
    Cascade delete handles related features, binning_steps, bins, etc.
    """
    try:
        dataset = get_dataset(record_id)
        if dataset:
            delete_dataset(record_id)
            return jsonify({"success": True})
        return jsonify({"error": "Record/Dataset not found"}), 404
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route('/api/record/<int:record_id>/load-dataset', methods=['GET'])
def load_record_dataset(record_id):
    """Loads the dataset for a given record and returns it as JSON."""
    try:
        dataset = get_dataset(record_id)
        if not dataset:
            return jsonify({"error": "Dataset not found"}), 404
            
        dataset_path = dataset.get('file_path')
        if not dataset_path:
            return jsonify({"error": "No dataset_path available"}), 404

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


@app.route('/api/latest-record-dataset-path', methods=['GET'])
def latest_record_dataset_path():
    """Returns the dataset_path of the latest record and whether the file exists."""
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


@app.route('/api/upsert-single-record', methods=['POST'])
def upsert_single_record():
    """
    Create or update a single dataset record using the new schema.
    If no dataset exists, insert one; otherwise update the latest dataset.
    """
    try:
        data = request.get_json()
        
        dataset_path = data.get('dataset_path', 'uploaded.csv')
        discrete_columns = data.get('discrete_columns', [])
        continuous_columns = data.get('continuous_columns', [])
        selected_columns = data.get('selected_columns', [])
        target_variable = data.get('target_variable', '')
        
        # Get latest dataset or create new one
        latest = get_latest_dataset()
        
        if latest is None:
            # Create new dataset
            dataset_id = create_dataset(
                name=f"Dataset {dataset_path}",
                file_path=dataset_path,
                total_features=len(discrete_columns) + len(continuous_columns),
                discrete_features=len(discrete_columns),
                continuous_features=len(continuous_columns),
                target_variable=target_variable
            )
        else:
            # Update existing dataset
            dataset_id = latest['id']
            update_dataset(
                dataset_id=dataset_id,
                target_variable=target_variable,
                file_path=dataset_path,
                total_features=len(discrete_columns) + len(continuous_columns),
                discrete_features=len(discrete_columns),
                continuous_features=len(continuous_columns)
            )
        
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
        
        # Update feature types and selection status
        for feature in existing_features:
            name = feature['name']
            if name in all_columns:
                new_type = 'discrete' if name in discrete_columns else 'continuous'
                is_selected = name in selected_columns
                update_feature(feature['id'], type=new_type, selected=is_selected)
        
        return jsonify({"success": True, "id": dataset_id})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# =====================================================================
# BINNING FUNCTIONS (Coarse & Fine)
# =====================================================================

def coarse_bin_continuous(df, var, target, bins=10):
    """Perform coarse binning for continuous variables."""
    try:
        if var not in df.columns or df[var].isna().all():
            raise ValueError(f"Column '{var}' is missing or contains only NaN values")
        if target not in df.columns:
            raise ValueError(f"Target column '{target}' not found")
        
        _, bin_edges = pd.qcut(df[var], q=bins, retbins=True, labels=False, duplicates='drop')
        n_bins = len(bin_edges) - 1
        
        if n_bins <= 0:
            raise ValueError(f"No valid bins could be created for '{var}'.")
        
        bin_labels = [f'Bin_{i}' for i in range(1, n_bins + 1)]
        df[f'{var}_binned'] = pd.cut(df[var], bins=bin_edges, labels=bin_labels, include_lowest=True, right=True)
        
        tab = pd.crosstab(df[f'{var}_binned'], df[target])
        tab.columns = ['Good', 'Bad']
        tab['Total'] = tab['Good'] + tab['Bad']
        tab = tab.reset_index()
        
        min_max_values = df.groupby(f'{var}_binned')[var].agg(['min', 'max']).reset_index()
        tab = tab.merge(min_max_values, on=f'{var}_binned', how='left')
        tab = tab.rename(columns={f'{var}_binned': 'Bin', 'min': 'Min', 'max': 'Max'})
        
        columns_order = ['Bin', 'Min', 'Max', 'Good', 'Bad', 'Total']
        tab = tab[columns_order]
        
        return tab, df[f'{var}_binned']
    except Exception as e:
        raise ValueError(f"Coarse binning (continuous) failed for '{var}': {str(e)}")


def coarse_bin_discrete(df, var, target, bad_label=1, bad_rate_diff=0.5):
    """Perform coarse binning for discrete variables based on Bad Rate similarity."""
    try:
        if var not in df.columns or df[var].isna().all():
            raise ValueError(f"Column '{var}' is missing or contains only NaN values")
        if target not in df.columns:
            raise ValueError(f"Target column '{target}' not found")

        tab = pd.crosstab(df[var], df[target])
        if bad_label not in tab.columns:
            raise ValueError(f"Bad label '{bad_label}' not found in target column '{target}'")

        tab['Bad'] = tab[bad_label]
        tab['Good'] = tab.drop(columns=[bad_label]).sum(axis=1)
        tab['Total'] = tab['Good'] + tab['Bad']
        tab['Bad Rate'] = (tab['Bad'] / tab['Total']) * 100
        tab = tab.sort_values('Bad Rate')

        bin_mapping = {}
        current_bin = 1
        prev_bad_rate = tab['Bad Rate'].iloc[0] if not tab.empty else 0

        for idx, row in tab.iterrows():
            if abs(row['Bad Rate'] - prev_bad_rate) > bad_rate_diff:
                current_bin += 1
            bin_mapping[idx] = current_bin
            prev_bad_rate = row['Bad Rate']

        df[f'{var}_binned'] = df[var].map(bin_mapping).astype(int)

        final_tab = pd.crosstab(df[f'{var}_binned'], df[target])
        final_tab['Bad'] = final_tab[bad_label]
        final_tab['Good'] = final_tab.drop(columns=[bad_label]).sum(axis=1)
        final_tab['Total'] = final_tab['Good'] + final_tab['Bad']
        final_tab = final_tab.reset_index()

        def compact_ranges(values):
            values = sorted(values)
            ranges, start, prev = [], values[0], values[0]
            for v in values[1:]:
                if v == prev + 1:
                    prev = v
                else:
                    ranges.append(f"{start}–{prev}" if start != prev else str(start))
                    start = prev = v
            ranges.append(f"{start}–{prev}" if start != prev else str(start))
            return ", ".join(ranges)

        bin_ranges = {}
        for b in final_tab[f'{var}_binned']:
            original_vals = sorted([v for v, bin_id in bin_mapping.items() if bin_id == b])
            bin_ranges[b] = compact_ranges(original_vals)

        final_tab['Range'] = final_tab[f'{var}_binned'].map(bin_ranges)
        final_tab = final_tab.rename(columns={f'{var}_binned': 'Bin'})

        columns_order = ['Bin', 'Range', 'Good', 'Bad', 'Total']
        final_tab = final_tab[columns_order]

        return final_tab, df[f'{var}_binned'], bin_mapping

    except Exception as e:
        raise ValueError(f"Coarse binning (discrete) failed for '{var}': {str(e)}")


# Fine binning functions would continue here...
# (Including fine_bin_continuous, fine_bin_discrete, and related helpers)
# I'll add these in the next section

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
