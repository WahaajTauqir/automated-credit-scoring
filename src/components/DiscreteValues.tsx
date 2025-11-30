import { useState } from 'react';
import './DiscreteValues.css';

interface DiscreteValuesDropdownProps {
  rangeValue: string;
  maxPreviewItems?: number;
}

export const DiscreteValuesDropdown: React.FC<DiscreteValuesDropdownProps> = ({ 
  rangeValue, 
  maxPreviewItems = 3 
}) => {
  const [isExpanded, setIsExpanded] = useState(false);

  if (!rangeValue || rangeValue === '—') {
    return <span>—</span>;
  }

  // Split the range value by comma to get individual values
  const values = rangeValue.split(',').map(v => v.trim()).filter(v => v.length > 0);

  // If there are few values, just show them all
  if (values.length <= maxPreviewItems) {
    return <span title={rangeValue}>{rangeValue}</span>;
  }

  // Show preview with dropdown
  const previewValues = values.slice(0, maxPreviewItems);
  const remainingCount = values.length - maxPreviewItems;

  return (
    <div className="discrete-values-dropdown">
      <button
        type="button"
        className={`discrete-values-toggle ${isExpanded ? 'expanded' : ''}`}
        onClick={(e) => {
          e.stopPropagation();
          setIsExpanded(!isExpanded);
        }}
        title={isExpanded ? 'Click to collapse' : `Click to show all ${values.length} values`}
        aria-label={isExpanded ? 'Collapse values' : `Expand to show all ${values.length} values`}
      >
        <span className="preview-values">
          {previewValues.join(', ')}
          {!isExpanded && (
            <span className="more-indicator"> +{remainingCount} more</span>
          )}
        </span>
        <svg 
          className="dropdown-icon" 
          width="12" 
          height="12" 
          viewBox="0 0 12 12" 
          fill="none"
          aria-hidden="true"
        >
          <path 
            d="M3 5L6 8L9 5" 
            stroke="currentColor" 
            strokeWidth="1.5" 
            strokeLinecap="round" 
            strokeLinejoin="round"
          />
        </svg>
      </button>
      
      {isExpanded && (
        <div className="discrete-values-list">
          <div className="values-scroll">
            {values.map((value, idx) => (
              <div key={idx} className="value-item">
                {value}
              </div>
            ))}
          </div>
          <div className="values-footer">
            Total: {values.length} value{values.length !== 1 ? 's' : ''}
          </div>
        </div>
      )}
    </div>
  );
};

export default DiscreteValuesDropdown;
