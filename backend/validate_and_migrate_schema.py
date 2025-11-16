#!/usr/bin/env python3
"""
Database Schema Validation and Migration Script
Validates the database schema and applies migrations if needed.
"""

import os
import sys
import argparse
from db import get_db_connection, ensure_final_selected_column

def check_table_exists(cursor, table_name):
    """Check if a table exists in the database."""
    cursor.execute("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public' AND table_name = %s
    """, (table_name,))
    return cursor.fetchone() is not None

def check_column_exists(cursor, table_name, column_name):
    """Check if a column exists in a table."""
    cursor.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = %s AND column_name = %s
    """, (table_name, column_name))
    return cursor.fetchone() is not None

def validate_schema():
    """Validate that all required tables and columns exist."""
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        required_tables = [
            'datasets',
            'features',
            'binning_steps',
            'bins',
            'merged_bins',
            'binning_totals'
        ]
        
        missing_tables = []
        for table in required_tables:
            if not check_table_exists(cur, table):
                missing_tables.append(table)
        
        if missing_tables:
            print(f"❌ Missing tables: {', '.join(missing_tables)}")
            return False
        
        # Check for critical columns
        if not check_column_exists(cur, 'features', 'final_selected'):
            print("⚠️  Missing column: features.final_selected")
            return False
        
        if not check_column_exists(cur, 'features', 'model_ready'):
            print("⚠️  Missing column: features.model_ready")
            return False
        
        print("✅ All required tables and columns exist")
        return True
        
    except Exception as e:
        print(f"❌ Error validating schema: {e}")
        return False
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

def apply_migrations():
    """Apply any missing migrations."""
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Ensure final_selected column exists
        if not check_column_exists(cur, 'features', 'final_selected'):
            print("Adding missing final_selected column...")
            cur.execute("ALTER TABLE features ADD COLUMN final_selected BOOLEAN DEFAULT FALSE")
            conn.commit()
            print("✅ Added final_selected column")
        else:
            print("✅ final_selected column already exists")
        
        # Ensure model_ready column exists
        if not check_column_exists(cur, 'features', 'model_ready'):
            print("Adding missing model_ready column...")
            cur.execute("ALTER TABLE features ADD COLUMN model_ready BOOLEAN DEFAULT FALSE")
            conn.commit()
            print("✅ Added model_ready column")
        else:
            print("✅ model_ready column already exists")
        
        return True
        
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"❌ Error applying migrations: {e}")
        return False
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

def recreate_schema(backup=False):
    """Recreate the entire database schema from schema_new.sql."""
    schema_file = os.path.join(os.path.dirname(__file__), 'schema_new.sql')
    
    if not os.path.exists(schema_file):
        print(f"❌ Schema file not found: {schema_file}")
        return False
    
    conn = None
    cur = None
    try:
        # Read schema file
        with open(schema_file, 'r') as f:
            schema_sql = f.read()
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        if backup:
            print("⚠️  Backup functionality not implemented. Proceeding without backup...")
        
        print("Executing schema...")
        cur.execute(schema_sql)
        conn.commit()
        
        print("✅ Schema recreated successfully")
        return True
        
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"❌ Error recreating schema: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

def main():
    parser = argparse.ArgumentParser(description='Validate and migrate database schema')
    parser.add_argument('--force-recreate', action='store_true', 
                       help='Force recreate the entire schema (WARNING: DROPS ALL TABLES)')
    parser.add_argument('--backup-old', action='store_true',
                       help='Backup existing data before recreating (not implemented)')
    parser.add_argument('--migrate', action='store_true',
                       help='Apply migrations without recreating schema')
    
    args = parser.parse_args()
    
    if args.force_recreate:
        print("⚠️  WARNING: This will DROP all existing tables!")
        print("Recreating schema...")
        if recreate_schema(backup=args.backup_old):
            # Apply any additional migrations
            apply_migrations()
            return 0
        else:
            return 1
    
    if args.migrate:
        print("Applying migrations...")
        if apply_migrations():
            return 0
        else:
            return 1
    
    # Default: validate schema
    if validate_schema():
        return 0
    else:
        return 1

if __name__ == '__main__':
    sys.exit(main())

