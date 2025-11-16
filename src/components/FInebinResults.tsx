import './Results.css';
import { DiscreteValuesDropdown } from './DiscreteValues';
import { NormalizedBin } from '../types/analysis';

interface FineBinResultsProps {
  fineBinResults: Record<string, NormalizedBin[]>;
  formatToFourDecimals: (value: any) => string;
  discreteColumns?: string[];
}

const FineBinResults = ({ fineBinResults, formatToFourDecimals, discreteColumns = [] }: FineBinResultsProps) => {
  if (!fineBinResults || Object.keys(fineBinResults).length === 0) return null;

  return (
    <div className="results-container" aria-label="Fine binning results summary">
      <h2>Fine Binning Results</h2>
      {Object.entries(fineBinResults).map(([col, bins]) => {
        if (!Array.isArray(bins) || bins.length === 0) return null;
        const isDiscrete = discreteColumns.includes(col);

        const sortedBins = [...bins].sort((a, b) => {
          const minA = typeof a.Min === 'number' ? a.Min : null;
          const minB = typeof b.Min === 'number' ? b.Min : null;
          if (minA !== null && minB !== null) return minA - minB;
          const labelA = a.Bin ?? '';
          const labelB = b.Bin ?? '';
          return labelA.localeCompare(labelB);
        });

        return (
          <article key={col} className="results-card" aria-label={`Fine binning table for ${col}`}>
            <div className="results-card-header">
              <div className="results-card-title">
                <h3>{col}</h3>
                <span className="results-card-badge">{isDiscrete ? 'Discrete' : 'Continuous'}</span>
              </div>
            </div>

            <div className="results-card-body">
              <div className="results-table-container">
                <table className="results-table" aria-label={`Fine bin distribution for ${col}`}>
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
                      <th>Bad</th>
                      <th>Good</th>
                      <th>Total</th>
                      <th>Bad Rate (%)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sortedBins.map((bin, idx) => {
                      const label = bin.Bin ?? `Bin_${idx + 1}`;
                      const rangeValue = typeof bin.Range === 'string' ? bin.Range : '';
                      const badRate =
                        typeof bin['Bad Rate'] === 'number'
                          ? bin['Bad Rate']
                          : (typeof bin.bad_rate === 'number'
                              ? bin.bad_rate
                              : (bin.Total > 0 ? (bin.Bad / bin.Total) * 100 : 0));

                      return (
                        <tr key={`${col}-${label}`}>
                          <td>{label}</td>
                          {isDiscrete ? (
                            <td>
                              <DiscreteValuesDropdown rangeValue={rangeValue} />
                            </td>
                          ) : (
                            <>
                              <td>{bin.Min ?? '—'}</td>
                              <td>{bin.Max ?? '—'}</td>
                            </>
                          )}
                          <td>{bin.Bad}</td>
                          <td>{bin.Good}</td>
                          <td>{bin.Total}</td>
                          <td>{formatToFourDecimals(badRate)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          </article>
        );
      })}
    </div>
  );
};

export default FineBinResults;
