import './Results.css';
import { useState } from 'react';

interface UnivariateResultsProps {
  univariateResults: Record<string, any>;
  formatToFourDecimals: (value: any) => string;
  onDropColumn?: (col: string) => void;
}

const UnivariateResults = ({
  univariateResults,
  formatToFourDecimals,
  onDropColumn,
}: UnivariateResultsProps) => {
  // State to track which ranges are expanded
  const [expandedRanges, setExpandedRanges] = useState<Record<string, boolean>>({});

  if (!univariateResults || Object.keys(univariateResults).length === 0) return null;

  const entries = Object.entries(univariateResults).filter(
    ([, result]: any) => result && Array.isArray(result.stats) && result.stats.length > 0
  );
  if (entries.length === 0) return null;

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
    <div style={{ marginTop: '40px', width: '100%' }}>
      <h2 style={{ textAlign: 'center', marginBottom: '10px' }}>
        Coarse Binning Results
      </h2>

      {entries.map(([col, result]: any, idx) => {
        const isDiscrete = result.type === 'discrete';
        const columnOrder = isDiscrete
          ? [col + '_binned', 'Range', 'Bad Rate', 'Bad', 'Good', 'Total', 'Freq%']
          : [col + '_binned', 'Min', 'Max', 'Bad Rate', 'Bad', 'Good', 'Total', 'Freq%'];

        return (
          <div
            key={idx}
            className="column-panel"
            style={{
              marginBottom: '20px',
              border: '1px solid gray',
              borderRadius: '5px',
              position: 'relative',
              paddingTop: '30px',
            }}
          >
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
                  cursor: 'pointer',
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
                    {columnOrder.map((key) => (
                      <th key={key} style={{ padding: '4px', borderBottom: '1px solid gray' }}>
                        {key === 'Bad Rate' ? 'Bad Rate (%)' : key === 'Freq%' ? 'Freq%' : key}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {result.stats.map((row: any, i: number) => {
                    const binnedKey = Object.keys(row).find((k) => k.endsWith('_binned'));
                    const binLabel = binnedKey ? row[binnedKey] : `Bin_${i + 1}`;
                    const rangeKey = `${col}_${i}`; // Unique key for each row's range

                    return (
                      <tr key={i}>
                        {columnOrder.map((key, j) => {
                          // Handle Range column for discrete variables
                          if (key === 'Range' && isDiscrete) {
                            const rangeValue = String(row[key] ?? '');
                            const isExpanded = expandedRanges[rangeKey];
                            const truncatedRange = truncateRange(rangeValue);
                            const isTruncated = rangeValue.length > truncatedRange.length;

                            return (
                              <td key={j} style={{ padding: '4px', textAlign: 'center' }}>
                                <span
                                  title={rangeValue} // Tooltip with full range
                                  style={{ cursor: isTruncated ? 'pointer' : 'default' }}
                                  onClick={isTruncated ? () => toggleRangeExpansion(rangeKey) : undefined}
                                >
                                  {isExpanded ? rangeValue : truncatedRange}
                                </span>
                              </td>
                            );
                          }

                          // Handle other columns
                          return (
                            <td key={j} style={{ padding: '4px', textAlign: 'center' }}>
                              {key === col + '_binned'
                                ? binLabel
                                : key === 'Bad Rate' || key === 'Freq%'
                                ? formatToFourDecimals(row[key])
                                : key === 'Min' || key === 'Max'
                                ? String(row[key] ?? '')
                                : String(row[key] ?? '')}
                            </td>
                          );
                        })}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        );
      })}
    </div>
  );
};

export default UnivariateResults;