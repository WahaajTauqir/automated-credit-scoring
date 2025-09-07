import { useLocation } from 'react-router-dom';
import { useEffect, useState } from 'react';
import UnivariateResults from './UnivariateResults';
import WoeIvResults from './WoeIvResults';
import './SelectedColumnsPage.css';

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
  const [selectedColumns, setSelectedColumns] = useState<string[]>(navSelectedColumns || []); // Local state for selected columns
  const [activeColumn, setActiveColumn] = useState<string>(navSelectedColumns?.[0] || '');
  const [currentStep, setCurrentStep] = useState(1);
  const [loading, setLoading] = useState(false);
  const [univariateResults, setUnivariateResults] = useState<Record<string, any>>({});
  const [coarseBinResults, setCoarseBinResults] = useState<Record<string, any[]>>({});
  const [selectedBinGroups, setSelectedBinGroups] = useState<Record<string, Record<number, any[]>>>({});
  const [activeGroup, setActiveGroup] = useState<Record<string, number>>({});
  const [fineBinResults, setFineBinResults] = useState<Record<string, any[]>>({});
  const [binMergeHistory, setBinMergeHistory] = useState<Record<string, Record<string, any[]>>>({});
  const [recordId, setRecordId] = useState<number | undefined>(initialRecordId);
  const [woeIvResults, setWoeIvResults] = useState<Record<string, any>>({});
  const [woeReadyColumns, setWoeReadyColumns] = useState<Set<string>>(new Set());
  const [selectedForModeling, setSelectedForModeling] = useState<string[]>([]);
  const [sortDesc, setSortDesc] = useState(true);
  const [searchTerm] = useState('');
  const [showLegend, setShowLegend] = useState(false);
  const [notification, setNotification] = useState<string | null>(null);
  const [expandedRanges, setExpandedRanges] = useState<Record<string, boolean>>({});

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
    if (navSelectedColumns) setSelectedColumns(navSelectedColumns); // Initialize local selectedColumns
    const first = (state as any).selectedColumns?.[0] || navSelectedColumns?.[0];
    if (first) setActiveColumn(first);
    if ((state as any).recordId) setRecordId((state as any).recordId);
  }, [state]);

  // NEW: useEffect to sync WOE/IV states when selectedColumns changes (e.g., after dropping a column)
  useEffect(() => {
    // Remove WOE/IV data for columns no longer in selectedColumns
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
  }, [selectedColumns, woeIvResults]); // Depend on selectedColumns to trigger cleanup

  // Utility functions
  const formatToFourDecimals = (value: any) => (typeof value === 'number' ? value.toFixed(4) : String(value));

  const showNotification = (message: string) => {
    setNotification(message);
    setTimeout(() => setNotification(null), 3000);
  };

  // Truncate long range strings
  const truncateRange = (range: string, maxLength: number = 50): string => {
    if (range.length <= maxLength) return range;
    return `${range.slice(0, maxLength - 3)}...`;
  };

  // Toggle expansion of a specific range
  const toggleRangeExpansion = (key: string) => {
    setExpandedRanges((prev) => ({
      ...prev,
      [key]: !prev[key],
    }));
  };

  // API calls
  const loadSavedFineBins = async (col: string, varType: string, coarseStats: any[]) => {
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
        setWoeReadyColumns(new Set(Object.keys(recordData.woe_iv_results)));
      }
      if (recordData.selected_columns) {
        setSelectedColumns(recordData.selected_columns.split(',')); // Update selectedColumns from backend
      }
    } catch (e) {
      console.error('Failed to load saved record data', e);
    }
  };

  const handleColumnClick = async (col: string) => {
    setActiveColumn(col);
    setLoading(true);
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
      await loadSavedFineBins(col, varType, data[col]?.stats || []);
    } catch {
      alert('Error fetching coarse bin results');
    } finally {
      setLoading(false);
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

  const runFineBinning = async (col: string) => {
    const colGroupsSnapshot = selectedBinGroups[col];
    if (!colGroupsSnapshot || Object.keys(colGroupsSnapshot).length === 0) {
      alert('Select at least one bin to merge');
      return;
    }

    const varType = (continuousColumns || []).includes(col) ? 'continuous' : 'discrete';
    setLoading(true);
    try {
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

      const res = await fetch('http://localhost:5000/api/fine-bin', {
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
      const data = await res.json();
      if (!data.success) {
        throw new Error(data.error || 'Fine binning failed');
      }

      setFineBinResults((prev) => ({ ...prev, [col]: data.stats || [] }));
      const mergesReturned = data.bin_merges || combined;
      setBinMergeHistory((prev) => ({ ...prev, [col]: mergesReturned }));
      setSelectedBinGroups((prev) => ({ ...prev, [col]: {} }));
      await persistFineBinColumn(col, mergesReturned);
      await fetchWoeIv(col, mergesReturned);
      setWoeReadyColumns((prev) => new Set(prev).add(col));
    } catch (err) {
      console.error('Error in runFineBinning:', err);
      alert('Error running fine binning');
    } finally {
      setLoading(false);
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
          selected_columns: selectedColumns, // Use local selectedColumns
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

  const handleDropColumn = (col: string) => {
    if (col === activeColumn) setActiveColumn('');
    setSelectedColumns((prev) => prev.filter((c) => c !== col)); // Remove from selectedColumns
    setUnivariateResults((prev) => { const { [col]: _, ...rest } = prev; return rest; });
    setCoarseBinResults((prev) => { const { [col]: _, ...rest } = prev; return rest; });
    setFineBinResults((prev) => { const { [col]: _, ...rest } = prev; return rest; });
    setSelectedBinGroups((prev) => { const { [col]: _, ...rest } = prev; return rest; });
    setActiveGroup((prev) => { const { [col]: _, ...rest } = prev; return rest; });
    setBinMergeHistory((prev) => { const { [col]: _, ...rest } = prev; return rest; });
    setWoeIvResults((prev) => { const { [col]: _, ...rest } = prev; return rest; }); // Already removes from WOE/IV here
    setWoeReadyColumns((prev) => {
      const newSet = new Set(prev);
      newSet.delete(col);
      return newSet;
    });
    setSelectedForModeling((prev) => prev.filter((c) => c !== col));
    showNotification(`Column ${col} dropped.`);
  };

  const handleSave = async () => {
    try {
      setLoading(true);
      let currentRecordId = recordId;
      const upsertResp = await fetch('http://localhost:5000/api/upsert-single-record', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          dataset_path: 'uploaded.csv',
          discrete_columns: discreteColumns || [],
          continuous_columns: continuousColumns || [],
          selected_columns: selectedColumns, // Use local selectedColumns
          target_variable: targetVariable || '',
          univariate_results: JSON.stringify(univariateResults || {}),
          finebin_results: JSON.stringify(fineBinResults || {}),
          crosstab_results: '',
          woe_iv_results: JSON.stringify(woeIvResults || {}),
        }),
      });
      const upsertData = await upsertResp.json();
      if (!upsertData.error) {
        currentRecordId = upsertData.id;
        setRecordId(currentRecordId);
      }

      if (currentRecordId) {
        const savePromises = Object.entries(binMergeHistory).map(([col, merges]) =>
          fetch('http://localhost:5000/api/finebin-details', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              record_id: currentRecordId,
              column_name: col,
              bin_merges: merges,
            }),
          })
        );
        await Promise.all(savePromises);
      }
      showNotification('Fine bin and WOE/IV results saved and persisted.');
    } catch (e) {
      console.error(e);
      showNotification('Failed to save results.');
    } finally {
      setLoading(false);
    }
  };

  const fetchWoeIv = async (col: string, merges?: Record<string, any[]>) => {
    try {
      if (recordId && !merges) {
        const recordResp = await fetch(`http://localhost:5000/api/record/${recordId}`);
        const recordData = await recordResp.json();
        if (recordData.woe_iv_results && recordData.woe_iv_results[col]) {
          setWoeIvResults((prev) => ({ ...prev, [col]: recordData.woe_iv_results[col] }));
          return;
        }
      }

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
      }
    } catch (e) {
      console.error('WOE/IV fetch failed', e);
    }
  };

  const handleModelingSelection = (col: string) => {
    setSelectedForModeling((prev) => {
      const newSelection = prev.includes(col)
        ? prev.filter((v) => v !== col)
        : [...prev, col];
      showNotification(`${col} ${prev.includes(col) ? 'deselected' : 'selected'}.`);
      return newSelection;
    });
  };

  const sortedIVResults = Object.entries(woeIvResults)
    .map(([col, res]) => ({ column: col, iv: res?.iv || 0 }))
    .sort((a, b) => (sortDesc ? b.iv - a.iv : a.iv - b.iv));

  const filteredIVResults = sortedIVResults.filter(({ column }) =>
    column.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const getIvColor = (iv: number) => {
    if (iv < 0.02) return '#ff4d4f';
    if (iv < 0.1) return '#fa8c16';
    if (iv < 0.3) return '#d4af37';
    if (iv < 0.5) return '#52c41a';
    return '#1890ff';
  };

  const canGoToStep = (step: number) => {
    switch (step) {
      case 1:
        return true;
      case 2:
        return !!activeColumn && !!univariateResults[activeColumn];
      case 3:
        return !!activeColumn && woeReadyColumns.has(activeColumn);
      case 4:
        return true;
      default:
        return false;
    }
  };

  let pageTitle = '';
  switch (currentStep) {
    case 1:
      pageTitle = 'Select a Column to View Results';
      break;
    case 2:
      pageTitle = `Binning for ${activeColumn}`;
      break;
    case 3:
      pageTitle = `WOE/IV Results for ${activeColumn}`;
      break;
    case 4:
      pageTitle = 'IV Selection for Modeling';
      break;
    default:
      pageTitle = 'Select a Column to View Results';
  }

  const canGoNext = () => {
    switch (currentStep) {
      case 1:
        return !!activeColumn && !!univariateResults[activeColumn];
      case 2:
        return woeReadyColumns.has(activeColumn);
      case 3:
        return true;
      default:
        return false;
    }
  };

  useEffect(() => {
    loadSavedData();
  }, [recordId]);

  useEffect(() => {
    const ensureWoeForAll = async () => {
      if (currentStep !== 4) return;
      const cols: string[] = selectedColumns; // Use local selectedColumns
      const missing = cols.filter((c) => !woeIvResults[c]);
      if (missing.length === 0) return;
      for (const col of missing) {
        await fetchWoeIv(col);
      }
    };
    ensureWoeForAll();
  }, [currentStep, selectedColumns, woeIvResults]);

  return (
    <div className="page-container">
      <div className="progress-bar">
        {['Select Column', 'Binning', 'WOE/IV', 'IV Selection'].map((step, index) => (
          <div
            key={step}
            className={`progress-step ${currentStep === index + 1 ? 'active' : ''} ${
              currentStep > index + 1 ? 'completed' : ''
            }`}
            style={{ cursor: canGoToStep(index + 1) ? 'pointer' : 'default', color: canGoToStep(index + 1) ? '#ffffffff' : '#999' }}
            onClick={() => canGoToStep(index + 1) && setCurrentStep(index + 1)}
          >
            <span className="progress-number">{index + 1}</span>
            <span>{step}</span>
          </div>
        ))}
      </div>

      <h2 className="page-title">{pageTitle}</h2>

      {notification && <div className="notification">{notification}</div>}

      {loading && <p className="loading-text">Loading...</p>}

      {currentStep === 1 && (
        <>
          <div className="columns-grid">
            {selectedColumns.map((col: string) => ( // Use local selectedColumns
              <div
                key={col}
                className={`column-card ${col === activeColumn ? 'active' : ''}`}
                onClick={() => handleColumnClick(col)}
              >
                <h4>{col}</h4>
                <small>{(discreteColumns || []).includes(col) ? 'Discrete' : 'Continuous'}</small>
              </div>
            ))}
          </div>

          {activeColumn && univariateResults[activeColumn] && (
            <div className="results-section">
              <UnivariateResults
                univariateResults={{ [activeColumn]: univariateResults[activeColumn] }}
                formatToFourDecimals={formatToFourDecimals}
                onDropColumn={handleDropColumn}
              />
            </div>
          )}
        </>
      )}

      {currentStep === 2 && (
        <>
          {!activeColumn ? (
            <p>Please go back to Step 1 and select a column.</p>
          ) : (
            <>
              {coarseBinResults[activeColumn] && (
                <div className="results-container">
                  <h3>{activeColumn} - Select Bins to Merge</h3>

                  {!((continuousColumns || []).includes(activeColumn)) && (
                    <div style={{ marginBottom: '10px' }}>
                      <label style={{ marginRight: '8px' }}>Select group:</label>
                      <select
                        value={activeGroup[activeColumn] || 1}
                        onChange={(e) => setActiveGroup((prev) => ({ ...prev, [activeColumn]: Number(e.target.value) }))}
                      >
                        {[1, 2, 3, 4, 5].map((g) => (
                          <option key={g} value={g}>
                            Group {g}
                          </option>
                        ))}
                      </select>
                    </div>
                  )}

                  <table className="cross-tab-table">
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
                                <span
                                  title={rangeValue}
                                  style={{ cursor: isTruncated ? 'pointer' : 'default' }}
                                  onClick={isTruncated ? () => toggleRangeExpansion(rangeKey) : undefined}
                                >
                                  {expandedRanges[rangeKey] ? rangeValue : truncatedRange}
                                </span>
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

                  <button className="fine-bin-btn" onClick={() => runFineBinning(activeColumn)}>
                    Fine Binning on Selected
                  </button>
                </div>
              )}

              {fineBinResults[activeColumn]?.length > 0 && (
                <div className="results-section">
                  <h3>Fine Binning Results - {activeColumn}</h3>
                  <table className="cross-tab-table">
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

                          return (
                            <tr
                              key={idx}
                              style={{
                                backgroundColor:
                                  typeof bin[activeColumn + '_fine_binned'] === 'string' &&
                                  bin[activeColumn + '_fine_binned'].indexOf(',') !== -1
                                    ? '#0d1117'
                                    : 'transparent',
                              }}
                            >
                              <td>{bin[activeColumn + '_fine_binned'] || bin['Bin'] || bin['Bin_1']}</td>
                              {isContinuous ? (
                                <>
                                  <td>{bin.Min ?? 'N/A'}</td>
                                  <td>{bin.Max ?? 'N/A'}</td>
                                </>
                              ) : (
                                <td>
                                  <span
                                    title={rangeValue}
                                    style={{ cursor: isTruncated ? 'pointer' : 'default' }}
                                    onClick={isTruncated ? () => toggleRangeExpansion(rangeKey) : undefined}
                                  >
                                    {expandedRanges[rangeKey] ? rangeValue : truncatedRange}
                                  </span>
                                </td>
                              )}
                              <td>{bin.Bad ?? bin['Bad'] ?? 0}</td>
                              <td>{bin.Good ?? bin['Good'] ?? 0}</td>
                              <td>{bin.Total ?? bin['Total'] ?? 0}</td>
                              <td>{typeof bin['Bad Rate'] === 'number' ? bin['Bad Rate'].toFixed(4) : bin['BadRate']?.toFixed(4) ?? '0.0000'}</td>
                              <td>{typeof bin['Freq%'] === 'number' ? bin['Freq%'].toFixed(2) : '0.00'}</td>
                            </tr>
                          );
                        })}
                    </tbody>
                  </table>
                </div>
              )}
            </>
          )}
        </>
      )}

      {currentStep === 3 && (
        <>
          {!activeColumn || !woeReadyColumns.has(activeColumn) || !woeIvResults[activeColumn] ? (
            <p>Please complete previous steps for a column.</p>
          ) : (
            <div className="results-section">
              <WoeIvResults
                woeIvResults={{ [activeColumn]: woeIvResults[activeColumn] }}
                formatToFourDecimals={formatToFourDecimals}
                discreteColumns={discreteColumns}
              />
            </div>
          )}
        </>
      )}

      {currentStep === 4 && (
        <div className="iv-selection-panel">
          <h3>Select Variables for Modeling</h3>
          <div className="iv-controls">
            <div className="iv-search">
              <button onClick={() => setSortDesc(!sortDesc)}>
                Sort by IV {sortDesc ? '↓' : '↑'}
              </button>
            </div>
            <div className="iv-bulk-actions">
              <button
                onClick={() => {
                  setSelectedForModeling(filteredIVResults.map((v) => v.column));
                  showNotification('All visible variables selected.');
                }}
              >
                Select All
              </button>
              <button
                onClick={() => {
                  setSelectedForModeling([]);
                  showNotification('All variables deselected.');
                }}
              >
                Deselect All
              </button>
            </div>
          </div>
          <table className="cross-tab-table">
            <thead>
              <tr>
                <th>Variable</th>
                <th>IV</th>
                <th>Select</th>
              </tr>
            </thead>
            <tbody>
              {filteredIVResults.map(({ column, iv }) => (
                <tr key={column} className="variable-row">
                  <td>{column}</td>
                  <td style={{ color: getIvColor(iv) }}>{iv.toFixed(4)}</td>
                  <td>
                    <input
                      type="checkbox"
                      checked={selectedForModeling.includes(column)}
                      onChange={() => handleModelingSelection(column)}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="iv-legend">
            <button onClick={() => setShowLegend(!showLegend)}>
              {showLegend ? 'Hide Legend' : 'Show IV Strength Legend'}
            </button>
            {showLegend && (
              <ul>
                <li>
                  <span style={{ color: '#ff4d4f' }}>&lt; 0.02: Useless</span>
                </li>
                <li>
                  <span style={{ color: '#fa8c16' }}>0.02 - 0.1: Weak</span>
                </li>
                <li>
                  <span style={{ color: '#d4af37' }}>0.1 - 0.3: Medium</span>
                </li>
                <li>
                  <span style={{ color: '#52c41a' }}>0.3 - 0.5: Strong</span>
                </li>
                <li>
                  <span style={{ color: '#1890ff' }}>&gt; 0.5: Suspicious (possibly overpredictive)</span>
                </li>
              </ul>
            )}
          </div>
          <div className="selected-variables">
            <h4>Selected Variables ({selectedForModeling.length})</h4>
            <div className="selected-tags">
              {selectedForModeling.map((col) => (
                <span key={col} className="selected-tag">
                  {col}
                  <button onClick={() => handleModelingSelection(col)}>×</button>
                </span>
              ))}
            </div>
          </div>
          <button
            className="proceed-btn"
            onClick={() => console.log('Proceed with:', selectedForModeling)}
            disabled={selectedForModeling.length === 0}
          >
            Proceed with Selected
          </button>
        </div>
      )}

      <div className="navigation-buttons">
        {currentStep > 1 && (
          <button onClick={() => setCurrentStep((prev) => prev - 1)}>Back</button>
        )}
        {currentStep < 4 && (
          <button disabled={!canGoNext()} onClick={() => setCurrentStep((prev) => prev + 1)}>
            Next
          </button>
        )}
      </div>

      <div className="save-button">
        <button className="file-upload-label" onClick={handleSave}>
          Save
        </button>
      </div>
    </div>
  );
};

export default SelectedColumnsPage;