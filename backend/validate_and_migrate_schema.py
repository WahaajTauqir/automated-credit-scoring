"""
Schema Validation and Migration Script for Credit Scoring Application

This script checks if the PostgreSQL database has the correct table structure.
If not, it provides options to:
1. Create the new schema (if tables don't exist)
2. Warn user to manually drop and recreate (if structure is incorrect)
3. Migrate data from old schema to new schema (if requested)

Usage:
    python validate_and_migrate_schema.py [--force-recreate] [--migrate-data]
"""

import psycopg2
from psycopg2.extras import RealDictCursor
import os
import sys
import argparse
from datetime import datetime

# Import database connection from db.py
try:
    from db import get_db_connection
except ImportError:
    print("Error: Could not import get_db_connection from db.py")
    sys.exit(1)


# Expected schema definition
EXPECTED_TABLES = {
    'datasets': {
        'columns': [
            'id', 'name', 'file_path', 'total_features', 'discrete_features',
            'continuous_features', 'target_variable', 'created_at', 'updated_at'
        ]
    },
    'features': {
        'columns': ['id', 'dataset_id', 'name', 'type', 'selected', 'created_at']
    },
    'binning_steps': {
        'columns': [
            'id', 'feature_id', 'step_type', 'method', 'num_bins',
            'is_monotonic', 'monotonic_direction', 'iv_value', 'created_at'
        ]
    },
    'bins': {
        'columns': [
            'id', 'binning_step_id', 'bin_number', 'bin_label', 'min_value',
            'max_value', 'range_text', 'good_count', 'bad_count', 'total_count',
            'good_bad_ratio', 'bad_rate', 'freq_percent', 'odds', 'index_value',
            'odds_index', 'dist_good', 'dist_bad', 'woe', 'iv', 'created_at'
        ]
    },
    'merged_bins': {
        'columns': [
            'id', 'fine_step_id', 'merged_bin_number', 'original_bin_ids',
            'original_bin_labels', 'created_at'
        ]
    }
}


def check_table_exists(conn, table_name):
    """Check if a table exists in the database."""
    cur = conn.cursor()
    cur.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name = %s
        );
    """, (table_name,))
    exists = cur.fetchone()[0]
    cur.close()
    return exists


def get_table_columns(conn, table_name):
    """Get list of columns for a table."""
    cur = conn.cursor()
    cur.execute("""
        SELECT column_name 
        FROM information_schema.columns
        WHERE table_schema = 'public' 
        AND table_name = %s
        ORDER BY ordinal_position;
    """, (table_name,))
    columns = [row[0] for row in cur.fetchall()]
    cur.close()
    return columns


def validate_schema(conn):
    """
    Validate the database schema against expected structure.
    
    Returns:
        tuple: (is_valid, missing_tables, incorrect_tables, old_tables)
    """
    print("\n=== Validating Database Schema ===\n")
    
    missing_tables = []
    incorrect_tables = {}
    is_valid = True
    
    # Check for expected tables
    for table_name, table_def in EXPECTED_TABLES.items():
        if not check_table_exists(conn, table_name):
            print(f"❌ Table '{table_name}' does NOT exist")
            missing_tables.append(table_name)
            is_valid = False
        else:
            # Check columns
            actual_columns = get_table_columns(conn, table_name)
            expected_columns = table_def['columns']
            
            missing_cols = set(expected_columns) - set(actual_columns)
            extra_cols = set(actual_columns) - set(expected_columns)
            
            if missing_cols or extra_cols:
                print(f"⚠️  Table '{table_name}' exists but has incorrect structure:")
                if missing_cols:
                    print(f"   Missing columns: {', '.join(missing_cols)}")
                if extra_cols:
                    print(f"   Extra columns: {', '.join(extra_cols)}")
                incorrect_tables[table_name] = {
                    'missing': list(missing_cols),
                    'extra': list(extra_cols)
                }
                is_valid = False
            else:
                print(f"✅ Table '{table_name}' is correct")
    
    # Check for old tables that should be removed
    old_tables = []
    old_table_names = ['records', 'finebin_details']
    for old_table in old_table_names:
        if check_table_exists(conn, old_table):
            print(f"⚠️  Old table '{old_table}' still exists (should be removed)")
            old_tables.append(old_table)
    
    return is_valid, missing_tables, incorrect_tables, old_tables


def create_new_schema(conn):
    """Create the new database schema."""
    print("\n=== Creating New Database Schema ===\n")
    
    schema_file = os.path.join(os.path.dirname(__file__), 'schema_new.sql')
    
    if not os.path.exists(schema_file):
        print(f"❌ Error: Schema file not found: {schema_file}")
        return False
    
    try:
        with open(schema_file, 'r') as f:
            schema_sql = f.read()
        
        cur = conn.cursor()
        cur.execute(schema_sql)
        conn.commit()
        cur.close()
        
        print("✅ New schema created successfully!")
        return True
        
    except Exception as e:
        print(f"❌ Error creating schema: {e}")
        conn.rollback()
        return False


def backup_old_data(conn):
    """Backup data from old schema before migration."""
    print("\n=== Backing Up Old Data ===\n")
    
    backup_dir = os.path.join(os.path.dirname(__file__), 'backup')
    os.makedirs(backup_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    try:
        # Backup records table
        if check_table_exists(conn, 'records'):
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("SELECT * FROM records")
            records = cur.fetchall()
            cur.close()
            
            backup_file = os.path.join(backup_dir, f'records_backup_{timestamp}.json')
            import json
            with open(backup_file, 'w') as f:
                json.dump([dict(r) for r in records], f, indent=2, default=str)
            print(f"✅ Backed up {len(records)} records to {backup_file}")
        
        # Backup finebin_details table
        if check_table_exists(conn, 'finebin_details'):
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("SELECT * FROM finebin_details")
            details = cur.fetchall()
            cur.close()
            
            backup_file = os.path.join(backup_dir, f'finebin_details_backup_{timestamp}.json')
            with open(backup_file, 'w') as f:
                json.dump([dict(d) for d in details], f, indent=2, default=str)
            print(f"✅ Backed up {len(details)} finebin_details to {backup_file}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error backing up data: {e}")
        return False


def drop_old_tables(conn):
    """Drop old tables (records, finebin_details)."""
    print("\n=== Dropping Old Tables ===\n")
    
    try:
        cur = conn.cursor()
        
        # Drop in correct order (dependencies first)
        if check_table_exists(conn, 'finebin_details'):
            cur.execute("DROP TABLE IF EXISTS finebin_details CASCADE")
            print("✅ Dropped table: finebin_details")
        
        if check_table_exists(conn, 'records'):
            cur.execute("DROP TABLE IF EXISTS records CASCADE")
            print("✅ Dropped table: records")
        
        conn.commit()
        cur.close()
        return True
        
    except Exception as e:
        print(f"❌ Error dropping old tables: {e}")
        conn.rollback()
        return False


def main():
    parser = argparse.ArgumentParser(description='Validate and migrate database schema')
    parser.add_argument('--force-recreate', action='store_true',
                       help='Force recreation of schema (drops existing tables)')
    parser.add_argument('--backup-old', action='store_true',
                       help='Backup old data before any operations')
    parser.add_argument('--drop-old', action='store_true',
                       help='Drop old tables (records, finebin_details)')
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("Credit Scoring Database Schema Validation & Migration")
    print("=" * 60)
    
    # Connect to database
    try:
        conn = get_db_connection()
        print(f"\n✅ Connected to database successfully")
    except Exception as e:
        print(f"\n❌ Error connecting to database: {e}")
        print("\nPlease check your database connection settings in .env file:")
        print("  - DATABASE_URL or")
        print("  - PG_DBNAME, PG_USER, PG_PASSWORD, PG_HOST, PG_PORT")
        sys.exit(1)
    
    # Backup old data if requested
    if args.backup_old:
        if not backup_old_data(conn):
            print("\n⚠️  Backup failed. Continuing anyway...")
    
    # Validate current schema
    is_valid, missing_tables, incorrect_tables, old_tables = validate_schema(conn)
    
    if is_valid and not old_tables:
        print("\n" + "=" * 60)
        print("✅ Database schema is CORRECT and UP TO DATE!")
        print("=" * 60)
        conn.close()
        return 0
    
    # Determine what needs to be done
    if args.force_recreate:
        print("\n⚠️  Force recreate mode enabled")
        
        # Drop all tables (new and old)
        try:
            cur = conn.cursor()
            cur.execute("""
                DROP TABLE IF EXISTS merged_bins CASCADE;
                DROP TABLE IF EXISTS bins CASCADE;
                DROP TABLE IF EXISTS binning_steps CASCADE;
                DROP TABLE IF EXISTS features CASCADE;
                DROP TABLE IF EXISTS datasets CASCADE;
                DROP TABLE IF EXISTS finebin_details CASCADE;
                DROP TABLE IF EXISTS records CASCADE;
            """)
            conn.commit()
            cur.close()
            print("✅ Dropped all existing tables")
        except Exception as e:
            print(f"❌ Error dropping tables: {e}")
            conn.rollback()
            conn.close()
            return 1
        
        # Create new schema
        if create_new_schema(conn):
            print("\n" + "=" * 60)
            print("✅ Schema recreated successfully!")
            print("=" * 60)
            conn.close()
            return 0
        else:
            conn.close()
            return 1
    
    elif missing_tables and not incorrect_tables:
        # Only missing tables, can create them
        print("\n=== Recommendation ===")
        print("Some tables are missing. Creating new schema...")
        
        if create_new_schema(conn):
            if old_tables and args.drop_old:
                drop_old_tables(conn)
            
            print("\n" + "=" * 60)
            print("✅ Schema created successfully!")
            print("=" * 60)
            conn.close()
            return 0
        else:
            conn.close()
            return 1
    
    else:
        # Tables exist but are incorrect
        print("\n" + "=" * 60)
        print("⚠️  SCHEMA MISMATCH DETECTED")
        print("=" * 60)
        
        if incorrect_tables:
            print("\nThe following tables have incorrect structure:")
            for table, issues in incorrect_tables.items():
                print(f"  - {table}")
        
        if old_tables:
            print("\nThe following old tables should be removed:")
            for table in old_tables:
                print(f"  - {table}")
        
        print("\n=== MANUAL ACTION REQUIRED ===\n")
        print("To fix the schema, run ONE of the following commands:\n")
        print("1. Drop and recreate (DESTRUCTIVE - will lose all data):")
        print("   python validate_and_migrate_schema.py --force-recreate\n")
        print("2. Backup old data first, then recreate:")
        print("   python validate_and_migrate_schema.py --backup-old --force-recreate\n")
        print("3. Just drop old tables and keep new structure:")
        print("   python validate_and_migrate_schema.py --drop-old\n")
        
        if args.drop_old and old_tables:
            if drop_old_tables(conn):
                print("\n✅ Old tables dropped successfully")
                # Re-validate
                is_valid, _, _, _ = validate_schema(conn)
                if is_valid:
                    print("\n✅ Schema is now correct!")
                    conn.close()
                    return 0
        
        conn.close()
        return 1


if __name__ == '__main__':
    sys.exit(main())
