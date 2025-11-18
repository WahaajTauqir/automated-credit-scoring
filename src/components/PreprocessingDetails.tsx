import React, { useState, useEffect } from 'react';
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
    variance: number; // Variance of the processed feature
    coefficient_of_variation?: number; // Coefficient of variation (CV)
    repeat_rate?: number; // Repeat rate (percentage of most frequent value)
    processed_stats?: FeatureStats; // Statistical information
    original_stats?: FeatureStats; // Original statistical information
    missingPercentage?: number; // Percentage of missing values
    isRemoved?: boolean; // Whether the column was removed
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
    onPreprocessingComplete?: () => void;
    onPreprocessSelectionSaved?: () => void;
}

const PreprocessingDetails: React.FC<PreprocessingDetailsProps> = ({ datasetId, onPreprocessSelectionSaved }) => {
    const [datasetStats, setDatasetStats] = useState<DatasetStats | null>(null);
    const [features, setFeatures] = useState<FeaturePreprocessingDetail[]>([]);
    const [isLoading, setIsLoading] = useState(false);
    const [preprocessSelectionSaved, setPreprocessSelectionSaved] = useState(false);

    // Load dataset stats and feature preprocessing details
    const loadPreprocessingData = async () => {
        if (!datasetId) return;

        try {
            setIsLoading(true);

            // Check if preprocess_selection is saved by getting the record
            const recordResponse = await fetch(`http://localhost:5000/api/record/${datasetId}`, {
                method: 'GET',
                headers: { 'Content-Type': 'application/json' }
            });

            let preprocessSelectionSavedLocal = false;
            if (recordResponse.ok) {
                const recordData = await recordResponse.json();
                preprocessSelectionSavedLocal = recordData.preprocess_selection === true;
                setPreprocessSelectionSaved(preprocessSelectionSavedLocal);
                if (preprocessSelectionSavedLocal && onPreprocessSelectionSaved) {
                    onPreprocessSelectionSaved();
                }
            }

            // Load features from database to get selected status
            const featuresResponse = await fetch(`http://localhost:5000/api/dataset/${datasetId}/features`, {
                method: 'GET',
                headers: { 'Content-Type': 'application/json' }
            });

            let featuresFromDb: any[] = [];
            if (featuresResponse.ok) {
                featuresFromDb = await featuresResponse.json();
            }

            // Always perform calculations to show stats and quality metrics
            // But use database selected status to determine selected/dropped
            // Load quality metrics for stats
            const metricsResponse = await fetch('http://localhost:5000/api/dataset-quality-metrics', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ dataset_id: datasetId })
            });

            // Load column changes for feature details
            const changesResponse = await fetch('http://localhost:5000/api/preprocessing-column-changes', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    dataset_id: datasetId,
                    preprocessing_steps: {
                        detect_types: true,
                        handle_missing: true,
                        remove_duplicates: true,
                        handle_outliers: false,
                        encode_categorical: false
                    }
                })
            });

            if (metricsResponse.ok && changesResponse.ok) {
                const metricsData = await metricsResponse.json();
                const changesData = await changesResponse.json();

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

                if (changesData.success) {
                    
                    // Create a map of feature names to their selected status from database
                    const featuresMap = new Map(
                        featuresFromDb.map((f: any) => [f.name, { selected: f.selected, exists: true }])
                    );

                    // Include ALL columns (including removed ones) so they can be unchecked
                    const featuresList: FeaturePreprocessingDetail[] = changesData.column_changes
                        .map((col: any) => {
                            // Get variance (default to 0 if not provided)
                            const variance = col.variance !== undefined ? col.variance : 0;
                            const coefficientOfVariation = col.coefficient_of_variation !== undefined ? col.coefficient_of_variation : null;
                            const repeatRate = col.repeat_rate !== undefined ? col.repeat_rate : null;
                            
                            // Calculate missing percentage
                            const missingPercentage = totalRows > 0 ? (col.original_missing / totalRows) * 100 : 0;
                            const hasHighMissingValues = missingPercentage > 95;
                            
                            // Check if column is removed
                            const isRemoved = col.processed_dtype === 'REMOVED' || col.removed === true;
                            
                            // Check for low variance (CV < 5%)
                            const hasLowVariance = coefficientOfVariation !== null && coefficientOfVariation < 5 && coefficientOfVariation > 0;
                            
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
                            // 4. Has non-zero variance (variance > 0)
                            // 5. Missing values are not > 95%
                            // 6. Coefficient of variation is not < 5% (low variance)
                            // 7. Repeat rate is not > 95% (high repeat rate for continuous)
                            const hasZeroVariance = variance === 0 || (typeof variance === 'number' && Math.abs(variance) < 1e-10);
                            const isFitForBinning = !isRemoved &&
                                                   col.processed_missing === 0 && 
                                                   col.processed_dtype !== 'REMOVED' &&
                                                   !hasZeroVariance &&
                                                   !hasHighMissingValues &&
                                                   !hasLowVariance &&
                                                   !hasHighRepeatRate &&
                                                   (col.processed_dtype === 'categorical' || 
                                                    col.processed_dtype === 'int64' || 
                                                    col.processed_dtype === 'float64' ||
                                                    col.processed_dtype === 'int32' ||
                                                    col.processed_dtype === 'float32');
                            
                            const dbFeature = featuresMap.get(col.column);
                            
                            // Determine selection based on preprocess_selection flag
                            let shouldBeSelected: boolean;
                            
                            if (preprocessSelectionSavedLocal) {
                                // If preprocess_selection is true, strictly use database selected status
                                // Calculations are only for display purposes (stats, quality checks, etc.)
                                shouldBeSelected = dbFeature?.selected || false;
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
                                            fetch('http://localhost:5000/api/update-feature-selection', {
                                                method: 'POST',
                                                headers: { 'Content-Type': 'application/json' },
                                                body: JSON.stringify({
                                                    dataset_id: datasetId,
                                                    feature_name: col.column,
                                                    selected: false
                                                })
                                            }).catch(err => console.error('Error auto-saving feature selection:', err));
                                        }
                                    } else {
                                        // Create feature with selected=false for removed/high missing/zero variance features
                                        fetch('http://localhost:5000/api/update-feature-selection', {
                                            method: 'POST',
                                            headers: { 'Content-Type': 'application/json' },
                                            body: JSON.stringify({
                                                dataset_id: datasetId,
                                                feature_name: col.column,
                                                selected: false
                                            })
                                        }).catch(err => console.error('Error auto-saving feature selection:', err));
                                    }
                                } else if (hasLowVariance || hasHighRepeatRate) {
                                    // Low variance or high repeat rate features - automatically uncheck but allow user to select
                                    shouldBeSelected = false;
                                    // Update DB to uncheck if feature exists and is currently selected
                                    if (dbFeature?.exists && dbFeature.selected) {
                                        fetch('http://localhost:5000/api/update-feature-selection', {
                                            method: 'POST',
                                            headers: { 'Content-Type': 'application/json' },
                                            body: JSON.stringify({
                                                dataset_id: datasetId,
                                                feature_name: col.column,
                                                selected: false
                                            })
                                        }).catch(err => console.error('Error auto-saving feature selection:', err));
                                    }
                                } else if (isFitForBinning) {
                                    // Auto-select features that pass quality checks
                                    shouldBeSelected = true;
                                    // Update DB if feature exists, or create it if it doesn't
                                    if (dbFeature?.exists) {
                                        // Only update if it's currently false (to avoid unnecessary updates)
                                        if (!dbFeature.selected) {
                                            fetch('http://localhost:5000/api/update-feature-selection', {
                                                method: 'POST',
                                                headers: { 'Content-Type': 'application/json' },
                                                body: JSON.stringify({
                                                    dataset_id: datasetId,
                                                    feature_name: col.column,
                                                    selected: true
                                                })
                                            }).catch(err => console.error('Error auto-saving feature selection:', err));
                                        }
                                    } else {
                                        // Feature doesn't exist in DB, create it with selected=true
                                        fetch('http://localhost:5000/api/update-feature-selection', {
                                            method: 'POST',
                                            headers: { 'Content-Type': 'application/json' },
                                            body: JSON.stringify({
                                                dataset_id: datasetId,
                                                feature_name: col.column,
                                                selected: true
                                            })
                                        }).catch(err => console.error('Error auto-saving feature selection:', err));
                                    }
                                } else {
                                    // Feature doesn't pass quality checks, use DB value or false
                                    shouldBeSelected = dbFeature?.selected || false;
                                }
                            }
                            
                            return {
                                name: col.column,
                                type: col.processed_dtype === 'categorical' ? 'discrete' : (col.processed_dtype === 'REMOVED' ? 'continuous' : 'continuous'),
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
                                isRemoved: isRemoved
                            };
                        });
                    // Include ALL features (including removed ones) so they can be displayed in dropped section
                    setFeatures(featuresList);
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
        // Find the current feature to get its current selected state
        const currentFeature = features.find(f => f.name === featureName);
        if (!currentFeature) return;
        
        const newSelectedState = !currentFeature.selected;
        
        // Update local state immediately for responsiveness
        setFeatures(prev => prev.map(f => 
            f.name === featureName ? { ...f, selected: newSelectedState } : f
        ));

        // Update database
        try {
            await fetch('http://localhost:5000/api/update-feature-selection', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    dataset_id: datasetId,
                    feature_name: featureName,
                    selected: newSelectedState
                })
            });
        } catch (error) {
            console.error('Error updating feature selection:', error);
            // Revert on error
            setFeatures(prev => prev.map(f => 
                f.name === featureName ? { ...f, selected: !newSelectedState } : f
            ));
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

    // Helper function to render feature card
    const renderFeatureCard = (feature: FeaturePreprocessingDetail, index: number, isSelected: boolean) => {
        const hasZeroVariance = feature.variance === 0 || (typeof feature.variance === 'number' && Math.abs(feature.variance) < 1e-10);
        const hasHighMissing = feature.missingPercentage !== undefined && feature.missingPercentage > 95;
        const hasLowVariance = feature.coefficient_of_variation !== undefined && feature.coefficient_of_variation < 5 && feature.coefficient_of_variation > 0;
        const hasHighRepeatRate = feature.type === 'continuous' && feature.repeat_rate !== undefined && feature.repeat_rate > 95;
        // Low variance and high repeat rate features are selectable (not disabled), but zero variance, high missing, and removed are disabled
        const shouldDisable = hasZeroVariance || hasHighMissing || feature.isRemoved;
        const disableReason = hasZeroVariance ? "This feature has zero variance and cannot be selected" 
                              : hasHighMissing ? `This feature has ${feature.missingPercentage.toFixed(1)}% missing values (>95%) and cannot be selected`
                              : feature.isRemoved ? "This feature was removed during preprocessing"
                              : "";
        return (
            <div
                key={feature.name}
                className={`feature-card ${feature.selected ? 'selected' : ''} ${hasZeroVariance ? 'zero-variance' : ''} ${hasHighMissing ? 'high-missing' : ''} ${hasLowVariance ? 'low-variance' : ''} ${hasHighRepeatRate ? 'high-repeat-rate' : ''}`}
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
                        {hasHighMissing && !hasZeroVariance && (
                            <div className="quality-badge" style={{ backgroundColor: '#f59e0b', color: 'white', marginLeft: '8px' }}>
                                High Missing ({feature.missingPercentage.toFixed(1)}%)
                            </div>
                        )}
                        {hasLowVariance && !hasZeroVariance && !hasHighMissing && (
                            <div className="quality-badge" style={{ backgroundColor: '#eab308', color: 'white', marginLeft: '8px' }}>
                                Low Variance (CV: {feature.coefficient_of_variation.toFixed(2)}%)
                            </div>
                        )}
                        {hasHighRepeatRate && !hasZeroVariance && !hasHighMissing && !hasLowVariance && (
                            <div className="quality-badge" style={{ backgroundColor: '#eab308', color: 'white', marginLeft: '8px' }}>
                                High Repeat Rate ({feature.repeat_rate.toFixed(1)}%)
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

                    {(feature.type === 'continuous' || (feature.type === 'discrete' && feature.variance !== undefined)) && (
                        <>
                            <div className="detail-row">
                                <span className="detail-label">Variance:</span>
                                <span className="detail-value">
                                    {feature.variance === 0 || (typeof feature.variance === 'number' && Math.abs(feature.variance) < 1e-10) ? (
                                        <span className="old-value" style={{ color: '#ef4444' }}>0 (Zero Variance)</span>
                                    ) : (
                                        <span className="success">{typeof feature.variance === 'number' ? feature.variance.toFixed(6) : 'N/A'}</span>
                                    )}
                                </span>
                            </div>
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
                    
                    <button
                        className="save-preprocess-btn"
                        onClick={async () => {
                            if (!datasetId) return;
                            
                            try {
                                const response = await fetch('http://localhost:5000/api/save-preprocess-selection', {
                                    method: 'POST',
                                    headers: { 'Content-Type': 'application/json' },
                                    body: JSON.stringify({ record_id: datasetId })
                                });
                                
                                if (response.ok) {
                                    const data = await response.json();
                                    setPreprocessSelectionSaved(true);
                                    if (onPreprocessSelectionSaved) {
                                        onPreprocessSelectionSaved();
                                    }
                                    alert('Preprocessing selection saved successfully!');
                                } else {
                                    const error = await response.json();
                                    alert(`Failed to save: ${error.error || 'Unknown error'}`);
                                }
                            } catch (error) {
                                console.error('Error saving preprocessing selection:', error);
                                alert('Failed to save preprocessing selection');
                            }
                        }}
                    >
                        Save
                    </button>
                </div>

                <div className="features-panel">
                    <div className="features-sections-container">
                        {/* Selected Features Section */}
                        <div className="features-section">
                            <div className="section-header">
                                <h3>Selected Features ({selectedCount})</h3>
                            </div>
                            <div className="features-container">
                                {selectedFeatures.length === 0 && !isLoading && (
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
                                {droppedFeatures.length === 0 && !isLoading && (
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
