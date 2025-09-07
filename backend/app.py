from flask import Flask, request, jsonify
from flask_cors import CORS
import pandas as pd
import numpy as np
import os
import datetime
import json
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
from db import get_db_connection, init_db, save_record_db, upsert_single_record_db, get_records_db, get_latest_record_dataset_path_db, get_record_db, delete_record_db, save_finebin_details_db, get_finebin_details_db

app = Flask(__name__)
CORS(app, origins=["http://localhost:5173"])

# ----------- Get Uploaded CSV Columns -----------
@app.route('/api/uploaded-csv-columns', methods=['GET'])
def get_uploaded_csv_columns():
    """
    Returns the column headers from the uploaded.csv file.
    """
    try:
        df = pd.read_csv('uploaded.csv', nrows=0)
        return jsonify({"columns": df.columns.tolist()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ----------- Health Check -----------
@app.route('/api/health', methods=['GET'])
def health():
    """
    A simple health check endpoint.
    """
    return jsonify({"status": "OK", "time": str(datetime.datetime.now())})

# ----------- Upload CSV -----------
@app.route('/api/upload-csv', methods=['POST'])
def upload_csv():
    """
    Handles CSV file uploads, saves the file, and returns column information.
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
            # Save to a known location in backend folder
            save_path = os.path.join(os.path.dirname(__file__), "uploaded.csv")
            df.to_csv(save_path, index=False)
            return jsonify({
                "success": True,
                "columns": df.columns.tolist(),
                "rowCount": len(df),
                "timestamp": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                "dataset_path": "uploaded.csv",
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
        df = pd.read_csv("uploaded.csv")
        data = request.get_json()
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
        tab['Freq%'] = (tab['Total'] / tab['Total'].sum()) * 100
        tab['Bad Rate'] = (tab['Bad'] / tab['Total']) * 100
        tab = tab.reset_index()
        
        # Calculate Min and Max from actual data in each bin
        min_max_values = df.groupby(f'{var}_binned')[var].agg(['min', 'max']).reset_index()
        tab = tab.merge(min_max_values, on=f'{var}_binned', how='left')
        
        # Reorder columns to include Min and Max after the bin label
        columns_order = [f'{var}_binned', 'min', 'max', 'Bad Rate', 'Bad', 'Good', 'Total', 'Freq%']
        tab = tab[columns_order]
        
        # Rename columns for clarity
        tab = tab.rename(columns={'min': 'Min', 'max': 'Max'})
        
        return tab, df[f'{var}_binned']
    except Exception as e:
        raise ValueError(f"Coarse binning (continuous) failed for '{var}': {str(e)}")

# ----------- Coarse Binning: Discrete -----------
import pandas as pd

def coarse_bin_discrete(df, var, target, bad_label=1, bad_rate_diff=0.5):
    """
    Coarse binning for discrete variables based on Bad Rate similarity.
    
    Parameters:
    - df : DataFrame
    - var : str, feature/column name
    - target : str, binary target column (0/1)
    - bad_label : value in target that indicates 'Bad' (default=1)
    - bad_rate_diff : float, threshold difference in bad rate to create new bin
    
    Returns:
    - final_tab : DataFrame with bin stats
    - df[f'{var}_binned'] : Series with bin assignments
    - bin_mapping : dict mapping original categories to bins
    """
    try:
        if var not in df.columns or df[var].isna().all():
            raise ValueError(f"Column '{var}' is missing or contains only NaN values")
        if target not in df.columns:
            raise ValueError(f"Target column '{target}' not found")

        # Crosstab (auto-detect Good/Bad based on bad_label)
        tab = pd.crosstab(df[var], df[target])
        if bad_label not in tab.columns:
            raise ValueError(f"Bad label '{bad_label}' not found in target column '{target}'")

        tab['Bad'] = tab[bad_label]
        tab['Good'] = tab.drop(columns=[bad_label]).sum(axis=1)
        tab['Total'] = tab['Good'] + tab['Bad']
        tab['Bad Rate'] = (tab['Bad'] / tab['Total']) * 100
        tab = tab.sort_values('Bad Rate')

        # Bin mapping based on bad rate difference
        bin_mapping = {}
        current_bin = 1
        prev_bad_rate = tab['Bad Rate'].iloc[0] if not tab.empty else 0

        for idx, row in tab.iterrows():
            if abs(row['Bad Rate'] - prev_bad_rate) > bad_rate_diff:
                current_bin += 1
            bin_mapping[idx] = current_bin
            prev_bad_rate = row['Bad Rate']

        # Apply binning
        df[f'{var}_binned'] = df[var].map(bin_mapping).astype(int)

        # Final crosstab
        final_tab = pd.crosstab(df[f'{var}_binned'], df[target])
        final_tab['Bad'] = final_tab[bad_label]
        final_tab['Good'] = final_tab.drop(columns=[bad_label]).sum(axis=1)
        final_tab['Total'] = final_tab['Good'] + final_tab['Bad']
        final_tab['Freq%'] = (final_tab['Total'] / final_tab['Total'].sum()) * 100
        final_tab['Bad Rate'] = (final_tab['Bad'] / final_tab['Total']) * 100
        final_tab = final_tab.reset_index()

        # Compact human-readable ranges
        def compact_ranges(values):
            values = sorted(values)
            ranges, start, prev = [], values[0], values[0]
            for v in values[1:]:
                if v == prev + 1:  # consecutive
                    prev = v
                else:
                    ranges.append(f"{start}–{prev}" if start != prev else str(start))
                    start = prev = v
            ranges.append(f"{start}–{prev}" if start != prev else str(start))
            return ", ".join(ranges)

        # Map original values to bins
        bin_ranges = {}
        for b in final_tab[f'{var}_binned']:
            original_vals = sorted([v for v, bin_id in bin_mapping.items() if bin_id == b])
            bin_ranges[b] = compact_ranges(original_vals)

        final_tab['Range'] = final_tab[f'{var}_binned'].map(bin_ranges)

        # Reorder
        columns_order = [f'{var}_binned', 'Range', 'Bad Rate', 'Bad', 'Good', 'Total', 'Freq%']
        final_tab = final_tab[columns_order]

        return final_tab, df[f'{var}_binned'], bin_mapping

    except Exception as e:
        raise ValueError(f"Coarse binning (discrete) failed for '{var}': {str(e)}")

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
                    min_val = int(np.floor(values.min())) if not values.empty else None
                    max_val = int(np.ceil(values.max())) if not values.empty else None
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
                    min_val = int(np.floor(values.min())) if not values.empty else None
                    max_val = int(np.ceil(values.max())) if not values.empty else None
                    bin_ranges[merged_name] = (min_val, max_val)
        
        # Apply new mapping
        df[fine_binned_col] = df[binned_col].map(lambda x: new_bin_map.get(x, x))
        # Add ranges for unmapped bins
        unmapped_bins = set(df[binned_col].unique()) - set(new_bin_map.keys())
        for bin_label in unmapped_bins:
            mask = df[binned_col] == bin_label
            if mask.any():
                values = df.loc[mask, var]
                min_val = int(np.floor(values.min())) if not values.empty else None
                max_val = int(np.ceil(values.max())) if not values.empty else None
                bin_ranges[bin_label] = (min_val, max_val)
        
        # Cross-tab summary
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
        cross_tab['Freq%'] = (cross_tab['Total'] / cross_tab['Total'].sum()) * 100
        cross_tab['Bad Rate'] = (cross_tab['Bad'] / cross_tab['Total']) * 100
        cross_tab = cross_tab.reset_index()
        
        # Add min and max columns
        cross_tab['Min'] = cross_tab[fine_binned_col].map(lambda x: bin_ranges.get(x, (None, None))[0])
        cross_tab['Max'] = cross_tab[fine_binned_col].map(lambda x: bin_ranges.get(x, (None, None))[1])
        
        columns_order = [fine_binned_col, 'Min', 'Max', 'Bad', 'Good', 'Total', 'Freq%', 'Bad Rate']
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

        # Crosstab
        cross_tab = pd.crosstab(df[fine_binned_col], df[target])
        col_map = {}
        if 0 in cross_tab.columns: col_map[0] = 'Good'
        if 1 in cross_tab.columns: col_map[1] = 'Bad'
        cross_tab = cross_tab.rename(columns=col_map)

        for col in ['Good', 'Bad']:
            if col not in cross_tab.columns:
                cross_tab[col] = 0

        cross_tab['Total'] = cross_tab['Good'] + cross_tab['Bad']
        cross_tab['Freq%'] = (cross_tab['Total'] / cross_tab['Total'].sum()) * 100
        cross_tab['Bad Rate'] = (cross_tab['Bad'] / cross_tab['Total']) * 100
        cross_tab = cross_tab.reset_index()

        # ✅ FIX: Always use str keys for bin_ranges lookup
        cross_tab['Range'] = cross_tab[fine_binned_col].astype(str).map(lambda x: ', '.join(map(str, bin_ranges.get(x, ['N/A']))))

        # Final order
        columns_order = [fine_binned_col, 'Range', 'Bad Rate', 'Bad', 'Good', 'Total', 'Freq%']
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
        df = pd.read_csv("uploaded.csv")
        df[target] = df[target].fillna(0).astype(int)
        if var_type == 'continuous':
            _, df[f'{var}_binned'] = coarse_bin_continuous(df, var, target)
            # Only keep bins that exist
            existing_bins = set(df[f'{var}_binned'].unique())
            bin_merges = {
                k: [b for b in v if b in existing_bins]
                for k, v in bin_merges.items()
            }
            # Remove empty merges
            bin_merges = {k: v for k, v in bin_merges.items() if v}
            tab, _, adjusted_merges, _ = fine_bin_continuous(df, var, target, bin_merges)  # Handle the extra bin_ranges return value
        else:
            _, df[f'{var}_binned'], bin_mapping = coarse_bin_discrete(df, var, target)
            tab, _, adjusted_merges = fine_bin_discrete(df, var, target, bin_merges, bin_mapping)
        if tab is None:
            return jsonify({"error": "Fine binning returned no results"}), 400
        df.to_csv("uploaded.csv", index=False)
        print("Fine binning done for", var)
        return jsonify({
            "success": True,
            "stats": tab.to_dict(orient='records'),
            "bin_merges": adjusted_merges
        })
    except Exception as e:
        import traceback
        print("ERROR:", traceback.format_exc())
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
        # Load dataset
        df = pd.read_csv("uploaded.csv")
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
        # Save updated dataset with binned columns
        df.to_csv("uploaded.csv", index=False)
        return jsonify(results)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ----------- Univariate Analysis API -----------
@app.route('/api/univariate-analysis', methods=['POST'])
def univariate_analysis():
    """
    Performs univariate analysis (coarse binning) for a list of variables.
    """
    try:
        req = request.get_json()
        discrete_cols = req.get('discrete', [])
        continuous_cols = req.get('continuous', [])
        target = req.get('target')
        if not target:
            return jsonify({"error": "Missing required field: target"}), 400
        df = pd.read_csv("uploaded.csv")
        if target not in df.columns:
            return jsonify({"error": f"Target column '{target}' not found in dataset"}), 400
        df[target] = df[target].fillna(0).astype(int)
        results = {}
        for col in discrete_cols:
            if col != target and col in df.columns:
                stats, _, _ = coarse_bin_discrete(df, col, target)
                results[col] = {
                    'type': 'discrete',
                    'stats': stats.to_dict(orient='records')
                }
        for col in continuous_cols:
            if col != target and col in df.columns:
                stats, _ = coarse_bin_continuous(df, col, target)
                results[col] = {
                    'type': 'continuous',
                    'stats': stats.to_dict(orient='records')
                }
        return jsonify(results)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ----------- WOE/IV Calculation -----------
def calculate_woe_iv(df, variable, target, bin_merges=None):
    # Apply fine bin merges if available
    if bin_merges:
        def map_bin(val):
            for label, bins in bin_merges.items():
                if val in bins:
                    return label
            return str(val)
        df["final_bin"] = df[f"{variable}_binned"].apply(map_bin)
    else:
        if f"{variable}_binned" in df.columns:
            df["final_bin"] = df[f"{variable}_binned"]
        else:
            df["final_bin"] = pd.qcut(df[variable], q=10, duplicates="drop")
    
    # Determine if variable is continuous or discrete
    is_continuous = pd.api.types.is_numeric_dtype(df[variable]) and df[variable].nunique(dropna=True) > 20
    
    # Compute bin ranges
    bin_ranges = {}
    if is_continuous:
        for bin_label in df["final_bin"].unique():
            mask = df["final_bin"] == bin_label
            if mask.any():
                values = df.loc[mask, variable]
                min_val = int(np.floor(values.min())) if not values.empty else None
                max_val = int(np.ceil(values.max())) if not values.empty else None
                bin_ranges[bin_label] = (min_val, max_val)
    else:
        for bin_label in df["final_bin"].unique():
            mask = df["final_bin"] == bin_label
            if mask.any():
                values = df.loc[mask, variable].unique()
                bin_ranges[bin_label] = sorted([str(val) for val in values])
    
    # Aggregate counts
    grouped = df.groupby("final_bin", observed=True).agg(
        Total=(target, "count"),
        Good=(target, lambda x: (x == 0).sum()),
        Bad=(target, lambda x: (x == 1).sum())
    ).reset_index()
    total_good = grouped["Good"].sum()
    total_bad = grouped["Bad"].sum()
    n_bins = len(grouped)
    stats = []
    iv_total = 0.0
    eps = 0.5
    adj_total_good = total_good + eps * n_bins
    adj_total_bad = total_bad + eps * n_bins
    for _, row in grouped.iterrows():
        dist_good = (row["Good"] + eps) / adj_total_good
        dist_bad = (row["Bad"] + eps) / adj_total_bad
        woe = np.log(dist_good / dist_bad)
        iv = (dist_good - dist_bad) * woe
        iv_total += iv
        bin_label = str(row["final_bin"])
        if is_continuous and "Interval" in bin_label:
            bin_label = bin_label.replace("Interval", "").replace("(", "").replace("]", "")
        # Add range information
        range_info = bin_ranges.get(row["final_bin"], (None, None) if is_continuous else [])
        stats.append({
            "Bin": bin_label,
            "Good": int(row["Good"]),
            "Bad": int(row["Bad"]),
            "Total": int(row["Total"]),
            "WOE": round(float(woe), 4),
            "IV": round(float(iv), 4),
            "Range": ', '.join(map(str, range_info)) if not is_continuous else f"{range_info[0]} - {range_info[1]}"
        })
    return round(float(iv_total), 4), stats

# ----------- WOE/IV API -----------
@app.route("/api/woe-iv", methods=["POST"])
def woe_iv_api():
    try:
        data = request.get_json()
        variables = data.get("variables", [])
        target = data.get("target")
        record_id = data.get("record_id")
        df = pd.read_csv("uploaded.csv")
        df[target] = df[target].fillna(0).astype(int)
        results = {}
        for var in variables:
            # 1) Ensure a binned column exists for this var
            # Infer type: treat as discrete if non-object numeric with small cardinality OR object/categorical
            var_series = df[var]
            if pd.api.types.is_numeric_dtype(var_series):
                # numeric but could be discrete if few unique levels
                if var_series.nunique(dropna=True) <= 20:
                    _, df[f"{var}_binned"], _ = coarse_bin_discrete(df.copy(), var, target)
                else:
                    _, df[f"{var}_binned"] = coarse_bin_continuous(df.copy(), var, target)
            else:
                # non-numeric => discrete
                _, df[f"{var}_binned"], _ = coarse_bin_discrete(df.copy(), var, target)
            # 2) Load saved merges (if any) for this var
            merges = None
            if record_id:
                finebin_details = get_finebin_details_db(record_id, var)
                if finebin_details:
                    merges = {}
                    for row in finebin_details:
                        try:
                            bins = json.loads(row["merged_bins"])
                            merges[str(row["group_id"])] = bins
                        except Exception:
                            pass
            # 3) Compute WOE/IV on the (possibly) merged final bins
            iv, stats = calculate_woe_iv(df.copy(), var, target, bin_merges=merges)
            results[var] = {"iv": iv, "stats": stats}
        # 4) Save WOE/IV results to the records table
        if record_id:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("SELECT woe_iv_results FROM records WHERE id = ?", (record_id,))
            row = cur.fetchone()
            existing_woe_iv = {}
            if row and row['woe_iv_results']:
                try:
                    existing_woe_iv = json.loads(row['woe_iv_results'])
                except json.JSONDecodeError:
                    existing_woe_iv = {}
            # Update with new results
            existing_woe_iv.update(results)
            cur.execute(
                "UPDATE records SET woe_iv_results = ? WHERE id = ?",
                (json.dumps(existing_woe_iv), record_id)
            )
            conn.commit()
            conn.close()
        return jsonify(results)
    except Exception as e:
        print("woe_iv_api failed:", str(e))
        return jsonify({"error": str(e)}), 500

# ----------- Save Record -----------
@app.route('/api/save-record', methods=['POST'])
def save_record():
    """
    Save a record of the analysis, including dataset path, columns, and results.
    """
    try:
        data = request.get_json()
        dataset_path = data.get('dataset_path', '')
        discrete_columns = ','.join(data.get('discrete_columns', []))
        continuous_columns = ','.join(data.get('continuous_columns', []))
        selected_columns = ','.join(data.get('selected_columns', []))
        target_variable = data.get('target_variable', '')
        univariate_results = data.get('univariate_results', '')
        finebin_results = data.get('finebin_results', '')
        crosstab_results = data.get('crosstab_results', '')
        record_id = save_record_db(
            dataset_path, discrete_columns, continuous_columns, 
            selected_columns, target_variable, univariate_results, 
            finebin_results, crosstab_results
        )
        return jsonify({"success": True, "id": record_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ----------- Upsert Single Record -----------
@app.route('/api/upsert-single-record', methods=['POST'])
def upsert_single_record():
    """
    Create or update a single record. If no record exists, insert one; otherwise update the latest record.
    This supports the UX where only one record should exist and be updated across actions.
    """
    try:
        data = request.get_json()
        dataset_path = data.get('dataset_path', '')
        discrete_columns = ','.join(data.get('discrete_columns', []))
        continuous_columns = ','.join(data.get('continuous_columns', []))
        selected_columns = ','.join(data.get('selected_columns', []))
        target_variable = data.get('target_variable', '')
        univariate_results = data.get('univariate_results', '')
        finebin_results = data.get('finebin_results', '')
        crosstab_results = data.get('crosstab_results', '')
        woe_iv_results = data.get('woe_iv_results', '')
        record_id = upsert_single_record_db(
            dataset_path, discrete_columns, continuous_columns, 
            selected_columns, target_variable, univariate_results, 
            finebin_results, crosstab_results, woe_iv_results
        )
        return jsonify({"success": True, "id": record_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ----------- Get Records -----------
@app.route('/api/records', methods=['GET'])
def get_records():
    """
    List all analysis records (summary only).
    """
    try:
        records = get_records_db()
        return jsonify(records)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ----------- Latest Record Dataset Path -----------
@app.route('/api/latest-record-dataset-path', methods=['GET'])
def latest_record_dataset_path():
    """
    Returns the dataset_path of the latest record and whether the file exists.
    """
    try:
        dataset_path, resolved_path, valid = get_latest_record_dataset_path_db()
        return jsonify({
            "dataset_path": dataset_path,
            "resolved_path": resolved_path,
            "valid": valid
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ----------- Get Record -----------
@app.route('/api/record/<int:record_id>', methods=['GET'])
def get_record(record_id):
    """
    Get a specific analysis record (full details).
    """
    try:
        record = get_record_db(record_id)
        if record:
            # Ensure woe_iv_results is parsed if it's a JSON string
            if record.get('woe_iv_results'):
                try:
                    record['woe_iv_results'] = json.loads(record['woe_iv_results'])
                except json.JSONDecodeError:
                    record['woe_iv_results'] = {}
            return jsonify(record)
        else:
            return jsonify({"error": "Record not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ----------- Logistic Regression Analysis -----------
@app.route('/api/logistic-regression', methods=['POST'])
def logistic_regression_analysis():
    """
    Perform logistic regression analysis on selected variables.
    Expects payload: { selected_variables: [list], target: string, woe_transformed_data: {} }
    Returns: model metrics, coefficients, p-values, VIF, Gini, ROC data
    """
    try:
        data = request.get_json()
        selected_variables = data.get('selected_variables', [])
        target = data.get('target')
        woe_transformed_data = data.get('woe_transformed_data', {})
        
        if not selected_variables or not target:
            return jsonify({"error": "Missing selected_variables or target"}), 400
        
        # Read the dataset
        df = pd.read_csv("uploaded.csv")
        
        if target not in df.columns:
            return jsonify({"error": f"Target variable '{target}' not found in dataset"}), 400
        
        # Create WOE transformed dataset
        woe_df = df[[target]].copy()
        
        for var in selected_variables:
            # Robust WOE mapping + diagnostics
            if var in woe_transformed_data:
                print(f"LOGISTIC DEBUG: woe_transformed_data for '{var}':", woe_transformed_data.get(var))
                # initialize column as NaN so we can detect unmapped rows
                woe_df[f'{var}_WOE'] = np.nan
                # woe_transformed_data[var] may be either:
                # - a list of bin dicts, or
                # - a dict like { 'iv': ..., 'stats': [bin_dicts...] }
                raw_bins = woe_transformed_data.get(var)
                if isinstance(raw_bins, dict) and isinstance(raw_bins.get('stats'), list):
                    bins_list = raw_bins.get('stats')
                elif isinstance(raw_bins, list):
                    bins_list = raw_bins
                else:
                    bins_list = []
                if not bins_list:
                    print(f"LOGISTIC DEBUG: no bin definitions found for '{var}' in woe_transformed_data")
                for bin_info in bins_list:
                    # accept multiple key spellings
                    bin_range = bin_info.get('range') or bin_info.get('Range') or bin_info.get('Bin') or bin_info.get('bin')
                    woe_value = bin_info.get('woe') or bin_info.get('WOE')
                    if woe_value is None:
                        continue
                    try:
                        woe_value = float(woe_value)
                    except Exception:
                        continue
                    # handle list/array of categories
                    if isinstance(bin_range, (list, tuple)):
                        mask = df[var].isin(bin_range)
                        woe_df.loc[mask, f'{var}_WOE'] = woe_value
                        continue
                    # handle string ranges: "a to b" or "a - b" or "min - max"
                    if isinstance(bin_range, str):
                        br = bin_range.strip()
                        # common separators
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
                        # discrete: maybe comma-separated categories
                        cats = re.split(r'[,\|;]', br)
                        cats = [c.strip() for c in cats if c.strip() != '']
                        if len(cats) > 1:
                            mask = df[var].astype(str).isin(cats)
                            woe_df.loc[mask, f'{var}_WOE'] = woe_value
                            continue
                        # fallback: direct equality to the label
                        mask = df[var].astype(str) == br
                        woe_df.loc[mask, f'{var}_WOE'] = woe_value
                    else:
                        # final fallback: compare as string
                        mask = df[var].astype(str) == str(bin_range)
                        woe_df.loc[mask, f'{var}_WOE'] = woe_value
                # diagnostics after mapping
                non_null = int(woe_df[f'{var}_WOE'].notna().sum())
                print(f"LOGISTIC DEBUG: mapped WOE rows for '{var}':", non_null, "of", len(df))
                # convert unmapped to 0 (or consider leaving NaN to detect issues)
                woe_df[f'{var}_WOE'] = woe_df[f'{var}_WOE'].fillna(0)
            else:
                print(f"LOGISTIC DEBUG: no woe_transformed_data for '{var}' — creating zero column")
                woe_df[f'{var}_WOE'] = 0
        
        # Prepare feature matrix
        feature_cols = [f'{var}_WOE' for var in selected_variables]
        X = woe_df[feature_cols].fillna(0)
        y = woe_df[target]
        
        # Remove any rows with missing target values
        mask = ~y.isna()
        X = X[mask]
        y = y[mask]
        
        if len(X) == 0:
            return jsonify({"error": "No valid data after preprocessing"}), 400
        
                # --- DIAGNOSTICS (added) ---
        # quick checks to identify singularity causes
        try:
            nunique = X.nunique()
            zero_var_cols = nunique[nunique <= 1].index.tolist()
            variances = X.var().to_dict()
            # exact duplicate columns
            dup_mask = X.T.duplicated()
            dup_cols = X.columns[dup_mask].tolist()
            sample = X.head(5).to_dict(orient='records')
            y_counts = y.value_counts().to_dict()
            print("LOGISTIC DEBUG: X shape:", X.shape)
            print("LOGISTIC DEBUG: feature_cols:", feature_cols)
            print("LOGISTIC DEBUG: zero-variance cols:", zero_var_cols)
            print("LOGISTIC DEBUG: duplicated cols:", dup_cols)
            print("LOGISTIC DEBUG: variances (sample):", {k: variances[k] for k in list(variances)[:10]})
            print("LOGISTIC DEBUG: y distribution:", y_counts)
            print("LOGISTIC DEBUG: X sample rows:", sample)
        except Exception as _diag:
            print("LOGISTIC DEBUG: diagnostics failed:", str(_diag))
        # --- END DIAGNOSTICS ---

        # Fit logistic regression model
        logit_model = sm.Logit(y, sm.add_constant(X))
        result = logit_model.fit(disp=0)
        
        # Calculate VIF for multicollinearity
        vif_data = []
        if len(feature_cols) > 1:
            X_with_const = sm.add_constant(X)
            for i, col in enumerate(['const'] + feature_cols):
                if i > 0:  # Skip constant
                    try:
                        vif = variance_inflation_factor(X_with_const.values, i)
                        vif_data.append({
                            'variable': selected_variables[i-1],
                            'vif': float(vif) if not np.isnan(vif) and not np.isinf(vif) else 0
                        })
                    except:
                        vif_data.append({
                            'variable': selected_variables[i-1],
                            'vif': 0
                        })
        
        # ROC Curve calculation
        y_pred_proba = result.predict(sm.add_constant(X))
        fpr, tpr, thresholds = roc_curve(y, y_pred_proba)
        roc_auc = auc(fpr, tpr)
        
        # Gini coefficient (2 * AUC - 1)
        gini_coefficient = 2 * roc_auc - 1
        
        # Classification predictions (threshold 0.5)
        try:
            y_pred = (y_pred_proba >= 0.5).astype(int)
        except Exception:
            # fallback in case shapes differ
            y_pred = (np.array(y_pred_proba) >= 0.5).astype(int)

        # Confusion matrix and classification metrics
        try:
            cm = confusion_matrix(y, y_pred)
            accuracy = accuracy_score(y, y_pred)
            precision = precision_score(y, y_pred, zero_division=0)
            recall = recall_score(y, y_pred, zero_division=0)
            f1 = f1_score(y, y_pred, zero_division=0)
        except Exception as _cm_err:
            cm = np.array([[0, 0], [0, 0]])
            accuracy = precision = recall = f1 = 0.0

        # Create confusion matrix image (PNG, base64)
        try:
            fig, ax = plt.subplots(figsize=(4, 4))
            im = ax.imshow(cm, interpolation='nearest', cmap='Blues')
            ax.set_title('Confusion Matrix')
            ax.set_ylabel('Actual')
            ax.set_xlabel('Predicted')
            # Tick labels for binary 0/1
            ax.set_xticks([0, 1])
            ax.set_yticks([0, 1])
            ax.set_xticklabels(['0', '1'])
            ax.set_yticklabels(['0', '1'])
            # Annotate
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
        
        # Prepare results
        coefficients = []
        p_values = []
        
        for i, var in enumerate(['const'] + selected_variables):
            coef = result.params[i] if i < len(result.params) else 0
            p_val = result.pvalues[i] if i < len(result.pvalues) else 1
            
            if var == 'const':
                coefficients.append({
                    'variable': 'Intercept',
                    'coefficient': float(coef),
                    'significance': 'Highly Significant' if p_val < 0.01 else 'Significant' if p_val < 0.05 else 'Not Significant'
                })
                p_values.append({
                    'variable': 'Intercept',
                    'p_value': float(p_val),
                    'significance': 'Highly Significant' if p_val < 0.01 else 'Significant' if p_val < 0.05 else 'Not Significant'
                })
            else:
                coefficients.append({
                    'variable': var,
                    'coefficient': float(coef),
                    'significance': 'Highly Significant' if p_val < 0.01 else 'Significant' if p_val < 0.05 else 'Not Significant'
                })
                p_values.append({
                    'variable': var,
                    'p_value': float(p_val),
                    'significance': 'Highly Significant' if p_val < 0.01 else 'Significant' if p_val < 0.05 else 'Not Significant'
                })
        
        # ROC Curve data for plotting
        roc_data = [{'fpr': float(f), 'tpr': float(t)} for f, t in zip(fpr, tpr)]
        
        # Model summary statistics
        model_stats = {
            'aic': float(result.aic),
            'bic': float(result.bic),
            'log_likelihood': float(result.llf),
            'pseudo_r_squared': float(result.prsquared),
            'n_observations': int(result.nobs)
        }
        
        return jsonify({
            'success': True,
            'coefficients': coefficients,
            'p_values': p_values,
            'vif_data': vif_data,
            'gini_coefficient': float(gini_coefficient),
            'auc': float(roc_auc),
            'roc_data': roc_data,
            'model_stats': model_stats,
            # Confusion matrix and classification metrics
            'confusion_matrix': cm.tolist() if isinstance(cm, (list, np.ndarray)) else None,
            'confusion_matrix_image': cm_image_data,
            'accuracy': float(accuracy),
            'precision': float(precision),
            'recall': float(recall),
            'f1': float(f1)
        })
        
    except Exception as e:
        return jsonify({"error": f"Failed to perform logistic regression: {str(e)}"}), 500

# ----------- Delete Record -----------
@app.route('/api/record/<int:record_id>', methods=['DELETE'])
def delete_record(record_id):
    """
    Delete a specific analysis record by ID, and remove any related finebin_details rows.
    """
    try:
        success = delete_record_db(record_id)
        return jsonify({"success": success})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ----------- Finebin Details API -----------
@app.route('/api/finebin-details', methods=['POST'])
def save_finebin_details():
    """
    Upsert fine binning details for a specific record and column.
    Expects payload: { record_id, column_name, bin_merges: { <group_id>: [bins], ... } }
    """
    data = request.get_json()
    record_id = data.get('record_id')
    column_name = data.get('column_name')
    bin_merges = data.get('bin_merges') # dict of group_id -> list of bins
    if not record_id or not column_name or not isinstance(bin_merges, dict):
        return jsonify({"error": "Missing or invalid fields (record_id, column_name, bin_merges)."}), 400
    try:
        success = save_finebin_details_db(record_id, column_name, bin_merges)
        return jsonify({"success": success})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/finebin-details/<int:record_id>/<string:column_name>', methods=['GET'])
def get_finebin_details(record_id, column_name):
    """
    Retrieve fine binning details for a specific record and column.
    """
    try:
        finebin_details = get_finebin_details_db(record_id, column_name)
        return jsonify(finebin_details)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=True, host='0.0.0.0', port=port)