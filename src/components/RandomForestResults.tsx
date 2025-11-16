import React, { useState } from 'react';
import './ModelResults.css'; // We'll create this shared CSS

interface RandomForestResultsProps {
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
    n_observations: number;
    n_features: number;
    oob_score?: number;
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

interface RandomForestResults {
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

const RandomForestResults: React.FC<RandomForestResultsProps> = ({
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
    const [results, setResults] = useState<RandomForestResults | null>(null);
    const [loading, setLoading] = useState(false);
    const [showLegend, setShowLegend] = useState(false);
    const [confusionView, setConfusionView] = useState<'counts' | 'percent'>('counts');
    const [activeTab, setActiveTab] = useState<'importance' | 'roc' | 'confusion' | 'ks'>('importance');

    const runRandomForest = async () => {
        if (selectedVariables.length === 0) {
            alert('Please select at least one variable from the Important Column Selection step');
            return;
        }

        setLoading(true);
        try {
            const response = await fetch('http://localhost:5000/api/random-forest', {
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
                
                // ADD THIS: Call the callback to update parent state
                if (onResultsUpdate) {
                    onResultsUpdate(data);
                }
            } else {
                alert(`Error: ${data.error}`);
            }
        } catch (error) {
            alert(`Error running Random Forest: ${error}`);
        } finally {
            setLoading(false);
        }
    };

    const formatNumber = (num: number, decimals: number = 4) => {
        return Number(num).toFixed(decimals);
    };

    const renderFeatureImportance = () => {
        if (!results?.feature_importance) return null;

        return (
            <div className="feature-importance-table">
                <h4>Feature Importance</h4>
                <table>
                    <thead>
                        <tr>
                            <th>Variable</th>
                            <th>Importance</th>
                            <th>Percentage</th>
                        </tr>
                    </thead>
                    <tbody>
                        {results.feature_importance.map((feature, index) => (
                            <tr key={index}>
                                <td>{feature.variable}</td>
                                <td>{formatNumber(feature.importance)}</td>
                                <td>{formatNumber(feature.importance_percentage, 2)}%</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        );
    };

    const renderROCCurve = () => {
        if (!results?.roc_data) return null;

        const svgWidth = 400;
        const svgHeight = 300;
        const margin = 40;
        const plotWidth = svgWidth - 2 * margin;
        const plotHeight = svgHeight - 2 * margin;

        const points = results.roc_data.map(point => ({
            x: margin + point.fpr * plotWidth,
            y: margin + (1 - point.tpr) * plotHeight
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
                        stroke="#1890ff"
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
        if (!cm || !Array.isArray(cm) || cm.length < 2) return <div style={{ color: '#f0f6fc' }}>No confusion matrix available</div>;

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
            return `rgba(24,144,255,${alpha})`;
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

    return (
        <div className="model-results-container">
            <div className="model-header">
                <div className="model-title">
                    <h3>Random Forest Analysis</h3>
                    <button
                        className="legend-toggle"
                        onClick={() => setShowLegend(!showLegend)}
                    >
                        {showLegend ? 'Hide Legend' : 'Show Legend'}
                    </button>
                </div>

                {showLegend && (
                    <div className="legend-panel">
                        <h4>Random Forest Legend</h4>
                        <div className="legend-section">
                            <h5>Feature Importance:</h5>
                            <ul>
                                <li>Shows relative importance of each variable</li>
                                <li>Higher percentage = more important for predictions</li>
                                <li>Sum of all importances = 100%</li>
                            </ul>
                        </div>
                        <div className="legend-section">
                            <h5>Gini Coefficient:</h5>
                            <ul>
                                <li>Ranges from 0 to 1 (higher is better)</li>
                                <li>&gt; 0.6: Excellent model</li>
                                <li>0.4 - 0.6: Good model</li>
                                <li>&lt; 0.4: Poor model</li>
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
                        onClick={runRandomForest}
                        disabled={loading || selectedVariables.length === 0}
                    >
                        {loading ? 'Running...' : 'Run Random Forest'}
                    </button>

                    {results && onGenerateScoreCard && (
                        <button
                            className="run-model-btn"
                            onClick={() => {
                                try {
                                    if (typeof onGotoScoreCard === 'function') onGotoScoreCard();
                                } catch (e) { }
                                onGenerateScoreCard('random_forest');
                            }}
                            disabled={generatingScoreCard || selectedVariables.length === 0}
                            style={{ marginTop: '10px' }}
                        >
                            {generatingScoreCard ? 'Generating...' : 'Generate Score Card (RF)'}
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
                            {activeTab === 'roc' && renderROCCurve()}
                            {activeTab === 'confusion' && renderConfusionMatrix()}
                            {activeTab === 'ks' && results.ks_curve && (
                                <div className="ks-panel">
                                    <h4>KS Curve</h4>
                                    <KSChart ks_curve={results.ks_curve} ks_stat={results.ks_stat ?? 0} />
                                </div>
                            )}
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
                                            <span>{formatNumber(results.precision ?? 0)}</span>
                                        </div>
                                        <div className="summary-item">
                                            <label>Recall:</label>
                                            <span>{formatNumber(results.recall ?? 0)}</span>
                                        </div>
                                        <div className="summary-item">
                                            <label>F1 Score:</label>
                                            <span>{formatNumber(results.f1 ?? 0)}</span>
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
                                            <label>Number of Trees:</label>
                                            <span>{results.model_stats.n_estimators}</span>
                                        </div>
                                        <div className="summary-item">
                                            <label>Max Depth:</label>
                                            <span>{results.model_stats.max_depth}</span>
                                        </div>
                                        <div className="summary-item">
                                            <label>OOB Score:</label>
                                            <span>{results.model_stats.oob_score ? formatNumber(results.model_stats.oob_score) : 'N/A'}</span>
                                        </div>
                                        <div className="summary-item">
                                            <label>Observations:</label>
                                            <span>{results.model_stats.n_observations}</span>
                                        </div>
                                    </>
                                ) : activeTab === 'ks' ? (
                                    <div style={{ color: '#f0f6fc', padding: 12 }}>
                                        <div><strong>KS statistic:</strong> {results.ks_stat !== undefined ? formatNumber(results.ks_stat) : 'N/A'} at threshold {results.ks_threshold !== undefined && results.ks_threshold !== null ? formatNumber(results.ks_threshold) : 'N/A'}</div>
                                        <div style={{ marginTop: 8, fontSize: 12, color: '#8b949e' }}>Higher KS (closer to 1) indicates better separation; &gt;0.4 excellent, 0.2–0.4 good, &lt;0.2 weak.</div>
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
                                                    <span>{formatNumber(results.precision ?? 0)}</span>
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

// KS Chart component (same as logistic regression)
const KSChart: React.FC<{ ks_curve: KSCurvePoint[] | undefined; ks_stat: number }> = ({ ks_curve, ks_stat }) => {
    if (!ks_curve || ks_curve.length === 0) return <div style={{ color: '#f0f6fc' }}>No KS data available</div>;

    const _fmt = (n: number, d = 4) => Number(n).toFixed(d);

    const width = 420;
    const height = 300;
    const margin = 40;
    const plotW = width - margin * 2;
    const plotH = height - margin * 2;

    // use ks_curve sorted by threshold (they usually come in threshold order)
    const points = ks_curve.map(p => ({ x: margin + p.threshold * plotW, fpr: margin + (1 - p.fpr) * plotH, tpr: margin + (1 - p.tpr) * plotH, diff: p.diff, threshold: p.threshold }));

    // For markers, find max diff index
    const ksIndex = ks_curve.reduce((acc, cur, idx) => (cur.diff > (ks_curve[acc]?.diff ?? 0) ? idx : acc), 0);
    const ksPoint = points[ksIndex];

    const tprPath = ks_curve.map((p, i) => `${i === 0 ? 'M' : 'L'} ${margin + i * (plotW / (ks_curve.length - 1))} ${margin + (1 - p.tpr) * plotH}`).join(' ');
    const fprPath = ks_curve.map((p, i) => `${i === 0 ? 'M' : 'L'} ${margin + i * (plotW / (ks_curve.length - 1))} ${margin + (1 - p.fpr) * plotH}`).join(' ');

    return (
        <div className="ks-chart-container">
            <svg width={width} height={height} className="roc-svg">
                {/* axes */}
                <line x1={margin} y1={margin} x2={margin} y2={margin + plotH} stroke="#f0f6fc" />
                <line x1={margin} y1={margin + plotH} x2={margin + plotW} y2={margin + plotH} stroke="#f0f6fc" />
                {/* paths */}
                <path d={tprPath} fill="none" stroke="#52c41a" strokeWidth={2} />
                <path d={fprPath} fill="none" stroke="#ff4d4f" strokeWidth={2} />
                {/* KS marker */}
                {ksPoint && (
                    <g>
                        <line x1={ksPoint.x} y1={margin} x2={ksPoint.x} y2={margin + plotH} stroke="#58a6ff" strokeDasharray="4,4" />
                        <text x={ksPoint.x} y={margin - 8} textAnchor="middle" fill="#58a6ff">KS={_fmt(ks_stat, 4)}</text>
                    </g>
                )}
            </svg>
            <div style={{ marginTop: 8, color: '#f0f6fc' }} />
        </div>
    );
};

export default RandomForestResults;
