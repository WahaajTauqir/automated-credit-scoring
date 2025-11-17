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
        WHERE table_schema = 'public' AND table_name = %s AND column_name = %s
    """, (table_name, column_name))
    return cursor.fetchone() is not None

def get_required_columns():
    """Return a dictionary of required columns for each table."""
    return {
        'datasets': [
            'id', 'name', 'file_path', 'total_features', 'discrete_features',
            'continuous_features', 'target_variable', 'created_at', 'updated_at',
            'identifier'
        ],
        'features': [
            'id', 'dataset_id', 'name', 'type', 'selected', 'model_ready',
            'final_selected', 'created_at'
        ],
        'binning_steps': [
            'id', 'feature_id', 'step_type', 'method', 'num_bins',
            'is_monotonic', 'monotonic_direction', 'iv_value', 'created_at'
        ],
        'bins': [
            'id', 'binning_step_id', 'bin_number', 'bin_label', 'min_value',
            'max_value', 'range_text', 'good_count', 'bad_count', 'total_count',
            'good_bad_ratio', 'bad_rate', 'freq_percent', 'odds', 'index_value',
            'odds_index', 'dist_good', 'dist_bad', 'woe', 'iv', 'created_at'
        ],
        'merged_bins': [
            'id', 'fine_step_id', 'merged_bin_number', 'original_bin_ids',
            'original_bin_labels', 'created_at'
        ],
        'binning_totals': [
            'id', 'binning_step_id', 'total_good', 'total_bad', 'total_count',
            'good_bad_ratio', 'bad_rate', 'freq_percent', 'iv', 'created_at'
        ]
    }

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
            return False, []
        
        # Check for all required columns
        required_columns = get_required_columns()
        missing_columns = []
        
        for table_name, columns in required_columns.items():
            if not check_table_exists(cur, table_name):
                continue  # Skip if table doesn't exist (already caught above)
            
            for column in columns:
                if not check_column_exists(cur, table_name, column):
                    missing_columns.append(f"{table_name}.{column}")
        
        if missing_columns:
            print(f"⚠️  Missing columns: {', '.join(missing_columns)}")
            return False, missing_columns
        
        print("✅ All required tables and columns exist")
        return True, []
        
    except Exception as e:
        print(f"❌ Error validating schema: {e}")
        import traceback
        traceback.print_exc()
        return False, []
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

def apply_migrations():
    """Apply any missing migrations - add missing columns to existing tables."""
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        required_columns = get_required_columns()
        columns_added = []
        columns_skipped = []
        
        # Column type mappings for ALTER TABLE statements
        column_definitions = {
            # datasets table
            'datasets.id': 'SERIAL PRIMARY KEY',  # This should already exist
            'datasets.name': 'TEXT NOT NULL',
            'datasets.file_path': 'TEXT',
            'datasets.total_features': 'INT',
            'datasets.discrete_features': 'INT',
            'datasets.continuous_features': 'INT',
            'datasets.target_variable': 'TEXT',
            'datasets.created_at': 'TIMESTAMP DEFAULT NOW()',
            'datasets.updated_at': 'TIMESTAMP DEFAULT NOW()',
            'datasets.identifier': 'TEXT',
            
            # features table
            'features.id': 'SERIAL PRIMARY KEY',  # This should already exist
            'features.dataset_id': 'INT NOT NULL REFERENCES datasets(id) ON DELETE CASCADE',
            'features.name': 'TEXT NOT NULL',
            'features.type': 'VARCHAR(20) NOT NULL',
            'features.selected': 'BOOLEAN DEFAULT FALSE',
            'features.model_ready': 'BOOLEAN DEFAULT FALSE',
            'features.final_selected': 'BOOLEAN DEFAULT FALSE',
            'features.created_at': 'TIMESTAMP DEFAULT NOW()',
            
            # binning_steps table
            'binning_steps.id': 'SERIAL PRIMARY KEY',
            'binning_steps.feature_id': 'INT NOT NULL REFERENCES features(id) ON DELETE CASCADE',
            'binning_steps.step_type': 'VARCHAR(20) NOT NULL',
            'binning_steps.method': 'VARCHAR(50)',
            'binning_steps.num_bins': 'INT',
            'binning_steps.is_monotonic': 'BOOLEAN DEFAULT FALSE',
            'binning_steps.monotonic_direction': 'VARCHAR(20)',
            'binning_steps.iv_value': 'NUMERIC(10, 6)',
            'binning_steps.created_at': 'TIMESTAMP DEFAULT NOW()',
            
            # bins table
            'bins.id': 'SERIAL PRIMARY KEY',
            'bins.binning_step_id': 'INT NOT NULL REFERENCES binning_steps(id) ON DELETE CASCADE',
            'bins.bin_number': 'INT NOT NULL',
            'bins.bin_label': 'TEXT',
            'bins.min_value': 'NUMERIC',
            'bins.max_value': 'NUMERIC',
            'bins.range_text': 'TEXT',
            'bins.good_count': 'INT NOT NULL DEFAULT 0',
            'bins.bad_count': 'INT NOT NULL DEFAULT 0',
            'bins.total_count': 'INT NOT NULL DEFAULT 0',
            'bins.good_bad_ratio': 'NUMERIC(10, 4)',
            'bins.bad_rate': 'NUMERIC(10, 4)',
            'bins.freq_percent': 'NUMERIC(10, 4)',
            'bins.odds': 'NUMERIC(10, 4)',
            'bins.index_value': 'NUMERIC(10, 4)',
            'bins.odds_index': 'NUMERIC(10, 4)',
            'bins.dist_good': 'NUMERIC(10, 4)',
            'bins.dist_bad': 'NUMERIC(10, 4)',
            'bins.woe': 'NUMERIC(10, 4)',
            'bins.iv': 'NUMERIC(10, 6)',
            'bins.created_at': 'TIMESTAMP DEFAULT NOW()',
            
            # merged_bins table
            'merged_bins.id': 'SERIAL PRIMARY KEY',
            'merged_bins.fine_step_id': 'INT NOT NULL REFERENCES binning_steps(id) ON DELETE CASCADE',
            'merged_bins.merged_bin_number': 'INT NOT NULL',
            'merged_bins.original_bin_ids': 'INT[] NOT NULL',
            'merged_bins.original_bin_labels': 'TEXT[] NOT NULL',
            'merged_bins.created_at': 'TIMESTAMP DEFAULT NOW()',
            
            # binning_totals table
            'binning_totals.id': 'SERIAL PRIMARY KEY',
            'binning_totals.binning_step_id': 'INT NOT NULL REFERENCES binning_steps(id) ON DELETE CASCADE',
            'binning_totals.total_good': 'INT NOT NULL DEFAULT 0',
            'binning_totals.total_bad': 'INT NOT NULL DEFAULT 0',
            'binning_totals.total_count': 'INT NOT NULL DEFAULT 0',
            'binning_totals.good_bad_ratio': 'NUMERIC(10, 4)',
            'binning_totals.bad_rate': 'NUMERIC(10, 4)',
            'binning_totals.freq_percent': 'NUMERIC(10, 4) DEFAULT 100.0',
            'binning_totals.iv': 'NUMERIC(10, 6)',
            'binning_totals.created_at': 'TIMESTAMP DEFAULT NOW()',
        }
        
        for table_name, columns in required_columns.items():
            if not check_table_exists(cur, table_name):
                print(f"⚠️  Table {table_name} does not exist. Skipping column migrations.")
                continue
            
            for column in columns:
                column_key = f"{table_name}.{column}"
                
                # Skip primary key columns (id) - they should already exist
                if column == 'id':
                    continue
                
                if not check_column_exists(cur, table_name, column):
                    col_def = column_definitions.get(column_key, None)
                    if col_def:
                        # Simplify column definition for ALTER TABLE (remove constraints that might conflict)
                        # Extract just the type and default
                        if 'PRIMARY KEY' in col_def or 'REFERENCES' in col_def or 'NOT NULL' in col_def:
                            # For columns with constraints, extract just the base type
                            if '[]' in col_def:  # Array types (INT[], TEXT[])
                                # For arrays, remove NOT NULL (can't add NOT NULL to existing table without default)
                                # Use empty array as default if needed
                                if 'INT[]' in col_def:
                                    simple_def = 'INT[] DEFAULT ARRAY[]::INT[]'
                                elif 'TEXT[]' in col_def:
                                    simple_def = 'TEXT[] DEFAULT ARRAY[]::TEXT[]'
                                else:
                                    simple_def = col_def.replace(' NOT NULL', '').replace('NOT NULL ', '')
                            elif 'BOOLEAN' in col_def:
                                simple_def = 'BOOLEAN DEFAULT FALSE' if 'DEFAULT FALSE' in col_def else 'BOOLEAN'
                            elif 'TEXT' in col_def:
                                simple_def = 'TEXT'
                            elif 'INT' in col_def:
                                simple_def = 'INT DEFAULT 0' if 'DEFAULT 0' in col_def else 'INT'
                            elif 'NUMERIC' in col_def:
                                simple_def = col_def.split('DEFAULT')[0].strip() if 'DEFAULT' in col_def else col_def.split('NOT NULL')[0].strip()
                            elif 'TIMESTAMP' in col_def:
                                simple_def = 'TIMESTAMP DEFAULT NOW()'
                            elif 'VARCHAR' in col_def:
                                simple_def = col_def.split('NOT NULL')[0].strip()
                            else:
                                simple_def = col_def.split('NOT NULL')[0].split('DEFAULT')[0].strip()
                        else:
                            simple_def = col_def
                        
                        try:
                            print(f"Adding missing column {column_key}...")
                            cur.execute(f"ALTER TABLE {table_name} ADD COLUMN {column} {simple_def}")
                            conn.commit()
                            columns_added.append(column_key)
                            print(f"✅ Added {column_key}")
                        except Exception as col_error:
                            conn.rollback()
                            print(f"⚠️  Could not add {column_key}: {col_error}")
                            print(f"   This column may need manual intervention.")
                    else:
                        print(f"⚠️  No definition found for {column_key}, skipping...")
                else:
                    columns_skipped.append(column_key)
        
        if columns_added:
            print(f"\n✅ Successfully added {len(columns_added)} missing column(s)")
        if columns_skipped:
            print(f"✅ Verified {len(columns_skipped)} existing column(s)")
        
        # Return True if migrations completed successfully (even if no columns were added)
        return True
        
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"❌ Error applying migrations: {e}")
        import traceback
        traceback.print_exc()
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
    is_valid, missing_columns = validate_schema()
    if is_valid:
        return 0
    else:
        # If validation failed but tables exist, try applying migrations
        if missing_columns:
            print("\nAttempting to apply migrations to fix missing columns...")
            print("-------------------------------------------")
            if apply_migrations():
                print("\nRe-validating schema after migrations...")
                is_valid_after, _ = validate_schema()
                if is_valid_after:
                    print("\n✅ Schema is now valid after migrations!")
                    return 0
                else:
                    print("\n⚠️  Schema still has issues after migrations.")
                    print("You may need to recreate the schema with --force-recreate")
                    return 1
            else:
                print("\n⚠️  Migrations could not be applied automatically.")
                print("You may need to recreate the schema with --force-recreate")
                return 1
        else:
            # Missing tables - need to recreate
            return 1

if __name__ == '__main__':
    sys.exit(main())

