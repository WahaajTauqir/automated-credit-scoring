import './Results.css';

interface UnivariateResultsProps {
  univariateResults: any;
  formatToFourDecimals: (value: any) => string;
}

const UnivariateResults = ({ univariateResults, formatToFourDecimals }: UnivariateResultsProps) => {
  if (Object.keys(univariateResults).length === 0) return null;

  return (
    <div style={{ marginTop: '40px', width: '100%' }}>
      <h2 style={{ textAlign: 'center', marginBottom: '10px' }}>
        Coarse Binning Results
      </h2>
      {Object.entries(univariateResults).map(([col, result]: any, idx) => (
        <div key={idx} className="column-panel" style={{ marginBottom: '20px' }}>
          <h3>{col} ({result.type})</h3>
          <div className="column-list">
            <table style={{ width: '100%', color: 'white', fontSize: '14px' }}>
              <thead>
                <tr>
                  {Object.keys(result.stats[0]).map((key) => (
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
                        {key === 'Freq%' || key === 'Bad Rate' ? formatToFourDecimals(val) : String(val)}
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