import { useLocation } from 'react-router-dom';
import { useState } from 'react';
import UnivariateResults from './UnivariateResults';
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

  interface BinStats { [key: string]: any; }
  interface Bin { [key: string]: any; }

  const [activeColumn, setActiveColumn] = useState<string>(navSelectedColumns?.[0] || '');

  const [loading, setLoading] = useState(false);
  const [univariateResults, setUnivariateResults] = useState<Record<string, any>>({});
  const [coarseBinResults, setCoarseBinResults] = useState<Record<string, BinStats[]>>({});
  const [selectedBinGroups, setSelectedBinGroups] = useState<Record<string, Record<number, any[]>>>({});
  const [activeGroup, setActiveGroup] = useState<Record<string, number>>({});
  const [fineBinResults, setFineBinResults] = useState<Record<string, BinStats[]>>({});
  // Persisted mapping of merges per column (group/bin identifier -> original bins list)
  const [binMergeHistory, setBinMergeHistory] = useState<Record<string, Record<string, any[]>>>({});
  const [recordId, setRecordId] = useState<number | undefined>(initialRecordId);

  const formatToFourDecimals = (value: any) => (typeof value === 'number' ? value.toFixed(4) : String(value));

  // Fetch univariate & coarse bins
  // Load previously saved fine bin merges/results for a column (if any)
  const loadSavedFineBins = async (col: string, varType: string, coarseStats: BinStats[]) => {
    if (!recordId) return;
    try {
      const resp = await fetch(`http://localhost:5000/api/finebin-details/${recordId}/${encodeURIComponent(col)}`);
      const details = await resp.json();
      if (!Array.isArray(details) || details.length === 0) return;

      // Build merges map
      const savedMerges: Record<string, any[]> = {};
      details.forEach((row: any) => {
        let bins: any[];
        try { bins = JSON.parse(row.merged_bins); } catch { bins = []; }
        if (!bins || bins.length === 0) return;
        if (varType === 'discrete') {
          const label = bins.sort((a,b)=> (Number(a)||0)-(Number(b)||0)).join(', ');
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
          body: JSON.stringify({ variable: col, target: targetVariable, type: varType, bin_merges: savedMerges })
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
    } catch (e) {
      console.error('Failed to load saved fine bins for', col, e);
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
          target: targetVariable
        }),
      });
      const data = await res.json();
      setUnivariateResults(prev => ({ ...prev, [col]: data[col] || data }));
      setCoarseBinResults(prev => ({ ...prev, [col]: (data[col]?.stats || []) as BinStats[] }));

      setSelectedBinGroups(prev => ({ ...prev, [col]: prev[col] || {} }));
      setActiveGroup(prev => ({ ...prev, [col]: 1 }));
  setFineBinResults(prev => ({ ...prev, [col]: prev[col] || [] }));

  // Attempt to restore existing fine bin state
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
      if (varType === 'continuous') {
        const existing = binMergeHistory[col] || {};
        const selectedBins = colGroupsSnapshot[1] || [];
        if (selectedBins.length === 0) { alert('Select at least one bin to merge for continuous variable'); setLoading(false); return; }
        const newKey = selectedBins.join('_');
        const combined = { ...existing, [newKey]: selectedBins };
        const res = await fetch('http://localhost:5000/api/fine-bin', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ variable: col, target: targetVariable, type: varType, bin_merges: combined })
        });
        const data = await res.json();
        if (!data.error) {
          setFineBinResults(p => ({ ...p, [col]: data.stats || [] }));
          const mergesReturned = data.bin_merges || combined;
          setBinMergeHistory(p => ({ ...p, [col]: mergesReturned }));
          setSelectedBinGroups(p => ({ ...p, [col]: {} }));
          await persistFineBinColumn(col, mergesReturned);
        } else alert(data.error);
      } else {
        const allBins = coarseBinResults[col] || [];
        const existing = binMergeHistory[col] || {};
        const newEntries: Record<string, any[]> = {};
        Object.entries(colGroupsSnapshot).forEach(([gid, bins]) => { if (bins && (bins as any[]).length) newEntries[gid] = bins as any[]; });
        const combined: Record<string, any[]> = { ...existing, ...newEntries };
        const mergedValues = Object.values(combined).flat();
        const total = allBins.reduce((s, b) => s + (b.Total || 0), 0);
        const remaining = allBins.filter(b => !mergedValues.includes(b[col + '_binned']))
          .map(b => ({ ...b, [col + '_fine_binned']: b[col + '_binned'], 'Freq%': total ? (b.Total / total) * 100 : 0, 'Bad Rate': b.Total ? (b.Bad / b.Total) * 100 : 0 }));
  const mergedStats = Object.entries(combined).map(([, bins]) => {
          const stat = allBins.filter(b => (bins as any[]).includes(b[col + '_binned'])).reduce((a, b) => { a.Total += b.Total || 0; a.Bad += b.Bad || 0; a.Good += b.Good || 0; return a; }, { Total: 0, Bad: 0, Good: 0 });
          stat['Bad Rate'] = stat.Total ? (stat.Bad / stat.Total) * 100 : 0;
          stat['Freq%'] = total ? (stat.Total / total) * 100 : 0;
          stat[col + '_fine_binned'] = (bins as any[]).join(', ');
          return stat;
        });
        setFineBinResults(p => ({ ...p, [col]: [...remaining, ...mergedStats] }));
        setBinMergeHistory(p => ({ ...p, [col]: combined }));
        setSelectedBinGroups(p => ({ ...p, [col]: {} }));
        await persistFineBinColumn(col, combined);
      }
    } catch (err) {
      console.error(err);
      alert("Error running fine binning");
    } finally {
      setLoading(false);
    }
  };

  // Persist single column merges & stats
  const persistFineBinColumn = async (col: string, merges: Record<string, any[]>) => {
    try {
      let current = recordId;
      const upsertResp = await fetch('http://localhost:5000/api/upsert-single-record', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          dataset_path: 'uploaded.csv',
          discrete_columns: discreteColumns || [],
          continuous_columns: continuousColumns || [],
          selected_columns: navSelectedColumns || [],
          target_variable: targetVariable || '',
          univariate_results: JSON.stringify(univariateResults || {}),
          finebin_results: JSON.stringify(fineBinResults || {}),
          crosstab_results: ''
        })
      });
      const up = await upsertResp.json();
      if (!up.error) { current = up.id; setRecordId(up.id); }
      if (current) {
        await fetch('http://localhost:5000/api/finebin-details', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ record_id: current, column_name: col, bin_merges: merges })
        });
      }
    } catch (e) { console.error('Persist column failed', e); }
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

  // Persist fine bin results & merges to backend
  const handleSave = async () => {
    try {
      setLoading(true);
      let currentRecordId = recordId;
      // Ensure record exists or create/update it with latest finebin_results
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
          crosstab_results: ''
        })
      });
      const upsertData = await upsertResp.json();
      if (!upsertData.error) {
        currentRecordId = upsertData.id;
        setRecordId(currentRecordId);
      }

      // Save finebin merge details per column
      if (currentRecordId) {
        const savePromises = Object.entries(binMergeHistory).map(([col, merges]) =>
          fetch('http://localhost:5000/api/finebin-details', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              record_id: currentRecordId,
              column_name: col,
              bin_merges: merges
            })
          })
        );
        await Promise.all(savePromises);
      }
  alert('Fine bin results saved and persisted.');
    } catch (e) {
      console.error(e);
      alert('Failed to save fine bin results.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="page-container">
      <h2 className="page-title">Select a Column to View Results</h2>

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

      {loading && <p className="loading-text">Loading...</p>}

      {activeColumn && univariateResults[activeColumn] && (
        <div className="results-section">
          <UnivariateResults
            univariateResults={{ [activeColumn]: univariateResults[activeColumn] }}
            formatToFourDecimals={formatToFourDecimals}
            onDropColumn={handleDropColumn}
          />
        </div>
      )}

      {activeColumn && coarseBinResults[activeColumn] && (
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
                .filter(bin => { // remove already merged bins from selection
                  const merges = binMergeHistory[activeColumn];
                  if (!merges) return true;
                  const mergedValues = Object.values(merges).flat();
                  return !mergedValues.includes(bin[`${activeColumn}_binned`]);
                })
                .map((bin, idx) => {
                const binLabelKey = `${activeColumn}_binned`;
                const group = activeGroup[activeColumn] || 1;
                const isContinuous = (continuousColumns || []).includes(activeColumn);

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

                    {/* Sequential Bin labels */}
                    <td>{`Bin_${idx + 1}`}</td>

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

      {activeColumn && fineBinResults[activeColumn]?.length > 0 && (
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

      <div style={{ marginTop: '30px', textAlign: 'center' }}>
  <button className="file-upload-label" onClick={handleSave}>Save</button>
      </div>
    </div>
  );
};

export default SelectedColumnsPage;
