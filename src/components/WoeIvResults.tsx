import React from 'react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  ResponsiveContainer,
  LineChart,
  Line,
  Legend,
} from 'recharts';
import './Results.css';
import { DiscreteValuesDropdown } from './DiscreteValues';
import { NormalizedBin } from '../types/analysis';

interface WoeIvResultsProps {
  woeIvResults: Record<string, { iv?: number; stats: NormalizedBin[] }>;
  formatToFourDecimals: (val: any) => string;
  discreteColumns?: string[];
}

const interpretIV = (iv: number): string => {
  if (iv < 0.02) return 'Not useful';
  if (iv < 0.1) return 'Weak predictor';
  if (iv < 0.3) return 'Medium predictor';
  if (iv < 0.5) return 'Strong predictor';
  return 'Suspicious / Too good (check for leakage)';
};

const WoeIvResults: React.FC<WoeIvResultsProps> = ({
  woeIvResults,
  formatToFourDecimals,
  discreteColumns = [],
}) => {
  const entries = Object.entries(woeIvResults).filter(
    ([, data]) => data && Array.isArray(data.stats) && data.stats.length > 0
  );

  if (entries.length === 0) return null;

  return (
    <div className="woe-iv-container results-container">
      {entries.map(([colName, colData]) => {
        const isDiscrete = discreteColumns.includes(colName);
        const stats = colData.stats;
        const chartData = stats.map((row, idx) => ({
          Bin: row.Bin ?? `Bin_${idx + 1}`,
          WOE: Number(row.WOE ?? 0),
          IV: Number(row.IV ?? 0),
          Total: row.Total,
          Good: row.Good,
          Bad: row.Bad,
          Range: row.Range,
        }));

        return (
          <article key={colName} className="results-card" aria-label={`WOE and IV analysis for ${colName}`}>
            <div className="results-card-header">
              <div className="results-card-title">
                <h3>WOE & IV Results - {colName}</h3>
                <span className="results-card-badge">{isDiscrete ? 'Discrete' : 'Continuous'}</span>
              </div>
            </div>

            <div className="results-card-body">
              <p style={{ margin: 0 }}>
                <strong>IV:</strong> {formatToFourDecimals(colData.iv ?? 0)}{' '}
                <span style={{ marginLeft: '10px', fontStyle: 'italic', color: '#888' }}>
                  ({interpretIV(colData.iv ?? 0)})
                </span>
              </p>

              <div className="results-table-container">
                <table className="results-table" aria-label={`WOE and IV results for ${colName}`}>
                  <thead>
                    <tr>
                      <th>Bin</th>
                      {isDiscrete && <th>Range</th>}
                      {!isDiscrete && (
                        <>
                          <th>Min</th>
                          <th>Max</th>
                        </>
                      )}
                      <th>Total</th>
                      <th>Good</th>
                      <th>Bad</th>
                      <th>Bad Rate (%)</th>
                      <th>WOE</th>
                      <th>IV</th>
                    </tr>
                  </thead>
                  <tbody>
                    {stats.map((row, idx) => {
                      const rangeValue = typeof row.Range === 'string' ? row.Range : '';
                      const badRate = row.Total > 0 ? (row.Bad / row.Total) * 100 : 0;
                      return (
                        <tr key={`${colName}-${idx}`}>
                          <td>{row.Bin ?? `Bin_${idx + 1}`}</td>
                          {isDiscrete ? (
                            <td>
                              <DiscreteValuesDropdown rangeValue={rangeValue} />
                            </td>
                          ) : (
                            <>
                              <td>{row.Min ?? '—'}</td>
                              <td>{row.Max ?? '—'}</td>
                            </>
                          )}
                          <td>{row.Total}</td>
                          <td>{row.Good}</td>
                          <td>{row.Bad}</td>
                          <td>{formatToFourDecimals(badRate)}</td>
                          <td>{formatToFourDecimals(row.WOE ?? 0)}</td>
                          <td>{formatToFourDecimals(row.IV ?? 0)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              <h4 style={{ marginTop: '20px' }}>WOE by Bin</h4>
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={chartData} margin={{ top: 20, right: 30, bottom: 40, left: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="Bin" angle={-30} textAnchor="end" interval={0} />
                  <YAxis />
                  <Tooltip />
                  <Bar dataKey="WOE" fill="#8884d8" />
                </BarChart>
              </ResponsiveContainer>

              <h4 style={{ marginTop: '20px' }}>IV Contribution by Bin</h4>
              <ResponsiveContainer width="100%" height={300}>
                <LineChart data={chartData} margin={{ top: 20, right: 30, bottom: 40, left: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="Bin" angle={-30} textAnchor="end" interval={0} />
                  <YAxis />
                  <Tooltip />
                  <Legend />
                  <Line type="monotone" dataKey="IV" stroke="#82ca9d" strokeWidth={2} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </article>
        );
      })}
    </div>
  );
};

export default WoeIvResults;
