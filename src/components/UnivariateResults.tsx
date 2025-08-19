import './Results.css';

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
  if (!univariateResults || Object.keys(univariateResults).length === 0) return null;

  const entries = Object.entries(univariateResults).filter(
    ([, result]: any) => result && Array.isArray(result.stats) && result.stats.length > 0
  );
  if (entries.length === 0) return null;

  // Column order
  const columnOrder = ['Bin', 'Bad', 'Good', 'Total', 'Bad Rate', 'Freq%'];

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
                  {columnOrder.map(key => (
                    <th key={key} style={{ padding: '4px', borderBottom: '1px solid gray' }}>
                      {key === 'Bad Rate' ? 'Bad Rate (%)' : key}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {result.stats.map((row: any, i: number) => {
                  // Prefer explicit binned column if present, else fallback to sequential label
                  const binnedKey = Object.keys(row).find(k => k.endsWith('_binned'));
                  const binLabel = binnedKey ? row[binnedKey] : `Bin_${i + 1}`;
                  return (
                    <tr key={i}>
                      {columnOrder.map((key, j) => (
                        <td key={j} style={{ padding: '4px', textAlign: 'center' }}>
                          {key === 'Bin'
                            ? binLabel
                            : key === 'Bad Rate' || key === 'Freq%'
                            ? formatToFourDecimals(row[key])
                            : String(row[key] ?? '')}
                        </td>
                      ))}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      ))}
    </div>
  );
};

export default UnivariateResults;
