"""
Automated Monotonic Binning Module

This module provides deterministic algorithms for automatically merging bins
to achieve monotonic WOE (Weight of Evidence) trends - either strictly increasing
or strictly decreasing.

For continuous variables: Only adjacent bins can be merged.
For discrete variables: Any bins can be merged.

Two algorithms are available:
1. Greedy: Fast, merges one violation at a time
   - Supports both continuous and discrete variables
   - For discrete: Finds best non-adjacent merge to minimize WOE variance
   
2. Exhaustive: Explores all 2^(n-1) possible adjacent merge combinations for n bins
   - Only supports continuous variables (adjacent-bin merging)
   - Falls back to greedy for discrete variables
   - Has performance limits: warns at n>25, hard limit at n>30
   - Finds optimal solution with maximum bins and monotonic WOE
"""

import numpy as np
import pandas as pd
from typing import List, Tuple, Dict, Optional, Any
import itertools
import copy

# Hard limit for exhaustive search (adjacent-merge continuous variables)
# Above this number of bins, exhaustive search (2^(n-1)) becomes prohibitively
# large. We enforce a conservative hard limit and a warning threshold.
EXHAUSTIVE_WARNING_LIMIT = 25
EXHAUSTIVE_HARD_LIMIT = 30

def compute_woe(good: np.ndarray, bad: np.ndarray) -> np.ndarray:
    """
    Compute Weight of Evidence (WOE) for each bin.
    
    WOE = ln(Dist_Good% / Dist_Bad%)
    
    Parameters:
    -----------
    good : np.ndarray
        Count of good instances in each bin
    bad : np.ndarray
        Count of bad instances in each bin
        
    Returns:
    --------
    np.ndarray
        WOE values for each bin
    """
    total_good = good.sum()
    total_bad = bad.sum()
    
    # Avoid division by zero
    good_dist = np.where(total_good == 0, 0, good / total_good)
    bad_dist = np.where(total_bad == 0, 0, bad / total_bad)
    
    # Avoid log of zero or division by zero
    # Use small epsilon for numerical stability
    epsilon = 1e-10
    good_dist = np.maximum(good_dist, epsilon)
    bad_dist = np.maximum(bad_dist, epsilon)
    
    woe = np.log(good_dist / bad_dist)
    
    return woe


def is_monotonic(arr: np.ndarray, increasing: bool = True) -> bool:
    """
    Check if array is monotonic (either increasing or decreasing).
    
    Parameters:
    -----------
    arr : np.ndarray
        Array to check
    increasing : bool
        If True, check for increasing trend. If False, check for decreasing trend.
        
    Returns:
    --------
    bool
        True if array is monotonic in the specified direction
    """
    if len(arr) <= 1:
        return True
        
    if increasing:
        return all(arr[i] <= arr[i+1] for i in range(len(arr)-1))
    else:
        return all(arr[i] >= arr[i+1] for i in range(len(arr)-1))


def greedy_merge_bins_woe(
    good: np.ndarray, 
    bad: np.ndarray, 
    bin_labels: List[str],
    increasing: Optional[bool] = None,
    continuous: bool = True
) -> Tuple[np.ndarray, np.ndarray, List[str], np.ndarray, Dict[str, List[str]]]:
    """
    Greedy algorithm to merge bins to achieve monotonic WOE.
    This is the simpler approach that merges bins one violation at a time.
    
    Parameters:
    -----------
    good : np.ndarray
        Count of good instances in each bin
    bad : np.ndarray
        Count of bad instances in each bin
    bin_labels : List[str]
        Labels for each bin
    increasing : Optional[bool]
        If True, aim for increasing WOE. If False, aim for decreasing WOE.
        If None, auto-detect based on overall trend.
    continuous : bool
        If True, only adjacent bins can merge (continuous variable).
        If False, any bins can merge (discrete variable).
        
    Returns:
    --------
    Tuple containing:
        - merged_good: Good counts after merging
        - merged_bad: Bad counts after merging
        - merged_labels: Labels after merging
        - final_woe: WOE values after merging
        - merge_map: Dictionary mapping new labels to original labels
    """
    good = good.copy()
    bad = bad.copy()
    labels = bin_labels.copy()
    merge_map = {label: [label] for label in labels}
    
    # Auto-detect direction if not specified
    if increasing is None:
        initial_woe = compute_woe(good, bad)
        # Use correlation with position to determine trend
        positions = np.arange(len(initial_woe))
        correlation = np.corrcoef(positions, initial_woe)[0, 1]
        increasing = correlation >= 0
    
    max_iterations = len(good) * 2  # Prevent infinite loops
    iteration = 0
    
    while iteration < max_iterations:
        woe = compute_woe(good, bad)
        
        if is_monotonic(woe, increasing):
            break  # Done - achieved monotonicity
        
        # Find first violation
        violation_idx = None
        for i in range(len(woe) - 1):
            if (increasing and woe[i] > woe[i+1]) or (not increasing and woe[i] < woe[i+1]):
                violation_idx = i
                break
        
        if violation_idx is None:
            break  # No violations found
        
        # For continuous: merge with adjacent bin
        # For discrete: merge with the bin that creates smallest WOE change
        if continuous:
            # Merge bins i and i+1
            merge_idx = violation_idx
            merge_with = violation_idx + 1
        else:
            # For discrete, find best bin to merge with (considering all possibilities)
            merge_idx = violation_idx
            best_merge_with = violation_idx + 1
            best_woe_variance = float('inf')
            
            for candidate in range(len(good)):
                if candidate == merge_idx:
                    continue
                    
                # Simulate merge
                test_good = good.copy()
                test_bad = bad.copy()
                test_good[merge_idx] += test_good[candidate]
                test_bad[merge_idx] += test_bad[candidate]
                test_good = np.delete(test_good, candidate)
                test_bad = np.delete(test_bad, candidate)
                
                test_woe = compute_woe(test_good, test_bad)
                woe_variance = np.var(test_woe)
                
                if woe_variance < best_woe_variance:
                    best_woe_variance = woe_variance
                    best_merge_with = candidate
            
            merge_with = best_merge_with
        
        # Perform the merge
        if merge_with < len(good):
            # Update merge map
            new_label = f"{labels[merge_idx]}_merged_{labels[merge_with]}"
            merge_map[new_label] = merge_map.get(labels[merge_idx], [labels[merge_idx]]) + \
                                   merge_map.get(labels[merge_with], [labels[merge_with]])
            
            # Remove old labels from merge_map
            if labels[merge_idx] in merge_map and labels[merge_idx] != new_label:
                del merge_map[labels[merge_idx]]
            if labels[merge_with] in merge_map and labels[merge_with] != new_label:
                del merge_map[labels[merge_with]]
            
            # Merge counts
            good[merge_idx] += good[merge_with]
            bad[merge_idx] += bad[merge_with]
            good = np.delete(good, merge_with)
            bad = np.delete(bad, merge_with)
            
            # Update labels
            labels[merge_idx] = new_label
            labels = [label for i, label in enumerate(labels) if i != merge_with]
        
        iteration += 1
    
    final_woe = compute_woe(good, bad)
    return good, bad, labels, final_woe, merge_map


def exhaustive_merge_bins_woe(
    good: np.ndarray,
    bad: np.ndarray,
    bin_labels: List[str],
    increasing: Optional[bool] = None,
    continuous: bool = True,
    max_bins: Optional[int] = None
) -> Tuple[np.ndarray, np.ndarray, List[str], np.ndarray, Dict[str, List[str]]]:
    """
    Exhaustive algorithm to find the best bin merging that achieves monotonic WOE.
    
    IMPORTANT: This function only supports continuous variables (adjacent-bin merging).
    For discrete variables, it will fall back to the greedy algorithm.
    
    For continuous variables: Explores ALL possible adjacent merge combinations 
    (2^(n-1) possibilities for n bins) and selects the optimal solution with 
    maximum bins and lowest WOE variance.
    
    For discrete variables: A true exhaustive search would require exploring all 
    possible set partitions (Bell number B_n), which is computationally infeasible.
    For example, B_10 = 115,975 and B_15 = 1,382,958,545.
    
    Parameters:
    -----------
    good : np.ndarray
        Count of good instances in each bin
    bad : np.ndarray
        Count of bad instances in each bin
    bin_labels : List[str]
        Labels for each bin
    increasing : Optional[bool]
        If True, aim for increasing WOE. If False, aim for decreasing WOE.
        If None, auto-detect based on overall trend.
    continuous : bool
        If True, only adjacent bins can merge (continuous variable).
        If False, any bins can merge (discrete variable).
    max_bins : Optional[int]
        Maximum number of bins to keep (will stop when reached)
        
    Returns:
    --------
    Tuple containing:
        - merged_good: Good counts after merging
        - merged_bad: Bad counts after merging
        - merged_labels: Labels after merging
        - final_woe: WOE values after merging
        - merge_map: Dictionary mapping new labels to original labels
    """
    # Auto-detect direction if not specified
    if increasing is None:
        initial_woe = compute_woe(good, bad)
        positions = np.arange(len(initial_woe))
        correlation = np.corrcoef(positions, initial_woe)[0, 1]
        increasing = correlation >= 0
    
    # For discrete variables, exhaustive search is not supported (would require exploring
    # all possible set partitions - Bell numbers). Fall back to greedy algorithm.
    if not continuous:
        print("WARNING: Exhaustive search not supported for discrete variables.")
        print("Falling back to greedy algorithm (which supports any-to-any bin merging).")
        return greedy_merge_bins_woe(good, bad, bin_labels, increasing, continuous)
    
    # Start with greedy solution as baseline
    best_good, best_bad, best_labels, best_woe, best_merge_map = greedy_merge_bins_woe(
        good, bad, bin_labels, increasing, continuous
    )
    best_num_bins = len(best_good)
    
    # If already has few bins or meets target, return greedy solution
    if max_bins and best_num_bins <= max_bins:
        return best_good, best_bad, best_labels, best_woe, best_merge_map
    
    # Try all possible merge combinations (truly exhaustive)
    n_bins = len(good)
    n_merge_positions = n_bins - 1
    
    # Generate all possible merge combinations
    # Each position can be merged (1) or not merged (0)
    # This gives us 2^(n_bins-1) possibilities
    total_combinations = 2 ** n_merge_positions
    
    # Warning for large search spaces
    if n_bins > 25:
        print(f"WARNING: Exhaustive search with {n_bins} bins requires exploring {total_combinations:,} combinations.")
        print(f"This may take a very long time. Consider using method='greedy' or reducing bins.")
    
    # Hard limit to prevent excessive computation
    if n_bins > 30:
        print(f"ERROR: Exhaustive search not recommended for {n_bins} bins (would require {total_combinations:,} combinations).")
        print(f"Falling back to greedy algorithm.")
        return best_good, best_bad, best_labels, best_woe, best_merge_map
    
    print(f"Exploring {total_combinations:,} merge combinations for {n_bins} bins...")
    
    for combination_idx in range(total_combinations):
        # Convert combination index to binary representation
        # Each bit represents whether to merge at that position
        merge_pattern = format(combination_idx, f'0{n_merge_positions}b')
        
        # Skip the all-zeros case (no merges) if we need monotonicity
        if combination_idx == 0:
            continue
        
        # Create a different merge strategy
        test_good = good.copy()
        test_bad = bad.copy()
        test_labels = bin_labels.copy()
        test_merge_map = {label: [label] for label in test_labels}
        
        # Apply merges based on the binary pattern
        # Process from right to left to maintain correct indices
        merges_to_apply = []
        for pos in range(n_merge_positions):
            if merge_pattern[pos] == '1':
                merges_to_apply.append(pos)
        
        # Apply merges from right to left to maintain indices
        for merge_idx in reversed(merges_to_apply):
            if merge_idx >= len(test_good) - 1:
                continue
            
            # Perform the merge
            new_label = f"{test_labels[merge_idx]}_merged_{test_labels[merge_idx + 1]}"
            test_merge_map[new_label] = test_merge_map.get(test_labels[merge_idx], [test_labels[merge_idx]]) + \
                                        test_merge_map.get(test_labels[merge_idx + 1], [test_labels[merge_idx + 1]])
            
            if test_labels[merge_idx] in test_merge_map:
                del test_merge_map[test_labels[merge_idx]]
            if test_labels[merge_idx + 1] in test_merge_map:
                del test_merge_map[test_labels[merge_idx + 1]]
            
            # Merge counts
            test_good[merge_idx] += test_good[merge_idx + 1]
            test_bad[merge_idx] += test_bad[merge_idx + 1]
            test_good = np.delete(test_good, merge_idx + 1)
            test_bad = np.delete(test_bad, merge_idx + 1)
            
            # Update labels
            test_labels[merge_idx] = new_label
            test_labels = [label for i, label in enumerate(test_labels) if i != merge_idx + 1]
        
        # After applying all merges, check if this solution is valid
        test_woe = compute_woe(test_good, test_bad)
        
        if is_monotonic(test_woe, increasing):
            # Found a valid solution - check if it's better
            # Prefer solutions with more bins (fewer merges), or same bins but lower WOE variance
            if len(test_good) > best_num_bins or \
               (len(test_good) == best_num_bins and np.std(test_woe) < np.std(best_woe)):
                best_good = test_good.copy()
                best_bad = test_bad.copy()
                best_labels = test_labels.copy()
                best_woe = test_woe
                best_merge_map = copy.deepcopy(test_merge_map)
                best_num_bins = len(test_good)
    
    return best_good, best_bad, best_labels, best_woe, best_merge_map


def auto_monotonic_binning(
    good: np.ndarray,
    bad: np.ndarray,
    bin_labels: List[str],
    variable_type: str = 'continuous',
    direction: Optional[str] = None,
    method: str = 'greedy',
    max_bins: Optional[int] = None
) -> Dict[str, Any]:
    """
    Main function to perform automated monotonic binning.
    
    Parameters:
    -----------
    good : np.ndarray
        Count of good instances in each bin
    bad : np.ndarray
        Count of bad instances in each bin
    bin_labels : List[str]
        Labels for each bin
    variable_type : str
        'continuous' or 'discrete'
    direction : Optional[str]
        'increasing', 'decreasing', or None (auto-detect)
    method : str
        'greedy' or 'exhaustive'
    max_bins : Optional[int]
        Maximum number of bins to keep
        
    Returns:
    --------
    Dict containing:
        - merged_good: Good counts after merging
        - merged_bad: Bad counts after merging
        - merged_labels: Labels after merging
        - woe_values: WOE values after merging
        - merge_mapping: Dictionary mapping new bins to original bins
        - is_monotonic: Boolean indicating if result is monotonic
        - direction: 'increasing' or 'decreasing'
        - num_merges: Number of merges performed
    """
    continuous = variable_type.lower() == 'continuous'
    
    # Convert direction to boolean
    if direction is None:
        increasing = None
    elif direction.lower() == 'increasing':
        increasing = True
    elif direction.lower() == 'decreasing':
        increasing = False
    else:
        increasing = None
    
    # Choose algorithm
    # If exhaustive requested for discrete variables, fall back to greedy with a warning
    if method == 'exhaustive' and not continuous:
        print("WARNING: 'exhaustive' method requested for discrete variable. Falling back to 'greedy'.")
        method = 'greedy'

    # If exhaustive requested, perform some safety checks on bin count before calling
    if method == 'exhaustive':
        n_bins = len(bin_labels)
        if n_bins > EXHAUSTIVE_WARNING_LIMIT:
            print(
                f"Warning: exhaustive search will explore 2^{n_bins-1} combinations for {n_bins} bins; this may be slow."
            )
        if n_bins > EXHAUSTIVE_HARD_LIMIT:
            raise ValueError(
                f"Exhaustive search not allowed for n_bins={n_bins} > {EXHAUSTIVE_HARD_LIMIT}. "
                "Use method='greedy' or reduce the number of initial bins."
            )

    if method == 'exhaustive':
        merged_good, merged_bad, merged_labels, final_woe, merge_map = exhaustive_merge_bins_woe(
            good, bad, bin_labels, increasing, continuous, max_bins
        )
    else:  # greedy
        merged_good, merged_bad, merged_labels, final_woe, merge_map = greedy_merge_bins_woe(
            good, bad, bin_labels, increasing, continuous
        )
    
    # Determine final direction
    if increasing is None:
        positions = np.arange(len(final_woe))
        correlation = np.corrcoef(positions, final_woe)[0, 1]
        final_direction = 'increasing' if correlation >= 0 else 'decreasing'
    else:
        final_direction = 'increasing' if increasing else 'decreasing'
    
    # Count number of merges
    num_original_bins = len(bin_labels)
    num_final_bins = len(merged_labels)
    num_merges = num_original_bins - num_final_bins
    
    return {
        'merged_good': merged_good.tolist(),
        'merged_bad': merged_bad.tolist(),
        'merged_labels': merged_labels,
        'woe_values': final_woe.tolist(),
        'merge_mapping': merge_map,
        'is_monotonic': is_monotonic(final_woe, final_direction == 'increasing'),
        'direction': final_direction,
        'num_merges': num_merges,
        'num_bins_original': num_original_bins,
        'num_bins_final': num_final_bins
    }


# Example usage and testing
if __name__ == "__main__":
    # Test case 1: Continuous variable with decreasing trend - GREEDY
    print("=" * 70)
    print("Test Case 1: Continuous Variable (Decreasing Trend) - GREEDY")
    print("=" * 70)
    
    good = np.array([50, 40, 30, 20])
    bad = np.array([10, 20, 30, 40])
    bin_labels = ['Bin_1', 'Bin_2', 'Bin_3', 'Bin_4']
    
    print("\nOriginal Bins:")
    print(f"Good: {good}")
    print(f"Bad: {bad}")
    print(f"Labels: {bin_labels}")
    print(f"Initial WOE: {compute_woe(good, bad)}")
    
    result = auto_monotonic_binning(good, bad, bin_labels, 'continuous', method='greedy')
    
    print("\nGreedy Algorithm Result:")
    print(f"Merged Good: {result['merged_good']}")
    print(f"Merged Bad: {result['merged_bad']}")
    print(f"Merged Labels: {result['merged_labels']}")
    print(f"WOE Values: {result['woe_values']}")
    print(f"Is Monotonic: {result['is_monotonic']}")
    print(f"Direction: {result['direction']}")
    print(f"Number of Merges: {result['num_merges']}")
    
    # Test case 2: Same continuous variable - EXHAUSTIVE
    print("\n" + "=" * 70)
    print("Test Case 2: Continuous Variable (Decreasing Trend) - EXHAUSTIVE")
    print("=" * 70)
    
    print("\nOriginal Bins:")
    print(f"Good: {good}")
    print(f"Bad: {bad}")
    print(f"Labels: {bin_labels}")
    print(f"Initial WOE: {compute_woe(good, bad)}")
    
    result = auto_monotonic_binning(good, bad, bin_labels, 'continuous', method='exhaustive')
    
    print("\nExhaustive Algorithm Result:")
    print(f"Merged Good: {result['merged_good']}")
    print(f"Merged Bad: {result['merged_bad']}")
    print(f"Merged Labels: {result['merged_labels']}")
    print(f"WOE Values: {result['woe_values']}")
    print(f"Is Monotonic: {result['is_monotonic']}")
    print(f"Direction: {result['direction']}")
    print(f"Number of Merges: {result['num_merges']}")
    
    # Test case 3: Continuous with non-monotonic pattern - Compare both methods
    print("\n" + "=" * 70)
    print("Test Case 3: Non-Monotonic Continuous - GREEDY vs EXHAUSTIVE")
    print("=" * 70)
    
    good = np.array([100, 50, 80, 40, 70, 30])
    bad = np.array([10, 40, 20, 50, 30, 60])
    bin_labels = ['Bin_1', 'Bin_2', 'Bin_3', 'Bin_4', 'Bin_5', 'Bin_6']
    
    print("\nOriginal Bins:")
    print(f"Good: {good}")
    print(f"Bad: {bad}")
    print(f"Labels: {bin_labels}")
    initial_woe = compute_woe(good, bad)
    print(f"Initial WOE: {initial_woe}")
    print(f"Initial Monotonic: {is_monotonic(initial_woe, True) or is_monotonic(initial_woe, False)}")
    
    result_greedy = auto_monotonic_binning(good, bad, bin_labels, 'continuous', method='greedy')
    print("\nGreedy Result:")
    print(f"Final Bins: {result_greedy['num_bins_final']}")
    print(f"WOE Values: {result_greedy['woe_values']}")
    print(f"Is Monotonic: {result_greedy['is_monotonic']}")
    print(f"Number of Merges: {result_greedy['num_merges']}")
    
    result_exhaustive = auto_monotonic_binning(good, bad, bin_labels, 'continuous', method='exhaustive')
    print("\nExhaustive Result:")
    print(f"Final Bins: {result_exhaustive['num_bins_final']}")
    print(f"WOE Values: {result_exhaustive['woe_values']}")
    print(f"Is Monotonic: {result_exhaustive['is_monotonic']}")
    print(f"Number of Merges: {result_exhaustive['num_merges']}")
    
    print("\nComparison:")
    print(f"Greedy bins: {result_greedy['num_bins_final']}, Exhaustive bins: {result_exhaustive['num_bins_final']}")
    if result_exhaustive['num_bins_final'] > result_greedy['num_bins_final']:
        print("✓ Exhaustive found solution with MORE bins (fewer merges) - Better!")
    elif result_exhaustive['num_bins_final'] == result_greedy['num_bins_final']:
        print("= Both methods achieved same number of bins")
    
    # Test case 4: Discrete variable - GREEDY
    print("\n" + "=" * 70)
    print("Test Case 4: Discrete Variable - GREEDY")
    print("=" * 70)
    
    good = np.array([100, 50, 90, 40, 80])
    bad = np.array([20, 50, 25, 55, 30])
    bin_labels = ['Category_A', 'Category_B', 'Category_C', 'Category_D', 'Category_E']
    
    print("\nOriginal Bins:")
    print(f"Good: {good}")
    print(f"Bad: {bad}")
    print(f"Labels: {bin_labels}")
    print(f"Initial WOE: {compute_woe(good, bad)}")
    
    result = auto_monotonic_binning(good, bad, bin_labels, 'discrete', method='greedy')
    
    print("\nGreedy Algorithm Result:")
    print(f"Merged Good: {result['merged_good']}")
    print(f"Merged Bad: {result['merged_bad']}")
    print(f"Merged Labels: {result['merged_labels']}")
    print(f"WOE Values: {result['woe_values']}")
    print(f"Is Monotonic: {result['is_monotonic']}")
    print(f"Direction: {result['direction']}")
    print(f"Number of Merges: {result['num_merges']}")
    
    # Test case 5: Discrete variable with EXHAUSTIVE (should fall back to greedy)
    print("\n" + "=" * 70)
    print("Test Case 5: Discrete Variable - EXHAUSTIVE (expects fallback)")
    print("=" * 70)
    
    print("\nOriginal Bins:")
    print(f"Good: {good}")
    print(f"Bad: {bad}")
    print(f"Labels: {bin_labels}")
    
    result = auto_monotonic_binning(good, bad, bin_labels, 'discrete', method='exhaustive')
    
    print("\nExhaustive Algorithm Result (should be same as greedy):")
    print(f"Final Bins: {result['num_bins_final']}")
    print(f"Is Monotonic: {result['is_monotonic']}")
    print(f"Number of Merges: {result['num_merges']}")
    
    print("\n" + "=" * 70)
    print("All tests completed!")
    print("=" * 70)
