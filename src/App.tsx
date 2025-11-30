import { useEffect, useState } from 'react';
import { useLocation, useNavigate, Routes, Route } from 'react-router-dom';
import CSVReader from './components/CSVReader';
import Navbar from './components/Navbar';
import AdminPanel from './components/Admin/AdminPanel';
import SelectedColumnsPage from './components/SelectedColumnsPage';
import CreditScorePage from './components/CreditScorePage';
import './App.css';
import './components/Admin/AdminPanel.css';
import { AnalysisRecord } from './types/analysis';
import { buildBinningState, buildTypeLookup } from './utils/binning';

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
  const [datasetPath, setDatasetPath] = useState<string>('');
  const [restoring, setRestoring] = useState<boolean>(false);
  const [expectedColumnsForRecord, setExpectedColumnsForRecord] = useState<string[] | undefined>(undefined);

  // Records (moved from AdminPanel into main page)
  const [records, setRecords] = useState<AnalysisRecord[]>([]);
  const [recordsLoading, setRecordsLoading] = useState<boolean>(false);
  const [activeRecordId, setActiveRecordId] = useState<number | undefined>(undefined);
  const [recordNames, setRecordNames] = useState<Record<number, string>>({});
  const [editingRecordId, setEditingRecordId] = useState<number | null>(null);
  const [editingRecordName, setEditingRecordName] = useState<string>('');

  // Fetch existing analysis records on mount (with auth headers)
  useEffect(() => {
    const fetchRecords = async () => {
      setRecordsLoading(true);
      try {
        const token = localStorage.getItem('credit_scoring_auth_token');
        const headers: HeadersInit = token ? { 'Authorization': `Bearer ${token}` } : {};
        const res = await fetch('http://localhost:5000/api/records', { headers });
        const data = await res.json();
        const list: AnalysisRecord[] = Array.isArray(data) ? data : [];
        setRecords(list);
        if (list.length > 0) {
          setActiveRecordId((prev) => prev ?? list[0].id);
        }
      } catch (err) {
        console.error('Failed to fetch records:', err);
      } finally {
        setRecordsLoading(false);
      }
    };
    fetchRecords();
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
      const token = localStorage.getItem('credit_scoring_auth_token');
      const headers: HeadersInit = { 'Content-Type': 'application/json' };
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }
      const resp = await fetch('http://localhost:5000/api/upsert-single-record', {
        method: 'POST',
        headers,
        body: JSON.stringify({
          dataset_path: datasetPath,
          discrete_columns: discreteColumns,
          continuous_columns: continuousColumns,
          selected_columns: selectedForUnivariate,
          record_id: activeRecordId,
          target_variable: targetVariable,
          univariate_results: '',
          finebin_results: '',
          crosstab_results: ''
        })
      });
      const saved = await resp.json().catch(() => ({} as any));
      const newRecordId = saved?.id;
      if (newRecordId) {
        setActiveRecordId(newRecordId);
      }

      navigate('/selected-columns', {
        state: {
          selectedColumns: selectedForUnivariate,
          discreteColumns,
          continuousColumns,
          targetVariable,
          recordId: newRecordId || undefined,
          datasetPath: datasetPath,
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
          targetVariable,
          datasetPath: datasetPath
        }
      });
    }
  };

  const handleCSVUploaded = (headers: string[], _rows?: any[], uploadedPath?: string, datasetId?: number) => {
    // CRITICAL: Clear ALL state when starting a new analysis
    // This prevents old data from previous records mixing into new records
    console.log('[App] 🧹 Clearing all state for new CSV upload');
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
    setSelectedForUnivariate([]);
    // CRITICAL: Clear activeRecordId when starting fresh (will be set after record is created)
    // Only set it if datasetId is explicitly provided (from existing record)
    if (datasetId) {
      setActiveRecordId(datasetId);
      console.log('[App] ✅ Using existing recordId:', datasetId);
    } else {
      setActiveRecordId(undefined);
      console.log('[App] ✅ Cleared activeRecordId for new analysis');
    }
    navigate('/selected-columns', {
      state: {
        columns: headers,
        datasetPath: uploadedPath,
        recordId: datasetId, // Will be undefined for new analysis
      }
    });
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
            target_variable: targetVariable,
            record_id: activeRecordId
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
        body: JSON.stringify({
          column: col,
          record_id: activeRecordId,
          dataset_path: datasetPath || undefined,
        }),
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
    if (!targetVariable || !activeRecordId) return;
    (async () => {
      try {
        // Persist target variable
        await fetch('http://localhost:5000/api/upsert-single-record', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            dataset_path: datasetPath,
            discrete_columns: discreteColumns,
            continuous_columns: continuousColumns,
            selected_columns: selectedForUnivariate,
            target_variable: targetVariable,
            record_id: activeRecordId
          })
        });
        console.log('[TARGET] ✅ Target variable persisted to backend');
      } catch (err) {
        console.error('Failed to persist target variable:', err);
      }
    })();
  }, [targetVariable, activeRecordId]);

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
      console.log(`[App] 🔄 Loading record ${id}`);
      
      // CRITICAL: Clear all state before loading new record to ensure complete isolation
      console.log('[App] 🧹 Clearing all state before loading record');
      setColumns([]);
      setDiscreteColumns([]);
      setContinuousColumns([]);
      setTargetVariable('');
      setUnivariateResults({});
      setFineBinResults({});
      setCrossTabResults({});
      setSelectedForUnivariate([]);
      setActiveRecordId(id);
      
      // Fetch complete record
      const recResp = await fetch(`http://localhost:5000/api/record/${id}`);
      const data: AnalysisRecord = await recResp.json();
      console.log(`[App] ✅ Loaded record ${id}: target_variable="${data.target_variable || ''}"`);

      // Infer columns from stored column arrays (much faster than loading entire CSV)
      const inferred = new Set<string>();
      const addField = (field: unknown) => {
        if (!Array.isArray(field)) return;
        field.forEach((c: any) => {
          if (c !== undefined && c !== null && String(c).trim()) {
            inferred.add(String(c).trim());
          }
        });
      };

      addField((data as any).discrete_columns ?? []);
      addField((data as any).continuous_columns ?? []);
      addField((data as any).selected_columns ?? []);
      const loadedColumns = Array.from(inferred);

      // Update state
      setColumns(loadedColumns);
      const discreteArr: string[] = Array.isArray((data as any).discrete_columns)
        ? (data as any).discrete_columns
        : [];

      const continuousArr: string[] = Array.isArray((data as any).continuous_columns)
        ? (data as any).continuous_columns
        : [];

      const selectedArr: string[] = Array.isArray((data as any).selected_columns)
        ? (data as any).selected_columns
        : [];

      const expected = loadedColumns.length ? loadedColumns : Array.from(new Set([...discreteArr, ...continuousArr, ...selectedArr]));
  setExpectedColumnsForRecord(expected);
      setDiscreteColumns(discreteArr);
      setContinuousColumns(continuousArr);
      setSelectedForUnivariate(selectedArr);
      setTargetVariable(data.target_variable || '');

      const typeLookup = buildTypeLookup(discreteArr, continuousArr);
      const normalizedBinning = buildBinningState(data.binning_data, typeLookup);
      setUnivariateResults(normalizedBinning.univariate);
      setFineBinResults(normalizedBinning.fine);
      setCrossTabResults(normalizedBinning.coarse);
      setCurrentPage(1);

      // Navigate passing full state to cover edge cases where local effect didn't fire yet
      const modelReadyColumns = Array.isArray((data as any).dashboard_selected_columns)
        ? (data as any).dashboard_selected_columns
        : [];
      const finalSelectedColumns = Array.isArray((data as any).final_selected_columns)
        ? (data as any).final_selected_columns
        : [];

      navigate('/selected-columns', {
        state: {
          columns: loadedColumns,
          selectedColumns: selectedArr,
          discreteColumns: discreteArr,
          continuousColumns: continuousArr,
          targetVariable: data.target_variable || '',
          recordId: id,
          datasetPath: data.dataset_path || '',
          univariateResults: normalizedBinning.univariate,
          fineBinResults: normalizedBinning.fine,
          crossTabResults: normalizedBinning.coarse,
          woeIvResults: normalizedBinning.woe,
          binningState: normalizedBinning,
          modelReadyColumns,
          finalSelectedColumns
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
          setRecordNames(prev => {
            const next = { ...prev };
            delete next[id];
            return next;
          });
        }
      })
      .catch(() => {});
  };

  const handleRecordNameEdit = (id: number, currentName: string) => {
    setEditingRecordId(id);
    setEditingRecordName(currentName || '');
  };

  const handleRecordNameSave = (id: number) => {
    setRecordNames(prev => ({ ...prev, [id]: editingRecordName }));
    setEditingRecordId(null);
    setEditingRecordName('');
  };

  const handleRecordNameCancel = () => {
    setEditingRecordId(null);
    setEditingRecordName('');
  };

  const getRecordName = (id: number): string => {
    return recordNames[id] || `Record ${id}`;
  };


  // Check if score card is generated (dummy for now - always return true for records with id > 0)
  const hasScoreCard = (recordId: number): boolean => {
    return recordId > 0; // Dummy logic
  };

  return (
    <Routes>
      <Route
        path="/"
        element={
          <div className="main-page-wrapper">
            {/* Optimized Animated Graph Background */}
            <div className="animated-graph-background">
              <svg className="graph-svg" viewBox="0 0 1200 600" preserveAspectRatio="xMidYMid slice">
                <defs>
                  <linearGradient id="lineGradient" x1="0%" y1="0%" x2="100%" y2="0%">
                    <stop offset="0%" stopColor="rgba(46, 160, 67, 0.5)" />
                    <stop offset="50%" stopColor="rgba(46, 160, 67, 0.7)" />
                    <stop offset="100%" stopColor="rgba(46, 160, 67, 0.5)" />
                  </linearGradient>
                </defs>
                
                {/* Simplified grid lines - reduced from 32 to 12 */}
                <g className="grid-lines">
                  {[0, 2, 4, 6, 8, 10].map((i) => (
                    <line
                      key={`h-${i}`}
                      x1="0"
                      y1={i * 60}
                      x2="1200"
                      y2={i * 60}
                      stroke="rgba(46, 160, 67, 0.2)"
                      strokeWidth="1"
                    />
                  ))}
                  {[0, 4, 8, 12, 16, 20].map((i) => (
                    <line
                      key={`v-${i}`}
                      x1={i * 60}
                      y1="0"
                      x2={i * 60}
                      y2="600"
                      stroke="rgba(46, 160, 67, 0.2)"
                      strokeWidth="1"
                    />
                  ))}
                </g>
                
                {/* Reduced to 2 graph lines instead of 4 */}
                <path
                  className="graph-line graph-line-1"
                  d="M 0,400 Q 300,350 600,300 T 1200,200"
                  fill="none"
                  stroke="url(#lineGradient)"
                  strokeWidth="3"
                />
                
                <path
                  className="graph-line graph-line-2"
                  d="M 0,500 Q 400,450 800,400 T 1200,350"
                  fill="none"
                  stroke="url(#lineGradient)"
                  strokeWidth="3"
                />
                
                {/* Reduced data points from 6 to 3 */}
                <g className="data-points">
                  {[300, 600, 900].map((x, i) => (
                    <circle
                      key={`point-${i}`}
                      className="data-point"
                      cx={x}
                      cy={300 + Math.sin(i) * 50}
                      r="3"
                      fill="rgba(46, 160, 67, 0.6)"
                    />
                  ))}
                </g>
              </svg>
            </div>
            
            <Navbar />
            {/* Full-width Info Section with Process Diagram */}
            <div className="info-hero-section">
              <h1 className="info-hero-title">Automated Credit Scoring System</h1>
              <p className="info-hero-subtitle">
                Build and deploy credit scoring models using advanced machine learning techniques powered by Generative AI
              </p>
              <p className="info-hero-description">
                Upload your dataset, select features, perform statistical analysis, and generate scorecards for credit risk assessment.
              </p>
              
              {/* Animated Process Diagram */}
              <div className="process-diagram">
                <div className="process-step" style={{ animationDelay: '0s' }}>
                  <div className="process-step-icon">
                    <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                      <polyline points="7 10 12 15 17 10"></polyline>
                      <line x1="12" y1="15" x2="12" y2="3"></line>
                    </svg>
                  </div>
                  <div className="process-step-label">Upload Dataset</div>
                </div>
                <div className="process-arrow">→</div>
                <div className="process-step" style={{ animationDelay: '0.1s' }}>
                  <div className="process-step-icon">
                    <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"></path>
                    </svg>
                  </div>
                  <div className="process-step-label">Classification</div>
                </div>
                <div className="process-arrow">→</div>
                <div className="process-step" style={{ animationDelay: '0.2s' }}>
                  <div className="process-step-icon">
                    <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                      <polyline points="14 2 14 8 20 8"></polyline>
                      <line x1="16" y1="13" x2="8" y2="13"></line>
                      <line x1="16" y1="17" x2="8" y2="17"></line>
                    </svg>
                  </div>
                  <div className="process-step-label">Data Preprocessing</div>
                </div>
                <div className="process-arrow">→</div>
                <div className="process-step" style={{ animationDelay: '0.3s' }}>
                  <div className="process-step-icon">
                    <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <line x1="18" y1="20" x2="18" y2="10"></line>
                      <line x1="12" y1="20" x2="12" y2="4"></line>
                      <line x1="6" y1="20" x2="6" y2="14"></line>
                    </svg>
                  </div>
                  <div className="process-step-label">Coarse Binning</div>
                </div>
                <div className="process-arrow">→</div>
                <div className="process-step" style={{ animationDelay: '0.4s' }}>
                  <div className="process-step-icon">
                    <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <line x1="18" y1="20" x2="18" y2="10"></line>
                      <line x1="12" y1="20" x2="12" y2="4"></line>
                      <line x1="6" y1="20" x2="6" y2="14"></line>
                    </svg>
                  </div>
                  <div className="process-step-label">Fine Binning</div>
                </div>
                <div className="process-arrow">→</div>
                <div className="process-step" style={{ animationDelay: '0.5s' }}>
                  <div className="process-step-icon">
                    <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline>
                    </svg>
                  </div>
                  <div className="process-step-label">Monotonicity & Multicolinearity</div>
                </div>
                <div className="process-arrow">→</div>
                <div className="process-step" style={{ animationDelay: '0.6s' }}>
                  <div className="process-step-icon">
                    <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M12 2L2 7l10 5 10-5-10-5z"></path>
                      <path d="M2 17l10 5 10-5"></path>
                      <path d="M2 12l10 5 10-5"></path>
                    </svg>
                  </div>
                  <div className="process-step-label">ML Training</div>
                </div>
                <div className="process-arrow">→</div>
                <div className="process-step" style={{ animationDelay: '0.7s' }}>
                  <div className="process-step-icon">
                    <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline>
                    </svg>
                  </div>
                  <div className="process-step-label">Training Analysis</div>
                </div>
                <div className="process-arrow">→</div>
                <div className="process-step" style={{ animationDelay: '0.8s' }}>
                  <div className="process-step-icon">
                    <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                      <polyline points="14 2 14 8 20 8"></polyline>
                      <line x1="16" y1="13" x2="8" y2="13"></line>
                      <line x1="16" y1="17" x2="8" y2="17"></line>
                      <polyline points="10 9 9 9 8 9"></polyline>
                    </svg>
                  </div>
                  <div className="process-step-label">Scorecard Generation</div>
                </div>
                <div className="process-arrow">→</div>
                <div className="process-step" style={{ animationDelay: '0.9s' }}>
                  <div className="process-step-icon">
                    <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M9 11l3 3L22 4"></path>
                      <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"></path>
                    </svg>
                  </div>
                  <div className="process-step-label">Credit Risk Check</div>
                </div>
              </div>
            </div>

            <div className="main-page-container">
              {/* Left Column: Upload and Credit History */}
              <div className="main-page-left">
                {/* Upload Section */}
                <div className="upload-section">
                  <CSVReader onCSVUploaded={handleCSVUploaded} />
                </div>
              </div>

              {/* Right Column: Records */}
              <div className="main-page-right">
                {/* Developed Score Card Records */}
                <div className="records-section">
                  <h2 className="records-section-title">
                    Developed Score Card
                  </h2>
                  {recordsLoading ? (
                    <div className="records-loading">Loading records...</div>
                  ) : records.length === 0 ? (
                    <div className="records-empty">No score cards developed yet.</div>
                  ) : (
                    <div className="records-list">
                      {records.map(rec => (
                        <div key={rec.id} className="record-card">
                          <div className="record-card-header">
                            {editingRecordId === rec.id ? (
                              <div className="record-name-edit">
                                <input
                                  type="text"
                                  value={editingRecordName}
                                  onChange={(e) => setEditingRecordName(e.target.value)}
                                  className="record-name-input"
                                  placeholder="Enter record name"
                                  autoFocus
                                />
                                <button
                                  className="record-name-save-btn"
                                  onClick={() => handleRecordNameSave(rec.id)}
                                  title="Save"
                                >
                                  Save
                                </button>
                                <button
                                  className="record-name-cancel-btn"
                                  onClick={handleRecordNameCancel}
                                  title="Cancel"
                                >
                                  Cancel
                                </button>
                              </div>
                            ) : (
                              <div className="record-name-display">
                                <span className="record-name">{getRecordName(rec.id)}</span>
                                <button
                                  className="record-name-edit-btn"
                                  onClick={() => handleRecordNameEdit(rec.id, recordNames[rec.id] || '')}
                                  title="Edit name"
                                >
                                  Edit
                                </button>
                              </div>
                            )}
                          </div>
                          <div className="record-card-body">
                            <div className="record-info-item">
                              <span className="record-info-label">ID:</span>
                              <span className="record-info-value">{rec.id}</span>
                            </div>
                            <div className="record-info-item">
                              <span className="record-info-label">Dataset:</span>
                              <span className="record-info-value" title={rec.dataset_path}>
                                {rec.dataset_path.split('/').pop() || rec.dataset_path}
                              </span>
                            </div>
                            <div className="record-info-item">
                              <span className="record-info-label">Columns:</span>
                              <span className="record-info-value">{rec.selected_columns.length}</span>
                            </div>
                            <div className="record-info-item">
                              <span className="record-info-label">Created:</span>
                              <span className="record-info-value">{new Date(rec.created_at).toLocaleDateString()}</span>
                            </div>
                          </div>
                          <div className="record-card-actions">
                            <button
                              className="record-action-btn record-action-view"
                              onClick={() => handleRecordView(rec.id)}
                            >
                              View
                            </button>
                            <button
                              className="record-action-btn record-action-check"
                              onClick={() => {
                                navigate('/credit-score', {
                                  state: {
                                    recordId: rec.id
                                  }
                                });
                              }}
                              disabled={!hasScoreCard(rec.id)}
                              title={hasScoreCard(rec.id) ? 'Check credit score' : 'Score card not generated yet'}
                            >
                              Check credit score
                            </button>
                            <button
                              className="record-action-btn record-action-delete"
                              onClick={() => handleRecordDelete(rec.id)}
                            >
                              Delete
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        }
      />
      <Route path="/admin" element={<AdminPanel />} />
      <Route path="/selected-columns" element={<SelectedColumnsPage />} />
      <Route path="/credit-score" element={<CreditScorePage />} />
    </Routes>
  );
}

export default App;
