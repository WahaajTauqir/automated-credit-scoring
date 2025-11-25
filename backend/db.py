"""
New Database Layer for Credit Scoring Application
Uses the restructured schema with records, features, binning_steps, bins, and merged_bins tables
"""

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
from psycopg2.pool import ThreadedConnectionPool
import os
import json
from typing import Optional, Dict, List, Tuple, Any


# PostgreSQL connection details
DATABASE_URL = os.getenv('DATABASE_URL')
PG_DBNAME = os.getenv('PG_DBNAME', 'mydb')
PG_USER = os.getenv('PG_USER', 'myuser')
PG_PASSWORD = os.getenv('PG_PASSWORD', 'mypassword')
PG_HOST = os.getenv('PG_HOST', 'localhost')
PG_PORT = os.getenv('PG_PORT', '5432')
PG_POOL_MIN = int(os.getenv('PG_POOL_MIN', '1'))
PG_POOL_MAX = int(os.getenv('PG_POOL_MAX', '10'))
PG_POOL_MAX = PG_POOL_MAX if PG_POOL_MAX >= PG_POOL_MIN else PG_POOL_MIN
POOL_DISABLED = os.getenv('PG_DISABLE_POOLING', '0') == '1'
_connection_pool: Optional[ThreadedConnectionPool] = None


class ManagedConnection:
    """Wraps a psycopg2 connection so .close() returns it to the pool when pooling is enabled."""

    def __init__(self, conn, pool=None):
        self._conn = conn
        self._pool = pool

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def close(self):
        if not self._conn:
            return
        if self._pool:
            self._pool.putconn(self._conn)
        else:
            self._conn.close()
        self._conn = None


def _connection_kwargs():
    if DATABASE_URL:
        return {'dsn': DATABASE_URL}
    return {
        'dbname': PG_DBNAME,
        'user': PG_USER,
        'password': PG_PASSWORD,
        'host': PG_HOST,
        'port': PG_PORT
    }


def _open_new_connection():
    kwargs = _connection_kwargs()
    if 'dsn' in kwargs:
        return psycopg2.connect(kwargs['dsn'])
    return psycopg2.connect(**kwargs)


def _get_connection_pool() -> Optional[ThreadedConnectionPool]:
    """Lazily create a shared connection pool unless pooling is disabled."""
    global _connection_pool
    if POOL_DISABLED:
        return None
    if _connection_pool is None:
        kwargs = _connection_kwargs()
        if 'dsn' in kwargs:
            _connection_pool = ThreadedConnectionPool(PG_POOL_MIN, PG_POOL_MAX, kwargs['dsn'])
        else:
            _connection_pool = ThreadedConnectionPool(PG_POOL_MIN, PG_POOL_MAX, **kwargs)
    return _connection_pool


def get_db_connection():
    """
    Return a psycopg2 connection. If DATABASE_URL is set, use it directly.
    Otherwise use individual PG_* environment variables.
    """
    pool = _get_connection_pool()
    if pool:
        conn = pool.getconn()
        return ManagedConnection(conn, pool)
    
    return ManagedConnection(_open_new_connection())


def init_db():
    """Initialize the database schema if needed."""
    # Note: Schema should be created using validate_and_migrate_schema.py
    pass

def ensure_final_selected_column():
    """Ensure the final_selected column exists in the features table."""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # Check if column exists
        cur.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='features' AND column_name='final_selected'
        """)
        if not cur.fetchone():
            # Column doesn't exist, add it
            cur.execute("ALTER TABLE features ADD COLUMN final_selected BOOLEAN DEFAULT FALSE")
            conn.commit()
            print("[DB] Added missing final_selected column to features table")
        else:
            print("[DB] final_selected column already exists")
    except Exception as e:
        conn.rollback()
        print(f"[DB] Error checking/adding final_selected column: {e}")
    finally:
        cur.close()
        conn.close()

def ensure_model_ready_column():
    """Ensure the model_ready column exists in the features table."""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # Check if column exists
        cur.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='features' AND column_name='model_ready'
        """)
        if not cur.fetchone():
            # Column doesn't exist, add it
            cur.execute("ALTER TABLE features ADD COLUMN model_ready BOOLEAN DEFAULT FALSE")
            conn.commit()
            print("[DB] Added missing model_ready column to features table")
        else:
            print("[DB] model_ready column already exists")
    except Exception as e:
        conn.rollback()
        print(f"[DB] Error checking/adding model_ready column: {e}")
    finally:
        cur.close()
        conn.close()

def ensure_dataset_identifier_column():
    """Ensure the identifier column exists in the records table."""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name='records' AND column_name='identifier'
        """)
        if not cur.fetchone():
            cur.execute("ALTER TABLE records ADD COLUMN identifier TEXT")
            conn.commit()
            print("[DB] Added missing identifier column to records table")
        else:
            print("[DB] identifier column already exists")
    except Exception as e:
        conn.rollback()
        print(f"[DB] Error ensuring identifier column: {e}")
    finally:
        cur.close()
        conn.close()

def sync_model_ready_to_final_selected(dataset_id: int) -> bool:
    """
    Copy model_ready values to final_selected for all features in a dataset.
    Called when user navigates from Column Selection & Binning to Model Training.
    """
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Check if columns exist
        cur.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='features' AND column_name IN ('model_ready', 'final_selected')
        """)
        existing_columns = {row[0] for row in cur.fetchall()}
        
        if 'model_ready' not in existing_columns:
            cur.execute("ALTER TABLE features ADD COLUMN model_ready BOOLEAN DEFAULT FALSE")
            conn.commit()
        
        if 'final_selected' not in existing_columns:
            cur.execute("ALTER TABLE features ADD COLUMN final_selected BOOLEAN DEFAULT FALSE")
            conn.commit()
        
        # Copy model_ready to final_selected
        cur.execute("""
            UPDATE features 
            SET final_selected = model_ready 
            WHERE dataset_id = %s
        """, (dataset_id,))
        
        conn.commit()
        print(f"[DB] Synced model_ready to final_selected for dataset {dataset_id}")
        return True
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"[DB] Error syncing model_ready to final_selected: {e}")
        return False
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


# =====================================================
# DATASET OPERATIONS
# =====================================================

def create_dataset(name: str, file_path: str, total_features: int,
                  discrete_features: int, continuous_features: int,
                  target_variable: str, identifier: Optional[str] = None) -> int:
    """
    Create a new dataset record.
    
    Returns:
        int: The ID of the created dataset
    """
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("""
        INSERT INTO records (name, file_path, total_features, discrete_features, 
                            continuous_features, target_variable, identifier)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id;
    """, (name, file_path, total_features, discrete_features, continuous_features, target_variable, identifier))
    
    dataset_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    
    return dataset_id


def get_dataset(dataset_id: int) -> Optional[Dict]:
    """Get a dataset by ID."""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    cur.execute("SELECT * FROM records WHERE id = %s", (dataset_id,))
    dataset = cur.fetchone()
    
    cur.close()
    conn.close()
    
    return dict(dataset) if dataset else None


def get_all_datasets() -> List[Dict]:
    """Get all datasets."""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    cur.execute("SELECT * FROM records ORDER BY created_at DESC")
    datasets = cur.fetchall()
    
    cur.close()
    conn.close()
    
    return [dict(d) for d in datasets]


def get_all_datasets_with_features() -> List[Dict]:
    """
    Return all datasets with their feature lists attached using a small,
    fixed number of queries (no per-dataset round trips).
    """
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    cur.execute("SELECT * FROM records ORDER BY created_at DESC")
    datasets = [dict(row) for row in cur.fetchall()]
    dataset_ids = [d['id'] for d in datasets]
    features_by_dataset: Dict[int, List[Dict]] = {d['id']: [] for d in datasets}
    
    if dataset_ids:
        cur.execute(
            """
            SELECT * FROM features
            WHERE dataset_id = ANY(%s)
            ORDER BY dataset_id, name
            """,
            (dataset_ids,),
        )
        for row in cur.fetchall():
            features_by_dataset.setdefault(row['dataset_id'], []).append(dict(row))
    
    cur.close()
    conn.close()
    
    for dataset in datasets:
        dataset['features'] = features_by_dataset.get(dataset['id'], [])
    
    return datasets


def get_latest_dataset() -> Optional[Dict]:
    """Get the most recently created dataset."""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    cur.execute("SELECT * FROM records ORDER BY created_at DESC LIMIT 1")
    dataset = cur.fetchone()
    
    cur.close()
    conn.close()
    
    return dict(dataset) if dataset else None


def update_dataset(dataset_id: int, **kwargs) -> bool:
    """
    Update dataset fields.
    
    Args:
        dataset_id: ID of dataset to update
        **kwargs: Fields to update (name, file_path, total_features, etc.)
    
    Returns:
        bool: True if successful
    """
    if not kwargs:
        return False
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Build SET clause dynamically
    set_clause = ", ".join([f"{key} = %s" for key in kwargs.keys()])
    values = list(kwargs.values()) + [dataset_id]
    
    cur.execute(f"""
        UPDATE records 
        SET {set_clause}
        WHERE id = %s
    """, values)
    
    conn.commit()
    cur.close()
    conn.close()
    
    return True


def delete_dataset(dataset_id: int) -> bool:
    """Delete a dataset and all related data (cascade)."""
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("DELETE FROM records WHERE id = %s", (dataset_id,))
    
    conn.commit()
    cur.close()
    conn.close()
    
    return True


# =====================================================
# FEATURE OPERATIONS
# =====================================================

def create_feature(dataset_id: int, name: str, feature_type: str, selected: bool = False) -> int:
    """
    Create a new feature record.
    
    Args:
        dataset_id: ID of the parent dataset
        name: Name of the feature/column
        feature_type: 'discrete' or 'continuous'
        selected: Whether this feature is selected for analysis
    
    Returns:
        int: The ID of the created feature
    """
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("""
        INSERT INTO features (dataset_id, name, type, selected)
        VALUES (%s, %s, %s, %s)
        RETURNING id;
    """, (dataset_id, name, feature_type, selected))
    
    feature_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    
    return feature_id


def create_features_batch(dataset_id: int, features: List[Dict]) -> List[int]:
    """
    Create multiple features at once.
    
    Args:
        dataset_id: ID of the parent dataset
        features: List of dicts with 'name', 'type', and optionally 'selected'
    
    Returns:
        List[int]: List of created feature IDs
    """
    if not features:
        return []
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    rows = [
        (
            dataset_id,
            feature['name'],
            feature['type'],
            feature.get('selected', False)
        )
        for feature in features
    ]
    
    query = """
        INSERT INTO features (dataset_id, name, type, selected)
        VALUES %s
        RETURNING id;
    """
    result = execute_values(cur, query, rows, fetch=True)
    feature_ids = [row[0] for row in result] if result else []
    
    conn.commit()
    cur.close()
    conn.close()
    
    return feature_ids


def get_feature(feature_id: int) -> Optional[Dict]:
    """Get a feature by ID."""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    cur.execute("SELECT * FROM features WHERE id = %s", (feature_id,))
    feature = cur.fetchone()
    
    cur.close()
    conn.close()
    
    return dict(feature) if feature else None


def get_features_by_dataset(dataset_id: int) -> List[Dict]:
    """Get all features for a dataset."""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    cur.execute("SELECT * FROM features WHERE dataset_id = %s ORDER BY name", (dataset_id,))
    features = cur.fetchall()
    
    cur.close()
    conn.close()
    
    return [dict(f) for f in features]


def get_features_with_fine_binning_metadata(dataset_id: int) -> List[Dict]:
    """
    Get all features for a dataset with their fine binning metadata.
    Returns features with is_monotonic, iv_value, and num_bins from fine binning step.
    """
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    cur.execute("""
        SELECT 
            f.*,
            bs.is_monotonic,
            bs.iv_value,
            bs.num_bins,
            bs.monotonic_direction
        FROM features f
        LEFT JOIN binning_steps bs ON f.id = bs.feature_id AND bs.step_type = 'fine'
        WHERE f.dataset_id = %s
        ORDER BY f.name
    """, (dataset_id,))
    features = cur.fetchall()
    
    cur.close()
    conn.close()
    
    return [dict(f) for f in features]


def get_feature_by_name(dataset_id: int, name: str) -> Optional[Dict]:
    """Get a feature by dataset ID and name."""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    cur.execute("SELECT * FROM features WHERE dataset_id = %s AND name = %s", (dataset_id, name))
    feature = cur.fetchone()
    
    cur.close()
    conn.close()
    
    return dict(feature) if feature else None


def update_feature(feature_id: int, **kwargs) -> bool:
    """Update feature fields (selected, type, etc.)."""
    if not kwargs:
        return False
    
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Check if final_selected or model_ready columns exist if we're trying to update them
        columns_to_check = []
        if 'final_selected' in kwargs:
            columns_to_check.append('final_selected')
        if 'model_ready' in kwargs:
            columns_to_check.append('model_ready')
        
        for col_name in columns_to_check:
            cur.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='features' AND column_name=%s
            """, (col_name,))
            if not cur.fetchone():
                # Column doesn't exist, add it
                cur.execute(f"ALTER TABLE features ADD COLUMN {col_name} BOOLEAN DEFAULT FALSE")
                conn.commit()
                print(f"[DB] Added missing {col_name} column to features table")
        
        set_clause = ", ".join([f"{key} = %s" for key in kwargs.keys()])
        values = list(kwargs.values()) + [feature_id]
        
        cur.execute(f"""
            UPDATE features 
            SET {set_clause}
            WHERE id = %s
        """, values)
        
        conn.commit()
        return True
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"[DB] Error in update_feature: {e}")
        raise
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


def update_features_selection(dataset_id: int, selected_feature_names: List[str]) -> bool:
    """
    Update which features are selected for analysis.
    NOTE: This function no longer sets all features to FALSE first.
    It only updates the specified features to maintain existing state.
    
    Args:
        dataset_id: ID of the dataset
        selected_feature_names: List of feature names that should be selected
    
    Returns:
        bool: True if successful
    """
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Only update the specified features - don't deselect all first
    # This preserves the existing state of features not in the list
    if selected_feature_names:
        # Set selected features to TRUE
        cur.execute("""
            UPDATE features 
            SET selected = TRUE 
            WHERE dataset_id = %s AND name = ANY(%s)
        """, (dataset_id, selected_feature_names))
    
    conn.commit()
    cur.close()
    conn.close()
    
    return True


def update_features_model_ready(dataset_id: int, model_ready_feature_names: List[str]) -> bool:
    """
    Update which features are marked as model_ready (set in Column Selection & Binning).
    
    Args:
        dataset_id: ID of the dataset
        model_ready_feature_names: List of feature names that should be model_ready
    
    Returns:
        bool: True if successful
    """
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Check if column exists first
        cur.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='features' AND column_name='model_ready'
        """)
        if not cur.fetchone():
            # Column doesn't exist, add it
            cur.execute("ALTER TABLE features ADD COLUMN model_ready BOOLEAN DEFAULT FALSE")
            conn.commit()
            print("[DB] Added missing model_ready column to features table")
        
        # First, deselect all features for this dataset
        cur.execute("UPDATE features SET model_ready = FALSE WHERE dataset_id = %s", (dataset_id,))
        
        # Then, select the specified features
        if model_ready_feature_names:
            # Use tuple with IN clause for better compatibility
            placeholders = ','.join(['%s'] * len(model_ready_feature_names))
            cur.execute(f"""
                UPDATE features 
                SET model_ready = TRUE 
                WHERE dataset_id = %s AND name IN ({placeholders})
            """, (dataset_id, *model_ready_feature_names))
        
        conn.commit()
        return True
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"[DB] Error in update_features_model_ready: {e}")
        raise
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

def update_features_final_selection(dataset_id: int, final_selected_feature_names: List[str]) -> bool:
    """
    Update which features are selected for final model training (final_selected column).
    
    Args:
        dataset_id: ID of the dataset
        final_selected_feature_names: List of feature names that should be final_selected
    
    Returns:
        bool: True if successful
    """
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Check if column exists first
        cur.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='features' AND column_name='final_selected'
        """)
        if not cur.fetchone():
            # Column doesn't exist, add it
            cur.execute("ALTER TABLE features ADD COLUMN final_selected BOOLEAN DEFAULT FALSE")
            conn.commit()
            print("[DB] Added missing final_selected column to features table")
        
        # First, deselect all features for this dataset
        cur.execute("UPDATE features SET final_selected = FALSE WHERE dataset_id = %s", (dataset_id,))
        
        # Then, select the specified features
        if final_selected_feature_names:
            # Use tuple with IN clause for better compatibility
            placeholders = ','.join(['%s'] * len(final_selected_feature_names))
            cur.execute(f"""
                UPDATE features 
                SET final_selected = TRUE 
                WHERE dataset_id = %s AND name IN ({placeholders})
            """, (dataset_id, *final_selected_feature_names))
        
        conn.commit()
        return True
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"[DB] Error in update_features_final_selection: {e}")
        raise
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


# =====================================================
# BINNING STEP OPERATIONS
# =====================================================

def create_binning_step(feature_id: int, step_type: str, method: str = None,
                       num_bins: int = None, is_monotonic: bool = False,
                       monotonic_direction: str = None, iv_value: float = None) -> int:
    """
    Create a new binning step record.
    
    Args:
        feature_id: ID of the feature
        step_type: 'coarse' or 'fine'
        method: Binning method used (e.g., 'qcut', 'merged', 'auto_monotonic')
        num_bins: Number of bins created
        is_monotonic: Whether WOE is monotonic
        monotonic_direction: 'increasing', 'decreasing', or None
        iv_value: Information Value for this binning
    
    Returns:
        int: The ID of the created binning step
    """
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # FIX: Ensure is_monotonic is Python bool (not numpy.bool) for psycopg2 compatibility
        is_monotonic_python = bool(is_monotonic) if is_monotonic is not None else False
        
        cur.execute("""
            INSERT INTO binning_steps (feature_id, step_type, method, num_bins, 
                                      is_monotonic, monotonic_direction, iv_value)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (feature_id, step_type) 
            DO UPDATE SET 
                method = EXCLUDED.method,
                num_bins = EXCLUDED.num_bins,
                is_monotonic = EXCLUDED.is_monotonic,
                monotonic_direction = EXCLUDED.monotonic_direction,
                iv_value = EXCLUDED.iv_value
            RETURNING id;
        """, (feature_id, step_type, method, num_bins, is_monotonic_python, monotonic_direction, iv_value))
        
        step_id = cur.fetchone()[0]
        conn.commit()
        return step_id
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"[DB] Error in create_binning_step: {e}")
        raise
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


def get_binning_step(step_id: int) -> Optional[Dict]:
    """Get a binning step by ID."""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    cur.execute("SELECT * FROM binning_steps WHERE id = %s", (step_id,))
    step = cur.fetchone()
    
    cur.close()
    conn.close()
    
    return dict(step) if step else None


def get_binning_steps_by_feature(feature_id: int) -> List[Dict]:
    """Get all binning steps for a feature."""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    cur.execute("SELECT * FROM binning_steps WHERE feature_id = %s ORDER BY step_type", (feature_id,))
    steps = cur.fetchall()
    
    cur.close()
    conn.close()
    
    return [dict(s) for s in steps]


def get_binning_step_by_type(feature_id: int, step_type: str) -> Optional[Dict]:
    """Get a specific binning step (coarse or fine) for a feature."""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    cur.execute("""
        SELECT * FROM binning_steps 
        WHERE feature_id = %s AND step_type = %s
    """, (feature_id, step_type))
    step = cur.fetchone()
    
    cur.close()
    conn.close()
    
    return dict(step) if step else None


def delete_binning_step(step_id: int) -> bool:
    """Delete a binning step and all related bins (cascade)."""
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("DELETE FROM binning_steps WHERE id = %s", (step_id,))
    
    conn.commit()
    cur.close()
    conn.close()
    
    return True


def update_binning_step(step_id: int, **kwargs) -> bool:
    """Update binning step fields (is_monotonic, monotonic_direction, etc.)."""
    if not kwargs:
        return False
    
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # FIX: Convert numpy.bool to Python bool for psycopg2 compatibility
        processed_kwargs = {}
        for key, value in kwargs.items():
            if key == 'is_monotonic' and value is not None:
                processed_kwargs[key] = bool(value)
            else:
                processed_kwargs[key] = value
        
        set_clause = ", ".join([f"{key} = %s" for key in processed_kwargs.keys()])
        values = list(processed_kwargs.values()) + [step_id]
        
        cur.execute(f"""
            UPDATE binning_steps 
            SET {set_clause}
            WHERE id = %s
        """, values)
        
        conn.commit()
        return True
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"[DB] Error in update_binning_step: {e}")
        raise
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


# =====================================================
# BIN OPERATIONS
# =====================================================

def create_bin(binning_step_id: int, bin_number: int, bin_label: str = None,
              min_value: float = None, max_value: float = None, range_text: str = None,
              good_count: int = 0, bad_count: int = 0, total_count: int = 0,
              **kwargs) -> int:
    """
    Create a new bin record.
    
    Args:
        binning_step_id: ID of the parent binning step
        bin_number: Sequential bin number (1, 2, 3, ...)
        bin_label: Human-readable bin label
        min_value: Minimum value (for continuous)
        max_value: Maximum value (for continuous)
        range_text: Text representation (for discrete)
        good_count: Count of Good cases
        bad_count: Count of Bad cases
        total_count: Total count
        **kwargs: Additional metrics (woe, iv, dist_good, dist_bad, etc.)
    
    Returns:
        int: The ID of the created bin
    """
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Extract additional metrics from kwargs (only woe and iv are stored)
    woe = kwargs.get('woe')
    iv = kwargs.get('iv')
    
    cur.execute("""
        INSERT INTO bins (
            binning_step_id, bin_number, bin_label, min_value, max_value, range_text,
            good_count, bad_count, total_count, woe, iv
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (binning_step_id, bin_number)
        DO UPDATE SET
            bin_label = EXCLUDED.bin_label,
            min_value = EXCLUDED.min_value,
            max_value = EXCLUDED.max_value,
            range_text = EXCLUDED.range_text,
            good_count = EXCLUDED.good_count,
            bad_count = EXCLUDED.bad_count,
            total_count = EXCLUDED.total_count,
            woe = EXCLUDED.woe,
            iv = EXCLUDED.iv
        RETURNING id;
    """, (binning_step_id, bin_number, bin_label, min_value, max_value, range_text,
          good_count, bad_count, total_count, woe, iv))
    
    bin_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    
    return bin_id


def create_bins_batch(binning_step_id: int, bins_data: List[Dict]) -> List[int]:
    """
    Create multiple bins at once.
    
    Args:
        binning_step_id: ID of the parent binning step
        bins_data: List of dicts containing bin data
    
    Returns:
        List[int]: List of created bin IDs
    """
    bin_ids = []
    for bin_data in bins_data:
        bin_id = create_bin(binning_step_id, **bin_data)
        bin_ids.append(bin_id)
    
    return bin_ids


def get_bins_by_step(binning_step_id: int) -> List[Dict]:
    """Get all bins for a binning step."""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    cur.execute("""
        SELECT * FROM bins 
        WHERE binning_step_id = %s 
        ORDER BY bin_number
    """, (binning_step_id,))
    bins = cur.fetchall()
    
    cur.close()
    conn.close()
    
    return [dict(b) for b in bins]


def delete_bins_by_step(binning_step_id: int) -> bool:
    """
    Delete all bins for a specific binning step.
    This ensures we start fresh when updating a binning step.
    """
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("DELETE FROM bins WHERE binning_step_id = %s", (binning_step_id,))
    
    conn.commit()
    cur.close()
    conn.close()
    
    return True


def get_bin(bin_id: int) -> Optional[Dict]:
    """Get a bin by ID."""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    cur.execute("SELECT * FROM bins WHERE id = %s", (bin_id,))
    bin_data = cur.fetchone()
    
    cur.close()
    conn.close()
    
    return dict(bin_data) if bin_data else None


# =====================================================
# MERGED BINS OPERATIONS
# =====================================================

def create_merged_bin(fine_step_id: int, merged_bin_number: int,
                     original_bin_ids: List[int], original_bin_labels: List[str]) -> int:
    """
    Create a merged bin record.
    
    Args:
        fine_step_id: ID of the fine binning step
        merged_bin_number: The resulting bin number after merge
        original_bin_ids: List of original bin IDs that were merged
        original_bin_labels: List of original bin labels that were merged
    
    Returns:
        int: The ID of the created merged bin record
    """
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("""
        INSERT INTO merged_bins (fine_step_id, merged_bin_number, original_bin_ids, original_bin_labels)
        VALUES (%s, %s, %s, %s)
        RETURNING id;
    """, (fine_step_id, merged_bin_number, original_bin_ids, original_bin_labels))
    
    merged_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    
    return merged_id


def get_merged_bins_by_step(fine_step_id: int) -> List[Dict]:
    """Get all merged bins for a fine binning step."""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    cur.execute("""
        SELECT * FROM merged_bins 
        WHERE fine_step_id = %s 
        ORDER BY merged_bin_number
    """, (fine_step_id,))
    merged_bins = cur.fetchall()
    
    cur.close()
    conn.close()
    
    return [dict(mb) for mb in merged_bins]


# =====================================================
# BINNING TOTALS OPERATIONS
# =====================================================

def create_binning_totals(binning_step_id: int, total_good: int, total_bad: int,
                         total_count: int, good_bad_ratio: float = None,
                         bad_rate: float = None, freq_percent: float = 100.0,
                         iv: float = None) -> int:
    """
    Create or update binning totals for a binning step.
    
    Args:
        binning_step_id: ID of the binning step
        total_good: Total count of Good cases
        total_bad: Total count of Bad cases
        total_count: Total count (Good + Bad)
        good_bad_ratio: Overall ratio of Good to Bad
        bad_rate: Overall percentage of Bad cases
        freq_percent: Frequency percentage (typically 100%)
        iv: Total Information Value
    
    Returns:
        int: The ID of the created/updated binning totals record
    """
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("""
        INSERT INTO binning_totals (
            binning_step_id, total_good, total_bad, total_count,
            good_bad_ratio, bad_rate, freq_percent, iv
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (binning_step_id)
        DO UPDATE SET
            total_good = EXCLUDED.total_good,
            total_bad = EXCLUDED.total_bad,
            total_count = EXCLUDED.total_count,
            good_bad_ratio = EXCLUDED.good_bad_ratio,
            bad_rate = EXCLUDED.bad_rate,
            freq_percent = EXCLUDED.freq_percent,
            iv = EXCLUDED.iv
        RETURNING id;
    """, (binning_step_id, total_good, total_bad, total_count,
          good_bad_ratio, bad_rate, freq_percent, iv))
    
    totals_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    
    return totals_id


def get_binning_totals(binning_step_id: int) -> Optional[Dict]:
    """Get binning totals for a binning step."""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    cur.execute("""
        SELECT * FROM binning_totals 
        WHERE binning_step_id = %s
    """, (binning_step_id,))
    totals = cur.fetchone()
    
    cur.close()
    conn.close()
    
    return dict(totals) if totals else None


def get_all_binning_totals_by_dataset(dataset_id: int) -> List[Dict]:
    """
    Get all binning totals for all features in a dataset.
    Joins with features and binning_steps to provide complete context.
    """
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    cur.execute("""
        SELECT 
            bt.*,
            bs.step_type,
            bs.method,
            bs.is_monotonic,
            f.name AS feature_name,
            f.type AS feature_type
        FROM binning_totals bt
        JOIN binning_steps bs ON bt.binning_step_id = bs.id
        JOIN features f ON bs.feature_id = f.id
        WHERE f.dataset_id = %s
        ORDER BY f.name, bs.step_type
    """, (dataset_id,))
    totals = cur.fetchall()
    
    cur.close()
    conn.close()
    
    return [dict(t) for t in totals]


# =====================================================
# HELPER FUNCTIONS FOR COMPLEX OPERATIONS
# =====================================================

def get_complete_binning_results(feature_id: int, step_type: str = 'fine') -> Optional[Dict]:
    """
    Get complete binning results for a feature including all bins, totals, and metadata.
    
    Args:
        feature_id: ID of the feature
        step_type: 'coarse' or 'fine' (default: 'fine')
    
    Returns:
        Dict with feature info, binning step info, bins data, totals, and merged bins
    """
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    # Get feature info
    feature = get_feature(feature_id)
    if not feature:
        return None
    
    # Get binning step
    step = get_binning_step_by_type(feature_id, step_type)
    if not step:
        return None
    
    # Get bins
    bins = get_bins_by_step(step['id'])
    
    # Get totals
    totals = get_binning_totals(step['id'])
    
    # Get merged bins if fine binning
    merged_bins = []
    if step_type == 'fine':
        merged_bins = get_merged_bins_by_step(step['id'])
    
    cur.close()
    conn.close()
    
    return {
        'feature': feature,
        'binning_step': step,
        'bins': bins,
        'totals': totals,
        'merged_bins': merged_bins
    }


def get_dataset_with_all_results(dataset_id: int) -> Optional[Dict]:
    """
    Get full dataset information (features + binning metadata) using batched queries
    so we only touch the database a handful of times regardless of feature count.
    """
    dataset = get_dataset(dataset_id)
    if not dataset:
        return None
    
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    cur.execute(
        """
        SELECT * FROM features
        WHERE dataset_id = %s
        ORDER BY name
        """,
        (dataset_id,),
    )
    features = [dict(row) for row in cur.fetchall()]
    feature_lookup = {f['id']: f for f in features}
    
    feature_ids = list(feature_lookup.keys())
    if not feature_ids:
        cur.close()
        conn.close()
        return {'dataset': dataset, 'features': features}
    
    # Pre-seed binning containers
    for feature in features:
        feature['binning'] = {'coarse': None, 'fine': None}
    
    cur.execute(
        """
        SELECT * FROM binning_steps
        WHERE feature_id = ANY(%s)
        ORDER BY feature_id, step_type
        """,
        (feature_ids,),
    )
    steps = [dict(row) for row in cur.fetchall()]
    step_ids = [s['id'] for s in steps]
    
    bins_by_step: Dict[int, List[Dict]] = {}
    totals_by_step: Dict[int, Dict] = {}
    merged_by_step: Dict[int, List[Dict]] = {}
    
    if step_ids:
        cur.execute(
            """
            SELECT * FROM bins
            WHERE binning_step_id = ANY(%s)
            ORDER BY binning_step_id, bin_number
            """,
            (step_ids,),
        )
        for row in cur.fetchall():
            bins_by_step.setdefault(row['binning_step_id'], []).append(dict(row))
        
        cur.execute(
            """
            SELECT * FROM binning_totals
            WHERE binning_step_id = ANY(%s)
            """,
            (step_ids,),
        )
        for row in cur.fetchall():
            totals_by_step[row['binning_step_id']] = dict(row)
    
    fine_step_ids = [s['id'] for s in steps if s.get('step_type') == 'fine']
    if fine_step_ids:
        cur.execute(
            """
            SELECT * FROM merged_bins
            WHERE fine_step_id = ANY(%s)
            ORDER BY fine_step_id, merged_bin_number
            """,
            (fine_step_ids,),
        )
        for row in cur.fetchall():
            merged_by_step.setdefault(row['fine_step_id'], []).append(dict(row))
    
    cur.close()
    conn.close()
    
    # Import calculate_derived_bin_metrics from app.py
    # Note: This creates a circular import, so we'll calculate in app.py instead
    # For now, bins are returned as-is from db.py, and app.py will enrich them
    for step in steps:
        feature = feature_lookup.get(step['feature_id'])
        if not feature:
            continue
        binning_payload = {
            'step': step,
            'bins': bins_by_step.get(step['id'], []),
            'totals': totals_by_step.get(step['id'])
        }
        if step['step_type'] == 'fine':
            binning_payload['merged_bins'] = merged_by_step.get(step['id'], [])
            binning_payload['iv'] = float(step['iv_value']) if step.get('iv_value') is not None else None
        binning_payload['type'] = feature.get('type')
        feature['binning'][step['step_type']] = binning_payload
    
    return {
        'dataset': dataset,
        'features': features
    }


def delete_all_binning_for_feature(feature_id: int) -> bool:
    """
    Delete all binning results (coarse and fine) for a feature.
    This includes binning_steps, bins, merged_bins, and binning_totals.
    Useful for resetting a feature's binning.
    """
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Get all fine_step_ids for this feature before deleting binning_steps
    # This ensures we can explicitly delete merged_bins (though CASCADE should handle it)
    cur.execute("""
        SELECT id FROM binning_steps 
        WHERE feature_id = %s AND step_type = 'fine'
    """, (feature_id,))
    fine_step_ids = [row[0] for row in cur.fetchall()]
    
    # Explicitly delete merged_bins for all fine steps (for clarity, though CASCADE should handle it)
    if fine_step_ids:
        # Delete merged_bins one by one or use a subquery for safety
        for fine_step_id in fine_step_ids:
            cur.execute("DELETE FROM merged_bins WHERE fine_step_id = %s", (fine_step_id,))
    
    # Delete all binning steps (this will CASCADE delete bins and binning_totals)
    cur.execute("DELETE FROM binning_steps WHERE feature_id = %s", (feature_id,))
    
    conn.commit()
    cur.close()
    conn.close()
    
    return True


# =====================================================
# TRAIN/TEST SPLIT OPERATIONS
# =====================================================

def save_train_test_split_metadata(dataset_id: int, split_info: Dict) -> bool:
    """
    Save train/test split metadata to database.
    
    Parameters:
    -----------
    dataset_id : int
        Dataset ID
    split_info : dict
        Split metadata dictionary containing:
        - seed: int
        - test_size: float (proportion)
        - method: str
        - train_size: int
        - test_size_count: int (count of test rows)
        - train_bad: int
        - test_bad: int
        - data_hash: str
        
    Returns:
    --------
    bool : Success status
    """
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # First, verify the record exists
        cur.execute("SELECT id FROM records WHERE id = %s", (dataset_id,))
        if not cur.fetchone():
            print(f"[DB] ERROR: Dataset {dataset_id} not found in records table")
            return False
        
        # Check if columns exist (if not, they'll be added by migration)
        cur.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'records' 
            AND column_name = 'train_test_split_seed'
        """)
        if not cur.fetchone():
            print(f"[DB] ERROR: Train/test split columns do not exist in records table!")
            print(f"[DB] Please run: python3 validate_and_migrate_schema.py")
            return False
        
        # Prepare values
        test_size_count = split_info.get('test_size_count', split_info.get('test_size', 0))
        
        print(f"[DB] Saving train/test split for dataset {dataset_id}:")
        print(f"  Seed: {split_info['seed']}")
        print(f"  Test size (proportion): {split_info['test_size']}")
        print(f"  Test size (count): {test_size_count}")
        print(f"  Train size: {split_info['train_size']}")
        print(f"  Train bad: {split_info['train_bad']}")
        print(f"  Test bad: {split_info['test_bad']}")
        
        # Check if train_path and test_path columns exist
        cur.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'records' 
            AND column_name IN ('train_path', 'test_path')
        """)
        path_columns_exist = len(cur.fetchall()) == 2
        
        # Build UPDATE query with or without path columns
        if path_columns_exist:
            cur.execute("""
                UPDATE records
                SET train_test_split_seed = %s,
                    train_test_split_size = %s,
                    train_test_split_method = %s,
                    train_size = %s,
                    test_size = %s,
                    train_bad_count = %s,
                    test_bad_count = %s,
                    split_created_at = NOW(),
                    data_hash = %s,
                    train_path = %s,
                    test_path = %s
                WHERE id = %s
            """, (
                split_info['seed'],
                split_info['test_size'],  # Proportion (0.2 for 20%)
                split_info['method'],
                split_info['train_size'],
                test_size_count,  # Count of test rows
                split_info['train_bad'],
                split_info['test_bad'],
                split_info.get('data_hash'),
                split_info.get('train_path'),
                split_info.get('test_path'),
                dataset_id
            ))
        else:
            # Fallback if columns don't exist yet
            cur.execute("""
                UPDATE records
                SET train_test_split_seed = %s,
                    train_test_split_size = %s,
                    train_test_split_method = %s,
                    train_size = %s,
                    test_size = %s,
                    train_bad_count = %s,
                    test_bad_count = %s,
                    split_created_at = NOW(),
                    data_hash = %s
                WHERE id = %s
            """, (
                split_info['seed'],
                split_info['test_size'],  # Proportion (0.2 for 20%)
                split_info['method'],
                split_info['train_size'],
                test_size_count,  # Count of test rows
                split_info['train_bad'],
                split_info['test_bad'],
                split_info.get('data_hash'),
                dataset_id
            ))
            if split_info.get('train_path') or split_info.get('test_path'):
                print(f"[DB] WARNING: train_path/test_path provided but columns don't exist in database")
                print(f"[DB] Please add columns: ALTER TABLE records ADD COLUMN train_path TEXT, ADD COLUMN test_path TEXT;")
        
        # Verify the update worked
        rows_updated = cur.rowcount
        if rows_updated == 0:
            print(f"[DB] WARNING: UPDATE affected 0 rows. Dataset {dataset_id} may not exist.")
            conn.rollback()
            return False
        
        conn.commit()
        print(f"[DB] ✅ Successfully saved train/test split metadata for dataset {dataset_id} ({rows_updated} row updated)")
        
        # Verify the save worked
        cur.execute("""
            SELECT train_test_split_seed, train_size, test_size 
            FROM records 
            WHERE id = %s
        """, (dataset_id,))
        verify_row = cur.fetchone()
        if verify_row and verify_row[0] is not None:
            print(f"[DB] ✅ Verified: Saved seed={verify_row[0]}, train={verify_row[1]}, test={verify_row[2]}")
        else:
            print(f"[DB] ⚠️  WARNING: Verification query returned None - data may not have been saved")
        
        return True
    except Exception as e:
        conn.rollback()
        print(f"[DB] ❌ Error saving train/test split: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        cur.close()
        conn.close()


def get_train_test_split_info(dataset_id: int) -> Optional[Dict]:
    """
    Get train/test split metadata for a dataset.
    
    Parameters:
    -----------
    dataset_id : int
        Dataset ID
        
    Returns:
    --------
    dict or None : Split metadata if exists
    """
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Check if train_path and test_path columns exist
        cur.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'records' 
            AND column_name IN ('train_path', 'test_path')
        """)
        path_columns_exist = len(cur.fetchall()) == 2
        
        # Build SELECT query with or without path columns
        if path_columns_exist:
            cur.execute("""
                SELECT train_test_split_seed,
                       train_test_split_size,
                       train_test_split_method,
                       train_size,
                       test_size,
                       train_bad_count,
                       test_bad_count,
                       split_created_at,
                       data_hash,
                       train_path,
                       test_path
                FROM records
                WHERE id = %s
            """, (dataset_id,))
        else:
            cur.execute("""
                SELECT train_test_split_seed,
                       train_test_split_size,
                       train_test_split_method,
                       train_size,
                       test_size,
                       train_bad_count,
                       test_bad_count,
                       split_created_at,
                       data_hash,
                       NULL as train_path,
                       NULL as test_path
                FROM records
                WHERE id = %s
            """, (dataset_id,))
        
        row = cur.fetchone()
        
        if not row or row[0] is None:
            # No split exists
            return None
        
        result = {
            'seed': row[0],
            'test_size': float(row[1]) if row[1] else None,  # Proportion (0.2 for 20%)
            'method': row[2],
            'train_size': row[3],
            'test_size_count': row[4],  # Count of test rows
            'train_bad': row[5],
            'test_bad': row[6],
            'split_created_at': row[7],
            'data_hash': row[8],
            # Calculate rates for convenience
            'train_bad_rate': row[5] / row[3] if row[3] and row[5] else None,
            'test_bad_rate': row[6] / row[4] if row[4] and row[6] else None
        }
        
        # Add paths if columns exist
        if path_columns_exist and len(row) > 9:
            result['train_path'] = row[9]
            result['test_path'] = row[10]
        
        return result
    except Exception as e:
        print(f"[DB] Error retrieving train/test split info: {e}")
        return None
    finally:
        cur.close()
        conn.close()


def clear_train_test_split(dataset_id: int) -> bool:
    """
    Clear train/test split metadata for a dataset.
    
    Parameters:
    -----------
    dataset_id : int
        Dataset ID
        
    Returns:
    --------
    bool : Success status
    """
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        cur.execute("""
            UPDATE records
            SET train_test_split_seed = NULL,
                train_test_split_size = NULL,
                train_test_split_method = NULL,
                train_size = NULL,
                test_size = NULL,
                train_bad_count = NULL,
                test_bad_count = NULL,
                split_created_at = NULL,
                data_hash = NULL
            WHERE id = %s
        """, (dataset_id,))
        
        conn.commit()
        print(f"[DB] Cleared train/test split for dataset {dataset_id}")
        return True
    except Exception as e:
        conn.rollback()
        print(f"[DB] Error clearing train/test split: {e}")
        return False
    finally:
        cur.close()
        conn.close()
