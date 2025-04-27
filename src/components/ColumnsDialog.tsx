import { useState, useEffect } from 'react';
import './ColumnsDialog.css';

interface ColumnsDialogProps {
    columns: string[];
    isOpen: boolean;
    onClose: () => void;
    onSelectColumns: (selectedColumns: string[]) => void;
}

const ColumnsDialog = ({ columns, isOpen, onClose, onSelectColumns }: ColumnsDialogProps) => {
    const [selectedColumns, setSelectedColumns] = useState<string[]>([]);

    // Reset selected columns when dialog opens with new columns
    useEffect(() => {
        if (isOpen) {
            setSelectedColumns([]);
        }
    }, [isOpen, columns]);

    if (!isOpen) return null;

    const toggleColumnSelection = (column: string) => {
        if (selectedColumns.includes(column)) {
            setSelectedColumns(selectedColumns.filter(col => col !== column));
        } else {
            setSelectedColumns([...selectedColumns, column]);
        }
    };

    const handleSelect = () => {
        onSelectColumns(selectedColumns);
        onClose();
    };

    return (
        <div className="dialog-overlay">
            <div className="dialog-content">
                <div className="dialog-header">
                    <h2>CSV Columns</h2>
                    <div style={{ display: 'flex', gap: '10px' }}>
                        <button
                            onClick={handleSelect}
                            style={{
                                background: 'none',
                                border: 'none',
                                fontSize: '18px',
                                cursor: 'pointer',
                                color: '#0066cc',
                                fontWeight: 'bold'
                            }}
                        >
                            Select
                        </button>
                        <button className="close-button" onClick={onClose}>×</button>
                    </div>
                </div>
                <div className="dialog-body">
                    <p>The CSV file contains the following {columns.length} columns. Click to select:</p>
                    <div className="columns-container">
                        {columns.map((column, index) => (
                            <button
                                key={index}
                                className="column-item"
                                onClick={() => toggleColumnSelection(column)}
                                style={{
                                    backgroundColor: selectedColumns.includes(column) ? '#0066cc' : '#f5f7fa',
                                    color: selectedColumns.includes(column) ? 'white' : 'black',
                                    cursor: 'pointer',
                                    textAlign: 'left'
                                }}
                            >
                                {column || <em>(Empty column)</em>}
                            </button>
                        ))}
                    </div>
                </div>
                <div className="dialog-footer">
                    <button className="ok-button" onClick={onClose}>Close</button>
                </div>
            </div>
        </div>
    );
};

export default ColumnsDialog;