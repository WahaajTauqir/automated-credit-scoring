import './Results.css';
import { DiscreteValuesDropdown } from './DiscreteValues';
import { NormalizedBin } from '../types/analysis';

interface UnivariateResultsProps {
  univariateResults: Record<string, { type?: 'discrete' | 'continuous'; stats: NormalizedBin[] }>;
  formatToFourDecimals: (value: any) => string;
  onDropColumn?: (col: string) => void;
}

const UnivariateResults = ({
  univariateResults,
  formatToFourDecimals,
  onDropColumn,
}: UnivariateResultsProps) => {
  if (!univariateResults || Object.keys(univariateResults).length === 0) return null;

  const entries = Object.entries(univariateResults).filter(
    ([, result]) => result && Array.isArray(result.stats) && result.stats.length > 0
  );
  if (entries.length === 0) return null;

  return (
    <div className="results-container coarse-binning-results" aria-label="Coarse binning results summary">
      <h2>Coarse Binning Results</h2>

      {entries.map(([col, result]) => {
        const isDiscrete = result.type === 'discrete';

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
                    {isDiscrete ? <th>Range</th> : (<><th>Min</th><th>Max</th></>)}
                    <th>Bad</th>
                    <th>Good</th>
                    <th>Total</th>
                    <th>Bad Rate (%)</th>
                    <th>Freq %</th>
                  </tr>
                </thead>
                <tbody>
                  {result.stats.map((row, index) => {
                    const binLabel = row.Bin ?? `Bin_${index + 1}`;
                    const rangeValue = typeof row.Range === 'string' ? row.Range : '';
                    const badRateValue =
                      typeof row['Bad Rate'] === 'number'
                        ? row['Bad Rate']
                        : (typeof row.bad_rate === 'number' ? row.bad_rate : (row.Total && row.Total > 0 ? (row.Bad / row.Total) * 100 : 0));
                    const freqValue =
                      typeof row['Freq%'] === 'number'
                        ? row['Freq%']
                        : (typeof row.freq_percent === 'number' ? row.freq_percent : 0);

                    return (
                      <tr key={`${col}-${index}`}>
                        <td>{binLabel}</td>
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
                        <td>{row.Bad}</td>
                        <td>{row.Good}</td>
                        <td>{row.Total}</td>
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
