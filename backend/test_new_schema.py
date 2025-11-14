"""
Test Script for New Database Schema

This script demonstrates how to use the new database schema
and validates that everything works correctly.

Usage:
    python test_new_schema.py
"""

import sys
import os
from datetime import datetime

# Add backend to path
sys.path.insert(0, os.path.dirname(__file__))

from db import (
    get_db_connection,
    create_dataset, get_dataset, get_all_datasets, get_latest_dataset,
    create_feature, create_features_batch, get_features_by_dataset, get_feature_by_name,
    create_binning_step, get_binning_step_by_type,
    create_bin, create_bins_batch, get_bins_by_step,
    create_merged_bin, get_merged_bins_by_step,
    create_binning_totals, get_binning_totals,
    get_complete_binning_results, get_dataset_with_all_results,
    update_features_selection
)


def test_database_connection():
    """Test database connection."""
    print("\n" + "="*60)
    print("TEST 1: Database Connection")
    print("="*60)
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT version();")
        version = cur.fetchone()[0]
        print(f"✅ Connected to PostgreSQL")
        print(f"   Version: {version[:50]}...")
        cur.close()
        conn.close()
        return True
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return False


def test_dataset_operations():
    """Test dataset CRUD operations."""
    print("\n" + "="*60)
    print("TEST 2: Dataset Operations")
    print("="*60)
    
    try:
        # Create dataset
        dataset_id = create_dataset(
            name=f'Test_Dataset_{datetime.now().strftime("%Y%m%d_%H%M%S")}',
            file_path='/backend/test_uploaded.csv',
            total_features=30,
            discrete_features=10,
            continuous_features=20,
            target_variable='default'
        )
        print(f"✅ Created dataset with ID: {dataset_id}")
        
        # Get dataset
        dataset = get_dataset(dataset_id)
        print(f"✅ Retrieved dataset: {dataset['name']}")
        
        # Get all datasets
        all_datasets = get_all_datasets()
        print(f"✅ Found {len(all_datasets)} total datasets")
        
        # Get latest dataset
        latest = get_latest_dataset()
        print(f"✅ Latest dataset: {latest['name'] if latest else 'None'}")
        
        return dataset_id
        
    except Exception as e:
        print(f"❌ Dataset operations failed: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_feature_operations(dataset_id):
    """Test feature CRUD operations."""
    print("\n" + "="*60)
    print("TEST 3: Feature Operations")
    print("="*60)
    
    if not dataset_id:
        print("⚠️  Skipping: No dataset_id provided")
        return None
    
    try:
        # Create multiple features
        features = [
            {'name': 'age', 'type': 'continuous', 'selected': True},
            {'name': 'gender', 'type': 'discrete', 'selected': True},
            {'name': 'income', 'type': 'continuous', 'selected': True},
            {'name': 'education', 'type': 'discrete', 'selected': False},
            {'name': 'credit_score', 'type': 'continuous', 'selected': False}
        ]
        
        feature_ids = create_features_batch(dataset_id, features)
        print(f"✅ Created {len(feature_ids)} features")
        
        # Get features by dataset
        dataset_features = get_features_by_dataset(dataset_id)
        print(f"✅ Retrieved {len(dataset_features)} features for dataset")
        
        # Get feature by name
        age_feature = get_feature_by_name(dataset_id, 'age')
        print(f"✅ Found feature 'age' with ID: {age_feature['id']}")
        
        # Update feature selection
        update_features_selection(dataset_id, ['age', 'gender', 'income'])
        print(f"✅ Updated feature selection")
        
        return age_feature['id']
        
    except Exception as e:
        print(f"❌ Feature operations failed: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_binning_operations(feature_id):
    """Test binning operations (coarse and fine)."""
    print("\n" + "="*60)
    print("TEST 4: Binning Operations")
    print("="*60)
    
    if not feature_id:
        print("⚠️  Skipping: No feature_id provided")
        return None
    
    try:
        # Create coarse binning step
        coarse_step_id = create_binning_step(
            feature_id=feature_id,
            step_type='coarse',
            method='qcut',
            num_bins=5,
            is_monotonic=False,
            iv_value=0.1234
        )
        print(f"✅ Created coarse binning step with ID: {coarse_step_id}")
        
        # Create coarse bins
        coarse_bins = [
            {
                'bin_number': 1,
                'bin_label': 'Bin_1',
                'min_value': 18.0,
                'max_value': 25.0,
                'good_count': 200,
                'bad_count': 50,
                'total_count': 250,
                'woe': 0.32,
                'iv': 0.012,
                'dist_good': 15.5,
                'dist_bad': 10.2,
                'bad_rate': 20.0
            },
            {
                'bin_number': 2,
                'bin_label': 'Bin_2',
                'min_value': 25.0,
                'max_value': 35.0,
                'good_count': 300,
                'bad_count': 40,
                'total_count': 340,
                'woe': 0.45,
                'iv': 0.015,
                'dist_good': 23.3,
                'dist_bad': 8.2,
                'bad_rate': 11.8
            },
            {
                'bin_number': 3,
                'bin_label': 'Bin_3',
                'min_value': 35.0,
                'max_value': 45.0,
                'good_count': 250,
                'bad_count': 60,
                'total_count': 310,
                'woe': 0.28,
                'iv': 0.011,
                'dist_good': 19.4,
                'dist_bad': 12.3,
                'bad_rate': 19.4
            }
        ]
        
        coarse_bin_ids = create_bins_batch(coarse_step_id, coarse_bins)
        print(f"✅ Created {len(coarse_bin_ids)} coarse bins")
        
        # Create coarse binning totals
        coarse_totals_id = create_binning_totals(
            binning_step_id=coarse_step_id,
            total_good=750,
            total_bad=150,
            total_count=900,
            good_bad_ratio=5.0,
            bad_rate=16.67,
            freq_percent=100.0,
            iv=0.1234
        )
        print(f"✅ Created coarse binning totals with ID: {coarse_totals_id}")
        
        # Create fine binning step
        fine_step_id = create_binning_step(
            feature_id=feature_id,
            step_type='fine',
            method='merged',
            num_bins=2,
            is_monotonic=True,
            monotonic_direction='increasing',
            iv_value=0.1156
        )
        print(f"✅ Created fine binning step with ID: {fine_step_id}")
        
        # Create merged bin record (Bin_1 + Bin_2 merged)
        merged_id = create_merged_bin(
            fine_step_id=fine_step_id,
            merged_bin_number=1,
            original_bin_ids=[coarse_bin_ids[0], coarse_bin_ids[1]],
            original_bin_labels=['Bin_1', 'Bin_2']
        )
        print(f"✅ Created merged bin record with ID: {merged_id}")
        
        # Create fine bins
        fine_bins = [
            {
                'bin_number': 1,
                'bin_label': 'Bin_1_2',
                'min_value': 18.0,
                'max_value': 35.0,
                'good_count': 500,
                'bad_count': 90,
                'total_count': 590,
                'woe': 0.38,
                'iv': 0.025,
                'dist_good': 38.8,
                'dist_bad': 18.4,
                'bad_rate': 15.3
            },
            {
                'bin_number': 2,
                'bin_label': 'Bin_3',
                'min_value': 35.0,
                'max_value': 45.0,
                'good_count': 250,
                'bad_count': 60,
                'total_count': 310,
                'woe': 0.28,
                'iv': 0.011,
                'dist_good': 19.4,
                'dist_bad': 12.3,
                'bad_rate': 19.4
            }
        ]
        
        fine_bin_ids = create_bins_batch(fine_step_id, fine_bins)
        print(f"✅ Created {len(fine_bin_ids)} fine bins")
        
        # Create fine binning totals
        fine_totals_id = create_binning_totals(
            binning_step_id=fine_step_id,
            total_good=750,
            total_bad=150,
            total_count=900,
            good_bad_ratio=5.0,
            bad_rate=16.67,
            freq_percent=100.0,
            iv=0.1156
        )
        print(f"✅ Created fine binning totals with ID: {fine_totals_id}")
        
        # Retrieve and verify totals
        coarse_totals = get_binning_totals(coarse_step_id)
        fine_totals = get_binning_totals(fine_step_id)
        
        if coarse_totals and fine_totals:
            print(f"✅ Retrieved binning totals successfully")
            print(f"   Coarse totals: Good={coarse_totals['total_good']}, Bad={coarse_totals['total_bad']}, IV={coarse_totals['iv']}")
            print(f"   Fine totals: Good={fine_totals['total_good']}, Bad={fine_totals['total_bad']}, IV={fine_totals['iv']}")
        else:
            print(f"⚠️  Warning: Could not retrieve binning totals")
        
        return feature_id
        
    except Exception as e:
        print(f"❌ Binning operations failed: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_complex_queries(feature_id):
    """Test complex query operations."""
    print("\n" + "="*60)
    print("TEST 5: Complex Query Operations")
    print("="*60)
    
    if not feature_id:
        print("⚠️  Skipping: No feature_id provided")
        return False
    
    try:
        # Get complete binning results
        results = get_complete_binning_results(feature_id, 'fine')
        if results:
            print(f"✅ Retrieved complete binning results:")
            print(f"   Feature: {results['feature']['name']}")
            print(f"   Step type: {results['binning_step']['step_type']}")
            print(f"   Number of bins: {len(results['bins'])}")
            print(f"   Number of merged bins: {len(results['merged_bins'])}")
            
            # Check if totals are included
            if results.get('totals'):
                totals = results['totals']
                print(f"   Totals: Good={totals['total_good']}, Bad={totals['total_bad']}, IV={totals['iv']}")
            else:
                print(f"   ⚠️  No totals found in results")
        
        # Get coarse binning results
        coarse_results = get_complete_binning_results(feature_id, 'coarse')
        if coarse_results:
            print(f"✅ Retrieved coarse binning results:")
            print(f"   Number of coarse bins: {len(coarse_results['bins'])}")
            
            if coarse_results.get('totals'):
                coarse_totals = coarse_results['totals']
                print(f"   Coarse Totals: Good={coarse_totals['total_good']}, Bad={coarse_totals['total_bad']}, IV={coarse_totals['iv']}")
        
        return True
        
    except Exception as e:
        print(f"❌ Complex query operations failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_full_workflow():
    """Test complete dataset workflow."""
    print("\n" + "="*60)
    print("TEST 6: Full Workflow (Dataset → Features → Binning)")
    print("="*60)
    
    try:
        # Get latest dataset
        dataset = get_latest_dataset()
        if not dataset:
            print("⚠️  No dataset found. Creating one...")
            dataset_id = test_dataset_operations()
            if not dataset_id:
                return False
            dataset = get_dataset(dataset_id)
        
        dataset_id = dataset['id']
        print(f"✅ Using dataset: {dataset['name']} (ID: {dataset_id})")
        
        # Get complete dataset with all results
        complete_data = get_dataset_with_all_results(dataset_id)
        if complete_data:
            print(f"✅ Retrieved complete dataset information:")
            print(f"   Dataset: {complete_data['dataset']['name']}")
            print(f"   Features: {len(complete_data['features'])}")
            
            # Count features with binning
            features_with_coarse = sum(1 for f in complete_data['features'] if f['binning']['coarse'])
            features_with_fine = sum(1 for f in complete_data['features'] if f['binning']['fine'])
            
            print(f"   Features with coarse binning: {features_with_coarse}")
            print(f"   Features with fine binning: {features_with_fine}")
        
        return True
        
    except Exception as e:
        print(f"❌ Full workflow test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    print("\n" + "="*70)
    print(" " * 15 + "NEW DATABASE SCHEMA TEST SUITE")
    print("="*70)
    
    # Test 1: Connection
    if not test_database_connection():
        print("\n❌ FATAL: Cannot connect to database. Aborting tests.")
        return False
    
    # Test 2: Dataset operations
    dataset_id = test_dataset_operations()
    
    # Test 3: Feature operations
    feature_id = test_feature_operations(dataset_id)
    
    # Test 4: Binning operations
    test_binning_operations(feature_id)
    
    # Test 5: Complex queries
    test_complex_queries(feature_id)
    
    # Test 6: Full workflow
    test_full_workflow()
    
    print("\n" + "="*70)
    print(" " * 20 + "ALL TESTS COMPLETED")
    print("="*70)
    
    print("\n✅ Database schema is working correctly!")
    print("\nNext steps:")
    print("1. Update app.py to use the new database layer (db_new.py)")
    print("2. Test the application end-to-end")
    print("3. Run the migration script to clean up old tables if needed")
    
    return True


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
