from flask import Flask, request, jsonify
from flask_cors import CORS
import pandas as pd
import numpy as np
import os
import datetime

app = Flask(__name__)
CORS(app)

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
            # Save file content for reuse later
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

# ---------- BINNING LOGIC ----------
def coarse_binning_continuous(df, col, target='is_bad', bins=10):
    df = df.copy()

    try:
        df = df[[col, target]].dropna()

        # Ensure the column is numeric
        df[col] = pd.to_numeric(df[col], errors='coerce')

        # Sort the dataframe by the column to bin
        df = df.sort_values(by=col).reset_index(drop=True)

        # Create equal-sized bins by index slicing (10% each)
        total_rows = df.shape[0]
        bin_size = total_rows // bins
        labels = []

        for i in range(bins):
            start_idx = i * bin_size
            end_idx = (i + 1) * bin_size if i < bins - 1 else total_rows

            bin_label = f"Bin {i+1}"
            labels.extend([bin_label] * (end_idx - start_idx))

        df['bin'] = labels

        # Now group and compute stats
        stats = df.groupby('bin')[target].agg(['count', 'sum'])
        stats['good'] = stats['count'] - stats['sum']
        stats['freq'] = stats['count'] / total_rows * 100
        stats['bad_rate'] = stats['sum'] / stats['count'] * 100

        # Round for clarity
        stats = stats.reset_index()
        stats['freq'] = stats['freq'].round(4)
        stats['bad_rate'] = stats['bad_rate'].round(4)

        return stats

    except Exception as e:
        return pd.DataFrame([{"error": f"Binning failed for {col}: {str(e)}"}])



def coarse_binning_discrete(df, col, target='is_bad', threshold=0.5):
    df = df.copy()
    try:
        df = df[[col, target]].dropna()
        stats = df.groupby(col)[target].agg(['count', 'sum']).reset_index()
        stats['good'] = stats['count'] - stats['sum']
        stats['bad_rate'] = stats['sum'] / stats['count'] * 100

        # Round float column
        stats['bad_rate'] = stats['bad_rate'].round(4)

        return stats
    except Exception as e:
        return pd.DataFrame([{"error": f"Binning failed for {col}: {str(e)}"}])



def auto_merge_discrete_bins(df, col, target='is_bad', threshold=0.5):
    df = df[[col, target]].dropna()
    stats = df.groupby(col)[target].agg(['count', 'sum']).reset_index()
    stats['good'] = stats['count'] - stats['sum']
    stats['bad_rate'] = (stats['sum'] / stats['count']) * 100

    # Sort by bad rate
    stats = stats.sort_values('bad_rate').reset_index(drop=True)

    # Auto merge adjacent groups within threshold
    merged_bins = []
    current_bin = [stats.iloc[0]]

    for i in range(1, len(stats)):
        prev = current_bin[-1]
        curr = stats.iloc[i]
        if abs(prev['bad_rate'] - curr['bad_rate']) <= threshold:
            current_bin.append(curr)
        else:
            # merge current_bin
            merged = {
                col: ', '.join([str(x[col]) for x in current_bin]),
                'count': sum(x['count'] for x in current_bin),
                'sum': sum(x['sum'] for x in current_bin),
            }
            merged['good'] = merged['count'] - merged['sum']
            merged['bad_rate'] = (merged['sum'] / merged['count']) * 100
            merged_bins.append(merged)
            current_bin = [curr]

    # Final merge
    if current_bin:
        merged = {
            col: ', '.join([str(x[col]) for x in current_bin]),
            'count': sum(x['count'] for x in current_bin),
            'sum': sum(x['sum'] for x in current_bin),
        }
        merged['good'] = merged['count'] - merged['sum']
        merged['bad_rate'] = (merged['sum'] / merged['count']) * 100
        merged_bins.append(merged)

    return pd.DataFrame(merged_bins)



@app.route('/api/univariate-analysis', methods=['POST'])
def univariate_analysis():
    try:
        req = request.get_json()
        discrete_cols = req['discrete']
        continuous_cols = req['continuous']
        target = req['target']

        df = pd.read_csv("uploaded.csv")

        if target not in df.columns:
            return jsonify({"error": f"Target column '{target}' not found."}), 400

        df[target] = df[target].fillna(0).astype(int)

        results = {}

        for col in discrete_cols:
            if col != target:
                stats = coarse_binning_discrete(df, col, target)
                results[col] = {
                    'type': 'discrete',
                    'stats': stats.to_dict(orient='records')
                }

        for col in continuous_cols:
            if col != target:
                stats = coarse_binning_continuous(df, col, target)
                results[col] = {
                    'type': 'continuous',
                    'stats': stats.to_dict(orient='records')
                }

        return jsonify(results)

    except Exception as e:
        return jsonify({"error": f"Univariate failed: {str(e)}"}), 500

# Health check
@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({"status": "OK", "time": str(datetime.datetime.now())})


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=True, host='0.0.0.0', port=port)
