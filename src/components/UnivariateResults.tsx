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
    <div className="results-container coarse-binning-results" aria-label="Coarse binning results summary">
      <h2>Coarse Binning Results</h2>

      {entries.map(([col, result]: any) => {
        const isDiscrete = result.type === 'discrete';
        const binHeaderLabel = isDiscrete ? 'Range' : 'Min / Max';

        return (
          <article key={col} className="results-card coarse-result-card" aria-label={`Coarse binning table for ${col}`}>
            <div className="results-card-header">
              <div className="results-card-title">
                <h3>{col}</h3>
                <span className="results-card-badge">{isDiscrete ? 'Discrete' : 'Continuous'}</span>
              </div>
              {onDropColumn && (
                <button
                  type="button"
                  className="drop-btn"
                  onClick={(e) => {
                    e.stopPropagation();
                    onDropColumn(col);
                  }}
                  title={`Remove ${col} from analysis`}
                >
                  Drop
                </button>
              )}
            </div>

            <div className="results-table-container">
              <table className="results-table cross-tab-table" aria-label={`Coarse binning distribution for ${col}`}>
                <thead>
                  <tr>
                    <th>Bin</th>
                    {isDiscrete ? (
                      <th>{binHeaderLabel}</th>
                    ) : (
                      <>
                        <th>Min</th>
                        <th>Max</th>
                      </>
                    )}
                    <th>Bad</th>
                    <th>Good</th>
                    <th>Total</th>
                    <th>Bad Rate (%)</th>
                    <th>Freq %</th>
                  </tr>
                </thead>
                <tbody>
                  {result.stats.map((row: any, index: number) => {
                    const binnedKey = Object.keys(row).find((key: string) => key.endsWith('_binned'));
                    const binLabel = binnedKey ? row[binnedKey] : `Bin_${index + 1}`;
                    const rangeKey = `${col}_${index}`;
                    const rangeValue = String(row.Range ?? '');
                    const isTruncated = rangeValue.length > 50;
                    const truncatedRange = truncateRange(rangeValue);
                    const canToggleRange = isTruncated;
                    const displayRange = canToggleRange && expandedRanges[rangeKey]
                      ? rangeValue
                      : truncatedRange;
                    const badRateValue =
                      row['Bad Rate'] ?? row['Bad Rate (%)'] ?? row.bad_rate ?? row.BadRate ?? 0;
                    const freqValue = row['Freq%'] ?? row.freq ?? row.Freq ?? 0;

                    return (
                      <tr key={`${col}-${index}`}>
                        <td>{binLabel}</td>
                        {isDiscrete ? (
                          <td>
                            <button
                              type="button"
                              className={`range-toggle-btn${canToggleRange ? '' : ' is-static'}`}
                              title={rangeValue}
                              onClick={canToggleRange ? () => toggleRangeExpansion(rangeKey) : undefined}
                              aria-label={
                                canToggleRange ? `Toggle full range for ${binLabel}` : undefined
                              }
                            >
                              {canToggleRange ? displayRange : rangeValue}
                            </button>
                          </td>
                        ) : (
                          <>
                            <td>{String(row.Min ?? '')}</td>
                            <td>{String(row.Max ?? '')}</td>
                          </>
                        )}
                        <td>{row.Bad ?? 0}</td>
                        <td>{row.Good ?? 0}</td>
                        <td>{row.Total ?? 0}</td>
                        <td>{formatToFourDecimals(badRateValue)}</td>
                        <td>{formatToFourDecimals(freqValue)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </article>
        );
      })}
    </div>
  );
};

export default UnivariateResults;