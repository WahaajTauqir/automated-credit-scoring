import { useLocation } from 'react-router-dom';
import { useEffect } from 'react';
import { useState } from 'react';
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
    recordId: initialRecordId
  } = state || {};
  console.log("Page state:", state);

  // Initialize component state from navigation state when present
  useEffect(() => {
    if (!state) return;
    // copy any precomputed results into local state so UI reflects them immediately
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
    // ensure active column defaults to first selected column
    const first = (state as any).selectedColumns?.[0] || navSelectedColumns?.[0];
    if (first) setActiveColumn(first);
    // set record id if given
    if ((state as any).recordId) setRecordId((state as any).recordId);
  }, [state]);

  interface BinStats { [key: string]: any; }
  interface Bin { [key: string]: any; }

  const [activeColumn, setActiveColumn] = useState<string>(navSelectedColumns?.[0] || '');
  const [currentStep, setCurrentStep] = useState(1);
  const [loading, setLoading] = useState(false);
  const [univariateResults, setUnivariateResults] = useState<Record<string, any>>({});
  const [coarseBinResults, setCoarseBinResults] = useState<Record<string, BinStats[]>>({});
  const [selectedBinGroups, setSelectedBinGroups] = useState<Record<string, Record<number, any[]>>>({});
  const [activeGroup, setActiveGroup] = useState<Record<string, number>>({});
  const [fineBinResults, setFineBinResults] = useState<Record<string, BinStats[]>>({});
  const [binMergeHistory, setBinMergeHistory] = useState<Record<string, Record<string, any[]>>>({});
  const [recordId, setRecordId] = useState<number | undefined>(initialRecordId);
  const [woeIvResults, setWoeIvResults] = useState<Record<string, any>>({});
  const [woeReadyColumns, setWoeReadyColumns] = useState<Set<string>>(new Set());
  const [selectedForModeling, setSelectedForModeling] = useState<string[]>([]);
  const [sortDesc, setSortDesc] = useState(true);
  const [searchTerm] = useState('');
  const [showLegend, setShowLegend] = useState(false);
  const [notification, setNotification] = useState<string | null>(null);

  const formatToFourDecimals = (value: any) => (typeof value === 'number' ? value.toFixed(4) : String(value));

  const showNotification = (message: string) => {
    setNotification(message);
    setTimeout(() => setNotification(null), 3000);
  };

  const loadSavedFineBins = async (col: string, varType: string, coarseStats: BinStats[]) => {
    if (!recordId) return;
    try {
      const resp = await fetch(`http://localhost:5000/api/finebin-details/${recordId}/${encodeURIComponent(col)}`);
      const details = await resp.json();
      if (!Array.isArray(details) || details.length === 0) return;

      const savedMerges: Record<string, any[]> = {};
      details.forEach((row: any) => {
        let bins: any[];
        try { bins = JSON.parse(row.merged_bins); } catch { bins = []; }
        if (!bins || bins.length === 0) return;
        if (varType === 'discrete') {
          const label = bins.sort((a, b) => (Number(a) || 0) - (Number(b) || 0)).join(', ');
          savedMerges[label] = bins;
        } else {
          savedMerges[row.group_id] = bins;
        }
      });
      if (Object.keys(savedMerges).length === 0) return;

      if (varType === 'continuous') {
        const res = await fetch('http://localhost:5000/api/fine-bin', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ variable: col, target: targetVariable, type: varType, bin_merges: savedMerges, record_id: recordId })
        });
        const data = await res.json();
        if (!data.error) {
          setFineBinResults(prev => ({ ...prev, [col]: data.stats || [] }));
          setBinMergeHistory(prev => ({ ...prev, [col]: savedMerges }));
        }
      } else {
        const allBins = coarseStats || [];
        const mergedBins: BinStats[] = [];
        const totalRecords = allBins.reduce((sum, bin) => sum + (bin.Total || 0), 0);
        Object.entries(savedMerges).forEach(([label, groupBins]) => {
          const mergedStats = allBins
            .filter(bin => groupBins.includes(bin[col + '_binned']))
            .reduce((acc, bin) => {
              acc.Total += bin.Total || 0;
              acc.Bad += bin.Bad || 0;
              acc.Good += bin.Good || 0;
              return acc;
            }, { Total: 0, Bad: 0, Good: 0 });
          mergedStats['Bad Rate'] = mergedStats.Total ? (mergedStats.Bad / mergedStats.Total) * 100 : 0;
          mergedStats['Freq%'] = totalRecords ? (mergedStats.Total / totalRecords) * 100 : 0;
          mergedStats[col + '_fine_binned'] = label;
          mergedBins.push(mergedStats);
        });
        const mergedValues = Object.values(savedMerges).flat();
        const remaining = allBins.filter(bin => !mergedValues.includes(bin[col + '_binned']))
          .map(bin => ({
            ...bin,
            [col + '_fine_binned']: bin[col + '_binned'],
            'Freq%': totalRecords ? (bin.Total / totalRecords) * 100 : 0,
            'Bad Rate': bin.Total ? (bin.Bad / bin.Total) * 100 : 0
          }));
        setFineBinResults(prev => ({ ...prev, [col]: [...remaining, ...mergedBins] }));
        setBinMergeHistory(prev => ({ ...prev, [col]: savedMerges }));
      }
      if (Object.keys(savedMerges).length > 0) {
        // pass saved merges so backend computes WOE/IV on updated bins immediately
        await fetchWoeIv(col, savedMerges);
        setWoeReadyColumns(prev => new Set(prev).add(col));
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
    } catch (e) {
      console.error('Failed to load saved record data', e);
    }
  };

  useEffect(() => {
    loadSavedData();
  }, [recordId]);

  // When user navigates directly to IV Selection, ensure WOE/IV results exist for the selected columns
  useEffect(() => {
    const ensureWoeForAll = async () => {
      if (currentStep !== 4) return;
      const cols: string[] = navSelectedColumns || [];
      const missing = cols.filter(c => !woeIvResults[c]);
      if (missing.length === 0) return;
      for (const col of missing) {
        // fetchWoeIv already checks record cache first
        // sequential fetch keeps load manageable and updates UI progressively
        // eslint-disable-next-line no-await-in-loop
        await fetchWoeIv(col);
      }
    };
    ensureWoeForAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentStep]);

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
          target: targetVariable
        }),
      });
      const data = await res.json();
      setUnivariateResults(prev => ({ ...prev, [col]: data[col] || data }));
      setCoarseBinResults(prev => ({ ...prev, [col]: (data[col]?.stats || []) as BinStats[] }));

      setSelectedBinGroups(prev => ({ ...prev, [col]: prev[col] || {} }));
      setActiveGroup(prev => ({ ...prev, [col]: 1 }));
      setFineBinResults(prev => ({ ...prev, [col]: prev[col] || [] }));

      await loadSavedFineBins(col, varType, (data[col]?.stats || []) as BinStats[]);
    } catch {
      alert('Error fetching coarse bin results');
    } finally {
      setLoading(false);
    }
  };

  const toggleBinSelection = (col: string, binValue: any, group?: number) => {
    const isContinuous = (continuousColumns || []).includes(col);
    setSelectedBinGroups(prev => {
      const colGroups = prev[col] || {};
      if (isContinuous) {
        const selectedBins = colGroups[1] || [];
        const updatedBins = selectedBins.includes(binValue)
          ? selectedBins.filter(v => v !== binValue)
          : [...selectedBins, binValue];
        return { ...prev, [col]: { 1: updatedBins } };
      } else {
        const currentGroupBins = colGroups[group!] || [];
        const updatedBins = currentGroupBins.includes(binValue)
          ? currentGroupBins.filter(v => v !== binValue)
          : [...currentGroupBins, binValue];
        return { ...prev, [col]: { ...colGroups, [group!]: updatedBins } };
      }
    });
  };

  const runFineBinning = async (col: string) => {
    const colGroupsSnapshot = selectedBinGroups[col];
    if (!colGroupsSnapshot || Object.keys(colGroupsSnapshot).length === 0) {
      alert("Select at least one bin to merge");
      return;
    }

    const varType = (continuousColumns || []).includes(col) ? 'continuous' : 'discrete';
    setLoading(true);
    try {
      let mergesToUse: Record<string, any[]> | undefined;
      if (varType === 'continuous') {
        const existing = binMergeHistory[col] || {};
        const selectedBins = colGroupsSnapshot[1] || [];
        if (selectedBins.length === 0) {
          alert('Select at least one bin to merge for continuous variable');
          setLoading(false);
          return;
        }
        const newKey = selectedBins.join('_');
        const combined = { ...existing, [newKey]: selectedBins };
        const res = await fetch('http://localhost:5000/api/fine-bin', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            variable: col,
            target: targetVariable,
            type: varType,
            bin_merges: combined,
            record_id: recordId
          })
        });
        const data = await res.json();
        if (!data.error) {
          setFineBinResults(p => ({ ...p, [col]: data.stats || [] }));
          const mergesReturned = data.bin_merges || combined;
          setBinMergeHistory(p => ({ ...p, [col]: mergesReturned }));
          setSelectedBinGroups(p => ({ ...p, [col]: {} }));
          await persistFineBinColumn(col, mergesReturned);
          mergesToUse = mergesReturned;
        } else alert(data.error);
      } else {
        const allBins = coarseBinResults[col] || [];
        const existing = binMergeHistory[col] || {};
        const newEntries: Record<string, any[]> = {};
        Object.entries(colGroupsSnapshot).forEach(([gid, bins]) => {
          if (bins && (bins as any[]).length) newEntries[gid] = bins as any[];
        });
        const combined: Record<string, any[]> = { ...existing, ...newEntries };
        const mergedValues = Object.values(combined).flat();
        const total = allBins.reduce((s, b) => s + (b.Total || 0), 0);
        const remaining = allBins.filter(b => !mergedValues.includes(b[col + '_binned']))
          .map(b => ({
            ...b,
            [col + '_fine_binned']: b[col + '_binned'],
            'Freq%': total ? (b.Total / total) * 100 : 0,
            'Bad Rate': b.Total ? (b.Bad / b.Total) * 100 : 0
          }));
        const mergedStats = Object.entries(combined).map(([, bins]) => {
          const stat = allBins.filter(b => (bins as any[]).includes(b[col + '_binned'])).reduce((a, b) => {
            a.Total += b.Total || 0;
            a.Bad += b.Bad || 0;
            a.Good += b.Good || 0;
            return a;
          }, { Total: 0, Bad: 0, Good: 0 });
          stat['Bad Rate'] = stat.Total ? (stat.Bad / stat.Total) * 100 : 0;
          stat['Freq%'] = total ? (stat.Total / total) * 100 : 0;
          stat[col + '_fine_binned'] = (bins as any[]).join(', ');
          return stat;
        });
        setFineBinResults(p => ({ ...p, [col]: [...remaining, ...mergedStats] }));
        setBinMergeHistory(p => ({ ...p, [col]: combined }));
        setSelectedBinGroups(p => ({ ...p, [col]: {} }));
        await persistFineBinColumn(col, combined);
        mergesToUse = combined;
      }

      // ensure WOE/IV are calculated using the latest merges we just persisted
      await fetchWoeIv(col, mergesToUse || binMergeHistory[col]);
      setWoeReadyColumns(prev => new Set(prev).add(col));
    } catch (err) {
      console.error(err);
      alert("Error running fine binning");
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
          selected_columns: navSelectedColumns || [],
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
    setUnivariateResults(prev => { const { [col]: _, ...rest } = prev; return rest; });
    setCoarseBinResults(prev => { const { [col]: _, ...rest } = prev; return rest; });
    setFineBinResults(prev => { const { [col]: _, ...rest } = prev; return rest; });
    setSelectedBinGroups(prev => { const { [col]: _, ...rest } = prev; return rest; });
    setActiveGroup(prev => { const { [col]: _, ...rest } = prev; return rest; });
    setBinMergeHistory(prev => { const { [col]: _, ...rest } = prev; return rest; });
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
          selected_columns: navSelectedColumns || [],
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

  // accepts optional merges so backend can compute using freshly created fine bins
  const fetchWoeIv = async (col: string, merges?: Record<string, any[]>) => {
    try {
      // if we have a record cached WOE/IV and no merges forced, use it
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

  return (
    <div className="page-container">
      <div className="progress-bar">
        {['Select Column', 'Binning', 'WOE/IV', 'IV Selection'].map((step, index) => (
          <div
            key={step}
            className={`progress-step ${currentStep === index + 1 ? 'active' : ''} ${currentStep > index + 1 ? 'completed' : ''}`}
            style={{ cursor: canGoToStep(index + 1) ? 'pointer' : 'default', color: canGoToStep(index + 1) ? '#ffffffff' : '#999' }}
            onClick={() => canGoToStep(index + 1) && setCurrentStep(index + 1)}
          >
            <span className="progress-number">{index + 1}</span>
            <span>{step}</span>
          </div>
        ))}
      </div>

      <h2 className="page-title">{pageTitle}</h2>

      {notification && (
        <div className="notification">{notification}</div>
      )}

      {loading && <p className="loading-text">Loading...</p>}

      {currentStep === 1 && (
        <>
          <div className="columns-grid">
            {navSelectedColumns?.map((col: string) => (
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
                        onChange={e => setActiveGroup(prev => ({ ...prev, [activeColumn]: Number(e.target.value) }))}
                      >
                        {[1, 2, 3, 4, 5].map(g => <option key={g} value={g}>Group {g}</option>)}
                      </select>
                    </div>
                  )}

                  <table className="cross-tab-table">
                    <thead>
                      <tr>
                        <th>Select</th>
                        <th>Bin</th>
                        <th>Bad</th>
                        <th>Good</th>
                        <th>Total</th>
                        <th>Bad Rate (%)</th>
                        <th>Freq %</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(coarseBinResults[activeColumn] as Bin[])
                        .filter(bin => {
                          const merges = binMergeHistory[activeColumn];
                          if (!merges) return true;
                          const mergedValues = Object.values(merges).flat();
                          return !mergedValues.includes(bin[`${activeColumn}_binned`]);
                        })
                        .map((bin) => {
                          const binLabelKey = `${activeColumn}_binned`;
                          const group = activeGroup[activeColumn] || 1;
                          const isContinuous = (continuousColumns || []).includes(activeColumn);
                          const originalLabel = typeof bin[binLabelKey] === 'string'
                            ? bin[binLabelKey]
                            : `Bin_${bin[binLabelKey]}`;
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
                              <td>{bin.Bad}</td>
                              <td>{bin.Good}</td>
                              <td>{bin.Total}</td>
                              <td>{formatToFourDecimals(bin["Bad Rate"])}%</td>
                              <td>{formatToFourDecimals(bin["Freq%"])}%</td>
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
                        <th>Bin</th><th>Bad</th><th>Good</th><th>Total</th><th>Bad Rate (%)</th><th>Freq%</th>
                      </tr>
                    </thead>
                    <tbody>
                      {fineBinResults[activeColumn]
                        .sort((a, b) => {
                          const labelA = (a[activeColumn + '_fine_binned'] || '').toString();
                          const labelB = (b[activeColumn + '_fine_binned'] || '').toString();
                          return labelA.localeCompare(labelB);
                        })
                        .map((bin, idx) => (
                          <tr
                            key={idx}
                            style={{
                              backgroundColor:
                                typeof bin[activeColumn + '_fine_binned'] === 'string' &&
                                  bin[activeColumn + '_fine_binned'].indexOf(',') !== -1
                                  ? '#0d1117'
                                  : 'transparent'
                            }}
                          >
                            <td>{bin[activeColumn + '_fine_binned'] || bin['Bin'] || bin['Bin_1']}</td>
                            <td>{bin.Bad ?? bin['Bad'] ?? 0}</td>
                            <td>{bin.Good ?? bin['Good'] ?? 0}</td>
                            <td>{bin.Total ?? bin['Total'] ?? 0}</td>
                            <td>{typeof bin['Bad Rate'] === 'number' ? bin['Bad Rate'].toFixed(4) : bin['BadRate']?.toFixed(4)}</td>
                            <td>{typeof bin['Freq%'] === 'number' ? bin['Freq%'].toFixed(2) : 0}</td>
                          </tr>
                        ))}
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
              <button onClick={() => {
                setSelectedForModeling(filteredIVResults.map((v) => v.column));
                showNotification('All visible variables selected.');
              }}>
                Select All
              </button>
              <button onClick={() => {
                setSelectedForModeling([]);
                showNotification('All variables deselected.');
              }}>
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
                <li><span style={{ color: '#ff4d4f' }}>&lt; 0.02: Useless</span></li>
                <li><span style={{ color: '#fa8c16' }}>0.02 - 0.1: Weak</span></li>
                <li><span style={{ color: '#d4af37' }}>0.1 - 0.3: Medium</span></li>
                <li><span style={{ color: '#52c41a' }}>0.3 - 0.5: Strong</span></li>
                <li><span style={{ color: '#1890ff' }}>&gt; 0.5: Suspicious (possibly overpredictive)</span></li>
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
            onClick={() => console.log("Proceed with:", selectedForModeling)}
            disabled={selectedForModeling.length === 0}
          >
            Proceed with Selected
          </button>
        </div>
      )}

      <div className="navigation-buttons">
        {currentStep > 1 && (
          <button onClick={() => setCurrentStep((prev) => prev - 1)}>
            Back
          </button>
        )}
        {currentStep < 4 && (
          <button disabled={!canGoNext()} onClick={() => setCurrentStep((prev) => prev + 1)}>
            Next
          </button>
        )}
      </div>

      <div className="save-button">
        <button className="file-upload-label" onClick={handleSave}>Save</button>
      </div>
    </div>
  );
};

export default SelectedColumnsPage;