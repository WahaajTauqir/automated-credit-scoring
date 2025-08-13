import './Results.css';

interface FineBinResultsProps {
  fineBinResults: Record<string, any[]>;  // object of arrays of bins per column
  formatToFourDecimals: (value: any) => string;
}

const FineBinResults = ({ fineBinResults, formatToFourDecimals }: FineBinResultsProps) => {
  if (Object.keys(fineBinResults).length === 0) return null;

  return (
    <div style={{ marginTop: '40px', width: '100%' }}>
      <h2 style={{ textAlign: 'center', marginBottom: '10px' }}>
        Fine Binning Results
      </h2>
      {Object.entries(fineBinResults).map(([col, stats], idx) => {
        // Group bins by 'group' key (adjust key name if needed)
        const groups = Array.isArray(stats) ? stats.reduce((acc: Record<string, any[]>, bin) => {
          const groupKey = bin.group ?? 'Ungrouped';
          if (!acc[groupKey]) acc[groupKey] = [];
          acc[groupKey].push(bin);
          return acc;
        }, {}) : {};

        return (
          <div key={idx} className="column-panel" style={{ marginBottom: '20px' }}>
            <h3>{col} (Fine Binned)</h3>

            {Object.entries(groups).map(([group, bins]) => {
              // Sum up Good + Bad (or fallback to Total) in current group for frequency denominator
              const groupSum = bins.reduce((sum, bin) => {
                // Assume your bins have 'Good' and 'Bad' fields
                const goodCount = bin['Good'] || 0;
                const badCount = bin['Bad'] || 0;
                const totalCount = bin['Total'] || 0;

                // Prefer Good + Bad sum if both exist, else fallback to Total
                if (goodCount || badCount) {
                  return sum + goodCount + badCount;
                } else {
                  return sum + totalCount;
                }
              }, 0);

              return (
                <div key={group} style={{ marginBottom: '15px' }}>
                  <h4>Group {group}</h4>
                  <div className="column-list">
                    <table style={{ width: '100%', color: 'white', fontSize: '14px' }}>
                      <thead>
                        <tr>
                          {Object.keys(bins[0]).map(key => (
                            <th key={key} style={{ padding: '4px', borderBottom: '1px solid gray' }}>
                              {key}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {bins.map((row, i) => (
                          <tr key={i}>
                            {Object.entries(row).map(([key, val], j) => {
                              if (key === 'Freq%') {
                                // Calculate frequency % using Good+Bad or Total
                                const goodCount = row['Good'] || 0;
                                const badCount = row['Bad'] || 0;
                                const totalCount = row['Total'] || 0;
                                const numerator = (goodCount || badCount) ? goodCount + badCount : totalCount;
                                const freq = groupSum ? (numerator / groupSum) * 100 : 0;
                                return (
                                  <td key={j} style={{ padding: '4px', textAlign: 'center' }}>
                                    {formatToFourDecimals(freq)}
                                  </td>
                                );
                              }
                              if (key === 'Bad Rate') {
                                return (
                                  <td key={j} style={{ padding: '4px', textAlign: 'center' }}>
                                    {formatToFourDecimals(val)}
                                  </td>
                                );
                              }
                              return (
                                <td key={j} style={{ padding: '4px', textAlign: 'center' }}>
                                  {String(val)}
                                </td>
                              );
                            })}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              );
            })}

          </div>
        );
      })}
    </div>
  );
};

export default FineBinResults;
