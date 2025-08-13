import { useLocation } from 'react-router-dom';
import { useState } from 'react';
import UnivariateResults from './UnivariateResults';
import FineBinResults from './FInebinResults';
import CrossTabResults from './CresstabResults';
import './SelectedColumnsPage.css';


import { useEffect } from 'react';

const SelectedColumnsPage = () => {
  const { state } = useLocation();
  const { selectedColumns, discreteColumns, continuousColumns, targetVariable, fineBinResults: navFineBinResults, finebin_results: navFinebinResultsRaw } = state || {};

  interface BinStats {
    [key: string]: any;
  }
  interface Bin {
    [key: string]: any;
  }


  // State for analysis results
  const [loading, setLoading] = useState(false);
  const [univariateResults, setUnivariateResults] = useState<Record<string, any>>({});
  const [coarseBinResults, setCoarseBinResults] = useState<Record<string, BinStats[]>>({});
  const [selectedBinGroups, setSelectedBinGroups] = useState<Record<string, Record<number, any[]>>>({});
  const [activeGroup, setActiveGroup] = useState<Record<string, number>>({});
  const [fineBinResults, setFineBinResults] = useState<Record<string, BinStats[]>>({});
  const [crossTabResults, setCrossTabResults] = useState<Record<string, any>>({});
  const [fineBinDetails, setFineBinDetails] = useState<Record<string, any>>({});

  // Restore fine binning results and bin merge info from navigation state
  useEffect(() => {
    // Restore fine bin results (actual stats)
    if (navFineBinResults && typeof navFineBinResults === 'object') {
      setFineBinResults(navFineBinResults);
    }
    // Restore bin merge info (which bins were merged)
    if (navFinebinResultsRaw) {
      let parsed = navFinebinResultsRaw;
      if (typeof navFinebinResultsRaw === 'string') {
        try {
          parsed = JSON.parse(navFinebinResultsRaw);
        } catch {}
      }
      if (parsed && typeof parsed === 'object') {
        setSelectedBinGroups(parsed);
      }
    }
  }, [navFineBinResults, navFinebinResultsRaw]);

  useEffect(() => {
    const fetchFineBinDetails = async () => {
      if (!selectedColumns || !state?.recordId) return;

      const details: Record<string, any> = {};
      for (const column of selectedColumns) {
        try {
          const response = await fetch(`http://localhost:5000/api/finebin-details/${state.recordId}/${column}`);
          if (response.ok) {
            const data = await response.json();
            details[column] = data;
          }
        } catch (error) {
          console.error(`Failed to fetch fine bin details for column ${column}:`, error);
        }
      }
      setFineBinDetails(details);
    };

    fetchFineBinDetails();
  }, [selectedColumns, state?.recordId]);

  const formatToFourDecimals = (value: any) => {
    if (typeof value === 'number') return value.toFixed(4);
    return String(value);
  };

  // Fetch univariate and coarse binning results on column click
  const handleColumnClick = async (col: string) => {
    setLoading(true);
    try {
      const varType = continuousColumns.includes(col) ? 'continuous' : 'discrete';

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
      setCoarseBinResults(prev => ({ ...prev, [col]: data[col]?.stats || [] }));
      // Reset selection and active group
      setSelectedBinGroups(prev => ({ ...prev, [col]: {} }));
      setActiveGroup(prev => ({ ...prev, [col]: 1 }));

      // Restore previously saved fine-bin merges if present, then recompute stats
      try {
        const resFine = await fetch(`http://localhost:5000/api/finebin-details/${state?.recordId || ''}/${col}`);
        if (resFine.ok) {
          const merges = await resFine.json();
          if (Array.isArray(merges) && merges.length > 0) {
            const restoredGroups: Record<string, any[]> = {};
            for (const row of merges) {
              const g = String(row.group_id);
              const bins = typeof row.merged_bins === 'string' ? JSON.parse(row.merged_bins) : row.merged_bins;
              restoredGroups[g] = bins;
            }
            setSelectedBinGroups(prev => ({ ...prev, [col]: restoredGroups }));

            // Also recompute and display fine-binned stats from restored merges
            const resReFine = await fetch('http://localhost:5000/api/fine-bin', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                variable: col,
                target: targetVariable,
                type: varType,
                bin_merges: restoredGroups,
              }),
            });
            const refined = await resReFine.json();
            if (!refined.error && Array.isArray(refined.stats)) {
              setFineBinResults(prev => ({ ...prev, [col]: refined.stats }));
            }

            // Hide already-merged bins from the selection table
            const mergedBinsFlat = Object.values(restoredGroups).flat();
            setCoarseBinResults(prev => {
              const prevBins = prev[col] || [];
              const binLabelKey = `${col}_binned`;
              const remainingBins = prevBins.filter((bin: Bin) => !mergedBinsFlat.includes(bin[binLabelKey]));
              return { ...prev, [col]: remainingBins };
            });
          }
        }
      } catch (e) {
        console.warn('No saved fine-bin merges to restore for', col);
      }
    } catch {
      alert('Error fetching coarse bin results');
    } finally {
      setLoading(false);
    }
  };

  const toggleBinSelection = (col: string, binValue: any, group: number) => {
    setSelectedBinGroups(prev => {
      const colGroups = prev[col] || {};
      const currentGroupBins = colGroups[group] || [];
      const updatedBins = currentGroupBins.includes(binValue)
        ? currentGroupBins.filter(v => v !== binValue)
        : [...currentGroupBins, binValue];

      return {
        ...prev,
        [col]: {
          ...colGroups,
          [group]: updatedBins
        }
      };
    });
  };

  // Run fine binning and merge new bins with existing ones
const runFineBinning = async (col: string) => {
  const colGroupsSnapshot = selectedBinGroups[col];
  if (!colGroupsSnapshot || Object.keys(colGroupsSnapshot).length === 0) {
    alert("Select at least one bin to merge");
    return;
  }
  const varType = continuousColumns.includes(col) ? 'continuous' : 'discrete';
  setLoading(true);
  try {
    const res = await fetch('http://localhost:5000/api/fine-bin', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ variable: col, target: targetVariable, type: varType, bin_merges: colGroupsSnapshot }),
    });
    const fineBinData = await res.json();
    if (!fineBinData.error) {
      setFineBinResults(prev => {
        const prevFineBins = prev[col] || [];

        // Attempt to find bin label key ending with '_fine_binned', fallback to first key if none
        const sampleBin: Bin = fineBinData.stats?.[0] || {};
        const binLabelKey =
          Object.keys(sampleBin).find(key => key.endsWith('_fine_binned')) || Object.keys(sampleBin)[0];

        if (!binLabelKey) {
          // If no key found, just overwrite
          return { ...prev, [col]: fineBinData.stats };
        }

        // Build map to avoid duplicates (new data overrides old)
        const mergedBinsMap: Record<string, Bin> = {};
        prevFineBins.forEach((bin: Bin) => {
          mergedBinsMap[bin[binLabelKey]] = bin;
        });
        fineBinData.stats.forEach((bin: Bin) => {
          mergedBinsMap[bin[binLabelKey]] = bin;
        });

        const mergedBins = Object.values(mergedBinsMap);

        return { ...prev, [col]: mergedBins };
      });

      // Remove merged bins from coarse bins
      setCoarseBinResults(prev => {
        const prevBins = prev[col] || [];
        const mergedBinsFlat = Object.values(colGroupsSnapshot).flat();
        const binLabelKey = `${col}_binned`;

        const remainingBins = prevBins.filter((bin: Bin) => !mergedBinsFlat.includes(bin[binLabelKey]));

        return { ...prev, [col]: remainingBins };
      });

      // Reset selections
      setSelectedBinGroups(prev => ({ ...prev, [col]: {} }));
      setActiveGroup(prev => ({ ...prev, [col]: 1 }));

      // Fetch cross-tab results
      const crossTabRes = await fetch('http://localhost:5000/api/cross-tab', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ variables: [col], target: targetVariable }),
      });
      const crossTabData = await crossTabRes.json();

      if (!crossTabData.error) {
        setCrossTabResults(prev => ({
          ...prev,
          [col]: crossTabData[col] || crossTabData,
        }));
      }

      // Persist fine bin merge info for all columns
      try {
        // Build a structure: { columnName: { ...bin_merges } }
        const fineBinMergeInfo: Record<string, any> = {};
        Object.keys(fineBinResults).forEach(fbCol => {
          fineBinMergeInfo[fbCol] = selectedBinGroups[fbCol] || {};
        });

        // Fetch previous merges for this column (if any) to union with current selection
        let previousMerges: Record<string, any[]> = {};
        try {
          const prevRes = await fetch(`http://localhost:5000/api/finebin-details/${state?.recordId || ''}/${col}`);
          if (prevRes.ok) {
            const prevRows = await prevRes.json();
            prevRows.forEach((r: any) => {
              const g = String(r.group_id);
              const bins = typeof r.merged_bins === 'string' ? JSON.parse(r.merged_bins) : r.merged_bins;
              previousMerges[g] = bins;
            });
          }
        } catch {}

        // Union merges: keep previous bins and add new ones per group
        const combined: Record<string, any[]> = { ...previousMerges };
        Object.entries(colGroupsSnapshot).forEach(([g, bins]) => {
          const prev = new Set(combined[g] || []);
          (bins as any[]).forEach(b => prev.add(b));
          combined[g] = Array.from(prev);
        });

        // Replace the column's merges with combined
        fineBinMergeInfo[col] = combined;

        // Upsert record with merged info
        const upResp = await fetch('http://localhost:5000/api/upsert-single-record', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            dataset_path: 'uploaded.csv',
            discrete_columns: discreteColumns,
            continuous_columns: continuousColumns,
            selected_columns: selectedColumns,
            target_variable: targetVariable,
            univariate_results: '',
            finebin_results: JSON.stringify(fineBinMergeInfo),
            crosstab_results: ''
          })
        });
        const upJson = await upResp.json().catch(() => ({} as any));
        const recId = state?.recordId || upJson?.id;

        if (recId) {
          // Save combined merges for this column to finebin_details
          await fetch('http://localhost:5000/api/finebin-details', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ record_id: recId, column_name: col, bin_merges: combined })
          });
        }

        // Hide merged bins from coarse table using combined merges
        const combinedFlat = Object.values(combined).flat();
        setCoarseBinResults(prev => {
          const prevBins = prev[col] || [];
          const binLabelKey = `${col}_binned`;
          const remainingBins = prevBins.filter((bin: Bin) => !combinedFlat.includes(bin[binLabelKey]));
          return { ...prev, [col]: remainingBins };
        });
      } catch (e) {
        console.error('Failed to upsert fine bin merge info:', e);
      }
    }
  } catch {
    alert("Error running fine binning");
  } finally {
    setLoading(false);
  }
};

  return (
    <div className="page-container">
      <h2 className="page-title">Select a Column to View Results</h2>

      {/* Column cards */}
      <div className="columns-grid">
        {selectedColumns?.map((col: string) => (
          <div key={col} className="column-card" onClick={() => handleColumnClick(col)}>
            <h4>{col}</h4>
            <small>{discreteColumns.includes(col) ? 'Discrete' : 'Continuous'}</small>
          </div>
        ))}
      </div>

      {loading && <p className="loading-text">Loading...</p>}

      {/* Univariate results */}
      {Object.keys(univariateResults).length > 0 && (
        <div className="results-section">
          <UnivariateResults
            univariateResults={univariateResults}
            formatToFourDecimals={formatToFourDecimals}
          />
        </div>
      )}

      {/* Coarse bin selection */}
      {Object.entries(coarseBinResults).map(([col, bins]) => (
        <div key={col} className="results-container">
          <h3>{col} - Select Bins to Merge</h3>

          <div style={{ marginBottom: '10px' }}>
            <label style={{ marginRight: '8px' }}>Select group:</label>
            <select
              value={activeGroup[col] || 1}
              onChange={e => setActiveGroup(prev => ({ ...prev, [col]: Number(e.target.value) }))}
            >
              {[1, 2, 3, 4, 5].map(g => (
                <option key={g} value={g}>
                  Group {g}
                </option>
              ))}
            </select>
          </div>

          <table className="cross-tab-table">
            <thead>
              <tr>
                <th>Select</th>
                <th>Bin</th>
                <th>Bad Rate (%)</th>
                <th>Total</th>
              </tr>
            </thead>
            <tbody>
              {bins.map((bin: Bin) => {
                const binLabelKey = `${col}_binned`;
                const group = activeGroup[col] || 1;
                return (
                  <tr key={bin[binLabelKey]}>
                    <td>
                      <input
                        type="checkbox"
                        checked={selectedBinGroups[col]?.[group]?.includes(bin[binLabelKey]) || false}
                        onChange={() => toggleBinSelection(col, bin[binLabelKey], group)}
                      />
                    </td>
                    <td>{bin[binLabelKey]}</td>
                    <td>{formatToFourDecimals(bin["Bad Rate"])}%</td>
                    <td>{bin["Total"]}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>

          <button onClick={() => runFineBinning(col)}>Fine Binning on Selected</button>
        </div>
      ))}

      {/* Fine bin results */}
      {Object.keys(fineBinResults).length > 0 && (
        <div className="results-section">
          <FineBinResults fineBinResults={fineBinResults} formatToFourDecimals={formatToFourDecimals} />
        </div>
      )}

      {/* Cross-tab results */}
      {Object.keys(crossTabResults).length > 0 && (
        <div className="results-section">
          <CrossTabResults
            crossTabResults={crossTabResults}
            formatToFourDecimals={formatToFourDecimals}
            selectedBins={Object.fromEntries(
              Object.entries(selectedBinGroups).map(([col, groups]) => [col, Object.values(groups).flat()])
            )}
            onBinToggle={(col, bin) => toggleBinSelection(col, bin, activeGroup[col] || 1)}
          />
        </div>
      )}
    </div>
  );
};

export default SelectedColumnsPage;
