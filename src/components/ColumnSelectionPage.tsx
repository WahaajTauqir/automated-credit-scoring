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
  formatToFourDecimals
}: ColumnSelectionPageProps) => {
  return (
    <div>
      <Navbar />
      <div className="app-container">
        {columns.length === 0 ? (
          <p style={{ textAlign: 'center', width: '100%' }}>No dataset loaded. Go back to the Dashboard and upload a CSV.</p>
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
