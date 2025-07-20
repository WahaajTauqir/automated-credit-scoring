from flask import Flask, request, jsonify
from flask_cors import CORS
import pandas as pd
import numpy as np
import os
import datetime
from math import ceil

app = Flask(__name__)
CORS(app)

# ----------- Upload CSV -----------
@app.route('/api/upload-csv', methods=['POST'])
def upload_csv():
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

        binned, _ = pd.qcut(df[var], q=bins, retbins=True, labels=False, duplicates='drop')
        n_bins = len(np.unique(binned.dropna()))
        if n_bins == 0:
            raise ValueError(f"No valid bins created for '{var}'")
        df[f'{var}_binned'] = pd.qcut(df[var], q=n_bins, labels=range(1, n_bins + 1), duplicates='drop')

        tab = pd.crosstab(df[f'{var}_binned'], df[target])
        tab.columns = ['Good', 'Bad']
        tab['Total'] = tab['Good'] + tab['Bad']
        tab['Freq%'] = (tab['Total'] / tab['Total'].sum()) * 100
        tab['Bad Rate'] = (tab['Bad'] / tab['Total']) * 100
        tab = tab.reset_index()
        columns_order = [f'{var}_binned'] + [col for col in tab.columns if col != f'{var}_binned']
        tab = tab[columns_order]
        return tab, df[f'{var}_binned']
    except Exception as e:
        raise ValueError(f"Coarse binning (continuous) failed for '{var}': {str(e)}")
# ----------- Coarse Binning: Discrete -----------
def coarse_bin_discrete(df, var, target, bad_rate_diff=0.5):
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
        columns_order = [f'{var}_binned'] + [col for col in final_tab.columns if col != f'{var}_binned']
        final_tab = final_tab[columns_order]
        return final_tab, df[f'{var}_binned'], bin_mapping
    except Exception as e:
        raise ValueError(f"Coarse binning (discrete) failed for '{var}': {str(e)}")
# ----------- Dynamic Bin Merging: Continuous -----------
def dynamic_bin_merges_continuous(df, var, target, coarse_bins):
    try:
        n_coarse_bins = len(np.unique(df[f'{var}_binned'].dropna()))
        if n_coarse_bins == 0:
            raise ValueError(f"No valid coarse bins for '{var}'")
        target_fine_bins = min(max(3, ceil(n_coarse_bins ** 0.5)), 5)  # Dynamic: 3 to 5 bins
        bins_per_group = ceil(n_coarse_bins / target_fine_bins)

        bin_merges = {}
        current_fine_bin = 1
        for i in range(1, n_coarse_bins + 1):
            fine_bin = min(current_fine_bin, target_fine_bins)
            bin_merges[fine_bin] = bin_merges.get(fine_bin, []) + [i]
            if i % bins_per_group == 0:
                current_fine_bin += 1

        return bin_merges
    except Exception as e:
        raise ValueError(f"Dynamic bin merging (continuous) failed for '{var}': {str(e)}")

# ----------- Dynamic Bin Merging: Discrete -----------
def dynamic_bin_merges_discrete(df, var, target, bin_mapping):
    try:
        tab = pd.crosstab(df[f'{var}_binned'], df[target])
        tab.columns = ['Good', 'Bad']
        tab['Total'] = tab['Good'] + tab['Bad']
        tab['Bad Rate'] = (tab['Bad'] / tab['Total']) * 100
        tab = tab.sort_values('Bad Rate')

        n_coarse_bins = len(np.unique(df[f'{var}_binned'].dropna()))
        if n_coarse_bins == 0:
            raise ValueError(f"No valid coarse bins for '{var}'")
        target_fine_bins = min(max(3, ceil(n_coarse_bins ** 0.5)), 5)  # Dynamic: 3 to 5 bins
        bins_per_group = ceil(n_coarse_bins / target_fine_bins)

        bin_merges = {}
        current_fine_bin = 1
        prev_bad_rate = tab['Bad Rate'].iloc[0] if not tab.empty else 0
        count = 0

        for idx, row in tab.iterrows():
            if count >= bins_per_group and abs(row['Bad Rate'] - prev_bad_rate) > 0.5:
                current_fine_bin += 1
                count = 0
            fine_bin = min(current_fine_bin, target_fine_bins)
            bin_merges[fine_bin] = bin_merges.get(fine_bin, []) + [idx]
            prev_bad_rate = row['Bad Rate']
            count += 1

        return bin_merges
    except Exception as e:
        raise ValueError(f"Dynamic bin merging (discrete) failed for '{var}': {str(e)}")

# ----------- Fine Binning: Continuous -----------
def fine_bin_continuous(df, var, target, bin_merges=None):
    try:
        binned_col = f'{var}_binned'
        fine_binned_col = f'{var}_fine_binned'

        if bin_merges is None:
            bin_merges = dynamic_bin_merges_continuous(df, var, target, coarse_bins=10)

        bin_map = {}
        for new_bin, old_bins in bin_merges.items():
            for old_bin in old_bins:
                bin_map[old_bin] = new_bin

        df[fine_binned_col] = df[binned_col].map(bin_map)

        cross_tab = pd.crosstab(df[fine_binned_col], df[target])
        cross_tab.columns = ['Good', 'Bad']
        cross_tab['Total'] = cross_tab['Good'] + cross_tab['Bad']
        cross_tab['Freq%'] = (cross_tab['Total'] / cross_tab['Total'].sum()) * 100
        cross_tab['Bad Rate'] = (cross_tab['Bad'] / cross_tab['Total']) * 100
        cross_tab = cross_tab.reset_index()
        columns_order = [fine_binned_col] + [col for col in cross_tab.columns if col != fine_binned_col]
        cross_tab = cross_tab[columns_order]
        return cross_tab, df[fine_binned_col], bin_merges
    except Exception as e:
        raise ValueError(f"Fine binning (continuous) failed for '{var}': {str(e)}")

# ----------- Fine Binning: Discrete -----------
def fine_bin_discrete(df, var, target, bin_merges=None, bin_mapping=None):
    try:
        binned_col = f'{var}_binned'
        fine_binned_col = f'{var}_fine_binned'

        if bin_merges is None:
            bin_merges = dynamic_bin_merges_discrete(df, var, target, bin_mapping)

        bin_map = {}
        for new_bin, old_bins in bin_merges.items():
            for old_bin in old_bins:
                bin_map[old_bin] = new_bin

        df[fine_binned_col] = df[binned_col].map(bin_map)

        cross_tab = pd.crosstab(df[fine_binned_col], df[target])
        cross_tab.columns = ['Good', 'Bad']
        cross_tab['Total'] = cross_tab['Good'] + cross_tab['Bad']
        cross_tab['Freq%'] = (cross_tab['Total'] / cross_tab['Total'].sum()) * 100
        cross_tab['Bad Rate'] = (cross_tab['Bad'] / cross_tab['Total']) * 100
        cross_tab = cross_tab.reset_index()
        columns_order = [fine_binned_col] + [col for col in cross_tab.columns if col != fine_binned_col]
        cross_tab = cross_tab[columns_order]
        return cross_tab, df[fine_binned_col], bin_merges
    except Exception as e:
        raise ValueError(f"Fine binning (discrete) failed for '{var}': {str(e)}")

# ----------- Cross Tab View -----------
def create_cross_tab_view(df, var, target):
    try:
        binned_col = f'{var}_fine_binned' if f'{var}_fine_binned' in df.columns else f'{var}_binned'
        if binned_col not in df.columns:
            return None, None

        tab = pd.crosstab(df[binned_col], df[target])
        tab.columns = ['Good', 'Bad']
        tab['Total'] = tab['Good'] + tab['Bad']
        tab['Freq%'] = (tab['Total'] / tab['Total'].sum()) * 100
        tab['Bad Rate'] = (tab['Bad'] / tab['Total']) * 100
        tab['Freq%'] = tab['Freq%'].round(1)
        tab['Bad Rate'] = tab['Bad Rate'].round(1)

        return f"{var} (Binned) * {target} Crosstabulation", tab.reset_index()
    except Exception as e:
        raise ValueError(f"Cross tab view failed for '{var}': {str(e)}")

# ----------- Fine Binning API -----------
@app.route('/api/fine-bin', methods=['POST'])
def fine_bin_api():
    try:
        req = request.get_json()
        var = req.get('variable')
        target = req.get('target')
        var_type = req.get('type')  # 'continuous' or 'discrete'
        bin_merges = req.get('bin_merges', None)  # Allow optional bin_merges from frontend

        if not var or not target or not var_type:
            return jsonify({"error": "Missing required fields: variable, target, or type"}), 400

        df = pd.read_csv("uploaded.csv")
        if target not in df.columns or var not in df.columns:
            return jsonify({"error": f"Column '{target}' or '{var}' not found in dataset"}), 400

        df[target] = df[target].fillna(0).astype(int)

        # Perform coarse binning first if not already done
        if var_type == 'continuous':
            _, df[f'{var}_binned'] = coarse_bin_continuous(df, var, target)
            tab, _, bin_merges = fine_bin_continuous(df, var, target, bin_merges)
        else:
            _, df[f'{var}_binned'], bin_mapping = coarse_bin_discrete(df, var, target)
            tab, _, bin_merges = fine_bin_discrete(df, var, target, bin_merges, bin_mapping)

        # Save the updated dataframe
        df.to_csv("uploaded.csv", index=False)

        return jsonify({
            "success": True,
            "stats": tab.to_dict(orient='records'),
            "bin_merges": bin_merges  # Return the used bin merges
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ----------- Cross Tab View API -----------
@app.route('/api/cross-tab-view', methods=['POST'])
def cross_tab_view_api():
    try:
        req = request.get_json()
        variables = req.get('variables', [])
        target = req.get('target')

        if not target or not variables:
            return jsonify({"error": "Missing required fields: variables or target"}), 400

        df = pd.read_csv("uploaded.csv")
        if target not in df.columns:
            return jsonify({"error": f"Target column '{target}' not found in dataset"}), 400

        df[target] = df[target].fillna(0).astype(int)
        results = {}

        for var in variables:
            title, tab = create_cross_tab_view(df, var, target)
            if tab is not None:
                results[var] = {
                    'title': title,
                    'stats': tab.to_dict(orient='records')
                }

        return jsonify(results)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ----------- Univariate Analysis API -----------
@app.route('/api/univariate-analysis', methods=['POST'])
def univariate_analysis():
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
    return jsonify({"status": "OK", "time": str(datetime.datetime.now())})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=True, host='0.0.0.0', port=port)