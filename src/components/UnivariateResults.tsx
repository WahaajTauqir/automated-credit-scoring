import { useState } from "react";
import './Results.css';

interface UnivariateResultsProps {
  univariateResults: Record<string, any>;
  formatToFourDecimals: (value: any) => string;
  onDropColumn?: (col: string) => void; // NEW
}

const UnivariateResults = ({
  univariateResults,
  formatToFourDecimals,
  onDropColumn,
}: UnivariateResultsProps) => {
  if (!univariateResults || Object.keys(univariateResults).length === 0) return null;

  const entries = Object.entries(univariateResults).filter(
    ([, result]: any) => result && Array.isArray(result.stats) && result.stats.length > 0
  );
  if (entries.length === 0) return null;

  return (
    <div style={{ marginTop: '40px', width: '100%' }}>
      <h2 style={{ textAlign: 'center', marginBottom: '10px' }}>
        Coarse Binning Results
      </h2>

      {entries.map(([col, result]: any, idx) => (
        <div
          key={idx}
          className="column-panel"
          style={{
            marginBottom: '20px',
            border: '1px solid gray',
            borderRadius: '5px',
            position: 'relative',
            paddingTop: '30px'
          }}
        >
          {/* Drop Button per column */}
          {onDropColumn && (
            <button
              style={{
                position: 'absolute',
                top: '5px',
                right: '5px',
                padding: '4px 8px',
                background: 'red',
                color: 'white',
                border: 'none',
                borderRadius: '4px',
                cursor: 'pointer'
              }}
              onClick={(e) => {
                e.stopPropagation();
                onDropColumn(col);
              }}
              title="Remove this column from analysis"
            >
              Drop
            </button>
          )}

          <h3 style={{ padding: '5px 10px' }}>
            {col} ({result.type})
          </h3>

          <div className="column-list">
            <table style={{ width: '100%', color: 'white', fontSize: '14px' }}>
              <thead>
                <tr>
                  {Object.keys(result.stats[0] || {}).map((key) => (
                    <th key={key} style={{ padding: '4px', borderBottom: '1px solid gray' }}>
                      {key}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {result.stats.map((row: any, i: number) => (
                  <tr key={i}>
                    {Object.entries(row).map(([key, val], j) => (
                      <td key={j} style={{ padding: '4px', textAlign: 'center' }}>
                        {key === 'Freq%' || key === 'Bad Rate'
                          ? formatToFourDecimals(val)
                          : String(val)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}
    </div>
  );
};

export default UnivariateResults;
