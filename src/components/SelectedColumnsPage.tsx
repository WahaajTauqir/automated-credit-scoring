import { useLocation, useNavigate } from 'react-router-dom';
import { useState } from 'react';
import UnivariateResults from './UnivariateResults';
import './SelectedColumnsPage.css';

const SelectedColumnsPage = () => {
  const { state } = useLocation();
  const {
    selectedColumns: navSelectedColumns,
    discreteColumns,
    continuousColumns,
    targetVariable
  } = state || {};

  interface BinStats { [key: string]: any; }
  interface Bin { [key: string]: any; }

  const [activeColumn, setActiveColumn] = useState<string>(navSelectedColumns?.[0] || '');
  const navigate = useNavigate();
  const handleGoHome = () => navigate('/');

  const [loading, setLoading] = useState(false);
  const [univariateResults, setUnivariateResults] = useState<Record<string, any>>({});
  const [coarseBinResults, setCoarseBinResults] = useState<Record<string, BinStats[]>>({});
  const [selectedBinGroups, setSelectedBinGroups] = useState<Record<string, Record<number, any[]>>>({});
  const [activeGroup, setActiveGroup] = useState<Record<string, number>>({});
  const [fineBinResults, setFineBinResults] = useState<Record<string, BinStats[]>>({});

  const formatToFourDecimals = (value: any) => (typeof value === 'number' ? value.toFixed(4) : String(value));

  // Fetch univariate & coarse bins
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
        // Continuous: call backend API for merging
        let binMerges: Record<string, string[]> = {};
        const selectedBins = colGroupsSnapshot[1] || [];
        if (selectedBins.length === 0) {
          alert("Select at least one bin to merge for continuous variable");
          setLoading(false);
          return;
        }
        binMerges[selectedBins.join("_")] = selectedBins;

        const res = await fetch('http://localhost:5000/api/fine-bin', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ variable: col, target: targetVariable, type: varType, bin_merges: binMerges }),
        });
        const fineBinData = await res.json();
        if (!fineBinData.error) {
          setFineBinResults(prev => ({ ...prev, [col]: fineBinData.stats || [] }));
          const binsToRemove = Object.values(binMerges).flat();
          setCoarseBinResults(prev => ({
            ...prev,
            [col]: (prev[col] || []).filter(bin => !binsToRemove.includes(bin[col + '_binned']))
          }));
          setSelectedBinGroups(prev => ({ ...prev, [col]: {} }));
        } else alert(fineBinData.error);

      } else {
        // Discrete: handle merging locally
        const allBins = coarseBinResults[col] || [];
        const mergedBins: BinStats[] = fineBinResults[col] || [];
        const totalRecords = allBins.reduce((sum, bin) => sum + (bin.Total || 0), 0);

        Object.values(colGroupsSnapshot).forEach(groupBins => {
          if (!groupBins || groupBins.length === 0) return;
          const mergedStats = allBins
            .filter(bin => groupBins.includes(bin[col + "_binned"]))
            .reduce((acc, bin) => {
              acc.Total += bin.Total || 0;
              acc.Bad += bin.Bad || 0;
              acc.Good += bin.Good || 0;
              return acc;
            }, { Total: 0, Bad: 0, Good: 0 });
          mergedStats["Bad Rate"] = mergedStats.Total ? (mergedStats.Bad / mergedStats.Total) * 100 : 0;
          mergedStats["Freq%"] = totalRecords ? (mergedStats.Total / totalRecords) * 100 : 0;
          mergedStats[col + "_fine_binned"] = groupBins.join(", ");
          mergedBins.push(mergedStats);
        });

        const mergedBinValues = Object.values(colGroupsSnapshot).flat();
        const remainingBins = allBins
          .filter(bin => !mergedBinValues.includes(bin[col + "_binned"]))
          .map(bin => ({
            ...bin,
            [col + "_fine_binned"]: bin[col + "_binned"],
            "Freq%": totalRecords ? ((bin.Total || 0) / totalRecords) * 100 : 0,
            "Bad Rate": bin.Total ? ((bin.Bad || 0) / bin.Total) * 100 : 0
          }));

        setFineBinResults(prev => ({ ...prev, [col]: [...remainingBins, ...mergedBins] }));
        setSelectedBinGroups(prev => ({ ...prev, [col]: {} }));
      }
    } catch (err) {
      console.error(err);
      alert("Error running fine binning");
    } finally {
      setLoading(false);
    }
  };

  const handleDropColumn = (col: string) => {
    if (col === activeColumn) setActiveColumn('');
    setUnivariateResults(prev => { const { [col]: _, ...rest } = prev; return rest; });
    setCoarseBinResults(prev => { const { [col]: _, ...rest } = prev; return rest; });
    setFineBinResults(prev => { const { [col]: _, ...rest } = prev; return rest; });
    setSelectedBinGroups(prev => { const { [col]: _, ...rest } = prev; return rest; });
    setActiveGroup(prev => { const { [col]: _, ...rest } = prev; return rest; });
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
              {(coarseBinResults[activeColumn] as Bin[]).map((bin, idx) => {
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
        <button className="file-upload-label" onClick={handleGoHome}>Save</button>
      </div>
    </div>
  );
};

export default SelectedColumnsPage;
