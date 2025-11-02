import psycopg2
from psycopg2.extras import RealDictCursor
import os
import json


# PostgreSQL connection details (replace with your actual credentials)
def init_db():
    """
    Stub for database initialization. No-op for PostgreSQL.
    """
    pass
# Prefer a full DATABASE_URL if provided; fall back to individual PG_* vars.
DATABASE_URL = os.getenv('DATABASE_URL')
PG_DBNAME = os.getenv('PG_DBNAME', 'your_db_name')
PG_USER = os.getenv('PG_USER', 'your_db_user')
PG_PASSWORD = os.getenv('PG_PASSWORD', 'your_db_password')
PG_HOST = os.getenv('PG_HOST', 'localhost')
PG_PORT = os.getenv('PG_PORT', '5432')


def get_db_connection():
    """
    Return a psycopg2 connection. If DATABASE_URL is set, use it directly
    (recommended). Otherwise use individual PG_* environment variables.
    """
    if DATABASE_URL:
        # Let psycopg2 parse the full connection string / DSN
        return psycopg2.connect(DATABASE_URL)

    # Fallback to component-wise connection
    conn = psycopg2.connect(
        dbname=PG_DBNAME,
        user=PG_USER,
        password=PG_PASSWORD,
        host=PG_HOST,
        port=PG_PORT
    )
    return conn


def save_record_db(dataset_path, discrete_columns, continuous_columns, selected_columns, dashboard_selected_columns, target_variable, univariate_results, finebin_results, crosstab_results, woe_iv_results):
    """
    Save a record of the analysis to the database.
    Returns the ID of the inserted record.
    """
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO records (dataset_path, discrete_columns, continuous_columns, selected_columns, dashboard_selected_columns, target_variable, univariate_results, finebin_results, crosstab_results, woe_iv_results)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id;
        """,
        (dataset_path, discrete_columns, continuous_columns, selected_columns, dashboard_selected_columns, target_variable, univariate_results, finebin_results, crosstab_results, woe_iv_results)
    )
    record_id = cur.fetchone()[0]
    conn.commit()
    conn.close()
    return record_id

def upsert_single_record_db(dataset_path, discrete_columns, continuous_columns, selected_columns, dashboard_selected_columns, target_variable, univariate_results, finebin_results, crosstab_results, woe_iv_results):
    """
    Create or update a single record in the database. If no record exists, insert one; otherwise update the latest record.
    Returns the ID of the inserted or updated record.
    """
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM records ORDER BY created_at DESC LIMIT 1")
    row = cur.fetchone()
    if row is None:
        cur.execute(
            """
            INSERT INTO records (dataset_path, discrete_columns, continuous_columns, selected_columns, dashboard_selected_columns, target_variable, univariate_results, finebin_results, crosstab_results, woe_iv_results)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id;
            """,
            (dataset_path, discrete_columns, continuous_columns, selected_columns, dashboard_selected_columns, target_variable, univariate_results, finebin_results, crosstab_results, woe_iv_results)
        )
        record_id = cur.fetchone()[0]
        conn.commit()
    else:
        record_id = row[0]
        cur.execute(
            """
            UPDATE records
            SET dataset_path = %s,
                discrete_columns = %s,
                continuous_columns = %s,
                selected_columns = %s,
                dashboard_selected_columns = COALESCE(%s, dashboard_selected_columns),
                target_variable = %s,
                univariate_results = %s,
                finebin_results = %s,
                crosstab_results = %s,
                woe_iv_results = %s
            WHERE id = %s
            """,
            (dataset_path, discrete_columns, continuous_columns, selected_columns, dashboard_selected_columns, target_variable, univariate_results, finebin_results, crosstab_results, woe_iv_results, record_id)
        )
        conn.commit()
    conn.close()
    return record_id

def get_records_db():
    """
    List all analysis records (summary only) from the database.
    """
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT id, dataset_path, discrete_columns, continuous_columns, selected_columns, target_variable, created_at FROM records ORDER BY created_at DESC")
    records = cur.fetchall()
    conn.close()
    return records

def get_latest_record_dataset_path_db():
    """
    Returns the dataset_path of the latest record and whether the file exists.
    """
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT dataset_path FROM records ORDER BY created_at DESC LIMIT 1")
    row = cur.fetchone()
    conn.close()
    if not row:
        return None, None, False
    dataset_path = row[0]
    resolved = dataset_path
    if dataset_path and not os.path.isabs(dataset_path):
        resolved = os.path.join(os.path.dirname(__file__), dataset_path)
    valid = bool(resolved and os.path.exists(resolved))
    return dataset_path, resolved, valid

def get_record_db(record_id):
    """
    Get a specific analysis record (full details) from the database.
    """
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM records WHERE id = %s", (record_id,))
    row = cur.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None

def delete_record_db(record_id):
    """
    Delete a specific analysis record by ID, and remove any related finebin_details rows.
    """
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM finebin_details WHERE record_id = %s", (record_id,))
    except Exception:
        pass
    cur.execute("DELETE FROM records WHERE id = %s", (record_id,))
    conn.commit()
    conn.close()
    return True

def save_finebin_details_db(record_id, column_name, bin_merges):
    """
    Upsert fine binning details for a specific record and column.
    """
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM finebin_details WHERE record_id = %s AND column_name = %s",
        (record_id, column_name)
    )
    for group_id, bins in bin_merges.items():
        cur.execute(
            """
            INSERT INTO finebin_details (record_id, column_name, group_id, merged_bins)
            VALUES (%s, %s, %s, %s)
            """,
            (record_id, column_name, str(group_id), json.dumps(bins))
        )
    conn.commit()
    conn.close()
    return True

def get_finebin_details_db(record_id, column_name):
    """
    Retrieve fine binning details for a specific record and column.
    """
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT group_id, merged_bins FROM finebin_details
        WHERE record_id = %s AND column_name = %s
        """,
        (record_id, column_name)
    )
    rows = cur.fetchall()
    conn.close()
    finebin_details = [
        {"group_id": row[0], "merged_bins": row[1]} for row in rows
    ]
    return finebin_details