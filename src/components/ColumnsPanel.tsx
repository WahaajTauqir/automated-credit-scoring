import Pagination from './Pagination';
import './ColumnsPanel.css';
import { RefObject } from 'react';

interface ColumnPanelsProps {
  columns: string[];
  paginatedColumns: string[];
  discreteColumns: string[];
  continuousColumns: string[];
  targetVariable: string;
  targetCounts: { [key: string]: number };
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
  datasetPath: string;
  recordId?: number;
  showCheckboxes?: boolean; // New prop to control checkbox visibility
  columnListRef?: RefObject<HTMLDivElement>; // Ref for dynamic pagination calculation
}

const ColumnPanels = ({
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
  toggleSelectAllDiscrete,
  toggleSelectAllContinuous,
  datasetPath,
  recordId,
  showCheckboxes = true, // Default to true for backward compatibility
  columnListRef,
}: ColumnPanelsProps) => {
  return (
    <div className="columns-layout">
      {/* All Columns */}
      <div className="column-panel">
        <h3>All Columns</h3>
        <p className="column-count">Total: {columns.length} columns</p>
        <div className="column-list" ref={columnListRef}>
          {paginatedColumns.map((col, idx) => (
            <div key={idx} className="column-box">
              {col}
              <div className="radio-group">
                <label>
                  <input
                    type="radio"
                    name={`type-${col}`}
                    value="discrete"
                    checked={discreteColumns.includes(col)}
                    onChange={() => handleTypeChange(col, 'discrete')}
                  />
                  Discrete
                </label>
                <label>
                  <input
                    type="radio"
                    name={`type-${col}`}
                    value="continuous"
                    checked={continuousColumns.includes(col)}
                    onChange={() => handleTypeChange(col, 'continuous')}
                  />
                  Continuous
                </label>
              </div>
            </div>
          ))}
        </div>
        <button
          className="assign-button"
          onClick={async () => {
            // Compute remaining columns locally to both update UI and persist to DB in one click
            const selectedDiscrete = new Set(discreteColumns);
            const remaining = columns.filter(
              (col) => !selectedDiscrete.has(col) && col !== targetVariable
            );
            // Update parent state
            assignRemainingToContinuous();
            // Persist a single record (create if none, else update)
            try {
              await fetch('http://localhost:5000/api/upsert-single-record', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                  dataset_path: datasetPath,
                  discrete_columns: discreteColumns,
                  continuous_columns: remaining,
                  selected_columns: selectedForUnivariate,
                  target_variable: targetVariable,
                  record_id: recordId,
                })
              });
            } catch (e) {
              // Non-blocking: keep UI responsive even if persistence fails
              console.error('Failed to upsert record:', e);
            }
          }}
        >
          Send Remaining to Continuous
        </button>
        <Pagination
          currentPage={currentPage}
          totalPages={totalPages}
          onNextPage={onNextPage}
          onPrevPage={onPrevPage}
        />
      </div>

      {/* Discrete Columns */}
      <div className="column-panel">
        <h3>Discrete Columns</h3>
        {showCheckboxes && (
          <div style={{ marginBottom: '8px' }}>
            <button
              className="assign-button"
              onClick={() => toggleSelectAllDiscrete && toggleSelectAllDiscrete()}
              title="Tick/untick all discrete variables"
            >
              Tick all discrete
            </button>
          </div>
        )}
        <div className="column-list">
          {discreteColumns.length === 0 && (
            <div className="column-box">(None selected)</div>
          )}
          {discreteColumns.map((col, idx) => (
            <div key={idx} className="column-box">
              {showCheckboxes ? (
                <label>
                  <input
                    type="checkbox"
                    checked={selectedForUnivariate.includes(col)}
                    onChange={() => toggleSelectedForUnivariate(col)}
                  />
                  {col}
                </label>
              ) : (
                col
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Continuous Columns */}
      <div className="column-panel">
        <h3>Continuous Columns</h3>
        {showCheckboxes && (
          <div style={{ marginBottom: '8px' }}>
            <button
              className="assign-button"
              onClick={() => toggleSelectAllContinuous && toggleSelectAllContinuous()}
              title="Tick/untick all continuous variables"
            >
              Tick all continuous
            </button>
          </div>
        )}
        <div className="column-list">
          {continuousColumns.length === 0 && (
            <div className="column-box">(None selected)</div>
          )}
          {continuousColumns.map((col, idx) => (
            <div key={idx} className="column-box">
              {showCheckboxes ? (
                <label>
                  <input
                    type="checkbox"
                    checked={selectedForUnivariate.includes(col)}
                    onChange={() => toggleSelectedForUnivariate(col)}
                  />
                  {col}
                </label>
              ) : (
                col
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Target Column + Class Distribution Donut */}
      <div className="column-panel" style={{ minWidth: '240px' }}>
        <h3>Target Variable</h3>
        <div className="column-list">
          <label htmlFor="target-select">Select Target Column:</label>
          <select
            id="target-select"
            value={targetVariable}
            onChange={(e) => setTargetVariable(e.target.value)}
          >
            <option value="">-- Select --</option>
            {columns.map((col, idx) => (
              <option key={idx} value={col}>
                {col}
              </option>
            ))}
          </select>
          {targetVariable && (
            <>
              <p className="selected-target">
                Selected: {targetVariable}
              </p>
              <div className="donut-chart">
                {Object.entries(targetCounts).map(
                  ([label, count], idx) => {
                    const total = Object.values(
                      targetCounts
                    ).reduce((a, b) => a + b, 0);
                    const percent = total
                      ? ((count / total) * 100).toFixed(1)
                      : 0;
                    const color =
                      label === '1'
                        ? '#f85149'
                        : '#238636';

                    return (
                      <div
                        className="donut-segment"
                        key={idx}
                      >
                        <svg
                          width="130"
                          height="120"
                          viewBox="0 0 36 36"
                        >
                          <path
                            className="circle-bg"
                            d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                            fill="none"
                            stroke="#30363d"
                            strokeWidth="3"
                          />
                          <path
                            className="circle"
                            stroke={color}
                            strokeWidth="3"
                            fill="none"
                            strokeDasharray={`${percent}, 100`}
                            d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                          />
                          <text
                            x="18"
                            y="20.35"
                            className="percentage"
                            textAnchor="middle"
                            fill={color}
                          >
                            {label}: {percent}%
                          </text>
                        </svg>
                      </div>
                    );
                  }
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
};

export default ColumnPanels;
