import React, { useState, useEffect } from 'react';
import './PreprocessingDetails.css';

interface QualityMetrics {
    basic_info: {
        num_rows: number;
        num_columns: number;
        memory_usage_mb: number;
        total_cells: number;
    };
    missing_analysis: {
        total_missing: number;
        missing_percentage: number;
        columns_with_missing: string[];
        severity: string;
    };
    duplicate_analysis: {
        exact_duplicates: number;
        percentage_duplicates: number;
        severity: string;
    };
    dtype_analysis: {
        numeric_columns: string[];
        categorical_columns: string[];
        datetime_columns: string[];
    };
    outlier_analysis: Record<string, any>;
    cardinality_analysis: Record<string, any>;
    quality_score: number;
    quality_rating: string;
}

interface PreprocessingStep {
    step_name: string;
    description: string;
    status: 'pending' | 'completed' | 'error';
    changes?: any;
    sample_data?: any[];
}

interface ColumnChange {
    column: string;
    changes: string[];
    original_dtype: string;
    processed_dtype: string;
    original_missing: number;
    processed_missing: number;
    has_changes: boolean;
}

interface PreprocessingDetailsProps {
    datasetId?: number;
    onPreprocessingComplete?: (newDatasetId: number) => void;
}

const PreprocessingDetails: React.FC<PreprocessingDetailsProps> = ({ datasetId, onPreprocessingComplete }) => {
    const [qualityMetrics, setQualityMetrics] = useState<QualityMetrics | null>(null);
    const [preprocessingSteps, setPreprocessingSteps] = useState<PreprocessingStep[]>([]);
    const [columnChanges, setColumnChanges] = useState<ColumnChange[]>([]);
    const [isLoading, setIsLoading] = useState(false);
    const [activeTab, setActiveTab] = useState('quality');
    const [previewData, setPreviewData] = useState<any>(null);
    const [selectedColumns, setSelectedColumns] = useState<Set<string>>(new Set());

    // Load quality metrics
    const loadQualityMetrics = async () => {
        if (!datasetId) return;

        try {
            const response = await fetch('http://localhost:5000/api/dataset-quality-metrics', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ dataset_id: datasetId })
            });

            if (response.ok) {
                const data = await response.json();
                if (data.success) {
                    setQualityMetrics(data.quality_metrics);
                }
            }
        } catch (error) {
            console.error('Error loading quality metrics:', error);
        }
    };

    // Load preprocessing steps
    const loadPreprocessingSteps = async () => {
        if (!datasetId) return;

        try {
            const response = await fetch('http://localhost:5000/api/preprocessing-steps-detailed', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    dataset_id: datasetId,
                    preprocessing_steps: {
                        detect_types: true,
                        handle_missing: true,
                        remove_duplicates: true,
                        handle_outliers: true,
                        encode_categorical: true
                    }
                })
            });

            if (response.ok) {
                const data = await response.json();
                if (data.success) {
                    setPreprocessingSteps(data.preprocessing_details.steps);
                    setPreviewData(data.preprocessing_details);
                }
            }
        } catch (error) {
            console.error('Error loading preprocessing steps:', error);
        }
    };

    // Load column changes
    const loadColumnChanges = async () => {
        if (!datasetId) return;

        try {
            const response = await fetch('http://localhost:5000/api/preprocessing-column-changes', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    dataset_id: datasetId,
                    preprocessing_steps: {
                        detect_types: true,
                        handle_missing: true,
                        remove_duplicates: true,
                        handle_outliers: true,
                        encode_categorical: true
                    }
                })
            });

            if (response.ok) {
                const data = await response.json();
                if (data.success) {
                    setColumnChanges(data.column_changes);
                }
            }
        } catch (error) {
            console.error('Error loading column changes:', error);
        }
    };

    // Apply preprocessing
    const applyPreprocessing = async () => {
        if (!datasetId) return;

        try {
            setIsLoading(true);
            const response = await fetch('http://localhost:5000/api/preprocess-dataset', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    dataset_id: datasetId,
                    preprocessing_steps: {
                        detect_types: true,
                        handle_missing: true,
                        remove_duplicates: true,
                        handle_outliers: true,
                        encode_categorical: true
                    }
                })
            });

            if (response.ok) {
                const data = await response.json();
                if (data.success && onPreprocessingComplete) {
                    onPreprocessingComplete(data.new_dataset_id);
                }
                // Reload all data
                await Promise.all([
                    loadQualityMetrics(),
                    loadPreprocessingSteps(),
                    loadColumnChanges()
                ]);
            }
        } catch (error) {
            console.error('Error applying preprocessing:', error);
        } finally {
            setIsLoading(false);
        }
    };

    // Load all data on component mount
    useEffect(() => {
        if (datasetId) {
            Promise.all([
                loadQualityMetrics(),
                loadPreprocessingSteps(),
                loadColumnChanges()
            ]);
        }
    }, [datasetId]);

    // Handle column selection
    const handleColumnSelect = (columnName: string) => {
        setSelectedColumns(prev => {
            const newSelected = new Set(prev);
            if (newSelected.has(columnName)) {
                newSelected.delete(columnName);
            } else {
                newSelected.add(columnName);
            }
            return newSelected;
        });
    };

    // Handle select all/none
    const handleSelectAll = () => {
        if (selectedColumns.size === columnChanges.length) {
            setSelectedColumns(new Set());
        } else {
            setSelectedColumns(new Set(columnChanges.map(col => col.column)));
        }
    };

    const getSeverityColor = (severity: string) => {
        switch (severity.toLowerCase()) {
            case 'high': return '#ff6b6b';
            case 'medium': return '#ffd93d';
            case 'low': return '#6bcf7f';
            default: return '#cccccc';
        }
    };

    const getStatusIcon = (status: string) => {
        switch (status) {
            case 'completed': return '✅';
            case 'error': return '❌';
            case 'pending': return '⏳';
            default: return '🔵';
        }
    };

    return (
        <div className="preprocessing-grid">
            {/* Header */}
            <div className="grid-header">
                <h1>Data Preprocessing Dashboard</h1>
                <p>Comprehensive data quality assessment and preprocessing pipeline</p>
            </div>

            {/* Navigation Tabs */}
            <div className="nav-tabs">
                <button
                    className={`tab-button ${activeTab === 'quality' ? 'active' : ''}`}
                    onClick={() => setActiveTab('quality')}
                >
                    📊 Quality Report
                </button>
                <button
                    className={`tab-button ${activeTab === 'pipeline' ? 'active' : ''}`}
                    onClick={() => setActiveTab('pipeline')}
                >
                    ⚙️ Preprocessing Pipeline
                </button>
                <button
                    className={`tab-button ${activeTab === 'changes' ? 'active' : ''}`}
                    onClick={() => setActiveTab('changes')}
                >
                    🔄 Column Changes
                </button>
            </div>

            {/* Quality Metrics Grid */}
            {activeTab === 'quality' && qualityMetrics && (
                <div className="tab-content">
                    <div className="section-header">
                        <h2>Data Quality Assessment</h2>
                        <div className="quality-score">
                            <div className="score-circle">
                                <span className="score-value">{qualityMetrics.quality_score}</span>
                                <span className="score-label">/100</span>
                            </div>
                            <div className="score-rating">
                                <span className="rating">{qualityMetrics.quality_rating}</span>
                                <span className="rating-description">Overall Quality</span>
                            </div>
                        </div>
                    </div>

                    <div className="metrics-grid">
                        {/* Basic Info Card */}
                        <div className="metric-card basic-info">
                            <div className="card-header">
                                <span className="card-icon">📋</span>
                                <h3>Dataset Overview</h3>
                            </div>
                            <div className="card-content">
                                <div className="info-grid">
                                    <div className="info-item">
                                        <span className="info-label">Rows</span>
                                        <span className="info-value">{qualityMetrics.basic_info.num_rows.toLocaleString()}</span>
                                    </div>
                                    <div className="info-item">
                                        <span className="info-label">Columns</span>
                                        <span className="info-value">{qualityMetrics.basic_info.num_columns}</span>
                                    </div>
                                    <div className="info-item">
                                        <span className="info-label">Memory</span>
                                        <span className="info-value">{qualityMetrics.basic_info.memory_usage_mb} MB</span>
                                    </div>
                                    <div className="info-item">
                                        <span className="info-label">Total Cells</span>
                                        <span className="info-value">{qualityMetrics.basic_info.total_cells.toLocaleString()}</span>
                                    </div>
                                </div>
                            </div>
                        </div>

                        {/* Missing Values Card */}
                        <div className="metric-card missing-values">
                            <div className="card-header">
                                <span className="card-icon">❓</span>
                                <h3>Missing Values</h3>
                            </div>
                            <div className="card-content">
                                <div className="metric-main">
                                    <span className="metric-value">{qualityMetrics.missing_analysis.total_missing}</span>
                                    <span className="metric-percentage">
                                        ({qualityMetrics.missing_analysis.missing_percentage}%)
                                    </span>
                                </div>
                                <div
                                    className="severity-badge"
                                    style={{ backgroundColor: getSeverityColor(qualityMetrics.missing_analysis.severity) }}
                                >
                                    {qualityMetrics.missing_analysis.severity} Severity
                                </div>
                                <div className="metric-details">
                                    <span>{qualityMetrics.missing_analysis.columns_with_missing.length} columns affected</span>
                                </div>
                            </div>
                        </div>

                        {/* Duplicates Card */}
                        <div className="metric-card duplicates">
                            <div className="card-header">
                                <span className="card-icon">🔍</span>
                                <h3>Duplicate Rows</h3>
                            </div>
                            <div className="card-content">
                                <div className="metric-main">
                                    <span className="metric-value">{qualityMetrics.duplicate_analysis.exact_duplicates}</span>
                                    <span className="metric-percentage">
                                        ({qualityMetrics.duplicate_analysis.percentage_duplicates}%)
                                    </span>
                                </div>
                                <div
                                    className="severity-badge"
                                    style={{ backgroundColor: getSeverityColor(qualityMetrics.duplicate_analysis.severity) }}
                                >
                                    {qualityMetrics.duplicate_analysis.severity} Severity
                                </div>
                                <div className="metric-details">
                                    <span>Exact duplicate rows detected</span>
                                </div>
                            </div>
                        </div>

                        {/* Data Types Card */}
                        <div className="metric-card data-types">
                            <div className="card-header">
                                <span className="card-icon">🎯</span>
                                <h3>Data Types</h3>
                            </div>
                            <div className="card-content">
                                <div className="type-distribution">
                                    <div className="type-item">
                                        <span className="type-name">Numeric</span>
                                        <span className="type-count">
                                            {qualityMetrics.dtype_analysis.numeric_columns.length}
                                        </span>
                                    </div>
                                    <div className="type-item">
                                        <span className="type-name">Categorical</span>
                                        <span className="type-count">
                                            {qualityMetrics.dtype_analysis.categorical_columns.length}
                                        </span>
                                    </div>
                                    <div className="type-item">
                                        <span className="type-name">Datetime</span>
                                        <span className="type-count">
                                            {qualityMetrics.dtype_analysis.datetime_columns.length}
                                        </span>
                                    </div>
                                </div>
                            </div>
                        </div>

                        {/* Outliers Card */}
                        <div className="metric-card outliers">
                            <div className="card-header">
                                <span className="card-icon">📊</span>
                                <h3>Outlier Analysis</h3>
                            </div>
                            <div className="card-content">
                                <div className="outlier-summary">
                                    {Object.entries(qualityMetrics.outlier_analysis).slice(0, 3).map(([col, analysis]) => (
                                        <div key={col} className="outlier-item">
                                            <span className="column-name">{col}</span>
                                            <span className="outlier-count">{analysis.outliers_count} outliers</span>
                                            <span className="outlier-percentage">({analysis.outliers_percentage}%)</span>
                                        </div>
                                    ))}
                                </div>
                                {Object.keys(qualityMetrics.outlier_analysis).length > 3 && (
                                    <div className="more-items">
                                        +{Object.keys(qualityMetrics.outlier_analysis).length - 3} more columns
                                    </div>
                                )}
                            </div>
                        </div>
                    </div>
                </div>
            )}

            {/* Preprocessing Pipeline Grid */}
            {activeTab === 'pipeline' && (
                <div className="tab-content">
                    <div className="section-header">
                        <h2>Preprocessing Pipeline</h2>
                        <p>Step-by-step data transformation process</p>
                    </div>

                    <div className="pipeline-grid">
                        {preprocessingSteps.map((step, index) => (
                            <div key={step.step_name} className={`pipeline-step ${step.status}`}>
                                <div className="step-header">
                                    <div className="step-number">{(index + 1).toString().padStart(2, '0')}</div>
                                    <div className="step-title">
                                        <h3>{step.step_name}</h3>
                                        <span className="step-status">
                                            {getStatusIcon(step.status)} {step.status}
                                        </span>
                                    </div>
                                </div>

                                <div className="step-description">
                                    {step.description}
                                </div>

                                {step.changes && (
                                    <div className="step-changes">
                                        <h4>Changes Applied:</h4>
                                        {step.step_name === 'Type Detection' && (
                                            <div className="change-details">
                                                <div className="change-item">
                                                    <span>Discrete Columns:</span>
                                                    <strong>{step.changes.discrete_count}</strong>
                                                </div>
                                                <div className="change-item">
                                                    <span>Continuous Columns:</span>
                                                    <strong>{step.changes.continuous_count}</strong>
                                                </div>
                                            </div>
                                        )}

                                        {step.step_name === 'Missing Values Treatment' && (
                                            <div className="change-details">
                                                <div className="change-item">
                                                    <span>Missing Values Before:</span>
                                                    <strong>{step.changes.total_missing_before}</strong>
                                                </div>
                                                <div className="change-item">
                                                    <span>Missing Values After:</span>
                                                    <strong>{step.changes.total_missing_after}</strong>
                                                </div>
                                                <div className="change-item highlight">
                                                    <span>Values Imputed:</span>
                                                    <strong>{step.changes.total_missing_before - step.changes.total_missing_after}</strong>
                                                </div>
                                            </div>
                                        )}

                                        {step.step_name === 'Duplicate Removal' && (
                                            <div className="change-details">
                                                <div className="change-item">
                                                    <span>Rows Before:</span>
                                                    <strong>{step.changes.rows_before}</strong>
                                                </div>
                                                <div className="change-item">
                                                    <span>Rows After:</span>
                                                    <strong>{step.changes.rows_after}</strong>
                                                </div>
                                                <div className="change-item highlight">
                                                    <span>Duplicates Removed:</span>
                                                    <strong>{step.changes.duplicates_removed}</strong>
                                                </div>
                                            </div>
                                        )}
                                    </div>
                                )}

                                {step.sample_data && step.sample_data.length > 0 && (
                                    <div className="step-preview">
                                        <h4>Data Preview:</h4>
                                        <div className="preview-table">
                                            <div className="table-scroll-container">
                                                <table>
                                                    <thead>
                                                        <tr>
                                                            {Object.keys(step.sample_data[0]).slice(0, 4).map(key => (
                                                                <th key={key}>{key}</th>
                                                            ))}
                                                        </tr>
                                                    </thead>
                                                    <tbody>
                                                        {step.sample_data.slice(0, 3).map((row, idx) => (
                                                            <tr key={idx}>
                                                                {Object.values(row).slice(0, 4).map((value, cellIdx) => (
                                                                    <td key={cellIdx}>{String(value)}</td>
                                                                ))}
                                                            </tr>
                                                        ))}
                                                    </tbody>
                                                </table>
                                            </div>
                                        </div>
                                    </div>
                                )}
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {/* Column Changes Grid */}
            {activeTab === 'changes' && (
                <div className="tab-content">
                    <div className="section-header">
                        <h2>Column Changes Analysis</h2>
                        <p>Detailed view of transformations applied to each column</p>
                        <div className="columns-count">
                            Total Columns: {columnChanges.length} | Selected: {selectedColumns.size}
                        </div>
                    </div>

                    <div className="changes-summary">
                        <div className="summary-card">
                            <span className="summary-value">
                                {columnChanges.filter(c => c.has_changes).length}
                            </span>
                            <span className="summary-label">Columns Modified</span>
                        </div>
                        <div className="summary-card">
                            <span className="summary-value">
                                {columnChanges.filter(c => c.original_dtype !== c.processed_dtype).length}
                            </span>
                            <span className="summary-label">Type Changes</span>
                        </div>
                        <div className="summary-card">
                            <span className="summary-value">
                                {columnChanges.filter(c => c.original_missing > c.processed_missing).length}
                            </span>
                            <span className="summary-label">Missing Values Treated</span>
                        </div>
                        <div className="summary-card">
                            <span className="summary-value">
                                {selectedColumns.size}
                            </span>
                            <span className="summary-label">Selected Columns</span>
                        </div>
                    </div>

                    {/* Selection Controls */}
                    <div className="selection-controls">
                        <div className="select-all-container">
                            <label className="select-all-checkbox">
                                <input
                                    type="checkbox"
                                    checked={selectedColumns.size === columnChanges.length && columnChanges.length > 0}
                                    onChange={handleSelectAll}
                                    disabled={columnChanges.length === 0}
                                />
                                <span className="checkmark"></span>
                                {selectedColumns.size === columnChanges.length && columnChanges.length > 0 ? 'Deselect All' : 'Select All'}
                            </label>
                        </div>
                        {selectedColumns.size > 0 && (
                            <div className="selection-actions">
                                <button className="btn-secondary btn-small">
                                    Use Selected ({selectedColumns.size})
                                </button>                             
                            </div>
                        )}
                    </div>

                    <div className="changes-grid">
                        <div className="changes-header">
                            <div className="column-number-header">#</div>
                            <div className="checkbox-column">
                                <span>Select</span>
                            </div>
                            <div>Column Name</div>
                            <div>Data Type</div>
                            <div>Missing Values</div>
                            <div>Changes Applied</div>
                        </div>

                        {columnChanges.map((column, index) => (
                            <div key={column.column} className={`changes-row ${column.has_changes ? 'has-changes' : ''} ${selectedColumns.has(column.column) ? 'selected' : ''}`}>
                                <div className="column-number">
                                    {index + 1}
                                </div>
                                <div className="checkbox-column">
                                    <label className="column-checkbox">
                                        <input
                                            type="checkbox"
                                            checked={selectedColumns.has(column.column)}
                                            onChange={() => handleColumnSelect(column.column)}
                                        />
                                        <span className="checkmark"></span>
                                    </label>
                                </div>
                                <div className="column-info">
                                    <span className="column-name">{column.column}</span>
                                    {column.has_changes && <span className="change-indicator">●</span>}
                                </div>

                                <div className="type-info">
                                    <span className={`type-badge ${column.original_dtype !== column.processed_dtype ? 'changed' : ''}`}>
                                        {column.processed_dtype}
                                    </span>
                                    {column.original_dtype !== column.processed_dtype && (
                                        <span className="type-change">→ {column.processed_dtype}</span>
                                    )}
                                </div>

                                <div className="missing-info">
                                    <div className="missing-comparison">
                                        <span className="before">{column.original_missing}</span>
                                        {column.original_missing !== column.processed_missing && (
                                            <span className="arrow">→</span>
                                        )}
                                        <span className="after">{column.processed_missing}</span>
                                    </div>
                                    {column.original_missing > column.processed_missing && (
                                        <span className="improvement">Improved</span>
                                    )}
                                </div>

                                <div className="changes-info">
                                    {column.changes.length > 0 ? (
                                        <div className="changes-list">
                                            {column.changes.map((change, idx) => (
                                                <span key={idx} className="change-tag">{change}</span>
                                            ))}
                                        </div>
                                    ) : (
                                        <span className="no-changes">No changes applied</span>
                                    )}
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {/* Action Buttons */}
            <div className="action-buttons">
                <button
                    className="btn-secondary"
                    onClick={() => Promise.all([loadQualityMetrics(), loadPreprocessingSteps(), loadColumnChanges()])}
                    disabled={isLoading}
                >
                    🔄 Refresh Data
                </button>
                <button
                    className="btn-primary"
                    onClick={applyPreprocessing}
                    disabled={isLoading || !datasetId}
                >
                    {isLoading ? '⏳ Processing...' : '⚡ Apply Preprocessing'}
                </button>
            </div>

            {/* Loading Overlay */}
            {isLoading && (
                <div className="loading-overlay">
                    <div className="loading-spinner"></div>
                    <p>Applying preprocessing transformations...</p>
                </div>
            )}
        </div>
    );
};

export default PreprocessingDetails;