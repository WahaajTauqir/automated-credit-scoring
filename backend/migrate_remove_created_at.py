#!/usr/bin/env python3
"""
Migration script to remove created_at columns from all tables except datasets.
Run this script to update existing databases.
"""

import sys
from db import get_db_connection

def drop_created_at_columns():
    """Drop created_at columns from tables (except datasets)."""
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Tables to remove created_at from (excluding datasets)
        tables_to_update = [
            'features',
            'binning_steps',
            'bins',
            'merged_bins',
            'binning_totals'
        ]
        
        dropped_columns = []
        skipped_columns = []
        
        for table_name in tables_to_update:
            # Check if column exists
            cur.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_schema = 'public' 
                AND table_name = %s 
                AND column_name = 'created_at'
            """, (table_name,))
            
            if cur.fetchone():
                try:
                    print(f"Dropping created_at column from {table_name}...")
                    cur.execute(f"ALTER TABLE {table_name} DROP COLUMN IF EXISTS created_at")
                    conn.commit()
                    dropped_columns.append(table_name)
                    print(f"✅ Dropped created_at from {table_name}")
                except Exception as e:
                    conn.rollback()
                    print(f"⚠️  Could not drop created_at from {table_name}: {e}")
            else:
                skipped_columns.append(table_name)
                print(f"ℹ️  {table_name} does not have created_at column (already removed or never existed)")
        
        print(f"\n✅ Migration complete!")
        if dropped_columns:
            print(f"   Dropped created_at from: {', '.join(dropped_columns)}")
        if skipped_columns:
            print(f"   Skipped (no created_at): {', '.join(skipped_columns)}")
        
        return True
        
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"❌ Error during migration: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

if __name__ == '__main__':
    print("=" * 60)
    print("Migration: Remove created_at from all tables (except datasets)")
    print("=" * 60)
    print()
    
    if drop_created_at_columns():
        print("\n✅ Migration completed successfully!")
        sys.exit(0)
    else:
        print("\n❌ Migration failed!")
        sys.exit(1)

