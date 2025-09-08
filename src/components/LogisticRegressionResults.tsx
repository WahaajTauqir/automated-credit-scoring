import React, { useState } from 'react';
import './LogisticRegressionResults.css';

interface LogisticRegressionResultsProps {
  selectedVariables: string[];
  allSelectedVariables?: string[];
  targetVariable: string;
  woeTransformedData: Record<string, any[]>;
  onColumnSelect: (column: string) => void;
  selectedColumn: string;
  onToggleSelect?: (column: string) => void;
  onGenerateScoreCard?: () => void;
  generatingScoreCard?: boolean;
  onGotoScoreCard?: () => void;
}

interface ModelStats {
  aic: number;
  bic: number;
  log_likelihood: number;
  pseudo_r_squared: number;
  n_observations: number;
}

interface Coefficient {
  variable: string;
  coefficient: number;
  significance: string;
}

interface PValue {
  variable: string;
  p_value: number;
  significance: string;
}

interface VIFData {
  variable: string;
  vif: number;
}

interface ROCPoint {
  fpr: number;
  tpr: number;
}

interface KSCurvePoint {
  threshold: number;
  tpr: number;
  fpr: number;
  diff: number;
}

interface LogisticResults {
  success: boolean;
  coefficients: Coefficient[];
  p_values: PValue[];
  vif_data: VIFData[];
  gini_coefficient: number;
  auc: number;
  roc_data: ROCPoint[];
  model_stats: ModelStats;
  confusion_matrix?: number[][] | null;
  confusion_matrix_image?: string | null;
  accuracy?: number;
  precision?: number;
  recall?: number;
  f1?: number;
  ks_stat?: number;
  ks_threshold?: number;
  ks_curve?: KSCurvePoint[];
}

const LogisticRegressionResults: React.FC<LogisticRegressionResultsProps> = ({
  selectedVariables,
  allSelectedVariables,
  targetVariable,
  woeTransformedData,
  onColumnSelect,
  selectedColumn,
  onToggleSelect,
  onGenerateScoreCard,
  generatingScoreCard
  , onGotoScoreCard
}) => {
  const [results, setResults] = useState<LogisticResults | null>(null);
  const [loading, setLoading] = useState(false);
  const [showLegend, setShowLegend] = useState(false);
  const [confusionView, setConfusionView] = useState<'counts' | 'percent'>('counts');
  const [activeTab, setActiveTab] = useState<'coefficients' | 'vif' | 'roc' | 'confusion' | 'ks'>('coefficients');

  const runLogisticRegression = async () => {
    if (selectedVariables.length === 0) {
      alert('Please select at least one variable from the Important Column Selection step');
      return;
    }

    setLoading(true);
    try {
      const response = await fetch('http://localhost:5000/api/logistic-regression', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          selected_variables: selectedVariables,
          target: targetVariable,
          woe_transformed_data: woeTransformedData
        })
      });

      const data = await response.json();
      if (data.success) {
        setResults(data);
      } else {
        alert(`Error: ${data.error}`);
      }
    } catch (error) {
      alert(`Error running logistic regression: ${error}`);
    } finally {
      setLoading(false);
    }
  };

  const getSignificanceColor = (significance: string) => {
    switch (significance) {
      case 'Highly Significant': return '#52c41a';
      case 'Significant': return '#fa8c16';
      case 'Not Significant': return '#ff4d4f';
      default: return '#8c8c8c';
    }
  };

  const getVIFColor = (vif: number) => {
    if (vif < 5) return '#52c41a';
    if (vif < 10) return '#fa8c16';
    return '#ff4d4f';
  };

  const formatNumber = (num: number, decimals: number = 4) => {
    return Number(num).toFixed(decimals);
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

    // ensure numbers
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
      // stronger color for higher percent
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
          <text x={pad + cell / 2} y={pad + size + 14} textAnchor="middle" fill={labelFill} fontSize={12} transform={`rotate(-90, ${pad + cell / 2}, ${pad + size/2})`}>Actual</text>

          {/* Grid cells */}
          {[0, 1].map((r) =>
            [0, 1].map((c) => {
              const count = [ [a00, a01], [a10, a11] ][r][c];
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
                    {confusionView === 'counts' ? `${((count/total)*100).toFixed(2)}%` : `(${String(count)})`}
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

        <div style={{ marginTop: 12, color: '#f0f6fc' }}>
          <strong>Note:</strong> Top-left = True Negative (actual 0 predicted 0), bottom-right = True Positive (actual 1 predicted 1).
        </div>
      </div>
    );
  };

  return (
    <div className="logistic-regression-container">
      <div className="lr-header">
        <div className="lr-title">
          <h3>Logistic Regression Analysis</h3>
          <button 
            className="legend-toggle"
            onClick={() => setShowLegend(!showLegend)}
          >
            {showLegend ? 'Hide Legend' : 'Show Legend'}
          </button>
        </div>
        
        {showLegend && (
          <div className="legend-panel">
            <h4>Legend</h4>
            <div className="legend-section">
              <h5>P-Value Significance:</h5>
              <ul>
                <li><span style={{ color: '#52c41a' }}>●</span> Highly Significant (p &lt; 0.01)</li>
                <li><span style={{ color: '#fa8c16' }}>●</span> Significant (p &lt; 0.05)</li>
                <li><span style={{ color: '#ff4d4f' }}>●</span> Not Significant (p ≥ 0.05)</li>
              </ul>
            </div>
            <div className="legend-section">
              <h5>VIF (Multicollinearity):</h5>
              <ul>
                <li><span style={{ color: '#52c41a' }}>●</span> Low (VIF &lt; 5): No multicollinearity</li>
                <li><span style={{ color: '#fa8c16' }}>●</span> Moderate (5 ≤ VIF &lt; 10): Some concern</li>
                <li><span style={{ color: '#ff4d4f' }}>●</span> High (VIF ≥ 10): High multicollinearity</li>
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
            <div className="legend-section">
              <h5>Confusion Matrix</h5>
              <ul>
                <li>Cells: top-left=TN, top-right=FP, bottom-left=FN, bottom-right=TP</li>
                <li>Accuracy = (TP+TN)/Total — &gt;0.80 good, 0.65–0.80 moderate, &lt;0.65 poor</li>
                <li>Precision = TP/(TP+FP) — &gt;0.75 good, 0.50–0.75 moderate, &lt;0.50 poor</li>
                <li>Recall = TP/(TP+FN) — &gt;0.75 good, 0.50–0.75 moderate, &lt;0.50 poor</li>
                <li>F1 Score = harmonic mean(Precision,Recall) — &gt;0.75 good, 0.50–0.75 moderate, &lt;0.50 poor</li>
              </ul>
            </div>
          </div>
        )}
      </div>

      <div className="lr-content">
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
                  onClick={(e) => e.stopPropagation()} // prevent row click
                  onChange={() => onToggleSelect ? onToggleSelect(variable) : undefined}
                />
              </div>
            ))}
          </div>
          
          <button 
            className="run-regression-btn"
            onClick={runLogisticRegression}
            disabled={loading || selectedVariables.length === 0}
          >
            {loading ? 'Running...' : 'Run Logistic Regression'}
          </button>
          
          {results && onGenerateScoreCard && (
            <button 
              className="run-regression-btn"
              onClick={() => {
                try {
                  if (typeof onGotoScoreCard === 'function') onGotoScoreCard();
                } catch (e) {}
                onGenerateScoreCard();
              }}
              disabled={generatingScoreCard || selectedVariables.length === 0}
              style={{ marginTop: '10px' }}
            >
              {generatingScoreCard ? 'Generating...' : 'Generate Score Card'}
            </button>
          )}
        </div>

  {results && (
          <div className="results-panel">
            <div className="results-tabs">
              <button 
                className={`tab-btn ${activeTab === 'coefficients' ? 'active' : ''}`}
                onClick={() => setActiveTab('coefficients')}
              >
                Coefficients
              </button>
              {/* P-Values merged into Coefficients table */}
              <button 
                className={`tab-btn ${activeTab === 'vif' ? 'active' : ''}`}
                onClick={() => setActiveTab('vif')}
              >
                Multicollinearity
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
              {activeTab === 'coefficients' && (
                <div className="coefficients-table">
                  <h4>Model Coefficients</h4>
                  <table>
                    <thead>
                      <tr>
                        <th>Variable</th>
                        <th>Coefficient</th>
                        <th>P-Value</th>
                        <th>Significance</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(() => {
                        const filtered = results.coefficients.filter(c => c.variable !== 'Intercept');
                        return filtered.map((coef, index) => (
                          <tr key={index}>
                            <td>{coef.variable}</td>
                            <td>{formatNumber(coef.coefficient)}</td>
                            {/* find matching p-value entry */}
                            <td>
                              {(() => {
                                const pv = results.p_values.find(p => p.variable === coef.variable);
                                return pv ? formatNumber(pv.p_value) : 'N/A';
                              })()}
                            </td>
                            <td style={{ color: getSignificanceColor(coef.significance) }}>
                              {(() => {
                                const pv = results.p_values.find(p => p.variable === coef.variable);
                                return pv ? pv.significance : coef.significance;
                              })()}
                            </td>
                          </tr>
                        ));
                      })()}
                    </tbody>
                  </table>
                </div>
              )}

              {activeTab === 'vif' && (
                <div className="vif-table">
                  <h4>Multicollinearity (VIF)</h4>
                  <table>
                    <thead>
                      <tr>
                        <th>Variable</th>
                        <th>VIF</th>
                        <th>Multicollinearity</th>
                      </tr>
                    </thead>
                    <tbody>
                      {results.vif_data.map((vif, index) => (
                        <tr key={index}>
                          <td>{vif.variable}</td>
                          <td>{formatNumber(vif.vif)}</td>
                          <td style={{ color: getVIFColor(vif.vif) }}>
                            {vif.vif < 5 ? 'Low' : vif.vif < 10 ? 'Moderate' : 'High'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

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
                {activeTab === 'confusion' ? (
                  // Only show classification metrics when Confusion Matrix tab is active
                  results.accuracy !== undefined ? (
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
                  ) : (
                    <div style={{ color: '#f0f6fc' }}>No classification metrics available</div>
                  )
                ) : activeTab === 'roc' ? (
                  // When ROC tab is active, show Gini guidance instead of full summary
                  <div style={{ color: '#f0f6fc', padding: 12 }}>
                    <h5 style={{ marginTop: 0 }}>Gini Coefficient:</h5>
                    <div>Ranges from 0 to 1 (higher is better)</div>
                    <ul style={{ marginTop: 8 }}>
                      <li>{'> 0.6'}: Excellent model</li>
                      <li>0.4 - 0.6: Good model</li>
                      <li>{'< 0.4'}: Poor model</li>
                    </ul>
                  </div>
                ) : activeTab === 'vif' ? (
                  // When Multicollinearity tab is active, show only AIC and BIC
                  <>
                    <div className="summary-item">
                      <label>AIC:</label>
                      <span>{formatNumber(results.model_stats.aic)}</span>
                    </div>
                    <div className="summary-item">
                      <label>BIC:</label>
                      <span>{formatNumber(results.model_stats.bic)}</span>
                    </div>
                  </>
                ) : activeTab === 'coefficients' ? (
                  // When Coefficients tab is active, show only Intercept, Log Likelihood, Pseudo R², Observations
                  <>
                    {(() => {
                      const intercept = results.coefficients.find(c => c.variable === 'Intercept');
                      if (!intercept) return null;
                      return (
                        <div className="summary-item">
                          <label>Intercept:</label>
                          <span>{formatNumber(intercept.coefficient)}</span>
                        </div>
                      );
                    })()}
                    <div className="summary-item">
                      <label>Log Likelihood:</label>
                      <span>{formatNumber(results.model_stats.log_likelihood)}</span>
                    </div>
                    <div className="summary-item">
                      <label>Pseudo R²:</label>
                      <span>{formatNumber(results.model_stats.pseudo_r_squared)}</span>
                    </div>
                    <div className="summary-item">
                      <label>Observations:</label>
                      <span>{results.model_stats.n_observations}</span>
                    </div>
                  </>
                ) : activeTab === 'ks' ? (
                  // When KS tab is active, show KS statistic and short guidance
                  <div style={{ color: '#f0f6fc', padding: 12 }}>
                    <div><strong>KS statistic:</strong> {results.ks_stat !== undefined ? formatNumber(results.ks_stat) : 'N/A'} at threshold {results.ks_threshold !== undefined && results.ks_threshold !== null ? formatNumber(results.ks_threshold) : 'N/A'}</div>
                    <div style={{ marginTop: 8, fontSize: 12, color: '#8b949e' }}>Higher KS (closer to 1) indicates better separation; &gt;0.4 excellent, 0.2–0.4 good, &lt;0.2 weak.</div>
                  </div>
                ) : (
                  // Full model summary for other tabs
                  <>
                    <div className="summary-item">
                      <label>AIC:</label>
                      <span>{formatNumber(results.model_stats.aic)}</span>
                    </div>
                    <div className="summary-item">
                      <label>BIC:</label>
                      <span>{formatNumber(results.model_stats.bic)}</span>
                    </div>
                    <div className="summary-item">
                      <label>Gini Coefficient:</label>
                      <span>{formatNumber(results.gini_coefficient)}</span>
                    </div>
                    {/* Classification metrics */}
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
                        <div className="summary-item">
                          <label>Recall:</label>
                          <span>{formatNumber(results.recall ?? 0)}</span>
                        </div>
                        <div className="summary-item">
                          <label>F1 Score:</label>
                          <span>{formatNumber(results.f1 ?? 0)}</span>
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

// Small KS chart component
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

export default LogisticRegressionResults;
