import { useEffect, useState } from 'react';
import CSVReader from './components/CSVReader';
import Navbar from './components/Navbar';
import ColumnPanels from './components/ColumnsPanel';
import UnivariateResults from './components/UnivariateResults';
import FineBinResults from './components/FInebinResults';
import CrossTabResults from './components/CresstabResults';
import './App.css';

function App() {
  const [columns, setColumns] = useState<string[]>([]);
  const [discreteColumns, setDiscreteColumns] = useState<string[]>([]);
  const [continuousColumns, setContinuousColumns] = useState<string[]>([]);
  const [targetVariable, setTargetVariable] = useState<string>('');
  const [univariateResults, setUnivariateResults] = useState<any>({});
  const [fineBinResults, setFineBinResults] = useState<any>({});
  const [crossTabResults, setCrossTabResults] = useState<any>({});
  const [loading, setLoading] = useState<boolean>(false);
  const [targetCounts, setTargetCounts] = useState<{ [key: string]: number }>({});
  const [selectedForUnivariate, setSelectedForUnivariate] = useState<string[]>([]);


  // Pagination setup
  const columnsPerPage = 7;
  const [currentPage, setCurrentPage] = useState<number>(1);
  const totalPages = Math.ceil(columns.length / columnsPerPage);
  const paginatedColumns = columns.slice(
    (currentPage - 1) * columnsPerPage,
    currentPage * columnsPerPage
  );

  const handleCSVUploaded = (headers: string[]) => {
    setColumns(headers);
    setDiscreteColumns([]);
    setContinuousColumns([]);
    setTargetVariable('');
    setUnivariateResults({});
    setFineBinResults({});
    setCrossTabResults({});
    setCurrentPage(1);
    setTargetCounts({});
  };
  const toggleSelectedForUnivariate = (col: string) => {
    setSelectedForUnivariate((prev) =>
      prev.includes(col) ? prev.filter((c) => c !== col) : [...prev, col]
    );
  };
  const assignRemainingToContinuous = () => {
    const selectedDiscrete = new Set(discreteColumns);
    const remaining = columns.filter(
      (col) => !selectedDiscrete.has(col) && col !== targetVariable
    );
    setContinuousColumns(remaining);
  };
  const handleTypeChange = (column: string, type: string) => {
    if (type === 'discrete') {
      setDiscreteColumns((prev) => [...new Set([...prev, column])]);
      setContinuousColumns((prev) => prev.filter((c) => c !== column));
    } else if (type === 'continuous') {
      setContinuousColumns((prev) => [...new Set([...prev, column])]);
      setDiscreteColumns((prev) => prev.filter((c) => c !== column));
    }
  };

  const handleRunUnivariate = async () => {
    if (!targetVariable) {
      alert('Please select a target variable.');
      return;
    }

    if (selectedForUnivariate.length === 0) {
      alert('Please select at least one column to analyze.');
      return;
    }

    setLoading(true);
    try {
      // Split selected columns into discrete and continuous
      const selectedDiscrete = selectedForUnivariate.filter((col) => discreteColumns.includes(col));
      const selectedContinuous = selectedForUnivariate.filter((col) => continuousColumns.includes(col));

      const univariateRes = await fetch('http://localhost:5000/api/univariate-analysis', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          discrete: selectedDiscrete,
          continuous: selectedContinuous,
          target: targetVariable,
        }),
      });

      const univariateData = await univariateRes.json();
      if (univariateData.error) {
        alert(univariateData.error);
        setLoading(false);
        return;
      }
      setUnivariateResults(univariateData);

      // Fine binning only for selected columns
      const fineBinResultsTemp: any = {};
      for (const col of selectedForUnivariate) {
        const varType = discreteColumns.includes(col) ? 'discrete' : 'continuous';

        const fineBinRes = await fetch('http://localhost:5000/api/fine-bin', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            variable: col,
            target: targetVariable,
            type: varType,
          }),
        });
        const fineBinData = await fineBinRes.json();
        if (!fineBinData.error) {
          fineBinResultsTemp[col] = fineBinData.stats;
        }
      }
      setFineBinResults(fineBinResultsTemp);

      // Cross-tabulation
      const crossTabRes = await fetch('http://localhost:5000/api/cross-tab-view', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          variables: selectedForUnivariate,
          target: targetVariable,
        }),
      });
      const crossTabData = await crossTabRes.json();
      if (!crossTabData.error) {
        setCrossTabResults(crossTabData);
      }
    } catch (err) {
      alert('Analysis failed.');
    } finally {
      setLoading(false);
    }
  };
  const fetchTargetCounts = async (col: string) => {
    try {
      const res = await fetch('http://localhost:5000/api/target-distribution', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ column: col }),
      });
      const data = await res.json();
      if (!data.error) {
        setTargetCounts(data);
      }
    } catch (err) {
      console.error('Failed to fetch target counts:', err);
    }
  };

  useEffect(() => {
    if (targetVariable) {
      fetchTargetCounts(targetVariable);
    }
  }, [targetVariable]);

  const handleNextPage = () => {
    if (currentPage < totalPages) setCurrentPage((prev) => prev + 1);
  };

  const handlePrevPage = () => {
    if (currentPage > 1) setCurrentPage((prev) => prev - 1);
  };

  // Helper function to format numbers to 4 decimal places
  const formatToFourDecimals = (value: any): string => {
    if (typeof value === 'number') {
      return value.toFixed(4);
    }
    return String(value);
  };

  return (
    <>
      <Navbar />
      <div className="app-container">
        {columns.length === 0 ? (
          <div className="upload-wrapper">
            <CSVReader onCSVUploaded={handleCSVUploaded} />
          </div>
        ) : (
          <>
            <ColumnPanels
              columns={columns}
              paginatedColumns={paginatedColumns}
              discreteColumns={discreteColumns}
              continuousColumns={continuousColumns}
              targetVariable={targetVariable}
              targetCounts={targetCounts}
              handleTypeChange={handleTypeChange}
              setTargetVariable={setTargetVariable}
              currentPage={currentPage}
              totalPages={totalPages}
              onNextPage={handleNextPage}
              onPrevPage={handlePrevPage}
              assignRemainingToContinuous={assignRemainingToContinuous}
              selectedForUnivariate={selectedForUnivariate}
              toggleSelectedForUnivariate={toggleSelectedForUnivariate}
            />
            <div style={{ marginTop: '30px', textAlign: 'center' }}>
              <button
                className="file-upload-label"
                onClick={handleRunUnivariate}
                disabled={loading}
              >
                {loading ? 'Running Analysis...' : 'Run Analysis'}
              </button>
            </div>
            <UnivariateResults
              univariateResults={univariateResults}
              formatToFourDecimals={formatToFourDecimals}
            />
            <FineBinResults
              fineBinResults={fineBinResults}
              formatToFourDecimals={formatToFourDecimals}
            />
            <CrossTabResults
              crossTabResults={crossTabResults}
              formatToFourDecimals={formatToFourDecimals}
            />
          </>
        )}
      </div>
    </>
  );
}

export default App;