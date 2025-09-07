import sqlite3
import os
import json

# Database initialization
DB_PATH = os.path.join(os.path.dirname(__file__), 'database.sql')
DB_FILE = os.path.join(os.path.dirname(__file__), 'records.db')

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with open(DB_PATH, 'r') as f:
        sql = f.read()
    conn = get_db_connection()

def save_record_db(dataset_path, discrete_columns, continuous_columns, selected_columns, target_variable, univariate_results, finebin_results, crosstab_results):
    """
    Save a record of the analysis to the database.
    Returns the ID of the inserted record.
    """
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO records (dataset_path, discrete_columns, continuous_columns, selected_columns, target_variable, univariate_results, finebin_results, crosstab_results)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (dataset_path, discrete_columns, continuous_columns, selected_columns, target_variable, univariate_results, finebin_results, crosstab_results)
    )
    conn.commit()
    record_id = cur.lastrowid
    conn.close()
    return record_id

def upsert_single_record_db(dataset_path, discrete_columns, continuous_columns, selected_columns, target_variable, univariate_results, finebin_results, crosstab_results, woe_iv_results):
    """
    Create or update a single record in the database. If no record exists, insert one; otherwise update the latest record.
    Returns the ID of the inserted or updated record.
    """
    conn = get_db_connection()
    cur = conn.cursor()
    # Check if a record exists
    cur.execute("SELECT id FROM records ORDER BY created_at DESC LIMIT 1")
    row = cur.fetchone()
    if row is None:
        # Insert new record
        cur.execute(
            """
            INSERT INTO records (dataset_path, discrete_columns, continuous_columns, selected_columns, target_variable, univariate_results, finebin_results, crosstab_results, woe_iv_results)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (dataset_path, discrete_columns, continuous_columns, selected_columns, target_variable, univariate_results, finebin_results, crosstab_results, woe_iv_results)
        )
        conn.commit()
        record_id = cur.lastrowid
    else:
        # Update existing latest record
        record_id = row['id'] if isinstance(row, sqlite3.Row) else row[0]
        cur.execute(
            """
            UPDATE records
            SET dataset_path = ?,
                discrete_columns = ?,
                continuous_columns = ?,
                selected_columns = ?,
                target_variable = ?,
                univariate_results = ?,
                finebin_results = ?,
                crosstab_results = ?,
                woe_iv_results = ?
            WHERE id = ?
            """,
            (dataset_path, discrete_columns, continuous_columns, selected_columns, target_variable, univariate_results, finebin_results, crosstab_results, woe_iv_results, record_id)
        )
        conn.commit()
    conn.close()
    return record_id

def get_records_db():
    """
    List all analysis records (summary only) from the database.
    """
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, dataset_path, discrete_columns, continuous_columns, selected_columns, target_variable, created_at FROM records ORDER BY created_at DESC")
    rows = cur.fetchall()
    records = [dict(row) for row in rows]
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
    dataset_path = row[0] if not isinstance(row, sqlite3.Row) else row['dataset_path']
    # Resolve relative paths relative to backend directory
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
    cur = conn.cursor()
    cur.execute("SELECT * FROM records WHERE id = ?", (record_id,))
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
    # First remove finebin_details for this record
    try:
        cur.execute("DELETE FROM finebin_details WHERE record_id = ?", (record_id,))
    except Exception:
        # If table doesn't exist or other issue, continue to delete record
        pass
    # Then remove the record
    cur.execute("DELETE FROM records WHERE id = ?", (record_id,))
    conn.commit()
    conn.close()
    return True

def save_finebin_details_db(record_id, column_name, bin_merges):
    """
    Upsert fine binning details for a specific record and column.
    """
    conn = get_db_connection()
    cur = conn.cursor()
    # Delete previous entries for this record/column
    cur.execute(
        "DELETE FROM finebin_details WHERE record_id = ? AND column_name = ?",
        (record_id, column_name)
    )
    # Insert new rows per group
    for group_id, bins in bin_merges.items():
        cur.execute(
            """
            INSERT INTO finebin_details (record_id, column_name, group_id, merged_bins)
            VALUES (?, ?, ?, ?)
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
        WHERE record_id = ? AND column_name = ?
        """,
        (record_id, column_name)
    )
    rows = cur.fetchall()
    conn.close()
    finebin_details = [
        {"group_id": row[0], "merged_bins": row[1]} for row in rows
    ]
    return finebin_details