import os
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
import sklearn
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

def generate_cluster_scatter(data, cluster_labels, columns, title="Cluster Distribution"):
    """Generate a scatter plot of the clusters with different colors for each cluster"""
    plt.figure(figsize=(10, 8))
    
    # Get unique clusters
    unique_clusters = np.unique(cluster_labels)
    num_clusters = len(unique_clusters)
    
    # Create colormap
    cmap = plt.cm.get_cmap('viridis', num_clusters)
    
    # For 1D data, create a scatter with jittered y-values
    if len(columns) == 1:
        # Add small random noise for y-axis to spread points vertically
        y_jitter = np.random.normal(0, 0.1, size=len(cluster_labels))
        
        for cluster_id in unique_clusters:
            mask = cluster_labels == cluster_id
            plt.scatter(data[mask], y_jitter[mask], alpha=0.6, 
                        label=f'Cluster {cluster_id+1}', color=cmap(cluster_id))
        
        plt.xlabel(columns[0])
        plt.ylabel('Jittered Value (for visualization only)')
        
    # For 2D data, create a regular scatter plot
    elif len(columns) == 2:
        for cluster_id in unique_clusters:
            mask = cluster_labels == cluster_id
            plt.scatter(data[mask, 0], data[mask, 1], alpha=0.6,
                        label=f'Cluster {cluster_id+1}', color=cmap(cluster_id))
        
        plt.xlabel(columns[0])
        plt.ylabel(columns[1])
        
    # For 3D+ data, use PCA to reduce to 2D for visualization
    else:
        from sklearn.decomposition import PCA
        
        # Reduce to 2D for visualization
        pca = PCA(n_components=2)
        data_2d = pca.fit_transform(data)
        
        for cluster_id in unique_clusters:
            mask = cluster_labels == cluster_id
            plt.scatter(data_2d[mask, 0], data_2d[mask, 1], alpha=0.6,
                        label=f'Cluster {cluster_id+1}', color=cmap(cluster_id))
        
        plt.xlabel('Principal Component 1')
        plt.ylabel('Principal Component 2')
        plt.text(0.05, 0.95, f'PCA applied: {len(columns)}-D → 2-D', 
                transform=plt.gca().transAxes, fontsize=9, va='top')
    
    # Add plot elements
    plt.title(title)
    plt.grid(linestyle='--', alpha=0.3)
    plt.legend(title="Clusters")
    plt.tight_layout()
    
    # Convert the plot to a base64-encoded string
    buffer = io.BytesIO()
    plt.savefig(buffer, format='png', dpi=100)
    buffer.seek(0)
    plot_data = base64.b64encode(buffer.getvalue()).decode('utf-8')
    plt.close()
    
    return plot_data

def perform_kmeans(dataframe, columns_to_cluster, k_range=K_RANGE, output_cluster_col_name="cluster", find_optimal_k=True):
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
                    # Use median instead of mean for more robust handling of outliers
                    median_value = df_cluster[col].median()
                    df_cluster[col].fillna(median_value, inplace=True)
                    print(f"Imputed NaNs in '{col}' using median: {median_value}")
                else:
                    # For non-numeric columns
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
            k_scores = {}
            
            # Calculate scores using multiple methods for each k
            for k in k_range:
                if k <= X_scaled.shape[0] and k > 1:  # Some metrics require at least 2 clusters
                    kmeans_model = KMeans(n_clusters=k, random_state=42, n_init=10)
                    cluster_labels = kmeans_model.fit_predict(X_scaled)
                    
                    # 1. Inertia (distortion)
                    distortion = kmeans_model.inertia_
                    distortions.append(distortion)
                    
                    # 2. Silhouette Score (higher is better)
                    silhouette = -1  # Default for k=1
                    try:
                        if k > 1:
                            silhouette = sklearn.metrics.silhouette_score(X_scaled, cluster_labels, random_state=42)
                    except:
                        silhouette = -1
                    
                    # 3. Calinski-Harabasz Index (higher is better)
                    ch_score = -1  # Default for k=1
                    try:
                        if k > 1:
                            ch_score = sklearn.metrics.calinski_harabasz_score(X_scaled, cluster_labels)
                    except:
                        ch_score = -1
                    
                    # 4. Davies-Bouldin Index (lower is better)
                    db_score = float('inf')  # Default for k=1
                    try:
                        if k > 1:
                            db_score = sklearn.metrics.davies_bouldin_score(X_scaled, cluster_labels)
                    except:
                        db_score = float('inf')
                    
                    # Store all scores
                    k_scores[k] = {
                        'distortion': distortion,
                        'silhouette': silhouette,
                        'ch_score': ch_score,
                        'db_score': db_score
                    }
                    valid_k_range.append(k)
            
            # Process scores only if we have valid data
            if len(valid_k_range) >= 2:
                # Normalize scores to 0-1 range for comparison
                normalized_scores = {}
                
                # 1. Process distortion (lower is better)
                if len(distortions) >= 2:
                    min_dist = min(distortions)
                    max_dist = max(distortions)
                    dist_range = max_dist - min_dist
                    
                    if dist_range > 0:
                        for k in k_scores:
                            # Invert so higher is better
                            normalized_scores.setdefault(k, {})
                            normalized_scores[k]['distortion'] = (max_dist - k_scores[k]['distortion']) / dist_range
                    
                    # Try to use KneeLocator for distortion
                    try:
                        if has_kneelocator:
                            kneedle = KneeLocator(valid_k_range, distortions, S=1.0, curve='convex', direction='decreasing')
                            if kneedle.elbow:
                                normalized_scores.setdefault(kneedle.elbow, {})
                                normalized_scores[kneedle.elbow].setdefault('votes', 0)
                                normalized_scores[kneedle.elbow]['votes'] = normalized_scores[kneedle.elbow].get('votes', 0) + 2  # Extra weight for elbow method
                    except Exception:
                        pass
                
                # 2. Process silhouette (higher is better)
                silhouette_values = [k_scores[k]['silhouette'] for k in k_scores if k_scores[k]['silhouette'] > -1]
                if silhouette_values:
                    min_sil = min(silhouette_values)
                    max_sil = max(silhouette_values)
                    sil_range = max_sil - min_sil
                    
                    if sil_range > 0:
                        for k in k_scores:
                            if k_scores[k]['silhouette'] > -1:
                                normalized_scores.setdefault(k, {})
                                normalized_scores[k]['silhouette'] = (k_scores[k]['silhouette'] - min_sil) / sil_range
                    
                    # Find k with maximum silhouette score
                    best_silhouette_k = max([k for k in k_scores], key=lambda k: k_scores[k]['silhouette'])
                    if best_silhouette_k > 0:
                        normalized_scores.setdefault(best_silhouette_k, {})
                        normalized_scores[best_silhouette_k].setdefault('votes', 0)
                        normalized_scores[best_silhouette_k]['votes'] = normalized_scores[best_silhouette_k].get('votes', 0) + 2  # Extra weight
                
                # 3. Process CH score (higher is better)
                ch_values = [k_scores[k]['ch_score'] for k in k_scores if k_scores[k]['ch_score'] > -1]
                if ch_values:
                    min_ch = min(ch_values)
                    max_ch = max(ch_values)
                    ch_range = max_ch - min_ch
                    
                    if ch_range > 0:
                        for k in k_scores:
                            if k_scores[k]['ch_score'] > -1:
                                normalized_scores.setdefault(k, {})
                                normalized_scores[k]['ch_score'] = (k_scores[k]['ch_score'] - min_ch) / ch_range
                    
                    # Find k with maximum CH score
                    best_ch_k = max([k for k in k_scores], key=lambda k: k_scores[k]['ch_score'])
                    if best_ch_k > 0:
                        normalized_scores.setdefault(best_ch_k, {})
                        normalized_scores[best_ch_k].setdefault('votes', 0)
                        normalized_scores[best_ch_k]['votes'] = normalized_scores[best_ch_k].get('votes', 0) + 1
                
                # 4. Process DB score (lower is better)
                db_values = [k_scores[k]['db_score'] for k in k_scores if k_scores[k]['db_score'] < float('inf')]
                if db_values:
                    min_db = min(db_values)
                    max_db = max(db_values)
                    db_range = max_db - min_db
                    
                    if db_range > 0:
                        for k in k_scores:
                            if k_scores[k]['db_score'] < float('inf'):
                                normalized_scores.setdefault(k, {})
                                # Invert so higher is better
                                normalized_scores[k]['db_score'] = (max_db - k_scores[k]['db_score']) / db_range
                    
                    # Find k with minimum DB score
                    best_db_k = min([k for k in k_scores], key=lambda k: k_scores[k]['db_score'])
                    if best_db_k > 0:
                        normalized_scores.setdefault(best_db_k, {})
                        normalized_scores[best_db_k].setdefault('votes', 0)
                        normalized_scores[best_db_k]['votes'] = normalized_scores[best_db_k].get('votes', 0) + 1
                
                # Calculate aggregate scores and make final decision
                final_scores = {}
                for k in normalized_scores:
                    # Sum up normalized scores (all metrics now have higher=better orientation)
                    metrics = ['distortion', 'silhouette', 'ch_score', 'db_score']
                    score_values = [normalized_scores[k].get(metric, 0) for metric in metrics]
                    score_count = sum(1 for x in score_values if x > 0)
                    
                    if score_count > 0:
                        final_scores[k] = sum(score_values) / score_count + normalized_scores[k].get('votes', 0) * 0.2
                
                # Choose k with the highest score
                if final_scores:
                    optimal_k = max(final_scores.items(), key=lambda x: x[1])[0]
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

        # Generate scatter plot of clusters
        scatter_plot = generate_cluster_scatter(
            X,  # Use original unscaled data for better interpretability
            cluster_labels,
            columns_to_cluster,
            f"Scatter Plot of {optimal_k} Clusters for {', '.join(columns_to_cluster)}"
        )
        result['plot'] = scatter_plot

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
    app.run(host='0.0.0.0', port=5000, debug=False)