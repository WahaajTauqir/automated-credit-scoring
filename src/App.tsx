import { useEffect, useState } from 'react';
import { useLocation, useNavigate, Routes, Route } from 'react-router-dom';
import CSVReader from './components/CSVReader';
import Navbar from './components/Navbar';
import AdminPanel from './components/Admin/AdminPanel';
import SelectedColumnsPage from './components/SelectedColumnsPage';
import ColumnSelectionPage from './components/ColumnSelectionPage';
import './App.css';
import './components/Admin/AdminPanel.css';

// Reuse the analysis record type from Admin panel locally for inline table
type AnalysisRecord = {
  id: number;
  dataset_path: string;
  discrete_columns: string;
  continuous_columns: string;
  selected_columns: string;
  target_variable: string;
  created_at: string;
  univariate_results?: string;
  finebin_results?: string;
  crosstab_results?: string;
};

function App() {
  const location = useLocation();
  const navigate = useNavigate();

  // State definitions
  const [columns, setColumns] = useState<string[]>([]);
  const [discreteColumns, setDiscreteColumns] = useState<string[]>([]);
  const [continuousColumns, setContinuousColumns] = useState<string[]>([]);
  const [targetVariable, setTargetVariable] = useState<string>('');
  const [univariateResults, setUnivariateResults] = useState<Record<string, any>>({});
  const [fineBinResults, setFineBinResults] = useState<Record<string, any>>({});
  const [crossTabResults, setCrossTabResults] = useState<Record<string, any>>({});
  const [targetCounts, setTargetCounts] = useState<Record<string, number>>({});
  const [selectedForUnivariate, setSelectedForUnivariate] = useState<string[]>([]);

  const [selectedBinGroups, setSelectedBinGroups] = useState<Record<string, any[]>>({});
  const [datasetPath, setDatasetPath] = useState<string>('uploaded.csv');
  const [restoring, setRestoring] = useState<boolean>(false);
  const [expectedColumnsForRecord, setExpectedColumnsForRecord] = useState<string[] | undefined>(undefined);

  // Records (moved from AdminPanel into main page)
  const [records, setRecords] = useState<AnalysisRecord[]>([]);
  const [recordsLoading, setRecordsLoading] = useState<boolean>(false);

  // Fetch existing analysis records on mount
  useEffect(() => {
    setRecordsLoading(true);
    fetch('http://localhost:5000/api/records')
      .then(res => res.json())
      .then(data => setRecords(Array.isArray(data) ? data : []))
      .catch(() => {})
      .finally(() => setRecordsLoading(false));
  }, []);

  // Restore state from navigation (AdminPanel)
  useEffect(() => {
    if (location.state) {
      const s = location.state as any;
  if (s.columns) setColumns(s.columns || []);
      setDiscreteColumns(s.discreteColumns || []);
      setContinuousColumns(s.continuousColumns || []);
      setSelectedForUnivariate(s.selectedForUnivariate || []);
      setTargetVariable(s.targetVariable || '');
      setUnivariateResults(s.univariateResults || {});
      setFineBinResults(s.fineBinResults || {});
      setCrossTabResults(s.crossTabResults || {});
    }
  }, [location.state]);

  // Pagination setup
  const columnsPerPage = 7;
  const [currentPage, setCurrentPage] = useState<number>(1);
  const totalPages = Math.ceil(columns.length / columnsPerPage);
  const paginatedColumns = columns.slice(
    (currentPage - 1) * columnsPerPage,
    currentPage * columnsPerPage
  );

  // Async handleFineBin
  const handleFineBin = async (column: string): Promise<void> => {
    try {
      console.log("Fine bin clicked for column:", column);
      // Example API call (replace with your endpoint)
      // const res = await fetch('http://localhost:5000/api/fine-bin', { ... });
      // const data = await res.json();
    } catch (err) {
      console.error("Error in fine binning:", err);
    }
  };

  const handleProceedToSelectedColumns = async () => {
    if (selectedForUnivariate.length === 0) {
      alert('Please select at least one column.');
      return;
    }

    try {
      const resp = await fetch('http://localhost:5000/api/upsert-single-record', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          dataset_path: datasetPath,
          discrete_columns: discreteColumns,
          continuous_columns: continuousColumns,
          selected_columns: selectedForUnivariate,
          target_variable: targetVariable,
          univariate_results: '',
          finebin_results: '',
          crosstab_results: ''
        })
      });
      const saved = await resp.json().catch(() => ({} as any));
      const newRecordId = saved?.id;

      navigate('/selected-columns', {
        state: {
          selectedColumns: selectedForUnivariate,
          discreteColumns,
          continuousColumns,
          targetVariable,
          recordId: newRecordId || undefined,
        }
      });
    } catch (e) {
      console.error('Failed to upsert record:', e);
      navigate('/selected-columns', {
        state: {
          selectedColumns: selectedForUnivariate,
          discreteColumns,
          continuousColumns,
          targetVariable
        }
      });
    }
  };

  const handleCSVUploaded = (headers: string[], _rows?: any[], uploadedPath?: string) => {
    setColumns(headers);
    if (uploadedPath) setDatasetPath(uploadedPath);
  setExpectedColumnsForRecord(undefined);
    setDiscreteColumns([]);
    setContinuousColumns([]);
    setTargetVariable('');
    setUnivariateResults({});
    setFineBinResults({});
    setCrossTabResults({});
    setSelectedBinGroups({});
    setCurrentPage(1);
    setTargetCounts({});
    navigate('/column-selection');
  };

  const toggleSelectedForUnivariate = (col: string) => {
    setSelectedForUnivariate(prev =>
      prev.includes(col) ? prev.filter(c => c !== col) : [...prev, col]
    );
  };

  const assignRemainingToContinuous = () => {
    const selectedDiscrete = new Set(discreteColumns);
    const remaining = columns.filter(col => !selectedDiscrete.has(col) && col !== targetVariable);
    setContinuousColumns(remaining);
  };

  const handleTypeChange = (column: string, type: string) => {
    if (type === 'discrete') {
      setDiscreteColumns(prev => [...new Set([...prev, column])]);
      setContinuousColumns(prev => prev.filter(c => c !== column));
    } else if (type === 'continuous') {
      setContinuousColumns(prev => [...new Set([...prev, column])]);
      setDiscreteColumns(prev => prev.filter(c => c !== column));
    }
  };


  const fetchTargetCounts = async (col: string) => {
    try {
      const res = await fetch('http://localhost:5000/api/target-distribution', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ column: col }),
      });
      const data = await res.json();
      if (!data.error) setTargetCounts(data);
    } catch (err) {
      console.error('Failed to fetch target counts:', err);
    }
  };

  useEffect(() => {
    if (targetVariable) fetchTargetCounts(targetVariable);
  }, [targetVariable]);

  const toggleBinSelection = (col: string, binValue: any) => {
    setSelectedBinGroups(prev => {
      const currentBins = prev[col] || [];
      if (currentBins.includes(binValue)) {
        return { ...prev, [col]: currentBins.filter(v => v !== binValue) };
      }
      return { ...prev, [col]: [...currentBins, binValue] };
    });
  };

  const handleNextPage = () => {
    if (currentPage < totalPages) setCurrentPage(prev => prev + 1);
  };

  const handlePrevPage = () => {
    if (currentPage > 1) setCurrentPage(prev => prev - 1);
  };

  const formatToFourDecimals = (value: any): string => {
    return typeof value === 'number' ? value.toFixed(4) : String(value);
  };

  // View existing record: load its saved state then go to column selection
  const handleRecordView = async (id: number) => {
    try {
      setRestoring(true);
      // Fetch complete record
      const recResp = await fetch(`http://localhost:5000/api/record/${id}`);
      const data: AnalysisRecord & { univariate_results?: string; finebin_results?: string; crosstab_results?: string } = await recResp.json();

      // Ask backend to load dataset & return columns
      let loadedColumns: string[] = [];
      try {
        const loadRes = await fetch(`http://localhost:5000/api/record/${id}/load-dataset`);
        const loadJson = await loadRes.json();
        if (loadRes.ok) {
          if (Array.isArray(loadJson.columns)) loadedColumns = loadJson.columns;
          if (loadJson.dataset_path) setDatasetPath(loadJson.dataset_path);
        }
      } catch { /* ignore */ }

      // Fallback: generic columns endpoint
      if (loadedColumns.length === 0) {
        try {
          const colsRes = await fetch('http://localhost:5000/api/uploaded-csv-columns');
          if (colsRes.ok) {
            const colsJson = await colsRes.json();
            if (Array.isArray(colsJson.columns)) loadedColumns = colsJson.columns;
          }
        } catch { /* ignore */ }
      }

      // Fallback: infer from stored column strings
      if (loadedColumns.length === 0) {
        const inferred = new Set<string>();
        (data.discrete_columns || '').split(',').filter(Boolean).forEach(c => inferred.add(c));
        (data.continuous_columns || '').split(',').filter(Boolean).forEach(c => inferred.add(c));
        (data.selected_columns || '').split(',').filter(Boolean).forEach(c => inferred.add(c));
        loadedColumns = Array.from(inferred);
      }

      // Update state
  setColumns(loadedColumns);
      const discreteArr = data.discrete_columns ? data.discrete_columns.split(',').filter(Boolean) : [];
      const continuousArr = data.continuous_columns ? data.continuous_columns.split(',').filter(Boolean) : [];
      const selectedArr = data.selected_columns ? data.selected_columns.split(',').filter(Boolean) : [];
  const expected = loadedColumns.length ? loadedColumns : Array.from(new Set([...discreteArr, ...continuousArr, ...selectedArr]));
  setExpectedColumnsForRecord(expected);
      setDiscreteColumns(discreteArr);
      setContinuousColumns(continuousArr);
      setSelectedForUnivariate(selectedArr);
      setTargetVariable(data.target_variable || '');
      const uni = data.univariate_results ? JSON.parse(data.univariate_results) : {};
      const fine = data.finebin_results ? JSON.parse(data.finebin_results) : {};
      const cross = data.crosstab_results ? JSON.parse(data.crosstab_results) : {};
      setUnivariateResults(uni);
      setFineBinResults(fine);
      setCrossTabResults(cross);
      setCurrentPage(1);

      // Navigate passing full state to cover edge cases where local effect didn't fire yet
  navigate('/column-selection', {
        state: {
          columns: loadedColumns,
          discreteColumns: discreteArr,
            continuousColumns: continuousArr,
            selectedForUnivariate: selectedArr,
            targetVariable: data.target_variable || '',
            univariateResults: uni,
            fineBinResults: fine,
    crossTabResults: cross,
    expectedColumns: expected
        }
      });
    } catch (e) {
      console.error('Failed to load record', e);
      alert('Failed to load record');
    } finally {
      setTimeout(() => setRestoring(false), 300);
    }
  };

  const handleRecordDelete = (id: number) => {
    if (!window.confirm('Are you sure you want to delete this record?')) return;
    fetch(`http://localhost:5000/api/record/${id}`, { method: 'DELETE' })
      .then(res => {
        if (res.ok) {
          setRecords(prev => prev.filter(r => r.id !== id));
        }
      })
      .catch(() => {});
  };

  return (
    <Routes>
      <Route
        path="/"
        element={
          <div>
            <Navbar />
            <div className="app-container">
              <div className="upload-wrapper">
                <CSVReader onCSVUploaded={handleCSVUploaded} />
              </div>

              {/* Records Table Section */}
              <div style={{ width: '100%', marginTop: '40px' }}>
                <h2 style={{ textAlign: 'center', marginBottom: '12px' }}>Records</h2>
                {recordsLoading ? (
                  <div className="admin-loading">Loading records...</div>
                ) : records.length === 0 ? (
                  <div className="admin-empty">No analyses found.</div>
                ) : (
                  <div className="admin-panel-container" style={{ margin: '0 auto', maxWidth: '100%' }}>
                    <table className="admin-table">
                      <thead>
                        <tr>
                          <th style={{ textAlign: 'center' }}>ID</th>
                          <th style={{ textAlign: 'center' }}>Dataset</th>
                          <th style={{ textAlign: 'center' }}>Selected Columns</th>
                          <th style={{ textAlign: 'center' }}>Date</th>
                          <th style={{ textAlign: 'center' }}>Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {records.map(rec => (
                          <tr key={rec.id}>
                            <td style={{ textAlign: 'center' }}>{rec.id}</td>
                            <td style={{ textAlign: 'center' }}>{rec.dataset_path}</td>
                            <td style={{ textAlign: 'center', whiteSpace: 'pre-wrap', wordBreak: 'break-word', maxWidth: 200 }}>{rec.selected_columns}</td>
                            <td style={{ textAlign: 'center' }}>{rec.created_at}</td>
                            <td style={{ textAlign: 'center' }}>
                              <div style={{ display: 'inline-flex', gap: '8px' }}>
                                <button className="admin-action-btn" title="View" onClick={() => handleRecordView(rec.id)}>View</button>
                                <button className="admin-action-btn" title="Delete" onClick={() => handleRecordDelete(rec.id)}>Delete</button>
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </div>
          </div>
        }
      />
      <Route
        path="/column-selection"
        element={
          <ColumnSelectionPage
            columns={columns}
            paginatedColumns={paginatedColumns}
            discreteColumns={discreteColumns}
            continuousColumns={continuousColumns}
            targetVariable={targetVariable}
            targetCounts={targetCounts}
            handleTypeChange={handleTypeChange}
            setTargetVariable={setTargetVariable}
            currentPage={currentPage}
            totalPages={totalPages}
            onNextPage={handleNextPage}
            onPrevPage={handlePrevPage}
            assignRemainingToContinuous={assignRemainingToContinuous}
            selectedForUnivariate={selectedForUnivariate}
            toggleSelectedForUnivariate={toggleSelectedForUnivariate}
            handleFineBin={handleFineBin}
            handleProceedToSelectedColumns={handleProceedToSelectedColumns}
            univariateResults={univariateResults}
            fineBinResults={fineBinResults}
            crossTabResults={crossTabResults}
            selectedBinGroups={selectedBinGroups}
            toggleBinSelection={toggleBinSelection}
            formatToFourDecimals={formatToFourDecimals}
            restoring={restoring}
            expectedColumns={expectedColumnsForRecord}
            onUploadReplacement={(headers, rows, path) => handleCSVUploaded(headers, rows, path)}
          />
        }
      />
      <Route path="/admin" element={<AdminPanel />} />
      <Route path="/selected-columns" element={<SelectedColumnsPage />} />
    </Routes>
  );
}

export default App;