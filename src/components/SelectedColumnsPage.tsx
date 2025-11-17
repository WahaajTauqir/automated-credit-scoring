import { useLocation } from 'react-router-dom';
import { useEffect, useState, useRef, useCallback } from 'react';
import LogisticRegressionResults from './LogisticRegressionResults';
import Navbar from './Navbar';
import RandomForestResults from './RandomForestResults';
import XGBoostResults from './XGBoostResults';
import { DiscreteValuesDropdown } from './DiscreteValues';
import ColumnPanels from './ColumnsPanel';
import PreprocessingDetails from './PreprocessingDetails';
// import WoeIvResults from './WoeIvResults';
import './SelectedColumnsPage.css';
import { buildBinningState, buildTypeLookup, normalizeBinArray, prepareBinMetricsPayload } from '../utils/binning';
import { NormalizedBin, NormalizedBinningState } from '../types/analysis';

const normalizeDisplayLabel = (value: string) => value.replace(/\s+/g, ' ').trim();

const getBinLabelValue = (bin: NormalizedBin | undefined, fallbackIndex = 0) => {
  if (!bin) return `Bin_${fallbackIndex + 1}`;
  const label = bin.Bin ?? bin.bin_label;
  return label ? String(label) : `Bin_${fallbackIndex + 1}`;
};

const getRangeText = (bin: NormalizedBin | undefined) =>
  typeof bin?.Range === 'string' ? bin.Range : '';

const getNumericOrderFromLabel = (label: string) => {
  const match = label.match(/\d+/);
  return match ? parseInt(match[0], 10) : null;
};

const getMinFromBin = (bin: NormalizedBin | undefined): number | null =>
  typeof bin?.Min === 'number' ? bin.Min : null;

const getMaxFromBin = (bin: NormalizedBin | undefined): number | null =>
  typeof bin?.Max === 'number' ? bin.Max : null;
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  ResponsiveContainer,
  LineChart,
  Line,
  Legend,
} from 'recharts';
const SelectedColumnsPage = () => {
  const { state } = useLocation();
  const {
    selectedColumns: navSelectedColumns,
    discreteColumns: navDiscreteColumns,
    continuousColumns: navContinuousColumns,
    targetVariable: navTargetVariable,
    recordId: initialRecordId,
    datasetPath: navDatasetPath,
    columns: navColumns,
    modelReadyColumns: navModelReadyColumns,
    finalSelectedColumns: navFinalSelectedColumns,
  } = state || {};
  // State declarations
  const [columns, setColumns] = useState<string[]>(navColumns || []);
  const [selectedColumns, setSelectedColumns] = useState<string[]>(navSelectedColumns || []);
  const [discreteColumns, setDiscreteColumns] = useState<string[]>(navDiscreteColumns || []);
  const [continuousColumns, setContinuousColumns] = useState<string[]>(navContinuousColumns || []);
  const [targetVariable, setTargetVariable] = useState<string>(navTargetVariable || '');
  const [activeColumn, setActiveColumn] = useState<string>('');
  const [currentStep, setCurrentStep] = useState(0); // Start at step 0 (Column Selection)
  const [currentPage, setCurrentPage] = useState(1);
  const columnsPerPage = 7;
  const totalPages = Math.ceil(columns.length / columnsPerPage);
  const paginatedColumns = columns.slice(
    (currentPage - 1) * columnsPerPage,
    currentPage * columnsPerPage
  );
  const [targetCounts, setTargetCounts] = useState<Record<string, number>>({});
  const [selectedForUnivariate, setSelectedForUnivariate] = useState<string[]>([]);
  const [univariateResults, setUnivariateResults] = useState<Record<string, any>>({});
  const [coarseBinResults, setCoarseBinResults] = useState<Record<string, NormalizedBin[]>>({});
  const [fineBinResults, setFineBinResults] = useState<Record<string, NormalizedBin[]>>({});
  const [selectedFineBins, setSelectedFineBins] = useState<Record<string, string[]>>({});
  const [binMergeHistory, setBinMergeHistory] = useState<Record<string, Record<string, any[]>>>({});
  const [recordId, setRecordId] = useState<number | undefined>(initialRecordId);
  const [datasetPath, setDatasetPath] = useState<string>(navDatasetPath || '');
  const [woeIvResults, setWoeIvResults] = useState<Record<string, { iv?: number; stats: NormalizedBin[] }>>({});
  const woeIvResultsRef = useRef<Record<string, { iv?: number; stats: NormalizedBin[] }>>({});
  const [woeReadyColumns, setWoeReadyColumns] = useState<Set<string>>(new Set());
  const [selectedForModeling, setSelectedForModeling] = useState<string[]>(navModelReadyColumns || []); // For Column Selection & Binning (model_ready)
  const [selectedForFinalModeling, setSelectedForFinalModeling] = useState<string[]>(navFinalSelectedColumns || []); // For Model Training (final_selected)
  const [notification, setNotification] = useState<string | null>(null);
  const [scoreCardData, setScoreCardData] = useState<any>(null);
  const [testScoreLoading, setTestScoreLoading] = useState(false);
  const [testScoreResults, setTestScoreResults] = useState<any[] | null>(null);
  const [testScoreKS, setTestScoreKS] = useState<number | null>(null);
  const [generatingScoreCard, setGeneratingScoreCard] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedModel, setSelectedModel] = useState<string>('logistic');
  const [selectedModelForScorecard, setSelectedModelForScorecard] = useState<string>('logistic');
  const [logisticResults, setLogisticResults] = useState<any>(null);
  const [randomForestResults, setRandomForestResults] = useState<any>(null);
  const [xgboostResults, setXgboostResults] = useState<any>(null);
  const [binningMode, setBinningMode] = useState<'manual' | 'auto'>('manual');
  const isLoadingAutoBinning = useRef(false);
  const [loadingColumns, setLoadingColumns] = useState<Set<string>>(new Set());
  const loadedColumnsRef = useRef<Set<string>>(new Set());
  const [autoBinningModeLoading, setAutoBinningModeLoading] = useState(false);
  const [autoBinningModeProgress, setAutoBinningModeProgress] = useState<string>('');
  const [autoBinningModePercentage, setAutoBinningModePercentage] = useState<number>(0);
  const [fullAutoMonotonicLoading, setFullAutoMonotonicLoading] = useState(false);
  const [fullAutoMonotonicProgress, setFullAutoMonotonicProgress] = useState('');
  const [fullAutoMonotonicPercentage, setFullAutoMonotonicPercentage] = useState(0);
  const [fullAutoMonotonicCurrent, setFullAutoMonotonicCurrent] = useState('');
  const FULL_AUTO_CONCURRENCY = 4;
  const [showPreprocessing, setShowPreprocessing] = useState(false);
  const [preprocessedDatasetId, setPreprocessedDatasetId] = useState<number | undefined>();
  const updateLocalWoeState = useCallback(
    (col: string, payload?: { iv?: number; stats?: any[]; bins?: any[] }) => {
      if (!payload) {
        return false;
      }
      const normalized = normalizeBinArray(payload.stats || payload.bins || []);
      if (normalized.length === 0 && typeof payload.iv !== 'number') {
        return false;
      }
      setWoeIvResults((prev) => {
        const next = {
          ...prev,
          [col]: {
            iv: typeof payload.iv === 'number' ? payload.iv : prev[col]?.iv,
            stats: normalized.length > 0 ? normalized : prev[col]?.stats || [],
          },
        };
        woeIvResultsRef.current = next;
        return next;
      });
      setWoeReadyColumns((prev) => {
        const next = new Set(prev);
        next.add(col);
        return next;
      });
      return true;
    },
    [setWoeIvResults, setWoeReadyColumns]
  );


  // Add to your existing state declarations
  const [binScoringMetrics, setBinScoringMetrics] = useState<Record<string, any[]>>({});
  const [binScoringTotals, setBinScoringTotals] = useState<Record<string, { total_good: number; total_bad: number; total_zero_one_ratio?: number }>>({});
  // Removed UI sorting controls per request; keep search only
  // Helper to format IV class if needed later
  // (kept here for possible future IV badge usage)
  // Filtered and sorted columns
  // Filter columns by search term and sort alphabetically by name
  // Add these state setters to your component
  const handleLogisticResults = (results: any) => {
    setLogisticResults(results);
  };

  const handleRandomForestResults = (results: any) => {
    setRandomForestResults(results);
  };

  const handleXGBoostResults = (results: any) => {
    setXgboostResults(results);
  };

  const syncBinningFromState = useCallback(
    (nextState?: Partial<NormalizedBinningState>) => {
      if (!nextState) {
        return;
      }

      if (nextState.univariate && Object.keys(nextState.univariate).length > 0) {
        setUnivariateResults((prev) => ({ ...prev, ...nextState.univariate! }));
      }

      if (nextState.coarse && Object.keys(nextState.coarse).length > 0) {
        setCoarseBinResults((prev) => ({ ...prev, ...nextState.coarse! }));
      }

      if (nextState.fine && Object.keys(nextState.fine).length > 0) {
        setFineBinResults((prev) => ({ ...prev, ...nextState.fine! }));
      }

      if (nextState.merged && Object.keys(nextState.merged).length > 0) {
        setBinMergeHistory((prev) => {
          const merged = nextState.merged!;
          const updated = { ...prev };
          Object.entries(merged).forEach(([col, value]) => {
            if (value && typeof value === 'object' && !Array.isArray(value)) {
              updated[col] = value as Record<string, any[]>;
            }
          });
          return updated;
        });
      }

      if (nextState.woe && Object.keys(nextState.woe).length > 0) {
        setWoeIvResults((prev) => {
          const woe = nextState.woe!;
          const updated = { ...prev };
          Object.entries(woe).forEach(([col, entry]) => {
            if (entry && typeof entry === 'object' && 'stats' in entry) {
              updated[col] = {
                iv: typeof entry.iv === 'number' ? entry.iv : undefined,
                stats: entry.stats || [],
              };
            }
          });
          return updated;
        });
        setWoeReadyColumns((prev) => {
          const updated = new Set(prev);
          Object.keys(nextState.woe!).forEach((col) => updated.add(col));
          return updated;
        });
      }
    },
    []
  );

  // Update your model components to pass these handlers
  const filteredColumns = selectedColumns
    .filter(col => col.toLowerCase().includes(searchTerm.toLowerCase()))
    .sort((a, b) => a.localeCompare(b));
  // Recommend functionality removed (UI buttons removed per request)
  // Initialize component state from navigation state
  useEffect(() => {
    if (!state) return;

    console.log('🔄 SelectedColumnsPage: Initializing from navigation state', {
      hasState: !!state,
      selectedColumns: navSelectedColumns?.length,
      discreteColumns: navDiscreteColumns?.length,
      continuousColumns: navContinuousColumns?.length,
      recordId: initialRecordId,
      datasetPath: navDatasetPath
    });

    const anyUnivariate = (state as any).univariateResults;
    const anyFine = (state as any).fineBinResults;
    const anyCross = (state as any).crossTabResults;
    const anyWoe = (state as any).woeIvResults;
    const incomingBinningState = (state as any).binningState as Partial<NormalizedBinningState> | undefined;

    if (anyUnivariate) {
      console.log('✅ Setting univariate results:', Object.keys(anyUnivariate).length, 'columns');
      const normalized: Record<string, any> = {};
      Object.entries(anyUnivariate).forEach(([col, entry]: [string, any]) => {
        normalized[col] = {
          ...entry,
          stats: normalizeBinArray(entry?.stats || entry || []),
        };
      });
      setUnivariateResults((prev) => ({ ...prev, ...normalized }));
    }
    if (anyFine) {
      console.log('✅ Setting fine bin results:', Object.keys(anyFine).length, 'columns');
      const normalizedFine: Record<string, NormalizedBin[]> = {};
      Object.entries(anyFine).forEach(([col, bins]: [string, any]) => {
        normalizedFine[col] = normalizeBinArray(bins);
      });
      setFineBinResults((prev) => ({ ...prev, ...normalizedFine }));
    }
    if (anyCross) {
      console.log('✅ Setting coarse bin results:', Object.keys(anyCross).length, 'columns');
      const normalizedCoarse: Record<string, NormalizedBin[]> = {};
      Object.entries(anyCross).forEach(([col, bins]: [string, any]) => {
        normalizedCoarse[col] = normalizeBinArray(bins?.stats || bins);
      });
      setCoarseBinResults((prev) => ({ ...prev, ...normalizedCoarse }));
    }
    if (anyWoe) {
      const woeKeys = Object.keys(anyWoe);
      console.log('✅ Setting WOE/IV results:', woeKeys.length, 'columns');
      const normalizedWoe: Record<string, { iv?: number; stats: NormalizedBin[] }> = {};
      woeKeys.forEach((col) => {
        const entry = anyWoe[col];
        normalizedWoe[col] = {
          ...entry,
          stats: normalizeBinArray(entry?.stats || entry?.bins || []),
        };
      });
      setWoeIvResults((prev) => ({ ...prev, ...normalizedWoe }));
      setWoeReadyColumns((prev) => {
        const next = new Set(prev);
        woeKeys.forEach((col) => next.add(col));
        return next;
      });
    }
    if (navSelectedColumns) {
      console.log('✅ Setting selected columns:', navSelectedColumns.length);
      setSelectedColumns(navSelectedColumns);
      // Also set selectedForUnivariate for Feature Selection checkboxes
      setSelectedForUnivariate(navSelectedColumns);
    }
    if (navDiscreteColumns) {
      console.log('✅ Setting discrete columns:', navDiscreteColumns.length);
      setDiscreteColumns(navDiscreteColumns);
    }
    if (navContinuousColumns) {
      console.log('✅ Setting continuous columns:', navContinuousColumns.length);
      setContinuousColumns(navContinuousColumns);
    }
    if (navTargetVariable) {
      console.log('✅ Setting target variable:', navTargetVariable);
      setTargetVariable(navTargetVariable);
    }
    if ((state as any).recordId) {
      console.log('✅ Setting record ID:', (state as any).recordId);
      setRecordId((state as any).recordId);
    }
    if ((state as any).datasetPath) {
      console.log('✅ Setting dataset path:', (state as any).datasetPath);
      setDatasetPath((state as any).datasetPath);
    }
    if (incomingBinningState) {
      syncBinningFromState(incomingBinningState);
    }
  }, [state, navSelectedColumns, navDiscreteColumns, navContinuousColumns, navTargetVariable, initialRecordId, navDatasetPath, syncBinningFromState]);
  // Sync WOE/IV states and selectedForModeling when selectedColumns changes
  useEffect(() => {
    const currentWoeKeys = Object.keys(woeIvResults);
    const columnsToRemove = currentWoeKeys.filter((col) => !selectedColumns.includes(col));
    if (columnsToRemove.length > 0) {
      setWoeIvResults((prev) => {
        const newResults = { ...prev };
        columnsToRemove.forEach((col) => delete newResults[col]);
        return newResults;
      });
      setWoeReadyColumns((prev) => {
        const newSet = new Set(prev);
        columnsToRemove.forEach((col) => newSet.delete(col));
        return newSet;
      });
      setSelectedForModeling((prev) => prev.filter((col) => selectedColumns.includes(col)));
      showNotification(`WOE/IV data cleaned for dropped columns: ${columnsToRemove.join(', ')}`);
    }
  }, [selectedColumns, woeIvResults, woeReadyColumns]);
  // Column Selection functions (from ColumnSelectionPage)
  const handleTypeChange = (column: string, type: string) => {
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

    // Persist change to backend (non-blocking)
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
            record_id: recordId
          })
        });
      } catch (err) {
        console.error('Failed to persist type change:', err);
      }
    })();
  };

  const assignRemainingToContinuous = () => {
    const selectedDiscrete = new Set(discreteColumns);
    const remaining = columns.filter(col => !selectedDiscrete.has(col) && col !== targetVariable);
    setContinuousColumns(remaining);

    // Persist to backend
    (async () => {
      try {
        await fetch('http://localhost:5000/api/upsert-single-record', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            dataset_path: datasetPath,
            discrete_columns: discreteColumns,
            continuous_columns: remaining,
            selected_columns: selectedForUnivariate,
            target_variable: targetVariable,
            record_id: recordId
          })
        });
      } catch (err) {
        console.error('Failed to persist remaining columns:', err);
      }
    })();
  };

  const toggleSelectedForUnivariate = (col: string) => {
    setSelectedForUnivariate(prev =>
      prev.includes(col) ? prev.filter(c => c !== col) : [...prev, col]
    );
  };

  const toggleSelectAllDiscrete = (selectAll?: boolean) => {
    setSelectedForUnivariate(prev => {
      const currentSet = new Set(prev);
      if (selectAll === false) {
        discreteColumns.forEach(c => currentSet.delete(c));
        return Array.from(currentSet);
      }
      if (selectAll === true) {
        discreteColumns.forEach(c => currentSet.add(c));
        return Array.from(currentSet);
      }
      const allSelected = discreteColumns.every(c => currentSet.has(c));
      if (allSelected) {
        discreteColumns.forEach(c => currentSet.delete(c));
      } else {
        discreteColumns.forEach(c => currentSet.add(c));
      }
      return Array.from(currentSet);
    });
  };

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

  const handleNextPage = () => {
    if (currentPage < totalPages) {
      setCurrentPage(prev => prev + 1);
    }
  };

  const handlePrevPage = () => {
    if (currentPage > 1) {
      setCurrentPage(prev => prev - 1);
    }
  };

  const handleProceedToFeatureSelection = async () => {
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
          record_id: recordId
        }),
      });
      const data = await resp.json();
      if (!data.error) {
        if (data.id) setRecordId(data.id);
        setSelectedColumns(selectedForUnivariate);
        setCurrentStep(2); // Move to Binning step (Step 2)
      } else {
        alert(`Error: ${data.error}`);
      }
    } catch (error) {
      alert(`Error: ${error}`);
    }
  };

  // Fetch target counts
  const fetchTargetCounts = async (col: string) => {
    try {
      const res = await fetch('http://localhost:5000/api/target-distribution', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ column: col, record_id: recordId }),
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

  // Persist target variable to backend when user selects it
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
            target_variable: targetVariable,
            record_id: recordId
          })
        });
      } catch (err) {
        console.error('Failed to persist target variable:', err);
      }
    })();
  }, [targetVariable]);

  // Utility functions

  // Calculate metrics for all bins of a column
  const handleTestScoreCard = async (modelType: string = selectedModelForScorecard) => {
    setTestScoreLoading(true);
    setTestScoreResults(null);
    try {
      // Get the appropriate model results based on the selected model
      let modelResults: any = null;

      switch (modelType) {
        case 'logistic':
          modelResults = logisticResults;
          break;
        case 'random_forest':
          modelResults = randomForestResults;
          break;
        case 'xgboost':
          modelResults = xgboostResults;
          break;
        default:
          modelResults = logisticResults;
      }


      if (!modelResults) {
        alert(`No results available for ${modelType}. Please run the model first.`);
        setTestScoreLoading(false);
        return;
      }

      const response = await fetch('http://localhost:5000/api/apply-scorecard', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          selected_variables: selectedForFinalModeling.length > 0 ? selectedForFinalModeling : selectedForModeling,
          target: targetVariable,
          woe_transformed_data: Object.fromEntries(
            Object.entries(woeIvResults).map(([key, value]) => [key, value.stats || []])
          ),
          model_results: modelResults,
          model_type: modelType,
          record_id: recordId
        })
      });

      const data = await response.json();
      if (data.success && data.results) {
        setTestScoreResults(data.results);
        setTestScoreKS(typeof data.ks_stat === 'number' ? data.ks_stat : null);
        showNotification(`Score card tested using ${modelType} model`);
      } else {
        alert('Error applying score card: ' + (data.error || 'Unknown error'));
      }
    } catch (err) {
      alert('Error applying score card: ' + err);
    } finally {
      setTestScoreLoading(false);
    }
  };
  const calculateAllBinMetrics = async (columnName: string, bins: NormalizedBin[]) => {
    if (!bins || bins.length === 0) {
      return null;
    }
    try {
      const response = await fetch('http://localhost:5000/api/calculate-bin-metrics', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ bins: prepareBinMetricsPayload(bins) })
      });

      if (!response.ok) {
        return null;
      }

      const data = await response.json();

      if (data?.success) {
        setBinScoringMetrics(prev => ({
          ...prev,
          [columnName]: data.bin_metrics
        }));
        setBinScoringTotals(prev => ({
          ...prev,
          [columnName]: {
            total_good: Number(data.total_good ?? 0),
            total_bad: Number(data.total_bad ?? 0),
            total_zero_one_ratio: data.total_zero_one_ratio
          }
        }));
        return data.bin_metrics;
      }
      return null;
    } catch {

      return null;
    }
  };

  // Call this when bin data changes
  // Add this useEffect to debug bin matching
  useEffect(() => {
    if (activeColumn && binScoringMetrics[activeColumn] && fineBinResults[activeColumn]) {

      // Check if we can match the first bin
      const firstBin = fineBinResults[activeColumn][0];
      if (firstBin) {
        const firstBinLabel = firstBin.Bin ?? `Bin_1`;
        const matchedMetric = binScoringMetrics[activeColumn]?.find(m => m.bin_name === String(firstBinLabel));
      }
    }
  }, [activeColumn, binScoringMetrics, fineBinResults]);
  // Ensure bin scoring metrics are calculated whenever fine bin results load for the active column
  useEffect(() => {
    const tryCompute = async () => {
      try {
        if (!activeColumn) return;
        const bins = fineBinResults[activeColumn];
        if (!Array.isArray(bins) || bins.length === 0) return;
        // Only request metrics if we don't already have them
        if (!binScoringMetrics[activeColumn] || binScoringMetrics[activeColumn].length === 0) {
          await calculateAllBinMetrics(activeColumn, bins);
        }
      } catch (e) {

      }
    };
    tryCompute();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeColumn, fineBinResults]);
  const formatToFourDecimals = (value: any) => (typeof value === 'number' ? value.toFixed(4) : String(value));

  const showNotification = (message: string) => {
    setNotification(message);
    setTimeout(() => setNotification(null), 3000);
  };
  const generateScoreCard = async () => {
    setGeneratingScoreCard(true);
    try {
      // Get the appropriate model results based on the selected model
      let modelResults: any = null;

      switch (selectedModelForScorecard) {
        case 'logistic':
          modelResults = logisticResults;
          break;
        case 'random_forest':
          modelResults = randomForestResults;
          break;
        case 'xgboost':
          modelResults = xgboostResults;
          break;
        default:
          modelResults = logisticResults;
      }

      if (!modelResults) {
        alert(`No results available for ${selectedModelForScorecard}. Please run the model first.`);
        setGeneratingScoreCard(false);
        return;
      }

      // Filter to only include variables that have WOE data
      const woeData = Object.fromEntries(
        Object.entries(woeIvResults).map(([key, value]) => [key, value.stats || []])
      );
      const varsToUse = selectedForFinalModeling.length > 0 ? selectedForFinalModeling : selectedForModeling;
      const validVariables = varsToUse.filter(v => v in woeData && woeData[v].length > 0);

      if (validVariables.length === 0) {
        alert('No variables with WOE data available. Please calculate WOE for selected variables first.');
        setGeneratingScoreCard(false);
        return;
      }

      if (validVariables.length < varsToUse.length) {
        const missing = varsToUse.filter(v => !(v in woeData) || woeData[v].length === 0);
        console.warn(`Skipping variables without WOE data: ${missing.join(', ')}`);
      }

      const response = await fetch('http://localhost:5000/api/generate-scorecard', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          selected_variables: validVariables,
          target: targetVariable,
          woe_transformed_data: Object.fromEntries(
            validVariables.map(v => [v, woeData[v]])
          ),
          model_type: selectedModelForScorecard,
          model_results: modelResults,
          record_id: recordId
        })
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ error: 'Failed to generate scorecard' }));
        alert(`Error generating score card: ${errorData.error || 'Unknown error'}`);
        setGeneratingScoreCard(false);
        return;
      }

      const data = await response.json();
      if (data.success) {
        setScoreCardData(data);
        if (data.scorecard_bins) {
          const totalBins = data.scorecard_bins.length;
          const varsToUse = selectedForFinalModeling.length > 0 ? selectedForFinalModeling : selectedForModeling;
          const variableCounts = varsToUse.map(variable => {
            const variableBins = data.scorecard_bins.filter((bin: any) => bin.variable === variable);
            return { variable, count: variableBins.length };
          });
          showNotification(`Score card generated with ${totalBins} bins across ${varsToUse.length} variables using ${selectedModelForScorecard} model`);
        } else {
          showNotification(`Score card generated successfully using ${selectedModelForScorecard} model!`);
        }
      } else {
        alert(`Error generating score card: ${data.error}`);
      }
    } catch (error) {
      alert(`Error generating score card: ${error}`);
    } finally {
      setGeneratingScoreCard(false);
    }
  };
  const gotoScoreCardAndGenerate = () => {
    setCurrentStep(4);
    setTimeout(() => {
      generateScoreCard();
    }, 50);
  };
  const runFineBinPassThrough = async (
    col: string,
    varType: string,
    mergesOverride?: Record<string, any[]>
  ): Promise<{ merges: Record<string, any[]> } | null> => {
    if (!recordId || !targetVariable) {
      return null;
    }
    try {
      const res = await fetch('http://localhost:5000/api/fine-bin', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          variable: col,
          target: targetVariable,
          type: varType,
          bin_merges: mergesOverride || {},
          record_id: recordId,
          dashboard_selected_columns: Array.from(selectedForModeling),
        }),
      });
      if (!res.ok) {
        console.warn(`Fine-bin fallback failed for ${col}:`, await res.text());
        return null;
      }
      const data = await res.json();
      if (!data.success || data.error) {
        console.warn(`Fine-bin fallback response for ${col} indicated failure`, data);
        return null;
      }
      const normalizedStats = normalizeBinArray(data.stats || []);
      const mergesToPersist = data.bin_merges || mergesOverride || {};
      setFineBinResults((prev) => ({ ...prev, [col]: normalizedStats }));
      setBinMergeHistory((prev) => ({ ...prev, [col]: mergesToPersist }));
      setSelectedFineBins((prev) => ({ ...prev, [col]: [] }));
      try {
        await calculateAllBinMetrics(col, normalizedStats);
      } catch (e) {

      }
      const appliedWoe = updateLocalWoeState(col, data.woe_iv);
      if (!appliedWoe) {
        await fetchWoeIv(col, mergesToPersist, false);
      }
      return { merges: mergesToPersist };
    } catch (error) {
      console.error(`Fine-bin fallback crashed for ${col}:`, error);
      return null;
    }
  };

  // API calls
  const loadSavedFineBins = async (
    col: string,
    varType: string
  ): Promise<{ merges: Record<string, any[]> | undefined; hydrated: boolean }> => {
    const cachedMerges = binMergeHistory[col];
    const cachedBins = fineBinResults[col];
    if (
      cachedMerges &&
      Object.keys(cachedMerges).length > 0 &&
      Array.isArray(cachedBins) &&
      cachedBins.length > 0
    ) {
      return { merges: cachedMerges, hydrated: true };
    }

    if (!recordId || !targetVariable) return { merges: undefined, hydrated: false };

    // First attempt: hydrate directly from persisted fine-bin cache (no recomputation)
    try {
      const cacheResp = await fetch(`http://localhost:5000/api/finebin-cache/${recordId}/${encodeURIComponent(col)}`);
      if (cacheResp.ok) {
        const cacheData = await cacheResp.json();
        if (cacheData?.success && Array.isArray(cacheData.stats) && cacheData.stats.length > 0) {
          const normalizedStats = normalizeBinArray(cacheData.stats);
          setFineBinResults((prev) => ({ ...prev, [col]: normalizedStats }));
          const mergesFromCache: Record<string, any[]> = cacheData.bin_merges || {};
          if (Object.keys(mergesFromCache).length > 0) {
            setBinMergeHistory((prev) => ({ ...prev, [col]: mergesFromCache }));
          }
          setSelectedFineBins((prev) => ({ ...prev, [col]: [] }));
          try {
            await calculateAllBinMetrics(col, normalizedStats);
          } catch (e) {

          }
          const cacheWoePayload =
            cacheData?.woe_iv ||
            (typeof cacheData?.iv === 'number'
              ? { iv: cacheData.iv, stats: cacheData.stats }
              : undefined);
          const woeApplied = updateLocalWoeState(col, cacheWoePayload);
          if (!woeApplied) {
            await fetchWoeIv(col, mergesFromCache, false);
          }
          return {
            merges: Object.keys(mergesFromCache).length > 0 ? mergesFromCache : cachedMerges,
            hydrated: true,
          };
        }
      }
    } catch (cacheError) {
      console.warn(`Fine-bin cache hydrate failed for ${col}:`, cacheError);
    }

    // Fallback: pull merge blueprint then recompute via fine-bin endpoint
    try {
      const resp = await fetch(`http://localhost:5000/api/finebin-details/${recordId}/${encodeURIComponent(col)}`);
      if (!resp.ok) {
        console.error(`Failed to load finebin details for ${col}:`, resp.status);
        return { merges: undefined, hydrated: false };
      }
      const details = await resp.json();
      if (!Array.isArray(details) || details.length === 0) {
        return { merges: undefined, hydrated: false };
      }
      const savedMerges: Record<string, any[]> = {};
      details.forEach((row: any) => {
        if (Array.isArray(row.merged_bins) && row.merged_bins.length > 0) {
          savedMerges[row.group_id] = row.merged_bins;
        }
      });
      if (Object.keys(savedMerges).length === 0) {
        return { merges: undefined, hydrated: false };
      }
      const fallbackResult = await runFineBinPassThrough(col, varType, savedMerges);
      if (fallbackResult) {
        return { merges: fallbackResult.merges, hydrated: true };
      }
    } catch (e) {
      console.warn(`Fine-bin rehydrate failed for ${col}:`, e);
    }
    return { merges: undefined, hydrated: false };
  };
  const loadSavedData = async () => {
    if (!recordId) return;
    try {
      const recordResp = await fetch(`http://localhost:5000/api/record/${recordId}`);
      const recordData = await recordResp.json();

      // Load dataset path from record
      if (recordData.dataset_path) {
        setDatasetPath(recordData.dataset_path);
      }

      if (recordData.binning_data) {
        const lookup = buildTypeLookup(
          Array.isArray(recordData.discrete_columns) ? recordData.discrete_columns : [],
          Array.isArray(recordData.continuous_columns) ? recordData.continuous_columns : []
        );
        const normalized = buildBinningState(recordData.binning_data, lookup);
        syncBinningFromState(normalized);
      }

      if (Array.isArray(recordData.selected_columns)) {
        setSelectedColumns(recordData.selected_columns);
        // Load selectedForUnivariate from database for Feature Selection checkboxes
        setSelectedForUnivariate(recordData.selected_columns);
      }

      let modelReadySelections: string[] = [];
      if (Array.isArray(recordData.dashboard_selected_columns)) {
        modelReadySelections = recordData.dashboard_selected_columns
          .map((value: any) => String(value).trim())
          .filter(Boolean);
      }
      let finalSelections: string[] = [];
      if (Array.isArray(recordData.final_selected_columns)) {
        finalSelections = recordData.final_selected_columns
          .map((value: any) => String(value).trim())
          .filter(Boolean);
      }

      try {
        const featuresResp = await fetch(`http://localhost:5000/api/dataset/${recordId}/features`);
        if (featuresResp.ok) {
          const featureList = await featuresResp.json();
          if (Array.isArray(featureList)) {
            const modelReadyFromDb = featureList
              .filter((feature: any) => feature?.model_ready)
              .map((feature: any) => String(feature.name).trim())
              .filter(Boolean);
            if (modelReadyFromDb.length > 0) {
              modelReadySelections = modelReadyFromDb;
            }

            const finalSelectedFromDb = featureList
              .filter((feature: any) => feature?.final_selected)
              .map((feature: any) => String(feature.name).trim())
              .filter(Boolean);
            if (finalSelectedFromDb.length > 0) {
              finalSelections = finalSelectedFromDb;
            }
          }
        }
      } catch (err) {
        console.error('Failed to load feature selections from database:', err);
      }

      setSelectedForModeling(modelReadySelections);
      setSelectedForFinalModeling(finalSelections);
    } catch (e) {

    }
  };
  const handleColumnClick = async (col: string) => {
    // Allow re-fetch if coming from auto mode or if data is missing
    if (col === activeColumn && fineBinResults[col] && fineBinResults[col].length > 0) {
      return; // Prevent re-fetching if already active and has data
    }
    setActiveColumn(col);
    try {
      const varType = (continuousColumns || []).includes(col) ? 'continuous' : 'discrete';

      // First, try to load saved fine bins from database
      const { merges, hydrated } = await loadSavedFineBins(col, varType);

      if (hydrated) {
        return;
      }

      if (merges && Object.keys(merges).length > 0) {
        // Data exists in database, bins were loaded by loadSavedFineBins
        const mergePayload = merges;

        // Fetch WOE/IV using existing bins
        const updatedWoe = await fetchWoeIv(col, mergePayload, false);

        if (updatedWoe) {
          setWoeReadyColumns((prev) => new Set(prev).add(col));
        }
      } else {
        // No saved data - calculate from scratch and store
        const res = await fetch('http://localhost:5000/api/univariate-analysis', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            discrete: varType === 'discrete' ? [col] : [],
            continuous: varType === 'continuous' ? [col] : [],
            target: targetVariable,
            record_id: recordId, // Pass record_id to persist results
          }),
        });
        const data = await res.json();
        const coarseStats = normalizeBinArray(data[col]?.stats || data[col] || []);
        setUnivariateResults((prev) => ({ ...prev, [col]: { ...(data[col] || {}), stats: coarseStats } }));
        setCoarseBinResults((prev) => ({ ...prev, [col]: coarseStats }));
        setFineBinResults((prev) => ({ ...prev, [col]: coarseStats }));

        // Precompute bin scoring metrics for the initial fine/coarse bins
        try {
          await calculateAllBinMetrics(col, coarseStats);
        } catch (e) {
          console.error('Error calculating bin metrics:', e);
        }

        setBinMergeHistory((prev) => ({ ...prev, [col]: prev[col] || {} }));
        setSelectedFineBins((prev) => ({ ...prev, [col]: [] }));

        // Calculate and store WOE/IV
        const updatedWoe = await fetchWoeIv(col, undefined, false);

        if (updatedWoe) {
          setWoeReadyColumns((prev) => new Set(prev).add(col));
        }
      }
    } catch (err) {
      console.error('Error in handleColumnClick:', err);
      alert('Error fetching coarse bin results');
    }
  };
  const toggleFineBinSelection = (col: string, binLabel: string) => {
    const normalized = String(binLabel);
    setSelectedFineBins((prev) => {
      const current = prev[col] || [];
      const exists = current.includes(normalized);
      const updated = exists ? current.filter((label) => label !== normalized) : [...current, normalized];
      return { ...prev, [col]: updated };
    });
  };
  const runBinning = async (col: string) => {
    const varType = (continuousColumns || []).includes(col) ? 'continuous' : 'discrete';
    const selectedLabels = Array.from(new Set((selectedFineBins[col] || []).map(String).filter(Boolean)));

    if (selectedLabels.length < 2) {
      showNotification('Select at least two bins to merge.');
      return;
    }

    const history = binMergeHistory[col] || {};

    // Expand selected labels using history to get underlying bin labels
    const expandedSelection = Array.from(new Set(
      selectedLabels.flatMap(label => {
        const underlying = history[label];
        if (Array.isArray(underlying) && underlying.length > 0) {
          return underlying.map(String).filter(Boolean);
        }
        return [String(label).trim()];
      })
    ));

    if (expandedSelection.length < 2) {
      showNotification('Selected bins do not resolve to at least two distinct bins to merge.');
      return;
    }

    // Remove any old merges that overlap with the new merge
    const filteredHistoryEntries = Object.entries(history).filter(([, bins]) => {
      if (!Array.isArray(bins)) return true;
      return !bins.some(b => expandedSelection.includes(String(b).trim()));
    });
    const filteredHistory = Object.fromEntries(filteredHistoryEntries);

    // Create merge key - use sorted labels for consistency
    const sortedExpanded = [...expandedSelection].sort((a, b) => a.localeCompare(b));
    const mergeKey = varType === 'continuous'
      ? `Merged_${Object.keys(filteredHistory).length + 1}`
      : sortedExpanded.join(', ');  // For discrete, use comma-separated labels

    const payloadMerges = { ...filteredHistory, [mergeKey]: sortedExpanded };

    try {
      // Re-run coarse binning to get latest stats
      const coarseRes = await fetch('http://localhost:5000/api/univariate-analysis', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          discrete: varType === 'discrete' ? [col] : [],
          continuous: varType === 'continuous' ? [col] : [],
          target: targetVariable,
          record_id: recordId,
        }),
      });
      const coarseData = await coarseRes.json();
      const coarseStats = normalizeBinArray(coarseData[col]?.stats || coarseData[col] || []);
      const updatedUnivariate = {
        ...univariateResults,
        [col]: { ...(coarseData[col] || {}), stats: coarseStats },
      };
      const updatedCoarse = { ...coarseBinResults, [col]: coarseStats };
      setUnivariateResults(updatedUnivariate);
      setCoarseBinResults(updatedCoarse);

      // Run fine binning
      const fineRes = await fetch('http://localhost:5000/api/fine-bin', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          variable: col,
          target: targetVariable,
          type: varType,
          bin_merges: payloadMerges,
          record_id: recordId,
          dashboard_selected_columns: selectedForModeling,
        }),
      });
      const fineData = await fineRes.json();

      if (!fineData.success) throw new Error(fineData.error);

      const mergesReturned = fineData.bin_merges || payloadMerges;
      const normalizedFine = normalizeBinArray(fineData.stats || []);
      const updatedFine = { ...fineBinResults, [col]: normalizedFine };
      const updatedHistory = { ...binMergeHistory, [col]: mergesReturned };
      setFineBinResults(updatedFine);
      setBinMergeHistory(updatedHistory);
      setSelectedFineBins(prev => ({ ...prev, [col]: [] }));

      // Recalculate bin scoring metrics (G/B odd, index, combined index, etc.) for the updated bins
      try {
        await calculateAllBinMetrics(col, normalizedFine);
      } catch (e) {

      }

      const latestWoe = await fetchWoeIv(col, mergesReturned, false);
      if (latestWoe) {
        setWoeReadyColumns(prev => new Set(prev).add(col));
      }

      const persistedRecordId = await persistFineBinColumn(col, mergesReturned, {
        univariateResults: updatedUnivariate,
        fineBinResults: updatedFine,
        crosstabResults: updatedCoarse,
        woeIvResults: latestWoe ?? woeIvResultsRef.current,
      });
      showNotification(`Bins merged successfully for ${col}. ${normalizedFine.length} bins remaining.`);
    } catch (err) {
      console.error('Error running binning:', err);
      const errorMessage = err instanceof Error ? err.message : 'Unknown error occurred';
      alert(`Error running binning: ${errorMessage}`);
      showNotification(`Failed to merge bins for ${col}: ${errorMessage}`);
    }
  };
  // const undoBinMerge = (col: string) => {
  // if (binMergeStack[col]) {
  // setBinMergeHistory((prev) => ({
  // ...prev,
  // [col]: typeof binMergeStack[col] === 'object' && !Array.isArray(binMergeStack[col]) ? binMergeStack[col] : {},
  // }));
  // setBinMergeStack((prev) => {
  // const newStack = { ...prev };
  // delete newStack[col];
  // return newStack;
  // });
  // showNotification(`Undo last merge for ${col}`);
  // // Re-run fine binning with previous history
  // runBinning(col);
  // } else {
  // showNotification(`No undo available for ${col}`);
  // }
  // };
  // Unmerge a specific merged fine bin for a column and refresh results
  const unmergeFineBin = async (col: string, mergedLabelRaw: any) => {
    const varType = (continuousColumns || []).includes(col) ? 'continuous' : 'discrete';
    const history = binMergeHistory[col] || {};
    const mergedLabel = String(mergedLabelRaw);

    let keyToRemove: string | null = null;

    if (varType === 'discrete') {
      // Match exactly on the merged key (e.g., "A, B, C")
      const normalizedTarget = mergedLabel.split(',').map(s => s.trim()).sort().join(', ');
      keyToRemove = Object.keys(history).find(k => {
        const normalizedKey = k.split(',').map(s => s.trim()).sort().join(', ');
        return normalizedKey === normalizedTarget;
      }) || (history[mergedLabel] ? mergedLabel : null);
    } else {
      keyToRemove = mergedLabel;
    }

    if (!keyToRemove || !history[keyToRemove]) {
      showNotification(`Could not find merge for '${mergedLabel}'`);
      return;
    }

    const newHistory = { ...history };
    delete newHistory[keyToRemove];

    // Re-run fine binning
    const res = await fetch('http://localhost:5000/api/fine-bin', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        variable: col,
        target: targetVariable,
        type: varType,
        bin_merges: newHistory,
        record_id: recordId,
        dashboard_selected_columns: selectedForModeling,
      }),
    });

    if (!res.ok) {
      const errorData = await res.json().catch(() => ({ error: 'Failed to unmerge fine bin' }));
      showNotification(`Error: ${errorData.error || 'Failed to unmerge fine bin'}`);
      return;
    }

    const data = await res.json();
    if (!data.success) {
      showNotification(`Error: ${data.error || 'Fine binning returned no results'}`);
      return;
    }

    const normalizedStats = normalizeBinArray(data.stats || []);
    const updatedFine = { ...fineBinResults, [col]: normalizedStats };
    const updatedHistory = { ...binMergeHistory, [col]: data.bin_merges || newHistory };
    setFineBinResults(updatedFine);
    setBinMergeHistory(updatedHistory);
    setSelectedFineBins(prev => ({ ...prev, [col]: [] }));

    // Recalculate metrics for the updated bins
    try {
      await calculateAllBinMetrics(col, normalizedStats);
    } catch (e) {

    }

    const latestWoe = await fetchWoeIv(col, data.bin_merges || newHistory, false);
    if (latestWoe) {
      setWoeReadyColumns(prev => new Set(prev).add(col));
    }
    await persistFineBinColumn(col, data.bin_merges || newHistory, {
      fineBinResults: updatedFine,
      woeIvResults: latestWoe ?? woeIvResultsRef.current,
      crosstabResults: coarseBinResults,
      univariateResults,
    });

    showNotification(`Unmerged '${mergedLabel}'`);
  };
  const resetFineBinning = async (col: string) => {
    const varType = (continuousColumns || []).includes(col) ? 'continuous' : 'discrete';

    // Reset UI state
    const clearedFine = { ...fineBinResults, [col]: [] };
    const clearedHistory = { ...binMergeHistory, [col]: {} };
    setFineBinResults(clearedFine);
    setBinMergeHistory(clearedHistory);
    setSelectedFineBins(prev => ({ ...prev, [col]: [] }));

    // Re-run coarse
    const res = await fetch('http://localhost:5000/api/univariate-analysis', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        discrete: varType === 'discrete' ? [col] : [],
        continuous: varType === 'continuous' ? [col] : [],
        target: targetVariable,
      }),
    });
    const data = await res.json();
    const columnResult = data[col] || data;
    const newStats = normalizeBinArray(columnResult?.stats || columnResult || []);
    const updatedUnivariate = { ...univariateResults, [col]: { ...columnResult, stats: newStats } };
    const updatedCoarse = { ...coarseBinResults, [col]: newStats };
    const updatedFine = { ...clearedFine, [col]: newStats };
    setUnivariateResults(updatedUnivariate);
    setCoarseBinResults(updatedCoarse);
    setFineBinResults(updatedFine);

    // Recompute metrics for reset bins
    try {
      await calculateAllBinMetrics(col, newStats);
    } catch (e) {

    }

    const latestWoe = await fetchWoeIv(col, {}, false);
    if (latestWoe) {
      setWoeReadyColumns(prev => new Set(prev).add(col));
    }

    await persistFineBinColumn(col, {}, {
      univariateResults: updatedUnivariate,
      fineBinResults: updatedFine,
      crosstabResults: updatedCoarse,
      woeIvResults: latestWoe ?? woeIvResultsRef.current,
    });

    showNotification(`Binning reset for ${col}`);
  };

  const runAutoMonotonicBinning = async (
    col: string,
    options: { silent?: boolean; onError?: (message: string) => void } = {}
  ): Promise<boolean> => {
    const { silent = false, onError } = options;
    if (!col) return false;
    const varType = (continuousColumns || []).includes(col) ? 'continuous' : 'discrete';

    try {
      if (!silent) {
        showNotification(`Running auto-monotonic binning for ${col}...`);
      }

      // Call the auto-monotonic-binning API
      const response = await fetch('http://localhost:5000/api/auto-monotonic-binning', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          variable: col,
          target: targetVariable,
          type: varType,
          direction: null,  // Auto-detect direction
          method: 'exhaustive',  // Use exhaustive algorithm
          record_id: recordId,
          dashboard_selected_columns: selectedForModeling,
        }),
      });

      const data = await response.json();

      if (!data.success) {
        throw new Error(data.error || 'Auto-binning failed');
      }

      // Update UI with results
      const normalizedAutoStats = normalizeBinArray(data.stats || []);
      const updatedFine = { ...fineBinResults, [col]: normalizedAutoStats };
      const updatedHistory = { ...binMergeHistory, [col]: data.bin_merges || {} };
      setFineBinResults(updatedFine);
      setBinMergeHistory(updatedHistory);
      setSelectedFineBins(prev => ({ ...prev, [col]: [] }));

      // Recalculate bin scoring metrics
      try {
        await calculateAllBinMetrics(col, normalizedAutoStats);
      } catch (e) {
        console.error('Error calculating bin metrics:', e);
      }

      const woeApplied = updateLocalWoeState(col, data.woe_iv);
      let latestWoe: Record<string, any> | null = null;
      if (!woeApplied) {
        latestWoe = await fetchWoeIv(col, data.bin_merges || {}, false);
      }

      await persistFineBinColumn(col, data.bin_merges || {}, {
        fineBinResults: updatedFine,
        crosstabResults: coarseBinResults,
        univariateResults,
        woeIvResults: latestWoe ?? woeIvResultsRef.current,
      });

      // Show success message with details
      const message = `Auto-binning completed for ${col}: ${data.num_merges} merges performed, ` +
        `${data.num_bins_original} → ${data.num_bins_final} bins, ` +
        `WOE trend: ${data.direction}, monotonic: ${data.is_monotonic ? 'Yes' : 'No'}`;

      if (!silent) {
        showNotification(message);
      }
      return true;

    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      console.error('Auto-binning error:', err);
      onError?.(message);
      if (!silent) {
        showNotification(`Error in auto-binning: ${message}`);
        alert('Error running auto-monotonic binning');
      }
      return false;
    }
  };

  const runFullAutoMonotonicBinning = async () => {
    if (fullAutoMonotonicLoading || autoBinningModeLoading) return;
    if (!targetVariable) {
      showNotification('Select a target variable before running Full Auto Monotonic Binning.');
      return;
    }
    const eligibleColumns = Array.from(
      new Set(
        (selectedColumns || []).filter((col) =>
          (discreteColumns || []).includes(col) || (continuousColumns || []).includes(col)
        )
      )
    ).filter((col) => col && col !== targetVariable);

    if (eligibleColumns.length === 0) {
      showNotification('No discrete or continuous features are available for Full Auto Monotonic Binning.');
      return;
    }

    setFullAutoMonotonicLoading(true);
    setFullAutoMonotonicProgress('Initializing full auto monotonic binning...');
    setFullAutoMonotonicPercentage(0);
    setFullAutoMonotonicCurrent('');

    const failedColumns: { column: string; reason: string }[] = [];
    const cachedColumns: string[] = [];
    let processed = 0;

    const processColumn = async (col: string) => {
      const varType = (continuousColumns || []).includes(col) ? 'continuous' : 'discrete';
      setFullAutoMonotonicCurrent(col);
      setFullAutoMonotonicProgress(`Processing ${col}...`);

      const hasFine = Array.isArray(fineBinResults[col]) && fineBinResults[col].length > 0;
      const hasWoe = Array.isArray(woeIvResults[col]?.stats) && woeIvResults[col]?.stats.length > 0;
      if (hasFine && hasWoe) {
        cachedColumns.push(col);
        return;
      }
      if (hasFine && !hasWoe) {
        const mergesForCol = binMergeHistory[col] && Object.keys(binMergeHistory[col] || {}).length > 0
          ? binMergeHistory[col]
          : undefined;
        await fetchWoeIv(col, mergesForCol, false);
        cachedColumns.push(col);
        return;
      }

      try {
        const { hydrated } = await loadSavedFineBins(col, varType);
        if (hydrated) {
          cachedColumns.push(col);
          return;
        }

        const errors: string[] = [];
        const success = await runAutoMonotonicBinning(col, {
          silent: true,
          onError: (message) => errors.push(message),
        });

        if (!success) {
          const fallback = await runFineBinPassThrough(col, varType);
          if (fallback) {
            cachedColumns.push(col);
          } else {
            failedColumns.push({ column: col, reason: errors[0] || 'Auto-binning failed' });
          }
        }
      } catch (err) {
        console.error(`Full auto monotonic error for ${col}:`, err);
        failedColumns.push({ column: col, reason: err instanceof Error ? err.message : String(err) });
      }
    };

    const queue = [...eligibleColumns];
    const workerCount = Math.min(FULL_AUTO_CONCURRENCY, Math.max(1, queue.length));
    const workers = Array.from({ length: workerCount }).map(async () => {
      while (queue.length > 0) {
        const next = queue.shift();
        if (!next) break;
        await processColumn(next);
        processed += 1;
        setFullAutoMonotonicPercentage(Math.round((processed / eligibleColumns.length) * 100));
      }
    });

    await Promise.all(workers);

    setFullAutoMonotonicProgress(
      failedColumns.length === 0
        ? 'Full Auto Monotonic Binning complete!'
        : `Completed with warnings for ${failedColumns.length} feature(s).`
    );
    setFullAutoMonotonicPercentage(100);

    if (failedColumns.length === 0) {
      const cachedNote = cachedColumns.length > 0
        ? ` Reused cached bins for ${cachedColumns.length} ${cachedColumns.length === 1 ? 'feature' : 'features'}.`
        : '';
      showNotification(`Full Auto Monotonic Binning finished for all requested features.${cachedNote}`);
    } else {
      const failurePreview = failedColumns.slice(0, 3).map(({ column }) => column).join(', ');
      showNotification(
        `Full Auto Monotonic finished with ${failedColumns.length} failure(s). ${failurePreview}${failedColumns.length > 3 ? ', ...' : ''
        }. Check console for details.`
      );
    }

    setTimeout(() => {
      setFullAutoMonotonicLoading(false);
      setFullAutoMonotonicProgress('');
      setFullAutoMonotonicPercentage(0);
      setFullAutoMonotonicCurrent('');
    }, 750);
  };

  const hydrateFromCache = async (col: string) => {
    const cachedBins = fineBinResults[col] && fineBinResults[col].length > 0
      ? fineBinResults[col]
      : (coarseBinResults[col] && coarseBinResults[col].length > 0 ? coarseBinResults[col] : []);
    const cachedMerges = binMergeHistory[col];

    if (!cachedBins || cachedBins.length === 0) {
      return false;
    }

    try {
      await calculateAllBinMetrics(col, cachedBins);
    } catch (e) {

    }

    if (cachedMerges && Object.keys(cachedMerges).length > 0 && recordId) {
      const woeData = await fetchWoeIv(col, cachedMerges, false);
      if (woeData && woeData[col]) {
        setWoeReadyColumns((prev) => new Set(prev).add(col));
      }
      return true;
    }

    return false;
  };

  const fetchAllAutoBinningData = async () => {
    // Prevent concurrent loads
    if (isLoadingAutoBinning.current) return;
    isLoadingAutoBinning.current = true;

    // Show loading animation
    setAutoBinningModeLoading(true);
    setAutoBinningModeProgress('Initializing...');
    setAutoBinningModePercentage(0);

    try {
      if (!targetVariable) {
        setAutoBinningModeProgress('Select a target variable first.');
        return;
      }

      // Count total columns to process
      const columnsToProcess = selectedColumns.filter(col => {
        const existing = woeIvResults[col];
        return !existing || !Array.isArray(existing.stats) || existing.stats.length === 0;
      });
      const totalColumns = columnsToProcess.length;
      let processedCount = 0;

      if (totalColumns === 0) {
        setAutoBinningModeProgress('All features already loaded!');
        setAutoBinningModePercentage(100);
        await new Promise(resolve => setTimeout(resolve, 200));
        return;
      }

      setAutoBinningModeProgress(`Processing ${totalColumns} features...`);
      setAutoBinningModePercentage(5);

      const batchSize = 3;
      for (let i = 0; i < columnsToProcess.length; i += batchSize) {
        const batch = columnsToProcess.slice(i, i + batchSize);

        await Promise.all(batch.map(async (col) => {
          const varType = (continuousColumns || []).includes(col) ? 'continuous' : 'discrete';

          try {
            // First try to hydrate from cached fine/coarse results (already in memory)
            const hydrated = await hydrateFromCache(col);
            if (hydrated) {
              return;
            }

            const res = await fetch('http://localhost:5000/api/univariate-analysis', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                discrete: varType === 'discrete' ? [col] : [],
                continuous: varType === 'continuous' ? [col] : [],
                target: targetVariable,
                record_id: recordId,
              }),
            });
            if (!res.ok) {
              console.error(`Failed univariate analysis for ${col}:`, await res.text());
              return;
            }
            const data = await res.json();
            const coarseStats = normalizeBinArray(data[col]?.stats || data[col] || []);

            if (coarseStats.length === 0) {
              return;
            }

            setUnivariateResults((prev) => ({ ...prev, [col]: { ...(data[col] || {}), stats: coarseStats } }));
            setCoarseBinResults((prev) => ({ ...prev, [col]: coarseStats }));
            setFineBinResults((prev) => ({ ...prev, [col]: coarseStats }));

            try {
              await calculateAllBinMetrics(col, coarseStats);
            } catch (e) {

            }

            const woeData = await fetchWoeIv(col, undefined, false);
            if (woeData && woeData[col]) {
              setWoeReadyColumns((prev) => new Set(prev).add(col));
            }

            processedCount++;
            const percentComplete = Math.round(((processedCount) / totalColumns) * 95) + 5;
            // Update progress only every batch or at completion
            if (processedCount % batchSize === 0 || processedCount === totalColumns) {
              setAutoBinningModePercentage(percentComplete);
              setAutoBinningModeProgress(`Processed ${processedCount} of ${totalColumns} features...`);
            }
          } catch (e) {
            console.error(`Error processing ${col}:`, e);
            processedCount++;
          }
        }));
      }

      setAutoBinningModePercentage(100);
      setAutoBinningModeProgress('Complete! All features loaded.');
      await new Promise(resolve => setTimeout(resolve, 200));

    } finally {
      isLoadingAutoBinning.current = false;
      setAutoBinningModeLoading(false);
      setAutoBinningModeProgress('');
      setAutoBinningModePercentage(0);
    }
  };

  const loadColumnData = async (col: string) => {

    // Skip if already has WOE/IV data, is currently loading, or has been attempted
    if (woeIvResults[col] || loadingColumns.has(col) || loadedColumnsRef.current.has(col)) return;

    // Mark as loading and attempted
    loadedColumnsRef.current.add(col);
    setLoadingColumns(prev => new Set(prev).add(col));

    const varType = (continuousColumns || []).includes(col) ? 'continuous' : 'discrete';
    try {
      // Check if there are saved fine bins for this column
      const { merges, hydrated } = await loadSavedFineBins(col, varType);
      if (hydrated) {
        return;
      }
      const mergePayload = merges && Object.keys(merges).length > 0 ? merges : undefined;


      // Fetch WOE/IV data (this will use existing bins, not run auto-binning)
      const fetched = await fetchWoeIv(col, mergePayload, false);

      // After auto-loading WOE/IV, compute bin scoring metrics so display matches manual flow
      try {
        const bins = fineBinResults[col] && fineBinResults[col].length > 0
          ? fineBinResults[col]
          : (coarseBinResults[col] && coarseBinResults[col].length > 0 ? coarseBinResults[col] : []);
        if (Array.isArray(bins) && bins.length > 0) {

          await calculateAllBinMetrics(col, bins);
        } else {

        }
      } catch (e) {

      }
    } catch (e) {

    } finally {
      // Remove from loading set
      setLoadingColumns(prev => {
        const newSet = new Set(prev);
        newSet.delete(col);
        return newSet;
      });
    }
  };

  const handleConfigureManually = async (col: string) => {
    setBinningMode('manual');
    // Load the column data if not already loaded or if it's a different column
    if (col !== activeColumn || !fineBinResults[col] || fineBinResults[col].length === 0) {
      await handleColumnClick(col);
    } else {
      setActiveColumn(col);
    }
  };

  const handleSwitchToAutoBinning = async () => {
    setBinningMode('auto');
    // Trigger loading animation and data fetch
    await fetchAllAutoBinningData();
  };

  type PersistStateOverrides = {
    univariateResults?: Record<string, any>;
    fineBinResults?: Record<string, any[]>;
    crosstabResults?: Record<string, any[]>;
    woeIvResults?: Record<string, any>;
    selectedColumns?: string[];
    dashboardSelectedColumns?: string[];
  };

  const persistFineBinColumn = async (
    col: string,
    merges: Record<string, any[]>,
    overrides: PersistStateOverrides = {}
  ): Promise<number | undefined> => {
    let current = recordId;
    try {
      const payloadSelectedColumns = overrides.selectedColumns ?? selectedColumns ?? [];
      const payloadDashboard = overrides.dashboardSelectedColumns ?? selectedForModeling ?? [];

      const upsertResp = await fetch('http://localhost:5000/api/upsert-single-record', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          dataset_path: datasetPath || undefined,
          discrete_columns: discreteColumns || [],
          continuous_columns: continuousColumns || [],
          selected_columns: payloadSelectedColumns,
          dashboard_selected_columns: payloadDashboard,
          target_variable: targetVariable || '',
          record_id: recordId,
        }),
      });
      const up = await upsertResp.json();
      if (!up.error && typeof up.id !== 'undefined') {
        current = up.id;
        setRecordId(up.id);
      }
      if (current) {
        await fetch('http://localhost:5000/api/finebin-details', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ record_id: current, column_name: col, bin_merges: merges }),
        });
      }
    } catch (e) {

    }
    return current;
  };
  const persistDashboardSelectedColumns = async (
    newSelection: string[],
    forceSync = false
  ): Promise<number | undefined> => {
    const performPersist = async () => {
      const resp = await fetch('http://localhost:5000/api/upsert-single-record', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          dataset_path: datasetPath || undefined,
          discrete_columns: discreteColumns || [],
          continuous_columns: continuousColumns || [],
          selected_columns: selectedColumns,
          dashboard_selected_columns: newSelection,
          target_variable: targetVariable || '',
          record_id: recordId || undefined,
        }),
      });
      const data = await resp.json();
      if (!data.error && data.id) {
        setRecordId(data.id);
        return data.id as number;
      }
      return recordId || undefined;
    };

    if (forceSync) {
      try {
        return await performPersist();
      } catch (error) {
        console.error('Failed to persist selected columns:', error);
        return recordId || undefined;
      }
    }

    setTimeout(() => {
      performPersist().catch((error) => {
        console.error('Failed to persist selected columns:', error);
      });
    }, 0);

    return recordId || undefined;
  };

  const queueModelingPersist = async (
    col: string,
    shouldSelect: boolean,
    newSelection: string[]
  ): Promise<number | undefined> => {
    let datasetId = recordId;
    if (!datasetId) {
      datasetId = await persistDashboardSelectedColumns(newSelection, true);
    } else {
      persistDashboardSelectedColumns(newSelection);
    }
    if (!datasetId) return undefined;
    try {
      await fetch('http://localhost:5000/api/update-feature-modeling', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          feature_name: col,
          record_id: datasetId,
          is_selected: shouldSelect,
        }),
      });
    } catch (err) {
      console.error('Failed to update feature modeling:', err);
    }
    return datasetId;
  };

  const queueFinalPersist = async (
    col: string,
    shouldSelect: boolean,
    newSelection: string[],
    datasetIdOverride?: number
  ) => {
    let datasetId = datasetIdOverride ?? recordId;
    if (!datasetId) {
      datasetId = await persistDashboardSelectedColumns(newSelection, true);
    }
    if (!datasetId) return;
    try {
      await fetch('http://localhost:5000/api/update-feature-final-selected', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          feature_name: col,
          record_id: datasetId,
          is_selected: shouldSelect,
        }),
      });
    } catch (err) {
      console.error('Failed to update feature final_selected:', err);
    }
  };

  const toggleSelectedForModeling = (col: string) => {
    // This is for Column Selection & Binning step (step 1) - updates model_ready
    setSelectedForModeling((prev) => {
      const isCurrentlySelected = prev.includes(col);
      const newSelection = isCurrentlySelected
        ? prev.filter((c) => c !== col)
        : [...prev, col];

      // Update UI immediately (optimistic update)
      showNotification(`${col} ${isCurrentlySelected ? 'deselected' : 'selected'} for modeling.`);

      queueModelingPersist(col, !isCurrentlySelected, newSelection).catch(() => { });
      return newSelection;
    });
  };

  const toggleSelectedForFinalModeling = (col: string) => {
    // This is for Model Training step (step 2) - updates final_selected
    setSelectedForFinalModeling((prev) => {
      const isCurrentlySelected = prev.includes(col);
      const newSelection = isCurrentlySelected
        ? prev.filter((c) => c !== col)
        : [...prev, col];

      // Also update selectedForModeling for compatibility with existing code
      setSelectedForModeling(newSelection);

      // Update UI immediately (optimistic update)
      showNotification(`${col} ${isCurrentlySelected ? 'deselected' : 'selected'} for final model training.`);

      queueModelingPersist(col, !isCurrentlySelected, newSelection)
        .then((datasetId) =>
          queueFinalPersist(col, !isCurrentlySelected, newSelection, datasetId)
        )
        .catch(() => {
          queueFinalPersist(col, !isCurrentlySelected, newSelection);
        });

      return newSelection;
    });
  };

  const prevSelectedColumnsRef = useRef<string[]>(selectedColumns);

  useEffect(() => {
    const prevSelected = prevSelectedColumnsRef.current || [];
    const removedColumns = prevSelected.filter((col) => !selectedColumns.includes(col));

    if (removedColumns.length > 0) {
      setWoeIvResults((prev) => {
        const next = { ...prev };
        removedColumns.forEach((col) => delete next[col]);
        return next;
      });
      setWoeReadyColumns((prev) => {
        const next = new Set(prev);
        removedColumns.forEach((col) => next.delete(col));
        return next;
      });
      setSelectedForModeling((prev) => prev.filter((col) => !removedColumns.includes(col)));
      showNotification(`WOE/IV data cleaned for dropped columns: ${removedColumns.join(', ')}`);
    }

    prevSelectedColumnsRef.current = selectedColumns;
  }, [selectedColumns]);

  useEffect(() => {
    woeIvResultsRef.current = woeIvResults;
  }, [woeIvResults]);
  const fetchWoeIv = async (
    col: string,
    merges?: Record<string, any[]>,
    addToModeling: boolean = true,
    options?: { recordIdOverride?: number },
  ): Promise<Record<string, any> | null> => {
    try {
      const varType = (continuousColumns || []).includes(col) ? 'continuous' : 'discrete';
      const resolvedRecordId = options?.recordIdOverride ?? recordId;
      const body: any = {
        variables: [col],
        target: targetVariable,
        type: varType  // Add this!
      };
      if (resolvedRecordId) body.record_id = resolvedRecordId;
      if (merges && Object.keys(merges).length > 0) {
        body.bin_merges = merges;
      }


      const res = await fetch('http://localhost:5000/api/woe-iv', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });

      if (!res.ok) {
        const errorData = await res.json().catch(() => ({ error: 'Failed to calculate WOE/IV' }));
        throw new Error(errorData.error || `WOE/IV calculation failed: ${res.status}`);
      }

      const data = await res.json();

      // Log whether the backend returned bin stats for the column (length and sample)
      try {
        const stats = data?.[col]?.stats ?? data?.[col]?.statistics ?? null;
        const statsLen = Array.isArray(stats) ? stats.length : (stats ? 1 : 0);
        const sample = Array.isArray(stats) && stats.length > 0 ? stats[0] : stats;

      } catch (e) {

      }

      if (!data.error && data[col]) {
        const normalizedEntry: { iv?: number; stats: NormalizedBin[] } = {
          iv: typeof data[col].iv === 'number' ? data[col].iv : undefined,
          stats: normalizeBinArray(data[col]?.stats || data[col]?.bins || []),
        };
        const mergedResults = { ...woeIvResultsRef.current, [col]: normalizedEntry };
        woeIvResultsRef.current = mergedResults;
        setWoeIvResults(mergedResults);
        setWoeReadyColumns((prev) => {
          const updated = new Set(prev);
          updated.add(col);
          return updated;
        });
        if (addToModeling) {
          setSelectedForModeling((prev) => [...new Set([...prev, col])]);
        }
        return mergedResults;
      } else {

      }
    } catch (e) {

    }
    return null;
  };

  // Show woeIvResults for the active column whenever it changes (helps debugging)
  useEffect(() => {
    if (!activeColumn) return;
    try {
      const w = woeIvResults[activeColumn];
      if (w) {
        try {
        } catch (e) {
          // ignore stringify errors
        }
      } else {
      }
    } catch (e) {

    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeColumn, woeIvResults]);
  const canGoToStep = (step: number) => {
    switch (step) {
      case 1:
        return true;
      case 2:
        return woeReadyColumns.size > 0; // Logistic Regression requires at least one WOE-ready column
      case 3:
        return woeReadyColumns.size > 0; // Score Card requires at least one WOE-ready column
      default:
        return false;
    }
  };
  const canGoNext = () => {
    switch (currentStep) {
      case 0: // Data Preprocessing - can always proceed
        return true;
      case 1: // Feature Selection - need selected columns and target
        return selectedForUnivariate.length > 0 && targetVariable !== '';
      case 2: // Binning - need at least one WOE-ready column
        return woeReadyColumns.size > 0;
      case 3: // Models - need at least one WOE-ready column
        return woeReadyColumns.size > 0;
      case 4: // Score Card - last step, no next
        return false;
      default:
        return false;
    }
  };
  const handleSave = async () => {
    if (!window.confirm('Are you sure you want to save the current analysis?')) return;
    try {
      const response = await fetch('http://localhost:5000/api/upsert-single-record', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          dataset_path: datasetPath || undefined,
          discrete_columns: discreteColumns || [],
          continuous_columns: continuousColumns || [],
          selected_columns: selectedColumns,
          dashboard_selected_columns: selectedForModeling,
          target_variable: targetVariable || '',
          record_id: recordId,
        }),
      });
      const data = await response.json();
      if (!data.error && data.id) {
        setRecordId(data.id);
        showNotification('Analysis saved successfully!');
      } else {

        alert(`Error saving analysis: ${data.error || 'Unknown error'}`);
      }
    } catch (error) {

      alert(`Error saving analysis: ${error}`);
    }
  };
  useEffect(() => {
    // Only fetch record when recordId changes, not in every render or loop
    loadSavedData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [recordId]);
  // Load model_ready checkboxes when moving to Binning section (step 1)
  useEffect(() => {
    if (currentStep === 1 && recordId) {
      fetch(`http://localhost:5000/api/dataset/${recordId}/features`)
        .then(r => r.json())
        .then((features: any[]) => {
          const modelReadyNames = features
            .filter((f: any) => f.model_ready)
            .map((f: any) => String(f.name).trim())
            .filter(Boolean);
          if (modelReadyNames.length > 0) {
            setSelectedForModeling(modelReadyNames);
          }
        })
        .catch(err => console.error('Failed to load model_ready features:', err));
    }
  }, [currentStep, recordId]);

  // Sync model_ready to final_selected and load final_selected checkboxes when navigating to Models step (step 2)
  useEffect(() => {
    if (currentStep === 2 && recordId) {
      // First sync model_ready to final_selected
      fetch('http://localhost:5000/api/sync-model-ready-to-final-selected', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          record_id: recordId
        })
      }).then(async (res) => {
        if (res.ok) {
          // After syncing, load final_selected values to initialize selectedForFinalModeling
          try {
            const features = await fetch(`http://localhost:5000/api/dataset/${recordId}/features`).then(r => r.json());
            const finalSelectedNames = features
              .filter((f: any) => f.final_selected)
              .map((f: any) => String(f.name).trim())
              .filter(Boolean);
            if (finalSelectedNames.length > 0) {
              setSelectedForFinalModeling(finalSelectedNames);
              setSelectedForModeling(finalSelectedNames); // Also update selectedForModeling for compatibility
            }
          } catch (err) {
            console.error('Failed to load final_selected features:', err);
          }
        }
      }).catch(err => console.error('Failed to sync model_ready to final_selected:', err));
    }
  }, [currentStep, recordId]);

  useEffect(() => {
    // Only trigger WOE/IV fetch when entering step 1 (Binning), 2 (Models), or 3 (Score Card), not in a loop
    if (currentStep === 1 || currentStep === 2 || currentStep === 3) {
      const cols: string[] = selectedColumns;
      const missing = cols.filter((c) => !woeIvResults[c]);
      if (missing.length > 0) {
        missing.forEach((col) => fetchWoeIv(col, undefined, false));
      }
    }
  }, [currentStep]);

  // Removed useEffect for auto binning mode - now handled by handleSwitchToAutoBinning

  return (
    <div>
      <Navbar />
      <div className="page-container">
        <div className="progress-header">
          <div className="progress-bar" role="navigation" aria-label="Analysis steps">
            {['Data Preprocessing', 'Feature Selection', 'Binning', 'Models', 'Score Card'].map((step, index) => (
              <button
                key={step}
                className={`progress-step ${currentStep === index ? 'active' : ''} ${currentStep > index ? 'completed' : ''}`}
                onClick={() => {
                  if (index <= currentStep) {
                    setCurrentStep(index);
                  }
                }}
                disabled={index > currentStep}
                aria-current={currentStep === index ? 'step' : undefined}
                aria-label={`${step} step`}
              >
                <span className="progress-number">{index + 1}</span>
                <span>{step}</span>
              </button>
            ))}
          </div>
          <div className="progress-actions">
            <button
              className="progress-action-btn previous-button"
              disabled={currentStep === 0}
              onClick={() => setCurrentStep((prev) => Math.max(0, prev - 1))}
              aria-label="Go to previous step"
            >
              Previous
            </button>
            <button
              className="progress-action-btn next-button"
              disabled={currentStep === 4 || !canGoNext()} // Updated to 4 since you have 5 steps (0-4)
              onClick={() => {
                if (currentStep === 0) {
                  // From Data Preprocessing, go to Feature Selection
                  setCurrentStep(1);
                } else if (currentStep === 1) {
                  // From Feature Selection, go to Binning
                  handleProceedToFeatureSelection();
                } else if (currentStep < 4) {
                  // For other steps, just increment
                  setCurrentStep((prev) => Math.min(4, prev + 1));
                }
              }}
              aria-label="Go to next step"
            >
              Next
            </button>
          </div>
        </div>
        {notification && <div className="notification" role="alert">{notification}</div>}
        <div className={`main-content-wrapper ${currentStep === 0 || currentStep === 1 || currentStep === 3 || currentStep === 4 ? 'full-width' : ''}`}>
          {/* Show sidebar only for Binning step (Step 2) */}
          {(currentStep === 2) && (
            <aside className="column-selection-section" aria-label="Scrollable column selection panel">
              <h3>Columns Dashboard</h3>
              <div className="sidebar-controls">
                <input
                  type="text"
                  placeholder="Search columns..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="search-input"
                />
                {/* Sorting controls and recommendation button removed */}
              </div>
              <div className="columns-grid" aria-label="List of selectable columns">
                {(() => {
                  try {

                  } catch { }
                  return null;
                })()}
                {filteredColumns.map((col: string) => {
                  const isChecked = selectedForModeling.includes(col);
                  try {

                  } catch { }
                  return (
                    <div
                      key={col}
                      className={`column-card ${col === activeColumn ? 'active' : ''}`}
                      onClick={() => handleColumnClick(col)}
                      role="button"
                      tabIndex={0}
                      onKeyDown={(e) => e.key === 'Enter' && handleColumnClick(col)}
                      aria-label={`Select column ${col}`}
                    >
                      <div className="column-card-content">
                        <input
                          type="checkbox"
                          checked={isChecked}
                          onChange={(e) => {
                            e.stopPropagation();
                            toggleSelectedForModeling(col);
                          }}
                          className="column-checkbox"
                          id={`checkbox-${col}`}
                          aria-label={`Include ${col} in modeling`}
                        />
                        <div className="column-info">
                          <h4 className="column-name">{col}</h4>
                          <small>{(discreteColumns || []).includes(col) ? 'Discrete' : 'Continuous'}</small>
                        </div>
                        {/* IV badge removed from column cards; moved into binning area */}
                        {/* Drop button removed as requested */}
                        {/* Compare button removed with WOE/IV section */}
                      </div>
                    </div>
                  );
                })}
              </div>
            </aside>
          )}

          <section className="content-section">
            {/* Step 0: Data Preprocessing */}
            {currentStep === 0 && (
              <div className="preprocessing-step" style={{ width: '100%' }}>
                <PreprocessingDetails
                  datasetId={recordId}
                  onPreprocessingComplete={(newDatasetId) => {
                    setPreprocessedDatasetId(newDatasetId);
                    setRecordId(newDatasetId);
                    setCurrentStep(1);
                    showNotification('Data preprocessing completed successfully!');
                    loadSavedData();
                  }}
                />

                {/* Skip preprocessing option */}
                <div className="preprocessing-skip" style={{ textAlign: 'center', marginTop: '20px' }}>
                  <button
                    className="skip-preprocessing-btn"
                    onClick={() => setCurrentStep(1)}
                    style={{
                      background: 'transparent',
                      border: '1px solid #ccc',
                      color: '#666',
                      padding: '8px 16px',
                      borderRadius: '4px',
                      cursor: 'pointer'
                    }}
                  >
                    Skip Preprocessing & Continue
                  </button>
                  <p style={{ fontSize: '12px', color: '#888', marginTop: '8px' }}>
                    You can always come back to preprocessing later
                  </p>
                </div>
              </div>
            )}

            {/* Step 1: Feature Selection */}
            {currentStep === 1 && (
              <div className="column-selection-step" style={{ width: '100%' }}>
                <div style={{ display: 'flex', justifyContent: 'center', gap: '12px', marginBottom: '16px' }}>
                  <button
                    className="assign-button"
                    onClick={async () => {
                      try {
                        const colsToClassify = columns;
                        if (!colsToClassify || colsToClassify.length === 0) {
                          alert('No columns to classify');
                          return;
                        }

                        alert(`Starting AI classification for ${colsToClassify.length} columns...`);

                        let sampleData: Record<string, any[]> = {};
                        try {
                          const sampleResp = await fetch('http://localhost:5000/api/csv-samples', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ columns: colsToClassify, sample_size: 20, record_id: recordId })
                          });
                          if (sampleResp.ok) {
                            sampleData = await sampleResp.json();
                          } else {
                            colsToClassify.forEach(col => {
                              sampleData[col] = [];
                            });
                          }
                        } catch (e) {
                          colsToClassify.forEach(col => {
                            sampleData[col] = [];
                          });
                        }

                        const resp = await fetch('http://localhost:5000/api/ai-classify-columns', {
                          method: 'POST',
                          headers: { 'Content-Type': 'application/json' },
                          body: JSON.stringify({ columns: colsToClassify, sampleData, record_id: recordId })
                        });
                        const data = await resp.json();
                        if (data && !data.error) {
                          let discreteCount = 0;
                          let continuousCount = 0;
                          Object.entries(data).forEach(([col, typ]) => {
                            if (col && (typ === 'discrete' || typ === 'continuous')) {
                              handleTypeChange(col, typ as string);
                              if (typ === 'discrete') discreteCount++;
                              else continuousCount++;
                            }
                          });
                          alert(`AI classification complete!\nClassified ${discreteCount} discrete and ${continuousCount} continuous variables.`);
                        } else {
                          alert('AI classification failed. See console for details.');
                        }
                      } catch (e) {
                        alert('AI classification failed. See console for details.');
                      }
                    }}
                  >
                    AI Separation (All Columns)
                  </button>
                  <button
                    className="assign-button"
                    onClick={() => setCurrentStep(0)}
                    style={{ background: '#28a745' }}
                  >
                    Back to Preprocessing
                  </button>
                </div>
                <div style={{ width: '100%' }}>
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
                    toggleSelectAllDiscrete={toggleSelectAllDiscrete}
                    toggleSelectAllContinuous={toggleSelectAllContinuous}
                    handleFineBin={async () => { }}
                    datasetPath={datasetPath}
                    recordId={recordId}
                  />
                </div>
              </div>
            )}
            {currentStep === 2 && (
              <div className="binning-mode-toggle">
                <div className="mode-toggle-group">
                  <button
                    className={`mode-toggle-btn ${binningMode === 'auto' ? 'active' : ''}`}
                    onClick={handleSwitchToAutoBinning}
                    disabled={autoBinningModeLoading || fullAutoMonotonicLoading}
                  >
                    Auto Binning
                  </button>
                  <button
                    className={`mode-toggle-btn ${binningMode === 'manual' ? 'active' : ''}`}
                    onClick={() => setBinningMode('manual')}
                    disabled={autoBinningModeLoading || fullAutoMonotonicLoading}
                  >
                    Manual Binning
                  </button>
                  {binningMode === 'auto' && (
                    <button
                      className={`mode-toggle-btn full-auto-action ${fullAutoMonotonicLoading ? 'loading' : ''}`}
                      onClick={runFullAutoMonotonicBinning}
                      disabled={fullAutoMonotonicLoading}
                    >
                      <span className="btn-icon">⚡</span>
                      Full Auto Monotonic
                    </button>
                  )}
                </div>
              </div>
            )}
            {binningMode === 'auto' && (
              <div className="auto-binning-container">
                <div className="auto-binning-grid">
                  {selectedColumns.map((col) => {
                    const woeData = woeIvResults[col];
                    const isLoading = loadingColumns.has(col);
                    const hasData = !!woeData;

                    const woeStats: NormalizedBin[] = woeData?.stats ?? [];
                    const totalIV = woeStats.reduce((sum: number, s: NormalizedBin) => sum + (Number(s.IV) || 0), 0);

                    const chartData = woeStats
                      .map((s, idx) => {
                        const label = getBinLabelValue(s, idx);
                        const order = typeof s.Min === 'number'
                          ? s.Min
                          : getNumericOrderFromLabel(label) ?? idx;
                        return {
                          bin: label,
                          WOE: Number(s.WOE ?? 0),
                          order
                        };
                      })
                      .sort((a, b) => (a.order ?? 0) - (b.order ?? 0));

                    return (
                      <div key={col} className="auto-binning-card">
                        <div className="auto-binning-card-header">
                          <input
                            type="checkbox"
                            className="fancy-checkbox"
                            checked={selectedForModeling.includes(col)}
                            onChange={(e) => {
                              e.stopPropagation();
                              toggleSelectedForModeling(col);
                            }}
                            aria-label={`Select ${col} for modeling`}
                          />
                          <h4>{col}</h4>
                        </div>

                        <div className="auto-binning-chart">
                          <div className="chart-label">WOE Graph</div>
                          {isLoading ? (
                            <div className="loading-placeholder">
                              <span>Loading...</span>
                            </div>
                          ) : chartData.length > 0 ? (
                            <ResponsiveContainer width="100%" height={120}>
                              <LineChart data={chartData}>
                                <CartesianGrid strokeDasharray="3 3" stroke="#30363d" />
                                <XAxis
                                  dataKey="bin"
                                  tick={{ fontSize: 10, fill: '#8b949e' }}
                                  interval={0}
                                  angle={-45}
                                  textAnchor="end"
                                  height={60}
                                />
                                <YAxis tick={{ fontSize: 10, fill: '#8b949e' }} />
                                <Tooltip
                                  contentStyle={{
                                    background: '#0d1117',
                                    border: '1px solid #30363d',
                                    borderRadius: '6px',
                                    fontSize: '12px'
                                  }}
                                />
                                <Line
                                  type="monotone"
                                  dataKey="WOE"
                                  stroke="#2ea043"
                                  strokeWidth={2}
                                  dot={{ r: 3, fill: '#2ea043' }}
                                />
                              </LineChart>
                            </ResponsiveContainer>
                          ) : (
                            <div className="no-data-placeholder">
                              <span>No WOE data available</span>
                            </div>
                          )}
                        </div>

                        <div className="auto-binning-footer">
                          <div className="iv-display">
                            <span className="iv-label">Total IV:</span>
                            <span className={`iv-value ${totalIV < 0.02 ? 'weak' : totalIV < 0.1 ? 'medium' : 'strong'}`}>
                              {totalIV.toFixed(4)}
                            </span>
                          </div>
                          <button
                            className="configure-manually-btn"
                            onClick={() => handleConfigureManually(col)}
                          >
                            Configure Manually
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
            {currentStep === 2 && binningMode === 'manual' && activeColumn && (() => {
              const isContinuousColumn = (continuousColumns || []).includes(activeColumn);
              const coarseRows: NormalizedBin[] = coarseBinResults[activeColumn] || [];
              const fineRowSource = fineBinResults[activeColumn];
              const fineRows: NormalizedBin[] =
                Array.isArray(fineRowSource) && fineRowSource.length > 0
                  ? fineRowSource
                  : coarseRows;
              const history = binMergeHistory[activeColumn] || {};
              const selectedLabels = selectedFineBins[activeColumn] || [];
              const selectedCount = selectedLabels.length;
              const woeStats: NormalizedBin[] = woeIvResults[activeColumn]?.stats || [];

              const metricsArray = binScoringMetrics[activeColumn] || [];
              const metricsAggregate = metricsArray.reduce(
                (acc, metric) => {
                  const g = Number(metric?.good_count ?? 0);
                  const b = Number(metric?.bad_count ?? 0);
                  acc.good += Number.isFinite(g) ? g : 0;
                  acc.bad += Number.isFinite(b) ? b : 0;
                  return acc;
                },
                { good: 0, bad: 0 }
              );

              const totalsRecord = binScoringTotals[activeColumn];
              const totalGoodForDerived = Number.isFinite(Number(totalsRecord?.total_good)) && totalsRecord?.total_good !== undefined
                ? Number(totalsRecord.total_good)
                : metricsAggregate.good;
              const totalBadForDerived = Number.isFinite(Number(totalsRecord?.total_bad)) && totalsRecord?.total_bad !== undefined
                ? Number(totalsRecord.total_bad)
                : metricsAggregate.bad;

              const computeDerivedStatsForCounts = (goodCount: number, badCount: number, totalCount: number) => {
                const safeGood = Number.isFinite(goodCount) ? goodCount : 0;
                const safeBad = Number.isFinite(badCount) ? badCount : 0;
                const safeTotal = Number.isFinite(totalCount) ? totalCount : safeGood + safeBad;

                const distGoodPct = totalGoodForDerived > 0 ? (safeGood / totalGoodForDerived) * 100 : 0;
                const distBadPct = totalBadForDerived > 0 ? (safeBad / totalBadForDerived) * 100 : 0;

                let woeValue = 0;
                let ivValue = 0;
                if (distGoodPct > 0 && distBadPct > 0) {
                  const ratio = distGoodPct / distBadPct;
                  const lnRatio = Math.log(ratio);
                  if (Number.isFinite(lnRatio)) {
                    const woeScaled = lnRatio * 100;
                    const ivRaw = ((distGoodPct - distBadPct) * lnRatio) / 100;
                    woeValue = Number(woeScaled.toFixed(1));
                    ivValue = Number(ivRaw.toFixed(4));
                  }
                }

                return {
                  goodCount: safeGood,
                  badCount: safeBad,
                  totalCount: safeTotal,
                  distGoodPct,
                  distBadPct,
                  woeValue,
                  ivValue,
                };
              };
              const standardizeKey = (value: string) => normalizeDisplayLabel(value).toLowerCase();

              const formatWoeKeyDisplay = (rawKey?: string | null) => {
                if (!rawKey) return '—';
                let working = String(rawKey).trim();
                const computedPrefix = working.startsWith('computed:');
                if (computedPrefix) {
                  working = working.slice('computed:'.length).trim();
                }
                const digitsOnly = working.match(/^\d+$/);
                if (digitsOnly) {
                  working = `Bin_${digitsOnly[0]}`;
                } else if (/^bin[\s_\-]*\d+$/i.test(working)) {
                  const match = working.match(/\d+/);
                  if (match) working = `Bin_${match[0]}`;
                } else if (working.includes(',')) {
                  const parts = working.split(',').map(p => p.trim()).filter(Boolean);
                  const normalized = parts.map(part => (part.match(/^\d+$/) ? `Bin_${part}` : part));
                  working = normalized.join('_');
                }
                return computedPrefix ? `computed:${working}` : working;
              };

              const woeLookup = (() => {
                const map = new Map<string, any>();
                const variantsFor = (raw: string) => {
                  const out = new Set<string>();
                  const s = String(raw).trim();
                  if (!s) return Array.from(out);
                  const base = s;
                  out.add(base);
                  // common variants: remove 'bin' prefix, replace underscores/spaces, numeric only
                  const noPrefix = base.replace(/^bin[\s_\-]*/i, '');
                  out.add(noPrefix);
                  out.add(base.replace(/[_\s\-]+/g, ' '));
                  out.add(base.replace(/[_\s\-]+/g, '_'));
                  out.add(base.replace(/[_\s\-]+/g, '-'));
                  // numeric-only variant if digits exist
                  const m = base.match(/(\d+)/);
                  if (m) out.add(m[1]);
                  return Array.from(out).map(x => standardizeKey(String(x)));
                };

                woeStats.forEach((row: NormalizedBin) => {
                  const candidates = [row.Bin, row.Range];
                  candidates.forEach((candidate) => {
                    if (candidate === null || candidate === undefined) return;
                    const variants = variantsFor(String(candidate));
                    variants.forEach(v => {
                      if (!map.has(v)) map.set(v, row);
                    });
                  });
                });
                return map;
              })();

              // Helper to find binScoringMetrics entry for a displayed label.
              // Handles merged labels like 'Bin_2_Bin_3' by splitting into components
              // and attempting to match by numeric parts or normalized equality.
              const findBinMetric = (labelRaw: any, labelDisplay?: string) => {
                const metrics = binScoringMetrics[activeColumn] || [];
                if (!metrics || metrics.length === 0) return null;
                const rawStr = String(labelRaw);
                // 1) exact match
                let m = metrics.find((mm: any) => String(mm.bin_name) === rawStr);
                if (m) return m;

                // 2) normalized key match
                const standardize = (v: string) => String(v).replace(/[_\s\-]+/g, ' ').trim().toLowerCase();
                const target = standardize(rawStr);
                m = metrics.find((mm: any) => standardize(String(mm.bin_name)) === target);
                if (m) return m;

                // 3) split merged labels into components and match by numeric parts
                const parts = rawStr.split(/[_\s,\-]+/).map(p => p.trim()).filter(Boolean);
                const numericParts = parts.flatMap(p => (p.match(/\d+/g) || []));
                if (numericParts.length > 0) {
                  // try to find a metric that contains all numericParts
                  m = metrics.find((mm: any) => {
                    const mmNums: string[] = (String(mm.bin_name).match(/\d+/g) || []) as string[];
                    return numericParts.every((np: string) => mmNums.includes(np));
                  });
                  if (m) return m;

                  // try partial match: any overlap
                  m = metrics.find((mm: any) => {
                    const mmNums: string[] = (String(mm.bin_name).match(/\d+/g) || []) as string[];
                    return numericParts.some((np: string) => mmNums.includes(np));
                  });
                  if (m) return m;
                }

                // 4) try matching by whether metric bin_name contains the display label
                if (labelDisplay) {
                  const disp = standardize(String(labelDisplay));
                  m = metrics.find((mm: any) => standardize(String(mm.bin_name)).includes(disp) || disp.includes(standardize(String(mm.bin_name))));
                  if (m) return m;
                }

                return null;
              };

              const getWoeRow = (label: string, range?: string, rawLabel?: any) => {
                if (!label && !range) return null;
                const tryKeys = (val?: string) => {
                  if (!val) return null;
                  const candidates = [] as string[];
                  const raw = String(val);
                  candidates.push(standardizeKey(raw));
                  // try removing common 'Bin' prefixes
                  candidates.push(standardizeKey(raw.replace(/^bin[\s_\-]*/i, '')));
                  // try numeric-only suffix
                  const m = raw.match(/(\d+)/);
                  if (m) candidates.push(standardizeKey(m[1]));
                  // try replacing underscores/spaces
                  candidates.push(standardizeKey(raw.replace(/[_\s\-]+/g, ' ')));
                  candidates.push(standardizeKey(raw.replace(/[_\s\-]+/g, '_')));
                  for (const k of candidates) {
                    const found = woeLookup.get(k);
                    if (found) return found;
                  }
                  return null;
                };

                // direct label match
                const direct = tryKeys(label);
                if (direct) return direct;
                // try range string
                const rangeMatch = tryKeys(range);
                if (rangeMatch) return rangeMatch;

                // fallback to scanning woeStats by normalized equality as last resort
                const scanned = woeStats.find((row: NormalizedBin) => {
                  const rowLabel = row.Bin ?? row.Range ?? '';
                  return normalizeDisplayLabel(String(rowLabel)) === normalizeDisplayLabel(label) ||
                    normalizeDisplayLabel(String(rowLabel)) === normalizeDisplayLabel(range || '');
                });
                if (scanned) return scanned;

                // absolute fallback: compute WOE/IV from binScoringMetrics when possible
                const metric = rawLabel !== undefined ? findBinMetric(rawLabel, label) : findBinMetric(label, label);
                const totals = binScoringTotals[activeColumn];
                if (metric && totals && (totals.total_good || totals.total_bad)) {
                  const goodValue = Number(metric.good_count || 0);
                  const badValue = Number(metric.bad_count || 0);
                  const totalValue = Number(metric.total_count || (goodValue + badValue));
                  const distGoodFrac = goodValue / Math.max(1, Number(totals.total_good));
                  const distBadFrac = badValue / Math.max(1, Number(totals.total_bad));
                  let woeVal = 0;
                  if (distGoodFrac > 0 && distBadFrac > 0) {
                    woeVal = Math.log(distGoodFrac / distBadFrac);
                  } else if (distGoodFrac > 0 && distBadFrac === 0) {
                    woeVal = Math.log(distGoodFrac / (1e-9));
                  } else if (distGoodFrac === 0 && distBadFrac > 0) {
                    woeVal = Math.log((1e-9) / distBadFrac);
                  }
                  const ivContribution = (distGoodFrac - distBadFrac) * woeVal;
                  const computedRow = {
                    WOE: woeVal,
                    IV: ivContribution,
                    'Dist_Good_%': distGoodFrac * 100,
                    'Dist_Bad_%': distBadFrac * 100,
                    Good: goodValue,
                    Bad: badValue,
                    Total: totalValue,
                    __computed: true
                  };
                  const key = standardizeKey(String(rawLabel ?? label));
                  if (!woeLookup.has(key)) {
                    woeLookup.set(key, computedRow);
                  }
                  return computedRow;
                }

                return null;
              };

              // Return the standardized key that matched in woeLookup (or null)
              const getMatchedKey = (label?: string, range?: string, rawLabel?: any) => {
                const tryKeys = (val?: string) => {
                  if (!val) return null;
                  const candidates = [] as string[];
                  const raw = String(val);
                  candidates.push(standardizeKey(raw));
                  candidates.push(standardizeKey(raw.replace(/^bin[\s_\-]*/i, '')));
                  const m = raw.match(/(\d+)/);
                  if (m) candidates.push(standardizeKey(m[1]));
                  candidates.push(standardizeKey(raw.replace(/[_\s\-]+/g, ' ')));
                  candidates.push(standardizeKey(raw.replace(/[_\s\-]+/g, '_')));
                  for (const k of candidates) {
                    if (woeLookup.has(k)) return k;
                  }
                  return null;
                };

                const d = tryKeys(label);
                if (d) return d;
                const r = tryKeys(range);
                if (r) return r;

                if (rawLabel !== undefined) {
                  const metric = findBinMetric(rawLabel, label);
                  const totals = binScoringTotals[activeColumn];
                  if (metric && totals && (totals.total_good || totals.total_bad)) {
                    return `computed:${standardizeKey(String(rawLabel))}`;
                  }
                }

                return null;
              };

              const pickNumeric = (...values: any[]) => {
                for (const value of values) {
                  if (value === null || value === undefined || value === '') continue;
                  const num = Number(value);
                  if (Number.isFinite(num)) {
                    return num;
                  }
                }
                return 0;
              };

              const getBinIdentifiers = (bin: NormalizedBin, idx: number) => {
                const raw = getBinLabelValue(bin, idx);
                const rangeValue = getRangeText(bin);
                return { labelValRaw: raw, labelVal: raw, rangeValue };
              };

              // === SORT BINS ===
              // === SORT BINS ===
              const sortedRows = [...fineRows].sort((a: NormalizedBin, b: NormalizedBin) => {
                // For discrete columns, sort by bin number (Bin_1, Bin_2, Bin_3, etc.)
                if (!isContinuousColumn) {
                  const labelA = getBinLabelValue(a, 0);
                  const labelB = getBinLabelValue(b, 0);

                  // Extract numeric parts from bin labels
                  const numA = getNumericOrderFromLabel(labelA);
                  const numB = getNumericOrderFromLabel(labelB);

                  // If both have numeric parts, sort numerically
                  if (numA !== null && numB !== null) {
                    return numA - numB;
                  }

                  // If only one has numeric part, put numeric first
                  if (numA !== null && numB === null) return -1;
                  if (numA === null && numB !== null) return 1;

                  // Fallback: alphabetical sort
                  return labelA.localeCompare(labelB);
                }

                // For continuous columns, use existing logic (sort by min value)
                const minA = getMinFromBin(a);
                const minB = getMinFromBin(b);
                if (!Number.isNaN(minA) && !Number.isNaN(minB)) {
                  return Number(minA) - Number(minB);
                }

                const labelA = getBinLabelValue(a, 0);
                const labelB = getBinLabelValue(b, 0);
                const numA = getNumericOrderFromLabel(labelA);
                const numB = getNumericOrderFromLabel(labelB);
                if (numA !== null && numB !== null) {
                  return numA - numB;
                }
                return labelA.localeCompare(labelB);
              });
              // === CHART DATA (WOE/IV from backend) ===
              const chartRows = sortedRows.map((bin: any, idx: number) => {
                const { labelValRaw, labelVal, rangeValue } = getBinIdentifiers(bin, idx);
                const woeData = getWoeRow(labelVal, rangeValue, labelValRaw) || {};

                // Prefer authoritative counts from binScoringMetrics when available
                const binMetrics = findBinMetric(labelValRaw, labelVal);
                const goodCount = binMetrics?.good_count ?? pickNumeric(woeData.Good, bin.Good, bin.good_count);
                const badCount = binMetrics?.bad_count ?? pickNumeric(woeData.Bad, bin.Bad, bin.bad_count);
                const totalCount = binMetrics?.total_count ?? pickNumeric(woeData.Total, bin.Total, bin.total_count, (goodCount + badCount));
                const derived = computeDerivedStatsForCounts(Number(goodCount), Number(badCount), Number(totalCount));

                return {
                  Bin: labelVal,
                  Range: rangeValue || (typeof woeData.Range === 'string' ? woeData.Range : ''),
                  WOE: derived.woeValue,
                  IV: derived.ivValue,
                  Good: derived.goodCount,
                  Bad: derived.badCount,
                  Total: derived.totalCount,
                };
              });

              return (
                <div className="binning-section" aria-label="Binning controls and results">
                  <div className="results-container">
                    <h3>Binning - {activeColumn}</h3>

                    <div className="table-container">
                      <table className="cross-tab-table" aria-label={`Fine binning workspace for ${activeColumn}`}>
                        <thead>
                          <tr>
                            <th>Select</th>
                            <th>Bin</th>
                            {isContinuousColumn ? (
                              <>
                                <th>Min</th>
                                <th>Max</th>
                              </>
                            ) : (
                              <th>Range</th>
                            )}
                            <th>0 (Good)</th>
                            <th>1 (Bad)</th>
                            <th>Total</th>
                            <th>0/1 (G/B)</th>
                            <th>Bad Rate (%)</th>
                            <th>Freq%</th>
                            <th>G/B Odd</th>
                            <th>Index</th>
                            <th>G/B Index</th>
                            <th>Dist Good (%)</th>
                            <th>Dist Bad (%)</th>
                            <th>WOE</th>
                            <th>IV</th>
                            <th>Actions</th>
                            <th>Metrics</th>
                          </tr>
                        </thead>
                        <tbody>
                          {sortedRows.length === 0 ? (
                            <tr>
                              <td colSpan={isContinuousColumn ? 17 : 16} style={{ textAlign: 'center', padding: '16px' }}>
                                No binning results available.
                              </td>
                            </tr>
                          ) : (
                            sortedRows.map((bin: NormalizedBin, idx: number) => {
                              const { labelValRaw, labelVal, rangeValue } = getBinIdentifiers(bin, idx);
                              const minVal = getMinFromBin(bin);
                              const maxVal = getMaxFromBin(bin);
                              const minDisplay = minVal !== null && minVal !== undefined ? minVal : (isContinuousColumn ? 'N/A' : '—');
                              const maxDisplay = maxVal !== null && maxVal !== undefined ? maxVal : (isContinuousColumn ? 'N/A' : '—');

                              const normalizedLabel = normalizeDisplayLabel(labelVal);
                              const rawWoe = getWoeRow(labelVal, rangeValue, labelValRaw) || getWoeRow(normalizedLabel, rangeValue, labelValRaw) || {};
                              const fallbackMetrics = findBinMetric(labelValRaw, labelVal);

                              const goodValue = pickNumeric(
                                fallbackMetrics?.good_count,
                                rawWoe.Good,
                                bin.Good,
                                bin.good_count
                              );
                              const badValue = pickNumeric(
                                fallbackMetrics?.bad_count,
                                rawWoe.Bad,
                                bin.Bad,
                                bin.bad_count
                              );
                              const totalValue = pickNumeric(
                                fallbackMetrics?.total_count,
                                rawWoe.Total,
                                bin.Total,
                                bin.total_count,
                                goodValue + badValue
                              );

                              const derived = computeDerivedStatsForCounts(Number(goodValue), Number(badValue), Number(totalValue));
                              const displayWoeData = {
                                ...rawWoe,
                                Good: derived.goodCount,
                                Bad: derived.badCount,
                                Total: derived.totalCount,
                                'Dist_Good_%': derived.distGoodPct,
                                'Dist_Bad_%': derived.distBadPct,
                                WOE: derived.woeValue,
                                IV: derived.ivValue,
                              };

                              const badRateRaw =
                                typeof bin['Bad Rate'] === 'number'
                                  ? bin['Bad Rate']
                                  : (typeof bin.bad_rate === 'number' ? bin.bad_rate : null);
                              const freqRaw =
                                typeof bin['Freq%'] === 'number'
                                  ? bin['Freq%']
                                  : (typeof bin.freq_percent === 'number' ? bin.freq_percent : null);

                              const isMergedLabel = Boolean(history[labelVal]);
                              const isSelected = selectedLabels.includes(labelVal);

                              // Build table cells programmatically to avoid accidental
                              // whitespace-only text nodes between JSX elements which
                              // can cause hydration errors when rendering <tr> children.
                              const cells: any[] = [];
                              // Checkbox cell
                              cells.push(
                                <td key={`chk-${labelVal}-${idx}`}>
                                  <input
                                    type="checkbox"
                                    checked={isSelected}
                                    onChange={(ev) => {
                                      ev.stopPropagation();
                                      toggleFineBinSelection(activeColumn, labelVal);
                                    }}
                                    aria-label={`Select bin ${labelVal} for ${activeColumn}`}
                                  />
                                </td>
                              );

                              // Label cell
                              cells.push(
                                <td key={`label-${labelVal}-${idx}`} title={rangeValue.length > 0 ? rangeValue : undefined} style={{ maxWidth: '160px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                                  {labelVal}
                                </td>
                              );

                              // Min/Max or Discrete dropdown
                              if (isContinuousColumn) {
                                cells.push(<td key={`min-${labelVal}-${idx}`}>{minDisplay}</td>);
                                cells.push(<td key={`max-${labelVal}-${idx}`}>{maxDisplay}</td>);
                              } else {
                                cells.push(
                                  <td key={`disc-${labelVal}-${idx}`}>
                                    <DiscreteValuesDropdown rangeValue={rangeValue} />
                                  </td>
                                );
                              }

                              // Good / Bad / Total
                              cells.push(<td key={`good-${labelVal}-${idx}`} style={{ color: 'green', fontWeight: 'bold' }}>{goodValue}</td>);
                              cells.push(<td key={`bad-${labelVal}-${idx}`} style={{ color: 'red', fontWeight: 'bold' }}>{badValue}</td>);
                              cells.push(<td key={`total-${labelVal}-${idx}`}>{totalValue}</td>);

                              // 0/1 Ratio
                              cells.push(
                                <td key={`ratio-${labelVal}-${idx}`}>
                                  {(() => {
                                    const binMetrics = findBinMetric(labelValRaw, labelVal);
                                    return binMetrics?.zero_one_ratio || '—';
                                  })()}
                                </td>
                              );

                              // Bad Rate and Freq
                              cells.push(<td key={`br-${labelVal}-${idx}`}>{badRateRaw !== null && badRateRaw !== undefined ? badRateRaw.toFixed(4) : '0.0000'}</td>);
                              cells.push(<td key={`freq-${labelVal}-${idx}`}>{freqRaw !== null && freqRaw !== undefined ? freqRaw.toFixed(2) : '0.00'}</td>);

                              // G/B Odd
                              cells.push(
                                <td key={`gbodd-${labelVal}-${idx}`}>
                                  {(() => {
                                    const binMetrics = findBinMetric(labelValRaw, labelVal);
                                    return binMetrics?.gb_odd || '—';
                                  })()}
                                </td>
                              );

                              // G/B Index
                              cells.push(
                                <td key={`gbindex-${labelVal}-${idx}`}>
                                  {(() => {
                                    const binMetrics = findBinMetric(labelValRaw, labelVal);
                                    return (
                                      <span style={{
                                        color: binMetrics?.gb_index === 'G' ? 'green' : 'red',
                                        fontWeight: 'bold'
                                      }}>
                                        {binMetrics?.gb_index || '—'}
                                      </span>
                                    );
                                  })()}
                                </td>
                              );

                              // Combined Index
                              cells.push(
                                <td key={`combined-${labelVal}-${idx}`}>
                                  {(() => {
                                    const binMetrics = findBinMetric(labelValRaw, labelVal);
                                    return (
                                      <span style={{
                                        color: binMetrics?.gb_index === 'G' ? 'green' : 'red',
                                        fontWeight: 'bold'
                                      }}>
                                        {binMetrics?.combined_index || '—'}
                                      </span>
                                    );
                                  })()}
                                </td>
                              );

                              // Dist Good/Bad, WOE, IV
                              cells.push(<td key={`distgood-${labelVal}-${idx}`}>{formatToFourDecimals(displayWoeData['Dist_Good_%'] || 0)}</td>);
                              cells.push(<td key={`distbad-${labelVal}-${idx}`}>{formatToFourDecimals(displayWoeData['Dist_Bad_%'] || 0)}</td>);
                              cells.push(<td key={`woe-${labelVal}-${idx}`}>{formatToFourDecimals(displayWoeData.WOE || 0)}</td>);
                              cells.push(<td key={`iv-${labelVal}-${idx}`}>{formatToFourDecimals(displayWoeData.IV || 0)}</td>);

                              const matchedKey = getMatchedKey(labelVal, rangeValue, labelValRaw);
                              const metricsBin = fallbackMetrics; // reuse previously resolved metric
                              const displayMatchedKey = matchedKey ? formatWoeKeyDisplay(matchedKey) : '—';
                              const displayMetricName = metricsBin?.bin_name ? formatWoeKeyDisplay(String(metricsBin.bin_name)) : '—';

                              // Actions cell (Unmerge)
                              cells.push(
                                <td key={`actions-${labelVal}-${idx}`}>
                                  {isMergedLabel ? (
                                    <button
                                      className="unmerge-btn compact"
                                      onClick={() => unmergeFineBin(activeColumn, labelVal)}
                                      aria-label={`Unmerge ${labelVal}`}
                                      title="Unmerge"
                                    >
                                      <span style={{ fontSize: '12px', fontWeight: 600, padding: '2px 8px', borderRadius: '6px', background: 'var(--bg-quaternary)', color: 'var(--fg-accent-red)', border: '1px solid var(--border-secondary)', boxShadow: 'var(--shadow-light)', transition: 'all 0.2s' }}>
                                        Unmerge
                                      </span>
                                    </button>
                                  ) : null}
                                </td>
                              );

                              // Metrics summary (woeKey, matched metric, Dist Good %)
                              cells.push(
                                <td key={`metrics-${labelVal}-${idx}`} style={{ fontSize: '11px', whiteSpace: 'nowrap' }}>
                                  <div>
                                    <div style={{ color: matchedKey ? '#9ae6b4' : '#fca5a5' }}><strong>woeKey:</strong> {displayMatchedKey}</div>
                                    <div style={{ color: metricsBin ? '#c7d2fe' : '#fef3c7' }}><strong>metric:</strong> {displayMetricName}</div>
                                  </div>
                                </td>
                              );

                              return (
                                <tr
                                  key={`${labelVal}-${idx}`}
                                  className={`bin-row ${isSelected ? 'selected' : ''}`}
                                  style={{ backgroundColor: isMergedLabel ? 'var(--merged-bin-bg, #21262d)' : 'transparent' }}
                                  role="button"
                                  tabIndex={0}
                                  onClick={(e) => {
                                    const target = e.target as HTMLElement;
                                    if (target.closest('button') || target.closest('input') || target.closest('a')) return;
                                    toggleFineBinSelection(activeColumn, labelVal);
                                  }}
                                  onKeyDown={(e) => {
                                    if (e.key === 'Enter' || e.key === ' ') {
                                      const target = e.target as HTMLElement;
                                      if (target.closest('button') || target.closest('input') || target.closest('a')) return;
                                      e.preventDefault();
                                      toggleFineBinSelection(activeColumn, labelVal);
                                    }
                                  }}
                                >
                                  {cells}
                                </tr>
                              );
                            })
                          )}
                        </tbody>
                        {/* === TOTALS ROW (Use authoritative data from backend) === */}
                        <tfoot>
                          {(() => {
                            // Calculate totals from authoritative backend data
                            let totalBad = 0;
                            let totalGood = 0;
                            let totalTotal = 0;
                            let sumFreq = 0;
                            let freqProvided = false;

                            let totalIvContribution = 0;
                            sortedRows.forEach((bin: any, idx: number) => {
                              const { labelValRaw, labelVal, rangeValue } = getBinIdentifiers(bin, idx);

                              const binMetrics = findBinMetric(labelValRaw, labelVal);
                              const woeTotalsRow = getWoeRow(labelVal, rangeValue, labelValRaw);

                              const good = Number(
                                binMetrics?.good_count ??
                                woeTotalsRow?.Good ??
                                0
                              );
                              const bad = Number(
                                binMetrics?.bad_count ??
                                woeTotalsRow?.Bad ??
                                0
                              );
                              const total = Number(
                                binMetrics?.total_count ??
                                woeTotalsRow?.Total ??
                                good + bad
                              );

                              const derived = computeDerivedStatsForCounts(good, bad, total);

                              totalBad += derived.badCount;
                              totalGood += derived.goodCount;
                              totalTotal += derived.totalCount;
                              totalIvContribution += derived.ivValue;

                              const freq = typeof bin['Freq%'] === 'number' ? bin['Freq%'] : (typeof bin.Freq === 'number' ? bin.Freq : null);
                              if (freq !== null) {
                                sumFreq += freq;
                                freqProvided = true;
                              }
                            });

                            const badRatePercent = totalTotal > 0 ? (totalBad / totalTotal) * 100 : 0;
                            const freqPercent = freqProvided ? sumFreq : (totalTotal > 0 ? 100 : 0);

                            // Calculate overall 0/1 ratio (Good/Bad)
                            const overallZeroOneRatio = totalBad > 0 ? totalGood / totalBad : 'Inf';
                            const totalIv = Number(totalIvContribution.toFixed(4));

                            return (
                              <tr className="totals-row">
                                <td><strong>Total</strong></td>
                                <td />
                                {isContinuousColumn ? (
                                  <>
                                    <td />
                                    <td />
                                  </>
                                ) : (
                                  <td />
                                )}
                                <td style={{ color: 'green', fontWeight: 'bold' }}>{totalGood}</td>
                                <td style={{ color: 'red', fontWeight: 'bold' }}>{totalBad}</td>
                                <td>{totalTotal}</td>
                                <td>{overallZeroOneRatio === 'Inf' ? 'Inf' : overallZeroOneRatio.toFixed(4)}</td>
                                <td>{badRatePercent.toFixed(2)}</td>
                                <td>{freqPercent.toFixed(2)}</td>

                                {/* 3 empty cells for G/B Odd, G/B Index, and Index */}
                                <td />
                                <td />
                                <td />

                                <td />
                                <td />
                                <td />
                                <td className="iv-total">{formatToFourDecimals(totalIv)}</td>
                                <td />
                                <td />
                              </tr>
                            );
                          })()}
                        </tfoot>
                      </table>
                    </div>

                    <div className="binning-controls">
                      <button
                        className="fine-bin-btn"
                        onClick={() => runBinning(activeColumn)}
                        aria-label={`Run binning for ${activeColumn}`}
                        disabled={selectedCount < 2}
                        title={selectedCount < 2 ? 'Select at least two bins to merge' : undefined}
                      >
                        Fine Binning on Selected
                      </button>
                      <button
                        className="auto-monotonic-btn"
                        onClick={() => runAutoMonotonicBinning(activeColumn)}
                        aria-label={`Run auto-monotonic binning for ${activeColumn}`}
                        title="Automatically merge bins to achieve monotonic WOE trend"
                      >
                        <span className="btn-icon">⚡</span>
                        Auto Monotonic Binning
                      </button>
                      <button
                        className="reset-bin-btn"
                        onClick={() => resetFineBinning(activeColumn)}
                        aria-label={`Reset binning for ${activeColumn}`}
                      >
                        Reset Binning
                      </button>
                    </div>
                  </div>

                  {/* WOE/IV Charts */}
                  {woeIvResults[activeColumn] && (
                    <div className="woe-iv-embedded" style={{ marginTop: '24px' }}>
                      <h3>WOE by Bin</h3>
                      <ResponsiveContainer width="100%" height={300}>
                        <LineChart data={chartRows} margin={{ top: 20, right: 30, bottom: 40, left: 0 }}>
                          <CartesianGrid strokeDasharray="3 3" />
                          <XAxis dataKey="Bin" angle={-30} textAnchor="end" interval={0} />
                          <YAxis />
                          <Tooltip />
                          <Legend />
                          <Line type="monotone" dataKey="WOE" stroke="#39ff14" strokeWidth={2} dot={{ r: 3, fill: '#39ff14' }} />
                        </LineChart>
                      </ResponsiveContainer>

                      <h3 style={{ marginTop: '20px' }}>IV Contribution by Bin</h3>
                      <ResponsiveContainer width="100%" height={300}>
                        <BarChart data={chartRows} margin={{ top: 20, right: 30, bottom: 40, left: 0 }}>
                          <CartesianGrid strokeDasharray="3 3" />
                          <XAxis dataKey="Bin" angle={-30} textAnchor="end" interval={0} />
                          <YAxis />
                          <Tooltip />
                          <Bar dataKey="IV" fill="#8884d8" />
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  )}
                </div>
              );
            })()}
            {currentStep === 3 && (
              <div className="model-selection">
                <h3>Model Selection</h3>
                <div className="model-buttons">
                  <button
                    className={`model-btn ${selectedModel === 'logistic' ? 'active' : ''}`}
                    onClick={() => setSelectedModel('logistic')}
                  >
                    Logistic Regression
                  </button>
                  <button
                    className={`model-btn ${selectedModel === 'random_forest' ? 'active' : ''}`}
                    onClick={() => setSelectedModel('random_forest')}
                  >
                    Random Forest
                  </button>
                  <button
                    className={`model-btn ${selectedModel === 'xgboost' ? 'active' : ''}`}
                    onClick={() => setSelectedModel('xgboost')}
                  >
                    XGBoost
                  </button>
                </div>

                {selectedModel === 'logistic' && (
                  <LogisticRegressionResults
                    selectedVariables={currentStep === 3 && selectedForFinalModeling.length > 0 ? selectedForFinalModeling : selectedForModeling}
                    allSelectedVariables={selectedColumns}
                    targetVariable={targetVariable}
                    woeTransformedData={Object.fromEntries(
                      Object.entries(woeIvResults).map(([key, value]) => [key, value.stats || []])
                    )}
                    onColumnSelect={(column) => setActiveColumn(column)}
                    onToggleSelect={toggleSelectedForFinalModeling}
                    selectedColumn={activeColumn}
                    onGenerateScoreCard={(modelType) => {
                      setSelectedModelForScorecard(modelType);
                      gotoScoreCardAndGenerate();
                    }}
                    generatingScoreCard={generatingScoreCard}
                    onGotoScoreCard={gotoScoreCardAndGenerate}
                    onResultsUpdate={handleLogisticResults}
                    recordId={recordId}
                  />
                )}

                {selectedModel === 'random_forest' && (
                  <RandomForestResults
                    selectedVariables={currentStep === 3 && selectedForFinalModeling.length > 0 ? selectedForFinalModeling : selectedForModeling}
                    allSelectedVariables={selectedColumns}
                    targetVariable={targetVariable}
                    woeTransformedData={Object.fromEntries(
                      Object.entries(woeIvResults).map(([key, value]) => [key, value.stats || []])
                    )}
                    onColumnSelect={(column) => setActiveColumn(column)}
                    onToggleSelect={toggleSelectedForFinalModeling}
                    selectedColumn={activeColumn}
                    onGenerateScoreCard={(modelType) => {
                      setSelectedModelForScorecard(modelType);
                      gotoScoreCardAndGenerate();
                    }}
                    generatingScoreCard={generatingScoreCard}
                    onGotoScoreCard={gotoScoreCardAndGenerate}
                    onResultsUpdate={handleRandomForestResults}
                    recordId={recordId}
                  />
                )}

                {selectedModel === 'xgboost' && (
                  <XGBoostResults
                    selectedVariables={currentStep === 3 && selectedForFinalModeling.length > 0 ? selectedForFinalModeling : selectedForModeling}
                    allSelectedVariables={selectedColumns}
                    targetVariable={targetVariable}
                    woeTransformedData={Object.fromEntries(
                      Object.entries(woeIvResults).map(([key, value]) => [key, value.stats || []])
                    )}
                    onColumnSelect={(column) => setActiveColumn(column)}
                    onToggleSelect={toggleSelectedForFinalModeling}
                    selectedColumn={activeColumn}
                    onGenerateScoreCard={(modelType) => {
                      setSelectedModelForScorecard(modelType);
                      gotoScoreCardAndGenerate();
                    }}
                    generatingScoreCard={generatingScoreCard}
                    onGotoScoreCard={gotoScoreCardAndGenerate}
                    onResultsUpdate={handleXGBoostResults}
                    recordId={recordId}
                  />
                )}
              </div>
            )}
            {currentStep === 4 && (
              <div className="scorecard-section">
                <h3>Score Card</h3>
                {/* Model Selection for Score Card */}
                <div className="scorecard-model-selection" style={{ marginBottom: '16px' }}>
                  <label htmlFor="scorecard-model-select">Select Model for Score Card: </label>
                  <select
                    id="scorecard-model-select"
                    value={selectedModelForScorecard}
                    onChange={(e) => setSelectedModelForScorecard(e.target.value)}
                    style={{ marginLeft: '8px', padding: '4px 8px' }}
                  >
                    <option value="logistic">Logistic Regression</option>
                    <option value="random_forest">Random Forest</option>
                    <option value="xgboost">XGBoost</option>
                  </select>
                </div>

                <div className="scorecard-controls">
                  <button
                    className="run-regression-btn"
                    onClick={generateScoreCard}
                    disabled={generatingScoreCard || selectedForModeling.length === 0}
                    aria-label="Generate score card"
                  >
                    {generatingScoreCard ? 'Generating...' : 'Generate Score Card'}
                  </button>
                </div>
                {/* Show loading skeleton while generating */}
                {generatingScoreCard && (
                  <div className="scorecard-results-loading">
                    <h4>Score Card Results</h4>
                    <div className="scorecard-loading-skeleton">
                      <div className="skeleton-header" />
                      <div className="skeleton-row" />
                      <div className="skeleton-row" />
                      <div className="skeleton-row" />
                    </div>
                  </div>
                )}

                {/* Only show results when not generating and scoreCardData is loaded */}
                {scoreCardData && !generatingScoreCard && (
                  <div className="scorecard-results">
                    <h4>Score Card Results (Based on {selectedModelForScorecard} model)</h4>
                    <div className="table-container">
                      <table className="scorecard-table" aria-label="Score card results">
                        <thead>
                          <tr>
                            <th>Bin #</th>
                            <th>Variable</th>
                            <th>Bin Range</th>
                            <th>WOE</th>
                            <th>
                              {selectedModelForScorecard === 'logistic'
                                ? 'Coefficient (β)'
                                : 'Feature Importance'}
                            </th>
                            <th>Score</th>
                          </tr>
                        </thead>
                        <tbody>
                          {scoreCardData.scorecard_bins && (() => {
                            const grouped: Record<string, any[]> = {};
                            const varsToUse = selectedForFinalModeling.length > 0 ? selectedForFinalModeling : selectedForModeling;
                            scoreCardData.scorecard_bins.forEach((b: any) => {
                              if (varsToUse.includes(b.variable)) {
                                grouped[b.variable] = grouped[b.variable] || [];
                                grouped[b.variable].push(b);
                              }
                            });
                            const rows: any[] = [];
                            Object.keys(grouped).forEach((variable, varIndex) => {
                              const bins = grouped[variable];
                              if (varIndex > 0) {
                                rows.push(
                                  <tr key={`sep-${variable}`} className="variable-separator">
                                    <td colSpan={6} />
                                  </tr>
                                );
                              }
                              for (let i = 0; i < bins.length; i++) {
                                const bin = bins[i];
                                rows.push(
                                  <tr key={`${variable}-${i}-${String(bin.bin_range)}`}>
                                    <td>{i + 1}</td>
                                    <td>{bin.variable}</td>
                                    <td>{bin.bin_range}</td>
                                    <td>{formatToFourDecimals(bin.woe)}</td>
                                    <td>
                                      {selectedModelForScorecard === 'logistic'
                                        ? formatToFourDecimals(bin.coefficient)
                                        : formatToFourDecimals(bin.feature_importance)
                                      }
                                    </td>
                                    <td>{Math.round(bin.score)}</td>
                                  </tr>
                                );
                              }
                            });
                            return rows;
                          })()}
                        </tbody>
                      </table>
                    </div>
                    {scoreCardData.score_parameters && (
                      <div className="score-parameters">
                        <h5>Score Card Parameters</h5>
                        <div className="parameters-grid">
                          <div className="parameter-item">
                            <label>Factor:</label>
                            <span>{formatToFourDecimals(scoreCardData.score_parameters.factor)}</span>
                          </div>
                          <div className="parameter-item">
                            <label>Offset:</label>
                            <span>{formatToFourDecimals(scoreCardData.score_parameters.offset)}</span>
                          </div>
                          <div className="parameter-item">
                            <label>Base Score (600 points):</label>
                            <span>Good/Bad Odds 50:1</span>
                          </div>
                          <div className="parameter-item">
                            <label>Score Range:</label>
                            <span>{scoreCardData.score_parameters.min_score} - {scoreCardData.score_parameters.max_score}</span>
                          </div>
                          <div className="parameter-item">
                            <label>Model Type:</label>
                            <span>{selectedModelForScorecard.toUpperCase()}</span>
                          </div>
                        </div>
                      </div>
                    )}
                    {/* Test Score Button and Results Table */}
                    <div style={{ marginTop: '32px' }}>
                      <div style={{ marginBottom: '16px' }}>
                        <button
                          className="run-regression-btn"
                          onClick={() => handleTestScoreCard(selectedModelForScorecard)}
                          disabled={testScoreLoading}
                          aria-label="Test Score Card on Data"
                        >
                          {testScoreLoading ? 'Testing...' : `Test Score Card (${selectedModelForScorecard})`}
                        </button>
                      </div>

                      {testScoreResults && (
                        <div className="scorecard-test-results">
                          <h5>Score Card Test Results - {selectedModelForScorecard.toUpperCase()} Model (Sorted by Score)</h5>
                          {testScoreKS !== null && (
                            <div style={{ marginBottom: '12px', fontWeight: 'bold' }}>
                              Separation Number (KS Statistic): {testScoreKS.toFixed(4)}
                            </div>
                          )}
                          <div className="table-container">
                            <table className="scorecard-table" aria-label="Score card test results">
                              <thead>
                                <tr>
                                  <th>#</th>
                                  <th>Score</th>
                                  <th>Target</th>
                                </tr>
                              </thead>
                              <tbody>
                                {testScoreResults.map((row: any, idx: number) => (
                                  <tr key={idx}>
                                    <td>{idx + 1}</td>
                                    <td>{row.score}</td>
                                    <td style={{
                                      color: row.target === 0 ? 'green' : row.target === 1 ? 'red' : undefined,
                                      fontWeight: row.target === 1 ? 'bold' : 'normal'
                                    }}>
                                      {row.target}
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            )}
          </section>
        </div >
        {/* Footer navigation removed per request: Next and Save moved beside progress bar */}

        {/* Auto Binning Mode Loading Overlay */}
        {autoBinningModeLoading && (
          <div className="auto-binning-loading-overlay">
            <div className="auto-binning-loading-modal">
              <div className="loading-animation">
                <div className="pulse-ring"></div>
                <div className="pulse-ring-delay"></div>
                <div className="loading-icon">📊</div>
              </div>
              <h3 className="loading-title">Loading Auto Binning</h3>
              <p className="loading-progress">{autoBinningModeProgress}</p>
              <div className="progress-bar-container">
                <div
                  className="progress-bar-fill"
                  style={{ width: `${autoBinningModePercentage}%` }}
                ></div>
              </div>
              <p className="loading-subtitle">
                {autoBinningModePercentage > 0 && autoBinningModePercentage < 100
                  ? 'Processing features...'
                  : 'Please wait while we load all features...'}
              </p>
            </div>
          </div>
        )}
        {fullAutoMonotonicLoading && (
          <div className="full-auto-overlay">
            <div className="full-auto-modal">
              <div className="full-auto-animation">
                <span className="full-auto-icon">⚡</span>
              </div>
              <h3 className="loading-title">Full Auto Monotonic</h3>
              <p className="loading-progress">
                {fullAutoMonotonicProgress}
                {fullAutoMonotonicCurrent ? ` • ${fullAutoMonotonicCurrent}` : ''}
              </p>
              <div className="progress-bar-container full-auto">
                <div
                  className="progress-bar-fill full-auto"
                  style={{ width: `${fullAutoMonotonicPercentage}%` }}
                ></div>
              </div>
              <p className="loading-subtitle">
                {fullAutoMonotonicPercentage < 100
                  ? 'Applying monotonic binning across all features...'
                  : 'All features processed.'}
              </p>
            </div>
          </div>
        )}
      </div >
    </div >
  );
};
export default SelectedColumnsPage;
