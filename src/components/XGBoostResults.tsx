import React, { useState } from 'react';
import './ModelResults.css';

// ✅ Add this prop to enable callback to parent
interface XGBoostResultsProps {
    selectedVariables: string[];
    allSelectedVariables?: string[];
    targetVariable: string;
    woeTransformedData: Record<string, any[]>;
    onColumnSelect: (column: string) => void;
    selectedColumn: string;
    onToggleSelect?: (column: string) => void;
    onGenerateScoreCard?: (modelType: string) => void;
    generatingScoreCard?: boolean;
    onGotoScoreCard?: () => void;
    // ✅ New prop to notify parent with model results
    onResultsUpdate?: (results: any) => void;
    recordId?: number;
}

interface FeatureImportance {
    variable: string;
    importance: number;
    importance_percentage: number;
}

interface ModelStats {
    n_estimators: number;
    max_depth: number;
    learning_rate: number;
    n_observations: number;
    n_features: number;
}

interface ROCPoint {
    fpr: number;
    tpr: number;
    threshold: number;
}

interface KSCurvePoint {
    threshold: number;
    tpr: number;
    fpr: number;
    diff: number;
}

interface XGBoostResults {
    success: boolean;
    feature_importance: FeatureImportance[];
    gini_coefficient: number;
    auc: number;
    roc_data: ROCPoint[];
    model_stats: ModelStats;
    confusion_matrix?: number[][];
    accuracy?: number;
    precision?: number;
    recall?: number;
    f1?: number;
    ks_stat?: number;
    ks_threshold?: number;
    ks_curve?: KSCurvePoint[];
}

const XGBoostResults: React.FC<XGBoostResultsProps> = ({
    selectedVariables,
    allSelectedVariables,
    targetVariable,
    woeTransformedData,
    onColumnSelect,
    selectedColumn,
    onToggleSelect,
    onGenerateScoreCard,
    generatingScoreCard,
    onGotoScoreCard,
    onResultsUpdate,
    recordId
}) => {
    const [results, setResults] = useState<XGBoostResults | null>(null);
    const [loading, setLoading] = useState(false);
    const [showLegend, setShowLegend] = useState(false);
    const [confusionView, setConfusionView] = useState<'counts' | 'percent'>('counts');
    const [activeTab, setActiveTab] = useState<'importance' | 'roc' | 'confusion' | 'ks' | 'parameters'>('importance');

    // ✅ Updated to trigger parent callback when model runs
    const runXGBoost = async () => {
        if (selectedVariables.length === 0) {
            alert('Please select at least one variable from the Important Column Selection step');
            return;
        }

        setLoading(true);
        try {
            const response = await fetch('http://localhost:5000/api/xgboost', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    selected_variables: selectedVariables,
                    target: targetVariable,
                    woe_transformed_data: woeTransformedData,
                    record_id: recordId
                })
            });

            const data = await response.json();
            if (data.success) {
                setResults(data);

                // ✅ Call parent update callback if provided
                if (onResultsUpdate) {
                    onResultsUpdate(data);
                }
            } else {
                alert(`Error: ${data.error}`);
            }
        } catch (error) {
            alert(`Error running XGBoost: ${error}`);
        } finally {
            setLoading(false);
        }
    };

    const formatNumber = (num: number | null | undefined, decimals: number = 4): string => {
        if (num === null || num === undefined || !Number.isFinite(num)) return 'N/A';
        return Number(num).toFixed(decimals);
    };

    const getKSInterpretation = (ksStat: number | null | undefined): string => {
        if (ksStat === null || ksStat === undefined || !Number.isFinite(ksStat)) return 'No data';
        if (ksStat > 0.4) return 'Excellent separation';
        if (ksStat > 0.2) return 'Good separation';
        return 'Weak separation';
    };

    const renderFeatureImportance = () => {
        if (!results?.feature_importance || results.feature_importance.length === 0) {
            return <div style={{ color: '#f0f6fc', padding: '20px', textAlign: 'center' }}>No feature importance data available</div>;
        }

        return (
            <div className="feature-importance-table">
                <h4>Feature Importance (Gain)</h4>
                <table>
                    <thead>
                        <tr>
                            <th>Rank</th>
                            <th>Variable</th>
                            <th>Importance</th>
                            <th>Percentage</th>
                            <th>Cumulative %</th>
                        </tr>
                    </thead>
                    <tbody>
                        {results.feature_importance.map((feature, index) => {
                            const cumulativePercentage = results.feature_importance
                                .slice(0, index + 1)
                                .reduce((sum, f) => sum + f.importance_percentage, 0);

                            return (
                                <tr key={index} className={index < 3 ? 'top-feature' : ''}>
                                    <td>#{index + 1}</td>
                                    <td>{feature.variable}</td>
                                    <td>{formatNumber(feature.importance)}</td>
                                    <td>{formatNumber(feature.importance_percentage, 2)}%</td>
                                    <td>{formatNumber(cumulativePercentage, 2)}%</td>
                                </tr>
                            );
                        })}
                    </tbody>
                </table>
                <div className="feature-importance-note">
                    <p><strong>Note:</strong> Importance is calculated based on the average gain across all splits where the feature is used.</p>
                </div>
            </div>
        );
    };

    const renderModelParameters = () => {
        if (!results?.model_stats) {
            return <div style={{ color: '#f0f6fc', padding: '20px', textAlign: 'center' }}>No model parameters available</div>;
        }

        return (
            <div className="parameters-panel">
                <h4>XGBoost Model Parameters</h4>
                <div className="parameters-grid">
                    <div className="parameter-item">
                        <label>Number of Trees:</label>
                        <span>{results.model_stats.n_estimators}</span>
                    </div>
                    <div className="parameter-item">
                        <label>Max Depth:</label>
                        <span>{results.model_stats.max_depth}</span>
                    </div>
                    <div className="parameter-item">
                        <label>Learning Rate:</label>
                        <span>{formatNumber(results.model_stats.learning_rate)}</span>
                    </div>
                    <div className="parameter-item">
                        <label>Number of Features:</label>
                        <span>{results.model_stats.n_features}</span>
                    </div>
                    <div className="parameter-item">
                        <label>Observations:</label>
                        <span>{results.model_stats.n_observations}</span>
                    </div>
                </div>

                <div className="parameters-explanation">
                    <h5>Parameter Explanation:</h5>
                    <ul>
                        <li><strong>Number of Trees:</strong> Total number of boosting rounds (higher = more complex model)</li>
                        <li><strong>Max Depth:</strong> Maximum depth of each tree (higher = more complex, risk of overfitting)</li>
                        <li><strong>Learning Rate:</strong> Step size shrinkage (lower = more robust, but requires more trees)</li>
                        <li><strong>Number of Features:</strong> Variables used in the model</li>
                        <li><strong>Observations:</strong> Number of training samples</li>
                    </ul>
                </div>
            </div>
        );
    };

    const renderROCCurve = () => {
        if (!results?.roc_data || results.roc_data.length === 0) {
            return <div style={{ color: '#f0f6fc', padding: '20px', textAlign: 'center' }}>No ROC data available</div>;
        }

        const svgWidth = 400;
        const svgHeight = 300;
        const margin = 40;
        const plotWidth = svgWidth - 2 * margin;
        const plotHeight = svgHeight - 2 * margin;

        const points = results.roc_data.map(point => ({
            x: margin + (point.fpr || 0) * plotWidth,
            y: margin + (1 - (point.tpr || 0)) * plotHeight
        }));

        const pathData = points.reduce((path, point, index) => {
            return path + (index === 0 ? `M ${point.x} ${point.y}` : ` L ${point.x} ${point.y}`);
        }, '');

        return (
            <div className="roc-curve-container">
                <h4>ROC Curve</h4>
                <svg width={svgWidth} height={svgHeight} className="roc-svg">
                    {/* Grid lines */}
                    {[0, 0.2, 0.4, 0.6, 0.8, 1.0].map(val => (
                        <g key={val}>
                            <line
                                x1={margin + val * plotWidth}
                                y1={margin}
                                x2={margin + val * plotWidth}
                                y2={margin + plotHeight}
                                stroke="#30363d"
                                strokeWidth={1}
                            />
                            <line
                                x1={margin}
                                y1={margin + val * plotHeight}
                                x2={margin + plotWidth}
                                y2={margin + val * plotHeight}
                                stroke="#30363d"
                                strokeWidth={1}
                            />
                        </g>
                    ))}

                    {/* Diagonal reference line */}
                    <line
                        x1={margin}
                        y1={margin + plotHeight}
                        x2={margin + plotWidth}
                        y2={margin}
                        stroke="#8c8c8c"
                        strokeWidth={1}
                        strokeDasharray="5,5"
                    />

                    {/* ROC Curve */}
                    <path
                        d={pathData}
                        fill="none"
                        stroke="#ff6b6b"
                        strokeWidth={2}
                    />

                    {/* Axes */}
                    <line x1={margin} y1={margin} x2={margin} y2={margin + plotHeight} stroke="#f0f6fc" strokeWidth={2} />
                    <line x1={margin} y1={margin + plotHeight} x2={margin + plotWidth} y2={margin + plotHeight} stroke="#f0f6fc" strokeWidth={2} />

                    {/* Labels */}
                    <text x={svgWidth / 2} y={svgHeight - 5} textAnchor="middle" fill="#f0f6fc" fontSize="12">
                        False Positive Rate
                    </text>
                    <text x={15} y={svgHeight / 2} textAnchor="middle" fill="#f0f6fc" fontSize="12" transform={`rotate(-90, 15, ${svgHeight / 2})`}>
                        True Positive Rate
                    </text>

                    {/* Tick labels */}
                    {[0, 0.2, 0.4, 0.6, 0.8, 1.0].map(val => (
                        <g key={val}>
                            <text x={margin + val * plotWidth} y={margin + plotHeight + 15} textAnchor="middle" fill="#f0f6fc" fontSize="10">
                                {val.toFixed(1)}
                            </text>
                            <text x={margin - 10} y={margin + (1 - val) * plotHeight + 3} textAnchor="end" fill="#f0f6fc" fontSize="10">
                                {val.toFixed(1)}
                            </text>
                        </g>
                    ))}
                </svg>
                <div className="roc-stats">
                    <p><strong>AUC:</strong> {formatNumber(results.auc)}</p>
                    <p><strong>Gini Coefficient:</strong> {formatNumber(results.gini_coefficient)}</p>
                </div>
            </div>
        );
    };

    const renderConfusionMatrix = () => {
        const cm = results?.confusion_matrix;
        if (!cm || !Array.isArray(cm) || cm.length < 2) {
            return <div style={{ color: '#f0f6fc', padding: '20px', textAlign: 'center' }}>No confusion matrix available</div>;
        }

        const a00 = Number(cm[0][0] ?? 0);
        const a01 = Number(cm[0][1] ?? 0);
        const a10 = Number(cm[1][0] ?? 0);
        const a11 = Number(cm[1][1] ?? 0);
        const total = a00 + a01 + a10 + a11 || 1;

        const normalized = [
            [a00 / total, a01 / total],
            [a10 / total, a11 / total]
        ];

        const size = 260;
        const cell = size / 2;
        const pad = 20;

        const labelFill = '#f0f6fc';
        const gridStroke = '#30363d';
        const bg = 'transparent';

        const getFill = (_count: number, norm: number) => {
            const alpha = Math.min(0.9, 0.25 + norm * 1.2);
            return `rgba(255, 107, 107, ${alpha})`;
        };

        return (
            <div className="confusion-svg-panel">
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <h4 style={{ margin: 0 }}>Confusion Matrix</h4>
                    <div>
                        <button className="tab-btn" onClick={() => setConfusionView('counts')} style={{ marginRight: 8 }}>
                            Counts
                        </button>
                        <button className="tab-btn" onClick={() => setConfusionView('percent')}>
                            Percent
                        </button>
                    </div>
                </div>

                <svg width={size + pad * 2} height={size + pad * 2} style={{ background: bg }}>
                    {/* Labels */}
                    <text x={pad + cell} y={pad - 6} textAnchor="middle" fill={labelFill} fontSize={12}>Predicted</text>
                    <text x={pad + cell / 2} y={pad + size + 14} textAnchor="middle" fill={labelFill} fontSize={12} transform={`rotate(-90, ${pad + cell / 2}, ${pad + size / 2})`}>Actual</text>

                    {/* Grid cells */}
                    {[0, 1].map((r) =>
                        [0, 1].map((c) => {
                            const count = [[a00, a01], [a10, a11]][r][c];
                            const norm = normalized[r][c];
                            const x = pad + c * cell;
                            const y = pad + r * cell;
                            return (
                                <g key={`${r}-${c}`}>
                                    <rect x={x} y={y} width={cell} height={cell} fill={getFill(count, norm)} stroke={gridStroke} />
                                    <text x={x + cell / 2} y={y + cell / 2 - 6} textAnchor="middle" fill={labelFill} fontSize={14} fontWeight={700}>
                                        {confusionView === 'counts' ? String(count) : `${(norm * 100).toFixed(2)}%`}
                                    </text>
                                    <text x={x + cell / 2} y={y + cell / 2 + 14} textAnchor="middle" fill={labelFill} fontSize={11}>
                                        {confusionView === 'counts' ? `${((count / total) * 100).toFixed(2)}%` : `(${String(count)})`}
                                    </text>
                                </g>
                            );
                        })
                    )}

                    {/* Axis tick labels 0/1 */}
                    <text x={pad + cell / 2} y={pad + size + 4} textAnchor="middle" fill={labelFill} fontSize={12}>0</text>
                    <text x={pad + cell + cell / 2} y={pad + size + 4} textAnchor="middle" fill={labelFill} fontSize={12}>1</text>
                    <text x={pad - 8} y={pad + cell / 2 + 4} textAnchor="end" fill={labelFill} fontSize={12}>0</text>
                    <text x={pad - 8} y={pad + cell + cell / 2 + 4} textAnchor="end" fill={labelFill} fontSize={12}>1</text>
                </svg>
            </div>
        );
    };

    const renderKSCurve = () => {
        if (!results?.ks_curve || results.ks_curve.length === 0) {
            return <div style={{ color: '#f0f6fc', padding: '20px', textAlign: 'center' }}>No KS data available</div>;
        }

        const ksData = results.ks_curve;
        const width = 420;
        const height = 300;
        const margin = 40;
        const plotW = width - margin * 2;
        const plotH = height - margin * 2;

        // Find KS point
        const ksIndex = ksData.reduce((acc, cur, idx) =>
            (cur.diff || 0) > ((ksData[acc]?.diff) || 0) ? idx : acc, 0
        );
        const ksPoint = ksData[ksIndex];

        // Create paths
        const tprPath = ksData.map((p, i) =>
            `${i === 0 ? 'M' : 'L'} ${margin + (i / (ksData.length - 1)) * plotW} ${margin + (1 - (p.tpr || 0)) * plotH}`
        ).join(' ');

        const fprPath = ksData.map((p, i) =>
            `${i === 0 ? 'M' : 'L'} ${margin + (i / (ksData.length - 1)) * plotW} ${margin + (1 - (p.fpr || 0)) * plotH}`
        ).join(' ');

        return (
            <div className="ks-chart-container">
                <h4>Kolmogorov-Smirnov (KS) Curve</h4>
                <svg width={width} height={height} className="roc-svg">
                    {/* Grid */}
                    {[0, 0.2, 0.4, 0.6, 0.8, 1.0].map(val => (
                        <g key={val}>
                            <line
                                x1={margin + val * plotW}
                                y1={margin}
                                x2={margin + val * plotW}
                                y2={margin + plotH}
                                stroke="#30363d"
                                strokeWidth={1}
                            />
                            <line
                                x1={margin}
                                y1={margin + val * plotH}
                                x2={margin + plotW}
                                y2={margin + val * plotH}
                                stroke="#30363d"
                                strokeWidth={1}
                            />
                        </g>
                    ))}

                    {/* Curves */}
                    <path d={tprPath} fill="none" stroke="#52c41a" strokeWidth={2} />
                    <path d={fprPath} fill="none" stroke="#ff4d4f" strokeWidth={2} />

                    {/* KS line */}
                    {ksPoint && (
                        <g>
                            <line
                                x1={margin + (ksIndex / (ksData.length - 1)) * plotW}
                                y1={margin + (1 - (ksPoint.tpr || 0)) * plotH}
                                x2={margin + (ksIndex / (ksData.length - 1)) * plotW}
                                y2={margin + (1 - (ksPoint.fpr || 0)) * plotH}
                                stroke="#ffd700"
                                strokeWidth={2}
                            />
                            <circle
                                cx={margin + (ksIndex / (ksData.length - 1)) * plotW}
                                cy={margin + (1 - (ksPoint.tpr || 0)) * plotH}
                                r={4}
                                fill="#52c41a"
                            />
                            <circle
                                cx={margin + (ksIndex / (ksData.length - 1)) * plotW}
                                cy={margin + (1 - (ksPoint.fpr || 0)) * plotH}
                                r={4}
                                fill="#ff4d4f"
                            />
                        </g>
                    )}

                    {/* Axes */}
                    <line x1={margin} y1={margin} x2={margin} y2={margin + plotH} stroke="#f0f6fc" strokeWidth={2} />
                    <line x1={margin} y1={margin + plotH} x2={margin + plotW} y2={margin + plotH} stroke="#f0f6fc" strokeWidth={2} />

                    {/* Labels */}
                    <text x={width / 2} y={height - 5} textAnchor="middle" fill="#f0f6fc" fontSize="12">
                        Threshold
                    </text>
                    <text x={15} y={height / 2} textAnchor="middle" fill="#f0f6fc" fontSize="12" transform={`rotate(-90, 15, ${height / 2})`}>
                        Rate
                    </text>

                    {/* Legend */}
                    <rect x={width - 120} y={margin} width={100} height={40} fill="#161b22" stroke="#30363d" />
                    <text x={width - 110} y={margin + 15} fill="#52c41a" fontSize="10">TPR (Good)</text>
                    <text x={width - 110} y={margin + 30} fill="#ff4d4f" fontSize="10">FPR (Bad)</text>
                </svg>

                <div className="ks-stats">
                    <p><strong>KS Statistic:</strong> {formatNumber(results.ks_stat)}</p>
                    <p><strong>KS Threshold:</strong> {formatNumber(results.ks_threshold)}</p>
                    <p><strong>Interpretation:</strong> {getKSInterpretation(results.ks_stat)}</p>
                </div>
            </div>
        );
    };

    return (
        <div className="model-results-container">
            <div className="model-header">
                <div className="model-title">
                    <h3>XGBoost Analysis</h3>
                    <button
                        className="legend-toggle"
                        onClick={() => setShowLegend(!showLegend)}
                    >
                        {showLegend ? 'Hide Legend' : 'Show Legend'}
                    </button>
                </div>

                {showLegend && (
                    <div className="legend-panel">
                        <h4>XGBoost Legend</h4>
                        <div className="legend-section">
                            <h5>Feature Importance (Gain):</h5>
                            <ul>
                                <li>Measures average improvement in accuracy when using the feature</li>
                                <li>Higher values indicate more important features</li>
                                <li>Cumulative % shows total importance covered by top features</li>
                                <li>Top 3 features are highlighted in green</li>
                            </ul>
                        </div>
                        <div className="legend-section">
                            <h5>Model Parameters:</h5>
                            <ul>
                                <li><strong>Number of Trees:</strong> More trees = more complex model</li>
                                <li><strong>Max Depth:</strong> Deeper trees = more complex, risk of overfitting</li>
                                <li><strong>Learning Rate:</strong> Lower = more robust, needs more trees</li>
                            </ul>
                        </div>
                        <div className="legend-section">
                            <h5>Performance Metrics:</h5>
                            <ul>
                                <li><strong>Gini &gt; 0.6:</strong> Excellent model</li>
                                <li><strong>Gini 0.4-0.6:</strong> Good model</li>
                                <li><strong>Gini &lt; 0.4:</strong> Poor model</li>
                                <li><strong>KS &gt; 0.4:</strong> Excellent separation</li>
                                <li><strong>KS 0.2-0.4:</strong> Good separation</li>
                                <li><strong>KS &lt; 0.2:</strong> Weak separation</li>
                            </ul>
                        </div>
                    </div>
                )}
            </div>

            <div className="model-content">
                <div className="selected-variables-panel">
                    <h4>Selected Variables ({(allSelectedVariables || selectedVariables).length})</h4>
                    <div className="variables-list">
                        {(allSelectedVariables || selectedVariables).map((variable) => (
                            <div
                                key={variable}
                                className={`variable-item ${selectedColumn === variable ? 'selected' : ''}`}
                            >
                                <span className="variable-name" onClick={(e) => { e.stopPropagation(); onColumnSelect(variable); }}>{variable}</span>
                                <input
                                    type="checkbox"
                                    checked={selectedVariables.includes(variable)}
                                    onClick={(e) => e.stopPropagation()}
                                    onChange={() => onToggleSelect ? onToggleSelect(variable) : undefined}
                                />
                            </div>
                        ))}
                    </div>

                    <button
                        className="run-model-btn"
                        onClick={runXGBoost}
                        disabled={loading || selectedVariables.length === 0}
                    >
                        {loading ? 'Running XGBoost...' : 'Run XGBoost'}
                    </button>

                    {results && onGenerateScoreCard && (
                        <button
                            className="run-model-btn"
                            onClick={() => {
                                try {
                                    if (typeof onGotoScoreCard === 'function') onGotoScoreCard();
                                } catch (e) { }
                                onGenerateScoreCard('xgboost');
                            }}
                            disabled={generatingScoreCard || selectedVariables.length === 0}
                            style={{ marginTop: '10px', background: '#d46b08' }}
                        >
                            {generatingScoreCard ? 'Generating...' : 'Generate Score Card (XGBoost)'}
                        </button>
                    )}
                </div>

                {results && (
                    <div className="results-panel">
                        <div className="results-tabs">
                            <button
                                className={`tab-btn ${activeTab === 'importance' ? 'active' : ''}`}
                                onClick={() => setActiveTab('importance')}
                            >
                                Feature Importance
                            </button>
                            <button
                                className={`tab-btn ${activeTab === 'parameters' ? 'active' : ''}`}
                                onClick={() => setActiveTab('parameters')}
                            >
                                Model Parameters
                            </button>
                            <button
                                className={`tab-btn ${activeTab === 'roc' ? 'active' : ''}`}
                                onClick={() => setActiveTab('roc')}
                            >
                                ROC Curve
                            </button>
                            <button
                                className={`tab-btn ${activeTab === 'confusion' ? 'active' : ''}`}
                                onClick={() => setActiveTab('confusion')}
                            >
                                Confusion Matrix
                            </button>
                            <button
                                className={`tab-btn ${activeTab === 'ks' ? 'active' : ''}`}
                                onClick={() => setActiveTab('ks')}
                            >
                                KS Statistic
                            </button>
                        </div>

                        <div className="tab-content">
                            {activeTab === 'importance' && renderFeatureImportance()}
                            {activeTab === 'parameters' && renderModelParameters()}
                            {activeTab === 'roc' && renderROCCurve()}
                            {activeTab === 'confusion' && renderConfusionMatrix()}
                            {activeTab === 'ks' && renderKSCurve()}
                        </div>

                        <div className="model-summary">
                            <h4>Model Summary</h4>
                            <div className="summary-grid">
                                {activeTab === 'confusion' && results.accuracy !== undefined ? (
                                    <>
                                        <div className="summary-item">
                                            <label>Accuracy:</label>
                                            <span>{formatNumber(results.accuracy)}</span>
                                        </div>
                                        <div className="summary-item">
                                            <label>Precision:</label>
                                            <span>{formatNumber(results.precision)}</span>
                                        </div>
                                        <div className="summary-item">
                                            <label>Recall:</label>
                                            <span>{formatNumber(results.recall)}</span>
                                        </div>
                                        <div className="summary-item">
                                            <label>F1 Score:</label>
                                            <span>{formatNumber(results.f1)}</span>
                                        </div>
                                    </>
                                ) : activeTab === 'roc' ? (
                                    <div style={{ color: '#f0f6fc', padding: 12 }}>
                                        <h5 style={{ marginTop: 0 }}>Gini Coefficient:</h5>
                                        <div>Ranges from 0 to 1 (higher is better)</div>
                                        <ul style={{ marginTop: 8 }}>
                                            <li>{'> 0.6'}: Excellent model</li>
                                            <li>0.4 - 0.6: Good model</li>
                                            <li>{'< 0.4'}: Poor model</li>
                                        </ul>
                                    </div>
                                ) : activeTab === 'importance' ? (
                                    <>
                                        <div className="summary-item">
                                            <label>Top Feature:</label>
                                            <span>{results.feature_importance[0]?.variable || 'N/A'}</span>
                                        </div>
                                        <div className="summary-item">
                                            <label>Top Feature Importance:</label>
                                            <span>{results.feature_importance[0] ? formatNumber(results.feature_importance[0].importance_percentage, 2) + '%' : 'N/A'}</span>
                                        </div>
                                        <div className="summary-item">
                                            <label>Features &gt; 5%:</label>
                                            <span>{results.feature_importance.filter(f => f.importance_percentage > 5).length}</span>
                                        </div>
                                        <div className="summary-item">
                                            <label>Total Features:</label>
                                            <span>{results.feature_importance.length}</span>
                                        </div>
                                    </>
                                ) : activeTab === 'parameters' ? (
                                    <>
                                        <div className="summary-item">
                                            <label>Number of Trees:</label>
                                            <span>{results.model_stats.n_estimators}</span>
                                        </div>
                                        <div className="summary-item">
                                            <label>Max Depth:</label>
                                            <span>{results.model_stats.max_depth}</span>
                                        </div>
                                        <div className="summary-item">
                                            <label>Learning Rate:</label>
                                            <span>{formatNumber(results.model_stats.learning_rate)}</span>
                                        </div>
                                        <div className="summary-item">
                                            <label>Observations:</label>
                                            <span>{results.model_stats.n_observations}</span>
                                        </div>
                                    </>
                                ) : activeTab === 'ks' ? (
                                    <div style={{ color: '#f0f6fc', padding: 12 }}>
                                        <div><strong>KS statistic:</strong> {formatNumber(results.ks_stat)}</div>
                                        <div><strong>KS threshold:</strong> {formatNumber(results.ks_threshold)}</div>
                                        <div style={{ marginTop: 8, fontSize: 12, color: '#8b949e' }}>
                                            <strong>Interpretation:</strong> {getKSInterpretation(results.ks_stat)}
                                        </div>
                                    </div>
                                ) : (
                                    <>
                                        <div className="summary-item">
                                            <label>Gini Coefficient:</label>
                                            <span>{formatNumber(results.gini_coefficient)}</span>
                                        </div>
                                        <div className="summary-item">
                                            <label>AUC:</label>
                                            <span>{formatNumber(results.auc)}</span>
                                        </div>
                                        {results.accuracy !== undefined && (
                                            <>
                                                <div className="summary-item">
                                                    <label>Accuracy:</label>
                                                    <span>{formatNumber(results.accuracy)}</span>
                                                </div>
                                                <div className="summary-item">
                                                    <label>Precision:</label>
                                                    <span>{formatNumber(results.precision)}</span>
                                                </div>
                                            </>
                                        )}
                                    </>
                                )}
                            </div>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
};

export default XGBoostResults;
