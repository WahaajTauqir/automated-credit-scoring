from flask import Flask, request, jsonify
from flask_cors import CORS
import pandas as pd
import numpy as np
import json
from kmeans_clustering import perform_kmeans

app = Flask(__name__)
CORS(app)

class NumpyJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.floating):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, float) and np.isnan(obj):
            return None
        return super().default(obj)

app.json_encoder = NumpyJSONEncoder

def convert_numpy_types(obj):
    if isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        if np.isnan(obj):
            return None
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, dict):
        return {key: convert_numpy_types(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [convert_numpy_types(item) for item in obj]
    elif isinstance(obj, float) and np.isnan(obj):
        return None
    else:
        return obj

@app.route('/api/upload-csv', methods=['POST'])
def upload_csv():
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file part'}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400

        if file:
            df = pd.read_csv(file)
            columns = df.columns.tolist()
            df = df.replace({np.nan: None})
            records = df.to_dict(orient='records')
            data = convert_numpy_types(records)

            return jsonify({
                'success': True,
                'columns': columns,
                'data': data
            })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/cluster', methods=['POST'])
def cluster_data():
    try:
        data = request.json

        if not data or 'data' not in data or 'columns' not in data:
            return jsonify({'success': False, 'error': 'Invalid request format. Need "data" and "columns"'}), 400

        try:
            df = pd.DataFrame(data['data'])
            df = df.replace({None: np.nan})
        except Exception as e:
            return jsonify({'success': False, 'error': f'Error creating DataFrame: {str(e)}'}), 400

        columns_to_cluster = data['columns']
        if not columns_to_cluster or not isinstance(columns_to_cluster, list):
            return jsonify({'success': False, 'error': 'Invalid columns list'}), 400

        k_range = range(1, data.get('max_k', 11))
        find_optimal_k = data.get('find_optimal_k', True)
        output_col = data.get('output_column', 'cluster')
        true_labels = data.get('true_labels')

        individual_results = {}
        for col in columns_to_cluster:
            result = perform_kmeans(df, [col], k_range, f"{col}_cluster", find_optimal_k, true_labels)
            if result['error'] is None:
                cluster_info = convert_numpy_types(result['cluster_info'])
                explanations = convert_numpy_types(result.get('explanations', {}))
                individual_results[col] = {
                    'k': int(result['k_used']),
                    'cluster_info': cluster_info,
                    'plot': result['plot'],
                    'explanations': explanations,
                    'validation_metrics': result['validation_metrics']
                }

        combined_result = None
        if len(columns_to_cluster) >= 2:
            result = perform_kmeans(df, columns_to_cluster, k_range, "combined_cluster", find_optimal_k, true_labels)
            if result['error'] is None:
                cluster_info = convert_numpy_types(result['cluster_info'])
                explanations = convert_numpy_types(result.get('explanations', {}))
                combined_result = {
                    'k': int(result['k_used']),
                    'cluster_info': cluster_info,
                    'plot': result['plot'],
                    'explanations': explanations,
                    'validation_metrics': result['validation_metrics']
                }

        return jsonify({
            'success': True,
            'individual_results': individual_results,
            'combined_result': combined_result,
            'error': None
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)