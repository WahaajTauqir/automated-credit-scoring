"""
ARCHIVED LEGACY MODULE (app_old.py)

Legacy application module that used JSON-blob persistence has been removed
from active code. Use `backend/app.py` and `backend/db.py` for current
normalized implementations.

The original content is preserved in git history. Importing this module
will raise to prevent accidental usage.
"""

def _archived_import_error():
    raise RuntimeError(
        "The legacy module 'app_old' is archived. Use 'backend/app.py' and 'backend/db.py' instead."
    )


_archived_import_error()


# ----------- Get Uploaded CSV Columns -----------
@app.route('/api/uploaded-csv-columns', methods=['GET'])
def get_uploaded_csv_columns():
    """
    Returns the column headers from the uploaded.csv file.
    """
    try:
        csv_path = get_csv_path()
        df = pd.read_csv(csv_path, nrows=0)
        return jsonify({"columns": df.columns.tolist()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ----------- Health Check -----------
@app.route('/api/health', methods=['GET'])
def health():
    """
    A simple health check endpoint.
    """
    return jsonify({"status": "OK", "time": str(datetime.datetime.now())})

# ----------- Database Health Check -----------
@app.route('/api/db-health', methods=['GET'])
def db_health():
    """
    Checks database connectivity by running a simple query.
    Returns connection parameters (masked) and status.
    """
    try:
        # Read env without mutating
        dbname = os.getenv('PG_DBNAME')
        user = os.getenv('PG_USER')
        host = os.getenv('PG_HOST')
        port = os.getenv('PG_PORT')

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('SELECT 1')
        cur.fetchone()
        conn.close()
        return jsonify({
            "ok": True,
            "connection": {
                "dbname": dbname,
                "user": user,
                "host": host,
                "port": port
            }
        })
    except Exception as e:
        logging.exception("DB health check failed")
        return jsonify({
            "ok": False,
            "error": str(e),
            "connection": {
                "dbname": os.getenv('PG_DBNAME'),
                "user": os.getenv('PG_USER'),
                "host": os.getenv('PG_HOST'),
                "port": os.getenv('PG_PORT')
            }
        }), 500

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
        csv_path = get_csv_path()
        df = pd.read_csv(csv_path)
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
        
        # Perform qcut to get bin edges and assign labels
        _, bin_edges = pd.qcut(df[var], q=bins, retbins=True, labels=False, duplicates='drop')
        n_bins = len(bin_edges) - 1
        
        if n_bins <= 0:
            raise ValueError(f"No valid bins could be created for '{var}'.")
        
        bin_labels = [f'Bin_{i}' for i in range(1, n_bins + 1)]
        df[f'{var}_binned'] = pd.cut(df[var], bins=bin_edges, labels=bin_labels, include_lowest=True, right=True)
        
        # Compute actual min and max for each bin based on data
        tab = pd.crosstab(df[f'{var}_binned'], df[target])
        tab.columns = ['Good', 'Bad']
        tab['Total'] = tab['Good'] + tab['Bad']
        tab = tab.reset_index()
        
        # Calculate Min and Max from actual data in each bin
        min_max_values = df.groupby(f'{var}_binned')[var].agg(['min', 'max']).reset_index()
        tab = tab.merge(min_max_values, on=f'{var}_binned', how='left')
        
        # Rename column for consistency: use 'Bin' instead of variable-prefixed name
        tab = tab.rename(columns={f'{var}_binned': 'Bin', 'min': 'Min', 'max': 'Max'})
        
        # Reorder columns - store only essential data (no derived metrics)
        columns_order = ['Bin', 'Min', 'Max', 'Good', 'Bad', 'Total']
        tab = tab[columns_order]
        
        return tab, df[f'{var}_binned']
    except Exception as e:
        raise ValueError(f"Coarse binning (continuous) failed for '{var}': {str(e)}")

# ----------- Coarse Binning: Discrete -----------
import pandas as pd

def coarse_bin_discrete(df, var, target, bad_label=1, bad_rate_diff=0.5):
    """
    Coarse binning for discrete variables based on Bad Rate similarity.
    
    Parameters:
    - df : DataFrame
    - var : str, feature/column name
    - target : str, binary target column (0/1)
    - bad_label : value in target that indicates 'Bad' (default=1)
    - bad_rate_diff : float, threshold difference in bad rate to create new bin
    
    Returns:
    - final_tab : DataFrame with bin stats
    - df[f'{var}_binned'] : Series with bin assignments
    - bin_mapping : dict mapping original categories to bins
    """
    try:
        if var not in df.columns or df[var].isna().all():
            raise ValueError(f"Column '{var}' is missing or contains only NaN values")
        if target not in df.columns:
            raise ValueError(f"Target column '{target}' not found")

        # Crosstab (auto-detect Good/Bad based on bad_label)
        tab = pd.crosstab(df[var], df[target])
        if bad_label not in tab.columns:
            raise ValueError(f"Bad label '{bad_label}' not found in target column '{target}'")

        tab['Bad'] = tab[bad_label]
        tab['Good'] = tab.drop(columns=[bad_label]).sum(axis=1)
        tab['Total'] = tab['Good'] + tab['Bad']
        tab['Bad Rate'] = (tab['Bad'] / tab['Total']) * 100
        tab = tab.sort_values('Bad Rate')

        # Bin mapping based on bad rate difference
        bin_mapping = {}
        current_bin = 1
        prev_bad_rate = tab['Bad Rate'].iloc[0] if not tab.empty else 0

        for idx, row in tab.iterrows():
            if abs(row['Bad Rate'] - prev_bad_rate) > bad_rate_diff:    
                current_bin += 1
            bin_mapping[idx] = current_bin
            prev_bad_rate = row['Bad Rate']

        # Apply binning
        df[f'{var}_binned'] = df[var].map(bin_mapping).astype(int)

        # Final crosstab
        final_tab = pd.crosstab(df[f'{var}_binned'], df[target])
        final_tab['Bad'] = final_tab[bad_label]
        final_tab['Good'] = final_tab.drop(columns=[bad_label]).sum(axis=1)
        final_tab['Total'] = final_tab['Good'] + final_tab['Bad']
        final_tab['Freq%'] = (final_tab['Total'] / final_tab['Total'].sum()) * 100
        final_tab['Bad Rate'] = (final_tab['Bad'] / final_tab['Total']) * 100
        final_tab = final_tab.reset_index()

        # Compact human-readable ranges
        def compact_ranges(values):
            values = sorted(values)
            ranges, start, prev = [], values[0], values[0]
            for v in values[1:]:
                if v == prev + 1:  # consecutive
                    prev = v
                else:
                    ranges.append(f"{start}–{prev}" if start != prev else str(start))
                    start = prev = v
            ranges.append(f"{start}–{prev}" if start != prev else str(start))
            return ", ".join(ranges)

        # Map original values to bins
        bin_ranges = {}
        for b in final_tab[f'{var}_binned']:
            original_vals = sorted([v for v, bin_id in bin_mapping.items() if bin_id == b])
            bin_ranges[b] = compact_ranges(original_vals)

        final_tab['Range'] = final_tab[f'{var}_binned'].map(bin_ranges)

        # Rename column for consistency: use 'Bin' instead of variable-prefixed name
        final_tab = final_tab.rename(columns={f'{var}_binned': 'Bin'})

        # Reorder - store only essential data (no derived metrics)
        columns_order = ['Bin', 'Range', 'Good', 'Bad', 'Total']
        final_tab = final_tab[columns_order]

        return final_tab, df[f'{var}_binned'], bin_mapping

    except Exception as e:
        raise ValueError(f"Coarse binning (discrete) failed for '{var}': {str(e)}")

# ----------- Fine Binning: Continuous -----------
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
        if curr_num == prev_num + 1: # ✅ adjacent
            current.append(curr_label)
        else: # ❌ break → start new group
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
            # Compute min and max for original bins
            bin_ranges = {}
            unique_bins = df[binned_col].unique()
            for bin_label in unique_bins:
                mask = df[binned_col] == bin_label
                if mask.any():
                    values = df.loc[mask, var]
                    # Preserve precise numeric min/max (do not round to integers)
                    min_val = float(values.min()) if not values.empty else None
                    max_val = float(values.max()) if not values.empty else None
                    bin_ranges[bin_label] = (min_val, max_val)
            return None, df[fine_binned_col], {}, bin_ranges
        
        new_bin_map = {}
        updated_merges = {}
        bin_ranges = {}
        for new_bin, old_bins in bin_merges.items():
            groups = split_into_adjacent_groups(old_bins)
            for idx, g in enumerate(groups, start=1):
                merged_name = f"{'_'.join(g)}"
                updated_merges[merged_name] = g
                for b in g:
                    new_bin_map[b] = merged_name
                # Compute min and max for merged bins
                mask = df[binned_col].isin(g)
                if mask.any():
                    values = df.loc[mask, var]
                    # Preserve precise numeric min/max for merged bins
                    min_val = float(values.min()) if not values.empty else None
                    max_val = float(values.max()) if not values.empty else None
                    bin_ranges[merged_name] = (min_val, max_val)
        
        # Apply new mapping
        df[fine_binned_col] = df[binned_col].map(lambda x: new_bin_map.get(x, x))
        # Add ranges for unmapped bins
        unmapped_bins = set(df[binned_col].unique()) - set(new_bin_map.keys())
        for bin_label in unmapped_bins:
            mask = df[binned_col] == bin_label
            if mask.any():
                values = df.loc[mask, var]
                # Preserve precise numeric min/max for unmapped bins
                min_val = float(values.min()) if not values.empty else None
                max_val = float(values.max()) if not values.empty else None
                bin_ranges[bin_label] = (min_val, max_val)
        
        # Ensure a deterministic ordering for continuous fine bins: sort by Min value
        # Build ordered labels from bin_ranges (Min value). Place None/empty bins at the end.
        try:
            ordered_bins = sorted(list(bin_ranges.items()), key=lambda kv: (kv[1][0] if kv[1][0] is not None else float('inf')))
            ordered_labels = [label for label, _ in ordered_bins]
            # apply ordered categorical so pandas preserves this order in aggregations
            df[fine_binned_col] = df[fine_binned_col].astype(str)
            df[fine_binned_col] = pd.Categorical(df[fine_binned_col], categories=ordered_labels, ordered=True)
        except Exception:
            # fallback: keep as-is
            df[fine_binned_col] = df[fine_binned_col].astype(str)

        # Cross-tab summary (avoid pandas automatic sorting)
        try:
            cross_tab = pd.crosstab(df[fine_binned_col], df[target], sort=False)
        except TypeError:
            # Older pandas versions don't accept 'sort' kwarg
            cross_tab = pd.crosstab(df[fine_binned_col], df[target])
        cols = cross_tab.columns.tolist()
        col_map = {}
        if 0 in cols:
            col_map[0] = 'Good'
        if 1 in cols:
            col_map[1] = 'Bad'
        cross_tab = cross_tab.rename(columns=col_map)
        for col in ['Good', 'Bad']:
            if col not in cross_tab.columns:
                cross_tab[col] = 0
        cross_tab['Total'] = cross_tab['Good'] + cross_tab['Bad']
        cross_tab = cross_tab.reset_index()
        
        # Add min and max columns
        cross_tab['Min'] = cross_tab[fine_binned_col].map(lambda x: bin_ranges.get(x, (None, None))[0])
        cross_tab['Max'] = cross_tab[fine_binned_col].map(lambda x: bin_ranges.get(x, (None, None))[1])
        
        # Rename column for consistency: use 'Bin' instead of variable-prefixed name
        cross_tab = cross_tab.rename(columns={fine_binned_col: 'Bin'})
        
        # Ensure the final table follows the ordered_labels if available
        try:
            if 'ordered_labels' in locals():
                cross_tab = cross_tab.set_index('Bin').reindex(ordered_labels).reset_index()
        except Exception:
            pass

        # Reorder - store only essential data
        columns_order = ['Bin', 'Min', 'Max', 'Good', 'Bad', 'Total']
        cross_tab = cross_tab[columns_order]
        return cross_tab, df[fine_binned_col], updated_merges, bin_ranges
    except Exception as e:
        raise ValueError(f"Fine binning (continuous) failed for '{var}': {str(e)}")
# ----------- Fine Binning: Discrete -----------
def fine_bin_discrete(df, var, target, bin_merges=None, bin_mapping=None):
    try:
        binned_col = f'{var}_binned'
        fine_binned_col = f'{var}_fine_binned'
        bin_map = {}

        if bin_merges is None:
            bin_merges = {}

        # Create mapping for merged bins
        for new_bin, old_bins in bin_merges.items():
            for old_bin in old_bins:
                bin_map[str(old_bin)] = str(new_bin)  # normalize to str

        # Apply mapping (keep as str always)
        df[fine_binned_col] = df[binned_col].astype(str).map(bin_map).fillna(df[binned_col].astype(str))

        # Compute ranges
        bin_ranges = {}
        for bin_label in df[fine_binned_col].unique():
            if bin_label in bin_merges:
                # Merged bin
                source_bins = bin_merges[bin_label]
                original_values = set()
                for source_bin in source_bins:
                    mask = df[binned_col].astype(str) == str(source_bin)
                    if mask.any():
                        values = df.loc[mask, var].dropna().unique()
                        original_values.update(values)
                bin_ranges[bin_label] = sorted(original_values) if original_values else ['N/A']
            else:
                # Single bin
                mask = df[fine_binned_col] == bin_label
                if mask.any():
                    values = df.loc[mask, var].dropna().unique()
                    bin_ranges[bin_label] = sorted(values) if len(values) > 0 else ['N/A']
                else:
                    bin_ranges[bin_label] = ['N/A']

        # Determine an ordered label set for discrete fine bins (preserve bin_merges order when present)
        try:
            if bin_merges:
                ordered_labels = [str(k) for k in bin_merges.keys()]
                # append any remaining bins in appearance order
                remaining = [lbl for lbl in df[fine_binned_col].astype(str).unique() if lbl not in ordered_labels]
                ordered_labels.extend(remaining)
            else:
                ordered_labels = [str(x) for x in df[fine_binned_col].astype(str).unique()]
            df[fine_binned_col] = df[fine_binned_col].astype(str)
            df[fine_binned_col] = pd.Categorical(df[fine_binned_col], categories=ordered_labels, ordered=True)
        except Exception:
            df[fine_binned_col] = df[fine_binned_col].astype(str)

        # Crosstab (avoid automatic sorting)
        try:
            cross_tab = pd.crosstab(df[fine_binned_col], df[target], sort=False)
        except TypeError:
            # Older pandas versions don't accept 'sort' kwarg
            cross_tab = pd.crosstab(df[fine_binned_col], df[target])
        col_map = {}
        if 0 in cross_tab.columns: col_map[0] = 'Good'
        if 1 in cross_tab.columns: col_map[1] = 'Bad'
        cross_tab = cross_tab.rename(columns=col_map)

        for col in ['Good', 'Bad']:
            if col not in cross_tab.columns:
                cross_tab[col] = 0

        cross_tab['Total'] = cross_tab['Good'] + cross_tab['Bad']
        cross_tab = cross_tab.reset_index()

        # ✅ FIX: Always use str keys for bin_ranges lookup
        cross_tab['Range'] = cross_tab[fine_binned_col].astype(str).map(lambda x: ', '.join(map(str, bin_ranges.get(x, ['N/A']))))

        # Rename column for consistency: use 'Bin' instead of variable-prefixed name
        cross_tab = cross_tab.rename(columns={fine_binned_col: 'Bin'})

        # Final order - store only essential data
        columns_order = ['Bin', 'Range', 'Good', 'Bad', 'Total']
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
        
        # Use absolute path to ensure we're working with the right file
        csv_path = os.path.join(os.path.dirname(__file__), "uploaded.csv")
        df = pd.read_csv(csv_path)
        df[target] = df[target].fillna(0).astype(int)

        if var_type == 'continuous':
            _, df[f'{var}_binned'] = coarse_bin_continuous(df, var, target)
            existing_bins = set(df[f'{var}_binned'].unique())
            bin_merges = {k: [b for b in v if b in existing_bins] for k, v in bin_merges.items()}
            bin_merges = {k: v for k, v in bin_merges.items() if v}
            tab, _, adjusted_merges, _ = fine_bin_continuous(df, var, target, bin_merges)
        else:
            _, df[f'{var}_binned'], bin_mapping = coarse_bin_discrete(df, var, target)
            tab, _, adjusted_merges = fine_bin_discrete(df, var, target, bin_merges, bin_mapping)

        if tab is None:
            return jsonify({"error": "Fine binning returned no results"}), 400

        # Recalculate WOE/IV for the fine-binned variable
        try:
            # Use the fine binning results to calculate WOE/IV
            iv, woe_stats = calculate_woe_iv(
                df=df,
                variable=var,
                target=target,
                bin_merges=adjusted_merges if adjusted_merges else None,
                var_type=var_type
            )
            print(f"Fine bin WOE/IV recalculated for {var}: IV={iv}")
        except Exception as woe_err:
            print(f"Warning: Could not calculate WOE/IV after fine binning: {woe_err}")
            iv = 0
            woe_stats = []

        # Save binning results to PostgreSQL
        from db import save_record_db, save_finebin_details_db, get_record_db
        # Always upsert into the same record (never create new)
        record_id = req.get('recordId')
        dataset_path = "uploaded.csv"
        # Load latest record to preserve selected_columns, discrete_columns, continuous_columns
        from db import get_records_db
        records = get_records_db()
        if records:
            latest = records[0]
            discrete_columns = latest.get('discrete_columns', '[]')
            continuous_columns = latest.get('continuous_columns', '[]')
            selected_columns = latest.get('selected_columns', '[]')
        else:
            discrete_columns = json.dumps([])
            continuous_columns = json.dumps([])
            selected_columns = json.dumps([])
        target_variable = target
        
        # Preserve existing univariate_results and update with new data
        univariate_results_dict = {}
        if record_id:
            existing_record = get_record_db(record_id)
            if existing_record and existing_record.get('univariate_results'):
                try:
                    univariate_results_dict = json.loads(existing_record['univariate_results'])
                except:
                    pass
        
        univariate_results = json.dumps(univariate_results_dict)
        
        # Store fine binning results as dict (not array) for consistency
        finebin_results_dict = {}
        if record_id:
            existing_record = get_record_db(record_id)
            if existing_record and existing_record.get('finebin_results'):
                try:
                    finebin_results_dict = json.loads(existing_record['finebin_results'])
                except:
                    pass
        
        # Update with current variable's fine binning
        finebin_results_dict[var] = tab.to_dict(orient='records')
        finebin_results = json.dumps(finebin_results_dict)
        
        crosstab_results = json.dumps([])
        
        # Update WOE/IV results for this variable
        woe_iv_dict = {}
        if record_id:
            existing_record = get_record_db(record_id)
            if existing_record and existing_record.get('woe_iv_results'):
                try:
                    woe_iv_dict = json.loads(existing_record['woe_iv_results'])
                    if not isinstance(woe_iv_dict, dict):
                        woe_iv_dict = {}
                except:
                    woe_iv_dict = {}
        
        # Store the recalculated WOE/IV for this variable
        woe_iv_dict[var] = {"iv": iv, "stats": woe_stats}
        woe_iv_results = json.dumps(woe_iv_dict)
        
        dashboard_selected_columns = json.dumps(req.get('dashboard_selected_columns', []))
        if not record_id:
            # If no recordId, upsert will create one
            record_id = upsert_single_record_db(dataset_path, discrete_columns, continuous_columns, selected_columns, dashboard_selected_columns, target_variable, univariate_results, finebin_results, crosstab_results, woe_iv_results)
        else:
            # If recordId exists, upsert will update it
            upsert_single_record_db(dataset_path, discrete_columns, continuous_columns, selected_columns, dashboard_selected_columns, target_variable, univariate_results, finebin_results, crosstab_results, woe_iv_results)
        save_finebin_details_db(int(record_id), var, adjusted_merges)
        print("Fine binning done for", var)
        return jsonify({
            "success": True,
            "stats": tab.to_dict(orient='records'),
            "bin_merges": adjusted_merges,
            "woe_iv": {"iv": iv, "stats": woe_stats}
        })
    except Exception as e:
        import traceback
        print("ERROR:", traceback.format_exc())
        return jsonify({"error": str(e)}), 500

# ----------- Automated Monotonic Binning API -----------
@app.route('/api/auto-monotonic-binning', methods=['POST'])
def auto_monotonic_binning_api():
    """
    Automatically merge bins to achieve monotonic WOE (Weight of Evidence).
    Uses deterministic algorithms to find the best bin merging strategy.
    
    Expects JSON payload:
    {
        "variable": "column_name",
        "target": "target_column",
        "type": "continuous" or "discrete",
        "direction": "increasing", "decreasing", or null (auto-detect),
        "method": "greedy" or "exhaustive",
        "prioritize_iv": true or false (default: true, only for exhaustive),
        "record_id": optional record ID,
        "dashboard_selected_columns": optional list
    }
    """
    try:
        req = request.get_json()
        print("Auto-binning request:", req)
        
        var = req.get('variable')
        target = req.get('target')
        var_type = req.get('type')
        direction = req.get('direction')  # 'increasing', 'decreasing', or None
        method = req.get('method', 'greedy')  # 'greedy' or 'exhaustive'
        prioritize_iv = req.get('prioritize_iv', True)  # default to True
        record_id = req.get('record_id')
        
        if not var or not target or not var_type:
            return jsonify({"error": "Missing required fields: variable, target, type"}), 400
        
        # Load data
        csv_path = os.path.join(os.path.dirname(__file__), "uploaded.csv")
        df = pd.read_csv(csv_path)
        df[target] = df[target].fillna(0).astype(int)
        
        # First perform coarse binning to get initial bins
        if var_type == 'continuous':
            coarse_stats, df[f'{var}_binned'] = coarse_bin_continuous(df, var, target)
        else:
            coarse_stats, df[f'{var}_binned'], bin_mapping = coarse_bin_discrete(df, var, target)
        
        # Extract good/bad counts and bin labels from coarse binning
        bin_labels = []
        good_counts = []
        bad_counts = []
        
        for _, row in coarse_stats.iterrows():
            # Get bin label
            if var_type == 'continuous':
                bin_label = row.get(f'{var}_binned', f'Bin_{len(bin_labels)+1}')
            else:
                bin_label = str(row.get(f'{var}_binned', len(bin_labels)+1))
            
            bin_labels.append(str(bin_label))
            good_counts.append(int(row.get('Good', 0)))
            bad_counts.append(int(row.get('Bad', 0)))
        
        # Convert to numpy arrays
        good = np.array(good_counts)
        bad = np.array(bad_counts)
        
        print(f"Auto-binning for {var}: {len(bin_labels)} bins, direction={direction}, method={method}, prioritize_iv={prioritize_iv}")
        print(f"Initial bins: {bin_labels}")
        print(f"Initial Good: {good}")
        print(f"Initial Bad: {bad}")
        print(f"Initial WOE: {compute_woe(good, bad).tolist()}")
        
        # Run automated monotonic binning
        result = auto_monotonic_binning(
            good=good,
            bad=bad,
            bin_labels=bin_labels,
            variable_type=var_type,
            direction=direction,
            method=method,
            prioritize_iv=prioritize_iv
        )
        
        print(f"Auto-binning result: {result['num_merges']} merges, monotonic={result['is_monotonic']}, IV={result['iv']:.4f}")
        print(f"Final bins: {result['merged_labels']}")
        print(f"Final WOE: {result['woe_values']}")
        
        # Convert merge mapping to format expected by fine_bin API
        # merge_mapping maps new labels to list of original labels
        bin_merges = {}
        for merged_label, original_labels in result['merge_mapping'].items():
            if len(original_labels) > 1:  # Only include actual merges
                bin_merges[merged_label] = original_labels
        
        print(f"Bin merges to apply: {bin_merges}")
        
        # Apply the merges using fine binning
        if var_type == 'continuous':
            _, df[f'{var}_binned'] = coarse_bin_continuous(df, var, target)
            existing_bins = set(df[f'{var}_binned'].unique())
            bin_merges = {k: [b for b in v if b in existing_bins] for k, v in bin_merges.items()}
            bin_merges = {k: v for k, v in bin_merges.items() if v}
            tab, _, adjusted_merges, _ = fine_bin_continuous(df, var, target, bin_merges)
        else:
            _, df[f'{var}_binned'], bin_mapping = coarse_bin_discrete(df, var, target)
            tab, _, adjusted_merges = fine_bin_discrete(df, var, target, bin_merges, bin_mapping)
        
        if tab is None:
            return jsonify({"error": "Auto-binning produced no results"}), 400
        
        # Recalculate WOE/IV using the result from auto binning
        try:
            iv, woe_stats = calculate_woe_iv(
                df=df,
                variable=var,
                target=target,
                bin_merges=adjusted_merges if adjusted_merges else None,
                var_type=var_type
            )
            print(f"Auto-binning WOE/IV calculated for {var}: IV={iv}")
        except Exception as woe_err:
            print(f"Warning: Could not calculate WOE/IV after auto-binning: {woe_err}")
            # Use the IV from the auto_monotonic_binning result as fallback
            iv = result['iv']
            woe_stats = []
        
        # Save results to database
        from db import get_records_db, get_record_db
        records = get_records_db()
        if records:
            latest = records[0]
            discrete_columns = latest.get('discrete_columns', '[]')
            continuous_columns = latest.get('continuous_columns', '[]')
            selected_columns = latest.get('selected_columns', '[]')
        else:
            discrete_columns = json.dumps([])
            continuous_columns = json.dumps([])
            selected_columns = json.dumps([])
        
        dataset_path = "uploaded.csv"
        target_variable = target
        
        # Preserve existing univariate_results
        univariate_results_dict = {}
        if record_id:
            existing_record = get_record_db(record_id)
            if existing_record and existing_record.get('univariate_results'):
                try:
                    univariate_results_dict = json.loads(existing_record['univariate_results'])
                except:
                    pass
        univariate_results = json.dumps(univariate_results_dict)
        
        # Store fine binning results as dict (not array) for consistency
        finebin_results_dict = {}
        if record_id:
            existing_record = get_record_db(record_id)
            if existing_record and existing_record.get('finebin_results'):
                try:
                    finebin_results_dict = json.loads(existing_record['finebin_results'])
                except:
                    pass
        
        # Update with current variable's fine binning
        finebin_results_dict[var] = tab.to_dict(orient='records')
        finebin_results = json.dumps(finebin_results_dict)
        
        crosstab_results = json.dumps([])
        
        # Update WOE/IV results for this variable
        woe_iv_dict = {}
        if record_id:
            existing_record = get_record_db(record_id)
            if existing_record and existing_record.get('woe_iv_results'):
                try:
                    woe_iv_dict = json.loads(existing_record['woe_iv_results'])
                    if not isinstance(woe_iv_dict, dict):
                        woe_iv_dict = {}
                except:
                    woe_iv_dict = {}
        
        # Store the calculated WOE/IV for this variable
        woe_iv_dict[var] = {"iv": iv, "stats": woe_stats}
        woe_iv_results = json.dumps(woe_iv_dict)
        
        dashboard_selected_columns = json.dumps(req.get('dashboard_selected_columns', []))
        
        if not record_id:
            record_id = upsert_single_record_db(
                dataset_path, discrete_columns, continuous_columns, selected_columns,
                dashboard_selected_columns, target_variable, univariate_results,
                finebin_results, crosstab_results, woe_iv_results
            )
        else:
            upsert_single_record_db(
                dataset_path, discrete_columns, continuous_columns, selected_columns,
                dashboard_selected_columns, target_variable, univariate_results,
                finebin_results, crosstab_results, woe_iv_results
            )
        
        save_finebin_details_db(int(record_id), var, adjusted_merges)
        
        print(f"Auto-binning completed for {var}")
        
        return jsonify({
            "success": True,
            "stats": tab.to_dict(orient='records'),
            "bin_merges": adjusted_merges,
            "is_monotonic": result['is_monotonic'],
            "direction": result['direction'],
            "num_merges": result['num_merges'],
            "num_bins_original": result['num_bins_original'],
            "num_bins_final": result['num_bins_final'],
            "woe_iv": {"iv": iv, "stats": woe_stats}
        })
        
    except Exception as e:
        import traceback
        print("ERROR in auto-monotonic-binning:", traceback.format_exc())
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
        binning_info = req.get('binning', {}) # optional: {var: {type: 'continuous'/'discrete', bin_merges: {...}}}
        if not target or not variables:
            return jsonify({"error": "Missing required fields: variables or target"}), 400
        
        # Load dataset with absolute path
        csv_path = os.path.join(os.path.dirname(__file__), "uploaded.csv")
        df = pd.read_csv(csv_path)
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
        
        # Save cross-tab results to PostgreSQL (if needed)
        # Example: upsert_single_record_db(...)
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
        csv_path = get_csv_path()
        df = pd.read_csv(csv_path)
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


# ----------- Reset Bins API -----------
@app.route('/api/reset-bins', methods=['POST'])
def reset_bins_api():
    """
    Reset binning for a variable: clears fine binning and WOE/IV, reverts to coarse bins.
    
    Expects JSON payload:
    {
        "variable": "column_name",
        "target": "target_column",
        "type": "continuous" or "discrete",
        "record_id": record ID
    }
    """
    try:
        req = request.get_json()
        var = req.get('variable')
        target = req.get('target')
        var_type = req.get('type')
        record_id = req.get('record_id')
        
        if not var or not target or not var_type or not record_id:
            return jsonify({"error": "Missing required fields: variable, target, type, record_id"}), 400
        
        # Load data and perform coarse binning
        csv_path = get_csv_path()
        df = pd.read_csv(csv_path)
        
        if target not in df.columns:
            return jsonify({"error": f"Target column '{target}' not found in dataset"}), 400
        
        df[target] = df[target].fillna(0).astype(int)
        
        # Perform coarse binning
        if var_type == 'continuous':
            coarse_stats, _ = coarse_bin_continuous(df, var, target)
        else:
            coarse_stats, _, _ = coarse_bin_discrete(df, var, target)
        
        # Load existing record
        from db import get_record_db, delete_record_db
        existing_record = get_record_db(record_id)
        
        if not existing_record:
            return jsonify({"error": f"Record {record_id} not found"}), 404
        
        # Update univariate_results with coarse bins
        univariate_results_dict = {}
        if existing_record.get('univariate_results'):
            try:
                univariate_results_dict = json.loads(existing_record['univariate_results'])
            except:
                pass
        
        univariate_results_dict[var] = {
            'type': var_type,
            'stats': coarse_stats.to_dict(orient='records')
        }
        
        # Remove from finebin_results
        finebin_results_dict = {}
        if existing_record.get('finebin_results'):
            try:
                finebin_results_dict = json.loads(existing_record['finebin_results'])
            except:
                pass
        
        if var in finebin_results_dict:
            del finebin_results_dict[var]
        
        # Remove from woe_iv_results
        woe_iv_dict = {}
        if existing_record.get('woe_iv_results'):
            try:
                woe_iv_dict = json.loads(existing_record['woe_iv_results'])
                if not isinstance(woe_iv_dict, dict):
                    woe_iv_dict = {}
            except:
                woe_iv_dict = {}
        
        if var in woe_iv_dict:
            del woe_iv_dict[var]
        
        # Delete finebin_details for this variable
        from db import get_db_connection
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM finebin_details WHERE record_id = %s AND column_name = %s",
            (record_id, var)
        )
        conn.commit()
        conn.close()
        
        # Update the record
        dataset_path = existing_record.get('dataset_path', 'uploaded.csv')
        discrete_columns = existing_record.get('discrete_columns', '')
        continuous_columns = existing_record.get('continuous_columns', '')
        selected_columns = existing_record.get('selected_columns', '')
        dashboard_selected_columns = existing_record.get('dashboard_selected_columns', '')
        target_variable = existing_record.get('target_variable', target)
        crosstab_results = existing_record.get('crosstab_results', '[]')
        
        upsert_single_record_db(
            dataset_path, discrete_columns, continuous_columns, selected_columns,
            dashboard_selected_columns, target_variable, 
            json.dumps(univariate_results_dict),
            json.dumps(finebin_results_dict),
            crosstab_results,
            json.dumps(woe_iv_dict)
        )
        
        print(f"Reset bins for {var}: cleared fine binning and WOE/IV")
        
        return jsonify({
            "success": True,
            "message": f"Bins reset for {var}",
            "coarse_stats": coarse_stats.to_dict(orient='records')
        })
        
    except Exception as e:
        import traceback
        print("ERROR in reset-bins:", traceback.format_exc())
        return jsonify({"error": str(e)}), 500


# ----------- Get CSV Sample Data for AI Classification -----------
@app.route('/api/csv-samples', methods=['POST'])
def get_csv_samples():
    """
    Get sample values from uploaded CSV for specified columns to help with AI classification.
    Expects JSON: { columns: [...] }
    Returns: { column_name: [sample_values...] }
    """
    try:
        payload = request.get_json() or {}
        columns = payload.get('columns', [])
        sample_size = payload.get('sample_size', 20)
        
        csv_path = get_csv_path()
        if not os.path.exists(csv_path):
            return jsonify({"error": "No CSV file uploaded"}), 400
            
        df = pd.read_csv(csv_path)
        
        samples = {}
        for col in columns:
            if col in df.columns:
                # Get sample values, removing NaN and converting to native Python types
                col_samples = df[col].dropna().head(sample_size).tolist()
                # Convert numpy types to native Python types for JSON serialization
                samples[col] = [x.item() if hasattr(x, 'item') else x for x in col_samples]
            else:
                samples[col] = []
                
        return jsonify(samples)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/ai-classify-columns', methods=['POST'])
def ai_classify_columns():
    """
    Classify columns as 'discrete' or 'continuous' using GitHub Models inference endpoint.
    Expects JSON: { columns: [...], sampleData: { col: [samples...] }, model: <optional model name> }
    """
    try:
        payload = request.get_json() or {}
        columns = payload.get('columns', [])
        sample_data = payload.get('sampleData', {})
        model = payload.get('model') or os.getenv('AI_CLASSIFY_MODEL') or 'openai/gpt-5-mini'

        token = os.getenv('GITHUB_TOKEN')
        if not token:
            print("ERROR: GITHUB_TOKEN environment variable not found")
            return jsonify({"error": "Server missing GITHUB_TOKEN environment variable. Set it and restart the backend."}), 401
        
        print(f"DEBUG: Using GitHub token (first 10 chars): {token[:10]}...")
        print(f"DEBUG: Processing {len(columns)} columns")

        # For large datasets, use enhanced heuristics as primary method
        if len(columns) > 50:
            print(f"DEBUG: Large dataset detected ({len(columns)} columns), using enhanced heuristics")
            results = {}
            for col in columns:
                results[col] = classify_with_heuristics(col, sample_data.get(col, []))
            return jsonify(results)

        # Build an enhanced prompt with detailed classification criteria
        prompt = (
            "You are a data science expert that classifies dataset columns as 'discrete' or 'continuous'.\n\n"
            "DISCRETE variables are:\n"
            "- Categorical (text labels, categories, yes/no, male/female)\n"
            "- Integer codes or IDs (customer_id, product_code, zip_code)\n"
            "- Binary/boolean values (0/1, true/false)\n"
            "- Ordinal scales with few distinct values (rating 1-5, grade A-F)\n"
            "- Countable items with limited distinct values (number_of_children, education_level)\n\n"
            "CONTINUOUS variables are:\n"
            "- Measurements (age, height, weight, temperature, price)\n"
            "- Financial amounts (salary, revenue, balance)\n"
            "- Percentages and ratios (interest_rate, conversion_rate)\n"
            "- Time durations (days, hours, response_time)\n"
            "- Scientific measurements (pressure, voltage, distance)\n\n"
            "Analyze the column names and sample values. Return ONLY a valid JSON object.\n"
            f"Columns to classify: {json.dumps(columns)}\n"
            f"Sample data: {json.dumps(sample_data)}\n\n"
            "Response format: {\"column_name\": \"discrete\" or \"continuous\"}\n"
        )

        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": "You are a helpful assistant that replies with strict JSON."},
                {"role": "user", "content": prompt}
            ]
        }

        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        url = "https://models.github.ai/inference/chat/completions"
        resp = requests.post(url, headers=headers, json=body, timeout=30)
        
        print(f"DEBUG: GitHub API response status: {resp.status_code}")
        if not resp.ok:
            print(f"DEBUG: GitHub API error response: {resp.text}")
            error_msg = f"GitHub Models API call failed (status {resp.status_code})"
            if resp.status_code == 401:
                error_msg += ". Check if your GitHub token has 'models:read' permission."
            elif resp.status_code == 403:
                error_msg += ". Rate limit exceeded or insufficient permissions."
            return jsonify({"error": error_msg, "details": resp.text}), 502

        data = resp.json()
        # Expected path: choices[0].message.content
        text = None
        try:
            text = data.get('choices', [])[0].get('message', {}).get('content')
        except Exception:
            text = None

        if not text:
            # fallback: try top-level generated_text
            if isinstance(data, list) and data and isinstance(data[0], dict):
                text = data[0].get('generated_text')

        if not text:
            return jsonify({"error": "Model returned unexpected response", "raw": data}), 502

        # Try to extract JSON from the model's text
        mapping = None
        try:
            mapping = json.loads(text.strip())
        except Exception:
            # attempt to find JSON substring
            import re
            m = re.search(r"\{[\s\S]*\}", text)
            if m:
                try:
                    mapping = json.loads(m.group(0))
                except Exception:
                    mapping = None

        if not mapping or not isinstance(mapping, dict):
            return jsonify({"error": "Failed to parse JSON from model response", "raw_text": text}), 502

        # Normalize values to 'discrete' or 'continuous' with enhanced heuristics
        normalized = {}
        for k, v in mapping.items():
            s = str(v).strip().lower()
            if s.startswith('d'):
                normalized[k] = 'discrete'
            elif s.startswith('c'):
                normalized[k] = 'continuous'
            else:
                # Enhanced fallback heuristics based on column name and samples
                samples = sample_data.get(k, [])
                col_name_lower = k.lower()
                
                # Check for discrete indicators in column name
                discrete_keywords = ['id', 'code', 'type', 'category', 'class', 'group', 'status', 
                                   'flag', 'level', 'grade', 'rating', 'rank', 'gender', 'sex',
                                   'marital', 'education', 'occupation', 'department', 'region',
                                   'state', 'country', 'city', 'zip', 'postal']
                
                continuous_keywords = ['age', 'amount', 'price', 'cost', 'salary', 'income', 'revenue',
                                     'balance', 'rate', 'ratio', 'percent', 'score', 'weight', 'height',
                                     'length', 'width', 'depth', 'distance', 'time', 'duration', 'years']
                
                is_discrete_name = any(keyword in col_name_lower for keyword in discrete_keywords)
                is_continuous_name = any(keyword in col_name_lower for keyword in continuous_keywords)
                
                if is_discrete_name:
                    normalized[k] = 'discrete'
                elif is_continuous_name:
                    normalized[k] = 'continuous'
                else:
                    # Analyze sample values
                    try:
                        if not samples:
                            normalized[k] = 'discrete'  # Default when no data
                        else:
                            # Check for non-numeric values
                            non_numeric_count = sum(1 for x in samples if not isinstance(x, (int, float)))
                            if non_numeric_count > 0:
                                normalized[k] = 'discrete'
                            else:
                                # For numeric data, check uniqueness and range
                                unique_values = len(set(samples))
                                if unique_values <= 10:  # Low cardinality suggests discrete
                                    normalized[k] = 'discrete'
                                elif unique_values == len(samples):  # All unique suggests continuous
                                    normalized[k] = 'continuous'
                                else:
                                    # Check if values look like IDs (integers) or measurements (floats)
                                    all_integers = all(isinstance(x, int) or (isinstance(x, float) and x.is_integer()) for x in samples)
                                    if all_integers and max(samples) - min(samples) > unique_values * 2:
                                        normalized[k] = 'discrete'  # Likely IDs or codes
                                    else:
                                        normalized[k] = 'continuous'  # Likely measurements
                    except Exception:
                        normalized[k] = 'discrete'  # Safe default

        return jsonify(normalized)
    except Exception as e:
        import traceback
        print('ai_classify_columns error:', traceback.format_exc())
        return jsonify({"error": str(e)}), 500

# ----------- Credit Scoring Metrics Calculation -----------
@app.route('/api/calculate-scoring-metrics', methods=['POST'])
def calculate_scoring_metrics():
    """
    Calculate credit scoring metrics including:
    - 0/1 (Good/Bad ratio)
    - G/B Odd (based on 0/1 ratio and total 0/1)
    - G/B Index (B/G label)
    - Index (Combined rounded G/B Odd + G/B Index)
    """
    try:
        data = request.get_json()
        good_count = data.get('good_count', 0)
        bad_count = data.get('bad_count', 0)
        total_count = data.get('total_count', 0)
        total_zero_one_ratio = data.get('total_zero_one_ratio', 0)
        
        # Validate inputs
        if good_count < 0 or bad_count < 0 or total_count < 0:
            return jsonify({"error": "Counts cannot be negative"}), 400
        
        # Calculate 0/1 ratio - Based on your image, it seems to be total/bad
        # But you want 716/9 = 79.5556, so let's use good/bad
        if bad_count > 0:
            zero_one_ratio = good_count / bad_count
        else:
            zero_one_ratio = float('inf')
        
        # G/B Odd calculation
        if zero_one_ratio < total_zero_one_ratio:
            if zero_one_ratio > 0:
                gb_odd = (total_zero_one_ratio / zero_one_ratio) * 100
            else:
                gb_odd = float('inf')
        else:
            if total_zero_one_ratio > 0:
                gb_odd = (zero_one_ratio / total_zero_one_ratio) * 100
            else:
                gb_odd = float('inf')
        
        # G/B Index
        gb_index = "B" if zero_one_ratio < total_zero_one_ratio else "G"
        
        # Combined Index
        rounded_gb_odd = round(gb_odd) if gb_odd != float('inf') else 0
        combined_index = f"{int(rounded_gb_odd)}{gb_index}"
        
        results = {
            'good_count': good_count,
            'bad_count': bad_count,
            'total_count': total_count,
            'zero_one_ratio': round(zero_one_ratio, 4) if zero_one_ratio != float('inf') else 'Inf',
            'gb_odd': round(gb_odd, 0) if gb_odd != float('inf') else 'Inf',
            'gb_index': gb_index,
            'combined_index': combined_index,
            'bad_rate': round((bad_count / total_count * 100), 2) if total_count > 0 else 0
        }
        
        return jsonify({
            "success": True,
            "metrics": results
        })
        
    except Exception as e:
        return jsonify({"error": f"Failed to calculate scoring metrics: {str(e)}"}), 500

# ----------- Batch Calculate Scoring Metrics for Bins -----------
@app.route('/api/calculate-bin-metrics', methods=['POST'])
def calculate_bin_metrics():
    """
    Calculate scoring metrics for multiple bins at once
    """
    try:
        data = request.get_json()
        bins_data = data.get('bins', [])
        
        if not bins_data:
            return jsonify({"error": "No bin data provided"}), 400
        
        # Calculate totals for overall ratio
        total_good = sum(bin_data.get('good_count', 0) for bin_data in bins_data)
        total_bad = sum(bin_data.get('bad_count', 0) for bin_data in bins_data)
        
        # Calculate overall 0/1 ratio
        if total_bad > 0:
            total_zero_one_ratio = total_good / total_bad
        else:
            total_zero_one_ratio = float('inf')
        
        results = []
        
        for bin_data in bins_data:
            good_count = bin_data.get('good_count', 0)
            bad_count = bin_data.get('bad_count', 0)
            total_count = bin_data.get('total_count', 0)
            bin_name = bin_data.get('bin_name', 'Unknown')
            bin_range = bin_data.get('bin_range', '')
            
            # Calculate 0/1 ratio - Using good/bad as requested
            if bad_count > 0:
                zero_one_ratio = good_count / bad_count
            else:
                zero_one_ratio = float('inf')
            
            # G/B Odd calculation
            if zero_one_ratio < total_zero_one_ratio:
                if zero_one_ratio > 0:
                    gb_odd = (total_zero_one_ratio / zero_one_ratio) * 100
                else:
                    gb_odd = float('inf')
            else:
                if total_zero_one_ratio > 0:
                    gb_odd = (zero_one_ratio / total_zero_one_ratio) * 100
                else:
                    gb_odd = float('inf')
            
            # G/B Index
            gb_index = "B" if zero_one_ratio < total_zero_one_ratio else "G"
            
            # Combined Index
            rounded_gb_odd = round(gb_odd) if gb_odd != float('inf') else 0
            combined_index = f"{int(rounded_gb_odd)}{gb_index}"
            
            bin_metrics = {
                'bin_name': bin_name,
                'bin_range': bin_range,
                'good_count': good_count,
                'bad_count': bad_count,
                'total_count': total_count,
                'zero_one_ratio': round(zero_one_ratio, 4) if zero_one_ratio != float('inf') else 'Inf',
                'gb_odd': round(gb_odd, 0) if gb_odd != float('inf') else 'Inf',
                'gb_index': gb_index,
                'combined_index': combined_index,
                'bad_rate': round((bad_count / total_count * 100), 2) if total_count > 0 else 0
            }
            
            results.append(bin_metrics)
        
        return jsonify({
            "success": True,
            "bin_metrics": results,
            "total_zero_one_ratio": round(total_zero_one_ratio, 4) if total_zero_one_ratio != float('inf') else 'Inf',
            "total_good": total_good,
            "total_bad": total_bad
        })
        
    except Exception as e:
        return jsonify({"error": f"Failed to calculate bin metrics: {str(e)}"}), 500

# ----------- WOE/IV Calculation -----------
def calculate_woe_iv(df, variable, target, bin_merges=None, var_type=None):
    """
    Calculate WOE and IV using the exact formula: ROUND(LN(L5/M5) * 100, 1)
    No smoothing - return 0 for any infinite/non-finite situations.
    
    WOE = ROUND(LN(Dist_Good_% / Dist_Bad_%) * 100, 1)
    IV = (Dist_Good_% - Dist_Bad_%) * LN(Dist_Good_% / Dist_Bad_%) / 100
    """
    import numpy as np
    import pandas as pd
    import math
    from flask import current_app as app

    app.logger.debug(f"calculate_woe_iv → {variable} | merges: {bool(bin_merges)} | type: {var_type}")

    # Create a clean working copy to avoid modifying original
    df_work = df.copy()
    
    # Verify target encoding
    unique_targets = df_work[target].unique()
    app.logger.debug(f"Target unique values: {unique_targets}")
    
    # Ensure target is properly encoded (0=Good, 1=Bad)
    if set(unique_targets) != {0, 1}:
        app.logger.warning(f"Target may not be properly encoded. Unique values: {unique_targets}")

    # infer var_type if not provided
    if var_type is None:
        is_numeric = pd.api.types.is_numeric_dtype(df_work[variable])
        var_type = "continuous" if (is_numeric and df_work[variable].nunique(dropna=True) > 20) else "discrete"

    binned_col = f"{variable}_binned"

    # Verify binned column exists and has data
    if binned_col not in df_work.columns:
        raise ValueError(f"Column {binned_col} missing – coarse binning must be performed first.")
    
    # CRITICAL FIX: Remove rows where binned column is NaN before any processing
    initial_count = len(df_work)
    df_work = df_work.dropna(subset=[binned_col])
    removed_count = initial_count - len(df_work)
    if removed_count > 0:
        app.logger.debug(f"Removed {removed_count} rows with NaN in {binned_col}")

    if len(df_work) == 0:
        raise ValueError(f"No valid data remaining after removing NaN from {binned_col}")

    # build final_bin
    if var_type == "discrete" and bin_merges:
        coarse_to_merge = {}
        for merge_key, coarse_labels in bin_merges.items():
            for lbl in coarse_labels:
                coarse_to_merge[str(lbl).strip()] = str(merge_key).strip()
        df_work["final_bin"] = (
            df_work[binned_col].astype(str).str.strip().map(coarse_to_merge)
            .fillna(df_work[binned_col].astype(str).str.strip())
        )
    elif var_type == "continuous" and bin_merges:
        interval_to_merge = {}
        for merge_key, intervals in bin_merges.items():
            for iv in intervals:
                interval_to_merge[str(iv).strip()] = str(merge_key).strip()
        df_work["final_bin"] = (
            df_work[binned_col].astype(str).str.strip().map(interval_to_merge)
            .fillna(df_work[binned_col].astype(str).str.strip())
        )
    else:
        df_work["final_bin"] = df_work[binned_col].astype(str)

    # Remove any rows where final_bin is NaN (additional safety)
    df_work = df_work.dropna(subset=["final_bin"])

    # build range info
    bin_ranges = {}
    if var_type == "continuous":
        for lbl in df_work["final_bin"].unique():
            mask = df_work["final_bin"] == lbl
            vals = df_work.loc[mask, variable]
            mn = vals.min() if not vals.empty else None
            mx = vals.max() if not vals.empty else None
            bin_ranges[str(lbl)] = (float(mn) if mn is not None else None, float(mx) if mx is not None else None)
    else:
        for lbl in df_work["final_bin"].unique():
            mask = df_work["final_bin"] == lbl
            uniq = df_work.loc[mask, variable].unique()
            bin_ranges[str(lbl)] = sorted([str(v) for v in uniq])

    # preserve ordering where possible
    ordered_labels = None
    try:
        if var_type == "continuous":
            def _min_val(iv):
                try:
                    ivs = str(iv)
                    if ivs.startswith("(-inf,"): return float('-inf')
                    if ivs.startswith("["): return float(ivs.split(",")[0].replace("[", ""))
                    return float(ivs.split(",")[0].replace("(", ""))
                except Exception:
                    return float('inf')
            ordered = sorted(
                [(lbl, bin_ranges.get(str(lbl), (None, None))) for lbl in df_work["final_bin"].unique()],
                key=lambda x: _min_val(x[0])
            )
            ordered_labels = [lbl for lbl, _ in ordered]
        else:
            ordered_labels = list(dict.fromkeys(df_work["final_bin"].astype(str).tolist()))
    except Exception as e:
        app.logger.warning(f"Ordering failed for {variable}: {e}")

    # aggregate counts
    grouped = (
        df_work.groupby("final_bin", observed=True, sort=False)
        .agg(
            Total=(target, "count"),
            Good=(target, lambda x: (x == 0).sum()),
            Bad=(target, lambda x: (x == 1).sum()),
        )
        .reset_index()
    )

    if ordered_labels:
        present = [lbl for lbl in ordered_labels if lbl in grouped["final_bin"].astype(str).tolist()]
        if present:
            grouped = grouped.set_index("final_bin").reindex(present).reset_index()

    # CRITICAL FIX: Calculate totals from the ACTUAL BINNED DATA only
    total_good = grouped["Good"].sum()
    total_bad = grouped["Bad"].sum()
    total_all = grouped["Total"].sum()
    
    # Log the actual binned data totals
    app.logger.debug(f"=== WOE/IV CALCULATION VERIFICATION ===")
    app.logger.debug(f"Variable: {variable}")
    app.logger.debug(f"Original dataset: {len(df)} rows")
    app.logger.debug(f"After binning: {len(df_work)} rows")
    app.logger.debug(f"Binned data - Total Good: {total_good}, Total Bad: {total_bad}, Total All: {total_all}")
    app.logger.debug(f"Good + Bad = {total_good + total_bad}, Should equal Total: {total_all}")
    if total_all > 0:
        app.logger.debug(f"Good Rate: {(total_good/total_all*100):.2f}%, Bad Rate: {(total_bad/total_all*100):.2f}%")

    n_bins = len(grouped)

    if n_bins == 0:
        return 0.0, []

    stats = []
    iv_total = 0.0

    # Calculate percentages (Dist_Good_% and Dist_Bad_%)
    for _, row in grouped.iterrows():
        g = int(row["Good"])
        b = int(row["Bad"])
        total_in_bin = int(row["Total"])

        # Calculate percentages from ACTUAL BINNED TOTALS
        dist_good_pct = (g / total_good * 100.0) if total_good > 0 else 0.0
        dist_bad_pct = (b / total_bad * 100.0) if total_bad > 0 else 0.0

        # Verify bin percentages
        bin_good_rate = (g / total_in_bin * 100) if total_in_bin > 0 else 0
        bin_bad_rate = (b / total_in_bin * 100) if total_in_bin > 0 else 0
        
        app.logger.debug(f"Bin '{row['final_bin']}': Good={g}, Bad={b}, Total={total_in_bin}")
        app.logger.debug(f"  Dist Good%: {dist_good_pct:.4f} (should be: {g}/{total_good}*100 = {(g/total_good*100):.4f})")
        app.logger.debug(f"  Dist Bad%: {dist_bad_pct:.4f} (should be: {b}/{total_bad}*100 = {(b/total_bad*100):.4f})")
        app.logger.debug(f"  Bin Good%: {bin_good_rate:.2f}%, Bin Bad%: {bin_bad_rate:.2f}%")

        woe_val = 0.0
        iv_val = 0.0

        # Exact formula: ROUND(LN(L5/M5) * 100, 1) with no smoothing
        if dist_good_pct > 0.0 and dist_bad_pct > 0.0:
            try:
                ratio = dist_good_pct / dist_bad_pct
                ln_ratio = math.log(ratio)
                if math.isfinite(ln_ratio):
                    # WOE = ROUND(LN(L5/M5) * 100, 1)
                    woe_val = round(ln_ratio * 100.0, 1)
                
                    iv_val = (dist_good_pct - dist_bad_pct) * ln_ratio 
                else:
                    woe_val = 0.0
                    iv_val = 0.0
            except (ValueError, ZeroDivisionError):
                woe_val = 0.0
                iv_val = 0.0
        else:
            # No smoothing - return 0 if either percentage is zero
            woe_val = 0.0
            iv_val = 0.0

        # Accumulate total IV
        if math.isfinite(iv_val):
            iv_total += float(iv_val)/100 # since iv_val is in percentage terms

        bin_label = str(row["final_bin"])
        range_info = bin_ranges.get(bin_label, (None, None) if var_type == "continuous" else [])
        range_str = (f"{range_info[0]} - {range_info[1]}" if var_type == "continuous"
                     else ', '.join(map(str, range_info)))

        stats.append({
            "Bin": bin_label,
            "Good": int(g),
            "Bad": int(b),
            "Total": int(total_in_bin),
            "Dist_Good_%": round(dist_good_pct, 4),
            "Dist_Bad_%": round(dist_bad_pct, 4),
            "WOE": float(woe_val),
            "IV": round(float(iv_val), 4),
            "Range": range_str,
        })

    app.logger.debug(f"Total IV for {variable}: {round(float(iv_total), 4)}")
    return round(float(iv_total), 4), stats

# ----------- WOE/IV API -----------
# ----------- WOE/IV API -----------
@app.route("/api/woe-iv", methods=["POST"])
def woe_iv_api():
    try:
        data = request.get_json()
        variables = data.get("variables", [])
        target = data.get("target")
        record_id = data.get("record_id")
        global_type = data.get("type")
        types_map = data.get("types", {}) if isinstance(data.get("types", {}), dict) else {}

        raw_bin_merges = data.get("bin_merges")

        def normalize_merge_map(merge_map):
            normalized = {}
            if isinstance(merge_map, dict):
                for group_key, group_vals in merge_map.items():
                    if group_vals is None:
                        continue
                    if isinstance(group_vals, (list, tuple, set)):
                        normalized[str(group_key).strip()] = [str(item).strip() for item in group_vals]
                    else:
                        normalized[str(group_key).strip()] = [str(group_vals).strip()]
            return {k: v for k, v in normalized.items() if v}

        requested_bin_merges = {}
        if isinstance(raw_bin_merges, dict) and raw_bin_merges:
            values = list(raw_bin_merges.values())
            # Case 1: Nested map { variable: { merge_key: [...] } }
            if values and all(isinstance(v, dict) for v in values):
                for var_key, merge_map in raw_bin_merges.items():
                    normalized = normalize_merge_map(merge_map)
                    if normalized:
                        requested_bin_merges[str(var_key)] = normalized
                        try:
                            print(f"WOE/IV DEBUG: Received {len(normalized)} merge groups from request for {var_key}")
                        except Exception:
                            pass
            # Case 2: Single-variable payload { merge_key: [...] }
            elif len(variables) == 1:
                normalized = normalize_merge_map(raw_bin_merges)
                if normalized:
                    requested_bin_merges[str(variables[0])] = normalized
                    try:
                        print(f"WOE/IV DEBUG: Received {len(normalized)} merge groups from request for {variables[0]}")
                    except Exception:
                        pass

        print(f"WOE/IV DEBUG: Starting with variables: {variables}, target: {target}")

        if not variables or not target:
            return jsonify({"error": "Missing required fields: variables or target"}), 400

        csv_path = get_csv_path()
        df = pd.read_csv(csv_path)
        
        if target not in df.columns:
            return jsonify({"error": f"Target column '{target}' not found in dataset"}), 400
        
        # Better target validation
        df[target] = df[target].fillna(0)
        
        # Ensure target is properly encoded as integers (0=Good, 1=Bad)
        try:
            df[target] = df[target].astype(int)
        except (ValueError, TypeError):
            # If target is not numeric, encode it properly
            unique_vals = df[target].unique()
            if len(unique_vals) == 2:
                # Map to 0 and 1
                val_map = {unique_vals[0]: 0, unique_vals[1]: 1}
                df[target] = df[target].map(val_map)
            else:
                return jsonify({"error": f"Target must have exactly 2 unique values, found {len(unique_vals)}"}), 400
        
        target_distribution = df[target].value_counts().to_dict()
        print(f"WOE/IV DEBUG: Target distribution - Good (0): {target_distribution.get(0, 0)}, Bad (1): {target_distribution.get(1, 0)}")
        
        if target_distribution.get(1, 0) == 0:
            return jsonify({"error": "No bad cases (target=1) found in dataset"}), 400

        results = {}

        # Load saved coarse bins if record_id provided
        existing_binned_columns = {}
        if record_id:
            try:
                record_data = get_record_db(record_id)
                if record_data and record_data.get('univariate_results'):
                    univariate_results = json.loads(record_data['univariate_results'])
                    for var in variables:
                        if var in univariate_results:
                            var_data = univariate_results[var]
                            saved_type = var_data.get('type', None)
                            # Use fresh data copy for each variable
                            temp_df = df.copy()
                            if saved_type == 'discrete':
                                _, temp_df[f"{var}_binned"], _ = coarse_bin_discrete(temp_df, var, target)
                            else:
                                _, temp_df[f"{var}_binned"] = coarse_bin_continuous(temp_df, var, target)
                            
                            # Copy only the binned column back to main dataframe
                            df[f"{var}_binned"] = temp_df[f"{var}_binned"]
                            existing_binned_columns[var] = True
                            print(f"WOE/IV DEBUG: Loaded saved bins for {var}, type: {saved_type}")
            except Exception as e:
                print(f"WOE/IV DEBUG: Could not load saved univariate results: {e}")

        # Create coarse bins for variables that are new
        for var in variables:
            if var in existing_binned_columns:
                continue
                
            var_series = df[var]
            is_likely_id = any(k in var.lower() for k in ['id', 'key', 'code', 'no', 'num'])
            unique_cnt = var_series.nunique(dropna=True)

            # Use fresh data copy for each variable
            temp_df = df.copy()
            
            if pd.api.types.is_numeric_dtype(var_series):
                if is_likely_id or unique_cnt <= 50:
                    try:
                        _, temp_df[f"{var}_binned"], _ = coarse_bin_discrete(temp_df, var, target)
                        print(f"WOE/IV DEBUG: Created discrete bins for {var} (numeric with {unique_cnt} unique values)")
                    except Exception as e:
                        print(f"WOE/IV DEBUG: Failed to create discrete bins for {var}: {e}")
                        continue
                else:
                    try:
                        _, temp_df[f"{var}_binned"] = coarse_bin_continuous(temp_df, var, target)
                        print(f"WOE/IV DEBUG: Created continuous bins for {var} (numeric with {unique_cnt} unique values)")
                    except Exception as e:
                        print(f"WOE/IV DEBUG: Failed to create continuous bins for {var}: {e}")
                        continue
            else:
                try:
                    _, temp_df[f"{var}_binned"], _ = coarse_bin_discrete(temp_df, var, target)
                    print(f"WOE/IV DEBUG: Created discrete bins for {var} (non-numeric)")
                except Exception as e:
                    print(f"WOE/IV DEBUG: Failed to create discrete bins for {var}: {e}")
                    continue
            
            # Copy only the binned column back to main dataframe
            df[f"{var}_binned"] = temp_df[f"{var}_binned"]

        # Load saved fine-bin merges
        merges_per_var = {}
        if record_id:
            for var in variables:
                finebin_details = get_finebin_details_db(record_id, var)
                if finebin_details:
                    merges = {}
                    for row in finebin_details:
                        try:
                            bins_loaded = json.loads(row["merged_bins"])
                            if isinstance(bins_loaded, (list, tuple, set)):
                                merges[str(row["group_id"]).strip()] = [str(item).strip() for item in bins_loaded]
                            elif bins_loaded is not None:
                                merges[str(row["group_id"]).strip()] = [str(bins_loaded).strip()]
                        except Exception:
                            pass
                    if merges:
                        merges_per_var[var] = merges
                        print(f"WOE/IV DEBUG: Loaded {len(merges)} merge groups for {var}")

        # Override/augment with merges provided directly in the request body
        if requested_bin_merges:
            for var_key, merge_map in requested_bin_merges.items():
                if merge_map:
                    merges_per_var[var_key] = merge_map
                    try:
                        print(f"WOE/IV DEBUG: Applying request merge overrides for {var_key} ({len(merge_map)} groups)")
                    except Exception:
                        pass

        # Compute WOE/IV per variable
        for var in variables:
            # Skip if we couldn't create bins for this variable
            if f"{var}_binned" not in df.columns:
                print(f"WOE/IV DEBUG: Skipping {var} - no binned column created")
                continue
                
            # determine var_type for this variable
            var_type_for_var = types_map.get(var) or global_type
            if not var_type_for_var:
                if pd.api.types.is_numeric_dtype(df[var]):
                    is_likely_id = any(k in var.lower() for k in ['id', 'key', 'code', 'no', 'num'])
                    unique_cnt = df[var].nunique(dropna=True)
                    var_type_for_var = 'discrete' if (is_likely_id or unique_cnt <= 50) else 'continuous'
                else:
                    var_type_for_var = 'discrete'

            merges = merges_per_var.get(var)
            
            # Compute WOE/IV
            try:
                iv, stats = calculate_woe_iv(
                    df=df,
                    variable=var,
                    target=target,
                    bin_merges=merges,
                    var_type=var_type_for_var
                )
                results[var] = {"iv": iv, "stats": stats}
                print(f"WOE/IV DEBUG: Calculated WOE/IV for {var} - IV: {iv}, bins: {len(stats)}")
            except Exception as e:
                print(f"WOE/IV DEBUG: Failed to calculate WOE/IV for {var}: {e}")
                results[var] = {"iv": 0, "stats": []}

        # Persist results if record_id provided
        if record_id:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("SELECT woe_iv_results FROM records WHERE id = %s", (record_id,))
            row = cur.fetchone()
            existing_woe = {}
            if row and row[0]:
                try:
                    existing_woe = json.loads(row[0])
                except json.JSONDecodeError:
                    existing_woe = {}

            # Defensive coercion: some older records may have stored a JSON list
            # (e.g. json.dumps([])). Ensure we have a dict before calling update().
            if isinstance(existing_woe, list):
                coerced = {}
                for item in existing_woe:
                    if isinstance(item, dict):
                        # Merge dict entries; later entries override earlier ones
                        for k, v in item.items():
                            coerced[str(k)] = v
                existing_woe = coerced

            # If still not a dict, replace with empty dict to avoid attribute errors
            if not isinstance(existing_woe, dict):
                existing_woe = {}

            # Merge new results into existing map
            existing_woe.update(results)
            cur.execute(
                "UPDATE records SET woe_iv_results = %s WHERE id = %s",
                (json.dumps(existing_woe), record_id)
            )
            conn.commit()
            conn.close()

        print(f"WOE/IV DEBUG: Completed successfully for {len(results)} variables")
        return jsonify(results)

    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"WOE/IV ERROR: {str(e)}")
        print(f"WOE/IV TRACEBACK: {error_trace}")
        return jsonify({"error": f"WOE/IV calculation failed: {str(e)}"}), 500
# ----------- Save Record -----------
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
        # Only update dashboard_selected_columns if provided; otherwise keep existing
        if 'dashboard_selected_columns' in data:
            dsc = data.get('dashboard_selected_columns')
            if isinstance(dsc, list):
                dashboard_selected_columns = ','.join(dsc)
            elif isinstance(dsc, str):
                dashboard_selected_columns = dsc
            else:
                dashboard_selected_columns = ''
        else:
            dashboard_selected_columns = None
        target_variable = data.get('target_variable', '')
        univariate_results = data.get('univariate_results', '')
        finebin_results = data.get('finebin_results', '')
        crosstab_results = data.get('crosstab_results', '')
        record_id = save_record_db(
            dataset_path, discrete_columns, continuous_columns,
            selected_columns, dashboard_selected_columns, target_variable, univariate_results,
            finebin_results, crosstab_results
        )
        return jsonify({"success": True, "id": record_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ----------- Upsert Single Record -----------
@app.route('/api/upsert-single-record', methods=['POST'])
def upsert_single_record():
    """
    Create or update a single record. If no record exists, insert one; otherwise update the latest record.
    This supports the UX where only one record should exist and be updated across actions.
    """
    try:
        data = request.get_json()
        try:
            print('[backend] upsert_single_record payload keys:', list(data.keys()) if isinstance(data, dict) else type(data))
        except Exception:
            pass
        dataset_path = data.get('dataset_path', '')
        discrete_columns = ','.join(data.get('discrete_columns', []))
        continuous_columns = ','.join(data.get('continuous_columns', []))
        selected_columns = ','.join(data.get('selected_columns', []))
        # Preserve existing dashboard_selected_columns unless explicitly provided
        if 'dashboard_selected_columns' in data:
            dsc = data.get('dashboard_selected_columns')
            if isinstance(dsc, list):
                dashboard_selected_columns = ','.join(dsc)
            elif isinstance(dsc, str):
                dashboard_selected_columns = dsc
            else:
                dashboard_selected_columns = ''
            try:
                print('[backend] upsert_single_record dashboard_selected_columns (provided):', dashboard_selected_columns)
            except Exception:
                pass
        else:
            dashboard_selected_columns = None  # triggers COALESCE to keep existing
            try:
                print('[backend] upsert_single_record dashboard_selected_columns not provided -> preserve existing')
            except Exception:
                pass
        target_variable = data.get('target_variable', '')
        univariate_results = data.get('univariate_results', '')
        finebin_results = data.get('finebin_results', '')
        crosstab_results = data.get('crosstab_results', '')
        woe_iv_results = data.get('woe_iv_results', '')
        record_id = upsert_single_record_db(
            dataset_path, discrete_columns, continuous_columns,
            selected_columns, dashboard_selected_columns, target_variable, univariate_results,
            finebin_results, crosstab_results, woe_iv_results
        )
        return jsonify({"success": True, "id": record_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ----------- Get Records -----------
@app.route('/api/records', methods=['GET'])
def get_records():
    """
    List all analysis records (summary only).
    """
    try:
        records = get_records_db()
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
        dataset_path, resolved_path, valid = get_latest_record_dataset_path_db()
        return jsonify({
            "dataset_path": dataset_path,
            "resolved_path": resolved_path,
            "valid": valid
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ----------- Get Record -----------
@app.route('/api/record/<int:record_id>', methods=['GET'])
def get_record(record_id):
    """
    Get a specific analysis record (full details).
    """
    try:
        record = get_record_db(record_id)
        if record:
            try:
                print('[backend] get_record returning dashboard_selected_columns:', record.get('dashboard_selected_columns'))
            except Exception:
                pass
            try:
                # Ensure types are serializable and add parsing indicators
                dbg = record.get('dashboard_selected_columns')
                print('[backend] get_record raw dashboard_selected_columns type:', type(dbg), 'value:', dbg)
            except Exception:
                pass
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

@app.route('/api/record/<int:record_id>/load-dataset', methods=['GET'])
def load_record_dataset(record_id):
    """
    Loads the dataset for a given record and returns it as JSON.
    """
    try:
        record = get_record_db(record_id)
        if not record:
            return jsonify({"error": "Record not found"}), 404
        dataset_path = record.get('dataset_path')
        if not dataset_path:
            return jsonify({"error": "No dataset_path in record"}), 404
        # Resolve relative path if needed
        if not os.path.isabs(dataset_path):
            dataset_path = os.path.join(os.path.dirname(__file__), dataset_path)
        if not os.path.exists(dataset_path):
            return jsonify({"error": f"Dataset file not found: {dataset_path}"}), 404
        df = pd.read_csv(dataset_path)
        return jsonify({"data": df.to_dict(orient="records"), "columns": df.columns.tolist()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
# ----------- Logistic Regression Analysis -----------
@app.route('/api/logistic-regression', methods=['POST'])
def logistic_regression_analysis():
    """
    Perform logistic regression analysis on selected variables.
    Expects payload: { selected_variables: [list], target: string, woe_transformed_data: {} }
    Returns: model metrics, coefficients, p-values, VIF, Gini, ROC data
    """
    def sanitize_for_json(obj):
        """Recursively replace NaN/inf with None for valid JSON."""
        import numpy as np
        if isinstance(obj, dict):
            return {sanitize_for_json(k): sanitize_for_json(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [sanitize_for_json(item) for item in obj]
        elif isinstance(obj, (np.integer, np.floating)):
            if np.isnan(obj) or np.isinf(obj):
                return None
            return float(obj)
        elif isinstance(obj, (int, float)):
            if math.isnan(obj) or math.isinf(obj):
                return None
            return obj
        else:
            return obj

    try:
        data = request.get_json()
        selected_variables = data.get('selected_variables', [])
        target = data.get('target')
        woe_transformed_data = data.get('woe_transformed_data', {})

        if not selected_variables or not target:
            return jsonify({"error": "Missing selected_variables or target"}), 400

        # Load CSV into df at the very start
        try:
            df = pd.read_csv(get_csv_path())
        except Exception as e:
            return jsonify({"error": f"Failed to load CSV: {str(e)}"}), 400

        if target not in df.columns:
            return jsonify({"error": f"Target variable '{target}' not found in dataset"}), 400

        # Filter to only variables with WOE data to avoid constant 0 columns
        valid_selected_vars = [var for var in selected_variables if var in woe_transformed_data]
        if len(valid_selected_vars) == 0:
            return jsonify({"error": "No variables have valid WOE transformations. Please check your WOE setup."}), 400
        if len(valid_selected_vars) < len(selected_variables):
            print(f"LOGISTIC DEBUG: Skipped {len(selected_variables) - len(valid_selected_vars)} variables without WOE data")

        selected_variables = valid_selected_vars  # Update to valid only
        woe_df = df[[target]].copy()
        dropped_constants = []

        for var in selected_variables:
            # Robust WOE mapping + diagnostics
            raw_bins = woe_transformed_data.get(var)
            if isinstance(raw_bins, dict) and isinstance(raw_bins.get('stats'), list):
                bins_list = raw_bins.get('stats')
            elif isinstance(raw_bins, list):
                bins_list = raw_bins
            else:
                bins_list = []
            if not bins_list:
                print(f"LOGISTIC DEBUG: no bin definitions found for '{var}' in woe_transformed_data")
                continue  # Skip if no bins

            woe_df[f'{var}_WOE'] = np.nan
            for bin_info in bins_list:
                bin_range = bin_info.get('range') or bin_info.get('Range') or bin_info.get('Bin') or bin_info.get('bin')
                woe_value = bin_info.get('woe') or bin_info.get('WOE')
                if woe_value is None:
                    continue
                try:
                    woe_value = float(woe_value)
                except Exception:
                    continue
                if isinstance(bin_range, (list, tuple)):
                    mask = df[var].isin(bin_range)
                    woe_df.loc[mask, f'{var}_WOE'] = woe_value
                    continue
                if isinstance(bin_range, str):
                    br = bin_range.strip()
                    if ' to ' in br:
                        parts = [p.strip() for p in br.split(' to ')]
                    elif '-' in br and any(ch.isdigit() for ch in br):
                        parts = [p.strip() for p in re.split(r"-", br, maxsplit=1)]
                    else:
                        parts = None
                    if parts and len(parts) == 2:
                        try:
                            min_val = float(parts[0])
                            max_val = float(parts[1])
                            mask = (pd.to_numeric(df[var], errors='coerce') >= min_val) & (pd.to_numeric(df[var], errors='coerce') <= max_val)
                            woe_df.loc[mask.fillna(False), f'{var}_WOE'] = woe_value
                            continue
                        except Exception:
                            pass
                    cats = re.split(r'[\,\|;]', br)
                    cats = [c.strip() for c in cats if c.strip() != '']
                    if len(cats) > 1:
                        mask = df[var].astype(str).isin(cats)
                        woe_df.loc[mask, f'{var}_WOE'] = woe_value
                        continue
                    mask = df[var].astype(str) == br
                    woe_df.loc[mask, f'{var}_WOE'] = woe_value
                else:
                    mask = df[var].astype(str) == str(bin_range)
                    woe_df.loc[mask, f'{var}_WOE'] = woe_value
            non_null = int(woe_df[f'{var}_WOE'].notna().sum())
            print(f"LOGISTIC DEBUG: mapped WOE rows for '{var}':", non_null, "of", len(df))
            woe_df[f'{var}_WOE'] = woe_df[f'{var}_WOE'].fillna(0)

        feature_cols = [f'{var}_WOE' for var in selected_variables]
        X = woe_df[feature_cols].fillna(0)
        y = woe_df[target]

        mask = ~y.isna()
        X = X[mask]
        y = y[mask]

        if len(X) == 0:
            return jsonify({"error": "No valid data after preprocessing"}), 400

        # Remove constant features (zero variance)
        variances = X.var()
        constant_cols = variances[variances == 0].index.tolist()
        if constant_cols:
            dropped_constants = [col.replace('_WOE', '') for col in constant_cols]
            print(f"LOGISTIC DEBUG: Removing constant columns: {dropped_constants}")
            X = X.drop(columns=constant_cols)
            feature_cols = [col for col in feature_cols if col not in constant_cols]
            selected_variables = [var for var in selected_variables if f'{var}_WOE' not in constant_cols]

        if len(selected_variables) == 0:
            return jsonify({"error": "All features are constant after WOE transformation. Try fewer or different variables."}), 400

        # Iterative VIF-based feature removal to prevent singularity
        max_vif_threshold = 10.0
        vif_dropped = []
        while len(X.columns) > 0:
            # Compute VIFs
            vif_data_temp = []
            X_with_const_temp = sm.add_constant(X)
            for i in range(1, len(X.columns) + 1):  # Skip const
                try:
                    vif = variance_inflation_factor(X_with_const_temp.values, i)
                    if np.isfinite(vif):
                        vif_data_temp.append((X.columns[i-1], vif))
                    else:
                        vif_data_temp.append((X.columns[i-1], np.inf))
                except Exception:
                    vif_data_temp.append((X.columns[i-1], np.inf))
            
            if not vif_data_temp:
                break
            
            # Find max VIF column
            max_vif_col, max_vif = max(vif_data_temp, key=lambda x: x[1])
            
            if max_vif < max_vif_threshold:
                break  # All good
            
            # Drop the high VIF column
            print(f"LOGISTIC DEBUG: Dropping high VIF column '{max_vif_col}' (VIF: {max_vif})")
            X = X.drop(columns=[max_vif_col])
            feature_cols = [col for col in feature_cols if col not in [max_vif_col]]
            selected_variables = [var for var in selected_variables if f'{var}_WOE' not in [max_vif_col]]
            vif_dropped.append(max_vif_col.replace('_WOE', ''))
        
        dropped_variables = dropped_constants + vif_dropped
        if len(selected_variables) == 0:
            return jsonify({"error": f"All features removed due to constants or high multicollinearity (VIF > {max_vif_threshold}). Try selecting fewer or less correlated variables."}), 400

        # Check for linear dependence via matrix rank
        X_const = sm.add_constant(X)
        rank = np.linalg.matrix_rank(X_const)
        full_rank = X_const.shape[1]
        rank_dropped = []
        while rank < full_rank and len(X.columns) > 0:
            # Drop the feature with lowest variance (least informative)
            var_dict = X.var().to_dict()
            if not var_dict:
                break
            to_drop = min(var_dict, key=var_dict.get)
            print(f"LOGISTIC DEBUG: Dropping low-variance column '{to_drop}' due to rank deficiency")
            X = X.drop(to_drop, axis=1)
            feature_cols = [col for col in feature_cols if col not in [to_drop]]
            selected_variables = [var for var in selected_variables if f'{var}_WOE' not in [to_drop]]
            rank_dropped.append(to_drop.replace('_WOE', ''))
            X_const = sm.add_constant(X)
            rank = np.linalg.matrix_rank(X_const)
            full_rank = X_const.shape[1]

        dropped_variables += rank_dropped
        if len(selected_variables) == 0:
            return jsonify({"error": "All features removed due to linear dependence. Try fewer variables."}), 400

        # Diagnostics (updated for current X)
        try:
            nunique = X.nunique()
            zero_var_cols = nunique[nunique <= 1].index.tolist()  # Should be empty now
            variances = X.var().to_dict()
            dup_mask = X.T.duplicated()
            dup_cols = X.columns[dup_mask].tolist()
            sample = X.head(5).to_dict(orient='records')
            y_counts = y.value_counts().to_dict()
            print("LOGISTIC DEBUG: X sample rows:", sample)
            print(f"LOGISTIC DEBUG: Final rank check - Rank: {rank}, Full: {full_rank}")
        except Exception as _diag:
            print("LOGISTIC DEBUG: diagnostics failed:", str(_diag))

        # Warn if too many variables relative to observations
        n_features = len(selected_variables)
        n_obs = len(X)
        if n_features > n_obs / 10:  # Stricter: 10 obs per feature
            print(f"LOGISTIC DEBUG: Warning - Very high dimensionality: {n_features} features vs {n_obs} observations. Model may be unstable.")

        # Now fit the model with robust optimizer
        logit_model = sm.Logit(y, X_const)
        result = None
        methods_to_try = ['bfgs', 'newton', 'nm']  # Fallback optimizers
        for method in methods_to_try:
            try:
                print(f"LOGISTIC DEBUG: Trying fit with method='{method}'")
                result = logit_model.fit(disp=0, method=method, maxiter=1000)
                print(f"LOGISTIC DEBUG: Fit succeeded with {method}")
                break
            except Exception as fit_err:
                print(f"LOGISTIC DEBUG: Fit failed with {method}: {fit_err}")
                if method == methods_to_try[-1]:  # Last one
                    return jsonify({"error": f"Model fitting failed with all optimizers due to data issues (e.g., perfect separation). Try fewer variables. Error: {str(fit_err)}"}), 400
                continue

        if result is None:
            return jsonify({"error": "Model fitting failed unexpectedly."}), 500

        # VIF on final model
        vif_data = []
        if len(feature_cols) > 1:
            X_with_const_final = sm.add_constant(X)
            for i in range(1, len(feature_cols) + 1):
                try:
                    vif = variance_inflation_factor(X_with_const_final.values, i)
                    vif_data.append({
                        'variable': selected_variables[i-1],
                        'vif': float(vif) if not np.isnan(vif) and not np.isinf(vif) else None
                    })
                except Exception as vif_err:
                    print(f"LOGISTIC DEBUG: VIF failed for {selected_variables[i-1]}: {vif_err}")
                    vif_data.append({
                        'variable': selected_variables[i-1],
                        'vif': None
                    })

        y_pred_proba = result.predict(X_const)
        fpr, tpr, thresholds = roc_curve(y, y_pred_proba)
        roc_auc = auc(fpr, tpr)
        gini_coefficient = 2 * roc_auc - 1

        try:
            y_pred = (y_pred_proba >= 0.5).astype(int)
        except Exception:
            y_pred = (np.array(y_pred_proba) >= 0.5).astype(int)

        try:
            cm = confusion_matrix(y, y_pred)
            accuracy = accuracy_score(y, y_pred)
            precision = precision_score(y, y_pred, zero_division=0)
            recall = recall_score(y, y_pred, zero_division=0)
            f1 = f1_score(y, y_pred, zero_division=0)
        except Exception as _cm_err:
            cm = np.array([[0, 0], [0, 0]])
            accuracy = precision = recall = f1 = 0.0

        try:
            fig, ax = plt.subplots(figsize=(4, 4))
            im = ax.imshow(cm, interpolation='nearest', cmap='Blues')
            ax.set_title('Confusion Matrix')
            ax.set_ylabel('Actual')
            ax.set_xlabel('Predicted')
            ax.set_xticks([0, 1])
            ax.set_yticks([0, 1])
            ax.set_xticklabels(['0', '1'])
            ax.set_yticklabels(['0', '1'])
            thresh = cm.max() / 2.0 if cm.max() != 0 else 0
            for i in range(cm.shape[0]):
                for j in range(cm.shape[1]):
                    color = 'white' if cm[i, j] > thresh else 'black'
                    ax.text(j, i, format(int(cm[i, j])), ha='center', va='center', color=color, fontsize=12)
            plt.tight_layout()
            buf = BytesIO()
            fig.savefig(buf, format='png', dpi=150)
            plt.close(fig)
            buf.seek(0)
            img_b64 = base64.b64encode(buf.read()).decode('utf-8')
            cm_image_data = f"data:image/png;base64,{img_b64}"
        except Exception as _img_err:
            cm_image_data = None

        coefficients = []
        p_values = []
        for i, var in enumerate(['const'] + selected_variables):
            coef = result.params[i] if i < len(result.params) else 0
            p_val = result.pvalues[i] if i < len(result.pvalues) else 1
            if var == 'const':
                coefficients.append({
                    'variable': 'Intercept',
                    'coefficient': float(coef) if np.isfinite(coef) else None,
                    'significance': 'Highly Significant' if p_val < 0.01 else 'Significant' if p_val < 0.05 else 'Not Significant'
                })
                p_values.append({
                    'variable': 'Intercept',
                    'p_value': float(p_val) if np.isfinite(p_val) else None,
                    'significance': 'Highly Significant' if p_val < 0.01 else 'Significant' if p_val < 0.05 else 'Not Significant'
                })
            else:
                coefficients.append({
                    'variable': var,
                    'coefficient': float(coef) if np.isfinite(coef) else None,
                    'significance': 'Highly Significant' if p_val < 0.01 else 'Significant' if p_val < 0.05 else 'Not Significant'
                })
                p_values.append({
                    'variable': var,
                    'p_value': float(p_val) if np.isfinite(p_val) else None,
                    'significance': 'Highly Significant' if p_val < 0.01 else 'Significant' if p_val < 0.05 else 'Not Significant'
                })

        def _sanitize_number(x):
            try:
                v = float(x)
                return v if np.isfinite(v) else None
            except Exception:
                return None

        try:
            raw_thresholds = list(thresholds)
            print('LOGISTIC DEBUG: raw thresholds sample (first 10):', raw_thresholds[:10])
            nonfinite_idxs = [i for i, t in enumerate(raw_thresholds) if not np.isfinite(t)]
            if nonfinite_idxs:
                print('LOGISTIC DEBUG: found non-finite thresholds at indices:', nonfinite_idxs,
                      'values:', [raw_thresholds[i] for i in nonfinite_idxs])
        except Exception as _th_err:
            print('LOGISTIC DEBUG: could not inspect thresholds:', str(_th_err))

        roc_data = [{'fpr': _sanitize_number(f), 'tpr': _sanitize_number(t), 'threshold': _sanitize_number(th)}
                    for f, t, th in zip(fpr, tpr, thresholds)]

        try:
            diffs = [abs(t - f) for f, t in zip(fpr, tpr)]
            ks_idx = int(np.argmax(diffs)) if len(diffs) > 0 else 0
            ks_stat_raw = diffs[ks_idx] if len(diffs) > 0 else 0.0
            ks_threshold_raw = thresholds[ks_idx] if len(thresholds) > 0 else 0.0
            ks_stat = float(ks_stat_raw) if np.isfinite(ks_stat_raw) else None
            ks_threshold = float(ks_threshold_raw) if np.isfinite(ks_threshold_raw) else None
            ks_curve = []
            for f, t, th in zip(fpr, tpr, thresholds):
                ks_curve.append({'threshold': _sanitize_number(th), 'tpr': _sanitize_number(t), 'fpr': _sanitize_number(f), 'diff': _sanitize_number(abs(t - f))})
            if ks_threshold is None:
                print('LOGISTIC DEBUG: KS threshold was non-finite; sanitized to None')
        except Exception as _ks_err:
            print('LOGISTIC DEBUG: KS computation failed:', str(_ks_err))
            ks_stat = None
            ks_threshold = None
            ks_curve = []

        model_stats = {
            'aic': float(result.aic) if np.isfinite(result.aic) else None,
            'bic': float(result.bic) if np.isfinite(result.bic) else None,
            'log_likelihood': float(result.llf) if np.isfinite(result.llf) else None,
            'pseudo_r_squared': float(result.prsquared) if np.isfinite(result.prsquared) else None,
            'n_observations': int(result.nobs)
        }

        try:
            print('LOGISTIC DEBUG: roc_data sample (first 8):', roc_data[:8])
            if any(item.get('threshold') is None for item in roc_data):
                print('LOGISTIC DEBUG: some roc_data.threshold entries are None')
            print('LOGISTIC DEBUG: ks_curve sample (first 8):', ks_curve[:8])
            if any(item.get('diff') is None for item in ks_curve):
                print('LOGISTIC DEBUG: some ks_curve.diff entries are None')
        except Exception as _log_err:
            print('LOGISTIC DEBUG: pre-return inspection failed:', str(_log_err))

        # Include dropped info in response for frontend (optional)
        resp = {
            'success': True,
            'coefficients': coefficients,
            'p_values': p_values,
            'vif_data': vif_data,
            'gini_coefficient': float(gini_coefficient) if np.isfinite(gini_coefficient) else None,
            'auc': float(roc_auc) if np.isfinite(roc_auc) else None,
            'roc_data': roc_data,
            'model_stats': model_stats,
            'confusion_matrix': (cm.tolist() if isinstance(cm, (list, np.ndarray)) else None),
            'confusion_matrix_image': cm_image_data,
            'accuracy': float(accuracy) if np.isfinite(accuracy) else None,
            'precision': float(precision) if np.isfinite(precision) else None,
            'recall': float(recall) if np.isfinite(recall) else None,
            'f1': float(f1) if np.isfinite(f1) else None,
            'ks_stat': ks_stat,
            'ks_threshold': ks_threshold,
            'ks_curve': ks_curve,
            'dropped_variables': dropped_variables  # Updated: includes constants, high-VIF, rank-deficient
        }

        # Sanitize entire response for JSON
        resp = sanitize_for_json(resp)

        if dropped_variables:
            print(f"LOGISTIC DEBUG: Dropped variables: {dropped_variables}")

        return jsonify(resp)

    except Exception as e:
        print(f"LOGISTIC DEBUG: Unhandled error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Failed to perform logistic regression: {str(e)}"}), 500


# ----------- Random Forest Analysis -----------
@app.route('/api/random-forest', methods=['POST'])
def random_forest_analysis():
    """
    Perform Random Forest analysis on selected variables.
    Expects payload: { selected_variables: [list], target: string, woe_transformed_data: {} }
    Returns: model metrics, feature importance, ROC data, etc.
    """
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.metrics import roc_curve, auc, classification_report, confusion_matrix, accuracy_score, precision_score, recall_score, f1_score

    def sanitize_for_json(obj):
        """Recursively replace NaN/inf with None for valid JSON."""
        import numpy as np
        if isinstance(obj, dict):
            return {sanitize_for_json(k): sanitize_for_json(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [sanitize_for_json(item) for item in obj]
        elif isinstance(obj, (np.integer, np.floating)):
            if np.isnan(obj) or np.isinf(obj):
                return None
            return float(obj)
        elif isinstance(obj, (int, float)):
            if math.isnan(obj) or math.isinf(obj):
                return None
            return obj
        else:
            return obj

    try:
        data = request.get_json()
        selected_variables = data.get('selected_variables', [])
        target = data.get('target')
        woe_transformed_data = data.get('woe_transformed_data', {})

        if not selected_variables or not target:
            return jsonify({"error": "Missing selected_variables or target"}), 400

        # Load CSV into df
        try:
            df = pd.read_csv(get_csv_path())
        except Exception as e:
            return jsonify({"error": f"Failed to load CSV: {str(e)}"}), 400

        if target not in df.columns:
            return jsonify({"error": f"Target variable '{target}' not found in dataset"}), 400

        # Prepare WOE-transformed data (same logic as logistic regression)
        modeling_data = {}
        woe_columns = []  # Track the actual column names we create
        
        for var in selected_variables:
            woe_data = woe_transformed_data.get(var)
            if isinstance(woe_data, dict) and isinstance(woe_data.get('stats'), list):
                bins_list = woe_data.get('stats')
            elif isinstance(woe_data, list):
                bins_list = woe_data
            else:
                print(f"RF DEBUG: No WOE data for {var}")
                continue

            if not bins_list:
                print(f"RF DEBUG: Empty bins list for {var}")
                continue

            # Create WOE column name
            woe_column_name = f'{var}_WOE'
            woe_columns.append(woe_column_name)
            modeling_data[woe_column_name] = np.zeros(len(df))
            
            assigned_count = 0
            for bin_info in bins_list:
                bin_range = bin_info.get('range') or bin_info.get('Range') or bin_info.get('Bin') or bin_info.get('bin')
                woe_value = bin_info.get('woe') or bin_info.get('WOE')
                if woe_value is None:
                    continue
                try:
                    woe_value = float(woe_value)
                except Exception:
                    continue
                
                # Apply WOE mapping
                mask = _create_woe_mask(df, var, bin_range)
                modeling_data[woe_column_name][mask] = woe_value
                assigned_count += mask.sum()

            print(f"RF DEBUG: Assigned WOE values for {var}: {assigned_count} rows")

        # Create DataFrame with WOE-transformed variables
        woe_df = pd.DataFrame(modeling_data)
        woe_df[target] = df[target].values

        # Remove rows with missing target
        mask = ~woe_df[target].isna()
        X = woe_df[woe_columns].fillna(0)  # Use the actual WOE column names
        y = woe_df[target][mask]
        X = X[mask]

        if len(X) == 0:
            return jsonify({"error": "No valid data after preprocessing"}), 400

        if len(woe_columns) == 0:
            return jsonify({"error": "No valid WOE-transformed features created"}), 400

        print(f"RF DEBUG: Final features: {woe_columns}")
        print(f"RF DEBUG: X shape: {X.shape}, y shape: {y.shape}")

        # Train Random Forest
        rf_model = RandomForestClassifier(
            n_estimators=100,
            max_depth=10,
            min_samples_split=5,
            min_samples_leaf=2,
            random_state=42,
            n_jobs=-1
        )
        
        rf_model.fit(X, y)
        y_pred_proba = rf_model.predict_proba(X)[:, 1]
        y_pred = rf_model.predict(X)

        # Calculate metrics
        fpr, tpr, thresholds = roc_curve(y, y_pred_proba)
        roc_auc = auc(fpr, tpr)
        gini_coefficient = 2 * roc_auc - 1

        # Feature importance
        feature_importance = []
        for i, col in enumerate(woe_columns):
            # Extract original variable name (remove _WOE suffix)
            original_var = col.replace('_WOE', '')
            feature_importance.append({
                'variable': original_var,
                'importance': float(rf_model.feature_importances_[i]),
                'importance_percentage': float(rf_model.feature_importances_[i] * 100)
            })

        # Sort by importance
        feature_importance.sort(key=lambda x: x['importance'], reverse=True)

        # Confusion matrix and classification metrics
        cm = confusion_matrix(y, y_pred)
        accuracy = accuracy_score(y, y_pred)
        precision = precision_score(y, y_pred, zero_division=0)
        recall = recall_score(y, y_pred, zero_division=0)
        f1 = f1_score(y, y_pred, zero_division=0)

        # KS Statistic
        try:
            diffs = np.abs(tpr - fpr)
            ks_idx = int(np.argmax(diffs)) if len(diffs) > 0 else 0
            ks_stat = float(diffs[ks_idx]) if len(diffs) > 0 else 0.0
            ks_threshold = float(thresholds[ks_idx]) if len(thresholds) > 0 else 0.0
            ks_curve = []
            for f, t, th in zip(fpr, tpr, thresholds):
                ks_curve.append({
                    'threshold': float(th) if np.isfinite(th) else None,
                    'tpr': float(t) if np.isfinite(t) else None,
                    'fpr': float(f) if np.isfinite(f) else None,
                    'diff': float(abs(t - f)) if np.isfinite(t) and np.isfinite(f) else None
                })
        except Exception as ks_err:
            print(f"RF DEBUG: KS calculation error: {ks_err}")
            ks_stat = None
            ks_threshold = None
            ks_curve = []

        # ROC data
        roc_data = []
        for f, t, th in zip(fpr, tpr, thresholds):
            roc_data.append({
                'fpr': float(f) if np.isfinite(f) else None,
                'tpr': float(t) if np.isfinite(t) else None,
                'threshold': float(th) if np.isfinite(th) else None
            })

        # Model stats
        model_stats = {
            'n_estimators': rf_model.n_estimators,
            'max_depth': rf_model.max_depth,
            'n_observations': len(X),
            'n_features': len(woe_columns),
            'oob_score': float(getattr(rf_model, 'oob_score_', 0)) if hasattr(rf_model, 'oob_score_') else None
        }

        resp = {
            'success': True,
            'feature_importance': feature_importance,
            'gini_coefficient': float(gini_coefficient) if np.isfinite(gini_coefficient) else None,
            'auc': float(roc_auc) if np.isfinite(roc_auc) else None,
            'roc_data': roc_data,
            'model_stats': model_stats,
            'confusion_matrix': cm.tolist(),
            'accuracy': float(accuracy) if np.isfinite(accuracy) else None,
            'precision': float(precision) if np.isfinite(precision) else None,
            'recall': float(recall) if np.isfinite(recall) else None,
            'f1': float(f1) if np.isfinite(f1) else None,
            'ks_stat': ks_stat,
            'ks_threshold': ks_threshold,
            'ks_curve': ks_curve
        }

        # Sanitize for JSON
        resp = sanitize_for_json(resp)
        return jsonify(resp)

    except Exception as e:
        print(f"RANDOM FOREST ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Failed to perform Random Forest analysis: {str(e)}"}), 500

# ----------- XGBoost Analysis -----------
@app.route('/api/xgboost', methods=['POST'])
def xgboost_analysis():
    """
    Perform XGBoost analysis on selected variables.
    Expects payload: { selected_variables: [list], target: string, woe_transformed_data: {} }
    Returns: model metrics, feature importance, ROC data, etc.
    """
    try:
        import xgboost as xgb
    except ImportError:
        return jsonify({"error": "XGBoost not installed. Please install with: pip install xgboost"}), 500

    from sklearn.metrics import roc_curve, auc, classification_report, confusion_matrix, accuracy_score, precision_score, recall_score, f1_score

    def sanitize_for_json(obj):
        """Recursively replace NaN/inf with None for valid JSON."""
        import numpy as np
        if isinstance(obj, dict):
            return {sanitize_for_json(k): sanitize_for_json(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [sanitize_for_json(item) for item in obj]
        elif isinstance(obj, (np.integer, np.floating)):
            if np.isnan(obj) or np.isinf(obj):
                return None
            return float(obj)
        elif isinstance(obj, (int, float)):
            if math.isnan(obj) or math.isinf(obj):
                return None
            return obj
        else:
            return obj

    try:
        data = request.get_json()
        selected_variables = data.get('selected_variables', [])
        target = data.get('target')
        woe_transformed_data = data.get('woe_transformed_data', {})

        if not selected_variables or not target:
            return jsonify({"error": "Missing selected_variables or target"}), 400

        # Load CSV into df
        try:
            df = pd.read_csv(get_csv_path())
        except Exception as e:
            return jsonify({"error": f"Failed to load CSV: {str(e)}"}), 400

        if target not in df.columns:
            return jsonify({"error": f"Target variable '{target}' not found in dataset"}), 400

        # Prepare WOE-transformed data (same logic as logistic regression)
        modeling_data = {}
        woe_columns = []  # Track the actual column names we create
        
        for var in selected_variables:
            woe_data = woe_transformed_data.get(var)
            if isinstance(woe_data, dict) and isinstance(woe_data.get('stats'), list):
                bins_list = woe_data.get('stats')
            elif isinstance(woe_data, list):
                bins_list = woe_data
            else:
                print(f"XGB DEBUG: No WOE data for {var}")
                continue

            if not bins_list:
                print(f"XGB DEBUG: Empty bins list for {var}")
                continue

            # Create WOE column name
            woe_column_name = f'{var}_WOE'
            woe_columns.append(woe_column_name)
            modeling_data[woe_column_name] = np.zeros(len(df))
            
            assigned_count = 0
            for bin_info in bins_list:
                bin_range = bin_info.get('range') or bin_info.get('Range') or bin_info.get('Bin') or bin_info.get('bin')
                woe_value = bin_info.get('woe') or bin_info.get('WOE')
                if woe_value is None:
                    continue
                try:
                    woe_value = float(woe_value)
                except Exception:
                    continue
                
                # Apply WOE mapping
                mask = _create_woe_mask(df, var, bin_range)
                modeling_data[woe_column_name][mask] = woe_value
                assigned_count += mask.sum()

            print(f"XGB DEBUG: Assigned WOE values for {var}: {assigned_count} rows")

        # Create DataFrame with WOE-transformed variables
        woe_df = pd.DataFrame(modeling_data)
        woe_df[target] = df[target].values

        # Remove rows with missing target
        mask = ~woe_df[target].isna()
        X = woe_df[woe_columns].fillna(0)  # Use the actual WOE column names
        y = woe_df[target][mask]
        X = X[mask]

        if len(X) == 0:
            return jsonify({"error": "No valid data after preprocessing"}), 400

        if len(woe_columns) == 0:
            return jsonify({"error": "No valid WOE-transformed features created"}), 400

        print(f"XGB DEBUG: Final features: {woe_columns}")
        print(f"XGB DEBUG: X shape: {X.shape}, y shape: {y.shape}")

        # Train XGBoost
        xgb_model = xgb.XGBClassifier(
            n_estimators=100,
            max_depth=6,
            learning_rate=0.1,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
            eval_metric='logloss',
            scale_pos_weight=10,
            use_label_encoder=False
        )
        
        xgb_model.fit(X, y)
        y_pred_proba = xgb_model.predict_proba(X)[:, 1]
        y_pred = xgb_model.predict(X)

        # Calculate metrics
        fpr, tpr, thresholds = roc_curve(y, y_pred_proba)
        roc_auc = auc(fpr, tpr)
        gini_coefficient = 2 * roc_auc - 1

        # Feature importance
        feature_importance = []
        for i, col in enumerate(woe_columns):
            # Extract original variable name (remove _WOE suffix)
            original_var = col.replace('_WOE', '')
            feature_importance.append({
                'variable': original_var,
                'importance': float(xgb_model.feature_importances_[i]),
                'importance_percentage': float(xgb_model.feature_importances_[i] * 100)
            })

        # Sort by importance
        feature_importance.sort(key=lambda x: x['importance'], reverse=True)

        # Confusion matrix and classification metrics
        cm = confusion_matrix(y, y_pred)
        accuracy = accuracy_score(y, y_pred)
        precision = precision_score(y, y_pred, zero_division=0)
        recall = recall_score(y, y_pred, zero_division=0)
        f1 = f1_score(y, y_pred, zero_division=0)

        # KS Statistic
        try:
            diffs = np.abs(tpr - fpr)
            ks_idx = int(np.argmax(diffs)) if len(diffs) > 0 else 0
            ks_stat = float(diffs[ks_idx]) if len(diffs) > 0 else 0.0
            ks_threshold = float(thresholds[ks_idx]) if len(thresholds) > 0 else 0.0
            ks_curve = []
            for f, t, th in zip(fpr, tpr, thresholds):
                ks_curve.append({
                    'threshold': float(th) if np.isfinite(th) else None,
                    'tpr': float(t) if np.isfinite(t) else None,
                    'fpr': float(f) if np.isfinite(f) else None,
                    'diff': float(abs(t - f)) if np.isfinite(t) and np.isfinite(f) else None
                })
        except Exception as ks_err:
            print(f"XGB DEBUG: KS calculation error: {ks_err}")
            ks_stat = None
            ks_threshold = None
            ks_curve = []

        # ROC data
        roc_data = []
        for f, t, th in zip(fpr, tpr, thresholds):
            roc_data.append({
                'fpr': float(f) if np.isfinite(f) else None,
                'tpr': float(t) if np.isfinite(t) else None,
                'threshold': float(th) if np.isfinite(th) else None
            })

        # Model stats
        model_stats = {
            'n_estimators': xgb_model.n_estimators,
            'max_depth': xgb_model.max_depth,
            'learning_rate': float(xgb_model.learning_rate),
            'n_observations': len(X),
            'n_features': len(woe_columns)
        }

        resp = {
            'success': True,
            'feature_importance': feature_importance,
            'gini_coefficient': float(gini_coefficient) if np.isfinite(gini_coefficient) else None,
            'auc': float(roc_auc) if np.isfinite(roc_auc) else None,
            'roc_data': roc_data,
            'model_stats': model_stats,
            'confusion_matrix': cm.tolist(),
            'accuracy': float(accuracy) if np.isfinite(accuracy) else None,
            'precision': float(precision) if np.isfinite(precision) else None,
            'recall': float(recall) if np.isfinite(recall) else None,
            'f1': float(f1) if np.isfinite(f1) else None,
            'ks_stat': ks_stat,
            'ks_threshold': ks_threshold,
            'ks_curve': ks_curve
        }

        # Sanitize for JSON
        resp = sanitize_for_json(resp)
        return jsonify(resp)

    except Exception as e:
        print(f"XGBOOST ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Failed to perform XGBoost analysis: {str(e)}"}), 500
        
# Helper function for WOE mapping (used by all models)
def _create_woe_mask(df, var, bin_range):
    """Create mask for WOE value assignment based on bin range."""
    import re
    import numpy as np
    
    if bin_range is None:
        return np.zeros(len(df), dtype=bool)
    
    # Handle Missing/NaN
    if isinstance(bin_range, str) and ('Missing' in bin_range or 'NaN' in bin_range):
        return df[var].isna()
    
    # Numeric range parsing
    if isinstance(bin_range, str) and any(ch in bin_range for ch in '(),[]'):
        range_str = bin_range.replace('(', '').replace(')', '').replace('[', '').replace(']', '')
        parts = [p.strip() for p in range_str.split(',') if p.strip()]
        if len(parts) == 2:
            try:
                lower = float(parts[0]) if parts[0].lower() not in ['-inf', 'inf'] else (float('-inf') if parts[0].lower() == '-inf' else float('inf'))
                upper = float(parts[1]) if parts[1].lower() not in ['-inf', 'inf'] else (float('-inf') if parts[1].lower() == '-inf' else float('inf'))
                if lower == float('-inf'):
                    return df[var] <= upper
                elif upper == float('inf'):
                    return df[var] > lower
                else:
                    return (df[var] > lower) & (df[var] <= upper)
            except (ValueError, TypeError):
                pass
    
    # Hyphen-separated ranges
    hyphen_match = re.match(r'^\s*-?\d+(?:\.\d+)?\s*-\s*-?\d+(?:\.\d+)?\s*$', str(bin_range))
    if isinstance(bin_range, str) and hyphen_match:
        try:
            parts = [p.strip() for p in bin_range.split('-')]
            lower, upper = float(parts[0]), float(parts[1])
            return (df[var].astype(float) >= lower) & (df[var].astype(float) <= upper)
        except (ValueError, TypeError):
            pass
    
    # Categorical values
    if isinstance(bin_range, str):
        cat_vals = [v.strip() for v in bin_range.split(',') if v.strip()]
        mask = np.zeros(len(df), dtype=bool)
        for cat_val in cat_vals:
            try:
                mask |= (df[var].astype(str) == str(cat_val))
            except Exception:
                continue
        return mask
    
    # Default: exact match
    return df[var].astype(str) == str(bin_range)

# ----------- Delete Record -----------
@app.route('/api/record/<int:record_id>', methods=['DELETE'])
def delete_record(record_id):
    """
    Delete a specific analysis record by ID, and remove any related finebin_details rows.
    """
    try:
        success = delete_record_db(record_id)
        return jsonify({"success": success})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ----------- Finebin Details API -----------
@app.route('/api/finebin-details', methods=['POST'])
def save_finebin_details():
    """
    Upsert fine binning details for a specific record and column.
    Expects payload: { record_id, column_name, bin_merges: { <group_id>: [bins], ... } }
    """
    data = request.get_json()
    record_id = data.get('record_id')
    column_name = data.get('column_name')
    bin_merges = data.get('bin_merges') # dict of group_id -> list of bins
    if not record_id or not column_name or not isinstance(bin_merges, dict):
        return jsonify({"error": "Missing or invalid fields (record_id, column_name, bin_merges)."}), 400
    try:
        success = save_finebin_details_db(record_id, column_name, bin_merges)
        return jsonify({"success": success})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/finebin-details/<int:record_id>/<string:column_name>', methods=['GET'])
def get_finebin_details(record_id, column_name):
    """
    Retrieve fine binning details for a specific record and column.
    """
    try:
        finebin_details = get_finebin_details_db(record_id, column_name)
        return jsonify(finebin_details)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ----------- Debug Binning -----------
@app.route('/api/debug-binning/<string:variable>', methods=['GET'])
def debug_binning(variable):
    """
    Debug endpoint to see what's happening with binning for a specific variable.
    """
    try:
        df = pd.read_csv(get_csv_path())
        
        if variable not in df.columns:
            return jsonify({"error": f"Variable {variable} not found"}), 400
            
        var_series = df[variable]
        result = {
            "variable": variable,
            "dtype": str(var_series.dtype),
            "nunique": var_series.nunique(dropna=True),
            "sample_values": var_series.dropna().head(10).tolist(),
            "is_numeric": pd.api.types.is_numeric_dtype(var_series)
        }
        
        # Check what our logic would classify it as
        is_likely_id = any(keyword in variable.lower() for keyword in ['id', 'key', 'code', 'no', 'num'])
        unique_count = var_series.nunique(dropna=True)
        
        if pd.api.types.is_numeric_dtype(var_series):
            if is_likely_id or unique_count <= 50:
                result["predicted_type"] = "discrete"
            else:
                result["predicted_type"] = "continuous"
        else:
            result["predicted_type"] = "discrete"
            
        result["is_likely_id"] = is_likely_id
        
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/generate-scorecard', methods=['POST'])
def generate_scorecard():
    """
    Generates a score card using pre-computed model results.
    """
    try:
        # Parse request data
        data = request.get_json()
        selected_variables = data.get('selected_variables', [])
        target = data.get('target')
        woe_transformed_data = data.get('woe_transformed_data', {})
        model_results = data.get('model_results', {})  # Accept pre-computed model results
        model_type = data.get('model_type', 'logistic')  # Accept model type

        # Input validation
        if not selected_variables or not target or not woe_transformed_data:
            return jsonify({"error": "Missing required data: selected_variables, target, or woe_transformed_data"}), 400
        if not all(isinstance(var, str) for var in selected_variables):
            return jsonify({"error": "All selected_variables must be strings"}), 400
        if not isinstance(woe_transformed_data, dict):
            return jsonify({"error": "woe_transformed_data must be a dictionary"}), 400

        # Load dataset
        df = pd.read_csv(get_csv_path())

        # Validate columns
        if target not in df.columns:
            return jsonify({"error": f"Target column '{target}' not found in dataset"}), 400
        missing_vars = [var for var in selected_variables if var not in df.columns]
        if missing_vars:
            return jsonify({"error": f"Variables not found in dataset: {missing_vars}"}), 400
        missing_woe = [var for var in selected_variables if var not in woe_transformed_data]
        if missing_woe:
            return jsonify({"error": f"Missing WOE data for variables: {missing_woe}"}), 400

        # Validate target is binary
        df[target] = pd.to_numeric(df[target], errors='coerce').fillna(0).astype(int)
        if set(df[target].unique()) - {0, 1}:
            return jsonify({"error": "Target variable must be binary (0/1)"}), 400

        # Extract coefficients from pre-computed model results
        coefficients = {}
        intercept = 0
        
        if model_results and model_type == 'logistic':
            # Extract from logistic regression results
            if 'coefficients' in model_results:
                for coef_info in model_results['coefficients']:
                    var_name = coef_info.get('variable')
                    if var_name and var_name != 'Intercept':
                        coefficients[var_name] = coef_info.get('coefficient', 0)
                    elif var_name == 'Intercept':
                        intercept = coef_info.get('coefficient', 0)
            else:
                return jsonify({"error": "No coefficients found in logistic regression results"}), 400
        
        elif model_results and model_type in ['random_forest', 'xgboost']:
            # For tree-based models, use feature importance with proper scaling
            if 'feature_importance' in model_results:
                # Normalize feature importances to sum to 1
                total_importance = sum(feature_info.get('importance', 0) for feature_info in model_results['feature_importance'])
                if total_importance > 0:
                    for feature_info in model_results['feature_importance']:
                        var_name = feature_info.get('variable')
                        importance = feature_info.get('importance', 0)
                        # Convert importance to coefficient-like values with proper scaling
                        # Use a scaling factor that makes sense for score ranges
                        coefficients[var_name] = (importance / total_importance) * 50  # Scale to reasonable range
                else:
                    return jsonify({"error": f"Total feature importance is zero for {model_type}"}), 400
            else:
                return jsonify({"error": f"No feature importance found in {model_type} results"}), 400
            # For tree models, we use a base intercept
            intercept = 0
        else:
            return jsonify({"error": f"Unsupported model type: {model_type} or missing model results"}), 400

        # Prepare WOE-transformed data for scorecard generation
        modeling_data = {}
        for var in selected_variables:
            woe_data = woe_transformed_data[var]
            ranges_list = None

            # Support both 'woe_ranges' and 'stats' structures
            if isinstance(woe_data, dict) and 'woe_ranges' in woe_data and isinstance(woe_data['woe_ranges'], list):
                ranges_list = woe_data['woe_ranges']
            elif isinstance(woe_data, dict) and 'stats' in woe_data and isinstance(woe_data['stats'], list):
                ranges_list = [{
                    'range': r.get('Range') or r.get('Bin') or str(r),
                    'woe': float(r.get('WOE') or 0)
                } for r in woe_data['stats']]
            else:
                continue

            if not ranges_list:
                continue

            # Build WOE mapping
            woe_mapping = {}
            for range_info in ranges_list:
                try:
                    bin_range = range_info.get('range') if isinstance(range_info, dict) else str(range_info)
                    woe_value = float(range_info.get('woe') if isinstance(range_info, dict) else 0)
                    if bin_range is None:
                        continue

                    # Handle Missing/NaN
                    if isinstance(bin_range, str) and ('Missing' in bin_range or 'NaN' in bin_range):
                        mask = df[var].isna()
                        for idx in df[mask].index:
                            woe_mapping[idx] = woe_value
                        continue

                    # Numeric range parsing (e.g., "(a, b]", "[a, b]")
                    if isinstance(bin_range, str) and any(ch in bin_range for ch in '(),[]'):
                        range_str = bin_range.replace('(', '').replace(')', '').replace('[', '').replace(']', '')
                        parts = [p.strip() for p in range_str.split(',') if p.strip()]
                        if len(parts) == 2:
                            try:
                                lower = float(parts[0]) if parts[0].lower() not in ['-inf', 'inf'] else (float('-inf') if parts[0].lower() == '-inf' else float('inf'))
                                upper = float(parts[1]) if parts[1].lower() not in ['-inf', 'inf'] else (float('-inf') if parts[1].lower() == '-inf' else float('inf'))
                                if lower == float('-inf'):
                                    mask = df[var] <= upper
                                elif upper == float('inf'):
                                    mask = df[var] > lower
                                else:
                                    mask = (df[var] > lower) & (df[var] <= upper)
                                for idx in df[mask].index:
                                    woe_mapping[idx] = woe_value
                                continue
                            except (ValueError, TypeError):
                                pass

                    # Hyphen-separated ranges (e.g., "1 - 2")
                    hyphen_match = re.match(r'^\s*-?\d+(?:\.\d+)?\s*-\s*-?\d+(?:\.\d+)?\s*$', str(bin_range))
                    if isinstance(bin_range, str) and hyphen_match:
                        try:
                            parts = [p.strip() for p in bin_range.split('-')]
                            lower, upper = float(parts[0]), float(parts[1])
                            mask = (df[var].astype(float) >= lower) & (df[var].astype(float) <= upper)
                            for idx in df[mask].index:
                                woe_mapping[idx] = woe_value
                            continue
                        except (ValueError, TypeError):
                            pass

                    # Categorical values (comma-separated or single)
                    if isinstance(bin_range, str):
                        cat_vals = [v.strip() for v in bin_range.split(',') if v.strip()]
                        for cat_val in cat_vals:
                            try:
                                mask = df[var].astype(str) == str(cat_val)
                                for idx in df[mask].index:
                                    woe_mapping[idx] = woe_value
                            except Exception:
                                continue
                except Exception:
                    pass

            if woe_mapping:
                woe_column = [woe_mapping.get(i, 0) for i in range(len(df))]
                modeling_data[var] = woe_column
            else:
                modeling_data[var] = [0] * len(df)

        # Create DataFrame with WOE-transformed variables
        model_df = pd.DataFrame(modeling_data)
        model_df[target] = df[target]

        # Check for missing variables
        missing_vars = [v for v in selected_variables if v not in model_df.columns]
        if missing_vars:
            return jsonify({
                "error": f"Missing variables in WOE-transformed data: {missing_vars}",
                "debug": {
                    "selected_variables": selected_variables,
                    "available_columns": list(model_df.columns)
                }
            }), 400

        # Remove rows with missing target values
        model_df = model_df.dropna(subset=[target])
        if model_df.empty:
            return jsonify({"error": "No valid data after removing missing target values"}), 400

        # Score card parameters - adjust for different model types
        N = len(selected_variables)
        
        # Adjust parameters based on model type
        if model_type == 'logistic':
            factor = 20 / np.log(2)  # ≈ 28.8539 (standard logistic scoring)
            base_odds = 50
            base_score = 600
            offset = base_score - factor * np.log(base_odds)  # ≈ 427.432
        else:
            # For tree-based models, use different parameters since we don't have true coefficients
            factor = 15 / np.log(2)  # Smaller factor for tree models
            base_odds = 50
            base_score = 600
            offset = base_score - factor * np.log(base_odds)

        # Generate score card and calculate score ranges
        scorecard_bins = []
        var_score_ranges = {var: [] for var in selected_variables}
        processed_ranges = set()

        for var in selected_variables:
            if var not in coefficients:
                continue
            beta = coefficients[var]
            ranges_source = None
            if var in woe_transformed_data and isinstance(woe_transformed_data[var], dict):
                if 'woe_ranges' in woe_transformed_data[var]:
                    ranges_source = woe_transformed_data[var]['woe_ranges']
                elif 'stats' in woe_transformed_data[var]:
                    ranges_source = [{
                        'range': r.get('Range') or r.get('Bin') or str(r),
                        'woe': float(r.get('WOE') or 0)
                    } for r in woe_transformed_data[var]['stats']]

            if not ranges_source:
                continue

            for i, range_info in enumerate(ranges_source):
                try:
                    bin_range = range_info.get('range') if isinstance(range_info, dict) else str(range_info)
                    woe_value = float(range_info.get('woe') if isinstance(range_info, dict) else 0)
                    range_key = f"{var}_{bin_range}_{woe_value}"
                    if range_key in processed_ranges:
                        continue
                    processed_ranges.add(range_key)

                    # Use NEGATIVE coefficients for proper credit scoring direction
                    # Higher risk = lower score, Lower risk = higher score
                    score = (-beta * woe_value + intercept / N) * factor + offset / N
                    bin_data = {
                        'variable': var,
                        'bin_range': bin_range,
                        'woe': woe_value,
                        'coefficient': beta,
                        'score': round(float(score), 2)
                    }
                    if model_type == 'logistic':
                        bin_data['coefficient'] = round(float(beta), 4)
                    else:  # random_forest or xgboost
                        bin_data['feature_importance'] = round(float(beta), 4)
                    scorecard_bins.append(bin_data)
                    var_score_ranges[var].append(score)
                except (ValueError, TypeError):
                    pass

        # Calculate score range per variable
        min_total_score = 0
        max_total_score = 0
        for var in selected_variables:
            scores = var_score_ranges.get(var, [])
            if scores:
                min_total_score += min(scores)
                max_total_score += max(scores)

        min_total_score = round(float(min_total_score), 2) if min_total_score else 0
        max_total_score = round(float(max_total_score), 2) if max_total_score else 0

        # For tree models, adjust the score range if it's unreasonable
        if model_type in ['random_forest', 'xgboost']:
            # Tree models might produce very different score ranges
            # Ensure reasonable credit score range (typically 300-850)
            if max_total_score > 1000 or min_total_score < 0:
                # Rescale to reasonable range
                current_range = max_total_score - min_total_score
                if current_range > 0:
                    scale_factor = 550 / current_range  # Target range of 550 points
                    # Rescale all scores
                    for bin_info in scorecard_bins:
                        bin_info['score'] = round(300 + (bin_info['score'] - min_total_score) * scale_factor, 2)
                    # Recalculate total range
                    min_total_score = 300
                    max_total_score = 850

        return jsonify({
            "success": True,
            "scorecard_bins": scorecard_bins,
            "score_parameters": {
                "factor": round(float(factor), 4),
                "offset": round(float(offset), 4),
                "base_score": base_score,
                "base_odds": base_odds,
                "intercept": round(float(intercept), 4),
                "n_variables": N,
                "min_score": min_total_score,
                "max_score": max_total_score,
                "model_type": model_type
            },
            "model_summary": {
                "coefficients": {k: round(float(v), 4) for k, v in coefficients.items()},
                "intercept": round(float(intercept), 4),
                "n_observations": len(model_df),
                "n_variables": N,
                "model_type": model_type
            }
        })

    except Exception as e:
        import traceback
        print(f"ERROR in generate_scorecard: {traceback.format_exc()}")
        return jsonify({"error": f"Failed to generate score card ({type(e).__name__}): {str(e)}"}), 500
    
# ----------- Apply Score Card to All Records -----------
@app.route('/api/apply-scorecard', methods=['POST'])
def apply_scorecard():
    """
    Applies the score card to all records in the uploaded dataset using pre-computed model results.
    """
    import numpy as np
    try:
        data = request.get_json()
        selected_variables = data.get('selected_variables', [])
        target = data.get('target')
        woe_transformed_data = data.get('woe_transformed_data', {})
        model_results = data.get('model_results', {})  # Accept pre-computed model results
        model_type = data.get('model_type', 'logistic')  # Accept model type

        # Input validation
        if not selected_variables or not target or not woe_transformed_data:
            return jsonify({"error": "Missing required data: selected_variables, target, or woe_transformed_data"}), 400

        df = pd.read_csv(get_csv_path())
        if target not in df.columns:
            return jsonify({"error": f"Target column '{target}' not found in dataset"}), 400

        # Sanitize non-finite values in selected variables
        for var in selected_variables:
            if var in df.columns:
                df[var] = df[var].replace([np.inf, -np.inf], np.nan)
                if df[var].isnull().any():
                    if df[var].dtype.kind in 'biufc':
                        df[var] = df[var].fillna(df[var].median())
                    else:
                        df[var] = df[var].fillna('Missing')

        # Prepare WOE-transformed data for each variable
        modeling_data = {}
        for var in selected_variables:
            woe_data = woe_transformed_data[var]
            ranges_list = None
            
            # Get the correct WOE data structure
            if isinstance(woe_data, dict) and 'woe_ranges' in woe_data and isinstance(woe_data['woe_ranges'], list):
                ranges_list = woe_data['woe_ranges']
            elif isinstance(woe_data, dict) and 'stats' in woe_data and isinstance(woe_data['stats'], list):
                ranges_list = [{
                    'range': r.get('Range') or r.get('Bin') or str(r),
                    'woe': float(r.get('WOE') or 0)
                } for r in woe_data['stats']]
            else:
                print(f"DEBUG: No valid WOE data structure found for {var}")
                continue
            if not ranges_list:
                print(f"DEBUG: Empty ranges list for {var}")
                continue
                
            woe_mapping = {}
            assigned_count = 0
            
            for range_info in ranges_list:
                try:
                    bin_range = range_info.get('range') if isinstance(range_info, dict) else str(range_info)
                    woe_value = float(range_info.get('woe') if isinstance(range_info, dict) else 0)
                    if bin_range is None:
                        continue

                    # Handle Missing/NaN
                    if isinstance(bin_range, str) and ('Missing' in bin_range or 'NaN' in bin_range):
                        mask = df[var].isna() | (df[var] == 'Missing')
                        for idx in df[mask].index:
                            woe_mapping[idx] = woe_value
                        assigned_count += mask.sum()
                        continue

                    # Numeric range parsing (e.g., "(a, b]", "[a, b]")
                    if isinstance(bin_range, str) and any(ch in bin_range for ch in '(),[]'):
                        range_str = bin_range.replace('(', '').replace(')', '').replace('[', '').replace(']', '')
                        parts = [p.strip() for p in range_str.split(',') if p.strip()]
                        if len(parts) == 2:
                            try:
                                lower = float(parts[0]) if parts[0].lower() not in ['-inf', 'inf'] else (float('-inf') if parts[0].lower() == '-inf' else float('inf'))
                                upper = float(parts[1]) if parts[1].lower() not in ['-inf', 'inf'] else (float('-inf') if parts[1].lower() == '-inf' else float('inf'))
                                if lower == float('-inf'):
                                    mask = df[var] <= upper
                                elif upper == float('inf'):
                                    mask = df[var] > lower
                                else:
                                    mask = (df[var] > lower) & (df[var] <= upper)
                                for idx in df[mask].index:
                                    woe_mapping[idx] = woe_value
                                assigned_count += mask.sum()
                                continue
                            except (ValueError, TypeError):
                                pass

                    # Hyphen-separated ranges (e.g., "1 - 2")
                    hyphen_match = re.match(r'^\s*-?\d+(?:\.\d+)?\s*-\s*-?\d+(?:\.\d+)?\s*$', str(bin_range))
                    if isinstance(bin_range, str) and hyphen_match:
                        try:
                            parts = [p.strip() for p in bin_range.split('-')]
                            lower, upper = float(parts[0]), float(parts[1])
                            mask = (df[var].astype(float) >= lower) & (df[var].astype(float) <= upper)
                            for idx in df[mask].index:
                                woe_mapping[idx] = woe_value
                            assigned_count += mask.sum()
                            continue
                        except (ValueError, TypeError):
                            pass

                    # Categorical values (comma-separated or single)
                    if isinstance(bin_range, str):
                        cat_vals = [v.strip() for v in bin_range.split(',') if v.strip()]
                        for cat_val in cat_vals:
                            try:
                                mask = df[var].astype(str) == str(cat_val)
                                for idx in df[mask].index:
                                    woe_mapping[idx] = woe_value
                                assigned_count += mask.sum()
                            except Exception:
                                continue
                except Exception as e:
                    print(f"DEBUG: Error processing range {bin_range} for {var}: {e}")
                    continue

            print(f"DEBUG: Assigned WOE values for {var}: {assigned_count} rows")
            
            if woe_mapping:
                woe_column = [woe_mapping.get(i, 0) for i in range(len(df))]
                modeling_data[var] = woe_column
            else:
                modeling_data[var] = [0] * len(df)

        # Create DataFrame with WOE-transformed variables
        model_df = pd.DataFrame(modeling_data)
        model_df[target] = pd.to_numeric(df[target], errors='coerce').fillna(0).astype(int)

        # Remove rows with missing target
        mask = ~model_df[target].isna()
        X = model_df[selected_variables]
        y = model_df[target][mask]
        X = X[mask]

        if len(X) == 0:
            return jsonify({"error": "No valid data after preprocessing"}), 400

        # Calculate scores based on model type
        scores = []
        
        if model_type == 'logistic' and model_results:
            # Use logistic regression coefficients
            coefficients = {}
            intercept = 0
            
            if 'coefficients' in model_results:
                for coef_info in model_results['coefficients']:
                    var_name = coef_info.get('variable')
                    if var_name and var_name != 'Intercept':
                        coefficients[var_name] = coef_info.get('coefficient', 0)
                    elif var_name == 'Intercept':
                        intercept = coef_info.get('coefficient', 0)
            
            # Score card parameters for logistic regression
            N = len(selected_variables)
            factor = 20 / np.log(2)  # ≈ 28.8539
            base_odds = 50
            base_score = 600
            offset = base_score - factor * np.log(base_odds)  # ≈ 427.432

            # FIXED: Use NEGATIVE coefficients so higher risk = lower score
            for idx in range(len(X)):
                score = 0
                for var in selected_variables:
                    beta = coefficients.get(var, 0)
                    woe = X.iloc[idx][var] if var in X.columns else 0
                    # FIX: Use NEGATIVE beta to ensure higher risk = lower score
                    score += (-beta * woe + intercept / N) * factor + offset / N
                scores.append(round(float(score), 2))
                
        elif model_type in ['random_forest', 'xgboost'] and model_results:
            # For tree-based models, use the actual model predictions
            try:
                if model_type == 'random_forest':
                    from sklearn.ensemble import RandomForestClassifier
                    # Recreate the Random Forest model with the same parameters
                    rf_model = RandomForestClassifier(
                        n_estimators=model_results.get('model_stats', {}).get('n_estimators', 100),
                        max_depth=model_results.get('model_stats', {}).get('max_depth', 10),
                        random_state=42,
                        n_jobs=-1
                    )
                    rf_model.fit(X, y)
                    # Get probability of being BAD (class 1)
                    y_pred_proba_bad = rf_model.predict_proba(X)[:, 1]
                    
                elif model_type == 'xgboost':
                    import xgboost as xgb
                    # Recreate the XGBoost model with the same parameters
                    xgb_model = xgb.XGBClassifier(
                        n_estimators=model_results.get('model_stats', {}).get('n_estimators', 100),
                        max_depth=model_results.get('model_stats', {}).get('max_depth', 6),
                        learning_rate=model_results.get('model_stats', {}).get('learning_rate', 0.1),
                        random_state=42
                    )
                    xgb_model.fit(X, y)
                    # Get probability of being BAD (class 1)
                    y_pred_proba_bad = xgb_model.predict_proba(X)[:, 1]
                
                # FIXED: Convert BAD probabilities to scores where higher risk = lower score
                min_score = 300
                max_score = 850
                
                # FIX: Higher bad probability = Lower score
                # Use inverse relationship: score = max_score - (bad_probability * score_range)
                score_range = max_score - min_score
                scores = max_score - (y_pred_proba_bad * score_range)
                
                scores = [round(float(score), 2) for score in scores]
                
                print(f"DEBUG: Tree model scoring - Bad probabilities range: {np.min(y_pred_proba_bad):.4f} to {np.max(y_pred_proba_bad):.4f}")
                print(f"DEBUG: Tree model scoring - Scores range: {np.min(scores):.2f} to {np.max(scores):.2f}")
                
            except Exception as model_err:
                print(f"DEBUG: Tree model scoring failed: {model_err}")
                # Fallback: use feature importance-based scoring with proper direction
                if 'feature_importance' in model_results:
                    coefficients = {}
                    for feature_info in model_results['feature_importance']:
                        var_name = feature_info.get('variable')
                        importance = feature_info.get('importance', 0)
                        coefficients[var_name] = importance * 100  # Scale factor
                    
                    # FIXED: Simple additive scoring with proper direction
                    for idx in range(len(X)):
                        score = 600  # Base score
                        for var in selected_variables:
                            beta = coefficients.get(var, 0)
                            woe = X.iloc[idx][var] if var in X.columns else 0
                            # FIX: Use negative relationship for risk factors
                            score -= beta * woe
                        scores.append(round(float(score), 2))
                else:
                    return jsonify({"error": f"Failed to calculate scores for {model_type}: {str(model_err)}"}), 500
        else:
            return jsonify({"error": f"Unsupported model type or missing model results: {model_type}"}), 400

        # Prepare results
        results_list = []
        y_true = y.tolist()
        y_score = scores
        
        for idx, score in enumerate(scores):
            results_list.append({
                "index": int(X.index[idx]) if hasattr(X, 'index') else idx,
                "score": score,
                "target": int(y_true[idx])
            })
        
        # Sort descending by score (HIGHEST scores first = LOWEST risk first)
        results_list = sorted(results_list, key=lambda x: x["score"], reverse=True)

        # Calculate KS statistic (separation number)
        try:
            from sklearn.metrics import roc_curve
            fpr, tpr, thresholds = roc_curve(y_true, y_score)
            diffs = np.abs(tpr - fpr)
            ks_stat = float(np.max(diffs)) if len(diffs) > 0 else 0.0
            
            # Get KS threshold
            ks_idx = np.argmax(diffs)
            ks_threshold = float(thresholds[ks_idx]) if len(thresholds) > ks_idx else 0.0
            
            print(f"DEBUG: KS Statistic calculated: {ks_stat}, Threshold: {ks_threshold}")
            
            # Debug: Check score distribution by target
            scores_0 = [score for score, target in zip(scores, y_true) if target == 0]
            scores_1 = [score for score, target in zip(scores, y_true) if target == 1]
            print(f"DEBUG: Score distribution - Good (0): {np.mean(scores_0):.2f} ± {np.std(scores_0):.2f}")
            print(f"DEBUG: Score distribution - Bad  (1): {np.mean(scores_1):.2f} ± {np.std(scores_1):.2f}")
            
        except Exception as ks_err:
            print(f"DEBUG: KS calculation error: {ks_err}")
            ks_stat = None
            ks_threshold = None

        # Calculate additional metrics
        try:
            from sklearn.metrics import auc, accuracy_score, precision_score, recall_score, f1_score
            
            # ROC AUC
            roc_auc = auc(fpr, tpr) if 'fpr' in locals() and 'tpr' in locals() else 0.0
            
            # For credit scoring, we typically use a different threshold than 0.5
            # Since scores are now properly scaled, we can use a score threshold
            score_threshold = np.percentile(scores, 50)  # Median score as threshold
            y_pred = [1 if score < score_threshold else 0 for score in scores]  # Lower score = higher risk = predicted bad
            
            accuracy = accuracy_score(y_true, y_pred)
            precision = precision_score(y_true, y_pred, zero_division=0)
            recall = recall_score(y_true, y_pred, zero_division=0)
            f1 = f1_score(y_true, y_pred, zero_division=0)
            
            print(f"DEBUG: Additional metrics - AUC: {roc_auc:.4f}, Accuracy: {accuracy:.4f}")
            print(f"DEBUG: Classification at score threshold {score_threshold:.2f}")
            
        except Exception as metric_err:
            print(f"DEBUG: Metric calculation error: {metric_err}")
            roc_auc = 0.0
            accuracy = 0.0
            precision = 0.0
            recall = 0.0
            f1 = 0.0

        return jsonify({
            "success": True, 
            "results": results_list, 
            "ks_stat": ks_stat,
            "ks_threshold": ks_threshold,
            "auc": roc_auc,
            "accuracy": accuracy,
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "model_type": model_type,
            "variables_used": selected_variables,
            "n_records": len(results_list),
            "score_range": {
                "min": float(np.min(scores)) if len(scores) > 0 else 0,
                "max": float(np.max(scores)) if len(scores) > 0 else 0,
                "mean": float(np.mean(scores)) if len(scores) > 0 else 0
            }
        })
        
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f"ERROR in apply_scorecard: {tb}")
        return jsonify({"error": f"Failed to apply score card ({type(e).__name__}): {str(e)}"}), 500
    
    
def classify_with_heuristics(column_name, samples):
    """
    Enhanced heuristic classification for discrete vs continuous variables.
    Uses column name patterns and sample data analysis.
    """
    col_name_lower = column_name.lower()
    
    # Check for discrete indicators in column name
    discrete_keywords = ['id', 'code', 'type', 'category', 'class', 'group', 'status', 
                       'flag', 'level', 'grade', 'rating', 'rank', 'gender', 'sex',
                       'marital', 'education', 'occupation', 'department', 'region',
                       'state', 'country', 'city', 'zip', 'postal', 'bool', 'binary']
    
    continuous_keywords = ['age', 'amount', 'price', 'cost', 'salary', 'income', 'revenue',
                         'balance', 'rate', 'ratio', 'percent', 'score', 'weight', 'height',
                         'length', 'width', 'depth', 'distance', 'time', 'duration', 'years',
                         'month', 'day', 'hour', 'minute', 'second', 'value']
    
    is_discrete_name = any(keyword in col_name_lower for keyword in discrete_keywords)
    is_continuous_name = any(keyword in col_name_lower for keyword in continuous_keywords)
    
    if is_discrete_name:
        return 'discrete'
    elif is_continuous_name:
        return 'continuous'
    else:
        # Analyze sample values if available
        try:
            if not samples or len(samples) == 0:
                return 'discrete'  # Default when no data
            
            # Remove None/null values
            clean_samples = [s for s in samples if s is not None and str(s).strip() != '']
            if not clean_samples:
                return 'discrete'
            
            # Check for non-numeric values (strings, booleans)
            non_numeric_count = 0
            for x in clean_samples:
                if isinstance(x, str) and not x.replace('.', '').replace('-', '').isdigit():
                    non_numeric_count += 1
                elif isinstance(x, bool):
                    non_numeric_count += 1
            
            if non_numeric_count > 0:
                return 'discrete'
            
            # Convert to numeric for analysis
            try:
                numeric_samples = [float(x) for x in clean_samples]
            except:
                return 'discrete'
            
            # For numeric data, check patterns
            unique_values = len(set(numeric_samples))
            total_values = len(numeric_samples)
            
            # Low cardinality suggests discrete
            if unique_values <= 10:
                return 'discrete'
            
            # High cardinality (many unique values) suggests continuous
            if unique_values > total_values * 0.8:
                return 'continuous'
            
            # Check if values are all integers
            all_integers = all(isinstance(x, int) or (isinstance(x, float) and x.is_integer()) for x in numeric_samples)
            
            if all_integers:
                # Integer sequences with large gaps might be IDs
                min_val, max_val = min(numeric_samples), max(numeric_samples)
                if max_val - min_val > unique_values * 3:
                    return 'discrete'  # Likely IDs or codes
                else:
                    return 'discrete' if unique_values <= 20 else 'continuous'
            else:
                # Float values generally suggest continuous
                return 'continuous'
                
        except Exception:
            return 'discrete'  # Safe default


if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=True, host='0.0.0.0', port=port)