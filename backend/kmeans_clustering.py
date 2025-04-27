import os
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
import matplotlib.pyplot as plt
import io
import base64
from flask import Flask, request, jsonify
from flask_cors import CORS

# Try to import kneed, handle if not found
try:
    from kneed import KneeLocator
    has_kneelocator = True
except ImportError:
    print("Warning: 'kneed' library not found. Optimal K will default to 3 or require manual input.")
    print("You can install it using: pip install kneed")
    has_kneelocator = False

# Default configuration
DEFAULT_K = 3
K_RANGE = range(1, 11)

def generate_cluster_histogram(cluster_labels, num_clusters, title="Cluster Distribution"):
    """Generate a histogram of the cluster sizes"""
    plt.figure(figsize=(10, 6))

    # Count the number of data points in each cluster
    unique, counts = np.unique(cluster_labels, return_counts=True)

    # Create the histogram
    plt.bar(range(num_clusters), counts, align='center', alpha=0.7)
    plt.xlabel('Cluster')
    plt.ylabel('Number of Data Points')
    plt.title(title)
    plt.xticks(range(num_clusters), [f'Cluster {i+1}' for i in range(num_clusters)])
    plt.grid(axis='y', linestyle='--', alpha=0.7)

    # Convert the plot to a base64-encoded string
    buffer = io.BytesIO()
    plt.savefig(buffer, format='png')
    buffer.seek(0)
    plot_data = base64.b64encode(buffer.getvalue()).decode('utf-8')
    plt.close()

    return plot_data


def perform_kmeans(dataframe, columns_to_cluster, k_range=K_RANGE, output_cluster_col_name="cluster", find_optimal_k=True):
    """
    Performs K-Means clustering on specified columns of a DataFrame.

    Args:
        dataframe (pd.DataFrame): The input DataFrame.
        columns_to_cluster (list): A list of column names to use for clustering.
        k_range (range): Range of K values to test for the Elbow method.
        output_cluster_col_name (str): Name for the new column storing cluster labels.
        find_optimal_k (bool): Whether to automatically find K using Elbow/KneeLocator.
                              If False or KneeLocator fails, uses DEFAULT_K.

    Returns:
        dict: Dictionary containing:
            - 'df': DataFrame with the added cluster label column
            - 'k_used': The number of clusters (K) used
            - 'cluster_info': Information about each cluster
            - 'centers': Cluster centers in original scale
            - 'plot': Base64 encoded plot image (if visualization enabled)
            - 'error': Error message if any
    """
    result = {
        'df': None,
        'k_used': -1,
        'cluster_info': [],
        'centers': None,
        'plot': None,
        'error': None
    }

    try:
        # --- Data Preparation ---
        # 1. Check if all columns exist
        missing_cols = [col for col in columns_to_cluster if col not in dataframe.columns]
        if missing_cols:
            result['error'] = f"The following columns were not found: {missing_cols}"
            return result

        # 2. Select the subset and create a copy
        df_cluster = dataframe[columns_to_cluster].copy()

        # 3. Handle missing values and check numeric types
        for col in columns_to_cluster:
            if df_cluster[col].isnull().any():
                if pd.api.types.is_numeric_dtype(df_cluster[col]):
                    mean_value = df_cluster[col].mean()
                    df_cluster[col].fillna(mean_value, inplace=True)
                else:
                    result['error'] = f"Column '{col}' has NaNs and is not numeric"
                    return result
            if not pd.api.types.is_numeric_dtype(df_cluster[col]):
                result['error'] = f"Column '{col}' is not numeric (Type: {df_cluster[col].dtype})"
                return result

        # 4. Extract data as NumPy array
        if len(columns_to_cluster) == 1:
            X = df_cluster.values.reshape(-1, 1)
        else:
            X = df_cluster.values

        if X.shape[0] == 0:
            result['error'] = "No data available for clustering after preparation"
            return result

        # 5. Scale the data
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)

        # --- Determine Optimal K ---
        optimal_k = DEFAULT_K
        distortions = []

        if find_optimal_k:
            valid_k_range = []
            for k in k_range:
                if k <= X_scaled.shape[0]:
                    kmeans_model_elbow = KMeans(n_clusters=k, random_state=42, n_init=10)
                    kmeans_model_elbow.fit(X_scaled)
                    distortions.append(kmeans_model_elbow.inertia_)
                    valid_k_range.append(k)

            # Try to find optimal k using KneeLocator if available
            if has_kneelocator and len(valid_k_range) >= 2:
                try:
                    kneedle = KneeLocator(valid_k_range, distortions, S=1.0, curve='convex', direction='decreasing')
                    if kneedle.elbow:
                        optimal_k = kneedle.elbow
                except Exception:
                    pass  # Fall back to DEFAULT_K

        # --- Apply K-Means ---
        # Ensure optimal_k is valid
        if optimal_k > X_scaled.shape[0]:
            optimal_k = max(1, X_scaled.shape[0])
        if optimal_k <= 0:
            result['error'] = "Number of clusters must be positive"
            return result

        kmeans = KMeans(n_clusters=optimal_k, random_state=42, n_init=10)
        kmeans.fit(X_scaled)
        cluster_labels = kmeans.labels_

        # Add cluster labels to DataFrame
        dataframe = dataframe.copy()  # Don't modify the input DataFrame
        dataframe[output_cluster_col_name] = pd.Series(cluster_labels, index=df_cluster.index)
        dataframe[output_cluster_col_name] = dataframe[output_cluster_col_name].fillna(-1).astype(int)

        # Get cluster centers in original scale
        cluster_centers_original = scaler.inverse_transform(kmeans.cluster_centers_)
        centers_df = pd.DataFrame(cluster_centers_original, columns=columns_to_cluster)

        # Generate histogram plot of cluster sizes
        histogram_plot = generate_cluster_histogram(
            cluster_labels,
            optimal_k,
            f"Distribution of Data Points in {optimal_k} Clusters for {', '.join(columns_to_cluster)}"
        )
        result['plot'] = histogram_plot

        # Collect cluster information
        cluster_info = []
        for cluster_id in range(optimal_k):
            cluster_df = dataframe[dataframe[output_cluster_col_name] == cluster_id]
            cluster_data = {}

            # For each column in the cluster, get some representative data points
            for col in columns_to_cluster:
                cluster_data[col] = {
                    'center': centers_df.loc[cluster_id, col],
                    'min': cluster_df[col].min() if not cluster_df.empty else None,
                    'max': cluster_df[col].max() if not cluster_df.empty else None,
                    'mean': cluster_df[col].mean() if not cluster_df.empty else None
                }

            # Get sample data points (limited to 20 for performance)
            sample_size = min(20, len(cluster_df))
            sample_data = cluster_df.sample(n=sample_size) if not cluster_df.empty and sample_size > 0 else pd.DataFrame()

            # Convert to dictionary for JSON serialization
            sample_data_dict = []
            for idx, row in sample_data.iterrows():
                row_dict = {}
                for col in columns_to_cluster:
                    row_dict[col] = float(row[col]) if pd.api.types.is_numeric_dtype(row[col]) else str(row[col])
                sample_data_dict.append(row_dict)

            cluster_info.append({
                'id': int(cluster_id),
                'count': int(cluster_df.shape[0]),
                'center': {col: float(centers_df.loc[cluster_id, col]) for col in columns_to_cluster},
                'column_stats': cluster_data,
                'sample_data': sample_data_dict
            })

        # Populate result
        result['df'] = dataframe
        result['k_used'] = optimal_k
        result['cluster_info'] = cluster_info
        result['centers'] = centers_df.to_dict(orient='records')

        return result

    except Exception as e:
        result['error'] = str(e)
        return result

# Flask application
app = Flask(__name__)
CORS(app)

@app.route('/api/cluster', methods=['POST'])
def cluster_data():
    try:
        # Get request data
        data = request.json

        if not data or 'data' not in data or 'columns' not in data:
            return jsonify({'success': False, 'error': 'Invalid request format. Need "data" and "columns"'}), 400

        # Convert data to DataFrame
        try:
            df = pd.DataFrame(data['data'])
        except Exception as e:
            return jsonify({'success': False, 'error': f'Error creating DataFrame: {str(e)}'}), 400

        columns_to_cluster = data['columns']
        if not columns_to_cluster or not isinstance(columns_to_cluster, list):
            return jsonify({'success': False, 'error': 'Invalid columns list'}), 400

        # Optional parameters
        k_range = range(1, data.get('max_k', 11))
        find_optimal_k = data.get('find_optimal_k', True)
        output_col = data.get('output_column', 'cluster')

        # Perform clustering for individual columns
        individual_results = {}
        for col in columns_to_cluster:
            result = perform_kmeans(df, [col], k_range, f"{col}_cluster", find_optimal_k)
            if result['error'] is None:
                individual_results[col] = {
                    'k': result['k_used'],
                    'cluster_info': result['cluster_info'],
                    'plot': result['plot']
                }

        # Perform clustering on combined columns
        combined_result = None
        if len(columns_to_cluster) >= 2:
            result = perform_kmeans(df, columns_to_cluster, k_range, "combined_cluster", find_optimal_k)
            if result['error'] is None:
                combined_result = {
                    'k': result['k_used'],
                    'cluster_info': result['cluster_info'],
                    'plot': result['plot']
                }

        # Return results
        return jsonify({
            'success': True,
            'individual_results': individual_results,
            'combined_result': combined_result,
            'error': None
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    # This block will execute if the script is run directly
    # For production, use a proper WSGI server
    app.run(host='0.0.0.0', port=5000, debug=False)