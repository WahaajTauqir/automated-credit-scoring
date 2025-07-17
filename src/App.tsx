import { useEffect, useState } from 'react';
import CSVReader from './components/CSVReader';
import Navbar from './components/Navbar';
import './App.css';

function App() {
  const [columns, setColumns] = useState<string[]>([]);
  const [discreteColumns, setDiscreteColumns] = useState<string[]>([]);
  const [continuousColumns, setContinuousColumns] = useState<string[]>([]);
  const [targetVariable, setTargetVariable] = useState<string>('');
  const [univariateResults, setUnivariateResults] = useState<any>({});
  const [fineBinResults, setFineBinResults] = useState<any>({});
  const [crossTabResults, setCrossTabResults] = useState<any>({});
  const [loading, setLoading] = useState<boolean>(false);
  const [targetCounts, setTargetCounts] = useState<{ [key: string]: number }>({});

  // Pagination setup
  const columnsPerPage = 7;
  const [currentPage, setCurrentPage] = useState<number>(1);
  const totalPages = Math.ceil(columns.length / columnsPerPage);
  const paginatedColumns = columns.slice(
    (currentPage - 1) * columnsPerPage,
    currentPage * columnsPerPage
  );

  const handleCSVUploaded = (headers: string[]) => {
    setColumns(headers);
    setDiscreteColumns([]);
    setContinuousColumns([]);
    setTargetVariable('');
    setUnivariateResults({});
    setFineBinResults({});
    setCrossTabResults({});
    setCurrentPage(1);
    setTargetCounts({});
  };

  const handleTypeChange = (column: string, type: string) => {
    if (type === 'discrete') {
      setDiscreteColumns((prev) => [...new Set([...prev, column])]);
      setContinuousColumns((prev) => prev.filter((c) => c !== column));
    } else if (type === 'continuous') {
      setContinuousColumns((prev) => [...new Set([...prev, column])]);
      setDiscreteColumns((prev) => prev.filter((c) => c !== column));
    }
  };

  const handleRunUnivariate = async () => {
    if (!targetVariable) {
      alert('Please select a target variable.');
      return;
    }

    const variables = [...discreteColumns, ...continuousColumns];
    if (variables.length === 0) {
      alert('Please select at least one discrete or continuous column.');
      return;
    }

    setLoading(true);
    try {
      // Run Univariate Analysis
      const univariateRes = await fetch('http://localhost:5000/api/univariate-analysis', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          discrete: discreteColumns,
          continuous: continuousColumns,
          target: targetVariable,
        }),
      });
      const univariateData = await univariateRes.json();
      if (univariateData.error) {
        alert(univariateData.error);
        setLoading(false);
        return;
      }
      setUnivariateResults(univariateData);

      // Run Fine Binning for each variable
      const fineBinResultsTemp: any = {};
      for (const col of variables) {
        const varType = discreteColumns.includes(col) ? 'discrete' : 'continuous';
        // Default bin merges (customize as needed)
        const binMerges = varType === 'continuous'
          ? { 1: [1, 2], 2: [3, 4, 5], 3: [6, 7, 8, 9, 10] }
          : { 1: [1, 2], 2: [3, 4], 3: [5, 6, 7, 8] };

        const fineBinRes = await fetch('http://localhost:5000/api/fine-bin', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            variable: col,
            target: targetVariable,
            type: varType,
            bin_merges: binMerges,
          }),
        });
        const fineBinData = await fineBinRes.json();
        if (!fineBinData.error) {
          fineBinResultsTemp[col] = fineBinData.stats;
        }
      }
      setFineBinResults(fineBinResultsTemp);

      // Run Cross-Tabulation
      const crossTabRes = await fetch('http://localhost:5000/api/cross-tab-view', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          variables,
          target: targetVariable,
        }),
      });
      const crossTabData = await crossTabRes.json();
      if (crossTabData.error) {
        alert(crossTabData.error);
      } else {
        setCrossTabResults(crossTabData);
      }
    } catch (err) {
      alert('Analysis failed.');
    } finally {
      setLoading(false);
    }
  };

  const fetchTargetCounts = async (col: string) => {
    try {
      const res = await fetch('http://localhost:5000/api/target-distribution', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ column: col }),
      });
      const data = await res.json();
      if (!data.error) {
        setTargetCounts(data);
      }
    } catch (err) {
      console.error('Failed to fetch target counts:', err);
    }
  };

  useEffect(() => {
    if (targetVariable) {
      fetchTargetCounts(targetVariable);
    }
  }, [targetVariable]);

  const handleNextPage = () => {
    if (currentPage < totalPages) setCurrentPage((prev) => prev + 1);
  };

  const handlePrevPage = () => {
    if (currentPage > 1) setCurrentPage((prev) => prev - 1);
  };

  // Helper function to format numbers to 4 decimal places
  const formatToFourDecimals = (value: any): string => {
    if (typeof value === 'number') {
      return value.toFixed(4);
    }
    return String(value);
  };

  return (
    <>
      <Navbar />
      <div className="app-container">
        {columns.length === 0 ? (
          <div className="upload-wrapper">
            <CSVReader onCSVUploaded={handleCSVUploaded} />
          </div>
        ) : (
          <>
            <div className="columns-layout">
              {/* All Columns */}
              <div className="column-panel">
                <h3>All Columns</h3>
                <p className="column-count">Total: {columns.length} columns</p>
                <div className="column-list">
                  {paginatedColumns.map((col, idx) => (
                    <div key={idx} className="column-box">
                      {col}
                      <div className="radio-group">
                        <label>
                          <input
                            type="radio"
                            name={`type-${col}`}
                            value="discrete"
                            checked={discreteColumns.includes(col)}
                            onChange={() => handleTypeChange(col, 'discrete')}
                          />
                          Discrete
                        </label>
                        <label>
                          <input
                            type="radio"
                            name={`type-${col}`}
                            value="continuous"
                            checked={continuousColumns.includes(col)}
                            onChange={() => handleTypeChange(col, 'continuous')}
                          />
                          Continuous
                        </label>
                      </div>
                    </div>
                  ))}
                </div>
                <div className="pagination-controls">
                  <button onClick={handlePrevPage} disabled={currentPage === 1}>
                    Previous
                  </button>
                  <span>Page {currentPage} of {totalPages}</span>
                  <button onClick={handleNextPage} disabled={currentPage === totalPages}>
                    Next
                  </button>
                </div>
              </div>

              {/* Discrete Columns */}
              <div className="column-panel">
                <h3>Discrete Columns</h3>
                <div className="column-list">
                  {discreteColumns.length === 0 && <div className="column-box">(None selected)</div>}
                  {discreteColumns.map((col, idx) => (
                    <div key={idx} className="column-box">{col}</div>
                  ))}
                </div>
              </div>

              {/* Continuous Columns */}
              <div className="column-panel">
                <h3>Continuous Columns</h3>
                <div className="column-list">
                  {continuousColumns.length === 0 && <div className="column-box">(None selected)</div>}
                  {continuousColumns.map((col, idx) => (
                    <div key={idx} className="column-box">{col}</div>
                  ))}
                </div>
              </div>

              {/* Target Column + Class Distribution Donut */}
              <div className="column-panel" style={{ minWidth: '240px' }}>
                <h3>Target Variable</h3>
                <div className="column-list">
                  <label htmlFor="target-select">Select Target Column:</label>
                  <select
                    id="target-select"
                    value={targetVariable}
                    onChange={(e) => setTargetVariable(e.target.value)}
                  >
                    <option value="">-- Select --</option>
                    {columns.map((col, idx) => (
                      <option key={idx} value={col}>
                        {col}
                      </option>
                    ))}
                  </select>
                  {targetVariable && (
                    <>
                      <p className="selected-target">Selected: {targetVariable}</p>
                      <div className="donut-chart">
                        {Object.entries(targetCounts).map(([label, count], idx) => {
                          const total = Object.values(targetCounts).reduce((a, b) => a + b, 0);
                          const percent = total ? ((count / total) * 100).toFixed(1) : 0;
                          const color = label === '1' ? '#f85149' : '#238636';

                          return (
                            <div className="donut-segment" key={idx}>
                              <svg width="130" height="120" viewBox="0 0 36 36">
                                <path
                                  className="circle-bg"
                                  d="M18 2.0845
                                     a 15.9155 15.9155 0 0 1 0 31.831
                                     a 15.9155 15.9155 0 0 1 0 -31.831"
                                  fill="none"
                                  stroke="#30363d"
                                  strokeWidth="3"
                                />
                                <path
                                  className="circle"
                                  stroke={color}
                                  strokeWidth="3"
                                  fill="none"
                                  strokeDasharray={`${percent}, 100`}
                                  d="M18 2.0845
                                     a 15.9155 15.9155 0 0 1 0 31.831
                                     a 15.9155 15.9155 0 0 1 0 -31.831"
                                />
                                <text x="18" y="20.35" className="percentage" textAnchor="middle" fill={color}>
                                  {label}: {percent}%
                                </text>
                              </svg>
                            </div>
                          );
                        })}
                      </div>
                    </>
                  )}
                </div>
              </div>
            </div>

            {/* Run Button */}
            <div style={{ marginTop: '30px', textAlign: 'center' }}>
              <button
                className="file-upload-label"
                onClick={handleRunUnivariate}
                disabled={loading}
              >
                {loading ? 'Running Analysis...' : 'Run Analysis'}
              </button>
            </div>

            {/* Univariate Results */}
            {Object.keys(univariateResults).length > 0 && (
              <div style={{ marginTop: '40px', width: '100%' }}>
                <h2 style={{ textAlign: 'center', marginBottom: '10px' }}>
                  Univariate Analysis Results
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
            )}

            {/* Fine Binning Results */}
            {Object.keys(fineBinResults).length > 0 && (
              <div style={{ marginTop: '40px', width: '100%' }}>
                <h2 style={{ textAlign: 'center', marginBottom: '10px' }}>
                  Fine Binning Results
                </h2>
                {Object.entries(fineBinResults).map(([col, stats]: any, idx) => (
                  <div key={idx} className="column-panel" style={{ marginBottom: '20px' }}>
                    <h3>{col} (Fine Binned)</h3>
                    <div className="column-list">
                      <table style={{ width: '100%', color: 'white', fontSize: '14px' }}>
                        <thead>
                          <tr>
                            {Object.keys(stats[0]).map((key) => (
                              <th key={key} style={{ padding: '4px', borderBottom: '1px solid gray' }}>
                                {key}
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {stats.map((row: any, i: number) => (
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
            )}

            {/* Cross-Tabulation Results */}
            {Object.keys(crossTabResults).length > 0 && (
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
            )}
          </>
        )}
      </div>
    </>
  );
}

export default App;