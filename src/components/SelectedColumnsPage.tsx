import { useLocation } from 'react-router-dom';
import { useEffect, useState } from 'react';
import LogisticRegressionResults from './LogisticRegressionResults';
import Navbar from './Navbar';
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
  console.log('Page state:', state);
  // State declarations
  const [selectedColumns, setSelectedColumns] = useState<string[]>(navSelectedColumns || []);
  const [activeColumn, setActiveColumn] = useState<string>('');
  const [currentStep, setCurrentStep] = useState(1);
  const [univariateResults, setUnivariateResults] = useState<Record<string, any>>({});
  const [coarseBinResults, setCoarseBinResults] = useState<Record<string, any[]>>({});
  const [fineBinResults, setFineBinResults] = useState<Record<string, any[]>>({});
  const [selectedFineBins, setSelectedFineBins] = useState<Record<string, string[]>>({});
  const [binMergeHistory, setBinMergeHistory] = useState<Record<string, Record<string, any[]>>>({});
  const [, setBinMergeStack] = useState<Record<string, any[]>>({}); // For undo (unused history for now)
  const [recordId, setRecordId] = useState<number | undefined>(initialRecordId);
  const [woeIvResults, setWoeIvResults] = useState<Record<string, any>>({});
  const [woeReadyColumns, setWoeReadyColumns] = useState<Set<string>>(new Set());
  const [selectedForModeling, setSelectedForModeling] = useState<string[]>([]);
  const [notification, setNotification] = useState<string | null>(null);
  const [scoreCardData, setScoreCardData] = useState<any>(null);
  const [testScoreLoading, setTestScoreLoading] = useState(false);
  const [testScoreResults, setTestScoreResults] = useState<any[] | null>(null);
  const [testScoreKS, setTestScoreKS] = useState<number | null>(null);
  const [generatingScoreCard, setGeneratingScoreCard] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  // Add to your existing state declarations
  const [binScoringMetrics, setBinScoringMetrics] = useState<Record<string, any[]>>({});
  // Removed UI sorting controls per request; keep search only
  // Helper to format IV class if needed later
  // (kept here for possible future IV badge usage)
  // Filtered and sorted columns
  // Filter columns by search term and sort alphabetically by name
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
          console.error('Failed to parse calculate-bin-metrics response:', parseErr, e2, text);
          return null;
        }
      }
      if (data.success) {
        setBinScoringMetrics(prev => ({
          ...prev,
          [columnName]: data.bin_metrics
        }));
        return data.bin_metrics;
      } else {
        console.error('Error calculating bin metrics:', data.error);
        return null;
      }
    } catch (error) {
      console.error('Failed to calculate bin metrics:', error);
      return null;
    }
  };

  // Call this when bin data changes
  // Add this useEffect to debug bin matching
  useEffect(() => {
    if (activeColumn && binScoringMetrics[activeColumn] && fineBinResults[activeColumn]) {
      console.log('=== BIN MATCHING DEBUG ===');
      console.log('Active Column:', activeColumn);
      console.log('Bin Scoring Metrics:', binScoringMetrics[activeColumn]);
      console.log('Fine Bin Results:', fineBinResults[activeColumn]);

      // Check if we can match the first bin
      const firstBin = fineBinResults[activeColumn][0];
      if (firstBin) {
        const firstBinLabel = firstBin[`${activeColumn}_fine_binned`] || firstBin[`${activeColumn}_binned`] || firstBin.Bin || firstBin.bin;
        console.log('First bin label:', firstBinLabel);
        const matchedMetric = binScoringMetrics[activeColumn]?.find(m => m.bin_name === String(firstBinLabel));
        console.log('Matched metric for first bin:', matchedMetric);
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
        console.error('Failed to calculate bin scoring metrics for', activeColumn, e);
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
      const response = await fetch('http://localhost:5000/api/generate-scorecard', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          selected_variables: selectedForModeling,
          target: targetVariable,
          woe_transformed_data: woeIvResults
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
          console.log(`Scorecard generated with ${totalBins} total bins:`);
          variableCounts.forEach(({ variable, count }) => {
            console.log(` ${variable}: ${count} bins`);
          });
          showNotification(`Score card generated with ${totalBins} bins across ${selectedForModeling.length} variables`);
        } else {
          showNotification('Score card generated successfully!');
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
          console.warn('Failed to calculate bin scoring metrics after loading saved fine bins for', col, e);
        }
        setBinMergeHistory((prev) => ({ ...prev, [col]: data.bin_merges || savedMerges }));
        setSelectedFineBins((prev) => ({ ...prev, [col]: [] }));
        return { merges: data.bin_merges || savedMerges };
      } else {
        console.error('Fine binning failed:', data.error);
      }
    } catch (e) {
      console.error('Failed to load saved fine bins for', col, e);
    }
    return { merges: undefined };
  };
  const loadSavedData = async () => {
    if (!recordId) return;
    try {
      const recordResp = await fetch(`http://localhost:5000/api/record/${recordId}`);
      const recordData = await recordResp.json();
      console.debug('[SelectedColumnsPage] loadSavedData: fetched record', recordId, recordData);
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
          console.warn('[SelectedColumnsPage] loadSavedData: failed to parse dashboard_selected_columns', e);
        }
        console.debug('[SelectedColumnsPage] loadSavedData: restoring selectedForModeling', restoredArr);
        setSelectedForModeling(restoredArr);
      }
    } catch (e) {
      console.error('Failed to load saved record data', e);
    }
  };
  const handleColumnClick = async (col: string) => {
    if (col === activeColumn) return; // Prevent re-fetching if already active
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
        console.warn('Failed to calculate initial bin scoring metrics for', col, e);
      }
      setBinMergeHistory((prev) => ({ ...prev, [col]: prev[col] || {} }));
      setSelectedFineBins((prev) => ({ ...prev, [col]: [] }));
      // Load any saved fine bins but do NOT auto-select the column for modeling when clicking the card
      const { merges } = await loadSavedFineBins(col, varType);
      const mergePayload = merges && Object.keys(merges).length > 0 ? merges : undefined;
      const woeSuccess = await fetchWoeIv(col, mergePayload, false);
      if (woeSuccess) {
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
      setUnivariateResults(prev => ({ ...prev, [col]: coarseData[col] || coarseData }));
      setCoarseBinResults(prev => ({ ...prev, [col]: coarseData[col]?.stats || [] }));

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
      setFineBinResults(prev => ({ ...prev, [col]: fineData.stats || [] }));
      setBinMergeHistory(prev => ({ ...prev, [col]: mergesReturned }));
      setSelectedFineBins(prev => ({ ...prev, [col]: [] }));

      // Recalculate bin scoring metrics (G/B odd, index, combined index, etc.) for the updated bins
      try {
        await calculateAllBinMetrics(col, fineData.stats || []);
      } catch (e) {
        console.warn('Failed to recalculate bin scoring metrics after merge for', col, e);
      }

      await persistFineBinColumn(col, mergesReturned);

      // Recompute WOE/IV with correct merges
      await fetchWoeIv(col, mergesReturned, false);
      setWoeReadyColumns(prev => new Set(prev).add(col));
      showNotification(`Binning completed for ${col}`);
    } catch (err) {
      console.error('Error in runBinning:', err);
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

    setFineBinResults(prev => ({ ...prev, [col]: data.stats || [] }));
    setBinMergeHistory(prev => ({ ...prev, [col]: data.bin_merges || newHistory }));
    setSelectedFineBins(prev => ({ ...prev, [col]: [] }));

    // Recalculate metrics for the updated bins
    try {
      await calculateAllBinMetrics(col, data.stats || []);
    } catch (e) {
      console.warn('Failed to recalculate bin scoring metrics after unmerge for', col, e);
    }

    await persistFineBinColumn(col, data.bin_merges || newHistory);
    await fetchWoeIv(col, data.bin_merges || newHistory, false);
    setWoeReadyColumns(prev => new Set(prev).add(col));

    showNotification(`Unmerged '${mergedLabel}'`);
  };
  const resetFineBinning = async (col: string) => {
    const varType = (continuousColumns || []).includes(col) ? 'continuous' : 'discrete';

    // Reset UI state
    setFineBinResults(prev => ({ ...prev, [col]: [] }));
    setBinMergeHistory(prev => ({ ...prev, [col]: {} }));
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
    setCoarseBinResults(prev => ({ ...prev, [col]: data[col]?.stats || [] }));
    const newStats = data[col]?.stats || [];
    setFineBinResults(prev => ({ ...prev, [col]: newStats }));

    // Recompute metrics for reset bins
    try {
      await calculateAllBinMetrics(col, newStats);
    } catch (e) {
      console.warn('Failed to recalculate bin scoring metrics after reset for', col, e);
    }

    await persistFineBinColumn(col, {});

    // Recompute WOE with NO merges
    await fetchWoeIv(col, {}, false);
    setWoeReadyColumns(prev => new Set(prev).add(col));

    showNotification(`Binning reset for ${col}`);
  };
  const persistFineBinColumn = async (col: string, merges: Record<string, any[]>) => {
    try {
      let current = recordId;
      const upsertResp = await fetch('http://localhost:5000/api/upsert-single-record', {
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
          crosstab_results: '',
          woe_iv_results: JSON.stringify(woeIvResults || {}),
        }),
      });
      const up = await upsertResp.json();
      if (!up.error) {
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
      console.error('Persist column failed', e);
    }
  };
  const persistDashboardSelectedColumns = async (newSelection: string[]) => {
    try {
      console.debug('[SelectedColumnsPage] persistDashboardSelectedColumns ->', newSelection);
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
      console.debug('[SelectedColumnsPage] upsert-single-record response:', data);
      if (!data.error && data.id) {
        setRecordId(data.id);
      }
    } catch (e) {
      console.error('Persist dashboard selections failed', e);
    }
  };
  const toggleSelectedForModeling = (col: string) => {
    setSelectedForModeling((prev) => {
      console.debug('[SelectedColumnsPage] toggleSelectedForModeling before:', prev);
      const newSelection = prev.includes(col)
        ? prev.filter((c) => c !== col)
        : [...prev, col];
      console.debug('[SelectedColumnsPage] toggleSelectedForModeling after:', newSelection);
      showNotification(`${col} ${prev.includes(col) ? 'deselected' : 'selected'} for modeling.`);
      // Fire-and-forget persistence (don't block UI)
      persistDashboardSelectedColumns(newSelection);
      return newSelection;
    });
  };
  // Debug render mapping of checkbox state to columns
  useEffect(() => {
    console.debug('[SelectedColumnsPage] render: selectedForModeling ->', selectedForModeling);
  }, [selectedForModeling]);
  const fetchWoeIv = async (
    col: string,
    merges?: Record<string, any[]>,
    addToModeling: boolean = true,
  ): Promise<boolean> => {
    try {
      const varType = (continuousColumns || []).includes(col) ? 'continuous' : 'discrete';
      const body: any = {
        variables: [col],
        target: targetVariable,
        type: varType  // Add this!
      };
      if (recordId) body.record_id = recordId;
      if (merges && Object.keys(merges).length > 0) {
        body.bin_merges = merges;
      }

      const res = await fetch('http://localhost:5000/api/woe-iv', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await res.json();

      if (!data.error && data[col]) {
        setWoeIvResults((prev) => ({ ...prev, [col]: data[col] }));
        if (addToModeling) {
          setSelectedForModeling((prev) => [...new Set([...prev, col])]);
        }
        return true;
      } else {
        console.warn('WOE/IV failed:', data.error);
      }
    } catch (e) {
      console.error('WOE/IV fetch failed', e);
    }
    return false;
  };
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
        console.error('Save failed:', data.error);
        alert(`Error saving analysis: ${data.error || 'Unknown error'}`);
      }
    } catch (error) {
      console.error('Save failed:', error);
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
  return (
    <div>
      <Navbar />
      <div className="page-container">
        <div className="progress-header">
          <div className="progress-bar" role="navigation" aria-label="Analysis steps">
            {['Column Selection & Binning', 'Logistic Regression', 'Score Card'].map((step, index) => (
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
                    console.debug('[SelectedColumnsPage] render: filteredColumns ->', filteredColumns);
                    console.debug('[SelectedColumnsPage] render: selectedColumns ->', selectedColumns);
                  } catch { }
                  return null;
                })()}
                {filteredColumns.map((col: string) => {
                  const isChecked = selectedForModeling.includes(col);
                  try {
                    console.debug('[SelectedColumnsPage] render checkbox', { col, isChecked });
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
            {currentStep === 1 && activeColumn && (() => {
              const isContinuousColumn = (continuousColumns || []).includes(activeColumn);
              const coarseRows = coarseBinResults[activeColumn] || [];
              const fineRows = (fineBinResults[activeColumn] && fineBinResults[activeColumn].length > 0)
                ? fineBinResults[activeColumn]
                : coarseRows;
              const history = binMergeHistory[activeColumn] || {};
              const selectedLabels = selectedFineBins[activeColumn] || [];
              const selectedCount = selectedLabels.length;
              const woeStats = woeIvResults[activeColumn]?.stats || [];
              const normalizeLabel = (value: string) => value.replace(/\s+/g, ' ').trim();
              

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
              const chartRows = woeStats.map((row: any) => {
                return {
                  Bin: row.Bin || row.temp_bin || row.Range || '',
                  WOE: row.WOE || row.woe || row.WoE || row.Woe || row.woe_value || row.WOEValue || 0,
                  IV: row.IV || row.iv || row.Iv || row.iv_contribution || row.IVContribution || 0
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
                              const labelValRaw = bin[`${activeColumn}_fine_binned`] ?? bin[`${activeColumn}_binned`] ?? bin.Bin ?? bin.bin ?? `Bin_${idx + 1}`;
                              const labelVal = String(labelValRaw);
                              const rangeValue = String(bin.Range ?? '');
                              const minVal = bin.Min ?? bin.min ?? bin.MinValue ?? bin.minValue ?? null;
                              const maxVal = bin.Max ?? bin.max ?? bin.MaxValue ?? bin.maxValue ?? null;
                              const minDisplay = minVal !== null && minVal !== undefined ? minVal : (isContinuousColumn ? 'N/A' : '—');
                              const maxDisplay = maxVal !== null && maxVal !== undefined ? maxVal : (isContinuousColumn ? 'N/A' : '—');

                              // Get authoritative values from backend WOE/IV results
                              const normalizedLabel = normalizeLabel(labelVal);
                              const woeData = woeStats.find((row: any) =>
                                (row.Bin || row.temp_bin || row.Range || '') === (labelVal || normalizedLabel)
                              ) || {
                                WOE: 0,
                                IV: 0,
                                'Dist_Good_%': 0,
                                'Dist_Bad_%': 0,
                                Good: 0,
                                Bad: 0,
                                Total: 0
                              };

                              // FIXED: Get Good/Bad counts - use authoritative data from backend
                              const goodValue = woeData.Good || bin.Good || bin.good || 0;
                              const badValue = woeData.Bad || bin.Bad || bin.bad || 0;
                              const totalValue = woeData.Total || bin.Total || bin.total || (goodValue + badValue);

                              const badRateRaw = typeof bin['Bad Rate'] === 'number' ? bin['Bad Rate'] : (typeof bin.BadRate === 'number' ? bin.BadRate : null);
                              const freqRaw = typeof bin['Freq%'] === 'number' ? bin['Freq%'] : (typeof bin.Freq === 'number' ? bin.Freq : null);

                              const isMergedLabel = Boolean(history[labelVal]);
                              const isSelected = selectedLabels.includes(labelVal);

                              return (
                                <tr
                                  key={`${labelVal}-${idx}`}
                                  className={`bin-row ${isSelected ? 'selected' : ''}`}
                                  style={{
                                    backgroundColor: isMergedLabel ? 'var(--merged-bin-bg, #21262d)' : 'transparent',
                                  }}
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
                                  <td>
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
                                  <td title={rangeValue.length > 0 ? rangeValue : undefined} style={{ maxWidth: '160px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                                    {labelVal}
                                  </td>
                                  {isContinuousColumn ? (
                                    <>
                                      <td>{minDisplay}</td>
                                      <td>{maxDisplay}</td>
                                    </>
                                  ) : (
                                    <td title={rangeValue.length > 0 ? rangeValue : undefined}>
                                      {rangeValue || '—'}
                                    </td>
                                  )}

                                  {/* 0/1 Columns - Good/Bad counts */}
                                  <td style={{ color: 'green', fontWeight: 'bold' }}>{goodValue}</td>
                                  <td style={{ color: 'red', fontWeight: 'bold' }}>{badValue}</td>
                                  <td>{totalValue}</td>

                                  {/* 0/1 Ratio Column (Good/Bad) */}
                                  <td>
                                    {(() => {
                                      const binMetrics = binScoringMetrics[activeColumn]?.find(
                                        (m: any) => m.bin_name === String(labelValRaw)
                                      );
                                      return binMetrics?.zero_one_ratio || '—';
                                    })()}
                                  </td>

                                  <td>{badRateRaw !== null && badRateRaw !== undefined ? badRateRaw.toFixed(4) : '0.0000'}</td>
                                  <td>{freqRaw !== null && freqRaw !== undefined ? freqRaw.toFixed(2) : '0.00'}</td>

                                  {/* G/B Metrics Columns */}
                                  <td>
                                    {(() => {
                                      const binMetrics = binScoringMetrics[activeColumn]?.find(
                                        (m: any) => m.bin_name === String(labelValRaw)
                                      );
                                      return binMetrics?.gb_odd || '—';
                                    })()}
                                  </td>
                                  <td>
                                    {(() => {
                                      const binMetrics = binScoringMetrics[activeColumn]?.find(
                                        (m: any) => m.bin_name === String(labelValRaw)
                                      );
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

                                  {/* Combined Index Column */}
                                  <td>
                                    {(() => {
                                      const binMetrics = binScoringMetrics[activeColumn]?.find(
                                        (m: any) => m.bin_name === String(labelValRaw)
                                      );
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

                                  <td>{formatToFourDecimals(woeData['Dist_Good_%'] || 0)}</td>
                                  <td>{formatToFourDecimals(woeData['Dist_Bad_%'] || 0)}</td>
                                  <td>{formatToFourDecimals(woeData.WOE || 0)}</td>
                                  <td>{formatToFourDecimals(woeData.IV || 0)}</td>
                                  <td>
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

                            sortedRows.forEach((bin: any) => {
                              const labelValRaw = bin[`${activeColumn}_fine_binned`] ?? bin[`${activeColumn}_binned`] ?? bin.Bin ?? bin.bin ?? '';
                              const labelVal = String(labelValRaw);
                              const normalizedLabel = normalizeLabel(labelVal);

                              // Get authoritative counts from backend
                              const woeData = woeStats.find((row: any) =>
                                (row.Bin || row.temp_bin || row.Range || '') === (labelVal || normalizedLabel)
                              ) || { Good: 0, Bad: 0, Total: 0 };

                              totalBad += woeData.Bad || 0;
                              totalGood += woeData.Good || 0;
                              totalTotal += woeData.Total || 0;

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

                            // Use authoritative total IV from backend
                            const totalIv = Number(woeIvResults[activeColumn]?.iv ?? 0) || 0;

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
              <LogisticRegressionResults
                selectedVariables={selectedForModeling}
                allSelectedVariables={selectedColumns}
                targetVariable={targetVariable}
                woeTransformedData={woeIvResults}
                onColumnSelect={(column) => setActiveColumn(column)}
                onToggleSelect={toggleSelectedForModeling}
                selectedColumn={activeColumn}
                onGenerateScoreCard={generateScoreCard}
                generatingScoreCard={generatingScoreCard}
                onGotoScoreCard={gotoScoreCardAndGenerate}
              />
            )}
            {currentStep === 3 && (
              <div className="scorecard-section">
                <h3>Score Card</h3>
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
                    <h4>Score Card Results</h4>
                    <div className="table-container">
                      <table className="scorecard-table" aria-label="Score card results">
                        <thead>
                          <tr>
                            <th>Bin #</th>
                            <th>Variable</th>
                            <th>Bin Range</th>
                            <th>WOE</th>
                            <th>Coefficient (β)</th>
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
                                    <td>{formatToFourDecimals(bin.coefficient)}</td>
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
                        </div>
                      </div>
                    )}
                    {/* Test Score Button and Results Table */}
                    <div style={{ marginTop: '32px' }}>
                      <button
                        className="run-regression-btn"
                        onClick={async () => {
                          setTestScoreLoading(true);
                          setTestScoreResults(null);
                          try {
                            const response = await fetch('http://localhost:5000/api/apply-scorecard', {
                              method: 'POST',
                              headers: { 'Content-Type': 'application/json' },
                              body: JSON.stringify({
                                selected_variables: selectedForModeling,
                                target: targetVariable,
                                woe_transformed_data: woeIvResults,
                                scorecard_bins: scoreCardData.scorecard_bins
                              })
                            });
                            const data = await response.json();
                            if (data.success && data.results) {
                              setTestScoreResults(data.results);
                              setTestScoreKS(typeof data.ks_stat === 'number' ? data.ks_stat : null);
                            } else {
                              alert('Error applying score card: ' + (data.error || 'Unknown error'));
                            }
                          } catch (err) {
                            alert('Error applying score card: ' + err);
                          } finally {
                            setTestScoreLoading(false);
                          }
                        }}
                        disabled={testScoreLoading}
                        aria-label="Test Score Card on Data"
                        style={{ marginBottom: '16px' }}
                      >
                        {testScoreLoading ? 'Testing...' : 'Test Score Card'}
                      </button>
                      {testScoreResults && (
                        <div className="scorecard-test-results">
                          <h5>Score Card Test Results (Sorted by Score)</h5>
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
                                    <td style={{ color: row.target === 0 ? 'green' : row.target === 1 ? 'red' : undefined }}>
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
        </div>
        {/* Footer navigation removed per request: Next and Save moved beside progress bar */}
      </div>
    </div>
  );
};
export default SelectedColumnsPage;