import './Results.css';
import { DiscreteValuesDropdown } from './DiscreteValues';

export interface BinStats {
  Bin: string;
  Count: number;
  Bad: number;
  Good: number;
  BadRate: number;
  Range?: string; // Optional Range field for discrete variables
}

interface FineBinResultsProps {
  fineBinResults: Record<string, BinStats[]>;
  formatToFourDecimals: (value: any) => string;
  discreteColumns?: string[]; // Prop to identify discrete variables
}

const FineBinResults = ({ fineBinResults, formatToFourDecimals, discreteColumns = [] }: FineBinResultsProps) => {

  if (!fineBinResults || Object.keys(fineBinResults).length === 0) return null;

  return (
    <div className="results-container" aria-label="Fine binning results summary">
      <h2>Fine Binning Results</h2>
      {Object.entries(fineBinResults).map(([col, bins]) => {
        const isDiscrete = discreteColumns.includes(col);

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
                      <th>Count</th>
                      <th>Bad</th>
                      <th>Good</th>
                      <th>Bad Rate</th>
                    </tr>
                  </thead>
                  <tbody>
                    {([...bins])
                      .slice()
                      .sort((a: any, b: any) => {
                        const getMin = (r: any) => {
                          const m = r.Min ?? r.min ?? r.MinValue ?? r.minValue ?? null;
                          const v = m === null || m === undefined ? NaN : Number(m);
                          return Number.isFinite(v) ? v : NaN;
                        };
                        const minA = getMin(a);
                        const minB = getMin(b);
                        if (!Number.isNaN(minA) && !Number.isNaN(minB)) return minA - minB;
                        const la = (a.Bin || a.bin || '').toString();
                        const lb = (b.Bin || b.bin || '').toString();
                        const na = parseInt((la.match(/\d+/) || [])[0] || '', 10);
                        const nb = parseInt((lb.match(/\d+/) || [])[0] || '', 10);
                        if (!Number.isNaN(na) && !Number.isNaN(nb)) return na - nb;
                        return la.localeCompare(lb);
                      })
                      .map((bin, idx) => {
                      const rangeValue = String(bin.Range ?? '');

                      return (
                        <tr key={idx}>
                          <td>{bin.Bin}</td>
                          {isDiscrete && (
                            <td>
                              <DiscreteValuesDropdown rangeValue={rangeValue} />
                            </td>
                          )}
                          <td>{bin.Count}</td>
                          <td>{bin.Bad}</td>
                          <td>{bin.Good}</td>
                          <td>{formatToFourDecimals(bin.BadRate)}</td>
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