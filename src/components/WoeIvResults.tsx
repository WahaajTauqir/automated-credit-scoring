import React, { useState } from 'react';
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

interface WoeIvResultsProps {
  woeIvResults: Record<string, any>;
  formatToFourDecimals: (val: any) => string;
  discreteColumns?: string[]; // Prop to identify discrete variables
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
  const [expandedRanges, setExpandedRanges] = useState<Record<string, boolean>>({});

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

  // Function to truncate long range strings
  const truncateRange = (range: string, maxLength: number = 50): string => {
    if (range.length <= maxLength) return range;
    return `${range.slice(0, maxLength - 3)}...`;
  };

  // Toggle expansion of a specific range
  const toggleRangeExpansion = (key: string) => {
    setExpandedRanges((prev) => ({
      ...prev,
      [key]: !prev[key],
    }));
  };

  return (
    <div className="woe-iv-container">
      <h3>WOE & IV Results - {colName}</h3>
      <p>
        <strong>IV:</strong> {formatToFourDecimals(colData.iv)}{' '}
        <span style={{ marginLeft: '10px', fontStyle: 'italic', color: '#888' }}>
          ({interpretIV(colData.iv)})
        </span>
      </p>

      {/* WOE Table */}
      <table className="cross-tab-table">
        <thead>
          <tr>
            <th>Bin</th>
            {isDiscrete && <th>Range</th>}
            <th>Total</th>
            <th>Good</th>
            <th>Bad</th>
            <th>WOE</th>
            <th>IV</th>
          </tr>
        </thead>
        <tbody>
          {colData.stats?.map((row: any, idx: number) => {
            const rangeKey = `${colName}_${idx}`; // Unique key for each row's range
            const rangeValue = String(row.Range ?? '');
            const isTruncated = rangeValue.length > 50;
            const truncatedRange = truncateRange(rangeValue);

            return (
              <tr key={idx}>
                <td>{row.Bin || row.temp_bin || row.Range}</td>
                {isDiscrete && (
                  <td>
                    <span
                      title={rangeValue} // Tooltip with full range
                      style={{ cursor: isTruncated ? 'pointer' : 'default' }}
                      onClick={isTruncated ? () => toggleRangeExpansion(rangeKey) : undefined}
                    >
                      {expandedRanges[rangeKey] ? rangeValue : truncatedRange}
                    </span>
                  </td>
                )}
                <td>{row.Total}</td>
                <td>{row.Good}</td>
                <td>{row.Bad}</td>
                <td>{formatToFourDecimals(row.WOE)}</td>
                <td>{formatToFourDecimals(row.IV)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>

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
  );
};

export default WoeIvResults;