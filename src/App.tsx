import { useEffect, useState } from 'react';
import { useLocation, useNavigate, Routes, Route } from 'react-router-dom';
import CSVReader from './components/CSVReader';
import Navbar from './components/Navbar';
import AdminPanel from './components/Admin/AdminPanel';
import SelectedColumnsPage from './components/SelectedColumnsPage';
import ColumnSelectionPage from './components/ColumnSelectionPage';
import './App.css';
import './components/Admin/AdminPanel.css';

// Type definition for the new database schema
type AnalysisRecord = {
  id: number;
  dataset_path: string;
  discrete_columns: string[];  // Changed from comma-separated string to array
  continuous_columns: string[];  // Changed from comma-separated string to array
  selected_columns: string[];  // Changed from comma-separated string to array
  target_variable: string;
  created_at: string;
  total_features?: number;
  discrete_features?: number;
  continuous_features?: number;
  binning_data?: Record<string, any>;  // New: structured binning data
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
      // Preserve any existing dashboard_selected_columns from latest record to avoid clearing on older backend versions
      let preservedDashboardSelected: string[] | undefined = undefined;
      try {
        if (records && records.length > 0) {
          const latestId = records[0].id;
          const recResp = await fetch(`http://localhost:5000/api/record/${latestId}`);
          const recJson = await recResp.json();
          const dsc = recJson?.dashboard_selected_columns;
          if (typeof dsc === 'string' && dsc.trim().length > 0) {
            preservedDashboardSelected = dsc.split(',').map((s: string) => s.trim()).filter((s: string) => s);
          } else if (Array.isArray(dsc) && dsc.length > 0) {
            preservedDashboardSelected = dsc.map((s: any) => String(s).trim()).filter((s: string) => s);
          }
        }
      } catch {
        // Non-blocking: proceed without preserved selection
      }

      const resp = await fetch('http://localhost:5000/api/upsert-single-record', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          dataset_path: datasetPath,
          discrete_columns: discreteColumns,
          continuous_columns: continuousColumns,
          selected_columns: selectedForUnivariate,
          // Include preserved selection if any, to avoid clearing on older server logic
          ...(preservedDashboardSelected ? { dashboard_selected_columns: preservedDashboardSelected } : {}),
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
          // pass-through analysis results so SelectedColumnsPage can initialize immediately
          univariateResults,
          fineBinResults,
          crossTabResults: crossTabResults,
          expectedColumns: expectedColumnsForRecord,
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

  // Select/unselect all discrete columns for univariate selection
  const toggleSelectAllDiscrete = (selectAll?: boolean) => {
    setSelectedForUnivariate(prev => {
      const currentSet = new Set(prev);
      // If selectAll explicitly false, remove all discrete
      if (selectAll === false) {
        discreteColumns.forEach(c => currentSet.delete(c));
        return Array.from(currentSet);
      }

      // If selectAll explicitly true, add all discrete
      if (selectAll === true) {
        discreteColumns.forEach(c => currentSet.add(c));
        return Array.from(currentSet);
      }

      // Otherwise toggle: if all discrete are already selected -> remove them, else add them
      const allSelected = discreteColumns.every(c => currentSet.has(c));
      if (allSelected) {
        discreteColumns.forEach(c => currentSet.delete(c));
      } else {
        discreteColumns.forEach(c => currentSet.add(c));
      }
      return Array.from(currentSet);
    });
  };

  // Select/unselect all continuous columns for univariate selection
  const toggleSelectAllContinuous = (selectAll?: boolean) => {
    setSelectedForUnivariate(prev => {
      const currentSet = new Set(prev);
      if (selectAll === false) {
        continuousColumns.forEach(c => currentSet.delete(c));
        return Array.from(currentSet);
      }
      if (selectAll === true) {
        continuousColumns.forEach(c => currentSet.add(c));
        return Array.from(currentSet);
      }
      const allSelected = continuousColumns.every(c => currentSet.has(c));
      if (allSelected) {
        continuousColumns.forEach(c => currentSet.delete(c));
      } else {
        continuousColumns.forEach(c => currentSet.add(c));
      }
      return Array.from(currentSet);
    });
  };

  const assignRemainingToContinuous = () => {
    const selectedDiscrete = new Set(discreteColumns);
    const remaining = columns.filter(col => !selectedDiscrete.has(col) && col !== targetVariable);
    setContinuousColumns(remaining);
  };

  const handleTypeChange = (column: string, type: string) => {
    // Use functional updates to avoid race conditions when many changes occur quickly
    let computedDiscrete: string[] = [];
    let computedContinuous: string[] = [];

    setDiscreteColumns(prev => {
      const next = type === 'discrete'
        ? Array.from(new Set([...prev, column]))
        : prev.filter(c => c !== column);
      computedDiscrete = next;
      return next;
    });

    setContinuousColumns(prev => {
      const next = type === 'continuous'
        ? Array.from(new Set([...prev, column]))
        : prev.filter(c => c !== column);
      computedContinuous = next;
      return next;
    });

    // Persist change to backend (non-blocking). Backend will recalc dataset counts.
    (async () => {
      try {
        await fetch('http://localhost:5000/api/upsert-single-record', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            dataset_path: datasetPath,
            discrete_columns: computedDiscrete,
            continuous_columns: computedContinuous,
            selected_columns: selectedForUnivariate,
            target_variable: targetVariable
          })
        });
      } catch (err) {
        // Non-fatal: keep UI responsive even if persistence fails
        console.error('Failed to persist type change:', err);
      }
    })();
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

  // Persist target variable to backend when user selects it (non-blocking)
  useEffect(() => {
    if (!targetVariable) return;
    (async () => {
      try {
        await fetch('http://localhost:5000/api/upsert-single-record', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            dataset_path: datasetPath,
            discrete_columns: discreteColumns,
            continuous_columns: continuousColumns,
            selected_columns: selectedForUnivariate,
            target_variable: targetVariable
          })
        });
      } catch (err) {
        console.error('Failed to persist target variable:', err);
      }
    })();
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
      const data: AnalysisRecord & { univariate_results?: any; finebin_results?: any; crosstab_results?: any } = await recResp.json();

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

      // Fallback: infer from stored column fields. Accept both array or comma-separated string formats.
      if (loadedColumns.length === 0) {
        const inferred = new Set<string>();
        const addField = (field: any) => {
          if (!field) return;
          if (Array.isArray(field)) {
            field.forEach((c: any) => { if (c) inferred.add(String(c).trim()); });
          } else if (typeof field === 'string') {
            field.split(',').map(s => s.trim()).filter(Boolean).forEach((c: string) => inferred.add(c));
          }
        };

        addField((data as any).discrete_columns);
        addField((data as any).continuous_columns);
        addField((data as any).selected_columns);
        loadedColumns = Array.from(inferred);
      }

      // Update state
  setColumns(loadedColumns);
      const discreteArr: string[] = Array.isArray((data as any).discrete_columns)
        ? (data as any).discrete_columns
        : (typeof (data as any).discrete_columns === 'string'
          ? (data as any).discrete_columns.split(',').filter(Boolean)
          : []);

      const continuousArr: string[] = Array.isArray((data as any).continuous_columns)
        ? (data as any).continuous_columns
        : (typeof (data as any).continuous_columns === 'string'
          ? (data as any).continuous_columns.split(',').filter(Boolean)
          : []);

      const selectedArr: string[] = Array.isArray((data as any).selected_columns)
        ? (data as any).selected_columns
        : (typeof (data as any).selected_columns === 'string'
          ? (data as any).selected_columns.split(',').filter(Boolean)
          : []);

      const expected = loadedColumns.length ? loadedColumns : Array.from(new Set([...discreteArr, ...continuousArr, ...selectedArr]));
  setExpectedColumnsForRecord(expected);
      setDiscreteColumns(discreteArr);
      setContinuousColumns(continuousArr);
      setSelectedForUnivariate(selectedArr);
      setTargetVariable(data.target_variable || '');
      let uni: Record<string, any> = {};
      let fine: Record<string, any> = {};
      let cross: Record<string, any> = {};
      // Backend now returns structured objects/arrays for these fields.
      uni = data.univariate_results && typeof data.univariate_results !== 'string' ? data.univariate_results : {};
      fine = data.finebin_results && typeof data.finebin_results !== 'string' ? data.finebin_results : {};
      cross = data.crosstab_results && typeof data.crosstab_results !== 'string' ? data.crosstab_results : {};
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
            toggleSelectAllDiscrete={toggleSelectAllDiscrete}
            toggleSelectAllContinuous={toggleSelectAllContinuous}
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