"""
Automated Monotonic Binning Module

This module provides deterministic algorithms for automatically merging bins
to achieve monotonic WOE (Weight of Evidence) trends - either strictly increasing
or strictly decreasing.

For continuous variables: Only adjacent bins can be merged.
For discrete variables: Any bins can be merged.

Two algorithms are available:
1. Greedy: Fast, intelligent merging with IV optimization
   - Supports both continuous and discrete variables
   - For discrete: Considers multi-bin merges (2-3 bins at once) and IV improvement
   - For continuous: Maintains adjacent-only merging constraint
   - Uses scoring that prioritizes IV improvement over just violation reduction
   
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
from collections import deque

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


def _greedy_discrete_explore_all_paths(
    good: np.ndarray,
    bad: np.ndarray,
    bin_labels: List[str],
    increasing: bool
) -> Tuple[np.ndarray, np.ndarray, List[str], np.ndarray, Dict[str, List[str]]]:
    """
    For discrete variables: Explore multiple merge paths to find all monotonic solutions,
    then select the one with highest IV.
    
    Uses a breadth-first approach to explore different merge strategies.
    """
    # Track all monotonic solutions found
    monotonic_solutions = []
    
    # Use a queue to explore different merge paths
    queue = deque()
    
    # Initial state
    initial_state = {
        'good': good.copy(),
        'bad': bad.copy(),
        'labels': bin_labels.copy(),
        'merge_map': {label: [label] for label in bin_labels},
        'path': []  # Track merge history
    }
    queue.append(initial_state)
    
    max_iterations = len(good) * 2  # Limit iterations
    iteration = 0
    visited_states = set()
    
    while queue and iteration < max_iterations:
        iteration += 1
        state = queue.popleft()
        
        # Create state hash to avoid revisiting
        state_hash = tuple(zip(state['labels'], state['good'], state['bad']))
        if state_hash in visited_states:
            continue
        visited_states.add(state_hash)
        
        # Check if current state is monotonic
        woe = compute_woe(state['good'], state['bad'])
        is_monotonic = True
        for i in range(len(woe) - 1):
            if (increasing and woe[i] > woe[i+1]) or (not increasing and woe[i] < woe[i+1]):
                is_monotonic = False
                break
        
        if is_monotonic:
            # Found a monotonic solution - store it
            iv = compute_iv(state['good'], state['bad'])
            monotonic_solutions.append({
                'good': state['good'].copy(),
                'bad': state['bad'].copy(),
                'labels': state['labels'].copy(),
                'merge_map': copy.deepcopy(state['merge_map']),
                'woe': woe,
                'iv': iv,
                'num_bins': len(state['good'])
            })
            continue
        
        # Find violations
        violations = []
        for i in range(len(woe) - 1):
            if (increasing and woe[i] > woe[i+1]) or (not increasing and woe[i] < woe[i+1]):
                violations.append(i)
        
        if not violations:
            continue
        
        # Generate candidate merges
        # Strategy 1: Merge violation bins with each other (any-to-any for discrete)
        for num_merge in range(2, min(4, len(violations) + 1)):
            for violation_combo in itertools.combinations(violations, num_merge):
                new_state = {
                    'good': state['good'].copy(),
                    'bad': state['bad'].copy(),
                    'labels': state['labels'].copy(),
                    'merge_map': copy.deepcopy(state['merge_map']),
                    'path': state['path'] + [violation_combo]
                }
                
                # Merge bins
                merge_indices = sorted(list(violation_combo), reverse=True)
                target_idx = merge_indices[0]
                
                # Merge all bins into the first one
                for idx in merge_indices[1:]:
                    new_state['good'][target_idx] += new_state['good'][idx]
                    new_state['bad'][target_idx] += new_state['bad'][idx]
                
                # Update merge map
                merged_labels = [new_state['labels'][i] for i in merge_indices]
                new_label = "_merged_".join(merged_labels)
                merged_original_labels = []
                for idx in merge_indices:
                    merged_original_labels.extend(new_state['merge_map'].pop(new_state['labels'][idx], [new_state['labels'][idx]]))
                new_state['merge_map'][new_label] = merged_original_labels
                new_state['labels'][target_idx] = new_label
                
                # Remove merged bins
                for idx in merge_indices[1:]:
                    new_state['good'] = np.delete(new_state['good'], idx)
                    new_state['bad'] = np.delete(new_state['bad'], idx)
                    new_state['labels'].pop(idx)
                
                queue.append(new_state)
        
        # Strategy 2: Merge violation bins with any other bins (not just violations)
        for viol_idx in violations[:3]:  # Limit to first 3 violations
            for other_idx in range(len(state['good'])):
                if other_idx == viol_idx:
                    continue
                
                new_state = {
                    'good': state['good'].copy(),
                    'bad': state['bad'].copy(),
                    'labels': state['labels'].copy(),
                    'merge_map': copy.deepcopy(state['merge_map']),
                    'path': state['path'] + [(viol_idx, other_idx)]
                }
                
                # Merge
                merge_indices = sorted([viol_idx, other_idx], reverse=True)
                target_idx = merge_indices[0]
                
                new_state['good'][target_idx] += new_state['good'][merge_indices[1]]
                new_state['bad'][target_idx] += new_state['bad'][merge_indices[1]]
                
                new_label = f"{new_state['labels'][target_idx]}_merged_{new_state['labels'][merge_indices[1]]}"
                new_state['merge_map'][new_label] = new_state['merge_map'].pop(new_state['labels'][target_idx], [new_state['labels'][target_idx]]) + \
                                                    new_state['merge_map'].pop(new_state['labels'][merge_indices[1]], [new_state['labels'][merge_indices[1]]])
                new_state['labels'][target_idx] = new_label
                
                new_state['good'] = np.delete(new_state['good'], merge_indices[1])
                new_state['bad'] = np.delete(new_state['bad'], merge_indices[1])
                new_state['labels'].pop(merge_indices[1])
                
                queue.append(new_state)
    
    # Select the monotonic solution with highest IV
    if monotonic_solutions:
        best_solution = max(monotonic_solutions, key=lambda x: (x['iv'], x['num_bins']))
        print(f"[Discrete Greedy] Found {len(monotonic_solutions)} monotonic solution(s). Selected: {best_solution['num_bins']} bins, IV = {best_solution['iv']:.6f}")
        return (best_solution['good'], best_solution['bad'], best_solution['labels'], 
                best_solution['woe'], best_solution['merge_map'])
    
    # Fallback: if no monotonic solution found, use iterative approach
    print("[Discrete Greedy] WARNING: No monotonic solution found in path exploration. Using fallback iterative approach.")
    return _greedy_discrete_iterative_fallback(good, bad, bin_labels, increasing)


def _greedy_discrete_iterative_fallback(
    good: np.ndarray,
    bad: np.ndarray,
    bin_labels: List[str],
    increasing: bool
) -> Tuple[np.ndarray, np.ndarray, List[str], np.ndarray, Dict[str, List[str]]]:
    """
    Fallback iterative approach for discrete variables when path exploration fails.
    """
    good = good.copy()
    bad = bad.copy()
    labels = bin_labels.copy()
    merge_map = {label: [label] for label in labels}
    
    max_iterations = len(good) * 3
    iteration = 0
    
    while iteration < max_iterations:
        woe = compute_woe(good, bad)
        is_strictly_monotonic = True
        for i in range(len(woe) - 1):
            if (increasing and woe[i] > woe[i+1]) or (not increasing and woe[i] < woe[i+1]):
                is_strictly_monotonic = False
                break
        if is_strictly_monotonic:
            break
            
        violations = []
        for i in range(len(woe) - 1):
            if (increasing and woe[i] > woe[i+1]) or (not increasing and woe[i] < woe[i+1]):
                violations.append(i)

        if not violations:
            break

        best_good, best_bad, best_labels, best_merge_map = None, None, None, None
        best_iv = -np.inf
        current_iv = compute_iv(good, bad)

        # Try merging violation bins with any other bins
        for viol_idx in violations:
            for other_idx in range(len(good)):
                if other_idx == viol_idx:
                    continue
                
                test_good = good.copy()
                test_bad = bad.copy()
                test_labels = labels.copy()
                test_merge_map = copy.deepcopy(merge_map)
                
                merge_indices = sorted([viol_idx, other_idx], reverse=True)
                target_idx = merge_indices[0]
                
                test_good[target_idx] += test_good[merge_indices[1]]
                test_bad[target_idx] += test_bad[merge_indices[1]]
                
                new_label = f"{test_labels[target_idx]}_merged_{test_labels[merge_indices[1]]}"
                test_merge_map[new_label] = test_merge_map.pop(test_labels[target_idx], [test_labels[target_idx]]) + \
                                            test_merge_map.pop(test_labels[merge_indices[1]], [test_labels[merge_indices[1]]])
                test_labels[target_idx] = new_label
                
                test_good = np.delete(test_good, merge_indices[1])
                test_bad = np.delete(test_bad, merge_indices[1])
                test_labels.pop(merge_indices[1])
                
                test_woe = compute_woe(test_good, test_bad)
                test_violations = sum(1 for i in range(len(test_woe)-1)
                                    if (increasing and test_woe[i] > test_woe[i+1]) or
                                       (not increasing and test_woe[i] < test_woe[i+1]))
                test_iv = compute_iv(test_good, test_bad)
                
                # Prefer monotonic solutions, then highest IV
                if test_violations == 0:
                    if test_iv > best_iv:
                        best_good = test_good
                        best_bad = test_bad
                        best_labels = test_labels
                        best_merge_map = test_merge_map
                        best_iv = test_iv
                elif test_iv > current_iv and test_iv > best_iv:
                    best_good = test_good
                    best_bad = test_bad
                    best_labels = test_labels
                    best_merge_map = test_merge_map
                    best_iv = test_iv
        
        if best_good is not None:
            good, bad, labels, merge_map = best_good, best_bad, best_labels, best_merge_map
        else:
            # Force merge first violation with any other bin
            viol_idx = violations[0]
            other_idx = (viol_idx + 1) % len(good)
            if other_idx == viol_idx:
                other_idx = (other_idx + 1) % len(good)
            
            merge_indices = sorted([viol_idx, other_idx], reverse=True)
            target_idx = merge_indices[0]
            
            good[target_idx] += good[merge_indices[1]]
            bad[target_idx] += bad[merge_indices[1]]
            
            new_label = f"{labels[target_idx]}_merged_{labels[merge_indices[1]]}"
            merge_map[new_label] = merge_map.pop(labels[target_idx], [labels[target_idx]]) + \
                                   merge_map.pop(labels[merge_indices[1]], [labels[merge_indices[1]]])
            labels[target_idx] = new_label
            
            good = np.delete(good, merge_indices[1])
            bad = np.delete(bad, merge_indices[1])
            labels.pop(merge_indices[1])
        
        iteration += 1
    
    final_woe = compute_woe(good, bad)
    return good, bad, labels, final_woe, merge_map


def compute_iv(good: np.ndarray, bad: np.ndarray) -> float:
    """
    Compute Information Value (IV) for the binning.
    
    IV = Σ (Dist_Good% - Dist_Bad%) * WOE
    
    Parameters:
    -----------
    good : np.ndarray
        Count of good instances in each bin
    bad : np.ndarray
        Count of bad instances in each bin
        
    Returns:
    --------
    float
        Information Value
    """
    total_good = good.sum()
    total_bad = bad.sum()
    
    # Avoid division by zero
    if total_good == 0 or total_bad == 0:
        return 0.0
    
    good_dist = good / total_good
    bad_dist = bad / total_bad
    
    # Compute WOE for each bin
    woe = compute_woe(good, bad)
    
    # IV = Σ (good_dist - bad_dist) * woe
    iv = np.sum((good_dist - bad_dist) * woe)
    
    return iv


def is_monotonic(arr: np.ndarray, increasing: bool = True, tolerance: float = 0.1) -> bool:
    """
    Check if array is monotonic (either increasing or decreasing) with tolerance.
    Allows small violations to handle flexible monotonic trends (not strictly linear).
    Goal: Avoid harsh wavy WOE trends while allowing slight variations.
    
    Parameters:
    -----------
    arr : np.ndarray
        Array to check
    increasing : bool
        If True, check for increasing trend. If False, check for decreasing trend.
    tolerance : float
        Tolerance for violations (0.0 = strict, higher = more lenient)
        Default 0.1 means allow violations if they're < 10% of the average step size
        
    Returns:
    --------
    bool
        True if array is mostly monotonic in the specified direction
    """
    if len(arr) <= 1:
        return True
    
    if len(arr) == 2:
        # For 2 elements, just check direction
        if increasing:
            return arr[0] <= arr[1]
        else:
            return arr[0] >= arr[1]
    
    # Calculate average step size for tolerance
    if increasing:
        steps = [arr[i+1] - arr[i] for i in range(len(arr)-1)]
    else:
        steps = [arr[i] - arr[i+1] for i in range(len(arr)-1)]
    
    avg_step = np.mean([abs(s) for s in steps if abs(s) > 1e-10]) if any(abs(s) > 1e-10 for s in steps) else 1.0
    max_allowed_violation = avg_step * tolerance
    
    # Count violations (adjacent pairs that go against the trend)
    violations = 0
    total_pairs = len(arr) - 1
    
    for i in range(len(arr) - 1):
        if increasing:
            violation = arr[i] - arr[i+1]  # Positive means violation
        else:
            violation = arr[i+1] - arr[i]  # Positive means violation
        
        # Only count as violation if it exceeds tolerance
        if violation > max_allowed_violation:
            violations += 1
    
    # Allow up to 20% violations for flexible monotonicity (avoids harsh wavy trends)
    # This means 80% of pairs must follow the trend
    max_allowed_violations = max(1, int(total_pairs * 0.2))  # At least 1 violation allowed, or 20% of pairs
    
    return violations <= max_allowed_violations


def monotonic_quality_score(woe: np.ndarray, increasing: bool) -> float:
    """
    Calculate a quality score for monotonic trends.
    Higher score = better monotonic trend.
    
    Measures:
    - Average step size (how much WOE changes between adjacent bins)
    - Penalizes flat segments (bins with same or very similar WOE)
    - Rewards consistent directional changes
    
    Parameters:
    -----------
    woe : np.ndarray
        WOE values to evaluate
    increasing : bool
        Whether the trend should be increasing or decreasing
        
    Returns:
    --------
    float
        Quality score (higher is better)
    """
    if len(woe) <= 1:
        return 0.0
    
    # Calculate step sizes (differences between adjacent bins)
    if increasing:
        steps = np.diff(woe)  # Should be >= 0 for increasing
    else:
        steps = -np.diff(woe)  # Should be >= 0 for decreasing
    
    # Count flat segments (steps that are very close to zero)
    flat_threshold = 0.001  # Consider steps smaller than this as "flat"
    flat_count = np.sum(np.abs(steps) < flat_threshold)
    flat_ratio = flat_count / len(steps) if len(steps) > 0 else 0.0
    
    # Calculate average step size (excluding flat segments)
    non_flat_steps = steps[np.abs(steps) >= flat_threshold]
    avg_step_size = np.mean(non_flat_steps) if len(non_flat_steps) > 0 else 0.0
    
    # Calculate consistency (coefficient of variation of step sizes)
    # Lower variation = more consistent trend
    if len(non_flat_steps) > 1 and np.mean(non_flat_steps) > 0:
        step_std = np.std(non_flat_steps)
        step_mean = np.mean(non_flat_steps)
        consistency = 1.0 / (1.0 + step_std / step_mean)  # Normalized consistency score
    else:
        consistency = 0.0
    
    # Quality score combines:
    # - Average step size (normalized, higher is better)
    # - Penalty for flat segments (lower flat_ratio is better)
    # - Consistency bonus (more consistent steps are better)
    # Normalize step size to 0-1 range (assuming typical WOE range is -5 to 5)
    normalized_step_size = min(avg_step_size / 2.0, 1.0) if avg_step_size > 0 else 0.0
    
    quality_score = (
        normalized_step_size * 0.5 +  # 50% weight on step size
        (1.0 - flat_ratio) * 0.3 +     # 30% weight on avoiding flat segments
        consistency * 0.2              # 20% weight on consistency
    )
    
    return quality_score


def greedy_merge_bins_woe(
    good: np.ndarray, 
    bad: np.ndarray, 
    bin_labels: List[str],
    increasing: Optional[bool] = None,
    continuous: bool = True
) -> Tuple[np.ndarray, np.ndarray, List[str], np.ndarray, Dict[str, List[str]]]:
    """
    Improved greedy algorithm to merge bins to achieve monotonic WOE.
    
    For CONTINUOUS variables: Only adjacent bins can merge. Uses iterative violation fixing.
    
    For DISCRETE variables: Any bins can merge. Explores multiple merge paths and tracks
    all monotonic solutions, then selects the one with highest IV.
    
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
    # Auto-detect direction
    if increasing is None:
        initial_woe = compute_woe(good, bad)
        positions = np.arange(len(initial_woe))
        correlation = np.corrcoef(positions, initial_woe)[0, 1]
        increasing = correlation >= 0
    
    # For discrete variables: explore multiple merge paths and select highest IV monotonic solution
    if not continuous:
        return _greedy_discrete_explore_all_paths(good, bad, bin_labels, increasing)
    
    # For continuous variables: use iterative violation fixing (adjacent merges only)
    good = good.copy()
    bad = bad.copy()
    labels = bin_labels.copy()
    merge_map = {label: [label] for label in labels}
    
    max_iterations = len(good) * 3
    iteration = 0
    
    while iteration < max_iterations:
        woe = compute_woe(good, bad)
        # FIX: Use strict monotonicity check (no tolerance) to ensure 100% monotonicity
        # Only exit if WOE is strictly monotonic (no violations allowed)
        is_strictly_monotonic = True
        for i in range(len(woe) - 1):
            if (increasing and woe[i] > woe[i+1]) or (not increasing and woe[i] < woe[i+1]):
                is_strictly_monotonic = False
                break
        if is_strictly_monotonic:
            break
            
        # Find all violation indices
        violations = []
        for i in range(len(woe) - 1):
            if (increasing and woe[i] > woe[i+1]) or (not increasing and woe[i] < woe[i+1]):
                violations.append(i)

        if not violations:
            break

        improved = False
        best_good, best_bad, best_labels, best_merge_map = None, None, None, None
        best_score = float('-inf')
        current_iv = compute_iv(good, bad)
        current_violations = len(violations)

        if False:  # Changed from "if not continuous:" - discrete now handled separately
            # For discrete variables: consider multi-bin merges
            # Strategy 1: Try merging multiple violation bins together
            for num_bins_to_merge in range(2, min(4, len(violations) + 1)):  # Try merging 2-3 bins at once
                for violation_combo in itertools.combinations(violations, num_bins_to_merge):
                    # Try merging these violation bins with each other
                    test_good = good.copy()
                    test_bad = bad.copy()
                    test_labels = labels.copy()
                    test_merge_map = copy.deepcopy(merge_map)
                    
                    # Sort indices in descending order to merge from right to left
                    merge_indices = sorted(list(violation_combo), reverse=True)
                    target_idx = merge_indices[0]
                    
                    # Merge all bins into the first one
                    merged_labels = [test_labels[i] for i in merge_indices]
                    for idx in merge_indices[1:]:
                        test_good[target_idx] += test_good[idx]
                        test_bad[target_idx] += test_bad[idx]
                    
                    # Update merge map
                    new_label = "_merged_".join(merged_labels)
                    merged_original_labels = []
                    for idx in merge_indices:
                        merged_original_labels.extend(test_merge_map.pop(test_labels[idx], [test_labels[idx]]))
                    test_merge_map[new_label] = merged_original_labels
                    test_labels[target_idx] = new_label
                    
                    # Remove merged bins (from right to left to maintain indices)
                    for idx in merge_indices[1:]:
                        test_good = np.delete(test_good, idx)
                        test_bad = np.delete(test_bad, idx)
                        test_labels.pop(idx)
                    
                    # Compute new WOE, violations, and IV
                    test_woe = compute_woe(test_good, test_bad)
                    test_violations = sum(1 for i in range(len(test_woe)-1)
                                        if (increasing and test_woe[i] > test_woe[i+1]) or
                                           (not increasing and test_woe[i] < test_woe[i+1]))
                    test_iv = compute_iv(test_good, test_bad)
                    test_num_bins = len(test_good)
                    current_num_bins = len(good)
                    
                    # Score: prioritize monotonicity, then bin preservation, then IV
                    # If monotonic, give huge bonus and reward more bins
                    # If not monotonic, prioritize violation reduction, then bins, then IV
                    is_monotonic_result = test_violations == 0
                    bins_preserved = test_num_bins
                    bins_lost = current_num_bins - test_num_bins
                    
                    if is_monotonic_result:
                        # Monotonic solutions: huge bonus, then prefer more bins, then IV
                        score = 1000000 + bins_preserved * 100 + (test_iv - current_iv) * 1000
                    else:
                        # Non-monotonic: prioritize violation reduction, then preserve bins, then IV
                        # Penalize losing too many bins at once
                        bin_penalty = bins_lost * 20 if bins_lost > 1 else 0
                        score = -test_violations * 1000 + bins_preserved * 50 + (test_iv - current_iv) * 100 - bin_penalty
                    
                    if score > best_score:
                        best_score = score
                        best_good = test_good.copy()
                        best_bad = test_bad.copy()
                        best_labels = test_labels.copy()
                        best_merge_map = copy.deepcopy(test_merge_map)
                        improved = True
            
            # Strategy 2: Try merging violation bins with similar WOE bins
            if not improved:
                for viol_idx in violations:
                    viol_woe = woe[viol_idx]
                    # Find bins with similar WOE values (within threshold)
                    similar_bins = []
                    for i in range(len(woe)):
                        if i != viol_idx and abs(woe[i] - viol_woe) < 50:  # Threshold for "similar"
                            similar_bins.append(i)
                    
                    # Try merging violation bin with similar bins
                    for similar_idx in similar_bins[:2]:  # Limit to 2 similar bins
                        test_good = good.copy()
                        test_bad = bad.copy()
                        test_labels = labels.copy()
                        test_merge_map = copy.deepcopy(merge_map)
                        
                        merge_indices = sorted([viol_idx, similar_idx], reverse=True)
                        target_idx = merge_indices[0]
                        
                        # Merge
                        test_good[target_idx] += test_good[merge_indices[1]]
                        test_bad[target_idx] += test_bad[merge_indices[1]]
                        
                        new_label = f"{test_labels[target_idx]}_merged_{test_labels[merge_indices[1]]}"
                        test_merge_map[new_label] = test_merge_map.pop(test_labels[target_idx], [test_labels[target_idx]]) + \
                                                    test_merge_map.pop(test_labels[merge_indices[1]], [test_labels[merge_indices[1]]])
                        test_labels[target_idx] = new_label
                        
                        test_good = np.delete(test_good, merge_indices[1])
                        test_bad = np.delete(test_bad, merge_indices[1])
                        test_labels.pop(merge_indices[1])
                        
                        test_woe = compute_woe(test_good, test_bad)
                        test_violations = sum(1 for i in range(len(test_woe)-1)
                                            if (increasing and test_woe[i] > test_woe[i+1]) or
                                               (not increasing and test_woe[i] < test_woe[i+1]))
                        test_iv = compute_iv(test_good, test_bad)
                        test_num_bins = len(test_good)
                        current_num_bins = len(good)
                        
                        # Score: prioritize monotonicity, then bin preservation, then IV
                        is_monotonic_result = test_violations == 0
                        bins_preserved = test_num_bins
                        bins_lost = current_num_bins - test_num_bins
                        
                        if is_monotonic_result:
                            score = 1000000 + bins_preserved * 100 + (test_iv - current_iv) * 1000
                        else:
                            bin_penalty = bins_lost * 20 if bins_lost > 1 else 0
                            score = -test_violations * 1000 + bins_preserved * 50 + (test_iv - current_iv) * 100 - bin_penalty
                        
                        if score > best_score:
                            best_score = score
                            best_good = test_good.copy()
                            best_bad = test_bad.copy()
                            best_labels = test_labels.copy()
                            best_merge_map = copy.deepcopy(test_merge_map)
                            improved = True

        # Original strategy: single bin merges (for continuous or as fallback)
        if not improved:
            for viol_idx in violations:
                candidates = list(range(len(good)))
                candidates.remove(viol_idx)

                for cand_idx in candidates:
                    # For continuous variables, only consider adjacent bins
                    if continuous and abs(viol_idx - cand_idx) != 1:
                        continue
                        
                    # Simulate merge
                    test_good = good.copy()
                    test_bad = bad.copy()
                    test_labels = labels.copy()
                    test_merge_map = copy.deepcopy(merge_map)

                    merge_from = viol_idx
                    merge_to = cand_idx

                    if merge_from > merge_to:
                        merge_from, merge_to = merge_to, merge_from

                    new_label = f"{test_labels[merge_to]}_merged_{test_labels[merge_from]}"
                    test_merge_map[new_label] = test_merge_map.pop(test_labels[merge_to], [test_labels[merge_to]]) + \
                                                test_merge_map.pop(test_labels[merge_from], [test_labels[merge_from]])

                    test_good[merge_to] += test_good[merge_from]
                    test_bad[merge_to] += test_bad[merge_from]

                    test_good = np.delete(test_good, merge_from)
                    test_bad = np.delete(test_bad, merge_from)
                    test_labels[merge_to] = new_label
                    test_labels.pop(merge_from)

                    test_woe = compute_woe(test_good, test_bad)
                    test_violations = sum(1 for i in range(len(test_woe)-1)
                                        if (increasing and test_woe[i] > test_woe[i+1]) or
                                           (not increasing and test_woe[i] < test_woe[i+1]))
                    test_iv = compute_iv(test_good, test_bad)
                    test_num_bins = len(test_good)
                    current_num_bins = len(good)
                    
                    # Score: prioritize monotonicity, then bin preservation, then IV
                    is_monotonic_result = test_violations == 0
                    bins_preserved = test_num_bins
                    bins_lost = current_num_bins - test_num_bins
                    
                    if is_monotonic_result:
                        score = 1000000 + bins_preserved * 100 + (test_iv - current_iv) * 1000
                    else:
                        bin_penalty = bins_lost * 20 if bins_lost > 1 else 0
                        score = -test_violations * 1000 + bins_preserved * 50 + (test_iv - current_iv) * 100 - bin_penalty

                    if score > best_score:
                        best_score = score
                        best_good = test_good.copy()
                        best_bad = test_bad.copy()
                        best_labels = test_labels.copy()
                        best_merge_map = copy.deepcopy(test_merge_map)
                        improved = True

        # Apply best merge found
        if improved and best_good is not None:
            good, bad, labels, merge_map = best_good, best_bad, best_labels, best_merge_map
        else:
            # Fallback: force merge first violation with next
            viol_idx = violations[0]
            merge_to = viol_idx + 1 if viol_idx + 1 < len(good) else viol_idx - 1
            if merge_to < 0:
                break

            new_label = f"{labels[merge_to]}_merged_{labels[viol_idx]}"
            merge_map[new_label] = merge_map.pop(labels[merge_to], [labels[merge_to]]) + \
                                   merge_map.pop(labels[viol_idx], [labels[viol_idx]])
            good[merge_to] += good[viol_idx]
            bad[merge_to] += bad[viol_idx]
            good = np.delete(good, viol_idx)
            bad = np.delete(bad, viol_idx)
            labels[merge_to] = new_label
            labels.pop(viol_idx)
        iteration += 1
        
    final_woe = compute_woe(good, bad)
    return good, bad, labels, final_woe, merge_map

def exhaustive_merge_bins_woe(
    good: np.ndarray,
    bad: np.ndarray,
    bin_labels: List[str],
    increasing: Optional[bool] = None,
    continuous: bool = True,
    max_bins: Optional[int] = None,
    prioritize_iv: bool = True
) -> Tuple[np.ndarray, np.ndarray, List[str], np.ndarray, Dict[str, List[str]]]:
    """
    Enhanced exhaustive algorithm to find the best bin merging that achieves monotonic WOE.
    
    IMPORTANT: This function only supports continuous variables (adjacent-bin merging).
    For discrete variables, it will fall back to the greedy algorithm.
    
    For continuous variables: Explores ALL possible adjacent merge combinations 
    (2^(n-1) possibilities for n bins) and selects the optimal solution.
    
    Selection criteria (in priority order):
    1. Monotonicity (MUST be monotonic - only monotonic solutions are considered)
    2. Best IV among all monotonic solutions (primary optimization goal)
    3. More bins (when IV is equal, prefer more bins)
    4. Lower WOE variance (final tiebreaker)
    
    The algorithm tries BOTH increasing and decreasing directions to find the best solution.
    
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
        If None, try BOTH directions and pick the best.
    continuous : bool
        If True, only adjacent bins can merge (continuous variable).
        If False, any bins can merge (discrete variable).
    max_bins : Optional[int]
        Maximum number of bins to keep (will stop when reached)
    prioritize_iv : bool
        Legacy parameter (kept for backward compatibility).
        Note: The algorithm now always prioritizes monotonicity first, then IV.
        
    Returns:
    --------
    Tuple containing:
        - merged_good: Good counts after merging
        - merged_bad: Bad counts after merging
        - merged_labels: Labels after merging
        - final_woe: WOE values after merging
        - merge_map: Dictionary mapping new labels to original labels
    """
    # For discrete variables, exhaustive search is not supported (would require exploring
    # all possible set partitions - Bell numbers). Fall back to greedy algorithm.
    if not continuous:
        print("WARNING: Exhaustive search not supported for discrete variables.")
        print("Falling back to greedy algorithm (which supports any-to-any bin merging).")
        if increasing is None:
            initial_woe = compute_woe(good, bad)
            positions = np.arange(len(initial_woe))
            correlation = np.corrcoef(positions, initial_woe)[0, 1]
            increasing = correlation >= 0
        return greedy_merge_bins_woe(good, bad, bin_labels, increasing, continuous)
    
    # Determine which directions to try
    directions_to_try = []
    if increasing is None:
        # Try both directions to find the best solution
        directions_to_try = [True, False]
    else:
        directions_to_try = [increasing]
    
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
        if increasing is None:
            initial_woe = compute_woe(good, bad)
            positions = np.arange(len(initial_woe))
            correlation = np.corrcoef(positions, initial_woe)[0, 1]
            increasing = correlation >= 0
        return greedy_merge_bins_woe(good, bad, bin_labels, increasing, continuous)
    
    print(f"Exploring {total_combinations:,} merge combinations for {n_bins} bins across {len(directions_to_try)} direction(s)...")
    print(f"Priority: 1) Monotonicity (MUST), 2) Best IV, 3) More bins, 4) Lower variance")
    
    # Track best solution across all directions
    best_good = None
    best_bad = None
    best_labels = None
    best_woe = None
    best_merge_map = None
    best_num_bins = 0
    best_iv = -np.inf  # Start with negative infinity to ensure any valid solution is better
    best_direction = None
    
    # Try each direction
    for direction in directions_to_try:
        direction_name = "increasing" if direction else "decreasing"
        print(f"  Trying {direction_name} direction...")
        
        # Track best solution for this direction
        dir_best_good = None
        dir_best_bad = None
        dir_best_labels = None
        dir_best_woe = None
        dir_best_merge_map = None
        dir_best_num_bins = 0
        dir_best_iv = -np.inf
        dir_monotonic_found = False
        
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
            
            # PRIORITY 1: Must be strictly monotonic (100% monotonicity, no tolerance)
            # FIX: Use strict monotonicity check to ensure 100% monotonicity
            is_strictly_monotonic = True
            for i in range(len(test_woe) - 1):
                if (direction and test_woe[i] > test_woe[i+1]) or (not direction and test_woe[i] < test_woe[i+1]):
                    is_strictly_monotonic = False
                    break
            if is_strictly_monotonic:
                dir_monotonic_found = True
                test_iv = compute_iv(test_good, test_bad)
                test_num_bins = len(test_good)
                
                # PRIORITY 2: Best IV among monotonic solutions
                # PRIORITY 3: More bins when IV is equal
                # PRIORITY 4: Lower WOE variance as tiebreaker
                is_better = False
                
                if test_iv > dir_best_iv:
                    # Higher IV is always better (primary goal)
                    is_better = True
                elif abs(test_iv - dir_best_iv) < 1e-10:  # IV essentially equal
                    # Same IV, prefer more bins
                    if test_num_bins > dir_best_num_bins:
                        is_better = True
                    elif test_num_bins == dir_best_num_bins:
                        # Same bins, prefer lower variance
                        test_variance = np.std(test_woe)
                        dir_best_variance = np.std(dir_best_woe) if dir_best_woe is not None else np.inf
                        is_better = test_variance < dir_best_variance
                
                if is_better:
                    dir_best_good = test_good.copy()
                    dir_best_bad = test_bad.copy()
                    dir_best_labels = test_labels.copy()
                    dir_best_woe = test_woe
                    dir_best_merge_map = copy.deepcopy(test_merge_map)
                    dir_best_num_bins = test_num_bins
                    dir_best_iv = test_iv
        
        # Compare best solution from this direction with overall best
        if dir_monotonic_found and dir_best_iv > best_iv:
            best_good = dir_best_good
            best_bad = dir_best_bad
            best_labels = dir_best_labels
            best_woe = dir_best_woe
            best_merge_map = dir_best_merge_map
            best_num_bins = dir_best_num_bins
            best_iv = dir_best_iv
            best_direction = direction
            print(f"    Found better {direction_name} solution: {dir_best_num_bins} bins, IV = {dir_best_iv:.4f}")
        elif dir_monotonic_found:
            print(f"    Found {direction_name} solution: {dir_best_num_bins} bins, IV = {dir_best_iv:.4f} (not better)")
        else:
            print(f"    No monotonic {direction_name} solution found")
    
    # If no monotonic solution found, fall back to greedy
    if best_good is None:
        print("WARNING: No monotonic solution found in exhaustive search. Falling back to greedy algorithm.")
        if increasing is None:
            initial_woe = compute_woe(good, bad)
            positions = np.arange(len(initial_woe))
            correlation = np.corrcoef(positions, initial_woe)[0, 1]
            increasing = correlation >= 0
        return greedy_merge_bins_woe(good, bad, bin_labels, increasing, continuous)
    
    direction_name = "increasing" if best_direction else "decreasing"
    print(f"Best solution found: {best_num_bins} bins, {direction_name} direction, IV = {best_iv:.4f}")
    
    return best_good, best_bad, best_labels, best_woe, best_merge_map


def auto_monotonic_binning(
    good: np.ndarray,
    bad: np.ndarray,
    bin_labels: List[str],
    variable_type: str = 'continuous',
    direction: Optional[str] = None,
    method: str = 'greedy',
    max_bins: Optional[int] = None,
    prioritize_iv: bool = True
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
    prioritize_iv : bool
        If True and method='exhaustive', prioritize solutions with higher IV.
        If False, prioritize solutions with more bins (traditional approach).
        Only applies to exhaustive method.
        
    Returns:
    --------
    Dict containing:
        - merged_good: Good counts after merging
        - merged_bad: Bad counts after merging
        - merged_labels: Labels after merging
        - woe_values: WOE values after merging
        - iv: Information Value of the final binning
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
            good, bad, bin_labels, increasing, continuous, max_bins, prioritize_iv
        )
    else:  # greedy
        merged_good, merged_bad, merged_labels, final_woe, merge_map = greedy_merge_bins_woe(
            good, bad, bin_labels, increasing, continuous
        )
    
    # Calculate IV for the final binning
    final_iv = compute_iv(merged_good, merged_bad)
    
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
    
    # FIX: Use strict monotonicity check for final result (100% monotonicity required)
    final_increasing = final_direction == 'increasing'
    is_strictly_monotonic_final = True
    for i in range(len(final_woe) - 1):
        if (final_increasing and final_woe[i] > final_woe[i+1]) or (not final_increasing and final_woe[i] < final_woe[i+1]):
            is_strictly_monotonic_final = False
            break
    
    return {
        'merged_good': merged_good.tolist(),
        'merged_bad': merged_bad.tolist(),
        'merged_labels': merged_labels,
        'woe_values': final_woe.tolist(),
        'iv': final_iv,
        'merge_mapping': merge_map,
        'is_monotonic': is_strictly_monotonic_final,
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
    print(f"IV: {result['iv']:.4f}")
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
    initial_iv = compute_iv(good, bad)
    print(f"Initial IV: {initial_iv:.4f}")
    
    result = auto_monotonic_binning(good, bad, bin_labels, 'continuous', method='exhaustive', prioritize_iv=True)
    
    print("\nExhaustive Algorithm Result (IV-prioritized):")
    print(f"Merged Good: {result['merged_good']}")
    print(f"Merged Bad: {result['merged_bad']}")
    print(f"Merged Labels: {result['merged_labels']}")
    print(f"WOE Values: {result['woe_values']}")
    print(f"IV: {result['iv']:.4f}")
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
    initial_iv = compute_iv(good, bad)
    print(f"Initial IV: {initial_iv:.4f}")
    print(f"Initial Monotonic: {is_monotonic(initial_woe, True) or is_monotonic(initial_woe, False)}")
    
    result_greedy = auto_monotonic_binning(good, bad, bin_labels, 'continuous', method='greedy')
    print("\nGreedy Result:")
    print(f"Final Bins: {result_greedy['num_bins_final']}")
    print(f"WOE Values: {result_greedy['woe_values']}")
    print(f"IV: {result_greedy['iv']:.4f}")
    print(f"Is Monotonic: {result_greedy['is_monotonic']}")
    print(f"Number of Merges: {result_greedy['num_merges']}")
    
    result_exhaustive = auto_monotonic_binning(good, bad, bin_labels, 'continuous', method='exhaustive', prioritize_iv=True)
    print("\nExhaustive Result (IV-prioritized):")
    print(f"Final Bins: {result_exhaustive['num_bins_final']}")
    print(f"WOE Values: {result_exhaustive['woe_values']}")
    print(f"IV: {result_exhaustive['iv']:.4f}")
    print(f"Is Monotonic: {result_exhaustive['is_monotonic']}")
    print(f"Number of Merges: {result_exhaustive['num_merges']}")
    
    result_exhaustive_bins = auto_monotonic_binning(good, bad, bin_labels, 'continuous', method='exhaustive', prioritize_iv=False)
    print("\nExhaustive Result (Bin-count prioritized):")
    print(f"Final Bins: {result_exhaustive_bins['num_bins_final']}")
    print(f"WOE Values: {result_exhaustive_bins['woe_values']}")
    print(f"IV: {result_exhaustive_bins['iv']:.4f}")
    print(f"Is Monotonic: {result_exhaustive_bins['is_monotonic']}")
    print(f"Number of Merges: {result_exhaustive_bins['num_merges']}")
    
    print("\nComparison:")
    print(f"Greedy: {result_greedy['num_bins_final']} bins, IV={result_greedy['iv']:.4f}")
    print(f"Exhaustive (IV-prioritized): {result_exhaustive['num_bins_final']} bins, IV={result_exhaustive['iv']:.4f}")
    print(f"Exhaustive (Bin-prioritized): {result_exhaustive_bins['num_bins_final']} bins, IV={result_exhaustive_bins['iv']:.4f}")
    
    if result_exhaustive['iv'] > result_greedy['iv']:
        print("✓ IV-prioritized exhaustive found solution with HIGHER IV - Better!")
    if result_exhaustive_bins['num_bins_final'] >= result_greedy['num_bins_final']:
        print("✓ Bin-prioritized exhaustive found solution with MORE bins - Better!")
    
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
