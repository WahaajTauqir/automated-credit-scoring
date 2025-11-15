"""
New API endpoints using the restructured database schema.
These endpoints replace the old JSON-based storage with normalized relational tables.

Gradual Migration Strategy:
1. Import this module in app.py
2. Test new endpoints alongside old ones
3. Switch frontend to use new endpoints
4. Remove old endpoints once verified
"""

from flask import jsonify, request
import pandas as pd
import numpy as np
import os
from db import (
    create_dataset, get_dataset, get_latest_dataset, update_dataset,
    create_features_batch, get_feature_by_name, get_features_by_dataset, update_features_selection,
    create_binning_step, get_binning_step_by_type,
    create_bins_batch, get_bins_by_step,
    create_merged_bin, get_merged_bins_by_step,
    create_binning_totals, get_binning_totals,
    get_complete_binning_results, delete_all_binning_for_feature
)


def get_csv_path():
    """Returns the absolute path to the dataset CSV file from the database record."""
    try:
        dataset = get_latest_dataset()
        if dataset and dataset.get('file_path'):
            fp = dataset.get('file_path')
            # First try relative to backend folder
            candidate = os.path.join(os.path.dirname(__file__), fp)
            if os.path.exists(candidate):
                return candidate
            # Next try if file_path is absolute on disk
            if fp and os.path.isabs(fp) and os.path.exists(fp):
                return fp
            # Next try looking in the uploads folder for the stored name
            uploads_dir = os.path.join(os.path.dirname(__file__), 'uploads')
            maybe = os.path.join(uploads_dir, os.path.basename(fp))
            if os.path.exists(maybe):
                return maybe
    except Exception:
        pass
    # As a last resort, pick the most recent CSV in uploads/ if present
    uploads_dir = os.path.join(os.path.dirname(__file__), 'uploads')
    if os.path.exists(uploads_dir):
        files = [os.path.join(uploads_dir, f) for f in os.listdir(uploads_dir) if f.lower().endswith('.csv')]
        if files:
            files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
            return files[0]

    # Nothing found — raise with helpful message so callers can return a proper error
    raise FileNotFoundError('No dataset CSV found. Upload a CSV via /api/upload-csv first.')


def calculate_woe_iv_for_bins(bins_df, target_col, total_good, total_bad):
    """
    Calculate WOE and IV for bins given Good/Bad counts.
    
    Args:
        bins_df: DataFrame with columns ['Bin', 'Good', 'Bad', 'Total', ...]
        target_col: Name of target column (not used, for consistency)
        total_good: Total Good count across all bins
        total_bad: Total Bad count across all bins
    
    Returns:
        List of dicts with bin statistics including WOE and IV
    """
    bins_data = []
    
    for idx, row in bins_df.iterrows():
        bin_number = idx + 1
        good = row['Good']
        bad = row['Bad']
        total = row['Total']
        
        # Calculate distributions
        dist_good = (good / total_good) if total_good > 0 else 0
        dist_bad = (bad / total_bad) if total_bad > 0 else 0
        
        # Calculate WOE (avoid log(0))
        if dist_good > 0 and dist_bad > 0:
            woe = np.log(dist_good / dist_bad)
        elif dist_good > 0:
            woe = np.log(dist_good / 0.001)  # Small denominator
        elif dist_bad > 0:
            woe = np.log(0.001 / dist_bad)  # Small numerator
        else:
            woe = 0
        
        # Calculate IV contribution
        iv_contrib = (dist_good - dist_bad) * woe
        
        bin_data = {
            'bin_number': bin_number,
            'bin_label': row.get('Bin', f'Bin_{bin_number}'),
            'good_count': int(good),
            'bad_count': int(bad),
            'total_count': int(total),
            'good_bad_ratio': float(good / bad) if bad > 0 else 0,
            'bad_rate': float(bad / total) if total > 0 else 0,
            'freq_percent': float((total / (total_good + total_bad)) * 100),
            'dist_good': float(dist_good * 100),
            'dist_bad': float(dist_bad * 100),
            'woe': float(woe),
            'iv': float(iv_contrib)
        }
        
        # Add range information if present
        if 'Min' in row and 'Max' in row:
            bin_data['min_value'] = float(row['Min'])
            bin_data['max_value'] = float(row['Max'])
        if 'Range' in row:
            bin_data['range_text'] = str(row['Range'])
        
        bins_data.append(bin_data)
    
    return bins_data


# ============================================================================
# NEW API ENDPOINTS
# ============================================================================

def api_classify_columns_new(app):
    """
    Updated column classification endpoint.
    Updates feature records with discrete/continuous types.
    """
    @app.route('/api/v2/classify-columns', methods=['POST'])
    def classify_columns_new():
        try:
            req = request.get_json()
            dataset_id = req.get('dataset_id')
            discrete_cols = req.get('discrete', [])
            continuous_cols = req.get('continuous', [])
            target_col = req.get('target')
            
            if not dataset_id:
                return jsonify({"error": "dataset_id is required"}), 400
            
            # Update dataset with target variable
            if target_col:
                update_dataset(dataset_id, target_variable=target_col)
            
            # Update feature types
            features = get_features_by_dataset(dataset_id)
            
            for feature in features:
                if feature['name'] in discrete_cols:
                    from db import update_feature
                    update_feature(feature['id'], type='discrete')
                elif feature['name'] in continuous_cols:
                    from db import update_feature
                    update_feature(feature['id'], type='continuous')
            
            # Update dataset counts
            update_dataset(
                dataset_id,
                discrete_features=len(discrete_cols),
                continuous_features=len(continuous_cols)
            )
            
            return jsonify({
                'success': True,
                'dataset_id': dataset_id,
                'discrete_count': len(discrete_cols),
                'continuous_count': len(continuous_cols)
            })
            
        except Exception as e:
            return jsonify({"error": str(e)}), 500


def api_univariate_analysis_new(app, coarse_bin_continuous_func, coarse_bin_discrete_func):
    """
    New univariate analysis endpoint using structured schema.
    
    Args:
        app: Flask app instance
        coarse_bin_continuous_func: Function for continuous binning from app.py
        coarse_bin_discrete_func: Function for discrete binning from app.py
    """
    @app.route('/api/v2/univariate-analysis', methods=['POST'])
    def univariate_analysis_new():
        try:
            req = request.get_json()
            dataset_id = req.get('dataset_id')
            discrete_cols = req.get('discrete', [])
            continuous_cols = req.get('continuous', [])
            target = req.get('target')
            
            if not dataset_id:
                # Fallback: get latest dataset
                latest = get_latest_dataset()
                if latest:
                    dataset_id = latest['id']
                else:
                    return jsonify({"error": "No dataset found. Please upload a CSV first."}), 400
            
            if not target:
                return jsonify({"error": "Target variable is required"}), 400
            
            # Update dataset with target variable
            update_dataset(dataset_id, target_variable=target)
            
            # Load CSV
            csv_path = get_csv_path()
            df = pd.read_csv(csv_path)
            
            if target not in df.columns:
                return jsonify({"error": f"Target column '{target}' not found"}), 400
            
            # Convert target to numeric
            df[target] = df[target].fillna(0).astype(int)
            
            results = {}
            
            # Process continuous columns
            for col in continuous_cols:
                if col == target or col not in df.columns:
                    continue
                
                try:
                    # Get feature record
                    feature = get_feature_by_name(dataset_id, col)
                    if not feature:
                        print(f"Warning: Feature {col} not found in database")
                        continue
                    
                    # Perform coarse binning
                    stats, _ = coarse_bin_continuous_func(df, col, target)
                    
                    # Calculate totals
                    total_good = int(stats['Good'].sum())
                    total_bad = int(stats['Bad'].sum())
                    total_count = int(stats['Total'].sum())
                    
                    # Calculate WOE and IV for each bin
                    bins_data = calculate_woe_iv_for_bins(stats, target, total_good, total_bad)
                    
                    # Calculate total IV
                    total_iv = sum([b['iv'] for b in bins_data])
                    
                    # Check monotonicity
                    woe_values = [b['woe'] for b in bins_data]
                    is_increasing = all(woe_values[i] <= woe_values[i+1] for i in range(len(woe_values)-1))
                    is_decreasing = all(woe_values[i] >= woe_values[i+1] for i in range(len(woe_values)-1))
                    is_monotonic = is_increasing or is_decreasing
                    monotonic_direction = 'increasing' if is_increasing else ('decreasing' if is_decreasing else None)
                    
                    # Create binning step
                    step_id = create_binning_step(
                        feature_id=feature['id'],
                        step_type='coarse',
                        method='qcut',
                        num_bins=len(bins_data),
                        is_monotonic=is_monotonic,
                        monotonic_direction=monotonic_direction,
                        iv_value=total_iv
                    )
                    
                    # Create bins
                    create_bins_batch(step_id, bins_data)
                    
                    # Create totals
                    create_binning_totals(
                        binning_step_id=step_id,
                        total_good=total_good,
                        total_bad=total_bad,
                        total_count=total_count,
                        good_bad_ratio=float(total_good / total_bad) if total_bad > 0 else 0,
                        bad_rate=float(total_bad / total_count) if total_count > 0 else 0,
                        freq_percent=100.0,
                        iv=total_iv
                    )
                    
                    results[col] = {
                        'type': 'continuous',
                        'feature_id': feature['id'],
                        'step_id': step_id,
                        'stats': stats.to_dict(orient='records'),
                        'total_iv': float(total_iv),
                        'is_monotonic': is_monotonic,
                        'monotonic_direction': monotonic_direction
                    }
                    
                except Exception as e:
                    print(f"Error processing {col}: {str(e)}")
                    continue
            
            # Process discrete columns
            for col in discrete_cols:
                if col == target or col not in df.columns:
                    continue
                
                try:
                    # Get feature record
                    feature = get_feature_by_name(dataset_id, col)
                    if not feature:
                        print(f"Warning: Feature {col} not found in database")
                        continue
                    
                    # Perform coarse binning
                    stats, _, bin_mapping = coarse_bin_discrete_func(df, col, target)
                    
                    # Calculate totals
                    total_good = int(stats['Good'].sum())
                    total_bad = int(stats['Bad'].sum())
                    total_count = int(stats['Total'].sum())
                    
                    # Calculate WOE and IV for each bin
                    bins_data = calculate_woe_iv_for_bins(stats, target, total_good, total_bad)
                    
                    # Calculate total IV
                    total_iv = sum([b['iv'] for b in bins_data])
                    
                    # Check monotonicity
                    woe_values = [b['woe'] for b in bins_data]
                    is_increasing = all(woe_values[i] <= woe_values[i+1] for i in range(len(woe_values)-1))
                    is_decreasing = all(woe_values[i] >= woe_values[i+1] for i in range(len(woe_values)-1))
                    is_monotonic = is_increasing or is_decreasing
                    monotonic_direction = 'increasing' if is_increasing else ('decreasing' if is_decreasing else None)
                    
                    # Create binning step
                    step_id = create_binning_step(
                        feature_id=feature['id'],
                        step_type='coarse',
                        method='bad_rate',
                        num_bins=len(bins_data),
                        is_monotonic=is_monotonic,
                        monotonic_direction=monotonic_direction,
                        iv_value=total_iv
                    )
                    
                    # Create bins
                    create_bins_batch(step_id, bins_data)
                    
                    # Create totals
                    create_binning_totals(
                        binning_step_id=step_id,
                        total_good=total_good,
                        total_bad=total_bad,
                        total_count=total_count,
                        good_bad_ratio=float(total_good / total_bad) if total_bad > 0 else 0,
                        bad_rate=float(total_bad / total_count) if total_count > 0 else 0,
                        freq_percent=100.0,
                        iv=total_iv
                    )
                    
                    results[col] = {
                        'type': 'discrete',
                        'feature_id': feature['id'],
                        'step_id': step_id,
                        'stats': stats.to_dict(orient='records'),
                        'total_iv': float(total_iv),
                        'is_monotonic': is_monotonic,
                        'monotonic_direction': monotonic_direction,
                        'bin_mapping': bin_mapping
                    }
                    
                except Exception as e:
                    print(f"Error processing {col}: {str(e)}")
                    continue
            
            return jsonify({
                'success': True,
                'dataset_id': dataset_id,
                'results': results
            })
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return jsonify({"error": str(e)}), 500


def api_woe_iv_new(app):
    """
    New WOE/IV retrieval endpoint using structured schema.
    """
    @app.route('/api/v2/woe-iv', methods=['POST', 'GET'])
    def woe_iv_new():
        try:
            if request.method == 'POST':
                req = request.get_json()
                dataset_id = req.get('dataset_id')
            else:
                dataset_id = request.args.get('dataset_id')
            
            if not dataset_id:
                # Fallback: get latest dataset
                latest = get_latest_dataset()
                if latest:
                    dataset_id = latest['id']
                else:
                    return jsonify({"error": "No dataset found"}), 400
            
            # Get all selected features
            features = get_features_by_dataset(dataset_id)
            selected_features = [f for f in features if f.get('selected', False)]
            
            # If no features selected, return all features with binning results
            if not selected_features:
                selected_features = features
            
            results = {}
            
            for feature in selected_features:
                # Try to get fine binning first, fallback to coarse
                fine_results = get_complete_binning_results(feature['id'], 'fine')
                coarse_results = get_complete_binning_results(feature['id'], 'coarse')
                
                binning_data = fine_results if fine_results else coarse_results
                
                if not binning_data or not binning_data.get('bins'):
                    continue
                
                results[feature['name']] = {
                    'feature_id': feature['id'],
                    'feature_name': feature['name'],
                    'feature_type': feature['type'],
                    'binning_type': binning_data['binning_step']['step_type'],
                    'method': binning_data['binning_step']['method'],
                    'num_bins': binning_data['binning_step']['num_bins'],
                    'is_monotonic': binning_data['binning_step']['is_monotonic'],
                    'monotonic_direction': binning_data['binning_step']['monotonic_direction'],
                    'total_iv': float(binning_data['binning_step']['iv_value'] or 0),
                    'bins': binning_data['bins'],
                    'totals': binning_data['totals'] if binning_data.get('totals') else None,
                    'merged_bins': binning_data.get('merged_bins', [])
                }
            
            return jsonify({
                'success': True,
                'dataset_id': dataset_id,
                'results': results
            })
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return jsonify({"error": str(e)}), 500


def register_new_endpoints(app, coarse_bin_continuous, coarse_bin_discrete):
    """
    Register all new v2 endpoints with the Flask app.
    
    Usage in app.py:
        from api_endpoints_new import register_new_endpoints
        register_new_endpoints(app, coarse_bin_continuous, coarse_bin_discrete)
    """
    api_classify_columns_new(app)
    api_univariate_analysis_new(app, coarse_bin_continuous, coarse_bin_discrete)
    api_woe_iv_new(app)
    
    print("✅ New v2 API endpoints registered:")
    print("   - POST /api/v2/classify-columns")
    print("   - POST /api/v2/univariate-analysis")
    print("   - POST /api/v2/woe-iv")
    print("   - GET  /api/v2/woe-iv")
