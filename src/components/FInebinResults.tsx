import './Results.css';

export interface BinStats {
  Bin: string;
  Count: number;
  Bad: number;
  Good: number;
  BadRate: number;
}

interface FineBinResultsProps {
  fineBinResults: Record<string, BinStats[]>;
  formatToFourDecimals: (value: any) => string; 
}

const FineBinResults = ({ fineBinResults, formatToFourDecimals }: FineBinResultsProps) => {
  if (!fineBinResults || Object.keys(fineBinResults).length === 0) return null;

  return (
    <div className="results-container">
      <h3>Fine Binning Results</h3>
      {Object.entries(fineBinResults).map(([col, bins]) => (
        <div key={col} className="result-section">
          <h4>{col}</h4>
          <table className="results-table">
            <thead>
              <tr>
                <th>Bin</th>
                <th>Count</th>
                <th>Bad</th>
                <th>Good</th>
                <th>Bad Rate</th>
              </tr>
            </thead>
            <tbody>
              {bins.map((bin, idx) => (
                <tr key={idx}>
                  <td>{bin.Bin}</td>
                  <td>{bin.Count}</td>
                  <td>{bin.Bad}</td>
                  <td>{bin.Good}</td>
                  <td>{formatToFourDecimals(bin.BadRate)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </div>
  );
};

export default FineBinResults;
