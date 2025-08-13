import { useEffect, useState } from 'react';
import { useLocation, useNavigate, Routes, Route } from 'react-router-dom';
import CSVReader from './components/CSVReader';
import Navbar from './components/Navbar';
import ColumnPanels from './components/ColumnsPanel';
import UnivariateResults from './components/UnivariateResults';
import FineBinResults from './components/FInebinResults';
import CrossTabResults from './components/CresstabResults';
import AdminPanel from './components/Admin/AdminPanel';
import SelectedColumnsPage from './components/SelectedColumnsPage';
import './App.css';

function App() {
  const location = useLocation();
  const navigate = useNavigate();

  // State definitions with explicit typing
  const [columns, setColumns] = useState<string[]>([]);
  const [discreteColumns, setDiscreteColumns] = useState<string[]>([]);
  const [continuousColumns, setContinuousColumns] = useState<string[]>([]);
  const [targetVariable, setTargetVariable] = useState<string>('');
  const [univariateResults, setUnivariateResults] = useState<Record<string, any>>({});
  const [fineBinResults, setFineBinResults] = useState<Record<string, any>>({});
  const [crossTabResults, setCrossTabResults] = useState<Record<string, any>>({});
  const [loading, setLoading] = useState<boolean>(false);
  const [targetCounts, setTargetCounts] = useState<Record<string, number>>({});
  const [selectedForUnivariate, setSelectedForUnivariate] = useState<string[]>([]);

  // For bin selection in CrossTab
  const [selectedBinGroups, setSelectedBinGroups] = useState<Record<string, any[]>>({});

  // Restore state from navigation (AdminPanel)
  useEffect(() => {
    if (location.state) {
      const s = location.state as any;
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

  const handleProceedToSelectedColumns = async () => {
    if (selectedForUnivariate.length === 0) {
      alert('Please select at least one column.');
      return;
    }
    // Save the current selection to the backend
    try {
      const resp = await fetch('http://localhost:5000/api/upsert-single-record', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          dataset_path: 'uploaded.csv',
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
      return;
    } catch (e) {
      // Non-blocking: allow navigation even if save fails
      console.error('Failed to upsert record:', e);
    }
    navigate('/selected-columns', {
      state: {
        selectedColumns: selectedForUnivariate,
        discreteColumns,
        continuousColumns,
        targetVariable
      }
    });
  };

  const handleCSVUploaded = (headers: string[]) => {
    setColumns(headers);
    setDiscreteColumns([]);
    setContinuousColumns([]);
    setTargetVariable('');
    setUnivariateResults({});
    setFineBinResults({});
    setCrossTabResults({});
    setSelectedBinGroups({});
    setCurrentPage(1);
    setTargetCounts({});
  };

  const toggleSelectedForUnivariate = (col: string) => {
    setSelectedForUnivariate(prev =>
      prev.includes(col) ? prev.filter(c => c !== col) : [...prev, col]
    );
  };

  const assignRemainingToContinuous = () => {
    const selectedDiscrete = new Set(discreteColumns);
    const remaining = columns.filter(
      col => !selectedDiscrete.has(col) && col !== targetVariable
    );
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

  const handleRunUnivariate = async () => {
    if (!targetVariable) {
      alert('Please select a target variable.');
      return;
    }
    if (selectedForUnivariate.length === 0) {
      alert('Please select at least one column to analyze.');
      return;
    }

    setLoading(true);
    try {
      // Split into discrete/continuous
      const selectedDiscrete = selectedForUnivariate.filter(col => discreteColumns.includes(col));
      const selectedContinuous = selectedForUnivariate.filter(col => continuousColumns.includes(col));

      // Univariate analysis
      const univariateRes = await fetch('http://localhost:5000/api/univariate-analysis', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          discrete: selectedDiscrete,
          continuous: selectedContinuous,
          target: targetVariable,
        }),
      });
      const univariateData = await univariateRes.json();
      if (univariateData.error) {
        alert(univariateData.error);
        return;
      }
      setUnivariateResults(univariateData);

      // Cross-tabulation
      const crossTabRes = await fetch('http://localhost:5000/api/cross-tab', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          variables: selectedForUnivariate,
          target: targetVariable,
        }),
      });
      const crossTabData = await crossTabRes.json();
      if (!crossTabData.error) {
        setCrossTabResults(crossTabData);
      }

  // Upsert single record (create first time, update thereafter)
  await fetch('http://localhost:5000/api/upsert-single-record', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          dataset_path: 'uploaded.csv',
          discrete_columns: discreteColumns,
          continuous_columns: continuousColumns,
          selected_columns: selectedForUnivariate,
          target_variable: targetVariable,
          univariate_results: JSON.stringify(univariateData),
          finebin_results: JSON.stringify(fineBinResults),
          crosstab_results: JSON.stringify(crossTabData),
        }),
      });
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
        headers: { 'Content-Type': 'application/json' },
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

  return (
    <Routes>
      <Route
        path="/"
        element={
          <div>
            <Navbar />
            <div className="app-container">
              {columns.length === 0 ? (
                <div className="upload-wrapper">
                  <CSVReader onCSVUploaded={handleCSVUploaded} />
                </div>
              ) : (
                <>
                  <ColumnPanels
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
                  />
                  <div style={{ marginTop: '30px', textAlign: 'center' }}>
                    <button className="file-upload-label" onClick={handleProceedToSelectedColumns}>
                      Proceed to Selected Columns
                    </button>
                  </div>
                  <UnivariateResults
                    univariateResults={univariateResults}
                    formatToFourDecimals={formatToFourDecimals}
                  />
                  <FineBinResults
                    fineBinResults={fineBinResults}
                    formatToFourDecimals={formatToFourDecimals}
                  />
                  <CrossTabResults
                    crossTabResults={crossTabResults}
                    formatToFourDecimals={formatToFourDecimals}
                    selectedBins={selectedBinGroups} // renamed to match component
                    onBinToggle={toggleBinSelection} // renamed to match component
                  />
                </>
              )}
            </div>
          </div>
        }
      />
      <Route path="/admin" element={<AdminPanel />} />
      <Route path="/selected-columns" element={<SelectedColumnsPage />} />
    </Routes>
  );
}

export default App;
