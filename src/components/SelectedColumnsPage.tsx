import { useLocation } from 'react-router-dom';
import { useEffect, useState, useRef } from 'react';
import LogisticRegressionResults from './LogisticRegressionResults';
import Navbar from './Navbar';
import RandomForestResults from './RandomForestResults';
import XGBoostResults from './XGBoostResults';
import { DiscreteValuesDropdown } from './DiscreteValues';
// import WoeIvResults from './WoeIvResults';
import './SelectedColumnsPage.css';
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
    discreteColumns,
    continuousColumns,
    targetVariable,
    recordId: initialRecordId,
  } = state || {};
  // State declarations
  const [selectedColumns, setSelectedColumns] = useState<string[]>(navSelectedColumns || []);
  const [activeColumn, setActiveColumn] = useState<string>('');
  const [currentStep, setCurrentStep] = useState(1);
  const [univariateResults, setUnivariateResults] = useState<Record<string, any>>({});
  const [coarseBinResults, setCoarseBinResults] = useState<Record<string, any[]>>({});
  const [fineBinResults, setFineBinResults] = useState<Record<string, any[]>>({});
  const [selectedFineBins, setSelectedFineBins] = useState<Record<string, string[]>>({});
  const [binMergeHistory, setBinMergeHistory] = useState<Record<string, Record<string, any[]>>>({});
  const [recordId, setRecordId] = useState<number | undefined>(initialRecordId);
  const [woeIvResults, setWoeIvResults] = useState<Record<string, any>>({});
  const woeIvResultsRef = useRef<Record<string, any>>({});
  const [woeReadyColumns, setWoeReadyColumns] = useState<Set<string>>(new Set());
  const [selectedForModeling, setSelectedForModeling] = useState<string[]>([]);
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

  // Update your model components to pass these handlers
  const filteredColumns = selectedColumns
    .filter(col => col.toLowerCase().includes(searchTerm.toLowerCase()))
    .sort((a, b) => a.localeCompare(b));
  // Recommend functionality removed (UI buttons removed per request)
  // Initialize component state from navigation state
  useEffect(() => {
    if (!state) return;
    const anyUnivariate = (state as any).univariateResults;
    const anyFine = (state as any).fineBinResults;
    const anyCross = (state as any).crossTabResults || (state as any).crosstab_results;
    const anyWoe = (state as any).woeIvResults || (state as any).woe_iv_results;
    if (anyUnivariate) setUnivariateResults(anyUnivariate);
    if (anyFine) setFineBinResults(anyFine);
    if (anyCross) setCoarseBinResults(anyCross);
    if (anyWoe) {
      setWoeIvResults(anyWoe);
      setWoeReadyColumns(new Set(Object.keys(anyWoe)));
    }
    if (navSelectedColumns) setSelectedColumns(navSelectedColumns);
    if ((state as any).recordId) setRecordId((state as any).recordId);
  }, [state]);
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
  // Utility functions

  // Calculate metrics for all bins of a column
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
          selected_variables: selectedForModeling,
          target: targetVariable,
          woe_transformed_data: woeIvResults,
          model_results: modelResults,
          model_type: modelType
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
  const calculateAllBinMetrics = async (columnName: string, bins: any[]) => {
    try {
      const binsData = bins.map(bin => {
        const good = bin.Good || bin.good || 0;
        const bad = bin.Bad || bin.bad || 0;
        const total = bin.Total || bin.total || (good + bad);
        const binRange = bin.Range || bin.range || '';

        // Use the same bin identifier that will be used in the table
        const binName = bin[`${columnName}_fine_binned`] || bin[`${columnName}_binned`] || bin.Bin || bin.bin || 'Unknown';

        return {
          bin_name: String(binName), // Ensure it's a string
          bin_range: binRange,
          good_count: good,
          bad_count: bad,
          total_count: total
        };
      });

      
      const response = await fetch('http://localhost:5000/api/calculate-bin-metrics', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ bins: binsData })
      });

      // Some backend responses may include non-standard tokens (Infinity, -Infinity, NaN)
      // which JSON.parse in the browser will reject. Read as text first and sanitize
      // those tokens before parsing.
    const text = await response.text();
      let data: any;
      try {
        data = JSON.parse(text);
      } catch (parseErr) {
        try {
          const sanitized = text
            // unquoted Infinity/-Infinity/NaN (common from some JSON serializers)
            .replace(/:\s*Infinity(,|\s|})/g, ': null$1')
            .replace(/:\s*-Infinity(,|\s|})/g, ': null$1')
            .replace(/:\s*NaN(,|\s|})/g, ': null$1');
          data = JSON.parse(sanitized);
        } catch (e2) {
          
          return null;
        }
      }
      
      if (data.success) {
        setBinScoringMetrics(prev => ({
          ...prev,
          [columnName]: data.bin_metrics
        }));
        // Save totals if provided by backend
        setBinScoringTotals(prev => ({
          ...prev,
          [columnName]: {
            total_good: Number(data.total_good ?? 0),
            total_bad: Number(data.total_bad ?? 0),
            total_zero_one_ratio: data.total_zero_one_ratio
          }
        }));
        return data.bin_metrics;
      } else {
        
        return null;
      }
    } catch (error) {
      
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
        const firstBinLabel = firstBin[`${activeColumn}_fine_binned`] || firstBin[`${activeColumn}_binned`] || firstBin.Bin || firstBin.bin;
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

      const response = await fetch('http://localhost:5000/api/generate-scorecard', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          selected_variables: selectedForModeling,
          target: targetVariable,
          woe_transformed_data: woeIvResults,
          model_type: selectedModelForScorecard,
          model_results: modelResults
        })
      });

      const data = await response.json();
      if (data.success) {
        setScoreCardData(data);
        if (data.scorecard_bins) {
          const totalBins = data.scorecard_bins.length;
          const variableCounts = selectedForModeling.map(variable => {
            const variableBins = data.scorecard_bins.filter((bin: any) => bin.variable === variable);
            return { variable, count: variableBins.length };
          });
          showNotification(`Score card generated with ${totalBins} bins across ${selectedForModeling.length} variables using ${selectedModelForScorecard} model`);
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
    setCurrentStep(3);
    setTimeout(() => {
      generateScoreCard();
    }, 50);
  };
  // API calls
  const loadSavedFineBins = async (col: string, varType: string): Promise<{ merges: Record<string, any[]> | undefined }> => {
    if (!recordId) return { merges: undefined };
    try {
      const resp = await fetch(`http://localhost:5000/api/finebin-details/${recordId}/${encodeURIComponent(col)}`);
      const details = await resp.json();
      if (!Array.isArray(details) || details.length === 0) {
        return { merges: undefined };
      }
      const savedMerges: Record<string, any[]> = {};
      details.forEach((row: any) => {
        let bins: any[];
        try {
          bins = JSON.parse(row.merged_bins);
        } catch {
          bins = [];
        }
        if (bins && bins.length > 0) {
          savedMerges[row.group_id] = bins;
        }
      });
      if (Object.keys(savedMerges).length === 0) {
        return { merges: undefined };
      }
      const res = await fetch('http://localhost:5000/api/fine-bin', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          variable: col,
          target: targetVariable,
          type: varType,
          bin_merges: savedMerges,
          record_id: recordId,
          // Pass current dashboard selections so backend doesn't wipe them
          dashboard_selected_columns: Array.from(selectedForModeling),
        }),
      });
      const data = await res.json();
      if (data.success && !data.error) {
        setFineBinResults((prev) => ({ ...prev, [col]: data.stats || [] }));
        // Recompute scoring metrics for the restored bins
        try {
          await calculateAllBinMetrics(col, data.stats || []);
        } catch (e) {
          
        }
        setBinMergeHistory((prev) => ({ ...prev, [col]: data.bin_merges || savedMerges }));
        setSelectedFineBins((prev) => ({ ...prev, [col]: [] }));
        return { merges: data.bin_merges || savedMerges };
      } else {
        
      }
    } catch (e) {
      
    }
    return { merges: undefined };
  };
  const loadSavedData = async () => {
    if (!recordId) return;
    try {
      const recordResp = await fetch(`http://localhost:5000/api/record/${recordId}`);
      const recordData = await recordResp.json();
      
      if (recordData.woe_iv_results) {
        setWoeIvResults(recordData.woe_iv_results);
        const readyColumns = new Set(Object.keys(recordData.woe_iv_results));
        setWoeReadyColumns(readyColumns);
      }
      if (recordData.selected_columns) {
        setSelectedColumns(recordData.selected_columns.split(','));
      }
      // Restore dashboard checkbox selection (supports string CSV or JSON array)
      if (recordData.dashboard_selected_columns !== undefined && recordData.dashboard_selected_columns !== null) {
        let restoredArr: string[] = [];
        try {
          if (Array.isArray(recordData.dashboard_selected_columns)) {
            restoredArr = recordData.dashboard_selected_columns.map((s: any) => String(s).trim()).filter((s: string) => s);
          } else if (typeof recordData.dashboard_selected_columns === 'string') {
            const raw = recordData.dashboard_selected_columns.trim();
            if (raw.startsWith('[')) {
              // JSON array stored as text
              const parsed = JSON.parse(raw);
              restoredArr = Array.isArray(parsed) ? parsed.map((s: any) => String(s).trim()).filter((s: string) => s) : [];
            } else {
              restoredArr = raw.split(',').map((s: string) => s.trim()).filter((s: string) => s);
            }
          }
        } catch (e) {
          
        }
        
        setSelectedForModeling(restoredArr);
      }
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
      const coarseStats = data[col]?.stats || [];
      setUnivariateResults((prev) => ({ ...prev, [col]: data[col] || data }));
      setCoarseBinResults((prev) => ({ ...prev, [col]: coarseStats }));
      setFineBinResults((prev) => ({ ...prev, [col]: coarseStats }));
      // Precompute bin scoring metrics for the initial fine/coarse bins
      try {
        await calculateAllBinMetrics(col, coarseStats || []);
      } catch (e) {
        
      }
      setBinMergeHistory((prev) => ({ ...prev, [col]: prev[col] || {} }));
      setSelectedFineBins((prev) => ({ ...prev, [col]: [] }));
      // Load any saved fine bins but do NOT auto-select the column for modeling when clicking the card
      const { merges } = await loadSavedFineBins(col, varType);
      const mergePayload = merges && Object.keys(merges).length > 0 ? merges : undefined;
      
      const updatedWoe = await fetchWoeIv(col, mergePayload, false);
      
      if (updatedWoe) {
        setWoeReadyColumns((prev) => new Set(prev).add(col));
      }
    } catch {
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
    const selectedLabels = Array.from(new Set((selectedFineBins[col] || []).map(String)));
    const history = binMergeHistory[col] || {};

    if (selectedLabels.length < 2) {
      showNotification('Select at least two bins to merge.');
      return;
    }

    // Expand selected labels using history
    const expandedSelection = Array.from(new Set(
      selectedLabels.flatMap(label => {
        const underlying = history[label];
        return Array.isArray(underlying) ? underlying.map(String) : [label];
      })
    ));

    // Remove any old merges that overlap
    const filteredHistoryEntries = Object.entries(history).filter(([, bins]) => {
      return !bins.some(b => expandedSelection.includes(String(b)));
    });
    const filteredHistory = Object.fromEntries(filteredHistoryEntries);

    // Create merge key
    const sortedExpanded = [...expandedSelection].sort((a, b) => a.localeCompare(b));
    const mergeKey = varType === 'continuous'
      ? `Merged_${Object.keys(filteredHistory).length + 1}`
      : sortedExpanded.join(', ');  // This is critical for discrete!

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
        }),
      });
      const coarseData = await coarseRes.json();
      const coarseStats = coarseData[col]?.stats || [];
      const updatedUnivariate = { ...univariateResults, [col]: coarseData[col] || coarseData };
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
      const updatedFine = { ...fineBinResults, [col]: fineData.stats || [] };
      const updatedHistory = { ...binMergeHistory, [col]: mergesReturned };
      setFineBinResults(updatedFine);
      setBinMergeHistory(updatedHistory);
      setSelectedFineBins(prev => ({ ...prev, [col]: [] }));

      // Recalculate bin scoring metrics (G/B odd, index, combined index, etc.) for the updated bins
      try {
        await calculateAllBinMetrics(col, fineData.stats || []);
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
      showNotification(`Binning completed for ${col}`);
    } catch (err) {
      
      alert('Error running binning');
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
    const data = await res.json();
    if (!data.success) throw new Error(data.error);

    const updatedFine = { ...fineBinResults, [col]: data.stats || [] };
    const updatedHistory = { ...binMergeHistory, [col]: data.bin_merges || newHistory };
    setFineBinResults(updatedFine);
    setBinMergeHistory(updatedHistory);
    setSelectedFineBins(prev => ({ ...prev, [col]: [] }));

    // Recalculate metrics for the updated bins
    try {
      await calculateAllBinMetrics(col, data.stats || []);
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
    const newStats = columnResult?.stats || [];
    const updatedUnivariate = { ...univariateResults, [col]: columnResult };
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

  const runAutoMonotonicBinning = async (col: string) => {
    const varType = (continuousColumns || []).includes(col) ? 'continuous' : 'discrete';

    try {
      showNotification(`Running auto-monotonic binning for ${col}...`);

      // Call the auto-monotonic-binning API
      const response = await fetch('http://localhost:5000/api/auto-monotonic-binning', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          variable: col,
          target: targetVariable,
          type: varType,
          direction: null,  // Auto-detect direction
          method: 'exhaustive',  // Use greedy algorithm (faster)
          record_id: recordId,
          dashboard_selected_columns: selectedForModeling,
        }),
      });

      const data = await response.json();

      if (!data.success) {
        throw new Error(data.error || 'Auto-binning failed');
      }

      // Update UI with results
      const updatedFine = { ...fineBinResults, [col]: data.stats || [] };
      const updatedHistory = { ...binMergeHistory, [col]: data.bin_merges || {} };
      setFineBinResults(updatedFine);
      setBinMergeHistory(updatedHistory);
      setSelectedFineBins(prev => ({ ...prev, [col]: [] }));

      // Recalculate bin scoring metrics
      try {
        await calculateAllBinMetrics(col, data.stats || []);
      } catch (e) {
        
      }

      const latestWoe = await fetchWoeIv(col, data.bin_merges || {}, false);
      if (latestWoe) {
        setWoeReadyColumns(prev => new Set(prev).add(col));
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
      showNotification(message);


    } catch (err) {
      
      showNotification(`Error in auto-binning: ${err instanceof Error ? err.message : String(err)}`);
      alert('Error running auto-monotonic binning');
    }
  };

  const fetchAllAutoBinningData = async () => {
    // Prevent concurrent loads
    if (isLoadingAutoBinning.current) return;
    isLoadingAutoBinning.current = true;

    try {
      // Simply ensure WOE/IV data is loaded for columns that need it
      // Don't call auto-monotonic-binning API - just use existing data or fetch WOE/IV
      for (const col of selectedColumns) {
        // Skip if already has WOE/IV data
        if (woeIvResults[col]) {
          
          continue;
        }
        
        const varType = (continuousColumns || []).includes(col) ? 'continuous' : 'discrete';
        try {
          // Check if there are saved fine bins for this column
          const { merges } = await loadSavedFineBins(col, varType);
          const mergePayload = merges && Object.keys(merges).length > 0 ? merges : undefined;
          

          // Fetch WOE/IV data (this will use existing bins, not run auto-binning)
          const fetched = await fetchWoeIv(col, mergePayload, false);
          // Ensure bin scoring metrics are computed for auto-loaded columns
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
          
        }
      }
    } finally {
      isLoadingAutoBinning.current = false;
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
      const { merges } = await loadSavedFineBins(col, varType);
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
      const payloadUnivariate = overrides.univariateResults ?? univariateResults ?? {};
      const payloadFine = overrides.fineBinResults ?? fineBinResults ?? {};
      const payloadCrosstab = overrides.crosstabResults ?? coarseBinResults ?? {};
      const payloadWoe = overrides.woeIvResults ?? woeIvResults ?? {};

      const upsertResp = await fetch('http://localhost:5000/api/upsert-single-record', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          dataset_path: 'uploaded.csv',
          discrete_columns: discreteColumns || [],
          continuous_columns: continuousColumns || [],
          selected_columns: payloadSelectedColumns,
          dashboard_selected_columns: payloadDashboard,
          target_variable: targetVariable || '',
          univariate_results: JSON.stringify(payloadUnivariate),
          finebin_results: JSON.stringify(payloadFine),
          crosstab_results: JSON.stringify(payloadCrosstab),
          woe_iv_results: JSON.stringify(payloadWoe),
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
  const persistDashboardSelectedColumns = async (newSelection: string[]) => {
    try {
      
      const resp = await fetch('http://localhost:5000/api/upsert-single-record', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          dataset_path: 'uploaded.csv',
          discrete_columns: discreteColumns || [],
          continuous_columns: continuousColumns || [],
          selected_columns: selectedColumns,
          dashboard_selected_columns: newSelection,
          target_variable: targetVariable || '',
          univariate_results: JSON.stringify(univariateResults || {}),
          finebin_results: JSON.stringify(fineBinResults || {}),
          crosstab_results: JSON.stringify(coarseBinResults || {}),
          woe_iv_results: JSON.stringify(woeIvResults || {}),
          record_id: recordId,
        }),
      });
      const data = await resp.json();
      
      if (!data.error && data.id) {
        setRecordId(data.id);
      }
    } catch (e) {
      
    }
  };
  const toggleSelectedForModeling = (col: string) => {
    setSelectedForModeling((prev) => {
      
      const newSelection = prev.includes(col)
        ? prev.filter((c) => c !== col)
        : [...prev, col];
      
      showNotification(`${col} ${prev.includes(col) ? 'deselected' : 'selected'} for modeling.`);
      // Fire-and-forget persistence (don't block UI)
      persistDashboardSelectedColumns(newSelection);
      return newSelection;
    });
  };

  // Debug render mapping of checkbox state to columns
  useEffect(() => {
    
  }, [selectedForModeling]);
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
      const data = await res.json();
      
      // Log whether the backend returned bin stats for the column (length and sample)
      try {
        const stats = data?.[col]?.stats ?? data?.[col]?.statistics ?? null;
        const statsLen = Array.isArray(stats) ? stats.length : (stats ? 1 : 0);
        const sample = Array.isArray(stats) && stats.length > 0 ? stats[0] : stats;
        
      } catch (e) {
        
      }

      if (!data.error && data[col]) {
        const mergedResults = { ...woeIvResultsRef.current, [col]: data[col] };
        setWoeIvResults(mergedResults);
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
      case 1:
        return woeReadyColumns.size > 0; // Need at least one WOE-ready column to proceed
      case 2:
        return woeReadyColumns.size > 0; // Can proceed to Score Card if WOE-ready columns exist
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
          dataset_path: 'uploaded.csv',
          discrete_columns: discreteColumns || [],
          continuous_columns: continuousColumns || [],
          selected_columns: selectedColumns,
          dashboard_selected_columns: selectedForModeling,
          target_variable: targetVariable || '',
          univariate_results: JSON.stringify(univariateResults || {}),
          finebin_results: JSON.stringify(fineBinResults || {}),
          crosstab_results: JSON.stringify(coarseBinResults || {}),
          woe_iv_results: JSON.stringify(woeIvResults || {}),
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
  useEffect(() => {
    // Only trigger WOE/IV fetch when entering step 2 or 3, not in a loop
    if (currentStep === 2 || currentStep === 3) {
      const cols: string[] = selectedColumns;
      const missing = cols.filter((c) => !woeIvResults[c]);
      if (missing.length > 0) {
        missing.forEach((col) => fetchWoeIv(col, undefined, false));
      }
    }
  }, [currentStep]);

  useEffect(() => {
    // Load data for columns in auto binning mode
    if (binningMode === 'auto' && currentStep === 1) {
      selectedColumns.forEach(col => {
        if (!woeIvResults[col] && !loadingColumns.has(col) && !loadedColumnsRef.current.has(col)) {
          loadColumnData(col);
        }
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [binningMode, currentStep]);

  return (
    <div>
      <Navbar />
      <div className="page-container">
        <div className="progress-header">
          <div className="progress-bar" role="navigation" aria-label="Analysis steps">
            {['Column Selection & Binning', 'Models', 'Score Card'].map((step, index) => (
              <button
                key={step}
                className={`progress-step ${currentStep === index + 1 ? 'active' : ''} ${currentStep > index + 1 ? 'completed' : ''
                  }`}
                disabled={!canGoToStep(index + 1)}
                onClick={() => canGoToStep(index + 1) && setCurrentStep(index + 1)}
                aria-current={currentStep === index + 1 ? 'step' : undefined}
                aria-label={`Go to ${step}`}
              >
                <span className="progress-number">{index + 1}</span>
                <span>{step}</span>
              </button>
            ))}
          </div>
          <div className="progress-actions">
            {currentStep < 3 && (
              <button
                className="progress-action-btn next-button"
                disabled={!canGoNext()}
                onClick={() => setCurrentStep((prev) => prev + 1)}
                aria-label="Go to next step"
              >
                Next
              </button>
            )}
            <button
              className="progress-action-btn save-button"
              onClick={handleSave}
              aria-label="Save analysis"
            >
              Save
            </button>
          </div>
        </div>
        {notification && <div className="notification" role="alert">{notification}</div>}
        <div className={`main-content-wrapper ${currentStep === 2 || currentStep === 3 ? 'full-width' : ''}`}>
          {(currentStep !== 2 && currentStep !== 3) && (
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
            {currentStep === 1 && (
              <div className="binning-mode-toggle">
                <button
                  className={`mode-toggle-btn ${binningMode === 'auto' ? 'active' : ''}`}
                  onClick={() => setBinningMode('auto')}
                >
                  Auto Binning
                </button>
                <button
                  className={`mode-toggle-btn ${binningMode === 'manual' ? 'active' : ''}`}
                  onClick={() => setBinningMode('manual')}
                >
                  Manual Binning
                </button>
              </div>
            )}
            {currentStep === 1 && binningMode === 'auto' && (
              <div className="auto-binning-container">
                <div className="auto-binning-grid">
                  {selectedColumns.map((col) => {
                    const woeData = woeIvResults[col];
                    const isLoading = loadingColumns.has(col);
                    const hasData = !!woeData;
                    
                    const totalIV = woeData?.stats?.reduce((sum: number, s: any) => sum + (s.IV || 0), 0) || 0;
                    
                    // Sort chart data by bin order
                    const unsortedChartData = woeData?.stats?.map((s: any) => ({
                      bin: s.Bin || s.bin || s.Range || '',
                      WOE: s.WOE || 0,
                      temp_bin: s.temp_bin || s.Bin || s.bin || ''
                    })) || [];
                    
                    // Sort bins numerically
                    const chartData = unsortedChartData.sort((a, b) => {
                      // Extract numeric part from bin labels like "Bin_1", "Bin_2", etc.
                      const extractNum = (binLabel: string) => {
                        const match = String(binLabel).match(/\d+/);
                        return match ? parseInt(match[0], 10) : 0;
                      };
                      
                      const numA = extractNum(a.temp_bin || a.bin);
                      const numB = extractNum(b.temp_bin || b.bin);
                      
                      return numA - numB;
                    });
                    
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
            {currentStep === 1 && binningMode === 'manual' && activeColumn && (() => {
              const isContinuousColumn = (continuousColumns || []).includes(activeColumn);
              const coarseRows = coarseBinResults[activeColumn] || [];
              const fineRows = (fineBinResults[activeColumn] && fineBinResults[activeColumn].length > 0)
                ? fineBinResults[activeColumn]
                : coarseRows;
              const history = binMergeHistory[activeColumn] || {};
              const selectedLabels = selectedFineBins[activeColumn] || [];
              const selectedCount = selectedLabels.length;
              const woeStats = woeIvResults[activeColumn]?.stats || [];

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
              const normalizeLabel = (value: string) => value.replace(/\s+/g, ' ').trim();
              const standardizeKey = (value: string) => normalizeLabel(value).toLowerCase();

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

                woeStats.forEach((row: any) => {
                  const candidates = [row.Bin, row.bin, row.temp_bin, row.Range, row.range];
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
                const scanned = woeStats.find((row: any) => {
                  const rowLabel = row.Bin || row.temp_bin || row.Range || '';
                  return normalizeLabel(String(rowLabel)) === normalizeLabel(label) || normalizeLabel(String(rowLabel)) === normalizeLabel(range || '');
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

              const getBinIdentifiers = (bin: any, idx: number) => {
                const raw = bin[`${activeColumn}_fine_binned`] ?? bin[`${activeColumn}_binned`] ?? bin.Bin ?? bin.bin ?? bin.temp_bin ?? bin.Range ?? `Bin_${idx + 1}`;
                const labelVal = String(raw);
                const rangeValue = String(bin.Range ?? '');
                return { labelValRaw: raw, labelVal, rangeValue };
              };

              // === SORT BINS ===
              const sortedRows = [...fineRows].sort((a: any, b: any) => {
                const getMin = (row: any) => {
                  const candidate = row.Min ?? row.min ?? row.MinValue ?? row.minValue ?? null;
                  const numeric = candidate === null || candidate === undefined ? NaN : Number(candidate);
                  return Number.isFinite(numeric) ? numeric : NaN;
                };
                const minA = getMin(a);
                const minB = getMin(b);
                if (!Number.isNaN(minA) && !Number.isNaN(minB)) {
                  return minA - minB;
                }
                const labelA = String(a[`${activeColumn}_fine_binned`] ?? a[`${activeColumn}_binned`] ?? a.Bin ?? a.bin ?? '');
                const labelB = String(b[`${activeColumn}_fine_binned`] ?? b[`${activeColumn}_binned`] ?? b.Bin ?? b.bin ?? '');
                const numA = parseInt((labelA.match(/\d+/) || [])[0] || '', 10);
                const numB = parseInt((labelB.match(/\d+/) || [])[0] || '', 10);
                if (!Number.isNaN(numA) && !Number.isNaN(numB)) {
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
                const goodCount = binMetrics?.good_count ?? pickNumeric(woeData.Good, bin.Good, bin.good);
                const badCount = binMetrics?.bad_count ?? pickNumeric(woeData.Bad, bin.Bad, bin.bad);
                const totalCount = binMetrics?.total_count ?? pickNumeric(woeData.Total, bin.Total, bin.total, (goodCount + badCount));
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
                            sortedRows.map((bin: any, idx: number) => {
                              const { labelValRaw, labelVal, rangeValue } = getBinIdentifiers(bin, idx);
                              const minVal = bin.Min ?? bin.min ?? bin.MinValue ?? bin.minValue ?? null;
                              const maxVal = bin.Max ?? bin.max ?? bin.MaxValue ?? bin.maxValue ?? null;
                              const minDisplay = minVal !== null && minVal !== undefined ? minVal : (isContinuousColumn ? 'N/A' : '—');
                              const maxDisplay = maxVal !== null && maxVal !== undefined ? maxVal : (isContinuousColumn ? 'N/A' : '—');

                              const normalizedLabel = normalizeLabel(labelVal);
                              const rawWoe = getWoeRow(labelVal, rangeValue, labelValRaw) || getWoeRow(normalizedLabel, rangeValue, labelValRaw) || {};
                              const fallbackMetrics = findBinMetric(labelValRaw, labelVal);

                              const goodValue = pickNumeric(
                                fallbackMetrics?.good_count,
                                rawWoe.Good,
                                (rawWoe as any)?.good,
                                bin.Good,
                                bin.good
                              );
                              const badValue = pickNumeric(
                                fallbackMetrics?.bad_count,
                                rawWoe.Bad,
                                (rawWoe as any)?.bad,
                                bin.Bad,
                                bin.bad
                              );
                              const totalValue = pickNumeric(
                                fallbackMetrics?.total_count,
                                rawWoe.Total,
                                (rawWoe as any)?.total,
                                bin.Total,
                                bin.total,
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

                              const badRateRaw = typeof bin['Bad Rate'] === 'number' ? bin['Bad Rate'] : (typeof bin.BadRate === 'number' ? bin.BadRate : null);
                              const freqRaw = typeof bin['Freq%'] === 'number' ? bin['Freq%'] : (typeof bin.Freq === 'number' ? bin.Freq : null);

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
            {currentStep === 2 && (
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
                    selectedVariables={selectedForModeling}
                    allSelectedVariables={selectedColumns}
                    targetVariable={targetVariable}
                    woeTransformedData={woeIvResults}
                    onColumnSelect={(column) => setActiveColumn(column)}
                    onToggleSelect={toggleSelectedForModeling}
                    selectedColumn={activeColumn}
                    onGenerateScoreCard={(modelType) => {
                      setSelectedModelForScorecard(modelType);
                      gotoScoreCardAndGenerate();
                    }}
                    generatingScoreCard={generatingScoreCard}
                    onGotoScoreCard={gotoScoreCardAndGenerate}
                    onResultsUpdate={handleLogisticResults} // Add this prop
                  />
                )}

                {selectedModel === 'random_forest' && (
                  <RandomForestResults
                    selectedVariables={selectedForModeling}
                    allSelectedVariables={selectedColumns}
                    targetVariable={targetVariable}
                    woeTransformedData={woeIvResults}
                    onColumnSelect={(column) => setActiveColumn(column)}
                    onToggleSelect={toggleSelectedForModeling}
                    selectedColumn={activeColumn}
                    onGenerateScoreCard={(modelType) => {
                      setSelectedModelForScorecard(modelType);
                      gotoScoreCardAndGenerate();
                    }}
                    generatingScoreCard={generatingScoreCard}
                    onGotoScoreCard={gotoScoreCardAndGenerate}
                    onResultsUpdate={handleRandomForestResults} // Add this prop
                  />
                )}

                {selectedModel === 'xgboost' && (
                  <XGBoostResults
                    selectedVariables={selectedForModeling}
                    allSelectedVariables={selectedColumns}
                    targetVariable={targetVariable}
                    woeTransformedData={woeIvResults}
                    onColumnSelect={(column) => setActiveColumn(column)}
                    onToggleSelect={toggleSelectedForModeling}
                    selectedColumn={activeColumn}
                    onGenerateScoreCard={(modelType) => {
                      setSelectedModelForScorecard(modelType);
                      gotoScoreCardAndGenerate();
                    }}
                    generatingScoreCard={generatingScoreCard}
                    onGotoScoreCard={gotoScoreCardAndGenerate}
                    onResultsUpdate={handleXGBoostResults} // Add this prop
                  />
                )}
              </div>
            )}
            {currentStep === 3 && (
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
                            scoreCardData.scorecard_bins.forEach((b: any) => {
                              if (selectedForModeling.includes(b.variable)) {
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
      </div >
    </div >
  );
};
export default SelectedColumnsPage;
