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
from sklearn import metrics
from sklearn.decomposition import PCA

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

def calculate_validation_metrics(X, labels, true_labels=None):
    """Calculate various cluster validation metrics"""
    validation_results = {}

    # Silhouette Score
    if len(np.unique(labels)) > 1:
        validation_results['silhouette_score'] = metrics.silhouette_score(X, labels)

    # Calinski-Harabasz Index
    validation_results['calinski_harabasz_score'] = metrics.calinski_harabasz_score(X, labels)

    # Davies-Bouldin Index
    validation_results['davies_bouldin_score'] = metrics.davies_bouldin_score(X, labels)

    # Adjusted Rand Index (if true labels are available)
    if true_labels is not None:
        validation_results['adjusted_rand_score'] = metrics.adjusted_rand_score(true_labels, labels)

    return validation_results

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

    plt.title(title)
    plt.grid(linestyle='--', alpha=0.3)
    plt.legend(title="Clusters")
    plt.tight_layout()

    buffer = io.BytesIO()
    plt.savefig(buffer, format='png', dpi=100)
    buffer.seek(0)
    plot_data = base64.b64encode(buffer.getvalue()).decode('utf-8')
    plt.close()

    return plot_data

def generate_cluster_profile_plot(cluster_stats, columns, title="Cluster Profile"):
    """Generate a radar chart showing how each cluster differs across dimensions"""
    plt.figure(figsize=(10, 8))

    categories = columns
    N = len(categories)

    angles = [n / float(N) * 2 * np.pi for n in range(N)]
    angles += angles[:1]

    ax = plt.subplot(111, polar=True)
    ax.set_theta_offset(np.pi / 2)
    ax.set_theta_direction(-1)

    plt.xticks(angles[:-1], categories)
    ax.set_rlabel_position(0)

    for cluster_id, stats in cluster_stats.items():
        values = [stats[col]['normalized_mean'] for col in columns]
        values += values[:1]
        ax.plot(angles, values, linewidth=1, linestyle='solid',
                label=f'Cluster {cluster_id+1}')
        ax.fill(angles, values, alpha=0.1)

    plt.legend(loc='upper right', bbox_to_anchor=(1.3, 1.1))
    plt.title(title, y=1.1)

    buffer = io.BytesIO()
    plt.savefig(buffer, format='png', dpi=100, bbox_inches='tight')
    buffer.seek(0)
    plot_data = base64.b64encode(buffer.getvalue()).decode('utf-8')
    plt.close()

    return plot_data

def calculate_feature_importance(cluster_info, columns):
    """Calculate feature importance for each cluster"""
    feature_importance = {}

    global_means = {col: np.mean([c['column_stats'][col]['mean']
                                  for c in cluster_info])
                    for col in columns}

    for cluster in cluster_info:
        cluster_id = cluster['id']
        importance_scores = {}

        for col in columns:
            cluster_mean = cluster['column_stats'][col]['mean']
            global_mean = global_means[col]
            std_dev = np.std([c['column_stats'][col]['mean']
                              for c in cluster_info])

            if std_dev > 0:
                importance = abs(cluster_mean - global_mean) / std_dev
            else:
                importance = 0

            importance_scores[col] = importance

        total = sum(importance_scores.values())
        if total > 0:
            importance_scores = {k: v/total for k, v in importance_scores.items()}

        feature_importance[cluster_id] = importance_scores

    return feature_importance

def generate_cluster_descriptions(cluster_info, columns, feature_importance):
    """Generate natural language descriptions of each cluster"""
    descriptions = []

    global_stats = {
        col: {
            'mean': np.mean([c['column_stats'][col]['mean'] for c in cluster_info]),
            'min': np.min([c['column_stats'][col]['min'] for c in cluster_info]),
            'max': np.max([c['column_stats'][col]['max'] for c in cluster_info])
        }
        for col in columns
    }

    for cluster in cluster_info:
        cluster_id = cluster['id']
        description_parts = []

        top_features = sorted(feature_importance[cluster_id].items(),
                              key=lambda x: x[1], reverse=True)[:3]

        for feature, importance in top_features:
            cluster_mean = cluster['column_stats'][feature]['mean']
            global_mean = global_stats[feature]['mean']

            if cluster_mean > global_mean * 1.2:
                relation = "higher than average"
            elif cluster_mean < global_mean * 0.8:
                relation = "lower than average"
            else:
                relation = "about average"

            description_parts.append(
                f"{feature} ({relation})"
            )

        description = (
                f"Cluster {cluster_id+1} is characterized by: " +
                ", ".join(description_parts) + ". " +
                f"It contains {cluster['count']} records " +
                f"({cluster['count']/sum(c['count'] for c in cluster_info):.1%} of total)."
        )

        descriptions.append({
            'cluster_id': cluster_id,
            'description': description,
            'top_features': [f[0] for f in top_features]
        })

    return descriptions

def perform_kmeans(dataframe, columns_to_cluster, k_range=K_RANGE, output_cluster_col_name="cluster", find_optimal_k=True, true_labels=None):
    result = {
        'df': None,
        'k_used': -1,
        'cluster_info': [],
        'centers': None,
        'plot': None,
        'error': None,
        'validation_metrics': None
    }

    try:
        # Data Preparation
        missing_cols = [col for col in columns_to_cluster if col not in dataframe.columns]
        if missing_cols:
            result['error'] = f"The following columns were not found: {missing_cols}"
            return result

        df_cluster = dataframe[columns_to_cluster].copy()

        for col in columns_to_cluster:
            if df_cluster[col].isnull().any():
                if pd.api.types.is_numeric_dtype(df_cluster[col]):
                    median_value = df_cluster[col].median()
                    df_cluster[col].fillna(median_value, inplace=True)
                else:
                    result['error'] = f"Column '{col}' has NaNs and is not numeric"
                    return result
            if not pd.api.types.is_numeric_dtype(df_cluster[col]):
                result['error'] = f"Column '{col}' is not numeric (Type: {df_cluster[col].dtype})"
                return result

        if len(columns_to_cluster) == 1:
            X = df_cluster.values.reshape(-1, 1)
        else:
            X = df_cluster.values

        if X.shape[0] == 0:
            result['error'] = "No data available for clustering after preparation"
            return result

        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)

        # Determine Optimal K
        optimal_k = DEFAULT_K
        distortions = []

        if find_optimal_k:
            valid_k_range = []
            k_scores = {}

            for k in k_range:
                if k <= X_scaled.shape[0] and k > 1:
                    kmeans_model = KMeans(n_clusters=k, random_state=42, n_init=10)
                    cluster_labels = kmeans_model.fit_predict(X_scaled)

                    distortion = kmeans_model.inertia_
                    distortions.append(distortion)

                    silhouette = -1
                    try:
                        if k > 1:
                            silhouette = sklearn.metrics.silhouette_score(X_scaled, cluster_labels, random_state=42)
                    except:
                        silhouette = -1

                    ch_score = -1
                    try:
                        if k > 1:
                            ch_score = sklearn.metrics.calinski_harabasz_score(X_scaled, cluster_labels)
                    except:
                        ch_score = -1

                    db_score = float('inf')
                    try:
                        if k > 1:
                            db_score = sklearn.metrics.davies_bouldin_score(X_scaled, cluster_labels)
                    except:
                        db_score = float('inf')

                    k_scores[k] = {
                        'distortion': distortion,
                        'silhouette': silhouette,
                        'ch_score': ch_score,
                        'db_score': db_score
                    }
                    valid_k_range.append(k)

            if len(valid_k_range) >= 2:
                normalized_scores = {}

                if len(distortions) >= 2:
                    min_dist = min(distortions)
                    max_dist = max(distortions)
                    dist_range = max_dist - min_dist

                    if dist_range > 0:
                        for k in k_scores:
                            normalized_scores.setdefault(k, {})
                            normalized_scores[k]['distortion'] = (max_dist - k_scores[k]['distortion']) / dist_range

                    try:
                        if has_kneelocator:
                            kneedle = KneeLocator(valid_k_range, distortions, S=1.0, curve='convex', direction='decreasing')
                            if kneedle.elbow:
                                normalized_scores.setdefault(kneedle.elbow, {})
                                normalized_scores[kneedle.elbow].setdefault('votes', 0)
                                normalized_scores[kneedle.elbow]['votes'] = normalized_scores[kneedle.elbow].get('votes', 0) + 2
                    except Exception:
                        pass

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

                    best_silhouette_k = max([k for k in k_scores], key=lambda k: k_scores[k]['silhouette'])
                    if best_silhouette_k > 0:
                        normalized_scores.setdefault(best_silhouette_k, {})
                        normalized_scores[best_silhouette_k].setdefault('votes', 0)
                        normalized_scores[best_silhouette_k]['votes'] = normalized_scores[best_silhouette_k].get('votes', 0) + 2

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

                    best_ch_k = max([k for k in k_scores], key=lambda k: k_scores[k]['ch_score'])
                    if best_ch_k > 0:
                        normalized_scores.setdefault(best_ch_k, {})
                        normalized_scores[best_ch_k].setdefault('votes', 0)
                        normalized_scores[best_ch_k]['votes'] = normalized_scores[best_ch_k].get('votes', 0) + 1

                db_values = [k_scores[k]['db_score'] for k in k_scores if k_scores[k]['db_score'] < float('inf')]
                if db_values:
                    min_db = min(db_values)
                    max_db = max(db_values)
                    db_range = max_db - min_db

                    if db_range > 0:
                        for k in k_scores:
                            if k_scores[k]['db_score'] < float('inf'):
                                normalized_scores.setdefault(k, {})
                                normalized_scores[k]['db_score'] = (max_db - k_scores[k]['db_score']) / db_range

                    best_db_k = min([k for k in k_scores], key=lambda k: k_scores[k]['db_score'])
                    if best_db_k > 0:
                        normalized_scores.setdefault(best_db_k, {})
                        normalized_scores[best_db_k].setdefault('votes', 0)
                        normalized_scores[best_db_k]['votes'] = normalized_scores[best_db_k].get('votes', 0) + 1

                final_scores = {}
                for k in normalized_scores:
                    metrics = ['distortion', 'silhouette', 'ch_score', 'db_score']
                    score_values = [normalized_scores[k].get(metric, 0) for metric in metrics]
                    score_count = sum(1 for x in score_values if x > 0)

                    if score_count > 0:
                        final_scores[k] = sum(score_values) / score_count + normalized_scores[k].get('votes', 0) * 0.2

                if final_scores:
                    optimal_k = max(final_scores.items(), key=lambda x: x[1])[0]

        # Apply K-Means
        if optimal_k > X_scaled.shape[0]:
            optimal_k = max(1, X_scaled.shape[0])
        if optimal_k <= 0:
            result['error'] = "Number of clusters must be positive"
            return result

        kmeans = KMeans(n_clusters=optimal_k, random_state=42, n_init=10)
        kmeans.fit(X_scaled)
        cluster_labels = kmeans.labels_

        dataframe = dataframe.copy()
        dataframe[output_cluster_col_name] = pd.Series(cluster_labels, index=df_cluster.index)
        dataframe[output_cluster_col_name] = dataframe[output_cluster_col_name].fillna(-1).astype(int)

        cluster_centers_original = scaler.inverse_transform(kmeans.cluster_centers_)
        centers_df = pd.DataFrame(cluster_centers_original, columns=columns_to_cluster)

        scatter_plot = generate_cluster_scatter(
            X,
            cluster_labels,
            columns_to_cluster,
            f"Scatter Plot of {optimal_k} Clusters for {', '.join(columns_to_cluster)}"
        )
        result['plot'] = scatter_plot

        # Calculate validation metrics
        result['validation_metrics'] = calculate_validation_metrics(
            X_scaled,
            cluster_labels,
            true_labels=true_labels
        )

        # Collect cluster information
        cluster_info = []
        for cluster_id in range(optimal_k):
            cluster_df = dataframe[dataframe[output_cluster_col_name] == cluster_id]
            cluster_data = {}

            for col in columns_to_cluster:
                cluster_data[col] = {
                    'center': centers_df.loc[cluster_id, col],
                    'min': cluster_df[col].min() if not cluster_df.empty else None,
                    'max': cluster_df[col].max() if not cluster_df.empty else None,
                    'mean': cluster_df[col].mean() if not cluster_df.empty else None
                }

            sample_size = min(20, len(cluster_df))
            sample_data = cluster_df.sample(n=sample_size) if not cluster_df.empty and sample_size > 0 else pd.DataFrame()

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

        # Add explainability features
        feature_importance = calculate_feature_importance(cluster_info, columns_to_cluster)
        cluster_descriptions = generate_cluster_descriptions(cluster_info, columns_to_cluster, feature_importance)

        # Generate cluster profile plot
        global_stats = {
            col: {
                'min': np.min([c['column_stats'][col]['min'] for c in cluster_info]),
                'max': np.max([c['column_stats'][col]['max'] for c in cluster_info])
            }
            for col in columns_to_cluster
        }

        cluster_stats = {
            c['id']: {
                col: {
                    'normalized_mean': (c['column_stats'][col]['mean'] - global_stats[col]['min']) /
                                       (global_stats[col]['max'] - global_stats[col]['min'])
                }
                for col in columns_to_cluster
            }
            for c in cluster_info
        }

        profile_plot = generate_cluster_profile_plot(
            cluster_stats,
            columns_to_cluster,
            f"Cluster Profiles for {', '.join(columns_to_cluster)}"
        )

        result['df'] = dataframe
        result['k_used'] = optimal_k
        result['cluster_info'] = cluster_info
        result['centers'] = centers_df.to_dict(orient='records')
        result['explanations'] = {
            'feature_importance': feature_importance,
            'cluster_descriptions': cluster_descriptions,
            'profile_plot': profile_plot
        }

        return result

    except Exception as e:
        result['error'] = str(e)
        return result