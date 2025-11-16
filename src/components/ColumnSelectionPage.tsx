import ColumnPanels from './ColumnsPanel';
import Navbar from './Navbar';

interface ColumnSelectionPageProps {
  columns: string[];
  paginatedColumns: string[];
  discreteColumns: string[];
  continuousColumns: string[];
  targetVariable: string;
  targetCounts: Record<string, number>;
  handleTypeChange: (column: string, type: string) => void;
  setTargetVariable: (value: string) => void;
  currentPage: number;
  totalPages: number;
  onNextPage: () => void;
  onPrevPage: () => void;
  assignRemainingToContinuous: () => void;
  selectedForUnivariate: string[];
  toggleSelectedForUnivariate: (col: string) => void;
  toggleSelectAllDiscrete?: (selectAll?: boolean) => void;
  toggleSelectAllContinuous?: (selectAll?: boolean) => void;
  handleFineBin: (column: string) => Promise<void>;
  handleProceedToSelectedColumns: () => Promise<void> | void;
  univariateResults: Record<string, any>;
  fineBinResults: Record<string, any>;
  crossTabResults: Record<string, any>;
  selectedBinGroups: Record<string, any[]>;
  toggleBinSelection: (col: string, binValue: any) => void;
  formatToFourDecimals: (value: any) => string;
  restoring?: boolean;
  expectedColumns?: string[];
  onUploadReplacement?: (headers: string[], rows: any[], path?: string) => void;
  datasetPath: string;
  recordId?: number;
}

const ColumnSelectionPage = ({
  columns,
  paginatedColumns,
  discreteColumns,
  continuousColumns,
  targetVariable,
  targetCounts,
  handleTypeChange,
  setTargetVariable,
  currentPage,
  totalPages,
  onNextPage,
  onPrevPage,
  assignRemainingToContinuous,
  selectedForUnivariate,
  toggleSelectedForUnivariate,
  handleFineBin,
  handleProceedToSelectedColumns,
  toggleSelectAllDiscrete,
  toggleSelectAllContinuous,
  restoring,
  expectedColumns,
  onUploadReplacement,
  datasetPath,
  recordId
}: ColumnSelectionPageProps) => {
  const needsUpload = restoring && columns.length === 0 && expectedColumns && expectedColumns.length > 0;
  const hasWrongCsv = !restoring && columns.length > 0 && expectedColumns && expectedColumns.length > 0 && expectedColumns.some(col => !columns.includes(col));
  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column' }}>
      <Navbar />
      <div className="app-container" style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
        {needsUpload && (
          <div style={{ textAlign: 'center', width: '100%' }}>
            <p>Saved analysis found. Please upload the corresponding CSV to continue.</p>
            {onUploadReplacement && (
              <div style={{ marginTop: '12px' }}>
                <p style={{ fontSize: '0.9rem', color: '#8b949e' }}>Expected columns sample: {expectedColumns.slice(0,10).join(', ')}{expectedColumns.length>10?'...':''}</p>
              </div>
            )}
          </div>
        )}
        {hasWrongCsv && (
          <div style={{ textAlign: 'center', width: '100%', color: '#f85149', marginBottom: '16px' }}>
            Please upload the correct CSV (columns don't match saved analysis).
            {onUploadReplacement && expectedColumns && (
              <p style={{ fontSize: '0.85rem', color: '#c9d1d9' }}>Expected includes: {expectedColumns.slice(0,10).join(', ')}{expectedColumns.length>10?'...':''}</p>
            )}
          </div>
        )}
        {columns.length === 0 && !needsUpload && !restoring && (
          <p style={{ textAlign: 'center', width: '100%' }}>No dataset loaded. Upload a CSV to begin.</p>
        )}
        {columns.length > 0 && !hasWrongCsv && (
          <>
            <div style={{ display: 'flex', justifyContent: 'center', gap: '12px', marginBottom: '16px' }}>
              <button
                className="assign-button"
                onClick={async () => {
                  // Classify ALL columns using backend AI endpoint (not just current page)
                  try {
                    const colsToClassify = columns; // Use ALL columns, not paginatedColumns
                    if (!colsToClassify || colsToClassify.length === 0) {
                      alert('No columns to classify');
                      return;
                    }
                    
                    // Show progress message
                    alert(`Starting AI classification for ${colsToClassify.length} columns...`);
                    
                    // Prepare sample data by fetching actual CSV data
                    let sampleData: Record<string, any[]> = {};
                    try {
                      // Fetch sample values from the uploaded CSV
                      const sampleResp = await fetch('http://localhost:5000/api/csv-samples', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ columns: colsToClassify, sample_size: 20, record_id: recordId })
                      });
                      if (sampleResp.ok) {
                        sampleData = await sampleResp.json();
                      } else {
                        console.warn('Could not fetch CSV samples, using empty data');
                        colsToClassify.forEach(col => {
                          sampleData[col] = [];
                        });
                      }
                    } catch (e) {
                      console.warn('Could not fetch CSV data for samples:', e);
                      // Fallback: send empty samples
                      colsToClassify.forEach(col => {
                        sampleData[col] = [];
                      });
                    }
                    
                    const resp = await fetch('http://localhost:5000/api/ai-classify-columns', {
                      method: 'POST',
                      headers: { 'Content-Type': 'application/json' },
                      body: JSON.stringify({ columns: colsToClassify, sampleData, record_id: recordId })
                    });
                    const data = await resp.json();
                    if (data && !data.error) {
                      // Apply classifications via provided handler
                      let discreteCount = 0;
                      let continuousCount = 0;
                      Object.entries(data).forEach(([col, typ]) => {
                        if (col && (typ === 'discrete' || typ === 'continuous')) {
                          handleTypeChange(col, typ as string);
                          if (typ === 'discrete') discreteCount++;
                          else continuousCount++;
                        }
                      });
                      alert(`AI classification complete!\nClassified ${discreteCount} discrete and ${continuousCount} continuous variables.`);
                    } else {
                      console.error('AI classify error', data);
                      alert('AI classification failed. See console for details.');
                    }
                  } catch (e) {
                    console.error('AI classification request failed', e);
                    alert('AI classification failed. See console for details.');
                  }
                }}
              >
                AI Separation (All Columns)
              </button>
            </div>

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
              onNextPage={onNextPage}
              onPrevPage={onPrevPage}
              assignRemainingToContinuous={assignRemainingToContinuous}
              selectedForUnivariate={selectedForUnivariate}
              toggleSelectedForUnivariate={toggleSelectedForUnivariate}
              toggleSelectAllDiscrete={toggleSelectAllDiscrete}
              toggleSelectAllContinuous={toggleSelectAllContinuous}
              handleFineBin={handleFineBin}
              datasetPath={datasetPath}
              recordId={recordId}
            />

            <div style={{ marginTop: '30px', textAlign: 'center' }}>
              <button className="file-upload-label" onClick={handleProceedToSelectedColumns}>
                Proceed to Selected Columns
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
};

export default ColumnSelectionPage;
