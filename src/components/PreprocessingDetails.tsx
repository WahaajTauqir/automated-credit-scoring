import React, { useState, useEffect } from 'react';
import { authGet, authPost } from '../utils/api';
import './PreprocessingDetails.css';

interface FeatureStats {
    min?: number;
    max?: number;
    mean?: number;
    median?: number;
    std?: number;
}

interface FeaturePreprocessingDetail {
    name: string;
    type: 'discrete' | 'continuous';
    selected: boolean;
    original_dtype: string;
    processed_dtype: string;
    original_missing: number;
    processed_missing: number;
    changes_applied: string[];
    passes_quality_check: boolean; // Auto-checked if true
    variance: number | null; // Variance of the processed feature (null for categorical columns)
    coefficient_of_variation?: number; // Coefficient of variation (CV)
    repeat_rate?: number; // Repeat rate (percentage of most frequent value)
    processed_stats?: FeatureStats; // Statistical information
    original_stats?: FeatureStats; // Original statistical information
    missingPercentage?: number; // Percentage of missing values
    isRemoved?: boolean; // Whether the column was removed
    is_warning?: boolean; // Whether this is a warning feature (e.g., ordered counting)
    removal_reason?: string; // Reason for removal (e.g., 'ordered_counting')
}

interface DatasetStats {
    total_rows: number;
    total_features: number;
    discrete_features: number;
    continuous_features: number;
    missing_values: number;
    duplicates_removed: number;
    quality_score: number;
}

interface PreprocessingDetailsProps {
    datasetId?: number;
    onPreprocessingComplete?: (newDatasetId?: number) => void;
    onPreprocessSelectionSaved?: () => void; // Keep for backward compatibility but will be called automatically
}

const PreprocessingDetails: React.FC<PreprocessingDetailsProps> = ({ datasetId, onPreprocessSelectionSaved }) => {
    const [datasetStats, setDatasetStats] = useState<DatasetStats | null>(null);
    const [features, setFeatures] = useState<FeaturePreprocessingDetail[]>([]);
    const [isLoading, setIsLoading] = useState(false);
    const [_preprocessSelectionSaved, setPreprocessSelectionSaved] = useState(false);

    // Load dataset stats and feature preprocessing details
    const loadPreprocessingData = async () => {
        if (!datasetId) return;

        try {
            setIsLoading(true);

            // Check if preprocess_selection is saved by getting the record
            const recordData = await authGet(`/api/record/${datasetId}`).catch(() => null);

            let preprocessSelectionSavedLocal = false;
            let targetVariable = '';
            if (recordData) {
                preprocessSelectionSavedLocal = recordData.preprocess_selection === true;
                targetVariable = recordData.target_variable || '';
                
                // Set state if already saved
                if (preprocessSelectionSavedLocal) {
                    setPreprocessSelectionSaved(true);
                    if (onPreprocessSelectionSaved) {
                        onPreprocessSelectionSaved();
                    }
                }
            }

            // Load features from database to get selected status
            const featuresFromDb = await authGet(`/api/dataset/${datasetId}/features`).catch(() => []);

            // Always perform calculations to show stats and quality metrics
            // But use database selected status to determine selected/dropped
            // Load quality metrics for stats
            const metricsResponse = await authPost('/api/dataset-quality-metrics', {
                dataset_id: datasetId
            });

            // Load column changes for feature details
            const changesResponse = await authPost('/api/preprocessing-column-changes', {
                    dataset_id: datasetId,
                    preprocessing_steps: {
                        detect_types: true,
                        handle_missing: true,
                        remove_duplicates: true,
                        handle_outliers: false,
                        encode_categorical: false
                    }
            });

            // Get data from responses (authPost returns data directly)
            const metricsData = metricsResponse;
            const changesData = changesResponse;
            
            // Debug logging
            console.log('\n[PREPROCESSING UI] ========================================');
            console.log('[PREPROCESSING UI] API Responses received');
            console.log('[PREPROCESSING UI] Metrics response:', metricsData);
            console.log('[PREPROCESSING UI] Changes response keys:', Object.keys(changesData));
            console.log('[PREPROCESSING UI] Changes success:', changesData.success);
            console.log('[PREPROCESSING UI] Column changes count:', changesData.column_changes?.length || 0);
            console.log('[PREPROCESSING UI] Column changes type:', typeof changesData.column_changes);
            console.log('[PREPROCESSING UI] Is array?', Array.isArray(changesData.column_changes));
            if (changesData.column_changes && changesData.column_changes.length > 0) {
                console.log('[PREPROCESSING UI] First column change:', changesData.column_changes[0]);
                console.log('[PREPROCESSING UI] Column names:', changesData.column_changes.map((c: any) => c.column).slice(0, 10));
            }
            console.log('[PREPROCESSING UI] Full changesData:', JSON.stringify(changesData, null, 2).substring(0, 1000));
            console.log('[PREPROCESSING UI] ========================================\n');
            
            // Check if responses have errors in the data
            if (!metricsData.success || !changesData.success) {
                console.error('Preprocessing API errors:', {
                    metrics: metricsData.error || 'Unknown error',
                    changes: changesData.error || 'Unknown error',
                    metricsData,
                    changesData
                });
                alert(`Preprocessing error: ${changesData.error || metricsData.error || 'Unknown error'}`);
                setIsLoading(false);
                return;
            }

            // Get total rows for calculating missing percentage
            let totalRows = 1;
            if (metricsData.success) {
                const metrics = metricsData.quality_metrics;
                totalRows = metrics.basic_info.num_rows || 1;
                setDatasetStats({
                    total_rows: metrics.basic_info.num_rows,
                    total_features: metrics.basic_info.num_columns,
                    discrete_features: metrics.dtype_analysis.categorical_columns.length,
                    continuous_features: metrics.dtype_analysis.numeric_columns.length,
                    missing_values: metrics.missing_analysis.total_missing,
                    duplicates_removed: metrics.duplicate_analysis.exact_duplicates,
                    quality_score: metrics.quality_score
                });
            } else if (changesData.summary?.original_shape?.[0]) {
                totalRows = changesData.summary.original_shape[0];
            }

            // Check if we have column_changes data
            if (!changesData.column_changes || !Array.isArray(changesData.column_changes)) {
                console.error('[PREPROCESSING] No column_changes found in response:', changesData);
                console.error('[PREPROCESSING] Full changesData:', JSON.stringify(changesData, null, 2));
                alert('No column data received from preprocessing API. Please check the backend logs.');
                setIsLoading(false);
                return;
            }

            console.log('[PREPROCESSING] Column changes array length:', changesData.column_changes.length);
            console.log('[PREPROCESSING] Column changes sample:', changesData.column_changes.slice(0, 2));
            console.log('[PREPROCESSING] changesData.success:', changesData.success);

            // Process features if we have column_changes data, even if success is false (to show what we have)
            if (changesData.column_changes.length > 0) {
                console.log('[PREPROCESSING] Processing', changesData.column_changes.length, 'column changes');
                    
                // Create a map of feature names to their data from database (selected status and type)
                interface DbFeature {
                    selected: boolean;
                    type: 'discrete' | 'continuous';
                    exists: boolean;
                }
                const featuresMap = new Map<string, DbFeature>(
                    featuresFromDb.map((f: any) => [f.name, { 
                        selected: f.selected, 
                        type: f.type, // 'discrete' or 'continuous' from database
                        exists: true 
                    }])
                );

                // Include ALL columns (including removed ones) so they can be unchecked
                const featuresList: FeaturePreprocessingDetail[] = changesData.column_changes
                        .map((col: any) => {
                            // Get variance (null for categorical columns, number for numeric)
                            // FIX: Categorical columns have variance = null (not applicable)
                            const variance = col.variance !== undefined ? col.variance : null;
                            const coefficientOfVariation = col.coefficient_of_variation !== undefined ? col.coefficient_of_variation : null;
                            const repeatRate = col.repeat_rate !== undefined ? col.repeat_rate : null;
                            
                            // Calculate missing percentage
                            const missingPercentage = totalRows > 0 ? (col.original_missing / totalRows) * 100 : 0;
                            const hasHighMissingValues = missingPercentage > 95;
                            
                            // Check if column is removed
                            const isRemoved = col.processed_dtype === 'REMOVED' || col.removed === true;
                            
                            // Check if this is a warning feature (e.g., ordered counting)
                            const isWarning = col.is_warning === true || col.removal_reason === 'ordered_counting';
                            const removalReason = col.removal_reason;
                            
                            // Check for low variance (CV < 5%) - only for numeric columns
                            // FIX: Don't check low variance for categorical columns
                            const isCategoricalForLowVar = col.original_dtype === 'object' || 
                                                          col.processed_dtype === 'object' ||
                                                          col.original_dtype === 'category' ||
                                                          col.processed_dtype === 'category' ||
                                                          variance === null || variance === undefined;
                            const hasLowVariance = !isCategoricalForLowVar && coefficientOfVariation !== null && coefficientOfVariation < 5 && coefficientOfVariation > 0;
                            
                            // Check for high repeat rate (>95%) for continuous columns
                            const isContinuous = col.processed_dtype === 'int64' || 
                                                col.processed_dtype === 'float64' ||
                                                col.processed_dtype === 'int32' ||
                                                col.processed_dtype === 'float32';
                            const hasHighRepeatRate = isContinuous && repeatRate !== null && repeatRate > 95;
                            
                            // Feature is fit for binning if:
                            // 1. Not removed
                            // 2. Has no missing values after preprocessing
                            // 3. Has a valid data type (discrete or continuous)
                            // 4. Has non-zero variance (variance > 0) OR for categorical columns, has multiple unique values
                            // 5. Missing values are not > 95%
                            // 6. Coefficient of variation is not < 5% (low variance)
                            // 7. Repeat rate is not > 95% (high repeat rate for continuous)
                            
                            // FIX: For categorical columns, variance doesn't apply (it's null)
                            // For numeric columns, check if variance is zero
                            const isCategorical = col.original_dtype === 'object' || 
                                                  col.processed_dtype === 'object' ||
                                                  col.original_dtype === 'category' ||
                                                  col.processed_dtype === 'category' ||
                                                  variance === null || variance === undefined;
                            
                            // FIX: Categorical columns should NOT be marked as zero variance
                            // Only numeric columns with variance = 0 should be marked as zero variance
                            const hasZeroVariance = isCategorical ? false : (variance === 0 || (typeof variance === 'number' && Math.abs(variance) < 1e-10));
                            // FIX: isFitForBinning should include categorical columns (even if encoded to numeric)
                            // Check if original dtype was categorical (object/category) OR if processed dtype is numeric
                            const wasCategorical = col.original_dtype === 'object' || 
                                                   col.original_dtype === 'category' ||
                                                   col.processed_dtype === 'object' ||
                                                   col.processed_dtype === 'category';
                            
                            const isFitForBinning = !isRemoved &&
                                                   col.processed_missing === 0 && 
                                                   col.processed_dtype !== 'REMOVED' &&
                                                   !hasZeroVariance &&
                                                   !hasHighMissingValues &&
                                                   !hasLowVariance &&
                                                   !hasHighRepeatRate &&
                                                   (wasCategorical ||  // Include categorical columns (original or processed)
                                                    col.processed_dtype === 'categorical' || 
                                                    col.processed_dtype === 'int64' || 
                                                    col.processed_dtype === 'float64' ||
                                                    col.processed_dtype === 'int32' ||
                                                    col.processed_dtype === 'float32');
                            
                            const dbFeature = featuresMap.get(col.column);
                            
                            // Debug logging for feature processing
                            if (col.column === changesData.column_changes[0]?.column || !dbFeature) {
                                console.log(`[PREPROCESSING UI] Processing feature: ${col.column}`);
                                console.log(`[PREPROCESSING UI]   DB feature exists:`, !!dbFeature);
                                console.log(`[PREPROCESSING UI]   DB selected:`, dbFeature?.selected);
                                console.log(`[PREPROCESSING UI]   DB type:`, dbFeature?.type);
                                console.log(`[PREPROCESSING UI]   Is removed:`, isRemoved);
                                console.log(`[PREPROCESSING UI]   Is fit for binning:`, isFitForBinning);
                            }
                            
                            // Determine feature type: use database type if available, otherwise infer from processed_dtype
                            let featureType: 'discrete' | 'continuous';
                            if (dbFeature?.type) {
                                // Use type from database (from AI classification or manual setting)
                                featureType = dbFeature.type as 'discrete' | 'continuous';
                            } else {
                                // Fallback: infer from processed_dtype
                                if (col.processed_dtype === 'categorical') {
                                    featureType = 'discrete';
                                } else if (col.processed_dtype === 'REMOVED') {
                                    // Default to continuous for removed columns (though they shouldn't be used)
                                    featureType = 'continuous';
                                } else {
                                    // For numeric types, default to continuous
                                    featureType = 'continuous';
                                }
                            }
                            
                            // Determine selection based on preprocess_selection flag
                            let shouldBeSelected: boolean;
                            
                            if (preprocessSelectionSavedLocal) {
                                // If preprocess_selection is true, use database selected status
                                // BUT: Auto-select valid categorical columns that were incorrectly unselected
                                // (e.g., due to previous zero variance bug)
                                if (wasCategorical && !isRemoved && !hasHighMissingValues && !hasZeroVariance) {
                                    // Valid categorical column - ensure it's selected
                                    if (!dbFeature?.selected) {
                                        console.log(`[PREPROCESSING UI] Auto-selecting valid categorical column (preprocessSelectionSaved=true): ${col.column}`);
                                        shouldBeSelected = true;
                                        // Update DB to reflect correct selection
                                        authPost('/api/update-feature-selection', {
                                                dataset_id: datasetId,
                                                feature_name: col.column,
                                                selected: true
                                        })
                                        .then(data => console.log(`[PREPROCESSING UI] Auto-select response for ${col.column}:`, data))
                                        .catch(err => console.error(`[PREPROCESSING UI] Error auto-saving feature selection for ${col.column}:`, err));
                                    } else {
                                        shouldBeSelected = dbFeature.selected;
                                    }
                                } else {
                                    // For other features, strictly use database selected status
                                    shouldBeSelected = dbFeature?.selected || false;
                                }
                            } else {
                                // If preprocess_selection is false, use calculation-based logic
                                // 1. If feature is removed, automatically uncheck it
                                // 2. If feature has >95% missing values, automatically uncheck it
                                // 3. If feature has zero variance, automatically uncheck it
                                // 4. If feature has low variance (CV < 5%), automatically uncheck it (but allow user to select)
                                // 5. If feature has high repeat rate (>95%), automatically uncheck it (but allow user to select)
                                // 6. If feature passes quality checks, auto-select it
                                // 7. Otherwise, use DB value (if exists) or false
                                if (isRemoved || hasHighMissingValues || hasZeroVariance) {
                                    // Removed, high missing, or zero variance - automatically uncheck
                                    shouldBeSelected = false;
                                    // Update DB to uncheck if feature exists and is currently selected
                                    // Also create feature with selected=false if it doesn't exist
                                    if (dbFeature?.exists) {
                                        if (dbFeature.selected) {
                                            console.log(`[PREPROCESSING UI] Auto-unselecting removed/high missing/zero variance feature: ${col.column}`);
                                            authPost('/api/update-feature-selection', {
                                                    dataset_id: datasetId,
                                                    feature_name: col.column,
                                                    selected: false
                                            })
                                            .then(data => console.log(`[PREPROCESSING UI] Auto-unselect response for ${col.column}:`, data))
                                            .catch(err => console.error(`[PREPROCESSING UI] Error auto-saving feature selection for ${col.column}:`, err));
                                        }
                                    } else {
                                        // Create feature with selected=false for removed/high missing/zero variance features
                                        console.log(`[PREPROCESSING UI] Creating feature with selected=false: ${col.column}`);
                                        authPost('/api/update-feature-selection', {
                                                dataset_id: datasetId,
                                                feature_name: col.column,
                                                selected: false
                                        })
                                        .then(data => console.log(`[PREPROCESSING UI] Create feature response for ${col.column}:`, data))
                                        .catch(err => console.error(`[PREPROCESSING UI] Error creating feature ${col.column}:`, err));
                                    }
                                } else if (hasLowVariance || hasHighRepeatRate) {
                                    // Low variance or high repeat rate features - automatically uncheck but allow user to select
                                    shouldBeSelected = false;
                                    // Update DB to uncheck if feature exists and is currently selected
                                    if (dbFeature?.exists && dbFeature.selected) {
                                        authPost('/api/update-feature-selection', {
                                                dataset_id: datasetId,
                                                feature_name: col.column,
                                                selected: false
                                        }).catch(err => console.error('Error auto-saving feature selection:', err));
                                    }
                                } else if (isFitForBinning) {
                                    // Auto-select features that pass quality checks
                                    shouldBeSelected = true;
                                    // Update DB if feature exists, or create it if it doesn't
                                    if (dbFeature?.exists) {
                                        // Only update if it's currently false (to avoid unnecessary updates)
                                        if (!dbFeature.selected) {
                                            console.log(`[PREPROCESSING UI] Auto-selecting quality-passed feature: ${col.column}`);
                                            authPost('/api/update-feature-selection', {
                                                    dataset_id: datasetId,
                                                    feature_name: col.column,
                                                    selected: true
                                            })
                                            .then(data => console.log(`[PREPROCESSING UI] Auto-select response for ${col.column}:`, data))
                                            .catch(err => console.error(`[PREPROCESSING UI] Error auto-saving feature selection for ${col.column}:`, err));
                                        }
                                    } else {
                                        // Feature doesn't exist in DB, create it with selected=true
                                        console.log(`[PREPROCESSING UI] Creating feature with selected=true: ${col.column}`);
                                        authPost('/api/update-feature-selection', {
                                                dataset_id: datasetId,
                                                feature_name: col.column,
                                                selected: true
                                        })
                                        .then(data => console.log(`[PREPROCESSING UI] Create feature response for ${col.column}:`, data))
                                        .catch(err => console.error(`[PREPROCESSING UI] Error creating feature ${col.column}:`, err));
                                    }
                                } else {
                                    // Feature doesn't pass quality checks
                                    // FIX: For valid categorical columns (not removed, no high missing, no zero variance),
                                    // default to selected=true even if they don't pass all quality checks
                                    // This ensures categorical columns are available for use
                                    if (wasCategorical && !isRemoved && !hasHighMissingValues && !hasZeroVariance) {
                                        // Valid categorical column - auto-select it
                                        shouldBeSelected = true;
                                        // Update DB if feature exists, or create it if it doesn't
                                        if (dbFeature?.exists) {
                                            if (!dbFeature.selected) {
                                                console.log(`[PREPROCESSING UI] Auto-selecting valid categorical column: ${col.column}`);
                                                authPost('/api/update-feature-selection', {
                                                        dataset_id: datasetId,
                                                        feature_name: col.column,
                                                        selected: true
                                                })
                                                .then(data => console.log(`[PREPROCESSING UI] Auto-select response for ${col.column}:`, data))
                                                .catch(err => console.error(`[PREPROCESSING UI] Error auto-saving feature selection for ${col.column}:`, err));
                                            }
                                        } else {
                                            // Create feature with selected=true for valid categorical columns
                                            console.log(`[PREPROCESSING UI] Creating feature with selected=true for valid categorical: ${col.column}`);
                                            authPost('/api/update-feature-selection', {
                                                    dataset_id: datasetId,
                                                    feature_name: col.column,
                                                    selected: true
                                            })
                                            .then(data => console.log(`[PREPROCESSING UI] Create feature response for ${col.column}:`, data))
                                            .catch(err => console.error(`[PREPROCESSING UI] Error creating feature ${col.column}:`, err));
                                        }
                                    } else {
                                        // For other features, use DB value or false
                                        shouldBeSelected = dbFeature?.selected || false;
                                    }
                                }
                            }
                            
                            return {
                                name: col.column,
                                type: featureType, // Use type from database or inferred from processed_dtype
                                selected: shouldBeSelected,
                                original_dtype: col.original_dtype,
                                processed_dtype: col.processed_dtype,
                                original_missing: col.original_missing,
                                processed_missing: col.processed_missing,
                                changes_applied: col.changes || [],
                                passes_quality_check: isFitForBinning,
                                variance: variance,
                                coefficient_of_variation: coefficientOfVariation,
                                repeat_rate: repeatRate,
                                processed_stats: col.processed_stats,
                                original_stats: col.original_stats,
                                missingPercentage: missingPercentage,
                                isRemoved: isRemoved,
                                is_warning: isWarning,
                                removal_reason: removalReason
                            };
                        });
                    // Filter out target variable - it should not be visible in preprocessing
                    // Also ensure target variable is always set to selected=false in database
                    const filteredFeaturesList = featuresList.filter(f => f.name !== targetVariable);
                    
                    // Ensure target variable is always set to selected=false in database
                    if (targetVariable) {
                        // Check if target variable exists in the features list (before filtering)
                        const targetFeature = featuresList.find(f => f.name === targetVariable);
                        if (targetFeature) {
                            // Always set target variable to selected=false
                            authPost('/api/update-feature-selection', {
                                    dataset_id: datasetId,
                                    feature_name: targetVariable,
                                    selected: false
                            }).catch(err => console.error('Error setting target variable to unselected:', err));
                        }
                    }
                    
                    // Include ALL features (including removed ones) except target variable
                    console.log('[PREPROCESSING UI] ========================================');
                    console.log('[PREPROCESSING UI] Setting features in UI state');
                    console.log('[PREPROCESSING UI] Total features:', filteredFeaturesList.length);
                    console.log('[PREPROCESSING UI] Selected features:', filteredFeaturesList.filter(f => f.selected).length);
                    console.log('[PREPROCESSING UI] Dropped features:', filteredFeaturesList.filter(f => !f.selected).length);
                    console.log('[PREPROCESSING UI] Features with selected=true:', filteredFeaturesList.filter(f => f.selected).map(f => f.name));
                    console.log('[PREPROCESSING UI] Features sample (first 5):', filteredFeaturesList.slice(0, 5).map(f => ({
                        name: f.name,
                        selected: f.selected,
                        type: f.type,
                        passes_quality: f.passes_quality_check
                    })));
                    console.log('[PREPROCESSING UI] ========================================');
                    
                    if (filteredFeaturesList.length === 0) {
                        console.warn('[PREPROCESSING UI] ⚠️ No features after filtering. All features may have been filtered out.');
                        console.warn('[PREPROCESSING UI] Target variable:', targetVariable);
                        console.warn('[PREPROCESSING UI] Original features list length:', featuresList.length);
                    }
                    
                    setFeatures(filteredFeaturesList);
                    console.log('[PREPROCESSING UI] ✅ Features state updated in React');
                    
                    // After all calculations are complete, automatically set preprocess_selection to true if it's false
                    if (!preprocessSelectionSavedLocal) {
                        try {
                            const saveResponse = await authPost('/api/save-preprocess-selection', { record_id: datasetId });
                            
                            if (saveResponse && !saveResponse.error) {
                                setPreprocessSelectionSaved(true);
                                if (onPreprocessSelectionSaved) {
                                    onPreprocessSelectionSaved();
                                }
                            }
                        } catch (error) {
                            console.error('Error auto-saving preprocess_selection:', error);
                        }
                    }
            } else {
                // No column_changes data
                console.error('[PREPROCESSING] No column_changes data available');
                console.error('[PREPROCESSING] changesData.success:', changesData.success);
                console.error('[PREPROCESSING] column_changes.length:', changesData.column_changes?.length);
                console.error('[PREPROCESSING] Full changesData:', JSON.stringify(changesData, null, 2));
                
                // Set empty features array to show "No features loaded" message
                setFeatures([]);
                
                if (!changesData.success) {
                    alert(`Failed to load preprocessing data: ${changesData.error || 'Unknown error'}`);
                } else if (changesData.column_changes && changesData.column_changes.length === 0) {
                    alert('No columns found in the dataset. Please check your data file.');
                } else {
                    alert('No column data available. Please check the backend logs.');
                }
            }
        } catch (error) {
            console.error('Error loading preprocessing data:', error);
        } finally {
            setIsLoading(false);
        }
    };

    // Toggle feature selection
    const handleFeatureToggle = async (featureName: string) => {
        console.log('[PREPROCESSING UI] ========================================');
        console.log('[PREPROCESSING UI] Toggling feature:', featureName);
        
        // Find the current feature to get its current selected state
        const currentFeature = features.find(f => f.name === featureName);
        if (!currentFeature) {
            console.error('[PREPROCESSING UI] Feature not found:', featureName);
            return;
        }
        
        const oldSelectedState = currentFeature.selected;
        const newSelectedState = !currentFeature.selected;
        
        console.log('[PREPROCESSING UI] Current state:', oldSelectedState, '→ New state:', newSelectedState);
        
        // Update local state immediately for responsiveness
        setFeatures(prev => prev.map(f => 
            f.name === featureName ? { ...f, selected: newSelectedState } : f
        ));
        console.log('[PREPROCESSING UI] ✅ Local state updated');

        // Update database
        try {
            console.log('[PREPROCESSING UI] Sending update to backend:', {
                dataset_id: datasetId,
                feature_name: featureName,
                selected: newSelectedState
            });
            
            const responseData = await authPost('/api/update-feature-selection', {
                    dataset_id: datasetId,
                    feature_name: featureName,
                    selected: newSelectedState
            });
            
            console.log('[PREPROCESSING UI] Backend response:', responseData);
            
            if (!responseData.success) {
                throw new Error(responseData.error || 'Failed to update feature selection');
            }
            
            console.log('[PREPROCESSING UI] ✅ Feature selection saved to database');
            console.log('[PREPROCESSING UI] ========================================');
        } catch (error) {
            console.error('[PREPROCESSING UI] ❌ Error updating feature selection:', error);
            // Revert on error
            setFeatures(prev => prev.map(f => 
                f.name === featureName ? { ...f, selected: oldSelectedState } : f
            ));
            console.log('[PREPROCESSING UI] ⚠️ Reverted local state due to error');
            alert(`Failed to save feature selection: ${error}`);
        }
    };

    // Load data on mount
    useEffect(() => {
        if (datasetId) {
            loadPreprocessingData();
        }
    }, [datasetId]);

    const selectedFeatures = features.filter(f => f.selected);
    const droppedFeatures = features.filter(f => !f.selected);
    const selectedCount = selectedFeatures.length;
    const droppedCount = droppedFeatures.length;
    const qualityPassCount = features.filter(f => f.passes_quality_check).length;
    
    // Debug logging when features change
    useEffect(() => {
        console.log('[PREPROCESSING UI] ========================================');
        console.log('[PREPROCESSING UI] Features state updated');
        console.log('[PREPROCESSING UI] Total features:', features.length);
        console.log('[PREPROCESSING UI] Selected:', selectedCount);
        console.log('[PREPROCESSING UI] Dropped:', droppedCount);
        console.log('[PREPROCESSING UI] Quality passed:', qualityPassCount);
        if (features.length > 0) {
            console.log('[PREPROCESSING UI] Selected feature names:', selectedFeatures.map(f => f.name));
            console.log('[PREPROCESSING UI] First 3 features details:', features.slice(0, 3).map(f => ({
                name: f.name,
                selected: f.selected,
                type: f.type
            })));
        }
        console.log('[PREPROCESSING UI] ========================================');
    }, [features, selectedCount, droppedCount, qualityPassCount, selectedFeatures]);
    
    // Debug logging when features change
    useEffect(() => {
        console.log('[PREPROCESSING UI] ========================================');
        console.log('[PREPROCESSING UI] Features state updated');
        console.log('[PREPROCESSING UI] Total features:', features.length);
        console.log('[PREPROCESSING UI] Selected:', selectedCount);
        console.log('[PREPROCESSING UI] Dropped:', droppedCount);
        console.log('[PREPROCESSING UI] Quality passed:', qualityPassCount);
        if (features.length > 0) {
            console.log('[PREPROCESSING UI] Selected feature names:', selectedFeatures.map(f => f.name));
            console.log('[PREPROCESSING UI] First 3 features details:', features.slice(0, 3).map(f => ({
                name: f.name,
                selected: f.selected,
                type: f.type
            })));
        }
        console.log('[PREPROCESSING UI] ========================================');
    }, [features, selectedCount, droppedCount, qualityPassCount]);

    // Helper function to render feature card
    const renderFeatureCard = (feature: FeaturePreprocessingDetail, index: number, _isSelected: boolean) => {
        // FIX: Categorical columns have variance = null (not applicable)
        // Only numeric columns with variance = 0 should be marked as zero variance
        const isCategorical = feature.original_dtype === 'object' || 
                             feature.processed_dtype === 'object' ||
                             feature.original_dtype === 'category' ||
                             feature.processed_dtype === 'category' ||
                             feature.variance === null || feature.variance === undefined;
        
        const hasZeroVariance = isCategorical ? false : (feature.variance === 0 || (typeof feature.variance === 'number' && Math.abs(feature.variance) < 1e-10));
        const hasHighMissing = feature.missingPercentage !== undefined && feature.missingPercentage > 95;
        const hasLowVariance = !isCategorical && feature.coefficient_of_variation !== undefined && feature.coefficient_of_variation < 5 && feature.coefficient_of_variation > 0;
        const hasHighRepeatRate = feature.type === 'continuous' && feature.repeat_rate !== undefined && feature.repeat_rate > 95;
        const isWarning = feature.is_warning === true || feature.removal_reason === 'ordered_counting';
        // Low variance and high repeat rate features are selectable (not disabled), but zero variance, high missing, and removed are disabled
        const shouldDisable = hasZeroVariance || hasHighMissing || feature.isRemoved;
        const disableReason = hasZeroVariance ? "This feature has zero variance and cannot be selected" 
                              : hasHighMissing && feature.missingPercentage !== undefined ? `This feature has ${feature.missingPercentage.toFixed(1)}% missing values (>95%) and cannot be selected`
                              : feature.isRemoved ? "This feature was removed during preprocessing"
                              : "";
        return (
            <div
                key={feature.name}
                className={`feature-card ${feature.selected ? 'selected' : ''} ${hasZeroVariance ? 'zero-variance' : ''} ${hasHighMissing ? 'high-missing' : ''} ${hasLowVariance ? 'low-variance' : ''} ${hasHighRepeatRate ? 'high-repeat-rate' : ''} ${isWarning ? 'warning-feature' : ''}`}
            >
                <div className="feature-header">
                    <div className="checkbox-wrapper">
                        <input
                            type="checkbox"
                            id={`feature-${index}`}
                            checked={feature.selected}
                            onChange={() => handleFeatureToggle(feature.name)}
                            disabled={shouldDisable}
                            className="feature-checkbox"
                            title={disableReason}
                        />
                        <label htmlFor={`feature-${index}`}></label>
                    </div>
                    <div className="feature-name-container">
                        <div className="feature-name">{feature.name}</div>
                        <div className="feature-type-badge">{feature.type}</div>
                        {hasZeroVariance && (
                            <div className="quality-badge" style={{ backgroundColor: '#ef4444', color: 'white', marginLeft: '8px' }}>
                                Zero Variance
                            </div>
                        )}
                        {hasHighMissing && !hasZeroVariance && feature.missingPercentage !== undefined && (
                            <div className="quality-badge" style={{ backgroundColor: '#f59e0b', color: 'white', marginLeft: '8px' }}>
                                High Missing ({feature.missingPercentage.toFixed(1)}%)
                            </div>
                        )}
                        {hasLowVariance && !hasZeroVariance && !hasHighMissing && feature.coefficient_of_variation !== undefined && (
                            <div className="quality-badge" style={{ backgroundColor: '#eab308', color: 'white', marginLeft: '8px' }}>
                                Low Variance (CV: {feature.coefficient_of_variation.toFixed(2)}%)
                            </div>
                        )}
                        {hasHighRepeatRate && !hasZeroVariance && !hasHighMissing && !hasLowVariance && feature.repeat_rate !== undefined && (
                            <div className="quality-badge" style={{ backgroundColor: '#eab308', color: 'white', marginLeft: '8px' }}>
                                High Repeat Rate ({feature.repeat_rate.toFixed(1)}%)
                            </div>
                        )}
                        {isWarning && feature.removal_reason === 'ordered_counting' && (
                            <div className="quality-badge" style={{ backgroundColor: '#d29922', color: 'white', marginLeft: '8px' }}>
                                Ordered Counting
                            </div>
                        )}
                    </div>
                </div>

                <div className="feature-details">
                    <div className="detail-row">
                        <span className="detail-label">Data Type:</span>
                        <span className="detail-value">
                            {feature.original_dtype !== feature.processed_dtype ? (
                                <>
                                    <span className="old-value">{feature.original_dtype}</span>
                                    <span className="arrow">→</span>
                                    <span className="new-value">{feature.processed_dtype}</span>
                                </>
                            ) : (
                                feature.processed_dtype
                            )}
                        </span>
                    </div>
                    
                    <div className="detail-row">
                        <span className="detail-label">Missing Values:</span>
                        <span className="detail-value">
                            {feature.original_missing > 0 ? (
                                <>
                                    <span className="old-value">{feature.original_missing}</span>
                                    <span className="arrow">→</span>
                                    <span className="new-value success">{feature.processed_missing}</span>
                                </>
                            ) : (
                                <span className="success">{feature.processed_missing}</span>
                            )}
                        </span>
                    </div>

                    {/* Show variance for all columns: numeric columns show actual variance, categorical show N/A */}
                    {/* FIX: Always show variance section for discrete columns (including categorical with null variance) */}
                    {(feature.type === 'continuous' || feature.type === 'discrete') && (
                        <>
                            <div className="detail-row">
                                <span className="detail-label">Variance:</span>
                                <span className="detail-value">
                                    {feature.variance === null || feature.variance === undefined ? (
                                        <span className="success">N/A (Categorical)</span>
                                    ) : feature.variance === 0 || (typeof feature.variance === 'number' && Math.abs(feature.variance) < 1e-10) ? (
                                        <span className="old-value" style={{ color: '#ef4444' }}>0 (Zero Variance)</span>
                                    ) : (
                                        <span className="success">{typeof feature.variance === 'number' ? feature.variance.toFixed(6) : 'N/A'}</span>
                                    )}
                                </span>
                            </div>
                            {/* Coefficient of Variation only applies to numeric columns */}
                            {feature.coefficient_of_variation !== undefined && feature.coefficient_of_variation !== null && (
                                <div className="detail-row">
                                    <span className="detail-label">Coefficient of Variation:</span>
                                    <span className="detail-value">
                                        <span className={hasLowVariance ? 'old-value' : 'success'} style={hasLowVariance ? { color: '#eab308' } : {}}>
                                            {feature.coefficient_of_variation.toFixed(2)}%
                                        </span>
                                    </span>
                                </div>
                            )}
                        </>
                    )}

                    {feature.type === 'continuous' && feature.repeat_rate !== undefined && feature.repeat_rate !== null && (
                        <div className="detail-row">
                            <span className="detail-label">Repeat Rate:</span>
                            <span className="detail-value">
                                <span className={hasHighRepeatRate ? 'old-value' : 'success'} style={hasHighRepeatRate ? { color: '#eab308' } : {}}>
                                    {feature.repeat_rate.toFixed(2)}%
                                </span>
                            </span>
                        </div>
                    )}

                    {/* Show statistics for selected features */}
                    {feature.selected && feature.processed_stats && (
                        <div className="detail-row">
                            <span className="detail-label">Statistics:</span>
                            <div className="stats-grid">
                                {feature.processed_stats.mean !== undefined && (
                                    <div className="stat-item-small">
                                        <span className="stat-label-small">Mean:</span>
                                        <span className="stat-value-small">{feature.processed_stats.mean.toFixed(4)}</span>
                                    </div>
                                )}
                                {feature.processed_stats.median !== undefined && (
                                    <div className="stat-item-small">
                                        <span className="stat-label-small">Median:</span>
                                        <span className="stat-value-small">{feature.processed_stats.median.toFixed(4)}</span>
                                    </div>
                                )}
                                {feature.processed_stats.std !== undefined && (
                                    <div className="stat-item-small">
                                        <span className="stat-label-small">Std Dev:</span>
                                        <span className="stat-value-small">{feature.processed_stats.std.toFixed(4)}</span>
                                    </div>
                                )}
                                {feature.processed_stats.min !== undefined && (
                                    <div className="stat-item-small">
                                        <span className="stat-label-small">Min:</span>
                                        <span className="stat-value-small">{feature.processed_stats.min.toFixed(4)}</span>
                                    </div>
                                )}
                                {feature.processed_stats.max !== undefined && (
                                    <div className="stat-item-small">
                                        <span className="stat-label-small">Max:</span>
                                        <span className="stat-value-small">{feature.processed_stats.max.toFixed(4)}</span>
                                    </div>
                                )}
                            </div>
                        </div>
                    )}

                    {feature.changes_applied.length > 0 && (
                        <div className="detail-row">
                            <span className="detail-label">Preprocessing Applied:</span>
                            <div className="changes-list">
                                {feature.changes_applied.map((change, idx) => (
                                    <span key={idx} className="change-badge">{change}</span>
                                ))}
                            </div>
                        </div>
                    )}
                </div>
            </div>
        );
    };

    // Debug: Log render state
    console.log('[PREPROCESSING UI] Rendering component');
    console.log('[PREPROCESSING UI] Current features count:', features.length);
    console.log('[PREPROCESSING UI] isLoading:', isLoading);
    
    return (
        <div className="preprocessing-container">
            <div className="preprocessing-layout">
                <div className="stats-panel">
                    <h3>Dataset Stats</h3>
                    {datasetStats && (
                        <>
                            <div className="stat-item">
                                <span className="stat-label">Rows</span>
                                <span className="stat-value">{datasetStats.total_rows.toLocaleString()}</span>
                            </div>
                            <div className="stat-item">
                                <span className="stat-label">Features</span>
                                <span className="stat-value">{datasetStats.total_features}</span>
                            </div>
                            <div className="stat-item">
                                <span className="stat-label">Discrete</span>
                                <span className="stat-value">{datasetStats.discrete_features}</span>
                            </div>
                            <div className="stat-item">
                                <span className="stat-label">Continuous</span>
                                <span className="stat-value">{datasetStats.continuous_features}</span>
                            </div>
                            <div className="stat-item">
                                <span className="stat-label">Missing</span>
                                <span className="stat-value">{datasetStats.missing_values}</span>
                            </div>
                            <div className="stat-item">
                                <span className="stat-label">Quality</span>
                                <span className="stat-value">{datasetStats.quality_score}/100</span>
                            </div>
                        </>
                    )}

                    <h3>Selection Summary</h3>
                    <div className="stat-item">
                        <span className="stat-label">Total Features</span>
                        <span className="stat-value">{features.length}</span>
                    </div>
                    <div className="stat-item">
                        <span className="stat-label">Selected</span>
                        <span className="stat-value highlight">{selectedCount}</span>
                    </div>
                    <div className="stat-item">
                        <span className="stat-label">Dropped</span>
                        <span className="stat-value" style={{ color: '#ef4444' }}>{droppedCount}</span>
                    </div>
                    <div className="stat-item">
                        <span className="stat-label">Quality Passed</span>
                        <span className="stat-value success">{qualityPassCount}</span>
                    </div>
                </div>

                <div className="features-panel">
                    <div className="features-sections-container">
                        {/* Selected Features Section */}
                        <div className="features-section">
                            <div className="section-header">
                                <h3>Selected Features ({selectedCount})</h3>
                            </div>
                            <div className="features-container">
                                {features.length === 0 && !isLoading && (
                                    <div className="empty-state">
                                        <span className="empty-icon">📭</span>
                                        <p>No features loaded</p>
                                        <p style={{ fontSize: '12px', color: '#666', marginTop: '8px' }}>
                                            Check browser console for errors
                                        </p>
                                    </div>
                                )}
                                {features.length > 0 && selectedFeatures.length === 0 && !isLoading && (
                                    <div className="empty-state">
                                        <span className="empty-icon">📭</span>
                                        <p>No selected features</p>
                                    </div>
                                )}
                                {selectedFeatures.map((feature, index) => {
                                    return renderFeatureCard(feature, index, true);
                                })}
                            </div>
                        </div>

                        {/* Dropped Features Section */}
                        <div className="features-section">
                            <div className="section-header">
                                <h3>Dropped Features ({droppedCount})</h3>
                            </div>
                            <div className="features-container">
                                {features.length === 0 && !isLoading && (
                                    <div className="empty-state">
                                        <span className="empty-icon">📭</span>
                                        <p>No features loaded</p>
                                    </div>
                                )}
                                {features.length > 0 && droppedFeatures.length === 0 && !isLoading && (
                                    <div className="empty-state">
                                        <span className="empty-icon">📭</span>
                                        <p>No dropped features</p>
                                    </div>
                                )}
                                {droppedFeatures.map((feature, index) => {
                                    return renderFeatureCard(feature, index + selectedFeatures.length, false);
                                })}
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            {isLoading && (
                <div className="loading-overlay">
                    <div className="loading-spinner"></div>
                    <p>Loading preprocessing data...</p>
                </div>
            )}
        </div>
    );
};

export default PreprocessingDetails;
