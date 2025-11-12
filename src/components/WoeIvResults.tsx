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

interface WoeIvResultsProps {
  woeIvResults: Record<string, any>;
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

  const colName = Object.keys(woeIvResults)[0];
  const colData = woeIvResults[colName];

  if (!colData) return null;

  const isDiscrete = discreteColumns.includes(colName);

  // Prepare chart data
  const chartData = colData.stats?.map((row: any, idx: number) => ({
    Bin: row.Bin || row.temp_bin || row.Range || `Bin_${idx + 1}`,
    WOE: parseFloat(row.WOE),
    IV: parseFloat(row.IV),
    Total: row.Total,
    Good: row.Good,
    Bad: row.Bad,
    Range: row.Range,
  }));

  return (
    <div className="woe-iv-container results-container">
      <article className="results-card" aria-label={`WOE and IV analysis for ${colName}`}>
        <div className="results-card-header">
          <div className="results-card-title">
            <h3>WOE & IV Results - {colName}</h3>
            <span className="results-card-badge">{isDiscrete ? 'Discrete' : 'Continuous'}</span>
          </div>
        </div>

        <div className="results-card-body">
          <p style={{ margin: 0 }}>
            <strong>IV:</strong> {formatToFourDecimals(colData.iv)}{' '}
            <span style={{ marginLeft: '10px', fontStyle: 'italic', color: '#888' }}>
              ({interpretIV(colData.iv)})
            </span>
          </p>

          {/* WOE Table */}
          <div className="results-table-container">
            <table className="results-table" aria-label={`WOE and IV results for ${colName}`}>
          <thead>
            <tr>
              <th>Bin</th>
              {isDiscrete && <th>Range</th>}
              <th>Total</th>
              <th>Good</th>
              <th>Bad</th>
              <th>Bad Rate (%)</th>
              <th>WOE</th>
              <th>IV</th>
            </tr>
          </thead>
          <tbody>
            {colData.stats?.map((row: any, idx: number) => {
              const rangeValue = String(row.Range ?? '');
              const badRate = row.Total > 0 ? (row.Bad / row.Total * 100) : 0;

              return (
                <tr key={idx}>
                  <td>{row.Bin || row.temp_bin || row.Range || `Bin_${idx + 1}`}</td>
                  {isDiscrete && (
                    <td>
                      <DiscreteValuesDropdown rangeValue={rangeValue} />
                    </td>
                  )}
                  <td>{row.Total}</td>
                  <td>{row.Good}</td>
                  <td>{row.Bad}</td>
                  <td>{formatToFourDecimals(badRate)}</td>
                  <td>{formatToFourDecimals(row.WOE)}</td>
                  <td>{formatToFourDecimals(row.IV)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
          </div>

          {/* WOE Bar Chart */}
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

          {/* IV Contribution Line Chart */}
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
    </div>
  );
};

export default WoeIvResults;