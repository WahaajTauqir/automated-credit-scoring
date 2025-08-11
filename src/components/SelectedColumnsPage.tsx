import { useLocation } from 'react-router-dom';
import { useState } from 'react';
import UnivariateResults from './UnivariateResults';
import FineBinResults from './FInebinResults';
import CrossTabResults from './CresstabResults';
import './SelectedColumnsPage.css';

const SelectedColumnsPage = () => {
  const { state } = useLocation();
  const { selectedColumns, discreteColumns, continuousColumns, targetVariable } = state || {};

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
    } catch {
      alert('Error fetching coarse bin results');
    } finally {
      setLoading(false);
    }
  };

  // Toggle bin selection in a group for a column
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
      body: JSON.stringify({
        variable: col,
        target: targetVariable,
        type: varType,
        bin_merges: colGroupsSnapshot,
      }),
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
