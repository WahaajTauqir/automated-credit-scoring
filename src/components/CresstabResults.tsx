import './Results.css';

interface CrossTabResultsProps {
  crossTabResults: any;
  formatToFourDecimals: (value: any) => string;
}

const CrossTabResults = ({ crossTabResults, formatToFourDecimals }: CrossTabResultsProps) => {
  if (Object.keys(crossTabResults).length === 0) return null;

  return (
    <div style={{ marginTop: '40px', width: '100%' }}>
      <h2 style={{ textAlign: 'center', marginBottom: '10px' }}>
        Cross-Tabulation Results
      </h2>
      {Object.entries(crossTabResults).map(([col, result]: any, idx) => (
        <div key={idx} className="column-panel" style={{ marginBottom: '20px' }}>
          <h3>{result.title}</h3>
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

export default CrossTabResults;