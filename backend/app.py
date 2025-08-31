from flask import Flask, request, jsonify
import sqlite3
from flask_cors import CORS
import pandas as pd
import numpy as np
import os
import datetime
from math import ceil
import json

# ----------- Get Uploaded CSV Columns -----------

app = Flask(__name__)
CORS(app, origins=["http://localhost:5173"])

@app.route('/api/uploaded-csv-columns', methods=['GET'])
def get_uploaded_csv_columns():
    """
    Returns the column headers from the uploaded.csv file.
    """
    import pandas as pd
    try:
        df = pd.read_csv('uploaded.csv', nrows=0)
        return jsonify({"columns": df.columns.tolist()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

app = Flask(__name__)
CORS(app, origins=["http://localhost:5173"])
@app.route('/api/record/<int:record_id>', methods=['DELETE'])
def delete_record(record_id):
    """
    Delete a specific analysis record by ID, and remove any related finebin_details rows.
    """
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        # First remove finebin_details for this record
        try:
            cur.execute("DELETE FROM finebin_details WHERE record_id = ?", (record_id,))
        except Exception:
            # If table doesn't exist or other issue, continue to delete record
            pass
        # Then remove the record
        cur.execute("DELETE FROM records WHERE id = ?", (record_id,))
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Database initialization
DB_PATH = os.path.join(os.path.dirname(__file__), 'database.sql')
DB_FILE = os.path.join(os.path.dirname(__file__), 'records.db')

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with open(DB_PATH, 'r') as f:
        sql = f.read()
    conn = get_db_connection()
    # Drop existing table to ensure schema update (use with caution in production)
    conn.execute("DROP TABLE IF EXISTS records")
    conn.executescript(sql)
    conn.commit()
    conn.close()
init_db()
# ----------- Health Check -----------
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

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO records (dataset_path, discrete_columns, continuous_columns, selected_columns, target_variable, univariate_results, finebin_results, crosstab_results)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (dataset_path, discrete_columns, continuous_columns, selected_columns, target_variable, univariate_results, finebin_results, crosstab_results)
        )
        conn.commit()
        record_id = cur.lastrowid
        conn.close()
        return jsonify({"success": True, "id": record_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

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
        woe_iv_results = data.get('woe_iv_results', '')  # Added to handle WOE/IV results

        conn = get_db_connection()
        cur = conn.cursor()

        # Check if a record exists
        cur.execute("SELECT id FROM records ORDER BY created_at DESC LIMIT 1")
        row = cur.fetchone()

        if row is None:
            # Insert new record
            cur.execute(
                """
                INSERT INTO records (dataset_path, discrete_columns, continuous_columns, selected_columns, target_variable, univariate_results, finebin_results, crosstab_results, woe_iv_results)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (dataset_path, discrete_columns, continuous_columns, selected_columns, target_variable, univariate_results, finebin_results, crosstab_results, woe_iv_results)
            )
            conn.commit()
            record_id = cur.lastrowid
        else:
            # Update existing latest record
            record_id = row['id'] if isinstance(row, sqlite3.Row) else row[0]
            cur.execute(
                """
                UPDATE records
                SET dataset_path = ?,
                    discrete_columns = ?,
                    continuous_columns = ?,
                    selected_columns = ?,
                    target_variable = ?,
                    univariate_results = ?,
                    finebin_results = ?,
                    crosstab_results = ?,
                    woe_iv_results = ?
                WHERE id = ?
                """,
                (dataset_path, discrete_columns, continuous_columns, selected_columns, target_variable, univariate_results, finebin_results, crosstab_results, woe_iv_results, record_id)
            )
            conn.commit()

        conn.close()
        return jsonify({"success": True, "id": record_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/records', methods=['GET'])
def get_records():
    """
    List all analysis records (summary only).
    """
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, dataset_path, discrete_columns, continuous_columns, selected_columns, target_variable, created_at FROM records ORDER BY created_at DESC")
        rows = cur.fetchall()
        records = [dict(row) for row in rows]
        conn.close()
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
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT dataset_path FROM records ORDER BY created_at DESC LIMIT 1")
        row = cur.fetchone()
        conn.close()
        if not row:
            return jsonify({"dataset_path": None, "valid": False})
        dataset_path = row[0] if not isinstance(row, sqlite3.Row) else row['dataset_path']
        # Resolve relative paths relative to backend directory
        resolved = dataset_path
        if dataset_path and not os.path.isabs(dataset_path):
            resolved = os.path.join(os.path.dirname(__file__), dataset_path)
        return jsonify({
            "dataset_path": dataset_path,
            "resolved_path": resolved,
            "valid": bool(resolved and os.path.exists(resolved))
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/record/<int:record_id>', methods=['GET'])
def get_record(record_id):
    """
    Get a specific analysis record (full details).
    """
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM records WHERE id = ?", (record_id,))
        row = cur.fetchone()
        conn.close()
        if row:
            record = dict(row)
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

# ----------- Coarse Binning: Continuous (CORRECTED & REORDERED) -----------
def coarse_bin_continuous(df, var, target, bins=10):
    """
    Performs coarse binning on a continuous variable using quantiles (qcut).
    The output is a dataframe with a specific column order.
    """
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
        tab['Freq%'] = (tab['Total'] / tab['Total'].sum()) * 100
        tab['Bad Rate'] = (tab['Bad'] / tab['Total']) * 100
        tab = tab.reset_index()

        # Reorder columns to the requested format
        columns_order = [f'{var}_binned', 'Bad Rate', 'Bad', 'Good', 'Total', 'Freq%']
        tab = tab[columns_order]
        return tab, df[f'{var}_binned']
    except Exception as e:
        raise ValueError(f"Coarse binning (continuous) failed for '{var}': {str(e)}")

# ----------- Coarse Binning: Discrete (REORDERED) -----------
def coarse_bin_discrete(df, var, target, bad_rate_diff=0.5):
    """
    Performs coarse binning on a discrete variable.
    The output is a dataframe with a specific column order.
    """
    try:
        if var not in df.columns or df[var].isna().all():
            raise ValueError(f"Column '{var}' is missing or contains only NaN values")
        if target not in df.columns:
            raise ValueError(f"Target column '{target}' not found")

        tab = pd.crosstab(df[var], df[target])
        tab.columns = ['Good', 'Bad']
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

        df[f'{var}_binned'] = df[var].map(bin_mapping)

        final_tab = pd.crosstab(df[f'{var}_binned'], df[target])
        final_tab.columns = ['Good', 'Bad']
        final_tab['Total'] = final_tab['Good'] + final_tab['Bad']
        final_tab['Freq%'] = (final_tab['Total'] / final_tab['Total'].sum()) * 100
        final_tab['Bad Rate'] = (final_tab['Bad'] / final_tab['Total']) * 100
        final_tab = final_tab.reset_index()

        # Reorder columns to the requested format
        columns_order = [f'{var}_binned', 'Bad Rate', 'Bad', 'Good', 'Total', 'Freq%']
        final_tab = final_tab[columns_order]
        return final_tab, df[f'{var}_binned'], bin_mapping
    except Exception as e:
        raise ValueError(f"Coarse binning (discrete) failed for '{var}': {str(e)}")

# ----------- Fine Binning: Continuous (REORDERED) -----------
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

        if curr_num == prev_num + 1:  # ✅ adjacent
            current.append(curr_label)
        else:  # ❌ break → start new group
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
            return None, df[fine_binned_col], {}

        new_bin_map = {}
        updated_merges = {}

        for new_bin, old_bins in bin_merges.items():
            # Split into adjacent groups instead of erroring
            groups = split_into_adjacent_groups(old_bins)

            for idx, g in enumerate(groups, start=1):
                merged_name = f"{'_'.join(g)}"
                updated_merges[merged_name] = g
                for b in g:
                    new_bin_map[b] = merged_name

        # Apply new mapping
        df[fine_binned_col] = df[binned_col].map(lambda x: new_bin_map.get(x, x))

        # Cross-tab summary
        cross_tab = pd.crosstab(df[fine_binned_col], df[target])

        # Rename target columns
        cols = cross_tab.columns.tolist()
        col_map = {}
        if 0 in cols:
            col_map[0] = 'Good'
        if 1 in cols:
            col_map[1] = 'Bad'
        cross_tab = cross_tab.rename(columns=col_map)

        # Fill missing
        for col in ['Good', 'Bad']:
            if col not in cross_tab.columns:
                cross_tab[col] = 0

        cross_tab['Total'] = cross_tab['Good'] + cross_tab['Bad']
        cross_tab['Freq%'] = (cross_tab['Total'] / cross_tab['Total'].sum()) * 100
        cross_tab['Bad Rate'] = (cross_tab['Bad'] / cross_tab['Total']) * 100
        cross_tab = cross_tab.reset_index()

        columns_order = [fine_binned_col, 'Bad', 'Good', 'Total', 'Freq%', 'Bad Rate']
        cross_tab = cross_tab[columns_order]

        return cross_tab, df[fine_binned_col], updated_merges

    except Exception as e:
        raise ValueError(f"Fine binning (continuous) failed for '{var}': {str(e)}")


# ----------- Fine Binning: Discrete (REORDERED) -----------
def fine_bin_discrete(df, var, target, bin_merges=None, bin_mapping=None):
    """
    Performs fine binning by merging coarse bins for a discrete variable.
    The output is a dataframe with a specific column order.
    """
    try:
        binned_col = f'{var}_binned'
        fine_binned_col = f'{var}_fine_binned'

        bin_map = {}
        for new_bin, old_bins in bin_merges.items():
            for old_bin in old_bins:
                bin_map[old_bin] = new_bin

        df[fine_binned_col] = df[binned_col].map(bin_map)

        cross_tab = pd.crosstab(df[fine_binned_col], df[target])

        # Dynamic rename of columns to Good/Bad depending on presence
        cols = cross_tab.columns.tolist()
        col_map = {}
        if 0 in cols:
            col_map[0] = 'Good'
        if 1 in cols:
            col_map[1] = 'Bad'
        cross_tab = cross_tab.rename(columns=col_map)

        # Add missing columns with 0 if needed
        for col in ['Good', 'Bad']:
            if col not in cross_tab.columns:
                cross_tab[col] = 0

        cross_tab['Total'] = cross_tab['Good'] + cross_tab['Bad']
        cross_tab['Freq%'] = (cross_tab['Total'] / cross_tab['Total'].sum()) * 100
        cross_tab['Bad Rate'] = (cross_tab['Bad'] / cross_tab['Total']) * 100
        cross_tab = cross_tab.reset_index()

        columns_order = [fine_binned_col, 'Bad Rate', 'Bad', 'Good', 'Total', 'Freq%']
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

            tab, _, adjusted_merges = fine_bin_continuous(df, var, target, bin_merges)

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
        binning_info = req.get('binning', {})  # optional: {var: {type: 'continuous'/'discrete', bin_merges: {...}}}

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

# ----------- Health Check -----------
@app.route('/api/health', methods=['GET'])
def health():
    """
    A simple health check endpoint.
    """
    return jsonify({"status": "OK", "time": str(datetime.datetime.now())})

# ----------- Finebin Details API -----------
@app.route('/api/finebin-details', methods=['POST'])
def save_finebin_details():
    """
    Upsert fine binning details for a specific record and column.
    Expects payload: { record_id, column_name, bin_merges: { <group_id>: [bins], ... } }
    For simplicity, we delete existing rows for (record_id, column_name) and insert fresh ones per group.
    """
    data = request.get_json()
    record_id = data.get('record_id')
    column_name = data.get('column_name')
    bin_merges = data.get('bin_merges')  # dict of group_id -> list of bins

    if not record_id or not column_name or not isinstance(bin_merges, dict):
        return jsonify({"error": "Missing or invalid fields (record_id, column_name, bin_merges)."}), 400

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Delete previous entries for this record/column
        cur.execute(
            "DELETE FROM finebin_details WHERE record_id = ? AND column_name = ?",
            (record_id, column_name)
        )

        # Insert new rows per group
        for group_id, bins in bin_merges.items():
            cur.execute(
                """
                INSERT INTO finebin_details (record_id, column_name, group_id, merged_bins)
                VALUES (?, ?, ?, ?)
                """,
                (record_id, column_name, str(group_id), json.dumps(bins))
            )

        conn.commit()
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/finebin-details/<int:record_id>/<string:column_name>', methods=['GET'])
def get_finebin_details(record_id, column_name):
    """
    Retrieve fine binning details for a specific record and column.
    """
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT group_id, merged_bins FROM finebin_details
            WHERE record_id = ? AND column_name = ?
            """,
            (record_id, column_name)
        )
        rows = cur.fetchall()
        conn.close()

        finebin_details = [
            {"group_id": row[0], "merged_bins": row[1]} for row in rows
        ]
        return jsonify(finebin_details)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
import numpy as np
import pandas as pd

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

    # Aggregate counts
    grouped = df.groupby("final_bin", observed=True).agg(
        Total=(target, "count"),
        Good=(target, lambda x: (x == 0).sum()),  # 0 = Good
        Bad=(target, lambda x: (x == 1).sum())    # 1 = Bad
    ).reset_index()

    total_good = grouped["Good"].sum()
    total_bad = grouped["Bad"].sum()
    n_bins = len(grouped)

    stats = []
    iv_total = 0.0

    # Laplace smoothing
    eps = 0.5
    adj_total_good = total_good + eps * n_bins
    adj_total_bad = total_bad + eps * n_bins

    for _, row in grouped.iterrows():
        # Apply smoothing to numerator and denominator consistently
        dist_good = (row["Good"] + eps) / adj_total_good
        dist_bad = (row["Bad"] + eps) / adj_total_bad

        woe = np.log(dist_good / dist_bad)
        iv = (dist_good - dist_bad) * woe
        iv_total += iv

        # Clean bin label for frontend
        bin_label = str(row["final_bin"])
        if "Interval" in bin_label:  # from pandas qcut
            bin_label = bin_label.replace("Interval", "").replace("(", "").replace("]", "")

        stats.append({
            "Bin": bin_label,
            "Good": int(row["Good"]),
            "Bad": int(row["Bad"]),
            "Total": int(row["Total"]),
            "WOE": round(float(woe), 4),
            "IV": round(float(iv), 4)
        })

    return round(float(iv_total), 4), stats

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
            #    Infer type: treat as discrete if non-object numeric with small cardinality OR object/categorical
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
                conn = get_db_connection()
                cur = conn.cursor()
                cur.execute(
                    "SELECT group_id, merged_bins FROM finebin_details WHERE record_id = ? AND column_name = ?",
                    (record_id, var)
                )
                rows = cur.fetchall()
                conn.close()
                if rows:
                    merges = {}
                    for row in rows:
                        try:
                            bins = json.loads(row[1])
                            merges[str(row[0])] = bins
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

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=True, host='0.0.0.0', port=port)
