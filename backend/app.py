from flask import Flask, request, jsonify
from flask_cors import CORS
import pandas as pd
import numpy as np
import os
import datetime

app = Flask(__name__)
CORS(app)

# ----------- Upload CSV -----------
@app.route('/api/upload-csv', methods=['POST'])
def upload_csv():
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400
    if file and file.filename.endswith('.csv'):
        try:
            df = pd.read_csv(file)
            df.to_csv("uploaded.csv", index=False)
            return jsonify({
                "success": True,
                "columns": df.columns.tolist(),
                "rowCount": len(df),
                "timestamp": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    return jsonify({"error": "Not a CSV file"}), 400

# ----------- Target Distribution -----------
@app.route('/api/target-distribution', methods=['POST'])
def target_distribution():
    try:
        df = pd.read_csv("uploaded.csv")
        data = request.get_json()
        col = data['column']
        counts = df[col].value_counts().to_dict()
        return jsonify(counts)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ----------- Coarse Binning: Continuous -----------
def coarse_bin_continuous(df, var, target, bins=10):
    try:
        binned, _ = pd.qcut(df[var], q=bins, retbins=True, labels=False, duplicates='drop')
        n_bins = len(np.unique(binned.dropna()))
        df[f'{var}_binned'] = pd.qcut(df[var], q=n_bins, labels=range(1, n_bins + 1), duplicates='drop')
    except ValueError:
        df[f'{var}_binned'] = 1

    tab = pd.crosstab(df[f'{var}_binned'], df[target])
    tab.columns = ['Good', 'Bad']
    tab['Total'] = tab['Good'] + tab['Bad']
    tab['Freq%'] = (tab['Total'] / tab['Total'].sum()) * 100
    tab['Bad Rate'] = (tab['Bad'] / tab['Total']) * 100
    return tab.reset_index(), df[f'{var}_binned']

# ----------- Coarse Binning: Discrete -----------
def coarse_bin_discrete(df, var, target, bad_rate_diff=0.5):
    tab = pd.crosstab(df[var], df[target])
    tab.columns = ['Good', 'Bad']
    tab['Total'] = tab['Good'] + tab['Bad']
    tab['Bad Rate'] = (tab['Bad'] / tab['Total']) * 100
    tab = tab.sort_values('Bad Rate')

    bin_mapping = {}
    current_bin = 1
    prev_bad_rate = tab['Bad Rate'].iloc[0]

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

    return final_tab.reset_index(), df[f'{var}_binned'], bin_mapping

# ----------- Fine Binning: Continuous -----------
def fine_bin_continuous(df, var, target, bin_merges):
    binned_col = f'{var}_binned'
    fine_binned_col = f'{var}_fine_binned'

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

    return cross_tab.reset_index(), df[fine_binned_col]

# ----------- Fine Binning: Discrete -----------
def fine_bin_discrete(df, var, target, bin_merges):
    binned_col = f'{var}_binned'
    fine_binned_col = f'{var}_fine_binned'

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

    return cross_tab.reset_index(), df[fine_binned_col]

# ----------- Cross Tab View -----------
def create_cross_tab_view(df, var, target):
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

# ----------- Fine Binning API -----------
@app.route('/api/fine-bin', methods=['POST'])
def fine_bin_api():
    try:
        req = request.get_json()
        var = req['variable']
        target = req['target']
        bin_merges = req['bin_merges']
        var_type = req['type']  # 'continuous' or 'discrete'

        df = pd.read_csv("uploaded.csv")
        if target not in df.columns or var not in df.columns:
            return jsonify({"error": f"Column '{target}' or '{var}' not found."}), 400

        df[target] = df[target].fillna(0).astype(int)

        # Perform coarse binning first if not already done
        if var_type == 'continuous':
            _, df[f'{var}_binned'] = coarse_bin_continuous(df, var, target)
            tab, _ = fine_bin_continuous(df, var, target, bin_merges)
        else:
            _, df[f'{var}_binned'], _ = coarse_bin_discrete(df, var, target)
            tab, _ = fine_bin_discrete(df, var, target, bin_merges)

        # Save the updated dataframe
        df.to_csv("uploaded.csv", index=False)

        return jsonify({
            "success": True,
            "stats": tab.to_dict(orient='records')
        })

    except Exception as e:
        return jsonify({"error": f"Fine binning failed: {str(e)}"}), 500

# ----------- Cross Tab View API -----------
@app.route('/api/cross-tab-view', methods=['POST'])
def cross_tab_view_api():
    try:
        req = request.get_json()
        variables = req['variables']
        target = req['target']

        df = pd.read_csv("uploaded.csv")
        if target not in df.columns:
            return jsonify({"error": f"Target column '{target}' not found."}), 400

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
        return jsonify({"error": f"Cross tab view failed: {str(e)}"}), 500

# ----------- Univariate Analysis API -----------
@app.route('/api/univariate-analysis', methods=['POST'])
def univariate_analysis():
    try:
        req = request.get_json()
        discrete_cols = req.get('discrete', [])
        continuous_cols = req.get('continuous', [])
        target = req['target']

        df = pd.read_csv("uploaded.csv")
        if target not in df.columns:
            return jsonify({"error": f"Target column '{target}' not found."}), 400

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
        return jsonify({"error": f"Univariate failed: {str(e)}"}), 500

# ----------- Health Check -----------
@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({"status": "OK", "time": str(datetime.datetime.now())})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=True, host='0.0.0.0', port=port)