#!/usr/bin/env python3
"""
Clear Database Script

This script removes all data from the database tables while keeping the schema intact.
Useful for testing or resetting the application to a clean state.

Usage:
    python clear_database.py              # Interactive mode
    python clear_database.py --force      # Skip confirmation
    python clear_database.py --help       # Show help
"""

import sys
import os
import argparse

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from db import get_db_connection
except ImportError:
    print("❌ Error: Could not import database module")
    print("Please ensure db.py exists in the same directory")
    sys.exit(1)


def clear_all_data(force=False):
    """
    Clear all data from all tables in the correct order (respecting foreign keys).
    
    Args:
        force: If True, skip confirmation prompt
    
    Returns:
        bool: True if successful, False otherwise
    """
    
    # Tables in order (child tables first, then parent tables)
    tables = [
        'binning_totals',
        'merged_bins',
        'bins',
        'binning_steps',
        'features',
        'records'
    ]
    
    if not force:
        print("\n" + "="*60)
        print("⚠️  WARNING: DATABASE CLEAR OPERATION")
        print("="*60)
        print("\nThis will DELETE ALL DATA from the following tables:")
        for table in tables:
            print(f"  - {table}")
        print("\nThe table structure will remain intact.")
        print("This operation CANNOT be undone!")
        print("\n" + "="*60)
        
        confirm = input("\nType 'DELETE ALL DATA' to confirm: ")
        if confirm != "DELETE ALL DATA":
            print("\n❌ Operation cancelled. No changes were made.")
            return False
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        print("\n" + "="*60)
        print("CLEARING DATABASE")
        print("="*60 + "\n")
        
        # Get counts before deletion
        counts_before = {}
        for table in tables:
            try:
                cur.execute(f"SELECT COUNT(*) FROM {table}")
                counts_before[table] = cur.fetchone()[0]
            except Exception as e:
                counts_before[table] = 0
        
        # Delete data from tables in order
        for table in tables:
            try:
                cur.execute(f"TRUNCATE TABLE {table} CASCADE")
                print(f"✅ Cleared {table} ({counts_before[table]} rows deleted)")
            except Exception as e:
                print(f"⚠️  Warning: Could not clear {table}: {e}")
        
        # Commit changes
        conn.commit()
        
        # Verify all tables are empty
        print("\n" + "="*60)
        print("VERIFICATION")
        print("="*60 + "\n")
        
        all_empty = True
        for table in tables:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            count = cur.fetchone()[0]
            if count == 0:
                print(f"✅ {table}: 0 rows")
            else:
                print(f"❌ {table}: {count} rows (should be 0)")
                all_empty = False
        
        cur.close()
        conn.close()
        
        if all_empty:
            print("\n" + "="*60)
            print("✅ SUCCESS: All data cleared successfully!")
            print("="*60)
            print("\nThe database is now empty but the schema is intact.")
            print("You can start using the application from scratch.")
            return True
        else:
            print("\n" + "="*60)
            print("⚠️  WARNING: Some tables still contain data")
            print("="*60)
            return False
        
    except Exception as e:
        print(f"\n❌ Error clearing database: {e}")
        import traceback
        traceback.print_exc()
        return False


def show_database_stats():
    """Show current database statistics."""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        tables = ['records', 'features', 'binning_steps', 'bins', 'merged_bins', 'binning_totals']
        
        print("\n" + "="*60)
        print("CURRENT DATABASE STATISTICS")
        print("="*60 + "\n")
        
        total_rows = 0
        for table in tables:
            try:
                cur.execute(f"SELECT COUNT(*) FROM {table}")
                count = cur.fetchone()[0]
                total_rows += count
                print(f"  {table:20s} : {count:6d} rows")
            except Exception as e:
                print(f"  {table:20s} : Error ({e})")
        
        print("\n" + "-"*60)
        print(f"  {'TOTAL':20s} : {total_rows:6d} rows")
        print("="*60)
        
        cur.close()
        conn.close()
        
        return total_rows
        
    except Exception as e:
        print(f"\n❌ Error getting database stats: {e}")
        return -1


def clear_specific_dataset(dataset_id):
    """
    Clear data for a specific dataset only.
    
    Args:
        dataset_id: ID of the dataset to delete
    
    Returns:
        bool: True if successful
    """
    try:
        from db import delete_dataset
        
        print(f"\n🗑️  Deleting dataset {dataset_id} and all related data...")
        delete_dataset(dataset_id)
        print(f"✅ Dataset {dataset_id} deleted successfully (CASCADE)")
        return True
        
    except Exception as e:
        print(f"❌ Error deleting dataset {dataset_id}: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Clear all data from the credit scoring database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python clear_database.py                  # Interactive mode
  python clear_database.py --force          # Skip confirmation
  python clear_database.py --stats          # Show current statistics
  python clear_database.py --dataset 1      # Delete specific dataset only
        """
    )
    
    parser.add_argument('--force', action='store_true',
                        help='Skip confirmation prompt')
    parser.add_argument('--stats', action='store_true',
                        help='Show database statistics only (no deletion)')
    parser.add_argument('--dataset', type=int, metavar='ID',
                        help='Delete specific dataset only (by ID)')
    
    args = parser.parse_args()
    
    # Show stats mode
    if args.stats:
        total = show_database_stats()
        if total == 0:
            print("\n✅ Database is already empty")
        sys.exit(0)
    
    # Delete specific dataset
    if args.dataset:
        print("\n" + "="*60)
        print(f"DELETE DATASET {args.dataset}")
        print("="*60)
        
        if not args.force:
            confirm = input(f"\nDelete dataset {args.dataset} and all related data? (y/N): ")
            if confirm.lower() != 'y':
                print("❌ Cancelled")
                sys.exit(0)
        
        success = clear_specific_dataset(args.dataset)
        sys.exit(0 if success else 1)
    
    # Clear all data mode
    print("\n" + "="*60)
    print("DATABASE CLEAR TOOL")
    print("="*60)
    
    # Show current stats first
    total = show_database_stats()
    
    if total == 0:
        print("\n✅ Database is already empty. Nothing to clear.")
        sys.exit(0)
    
    # Proceed with clearing
    success = clear_all_data(force=args.force)
    
    if success:
        print("\n✅ Operation completed successfully")
        sys.exit(0)
    else:
        print("\n❌ Operation failed or was cancelled")
        sys.exit(1)


if __name__ == '__main__':
    main()
