from flask import Flask, request, jsonify
import sqlite3
from flask_cors import CORS
import pandas as pd
import numpy as np
import os
import datetime
from math import ceil


app = Flask(__name__)
CORS(app, origins=["http://localhost:5173"])
@app.route('/api/record/<int:record_id>', methods=['DELETE'])
def delete_record(record_id):
    """
    Delete a specific analysis record by ID.
    """
    try:
        conn = get_db_connection()
        cur = conn.cursor()
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
            return jsonify(dict(row))
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
            df.to_csv("uploaded.csv", index=False)
            return jsonify({
                "success": True,
                "columns": df.columns.tolist(),
                "rowCount": len(df),
                "timestamp": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
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
def fine_bin_continuous(df, var, target, bin_merges=None):
    """
    Performs fine binning by merging coarse bins for a continuous variable.
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
    """
    Performs fine binning (merging of coarse bins) via a REST API endpoint,
    expects manual bin_merges dict from frontend.
    """
    try:
        req = request.get_json()
        var = req.get('variable')
        target = req.get('target')
        var_type = req.get('type')
        bin_merges = req.get('bin_merges')

        if not var or not target or not var_type or bin_merges is None:
            return jsonify({"error": "Missing required fields: variable, target, type, or bin_merges"}), 400

        df = pd.read_csv("uploaded.csv")
        if target not in df.columns or var not in df.columns:
            return jsonify({"error": f"Column '{target}' or '{var}' not found in dataset"}), 400

        df[target] = df[target].fillna(0).astype(int)

        if var_type == 'continuous':
            # You still need to do coarse binning to get the base bins first
            _, df[f'{var}_binned'] = coarse_bin_continuous(df, var, target)
            tab, _, bin_merges = fine_bin_continuous(df, var, target, bin_merges)
        else:
            _, df[f'{var}_binned'], bin_mapping = coarse_bin_discrete(df, var, target)
            tab, _, bin_merges = fine_bin_discrete(df, var, target, bin_merges, bin_mapping)

        df.to_csv("uploaded.csv", index=False)

        return jsonify({
            "success": True,
            "stats": tab.to_dict(orient='records'),
            "bin_merges": bin_merges
        })
    except Exception as e:
        import traceback
        print(traceback.format_exc())  # print full error stack trace in your server console
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

        df[target] = df[target].fillna(0).astype(int)
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

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=True, host='0.0.0.0', port=port)
