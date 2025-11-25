import React, { useState, useEffect } from 'react';
import './ModelResults.css';

interface StackingResultsProps {
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
  triggerRegression?: number; // Trigger count to run regression from sidebar
}

interface MetaLearnerWeights {
  logistic_regression: number;
  random_forest: number;
  xgboost: number;
  intercept?: number;
}

interface BaseModelPerformance {
  model: string;
  auc: number;
  gini: number;
  recall: number;
  precision: number;
  f1: number;
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

interface StackingResults {
  success: boolean;
  meta_learner_weights: MetaLearnerWeights;
  base_models_performance: BaseModelPerformance[];
  ensemble_performance: {
    gini_coefficient: number;
    auc: number;
    accuracy?: number;
    precision?: number;
    recall?: number;
    f1?: number;
    ks_stat?: number;
    ks_threshold?: number;
  };
  roc_data: ROCPoint[];
  confusion_matrix?: number[][];
  ks_curve?: KSCurvePoint[];
}

const StackingResults: React.FC<StackingResultsProps> = ({
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
  recordId,
  triggerRegression
}) => {
  const [results, setResults] = useState<StackingResults | null>(null);
  const [loading, setLoading] = useState(false);
  const [confusionView, setConfusionView] = useState<'counts' | 'percent'>('counts');

  // Watch for trigger from sidebar button
  useEffect(() => {
    if (triggerRegression && triggerRegression > 0) {
      runStacking();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [triggerRegression]);

  const runStacking = async () => {
    if (selectedVariables.length === 0) {
      alert('Please select at least one variable from the Important Column Selection step');
      return;
    }

    setLoading(true);
    try {
      const response = await fetch('http://localhost:5000/api/stacking', {
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
        if (onResultsUpdate) {
          onResultsUpdate(data);
        }
      } else {
        alert(`Error: ${data.error}`);
      }
    } catch (error) {
      alert(`Error running stacking ensemble: ${error}`);
    } finally {
      setLoading(false);
    }
  };

  const formatNumber = (num: number, decimals: number = 4) => {
    return Number(num).toFixed(decimals);
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
            stroke="#52c41a"
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
          <p><strong>AUC:</strong> {formatNumber(results.ensemble_performance.auc)}</p>
          <p><strong>Gini Coefficient:</strong> {formatNumber(results.ensemble_performance.gini_coefficient)}</p>
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
      return `rgba(82, 196, 26, ${alpha})`;
    };

    return (
      <div className="confusion-svg-panel">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', marginBottom: '12px' }}>
          <button className="view-toggle-btn" onClick={() => setConfusionView('counts')} style={{ marginRight: 8 }}>
              Counts
            </button>
          <button className="view-toggle-btn" onClick={() => setConfusionView('percent')}>
              Percent
            </button>
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
      return <div className="no-data-message">No KS curve data available</div>;
    }

    const svgWidth = 400;
    const svgHeight = 300;
    const margin = 40;
    const plotWidth = svgWidth - 2 * margin;
    const plotHeight = svgHeight - 2 * margin;

    const maxDiff = Math.max(...results.ks_curve.map(p => Math.abs(p.diff || 0)), 1);
    const ksData = results.ks_curve;
    const dataLength = ksData.length;
    const divisor = dataLength > 1 ? dataLength - 1 : 1;

    const tprPoints = ksData.map((point, idx) => ({
      x: margin + (idx / divisor) * plotWidth,
      y: margin + (1 - (point.tpr || 0)) * plotHeight
    }));

    const fprPoints = ksData.map((point, idx) => ({
      x: margin + (idx / divisor) * plotWidth,
      y: margin + (1 - (point.fpr || 0)) * plotHeight
    }));

    const diffPoints = ksData.map((point, idx) => ({
      x: margin + (idx / divisor) * plotWidth,
      y: margin + (1 - Math.abs(point.diff || 0) / maxDiff) * plotHeight
    }));

    const tprPath = tprPoints.reduce((path, point, index) => {
      return path + (index === 0 ? `M ${point.x} ${point.y}` : ` L ${point.x} ${point.y}`);
    }, '');

    const fprPath = fprPoints.reduce((path, point, index) => {
      return path + (index === 0 ? `M ${point.x} ${point.y}` : ` L ${point.x} ${point.y}`);
    }, '');

    const diffPath = diffPoints.reduce((path, point, index) => {
      return path + (index === 0 ? `M ${point.x} ${point.y}` : ` L ${point.x} ${point.y}`);
    }, '');

    return (
      <div className="ks-chart-container">
        <svg width={svgWidth} height={svgHeight} className="roc-svg" style={{ maxWidth: '100%', height: 'auto' }}>
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

          {/* TPR curve */}
          <path d={tprPath} fill="none" stroke="#52c41a" strokeWidth={2} />
          {/* FPR curve */}
          <path d={fprPath} fill="none" stroke="#ff4d4f" strokeWidth={2} />
          {/* Difference curve */}
          <path d={diffPath} fill="none" stroke="#1890ff" strokeWidth={2} strokeDasharray="5,5" />

          {/* Axes */}
          <line x1={margin} y1={margin} x2={margin} y2={margin + plotHeight} stroke="#f0f6fc" strokeWidth={2} />
          <line x1={margin} y1={margin + plotHeight} x2={margin + plotWidth} y2={margin + plotHeight} stroke="#f0f6fc" strokeWidth={2} />

          {/* Labels */}
          <text x={svgWidth / 2} y={svgHeight - 5} textAnchor="middle" fill="#f0f6fc" fontSize="12">
            Threshold
          </text>
          <text x={15} y={svgHeight / 2} textAnchor="middle" fill="#f0f6fc" fontSize="12" transform={`rotate(-90, 15, ${svgHeight / 2})`}>
            Rate
          </text>
        </svg>
        <div style={{ marginTop: '8px', color: '#f0f6fc', fontSize: '13px' }}>
          <p style={{ margin: '4px 0' }}><strong>KS Statistic:</strong> {results.ensemble_performance.ks_stat ? formatNumber(results.ensemble_performance.ks_stat) : 'N/A'}</p>
          <p style={{ margin: '4px 0' }}><strong>Optimal Threshold:</strong> {results.ensemble_performance.ks_threshold ? formatNumber(results.ensemble_performance.ks_threshold) : 'N/A'}</p>
        </div>
      </div>
    );
  };

  return (
    <div className="model-results-container">
      {loading && (
        <div className="loading-container">
          <div className="loading-spinner"></div>
          <p>Running Stacking Ensemble...</p>
        </div>
      )}

      {!loading && !results && (
        <div className="no-results-message">
          <p>Click "Run Stacking Ensemble" to train the model</p>
        </div>
      )}

      {results && (
        <>
          {/* Top Section: 3 Graphs Side by Side */}
          <div className="model-graphs-section">
            <div className="graph-card">
              <h4>ROC Curve</h4>
              {renderROCCurve()}
            </div>
            <div className="graph-card">
              <h4>Confusion Matrix</h4>
              {renderConfusionMatrix()}
            </div>
            <div className="graph-card">
              <h4>KS Statistics</h4>
              {renderKSCurve()}
            </div>
      </div>

          {/* Bottom Section: All Details */}
          <div className="model-details-section">
            {/* Meta-Learner Weights */}
            <div className="detail-card">
                  <h4>Meta-Learner Weights (Logistic Regression)</h4>
              <div className="table-container">
                <table>
                      <thead>
                        <tr>
                          <th>Base Model</th>
                          <th>Weight (Coefficient)</th>
                          <th>Interpretation</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr>
                          <td><strong>Logistic Regression</strong></td>
                          <td>{formatNumber(results.meta_learner_weights.logistic_regression)}</td>
                          <td>Contribution of LR predictions to ensemble</td>
                        </tr>
                        <tr>
                          <td><strong>Random Forest</strong></td>
                          <td>{formatNumber(results.meta_learner_weights.random_forest)}</td>
                          <td>Contribution of RF predictions to ensemble</td>
                        </tr>
                        <tr>
                          <td><strong>XGBoost</strong></td>
                          <td>{formatNumber(results.meta_learner_weights.xgboost)}</td>
                          <td>Contribution of XGB predictions to ensemble</td>
                        </tr>
                        {results.meta_learner_weights.intercept !== undefined && (
                          <tr>
                            <td><strong>Intercept</strong></td>
                            <td>{formatNumber(results.meta_learner_weights.intercept)}</td>
                            <td>Base probability adjustment</td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>
              <div style={{ marginTop: '20px', color: '#f0f6fc', fontSize: '13px' }}>
                <h5 style={{ marginTop: 0, marginBottom: '8px' }}>How to Interpret Weights:</h5>
                <ul style={{ margin: 0, paddingLeft: '20px' }}>
                      <li>Weights are coefficients from the meta-learner (Logistic Regression)</li>
                      <li>Final probability = sigmoid(intercept + LR_weight × LR_prob + RF_weight × RF_prob + XGB_weight × XGB_prob)</li>
                      <li>Positive weights increase the probability of default</li>
                      <li>Negative weights decrease the probability of default</li>
                      <li>The meta-learner learns these weights to minimize prediction error</li>
                    </ul>
                  </div>
                </div>

            {/* Base Models Performance */}
            <div className="detail-card">
                  <h4>Base Models Performance (Test Set)</h4>
              <div className="table-container">
                <table>
                    <thead>
                      <tr>
                        <th>Model</th>
                        <th>AUC</th>
                        <th>Gini</th>
                        <th>Recall</th>
                        <th>Precision</th>
                        <th>F1-Score</th>
                      </tr>
                    </thead>
                    <tbody>
                      {results.base_models_performance.map((model, idx) => (
                        <tr key={idx}>
                          <td><strong>{model.model}</strong></td>
                          <td>{formatNumber(model.auc)}</td>
                          <td>{formatNumber(model.gini)}</td>
                          <td>{formatNumber(model.recall)}</td>
                          <td>{formatNumber(model.precision)}</td>
                          <td>{formatNumber(model.f1)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
              </div>
            </div>

            {/* Ensemble Performance */}
            <div className="detail-card">
              <h4>Ensemble Performance (Test Set)</h4>
              <div className="summary-grid">
                <div className="summary-item">
                      <label>AUC-ROC:</label>
                      <span>{formatNumber(results.ensemble_performance.auc)}</span>
                    </div>
                <div className="summary-item">
                      <label>Gini Coefficient:</label>
                      <span>{formatNumber(results.ensemble_performance.gini_coefficient)}</span>
                    </div>
                <div className="summary-item">
                      <label>Accuracy:</label>
                      <span>{results.ensemble_performance.accuracy ? formatNumber(results.ensemble_performance.accuracy) : 'N/A'}</span>
                    </div>
                <div className="summary-item">
                      <label>Precision:</label>
                      <span>{results.ensemble_performance.precision ? formatNumber(results.ensemble_performance.precision) : 'N/A'}</span>
                    </div>
                <div className="summary-item">
                      <label>Recall:</label>
                      <span>{results.ensemble_performance.recall ? formatNumber(results.ensemble_performance.recall) : 'N/A'}</span>
                    </div>
                <div className="summary-item">
                      <label>F1-Score:</label>
                      <span>{results.ensemble_performance.f1 ? formatNumber(results.ensemble_performance.f1) : 'N/A'}</span>
                    </div>
                <div className="summary-item">
                      <label>KS Statistic:</label>
                      <span>{results.ensemble_performance.ks_stat ? formatNumber(results.ensemble_performance.ks_stat) : 'N/A'}</span>
                    </div>
                <div className="summary-item">
                      <label>Optimal Threshold:</label>
                      <span>{results.ensemble_performance.ks_threshold ? formatNumber(results.ensemble_performance.ks_threshold) : 'N/A'}</span>
                    </div>
                  </div>
                </div>

            {/* Generate Score Card Button */}
            {onGenerateScoreCard && (
              <div className="detail-card">
                <button
                  className="generate-scorecard-btn"
                  onClick={() => {
                    try {
                      if (typeof onGotoScoreCard === 'function') onGotoScoreCard();
                    } catch (e) { }
                    onGenerateScoreCard('stacking');
                  }}
                  disabled={generatingScoreCard || selectedVariables.length === 0}
                >
                  {generatingScoreCard ? 'Generating...' : 'Generate Score Card'}
                </button>
          </div>
        )}
      </div>
        </>
      )}
    </div>
  );
};

export default StackingResults;

