"""
Database Migration: Add Train/Test Split Columns

This script adds the train/test split metadata columns to the records table.
Run this once to update your existing database.

Usage:
    python migrate_add_train_test_split.py
"""

import psycopg2
import os
from db import get_db_connection


def add_train_test_split_columns():
    """Add train/test split columns to records table."""
    
    print("=" * 60)
    print("TRAIN/TEST SPLIT COLUMNS MIGRATION")
    print("=" * 60)
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        print("\nAdding train/test split columns to records table...")
        
        # Add columns one by one with IF NOT EXISTS
        columns_to_add = [
            ("train_test_split_seed", "INTEGER"),
            ("train_test_split_size", "NUMERIC(5, 3)"),
            ("train_test_split_method", "VARCHAR(50)"),
            ("train_size", "INTEGER"),
            ("test_size", "INTEGER"),
            ("train_bad_count", "INTEGER"),
            ("test_bad_count", "INTEGER"),
            ("split_created_at", "TIMESTAMP"),
            ("data_hash", "VARCHAR(64)")
        ]
        
        for col_name, col_type in columns_to_add:
            try:
                cur.execute(f"""
                    ALTER TABLE records 
                    ADD COLUMN IF NOT EXISTS {col_name} {col_type};
                """)
                print(f"  ✓ Added column: {col_name}")
            except Exception as e:
                print(f"  ⚠️  Column {col_name} may already exist: {e}")
        
        conn.commit()
        
        # Add comments
        print("\nAdding column comments...")
        comments = [
            ("train_test_split_seed", "Random seed used for train/test split (for reproducibility)"),
            ("train_test_split_size", "Proportion of data allocated to test set (e.g., 0.200 for 20%)"),
            ("train_test_split_method", "Method used for split (stratified, random, time_based)"),
            ("train_size", "Number of rows in training set"),
            ("test_size", "Number of rows in test set"),
            ("train_bad_count", "Number of bad cases (target=1) in training set"),
            ("test_bad_count", "Number of bad cases (target=1) in test set"),
            ("split_created_at", "Timestamp when train/test split was created"),
            ("data_hash", "Hash of data to detect changes requiring new split")
        ]
        
        for col_name, comment in comments:
            try:
                cur.execute(f"""
                    COMMENT ON COLUMN records.{col_name} IS %s;
                """, (comment,))
                print(f"  ✓ Added comment for: {col_name}")
            except Exception as e:
                print(f"  ⚠️  Could not add comment for {col_name}: {e}")
        
        conn.commit()
        
        # Verify columns exist
        print("\nVerifying columns...")
        cur.execute("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'records' 
            AND column_name LIKE 'train%' OR column_name = 'data_hash'
            ORDER BY column_name;
        """)
        
        columns = cur.fetchall()
        if columns:
            print("\nColumns successfully added:")
            for col_name, col_type in columns:
                print(f"  - {col_name}: {col_type}")
        else:
            print("\n⚠️  Warning: Could not verify columns. They may already exist.")
        
        print("\n" + "=" * 60)
        print("MIGRATION COMPLETED SUCCESSFULLY!")
        print("=" * 60)
        print("\nNext steps:")
        print("1. Create train/test split: POST /api/train-test-split")
        print("2. The split will be created automatically after variable classification")
        print("3. All binning and training will use train set only")
        
        return True
        
    except Exception as e:
        conn.rollback()
        print(f"\n❌ ERROR during migration: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    success = add_train_test_split_columns()
    exit(0 if success else 1)

