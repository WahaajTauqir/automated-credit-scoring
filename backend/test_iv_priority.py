"""
Test script to demonstrate IV prioritization in exhaustive binning.

This script creates test cases where prioritizing IV vs bin count
leads to different results.
"""

import numpy as np
from auto_monotonic_binning import auto_monotonic_binning, compute_woe, compute_iv, is_monotonic

def print_section(title):
    """Print a formatted section header"""
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)

def print_result(result, label):
    """Print the result in a formatted way"""
    print(f"\n{label}:")
    print(f"  Bins: {result['num_bins_final']} (from {result['num_bins_original']} original)")
    print(f"  IV: {result['iv']:.6f}")
    print(f"  Monotonic: {result['is_monotonic']} ({result['direction']})")
    print(f"  WOE Values: {[f'{w:.4f}' for w in result['woe_values']]}")
    print(f"  Labels: {result['merged_labels']}")


# Test Case: A scenario where different merge strategies lead to different IVs
print_section("Test: IV vs Bin Count Prioritization")
print("This test demonstrates how different merge strategies affect IV")

# Create bins where:
# - Some adjacent bins have similar WOE (merging them reduces bins but maintains IV)
# - Other adjacent bins have very different WOE (merging them reduces IV significantly)
good = np.array([100, 95, 70, 50, 30, 10])
bad = np.array([5, 10, 30, 50, 70, 90])
bin_labels = ['Bin_1', 'Bin_2', 'Bin_3', 'Bin_4', 'Bin_5', 'Bin_6']

print("\nOriginal Binning:")
initial_woe = compute_woe(good, bad)
initial_iv = compute_iv(good, bad)
print(f"  Good: {good}")
print(f"  Bad:  {bad}")
print(f"  WOE:  {[f'{w:.4f}' for w in initial_woe]}")
print(f"  IV:   {initial_iv:.6f}")
print(f"  Monotonic: {is_monotonic(initial_woe, True) or is_monotonic(initial_woe, False)}")

# Greedy approach
result_greedy = auto_monotonic_binning(
    good, bad, bin_labels, 
    variable_type='continuous',
    method='greedy'
)
print_result(result_greedy, "Greedy Result")

# Exhaustive with IV prioritization
result_iv = auto_monotonic_binning(
    good, bad, bin_labels,
    variable_type='continuous', 
    method='exhaustive',
    prioritize_iv=True
)
print_result(result_iv, "Exhaustive (IV-prioritized)")

# Exhaustive with bin count prioritization
result_bins = auto_monotonic_binning(
    good, bad, bin_labels,
    variable_type='continuous',
    method='exhaustive', 
    prioritize_iv=False
)
print_result(result_bins, "Exhaustive (Bin-count prioritized)")

# Analysis
print("\n" + "-" * 80)
print("ANALYSIS:")
print("-" * 80)

if result_iv['iv'] > result_bins['iv']:
    diff = ((result_iv['iv'] - result_bins['iv']) / result_bins['iv']) * 100
    print(f"✓ IV-prioritized solution has {diff:.2f}% higher IV!")
    print(f"  (IV: {result_iv['iv']:.6f} vs {result_bins['iv']:.6f})")
elif result_iv['iv'] == result_bins['iv']:
    print("= Both prioritization strategies resulted in same IV")
else:
    print("  Note: Bin-prioritized has higher IV in this case")

if result_bins['num_bins_final'] > result_iv['num_bins_final']:
    print(f"✓ Bin-prioritized solution has {result_bins['num_bins_final'] - result_iv['num_bins_final']} more bins")
    print(f"  (Bins: {result_bins['num_bins_final']} vs {result_iv['num_bins_final']})")
elif result_bins['num_bins_final'] == result_iv['num_bins_final']:
    print("= Both prioritization strategies resulted in same number of bins")
else:
    print(f"✓ IV-prioritized solution has {result_iv['num_bins_final'] - result_bins['num_bins_final']} more bins")

print("\nKEY INSIGHT:")
print("When prioritize_iv=True, the algorithm selects the monotonic binning")
print("configuration that maximizes Information Value, even if it means fewer bins.")
print("This is useful when predictive power is more important than granularity.")


# Test Case 2: More extreme case
print_section("Test 2: Extreme Case - High IV Loss Potential")

# Create a scenario where merging certain bins causes significant IV loss
good2 = np.array([120, 110, 90, 80, 40, 20, 10])
bad2 = np.array([5, 10, 20, 30, 60, 80, 90])
bin_labels2 = ['Bin_1', 'Bin_2', 'Bin_3', 'Bin_4', 'Bin_5', 'Bin_6', 'Bin_7']

print("\nOriginal Binning:")
initial_woe2 = compute_woe(good2, bad2)
initial_iv2 = compute_iv(good2, bad2)
print(f"  Good: {good2}")
print(f"  Bad:  {bad2}")
print(f"  WOE:  {[f'{w:.4f}' for w in initial_woe2]}")
print(f"  IV:   {initial_iv2:.6f}")
print(f"  Monotonic: {is_monotonic(initial_woe2, True) or is_monotonic(initial_woe2, False)}")

result_greedy2 = auto_monotonic_binning(good2, bad2, bin_labels2, 'continuous', method='greedy')
print_result(result_greedy2, "Greedy Result")

result_iv2 = auto_monotonic_binning(good2, bad2, bin_labels2, 'continuous', method='exhaustive', prioritize_iv=True)
print_result(result_iv2, "Exhaustive (IV-prioritized)")

result_bins2 = auto_monotonic_binning(good2, bad2, bin_labels2, 'continuous', method='exhaustive', prioritize_iv=False)
print_result(result_bins2, "Exhaustive (Bin-count prioritized)")

print("\n" + "-" * 80)
print("COMPARISON SUMMARY:")
print("-" * 80)
print(f"Greedy:              {result_greedy2['num_bins_final']} bins, IV={result_greedy2['iv']:.6f}")
print(f"Exhaustive (IV):     {result_iv2['num_bins_final']} bins, IV={result_iv2['iv']:.6f}")
print(f"Exhaustive (Bins):   {result_bins2['num_bins_final']} bins, IV={result_bins2['iv']:.6f}")

if result_iv2['iv'] >= result_greedy2['iv'] and result_iv2['iv'] >= result_bins2['iv']:
    print("\n✓✓✓ IV-prioritized exhaustive found the BEST solution!")

print("\n" + "=" * 80)
print("Tests completed successfully!")
print("=" * 80)
