#!/usr/bin/env python3
"""
Quick verification script to test the new database schema integration.
Run this after setup_database.sh to verify everything is working.
"""

import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_import():
    """Test that db.py can be imported"""
    try:
        import db
        print("✅ db.py imported successfully")
        return True
    except Exception as e:
        print(f"❌ Failed to import db.py: {e}")
        return False

def test_connection():
    """Test database connection"""
    try:
        from db import get_db_connection
        conn = get_db_connection()
        conn.close()
        print("✅ Database connection successful")
        return True
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return False

def test_schema():
    """Test that all tables exist"""
    try:
        from db import get_db_connection
        conn = get_db_connection()
        cur = conn.cursor()
        
        tables = ['datasets', 'features', 'binning_steps', 'bins', 'merged_bins', 'binning_totals']
        for table in tables:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            cur.fetchone()
            print(f"✅ Table '{table}' exists")
        
        conn.close()
        return True
    except Exception as e:
        print(f"❌ Schema verification failed: {e}")
        return False

def test_crud_operations():
    """Test basic CRUD operations"""
    try:
        from db import (
            create_dataset, get_dataset, delete_dataset,
            create_features_batch, get_features_by_dataset
        )
        
        # Create test dataset
        dataset_id = create_dataset(
            name="test_dataset",
            file_path="/tmp/test.csv",
            total_features=2,
            discrete_features=1,
            continuous_features=1,
            target_variable="target"
        )
        print(f"✅ Created test dataset (ID: {dataset_id})")
        
        # Read dataset
        dataset = get_dataset(dataset_id)
        assert dataset['name'] == "test_dataset"
        print("✅ Retrieved dataset successfully")
        
        # Create features
        features_data = [
            {'name': 'age', 'type': 'continuous', 'selected': False},
            {'name': 'gender', 'type': 'discrete', 'selected': False}
        ]
        feature_ids = create_features_batch(dataset_id, features_data)
        print(f"✅ Created {len(feature_ids)} features")
        
        # Read features
        features = get_features_by_dataset(dataset_id)
        assert len(features) == 2
        print("✅ Retrieved features successfully")
        
        # Delete dataset (cascade should delete features too)
        delete_dataset(dataset_id)
        print("✅ Deleted test dataset (cascade delete)")
        
        return True
    except Exception as e:
        print(f"❌ CRUD operations failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_binning_operations():
    """Test binning-related operations"""
    try:
        from db import (
            create_dataset, create_features_batch,
            create_binning_step, create_bins_batch, create_binning_totals,
            get_bins_by_step, get_binning_totals,
            delete_dataset
        )
        
        # Create test data
        dataset_id = create_dataset(
            name="test_binning",
            file_path="/tmp/test.csv",
            total_features=1,
            discrete_features=0,
            continuous_features=1,
            target_variable="target"
        )
        
        features_data = [{'name': 'age', 'type': 'continuous', 'selected': True}]
        feature_ids = create_features_batch(dataset_id, features_data)
        feature_id = feature_ids[0]
        
        # Create binning step
        step_id = create_binning_step(
            feature_id=feature_id,
            step_type='coarse',
            method='qcut',
            num_bins=3,
            is_monotonic=False,
            monotonic_direction=None,
            iv_value=0.123
        )
        print(f"✅ Created binning step (ID: {step_id})")
        
        # Create bins
        bins_data = [
            {
                'bin_number': 1,
                'bin_label': 'Bin_1',
                'min_value': 18.0,
                'max_value': 30.0,
                'good_count': 100,
                'bad_count': 20,
                'total_count': 120,
                'woe': 0.12,
                'iv': 0.004
            },
            {
                'bin_number': 2,
                'bin_label': 'Bin_2',
                'min_value': 30.0,
                'max_value': 50.0,
                'good_count': 150,
                'bad_count': 30,
                'total_count': 180,
                'woe': 0.15,
                'iv': 0.005
            }
        ]
        bin_ids = create_bins_batch(step_id, bins_data)
        print(f"✅ Created {len(bin_ids)} bins")
        
        # Create binning totals
        totals_id = create_binning_totals(
            binning_step_id=step_id,
            total_good=250,
            total_bad=50,
            total_count=300,
            good_bad_ratio=5.0,
            bad_rate=0.1667,
            freq_percent=100.0,
            iv=0.123
        )
        print(f"✅ Created binning totals (ID: {totals_id})")
        
        # Retrieve bins
        bins = get_bins_by_step(step_id)
        assert len(bins) == 2
        print("✅ Retrieved bins successfully")
        
        # Retrieve totals
        totals = get_binning_totals(step_id)
        assert totals['total_good'] == 250
        assert totals['total_bad'] == 50
        print("✅ Retrieved binning totals successfully")
        
        # Cleanup
        delete_dataset(dataset_id)
        print("✅ Cleaned up test data")
        
        return True
    except Exception as e:
        print(f"❌ Binning operations failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_api_endpoints():
    """Test that API endpoints are registered"""
    try:
        import api_endpoints_new
        print("✅ api_endpoints_new.py imported successfully")
        return True
    except Exception as e:
        print(f"❌ Failed to import api_endpoints_new.py: {e}")
        return False

def main():
    print("\n" + "="*60)
    print("DATABASE SCHEMA INTEGRATION VERIFICATION")
    print("="*60 + "\n")
    
    tests = [
        ("Import Check", test_import),
        ("Database Connection", test_connection),
        ("Schema Verification", test_schema),
        ("CRUD Operations", test_crud_operations),
        ("Binning Operations", test_binning_operations),
        ("API Endpoints", test_api_endpoints)
    ]
    
    results = []
    for test_name, test_func in tests:
        print(f"\n📋 Testing: {test_name}")
        print("-" * 60)
        result = test_func()
        results.append(result)
        print()
    
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    
    passed = sum(results)
    total = len(results)
    
    for i, (test_name, _) in enumerate(tests):
        status = "✅ PASS" if results[i] else "❌ FAIL"
        print(f"{status} - {test_name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed! The integration is ready to use.")
        print("\nNext steps:")
        print("1. Start the backend: python app.py")
        print("2. Test new endpoints with curl or Postman")
        print("3. Update frontend to use /api/v2/* endpoints")
        return 0
    else:
        print("\n⚠️  Some tests failed. Please check the errors above.")
        print("\nTroubleshooting:")
        print("1. Ensure PostgreSQL is running")
        print("2. Check .env file for correct database credentials")
        print("3. Run: ./setup_database.sh")
        return 1

if __name__ == '__main__':
    sys.exit(main())
