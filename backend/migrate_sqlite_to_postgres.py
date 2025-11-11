import sqlite3
import psycopg2
import os

# SQLite and PostgreSQL connection details
SQLITE_DB = os.path.join(os.path.dirname(__file__), 'records.db')
PG_DBNAME = os.getenv('PG_DBNAME', 'mydb')
PG_USER = os.getenv('PG_USER', 'myuser')
PG_PASSWORD = os.getenv('PG_PASSWORD', 'mypassword')
PG_HOST = os.getenv('PG_HOST', 'localhost')
PG_PORT = os.getenv('PG_PORT', '5432')

# Connect to SQLite
sqlite_conn = sqlite3.connect(SQLITE_DB)
sqlite_cur = sqlite_conn.cursor()

# Connect to PostgreSQL
pg_conn = psycopg2.connect(
    dbname=PG_DBNAME,
    user=PG_USER,
    password=PG_PASSWORD,
    host=PG_HOST,
    port=PG_PORT
)
pg_cur = pg_conn.cursor()

# Migrate records table
sqlite_cur.execute('SELECT id, dataset_path, discrete_columns, continuous_columns, selected_columns, target_variable, univariate_results, finebin_results, crosstab_results, woe_iv_results, created_at FROM records')
records = sqlite_cur.fetchall()
for row in records:
    pg_cur.execute('''
        INSERT INTO records (id, dataset_path, discrete_columns, continuous_columns, selected_columns, target_variable, univariate_results, finebin_results, crosstab_results, woe_iv_results, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (id) DO NOTHING;
    ''', row)

# Migrate finebin_details table
sqlite_cur.execute('SELECT id, record_id, column_name, group_id, merged_bins FROM finebin_details')
finebins = sqlite_cur.fetchall()
for row in finebins:
    pg_cur.execute('''
        INSERT INTO finebin_details (id, record_id, column_name, group_id, merged_bins)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (id) DO NOTHING;
    ''', row)

pg_conn.commit()
sqlite_conn.close()
pg_conn.close()

print('Migration complete!')
