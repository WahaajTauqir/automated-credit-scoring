import { useLocation } from 'react-router-dom';
import { useState } from 'react';
import UnivariateResults from './UnivariateResults';
import FineBinResults from './FInebinResults';
import CrossTabResults from './CresstabResults';
import './SelectedColumnsPage.css';

const SelectedColumnsPage = () => {
  const { state } = useLocation();
  const { selectedColumns, discreteColumns, continuousColumns, targetVariable } = state || {};
  
  const [loading, setLoading] = useState(false);
  const [univariateResults, setUnivariateResults] = useState({});
  const [fineBinResults, setFineBinResults] = useState({});
  const [crossTabResults, setCrossTabResults] = useState({});
  
  const formatToFourDecimals = (value: any) => {
    if (typeof value === 'number') return value.toFixed(4);
    return String(value);
  };

  const handleColumnClick = async (col: string) => {
    setLoading(true);
    try {
      const varType = discreteColumns.includes(col) ? 'discrete' : 'continuous';

      // Univariate
      const univariateRes = await fetch('http://localhost:5000/api/univariate-analysis', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          discrete: varType === 'discrete' ? [col] : [],
          continuous: varType === 'continuous' ? [col] : [],
          target: targetVariable
        })
      });
      const univariateData = await univariateRes.json();
      setUnivariateResults({ [col]: univariateData[col] || univariateData });

      // Fine binning
      const fineBinRes = await fetch('http://localhost:5000/api/fine-bin', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          variable: col,
          target: targetVariable,
          type: varType
        })
      });
      const fineBinData = await fineBinRes.json();
      if (!fineBinData.error) {
        setFineBinResults({ [col]: fineBinData.stats });
      }

      // Crosstab
      const crossTabRes = await fetch('http://localhost:5000/api/cross-tab-view', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          variables: [col],
          target: targetVariable
        })
      });
      const crossTabData = await crossTabRes.json();
      if (!crossTabData.error) {
        setCrossTabResults({ [col]: crossTabData[col] || crossTabData });
      }

    } catch (err) {
      alert('Error fetching column analysis');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="page-container">
      <h2 className="page-title">Select a Column to View Results</h2>
      
      <div className="columns-grid">
        {selectedColumns?.map((col: string) => (
          <div
            key={col}
            className="column-card"
            onClick={() => handleColumnClick(col)}
          >
            <h4>{col}</h4>
            <small>{discreteColumns.includes(col) ? 'Discrete' : 'Continuous'}</small>
          </div>
        ))}
      </div>

      {loading && <p className="loading-text">Loading analysis...</p>}

      {Object.keys(univariateResults).length > 0 && (
        <div className="results-section">
          <UnivariateResults
            univariateResults={univariateResults}
            formatToFourDecimals={formatToFourDecimals}
          />
        </div>
      )}

      {Object.keys(fineBinResults).length > 0 && (
        <div className="results-section">
          <FineBinResults
            fineBinResults={fineBinResults}
            formatToFourDecimals={formatToFourDecimals}
          />
        </div>
      )}

      {Object.keys(crossTabResults).length > 0 && (
        <div className="results-section">
          <CrossTabResults
            crossTabResults={crossTabResults}
            formatToFourDecimals={formatToFourDecimals}
          />
        </div>
      )}
    </div>
  );
};

export default SelectedColumnsPage;
