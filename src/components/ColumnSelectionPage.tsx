import ColumnPanels from './ColumnsPanel';
import UnivariateResults from './UnivariateResults';
import FineBinResults from './FInebinResults';
import CrossTabResults from './CresstabResults';
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
  univariateResults,
  fineBinResults,
  crossTabResults,
  selectedBinGroups,
  toggleBinSelection,
  formatToFourDecimals,
  restoring,
  expectedColumns,
  onUploadReplacement
}: ColumnSelectionPageProps) => {
  const needsUpload = restoring && columns.length === 0 && expectedColumns && expectedColumns.length > 0;
  const hasWrongCsv = !restoring && columns.length > 0 && expectedColumns && expectedColumns.length > 0 && expectedColumns.some(col => !columns.includes(col));
  return (
    <div>
      <Navbar />
      <div className="app-container">
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
              handleFineBin={handleFineBin}
            />

            <div style={{ marginTop: '30px', textAlign: 'center' }}>
              <button className="file-upload-label" onClick={handleProceedToSelectedColumns}>
                Proceed to Selected Columns
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
              selectedBins={selectedBinGroups}
              onBinToggle={toggleBinSelection}
            />
          </>
        )}
      </div>
    </div>
  );
};

export default ColumnSelectionPage;
