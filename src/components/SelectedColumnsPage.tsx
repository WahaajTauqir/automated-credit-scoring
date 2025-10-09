import { useLocation } from 'react-router-dom';
import { useEffect, useState } from 'react';
import UnivariateResults from './UnivariateResults';
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
  const [compareColumn, setCompareColumn] = useState<string | null>(null);
  const [currentStep, setCurrentStep] = useState(1);
  const [univariateResults, setUnivariateResults] = useState<Record<string, any>>({});
  const [coarseBinResults, setCoarseBinResults] = useState<Record<string, any[]>>({});
  const [selectedBinGroups, setSelectedBinGroups] = useState<Record<string, Record<number, any[]>>>({});
  const [activeGroup, setActiveGroup] = useState<Record<string, number>>({});
  const [fineBinResults, setFineBinResults] = useState<Record<string, any[]>>({});
  const [binMergeHistory, setBinMergeHistory] = useState<Record<string, Record<string, any[]>>>({});
  const [binMergeStack, setBinMergeStack] = useState<Record<string, any[]>>({}); // For undo
  const [recordId, setRecordId] = useState<number | undefined>(initialRecordId);
  const [woeIvResults, setWoeIvResults] = useState<Record<string, any>>({});
  const [woeReadyColumns, setWoeReadyColumns] = useState<Set<string>>(new Set());
  const [selectedForModeling, setSelectedForModeling] = useState<string[]>([]);
  const [notification, setNotification] = useState<string | null>(null);
  const [expandedRanges, setExpandedRanges] = useState<Record<string, boolean>>({});
  const [scoreCardData, setScoreCardData] = useState<any>(null);
  const [testScoreLoading, setTestScoreLoading] = useState(false);
  const [testScoreResults, setTestScoreResults] = useState<any[] | null>(null);
  const [testScoreKS, setTestScoreKS] = useState<number | null>(null);
  const [generatingScoreCard, setGeneratingScoreCard] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [sortBy, setSortBy] = useState<'name' | 'iv' | 'type'>('name');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('asc');

  // Get IV badge class based on IV value
  const getIVBadgeClass = (iv: number) => {
    if (iv < 0.1) return 'weak';
    if (iv < 0.3) return 'medium';
    return 'strong';
  };

  // Filtered and sorted columns
  const filteredColumns = selectedColumns
    .filter(col => col.toLowerCase().includes(searchTerm.toLowerCase()))
    .sort((a, b) => {
      let valA, valB;
      if (sortBy === 'iv') {
        valA = woeIvResults[a]?.iv || 0;
        valB = woeIvResults[b]?.iv || 0;
      } else if (sortBy === 'type') {
        valA = (discreteColumns || []).includes(a) ? 'Discrete' : 'Continuous';
        valB = (discreteColumns || []).includes(b) ? 'Discrete' : 'Continuous';
      } else {
        valA = a;
        valB = b;
      }
      if (valA < valB) return sortOrder === 'asc' ? -1 : 1;
      if (valA > valB) return sortOrder === 'asc' ? 1 : -1;
      return 0;
    });

  // Recommend top columns
  const recommendTopColumns = async (topN: number = 5) => {
    try {
      const missing = selectedColumns.filter(col => !woeIvResults[col]);
      for (const col of missing) {
        await fetchWoeIv(col);
      }
      const sortedByIV = [...selectedColumns].sort((a, b) => (woeIvResults[b]?.iv || 0) - (woeIvResults[a]?.iv || 0));
      const top = sortedByIV.slice(0, topN);
      setSelectedForModeling(top);
      showNotification(`Recommended and selected top ${topN} columns by IV.`);
    } catch (e) {
      console.error('Recommendation failed', e);
    }
  };

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
      setSelectedForModeling(Object.keys(anyWoe)); // Auto-select all WOE-ready columns
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
    // Update selectedForModeling to include all woeReadyColumns
    setSelectedForModeling(Array.from(woeReadyColumns));
  }, [selectedColumns, woeIvResults, woeReadyColumns]);

  // Utility functions
  const formatToFourDecimals = (value: any) => (typeof value === 'number' ? value.toFixed(4) : String(value));

  const showNotification = (message: string) => {
    setNotification(message);
    setTimeout(() => setNotification(null), 3000);
  };

  const truncateRange = (range: string, maxLength: number = 50): string => {
    if (range.length <= maxLength) return range;
    return `${range.slice(0, maxLength - 3)}...`;
  };

  const toggleRangeExpansion = (key: string) => {
    setExpandedRanges((prev) => ({
      ...prev,
      [key]: !prev[key],
    }));
  };

  const handleDropColumn = (col: string) => {
    setSelectedColumns((prev) => prev.filter((c) => c !== col));
    setUnivariateResults((prev) => {
      const newResults = { ...prev };
      delete newResults[col];
      return newResults;
    });
    setCoarseBinResults((prev) => {
      const newResults = { ...prev };
      delete newResults[col];
      return newResults;
    });
    setFineBinResults((prev) => {
      const newResults = { ...prev };
      delete newResults[col];
      return newResults;
    });
    setBinMergeHistory((prev) => {
      const newHistory = { ...prev };
      delete newHistory[col];
      return newHistory;
    });
    setSelectedBinGroups((prev) => {
      const newGroups = { ...prev };
      delete newGroups[col];
      return newGroups;
    });
    setWoeIvResults((prev) => {
      const newResults = { ...prev };
      delete newResults[col];
      return newResults;
    });
    setWoeReadyColumns((prev) => {
      const newSet = new Set(prev);
      newSet.delete(col);
      return newSet;
    });
    setSelectedForModeling((prev) => prev.filter((c) => c !== col));
    if (activeColumn === col) {
      setActiveColumn('');
    }
    if (compareColumn === col) {
      setCompareColumn(null);
    }
    showNotification(`Column ${col} dropped.`);
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
            console.log(`  ${variable}: ${count} bins`);
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
  const loadSavedFineBins = async (col: string, varType: string) => {
    if (!recordId) return;
    try {
      const resp = await fetch(`http://localhost:5000/api/finebin-details/${recordId}/${encodeURIComponent(col)}`);
      const details = await resp.json();
      if (!Array.isArray(details) || details.length === 0) return;

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
      if (Object.keys(savedMerges).length === 0) return;

      const res = await fetch('http://localhost:5000/api/fine-bin', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          variable: col,
          target: targetVariable,
          type: varType,
          bin_merges: savedMerges,
          record_id: recordId,
        }),
      });
      const data = await res.json();
      if (data.success && !data.error) {
        setFineBinResults((prev) => ({ ...prev, [col]: data.stats || [] }));
        setBinMergeHistory((prev) => ({ ...prev, [col]: data.bin_merges || savedMerges }));
        await fetchWoeIv(col, data.bin_merges || savedMerges);
        setWoeReadyColumns((prev) => new Set(prev).add(col));
        setSelectedForModeling((prev) => [...new Set([...prev, col])]); // Add to modeling
      } else {
        console.error('Fine binning failed:', data.error);
      }
    } catch (e) {
      console.error('Failed to load saved fine bins for', col, e);
    }
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
        setSelectedForModeling(Array.from(readyColumns)); // Auto-select all WOE-ready columns
      }
      if (recordData.selected_columns) {
        setSelectedColumns(recordData.selected_columns.split(','));
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
      setUnivariateResults((prev) => ({ ...prev, [col]: data[col] || data }));
      setCoarseBinResults((prev) => ({ ...prev, [col]: (data[col]?.stats || []) }));
      setSelectedBinGroups((prev) => ({ ...prev, [col]: prev[col] || {} }));
      setActiveGroup((prev) => ({ ...prev, [col]: 1 }));
      setFineBinResults((prev) => ({ ...prev, [col]: prev[col] || [] }));
      await loadSavedFineBins(col, varType);
    } catch {
      alert('Error fetching coarse bin results');
    }
  };

  const toggleBinSelection = (col: string, binValue: any, group?: number) => {
    const isContinuous = (continuousColumns || []).includes(col);
    setSelectedBinGroups((prev) => {
      const colGroups = prev[col] || {};
      if (isContinuous) {
        const selectedBins = colGroups[1] || [];
        const updatedBins = selectedBins.includes(binValue)
          ? selectedBins.filter((v) => v !== binValue)
          : [...selectedBins, binValue];
        return { ...prev, [col]: { 1: updatedBins } };
      } else {
        const currentGroupBins = colGroups[group!] || [];
        const updatedBins = currentGroupBins.includes(binValue)
          ? currentGroupBins.filter((v) => v !== binValue)
          : [...currentGroupBins, binValue];
        return { ...prev, [col]: { ...colGroups, [group!]: updatedBins } };
      }
    });
  };

  const runBinning = async (col: string) => {
    const varType = (continuousColumns || []).includes(col) ? 'continuous' : 'discrete';
    try {
      // Backup for undo
      setBinMergeStack((prev) => ({
        ...prev,
        [col]: Array.isArray(binMergeHistory[col]) ? binMergeHistory[col] : [],
      }));

      // Step 1: Run coarse binning
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
      setUnivariateResults((prev) => ({ ...prev, [col]: coarseData[col] || coarseData }));
      setCoarseBinResults((prev) => ({ ...prev, [col]: (coarseData[col]?.stats || []) }));

      // Step 2: Run fine binning if bins are selected
      const colGroupsSnapshot = selectedBinGroups[col];
      let mergesReturned = {};
      if (colGroupsSnapshot && Object.keys(colGroupsSnapshot).length > 0) {
        const existing = binMergeHistory[col] || {};
        const newEntries: Record<string, any[]> = {};
        Object.entries(colGroupsSnapshot).forEach(([gid, bins]) => {
          if (bins && bins.length > 0) {
            const sortedBins = [...bins].sort((a, b) => String(a).localeCompare(String(b)));
            const mergeKey = varType === 'continuous' ? `Merged_${gid}` : sortedBins.join(', ');
            newEntries[mergeKey] = sortedBins;
          }
        });
        const combined = { ...existing, ...newEntries };
        console.log(`bin_merges for ${col}:`, combined);

        const fineRes = await fetch('http://localhost:5000/api/fine-bin', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            variable: col,
            target: targetVariable,
            type: varType,
            bin_merges: combined,
            record_id: recordId,
          }),
        });
        const fineData = await fineRes.json();
        if (!fineData.success) {
          throw new Error(fineData.error || 'Fine binning failed');
        }

        setFineBinResults((prev) => ({ ...prev, [col]: fineData.stats || [] }));
        mergesReturned = fineData.bin_merges || combined;
        setBinMergeHistory((prev) => ({ ...prev, [col]: mergesReturned }));
        setSelectedBinGroups((prev) => ({ ...prev, [col]: {} }));
        await persistFineBinColumn(col, mergesReturned);
      } else {
        // If no bins selected, use coarse binning results
        setFineBinResults((prev) => ({ ...prev, [col]: coarseData[col]?.stats || [] }));
        setBinMergeHistory((prev) => ({ ...prev, [col]: {} }));
        await persistFineBinColumn(col, {});
      }
      // Always trigger fresh WOE/IV calculation after fine binning
      await fetchWoeIv(col, mergesReturned);
      setWoeReadyColumns((prev) => new Set(prev).add(col));
      setSelectedForModeling((prev) => [...new Set([...prev, col])]); // Add to modeling

      showNotification(`Binning completed for ${col}`);
    } catch (err) {
      console.error('Error in runBinning:', err);
      alert('Error running binning');
    }
  };

  const undoBinMerge = (col: string) => {
    if (binMergeStack[col]) {
      setBinMergeHistory((prev) => ({
        ...prev,
        [col]: typeof binMergeStack[col] === 'object' && !Array.isArray(binMergeStack[col]) ? binMergeStack[col] : {},
      }));
      setBinMergeStack((prev) => {
        const newStack = { ...prev };
        delete newStack[col];
        return newStack;
      });
      showNotification(`Undo last merge for ${col}`);
      // Re-run fine binning with previous history
      runBinning(col);
    } else {
      showNotification(`No undo available for ${col}`);
    }
  };

  // Unmerge a specific merged fine bin for a column and refresh results
  const unmergeFineBin = async (col: string, mergedLabelRaw: any) => {
    try {
      const varType = (continuousColumns || []).includes(col) ? 'continuous' : 'discrete';
      const history = binMergeHistory[col] || {};
      const mergedLabel = String(mergedLabelRaw || '');

      if (!history || Object.keys(history).length === 0) {
        showNotification(`No merges to unmerge for ${col}.`);
        return;
      }

      // Helper to compare label against history keys regardless of spacing
      const normalizeParts = (s: string) => s.split(',').map(p => p.trim()).filter(Boolean).sort();

      let keyToRemove: string | null = null;
      if (varType === 'continuous') {
        // For continuous merges we used keys like 'Merged_1', 'Merged_2', ...
        if (history[mergedLabel]) {
          keyToRemove = mergedLabel;
        } else {
          // fallback: find any key that startsWith 'Merged_' and whose value array contains the label's parts (unlikely)
          keyToRemove = Object.keys(history).find(k => k === mergedLabel) || null;
        }
      } else {
        // Discrete: keys are a sorted joined list like 'A, B, C'
        const targetParts = normalizeParts(mergedLabel);
        keyToRemove = Object.keys(history).find(k => {
          const kParts = normalizeParts(k);
          if (kParts.length !== targetParts.length) return false;
          for (let i = 0; i < kParts.length; i++) {
            if (kParts[i] !== targetParts[i]) return false;
          }
          return true;
        }) || null;
        // Also try direct match when label matches key exactly
        if (!keyToRemove && history[mergedLabel]) keyToRemove = mergedLabel;
      }

      if (!keyToRemove) {
        showNotification(`Could not find a matching merge for '${mergedLabel}'.`);
        return;
      }

      const newHistory = { ...history } as Record<string, any[]>;
      delete newHistory[keyToRemove];

      // For continuous: ensure merges reference existing coarse bins only
      if (varType === 'continuous') {
        const coarseRows = (coarseBinResults[col] || []) as any[];
        const binLabelKey = `${col}_binned`;
        const existingBins = new Set(
          coarseRows.map((r) => String(r[binLabelKey])).filter((v) => v !== undefined)
        );
        // filter each merge's old_bins values
        Object.keys(newHistory).forEach((k) => {
          newHistory[k] = (newHistory[k] || []).map(String).filter((b) => existingBins.has(String(b)));
          if (!newHistory[k] || newHistory[k].length === 0) {
            delete newHistory[k];
          }
        });
      }

      // Always re-run fine binning and WOE/IV after unmerge
      let fineBinStats = [];
      let mergesReturned = {};
      if (varType === 'continuous' && Object.keys(newHistory).length === 0) {
        // Revert to coarse bins
        const coarseRes = await fetch('http://localhost:5000/api/univariate-analysis', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            discrete: [],
            continuous: [col],
            target: targetVariable,
          }),
        });
        const coarseData = await coarseRes.json();
        setCoarseBinResults((prev) => ({ ...prev, [col]: (coarseData[col]?.stats || []) }));
        setUnivariateResults((prev) => ({ ...prev, [col]: coarseData[col] || coarseData }));
        const coarseStats = coarseData[col]?.stats || [];
        const binLabelKey = `${col}_binned`;
        fineBinStats = coarseStats.map((row: any) => ({
          ...row,
          Bin: row.Bin ?? row[binLabelKey] ?? '',
        }));
        mergesReturned = {};
      } else {
        // Re-run fine binning with updated merges
        const res = await fetch('http://localhost:5000/api/fine-bin', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            variable: col,
            target: targetVariable,
            type: varType,
            bin_merges: newHistory,
            record_id: recordId,
          }),
        });
        const data = await res.json();
        if (!data.success) {
          throw new Error(data.error || 'Fine binning failed during unmerge');
        }
        fineBinStats = data.stats || [];
        mergesReturned = data.bin_merges || newHistory;
      }
      setFineBinResults((prev) => ({ ...prev, [col]: fineBinStats }));
      setBinMergeHistory((prev) => ({ ...prev, [col]: mergesReturned }));
      setSelectedBinGroups((prev) => ({ ...prev, [col]: {} }));
      await persistFineBinColumn(col, mergesReturned);
      // Always trigger fresh WOE/IV calculation with latest merges
      await fetchWoeIv(col, mergesReturned);
      setWoeReadyColumns((prev) => new Set(prev).add(col));
      setSelectedForModeling((prev) => [...new Set([...prev, col])]);

      showNotification(`Unmerged '${mergedLabel}' for ${col}.`);
    } catch (err) {
      console.error('Error unmerging fine bin:', err);
      alert('Error unmerging fine bin');
    }
  };

  const resetFineBinning = async (col: string) => {
    try {
      // Reset fine binning results and history
      setFineBinResults((prev) => ({ ...prev, [col]: [] }));
      setBinMergeHistory((prev) => ({ ...prev, [col]: {} }));
      setSelectedBinGroups((prev) => ({ ...prev, [col]: {} }));
      setWoeIvResults((prev) => {
        const newResults = { ...prev };
        delete newResults[col];
        return newResults;
      });
      setWoeReadyColumns((prev) => {
        const newSet = new Set(prev);
        newSet.delete(col);
        return newSet;
      });
      setSelectedForModeling((prev) => prev.filter((c) => c !== col));

      // Re-run coarse binning to restore original bins
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
      setCoarseBinResults((prev) => ({ ...prev, [col]: (data[col]?.stats || []) }));
      setUnivariateResults((prev) => ({ ...prev, [col]: data[col] || data }));
      setFineBinResults((prev) => ({ ...prev, [col]: data[col]?.stats || [] }));
      
      // Persist the reset state
      await persistFineBinColumn(col, {});
      showNotification(`Binning for ${col} reset to original coarse bins.`);
    } catch (err) {
      console.error('Error resetting binning:', err);
      alert('Error resetting binning');
    }
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

  const toggleSelectedForModeling = (col: string) => {
    setSelectedForModeling((prev) => {
      const newSelection = prev.includes(col)
        ? prev.filter((c) => c !== col)
        : [...prev, col];
      showNotification(`${col} ${prev.includes(col) ? 'deselected' : 'selected'} for modeling.`);
      return newSelection;
    });
  };

  const fetchWoeIv = async (col: string, merges?: Record<string, any[]>) => {
    try {
      const body: any = { variables: [col], target: targetVariable };
      if (recordId) body.record_id = recordId;
      if (merges) body.bin_merges = merges;

      const res = await fetch('http://localhost:5000/api/woe-iv', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (!data.error) {
        setWoeIvResults((prev) => ({ ...prev, ...data }));
        setSelectedForModeling((prev) => [...new Set([...prev, col])]); // Add to modeling
      }
    } catch (e) {
      console.error('WOE/IV fetch failed', e);
    }
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
        missing.forEach((col) => fetchWoeIv(col));
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
                className={`progress-step ${currentStep === index + 1 ? 'active' : ''} ${
                  currentStep > index + 1 ? 'completed' : ''
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

        <div className="main-content-wrapper" style={{ display: 'flex', gap: '20px' }}>
          {(currentStep !== 2 && currentStep !== 3) && (
            <aside className="column-selection-section" aria-label="Scrollable column selection panel" style={{ width: '30%', minWidth: '250px' }}>
              <h3>Columns Dashboard</h3>
              <div className="sidebar-controls">
                <input
                  type="text"
                  placeholder="Search columns..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="search-input"
                />
                <select
                  value={sortBy}
                  onChange={(e) => setSortBy(e.target.value as 'name' | 'iv' | 'type')}
                  className="sort-select"
                >
                  <option value="name">Sort by Name</option>
                  <option value="iv">Sort by IV</option>
                  <option value="type">Sort by Type</option>
                </select>
                <button onClick={() => setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc')} className="sort-order-btn">
                  {sortOrder === 'asc' ? '↑' : '↓'}
                </button>
                <button onClick={() => recommendTopColumns(5)} className="recommend-btn">Recommend Top 5</button>
              </div>
              <div className="columns-grid" aria-label="List of selectable columns">
                {filteredColumns.map((col: string) => (
                  <div
                    key={col}
                    className={`column-card ${col === activeColumn ? 'active' : ''} ${col === compareColumn ? 'compare-active' : ''}`}
                    onClick={() => handleColumnClick(col)}
                    role="button"
                    tabIndex={0}
                    onKeyDown={(e) => e.key === 'Enter' && handleColumnClick(col)}
                    aria-label={`Select column ${col}`}
                  >
                    <div className="column-card-content">
                      <input
                        type="checkbox"
                        checked={selectedForModeling.includes(col)}
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
                      {woeIvResults[col] && (
                        <span className={`iv-badge ${getIVBadgeClass(woeIvResults[col].iv)}`}>
                          IV: {formatToFourDecimals(woeIvResults[col].iv)}
                        </span>
                      )}
                      {/* Drop button removed as requested */}
                      {/* Compare button removed with WOE/IV section */}
                    </div>
                  </div>
                ))}
              </div>
            </aside>
          )}

          <section
            className="content-section"
            style={{
              width: (currentStep === 2 || currentStep === 3) ? '100%' : '70%',
              transition: 'width 0.3s'
            }}
          >
            {currentStep === 1 && activeColumn && (
              <div className="binning-section" aria-label="Binning controls and results">

                {coarseBinResults[activeColumn] && (
                  <div className="results-container">
                    <h3>Binning - {activeColumn}</h3>
                    <h4>Merge Adjacent Bins For Fine Binning</h4>

                    {!((continuousColumns || []).includes(activeColumn)) && (
                      <div className="group-selector">
                        <label htmlFor={`group-select-${activeColumn}`} style={{ marginRight: '8px' }}>
                          Select group:
                        </label>
                        <select
                          id={`group-select-${activeColumn}`}
                          value={activeGroup[activeColumn] || 1}
                          onChange={(e) => setActiveGroup((prev) => ({ ...prev, [activeColumn]: Number(e.target.value) }))}
                          aria-label={`Select binning group for ${activeColumn}`}
                        >
                          {[1, 2, 3, 4, 5].map((g) => (
                            <option key={g} value={g}>
                              Group {g}
                            </option>
                          ))}
                        </select>
                      </div>
                    )}

                    <div className="table-container">
                      <table className="cross-tab-table" aria-label={`Coarse binning results for ${activeColumn}`}>
                        <thead>
                          <tr>
                            <th>Select</th>
                            <th>Bin</th>
                            {(continuousColumns || []).includes(activeColumn) ? (
                              <>
                                <th>Min</th>
                                <th>Max</th>
                              </>
                            ) : (
                              <th>Range</th>
                            )}
                            <th>Bad</th>
                            <th>Good</th>
                            <th>Total</th>
                            <th>Bad Rate (%)</th>
                            <th>Freq %</th>
                          </tr>
                        </thead>
                        <tbody>
                          {(coarseBinResults[activeColumn] || []).filter((bin) => {
                            const merges = binMergeHistory[activeColumn];
                            if (!merges) return true;
                            const mergedValues = Object.values(merges).flat();
                            return !mergedValues.includes(bin[`${activeColumn}_binned`]);
                          }).map((bin, idx) => {
                            const binLabelKey = `${activeColumn}_binned`;
                            const group = activeGroup[activeColumn] || 1;
                            const isContinuous = (continuousColumns || []).includes(activeColumn);
                            const originalLabel = typeof bin[binLabelKey] === 'string' ? bin[binLabelKey] : `Bin_${bin[binLabelKey]}`;
                            const rangeKey = `${activeColumn}_${idx}`;
                            const rangeValue = String(bin.Range ?? '');
                            const isTruncated = !isContinuous && rangeValue.length > 50;
                            const truncatedRange = isTruncated ? truncateRange(rangeValue) : rangeValue;

                            return (
                              <tr key={bin[binLabelKey]}>
                                <td>
                                  <input
                                    type="checkbox"
                                    checked={
                                      selectedBinGroups[activeColumn]?.[isContinuous ? 1 : group]?.includes(bin[binLabelKey]) || false
                                    }
                                    onChange={() => toggleBinSelection(activeColumn, bin[binLabelKey], isContinuous ? 1 : group)}
                                    aria-label={`Select bin ${originalLabel} for ${activeColumn}`}
                                  />
                                </td>
                                <td>{originalLabel}</td>
                                {isContinuous ? (
                                  <>
                                    <td>{bin.Min ?? ''}</td>
                                    <td>{bin.Max ?? ''}</td>
                                  </>
                                ) : (
                                  <td>
                                    <button
                                      type="button"
                                      title={rangeValue}
                                      style={{ cursor: isTruncated ? 'pointer' : 'default', background: 'none', border: 'none', color: 'inherit' }}
                                      onClick={isTruncated ? () => toggleRangeExpansion(rangeKey) : undefined}
                                      aria-label={isTruncated ? `Expand range for bin ${originalLabel}` : undefined}
                                    >
                                      {expandedRanges[rangeKey] ? rangeValue : truncatedRange}
                                    </button>
                                  </td>
                                )}
                                <td>{bin.Bad}</td>
                                <td>{bin.Good}</td>
                                <td>{bin.Total}</td>
                                <td>{formatToFourDecimals(bin['Bad Rate'])}%</td>
                                <td>{formatToFourDecimals(bin['Freq%'])}%</td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>

                    <div className="binning-controls">
                      <button className="fine-bin-btn" onClick={() => runBinning(activeColumn)} aria-label={`Run binning for ${activeColumn}`}>
                        Fine Binning on Selected
                      </button>
                      <button className="reset-bin-btn" onClick={() => resetFineBinning(activeColumn)} aria-label={`Reset binning for ${activeColumn}`}>
                        Reset Binning
                      </button>
                    </div>
                  </div>
                )}

                {activeColumn && univariateResults[activeColumn] && (
                  <div className="univariate-results-section">
                    <UnivariateResults
                      univariateResults={{ [activeColumn]: univariateResults[activeColumn] }}
                      formatToFourDecimals={formatToFourDecimals}
                      onDropColumn={handleDropColumn}
                    />
                  </div>
                )}

                {fineBinResults[activeColumn]?.length > 0 && (
                  <div className="results-container">
                    <h2>Fine Binning Results</h2>
                    <div className="table-container">
                      <table className="cross-tab-table" aria-label={`Fine binning results for ${activeColumn}`}>
                        <thead>
                          <tr>
                            <th>Bin</th>
                            {(continuousColumns || []).includes(activeColumn) ? (
                              <>
                                <th>Min</th>
                                <th>Max</th>
                              </>
                            ) : (
                              <th>Range</th>
                            )}
                            <th>Bad</th>
                            <th>Good</th>
                            <th>Total</th>
                            <th>Bad Rate (%)</th>
                            <th>Freq%</th>
                            <th>Actions</th>
                          </tr>
                        </thead>
                        <tbody>
                          {fineBinResults[activeColumn]
                            .sort((a, b) => {
                              const labelA = (a[activeColumn + '_fine_binned'] || '').toString();
                              const labelB = (b[activeColumn + '_fine_binned'] || '').toString();
                              return labelA.localeCompare(labelB);
                            })
                            .map((bin, idx) => {
                              const isContinuous = (continuousColumns || []).includes(activeColumn);
                              const rangeKey = `${activeColumn}_${idx}`;
                              const rangeValue = String(bin.Range ?? '');
                              const isTruncated = !isContinuous && rangeValue.length > 50;
                              const truncatedRange = isTruncated ? truncateRange(rangeValue) : rangeValue;

                              const labelVal = bin[activeColumn + '_fine_binned'] || bin['Bin'] || bin['Bin_1'];
                              const isMergedLabel = typeof labelVal === 'string' && (
                                labelVal.includes(',') || (binMergeHistory[activeColumn] && binMergeHistory[activeColumn][labelVal]) ||
                                labelVal.startsWith('Merged_')
                              );

                              return (
                                <tr
                                  key={idx}
                                  style={{
                                    backgroundColor:
                                      typeof bin[activeColumn + '_fine_binned'] === 'string' &&
                                      (bin[activeColumn + '_fine_binned'].indexOf(',') !== -1 || bin[activeColumn + '_fine_binned'].startsWith('Merged_'))
                                        ? 'var(--merged-bin-bg, #21262d)'
                                        : 'transparent',
                                  }}
                                >
                                  <td style={{ maxWidth: '120px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', verticalAlign: 'middle' }} title={labelVal}>
                                    {labelVal}
                                  </td>
                                  {isContinuous ? (
                                    <>
                                      <td>{bin.Min ?? 'N/A'}</td>
                                      <td>{bin.Max ?? 'N/A'}</td>
                                    </>
                                  ) : (
                                    <td>
                                      <button
                                        type="button"
                                        title={rangeValue}
                                        style={{ cursor: isTruncated ? 'pointer' : 'default', background: 'none', border: 'none', color: 'inherit' }}
                                        onClick={isTruncated ? () => toggleRangeExpansion(rangeKey) : undefined}
                                        aria-label={isTruncated ? `Expand range for bin ${bin[activeColumn + '_fine_binned']}` : undefined}
                                      >
                                        {expandedRanges[rangeKey] ? rangeValue : truncatedRange}
                                      </button>
                                    </td>
                                  )}
                                  <td>{bin.Bad ?? bin['Bad'] ?? 0}</td>
                                  <td>{bin.Good ?? bin['Good'] ?? 0}</td>
                                  <td>{bin.Total ?? bin['Total'] ?? 0}</td>
                                  <td>{typeof bin['Bad Rate'] === 'number' ? bin['Bad Rate'].toFixed(4) : bin['BadRate']?.toFixed(4) ?? '0.0000'}</td>
                                  <td>{typeof bin['Freq%'] === 'number' ? bin['Freq%'].toFixed(2) : '0.00'}</td>
                                  <td>
                                    {isMergedLabel ? (
                                      <button
                                        className="unmerge-btn compact"
                                        onClick={() => unmergeFineBin(activeColumn, labelVal)}
                                        aria-label={`Unmerge ${String(labelVal)}`}
                                        title="Unmerge"
                                      >
                                        <span style={{fontSize: '12px', fontWeight: 600, padding: '2px 8px', borderRadius: '6px', background: 'var(--bg-quaternary)', color: 'var(--fg-accent-red)', border: '1px solid var(--border-secondary)', boxShadow: 'var(--shadow-light)', transition: 'all 0.2s'}}>Unmerge</span>
                                      </button>
                                    ) : null}
                                  </td>
                                </tr>
                              );
                            })}
                        </tbody>
                      </table>
                    </div>

                    {woeIvResults[activeColumn] && (
                      <div className="woe-iv-embedded" style={{ marginTop: '24px' }}>
                        <h3>WOE by Bin</h3>
                        <ResponsiveContainer width="100%" height={300}>
                          <BarChart
                            data={(woeIvResults[activeColumn]?.stats || []).map((row: any, idx: number) => ({
                              Bin: row.Bin || row.temp_bin || row.Range || `Bin_${idx + 1}`,
                              WOE: parseFloat(row.WOE),
                            }))}
                            margin={{ top: 20, right: 30, bottom: 40, left: 0 }}
                          >
                            <CartesianGrid strokeDasharray="3 3" />
                            <XAxis dataKey="Bin" angle={-30} textAnchor="end" interval={0} />
                            <YAxis />
                            <Tooltip />
                            <Bar dataKey="WOE" fill="#8884d8" />
                          </BarChart>
                        </ResponsiveContainer>

                        <h3 style={{ marginTop: '20px' }}>IV Contribution by Bin</h3>
                        <ResponsiveContainer width="100%" height={300}>
                          <LineChart
                            data={(woeIvResults[activeColumn]?.stats || []).map((row: any, idx: number) => ({
                              Bin: row.Bin || row.temp_bin || row.Range || `Bin_${idx + 1}`,
                              IV: parseFloat(row.IV),
                            }))}
                            margin={{ top: 20, right: 30, bottom: 40, left: 0 }}
                          >
                            <CartesianGrid strokeDasharray="3 3" />
                            <XAxis dataKey="Bin" angle={-30} textAnchor="end" interval={0} />
                            <YAxis />
                            <Tooltip />
                            <Legend />
                            <Line type="monotone" dataKey="IV" stroke="#82ca9d" strokeWidth={2} />
                          </LineChart>
                        </ResponsiveContainer>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}

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