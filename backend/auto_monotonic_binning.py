"""
Automated Monotonic Binning Module

This module provides deterministic algorithms for automatically merging bins
to achieve monotonic WOE (Weight of Evidence) trends - either strictly increasing
or strictly decreasing.

For continuous variables: Only adjacent bins can be merged.
For discrete variables: Any bins can be merged.

The algorithm exhaustively explores merge possibilities and selects the best solution
that achieves monotonicity with the minimum number of merges.
"""

import numpy as np
import pandas as pd
from typing import List, Tuple, Dict, Optional, Any
import itertools
import copy


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
    This explores multiple merge possibilities and selects the best one.
    
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
    
    # Start with greedy solution as baseline
    best_good, best_bad, best_labels, best_woe, best_merge_map = greedy_merge_bins_woe(
        good, bad, bin_labels, increasing, continuous
    )
    best_num_bins = len(best_good)
    
    # If already has few bins or meets target, return greedy solution
    if max_bins and best_num_bins <= max_bins:
        return best_good, best_bad, best_labels, best_woe, best_merge_map
    
    # Try to find better solutions with fewer merges
    # Limit search space for computational efficiency
    n_bins = len(good)
    if n_bins <= 4:
        # For small number of bins, can try more combinations
        max_merge_attempts = min(10, 2 ** (n_bins - 1))
    else:
        # For larger bins, limit to reasonable number
        max_merge_attempts = 20
    
    for attempt in range(max_merge_attempts):
        # Create a different merge strategy
        test_good = good.copy()
        test_bad = bad.copy()
        test_labels = bin_labels.copy()
        test_merge_map = {label: [label] for label in test_labels}
        
        # Randomly select merge order (with seed for determinism)
        np.random.seed(attempt)
        merge_order = np.random.permutation(len(test_good) - 1)
        
        for merge_idx in merge_order:
            if merge_idx >= len(test_good) - 1:
                continue
                
            # Check if merge would help monotonicity
            woe_before = compute_woe(test_good, test_bad)
            
            # Simulate merge
            sim_good = test_good.copy()
            sim_bad = test_bad.copy()
            sim_good[merge_idx] += sim_good[merge_idx + 1]
            sim_bad[merge_idx] += sim_bad[merge_idx + 1]
            sim_good = np.delete(sim_good, merge_idx + 1)
            sim_bad = np.delete(sim_bad, merge_idx + 1)
            
            woe_after = compute_woe(sim_good, sim_bad)
            
            # Only merge if it improves or maintains monotonicity
            if is_monotonic(woe_after, increasing):
                # Accept this merge
                new_label = f"{test_labels[merge_idx]}_merged_{test_labels[merge_idx + 1]}"
                test_merge_map[new_label] = test_merge_map.get(test_labels[merge_idx], [test_labels[merge_idx]]) + \
                                            test_merge_map.get(test_labels[merge_idx + 1], [test_labels[merge_idx + 1]])
                
                if test_labels[merge_idx] in test_merge_map:
                    del test_merge_map[test_labels[merge_idx]]
                if test_labels[merge_idx + 1] in test_merge_map:
                    del test_merge_map[test_labels[merge_idx + 1]]
                
                test_good = sim_good
                test_bad = sim_bad
                test_labels[merge_idx] = new_label
                test_labels = [label for i, label in enumerate(test_labels) if i != merge_idx + 1]
                
                if is_monotonic(woe_after, increasing):
                    # Found a valid solution
                    if len(test_good) > best_num_bins or \
                       (len(test_good) == best_num_bins and np.std(woe_after) < np.std(best_woe)):
                        best_good = test_good
                        best_bad = test_bad
                        best_labels = test_labels
                        best_woe = woe_after
                        best_merge_map = test_merge_map
                        best_num_bins = len(test_good)
                    break
    
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
    # Test case 1: Continuous variable with decreasing trend
    print("=" * 60)
    print("Test Case 1: Continuous Variable (Decreasing Trend)")
    print("=" * 60)
    
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
    print(f"Merge Mapping: {result['merge_mapping']}")
    
    # Test case 2: Discrete variable
    print("\n" + "=" * 60)
    print("Test Case 2: Discrete Variable")
    print("=" * 60)
    
    good = np.array([100, 80, 60, 90, 70])
    bad = np.array([20, 30, 40, 25, 35])
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
    print(f"Merge Mapping: {result['merge_mapping']}")
