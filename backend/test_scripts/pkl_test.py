#!/usr/bin/env python3
"""
Script to read and inspect model artifact pickle files.
Usage: python inspect_artifact.py <artifact_path>
Example: python inspect_artifact.py artifacts/297_stacking_ensemble.pkl
"""

import pickle
import json
import sys
import os
from typing import Any, Dict

def inspect_artifact(artifact_path: str):
    """Load and inspect a model artifact pickle file."""
    
    if not os.path.exists(artifact_path):
        print(f"❌ Error: File not found: {artifact_path}")
        return
    
    print("=" * 80)
    print("MODEL ARTIFACT INSPECTOR")
    print("=" * 80)
    print(f"\n📁 File: {artifact_path}")
    file_size = os.path.getsize(artifact_path) / (1024 * 1024)  # Size in MB
    print(f"📊 File Size: {file_size:.2f} MB")
    
    try:
        with open(artifact_path, 'rb') as f:
            artifact = pickle.load(f)
        
        print(f"\n✅ Successfully loaded artifact")
        print(f"📋 Total Keys: {len(artifact.keys())}")
        print(f"\n🔑 All Keys:")
        for i, key in enumerate(sorted(artifact.keys()), 1):
            value = artifact[key]
            if isinstance(value, (bytes, bytearray)):
                print(f"  {i:2d}. {key:30s} → <binary data, {len(value)} bytes>")
            elif isinstance(value, (list, dict)):
                print(f"  {i:2d}. {key:30s} → <{type(value).__name__}, {len(value)} items>")
            else:
                print(f"  {i:2d}. {key:30s} → {type(value).__name__}")
        
        # ========== METADATA ==========
        print(f"\n{'='*80}")
        print("📝 METADATA")
        print(f"{'='*80}")
        print(f"Dataset ID:      {artifact.get('dataset_id', 'N/A')}")
        print(f"Model Label:     {artifact.get('model_label', 'N/A')}")
        print(f"Model Type:      {artifact.get('model_type', 'N/A')}")
        print(f"Saved At:        {artifact.get('saved_at', 'N/A')}")
        print(f"Target:          {artifact.get('target', 'N/A')}")
        
        # ========== VARIABLES ==========
        print(f"\n{'='*80}")
        print("📊 VARIABLES")
        print(f"{'='*80}")
        selected_vars = artifact.get('selected_variables', [])
        model_vars = artifact.get('model_variables', [])
        print(f"Selected Variables: {len(selected_vars)}")
        if selected_vars:
            print(f"  {', '.join(selected_vars[:10])}")
            if len(selected_vars) > 10:
                print(f"  ... and {len(selected_vars) - 10} more")
        print(f"Model Variables: {len(model_vars)}")
        
        # ========== SCORECARD PARAMETERS ==========
        print(f"\n{'='*80}")
        print("🎯 SCORECARD PARAMETERS")
        print(f"{'='*80}")
        score_params = artifact.get('score_parameters', {})
        if score_params:
            print(json.dumps(score_params, indent=2))
        else:
            print("  ⚠️  No score_parameters found")
        
        # ========== SCORECARD BINS ==========
        print(f"\n{'='*80}")
        print("📦 SCORECARD BINS")
        print(f"{'='*80}")
        scorecard_bins = artifact.get('scorecard_bins', [])
        if scorecard_bins:
            print(f"Total Bins: {len(scorecard_bins)}")
            print(f"\nFirst 5 bins:")
            for i, bin_data in enumerate(scorecard_bins[:5], 1):
                print(f"  {i}. {bin_data.get('variable', 'N/A')}: {bin_data.get('bin_range', 'N/A')}")
                print(f"     WOE: {bin_data.get('woe', 'N/A')}, Score: {bin_data.get('score', 'N/A')}")
            
            if len(scorecard_bins) > 5:
                print(f"  ... and {len(scorecard_bins) - 5} more bins")
            
            # Group by variable
            vars_bins = {}
            for bin_data in scorecard_bins:
                var = bin_data.get('variable', 'unknown')
                if var not in vars_bins:
                    vars_bins[var] = 0
                vars_bins[var] += 1
            
            print(f"\nBins per variable:")
            for var, count in sorted(vars_bins.items()):
                print(f"  {var:30s}: {count} bins")
        else:
            print("  ⚠️  No scorecard_bins found")
        
        # ========== WOE DATA ==========
        print(f"\n{'='*80}")
        print("📈 WOE TRANSFORMED DATA")
        print(f"{'='*80}")
        woe_data = artifact.get('woe_transformed_data', {})
        if woe_data:
            print(f"Variables with WOE data: {len(woe_data)}")
            for var, bins in list(woe_data.items())[:3]:
                if isinstance(bins, list):
                    print(f"  {var}: {len(bins)} bins")
                else:
                    print(f"  {var}: {type(bins).__name__}")
            if len(woe_data) > 3:
                print(f"  ... and {len(woe_data) - 3} more variables")
        else:
            print("  ⚠️  No woe_transformed_data found")
        
        # ========== MODEL DATA ==========
        print(f"\n{'='*80}")
        print("🤖 MODEL DATA")
        print(f"{'='*80}")
        model_type = artifact.get('model_type', 'unknown')
        
        if model_type == 'stacking_ensemble':
            print("Stacking Ensemble Model:")
            print(f"  Meta-learner: {'meta_learner_bytes' in artifact}")
            print(f"  Scaler: {'scaler_bytes' in artifact}")
            print(f"  Base Models:")
            print(f"    - LR: {'lr_model_final_bytes' in artifact}")
            print(f"    - RF: {'rf_model_final_bytes' in artifact}")
            print(f"    - XGB: {'xgb_model_final_bytes' in artifact}")
            
            perf_weights = artifact.get('performance_weights', [])
            if perf_weights:
                print(f"  Performance Weights: LR={perf_weights[0]:.3f}, RF={perf_weights[1]:.3f}, XGB={perf_weights[2]:.3f}")
        
        elif model_type == 'logistic_regression':
            print("Logistic Regression Model:")
            print(f"  Coefficients: {'coefficients' in artifact}")
            print(f"  Intercept: {'intercept' in artifact}")
            if 'coefficients' in artifact:
                coefs = artifact['coefficients']
                if isinstance(coefs, dict):
                    print(f"  Number of coefficients: {len(coefs)}")
        
        elif model_type in ['random_forest', 'xgboost']:
            print(f"{model_type.title()} Model:")
            print(f"  Model bytes: {'model_bytes' in artifact}")
        
        # ========== TRAINING METRICS ==========
        print(f"\n{'='*80}")
        print("📊 TRAINING METRICS")
        print(f"{'='*80}")
        metrics = artifact.get('training_metrics', {})
        if metrics:
            print(json.dumps(metrics, indent=2, default=str))
        else:
            print("  ⚠️  No training_metrics found")
        
        # ========== SUMMARY ==========
        print(f"\n{'='*80}")
        print("✅ SUMMARY")
        print(f"{'='*80}")
        has_scorecard = 'scorecard_bins' in artifact and 'score_parameters' in artifact
        has_models = any(key.endswith('_bytes') for key in artifact.keys())
        has_woe = 'woe_transformed_data' in artifact
        
        print(f"✓ Scorecard Data: {'Yes' if has_scorecard else 'No'}")
        print(f"✓ Model Data: {'Yes' if has_models else 'No'}")
        print(f"✓ WOE Data: {'Yes' if has_woe else 'No'}")
        print(f"✓ Production Ready: {'Yes' if (has_scorecard and has_models and has_woe) else 'No'}")
        
        print(f"\n{'='*80}")
        print("✅ Inspection Complete!")
        print(f"{'='*80}")
        
    except Exception as e:
        print(f"\n❌ Error loading artifact: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python inspect_artifact.py <artifact_path>")
        print("Example: python inspect_artifact.py artifacts/299_stacking_ensemble.pkl")
        sys.exit(1)
    
    artifact_path = "../artifacts/299_stacking_ensemble.pkl"
    inspect_artifact(artifact_path)