import React from "react";
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
  Legend
} from "recharts";

interface WoeIvResultsProps {
  woeIvResults: Record<string, any>;
  formatToFourDecimals: (val: any) => string;
}

const interpretIV = (iv: number): string => {
  if (iv < 0.02) return "Not useful";
  if (iv < 0.1) return "Weak predictor";
  if (iv < 0.3) return "Medium predictor";
  if (iv < 0.5) return "Strong predictor";
  return "Suspicious / Too good (check for leakage)";
};

const WoeIvResults: React.FC<WoeIvResultsProps> = ({
  woeIvResults,
  formatToFourDecimals
}) => {
  const colName = Object.keys(woeIvResults)[0];
  const colData = woeIvResults[colName];

  if (!colData) return null;

  // Prepare chart data
  const chartData = colData.stats?.map((row: any, idx: number) => ({
    Bin: row.Bin || row.temp_bin || row.Range || `Bin_${idx + 1}`,
    WOE: parseFloat(row.WOE),
    IV: parseFloat(row.IV),
    Total: row.Total,
    Good: row.Good,
    Bad: row.Bad
  }));

  return (
    <div className="woe-iv-container">
      <h3>WOE & IV Results - {colName}</h3>
      <p>
        <strong>IV:</strong> {formatToFourDecimals(colData.iv)}{" "}
        <span
          style={{
            marginLeft: "10px",
            fontStyle: "italic",
            color: "#888"
          }}
        >
          ({interpretIV(colData.iv)})
        </span>
      </p>

      {/* WOE Table */}
      <table className="cross-tab-table">
        <thead>
          <tr>
            <th>Bin</th>
            <th>Total</th>
            <th>Good</th>
            <th>Bad</th>
            <th>WOE</th>
            <th>IV</th>
          </tr>
        </thead>
        <tbody>
          {colData.stats?.map((row: any, idx: number) => (
            <tr key={idx}>
              <td>{row.Bin || row.temp_bin || row.Range}</td>
              <td>{row.Total}</td>
              <td>{row.Good}</td>
              <td>{row.Bad}</td>
              <td>{formatToFourDecimals(row.WOE)}</td>
              <td>{formatToFourDecimals(row.IV)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {/* WOE Bar Chart */}
      <h4 style={{ marginTop: "20px" }}>WOE by Bin</h4>
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
      <h4 style={{ marginTop: "20px" }}>IV Contribution by Bin</h4>
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
