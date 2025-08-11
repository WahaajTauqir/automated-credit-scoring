import React from 'react';

interface CrossTabResultsProps {
  crossTabResults: Record<string, any>;
  formatToFourDecimals: (value: any) => string;
  selectedBins: Record<string, any[]>; // keyed by column
  onBinToggle: (col: string, binValue: any) => void;
}

const CrossTabResults: React.FC<CrossTabResultsProps> = ({ 
  crossTabResults, 
  formatToFourDecimals,
  selectedBins,
  onBinToggle
}) => {
  if (!crossTabResults || Object.keys(crossTabResults).length === 0) {
    return <div>No cross tabulation results available</div>;
  }

  return (
    <div className="results-container">
      {Object.entries(crossTabResults).map(([column, data]) => (
        <div key={column} className="result-card">
          <h3>{column} - Select Bins to Merge</h3>
          {data && Array.isArray(data) ? (
            <table>
              <thead>
                <tr>
                  <th>Select</th>
                  <th>Category</th>
                  <th>Count</th>
                  <th>Percentage</th>
                </tr>
              </thead>
              <tbody>
                {data.map((row, index) => {
                  const binValue = row.category || 'N/A';
                  return (
                    <tr key={index}>
                      <td>
                        <input
                          type="checkbox"
                          checked={selectedBins[column]?.includes(binValue) || false}
                          onChange={() => onBinToggle(column, binValue)}
                        />
                      </td>
                      <td>{binValue}</td>
                      <td>{row.count || 0}</td>
                      <td>{formatToFourDecimals(row.percentage)}%</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          ) : (
            <p>No cross tabulation data available for this column</p>
          )}
        </div>
      ))}
    </div>
  );
};

export default CrossTabResults;
