#!/usr/bin/env python3
"""
Migration script to rename the 'datasets' table to 'records' in existing databases.
Run this script to update existing databases without losing data.
"""

import sys
from db import get_db_connection

def rename_datasets_to_records():
    """Rename the datasets table to records."""
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Check if datasets table exists
        cur.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name = 'datasets'
        """)
        
        if not cur.fetchone():
            print("ℹ️  'datasets' table does not exist. Nothing to migrate.")
            # Check if records table already exists
            cur.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'records'
            """)
            if cur.fetchone():
                print("✅ 'records' table already exists. Database is up to date.")
            else:
                print("⚠️  Neither 'datasets' nor 'records' table exists. Please run schema setup first.")
            return True
        
        # Check if records table already exists
        cur.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name = 'records'
        """)
        
        if cur.fetchone():
            print("⚠️  'records' table already exists. Cannot rename 'datasets' to 'records'.")
            print("   Please manually resolve this conflict before running the migration.")
            return False
        
        print("Renaming 'datasets' table to 'records'...")
        
        # Rename the table
        cur.execute("ALTER TABLE datasets RENAME TO records")
        conn.commit()
        
        # Rename the trigger
        cur.execute("""
            SELECT trigger_name 
            FROM information_schema.triggers 
            WHERE trigger_schema = 'public' 
            AND event_object_table = 'records'
            AND trigger_name LIKE '%datasets%'
        """)
        trigger_result = cur.fetchone()
        if trigger_result:
            old_trigger_name = trigger_result[0]
            new_trigger_name = old_trigger_name.replace('datasets', 'records')
            cur.execute(f"ALTER TRIGGER {old_trigger_name} ON records RENAME TO {new_trigger_name}")
            conn.commit()
            print(f"✅ Renamed trigger '{old_trigger_name}' to '{new_trigger_name}'")
        
        # Update the foreign key constraint name if it exists
        # PostgreSQL automatically updates FK constraint names, but we'll verify
        cur.execute("""
            SELECT constraint_name 
            FROM information_schema.table_constraints 
            WHERE table_schema = 'public' 
            AND table_name = 'features'
            AND constraint_type = 'FOREIGN KEY'
            AND constraint_name LIKE '%datasets%'
        """)
        fk_result = cur.fetchone()
        if fk_result:
            # The FK constraint name might reference datasets, but the actual reference
            # should be updated automatically. Let's verify the FK still works.
            cur.execute("""
                SELECT constraint_name 
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                    ON tc.constraint_name = kcu.constraint_name
                WHERE tc.table_schema = 'public' 
                AND tc.table_name = 'features'
                AND tc.constraint_type = 'FOREIGN KEY'
                AND kcu.referenced_table_name = 'records'
            """)
            if cur.fetchone():
                print("✅ Foreign key constraint updated successfully")
            else:
                print("⚠️  Warning: Could not verify foreign key constraint update")
        
        print("✅ Successfully renamed 'datasets' table to 'records'")
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
    print("Migration: Rename 'datasets' table to 'records'")
    print("=" * 60)
    print()
    
    if rename_datasets_to_records():
        print("\n✅ Migration completed successfully!")
        sys.exit(0)
    else:
        print("\n❌ Migration failed!")
        sys.exit(1)

