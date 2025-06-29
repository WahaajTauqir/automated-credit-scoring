import { useState } from 'react';
import CSVReader from './components/CSVReader';
import Navbar from './components/Navbar';

import './App.css';

function App() {
    const [columns, setColumns] = useState<string[]>([]);
    const [discreteColumns, setDiscreteColumns] = useState<string[]>([]);
    const [continuousColumns, setContinuousColumns] = useState<string[]>([]);
    const [targetVariable, setTargetVariable] = useState<string>('');
    const [univariateResults, setUnivariateResults] = useState<any>({});
    const [loading, setLoading] = useState<boolean>(false);

    const handleCSVUploaded = (headers: string[]) => {
        setColumns(headers);
        setDiscreteColumns([]);
        setContinuousColumns([]);
        setTargetVariable('');
        setUnivariateResults({});
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

        setLoading(true);
        try {
            const res = await fetch('http://localhost:5000/api/univariate-analysis', {
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

            const data = await res.json();
            if (data.error) {
                alert(data.error);
            } else {
                setUnivariateResults(data);
            }
        } catch (err) {
            alert('Univariate analysis failed.');
        } finally {
            setLoading(false);
        }
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
                            <div className="column-panel">
                                <h3>All Columns</h3>
                                <p className="column-count">Total: {columns.length} columns</p>
                                <div className="column-list">
                                    {columns.map((col, idx) => (
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
                            </div>

                            <div className="column-panel">
                                <h3>Discrete Columns</h3>
                                <div className="column-list">
                                    {discreteColumns.length === 0 && (
                                        <div className="column-box">(None selected)</div>
                                    )}
                                    {discreteColumns.map((col, idx) => (
                                        <div key={idx} className="column-box">{col}</div>
                                    ))}
                                </div>
                            </div>

                            <div className="column-panel">
                                <h3>Continuous Columns</h3>
                                <div className="column-list">
                                    {continuousColumns.length === 0 && (
                                        <div className="column-box">(None selected)</div>
                                    )}
                                    {continuousColumns.map((col, idx) => (
                                        <div key={idx} className="column-box">{col}</div>
                                    ))}
                                </div>
                            </div>

                            <div className="column-panel">
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
                                        <p className="selected-target">Selected: {targetVariable}</p>
                                    )}
                                </div>
                            </div>
                        </div>

                        <div style={{ marginTop: '30px', textAlign: 'center' }}>
                            <button className="file-upload-label" onClick={handleRunUnivariate} disabled={loading}>
                                {loading ? 'Running Analysis...' : 'Run Univariate Analysis'}
                            </button>
                        </div>

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
                                                            {Object.values(row).map((val, j) => (
                                                                <td key={j} style={{ padding: '4px', textAlign: 'center' }}>
                                                                    {String(val)}
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
