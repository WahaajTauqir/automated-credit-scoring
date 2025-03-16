import './ColumnsDialog.css';

interface ColumnsDialogProps {
    columns: string[];
    isOpen: boolean;
    onClose: () => void;
}

const ColumnsDialog = ({ columns, isOpen, onClose }: ColumnsDialogProps) => {
    if (!isOpen) return null;

    return (
        <div className="dialog-overlay">
            <div className="dialog-content">
                <div className="dialog-header">
                    <h2>CSV Columns</h2>
                    <button className="close-button" onClick={onClose}>×</button>
                </div>
                <div className="dialog-body">
                    <p>The CSV file contains the following {columns.length} columns:</p>
                    <div className="columns-container">
                        {columns.map((column, index) => (
                            <div key={index} className="column-item">
                                {column || <em>(Empty column)</em>}
                            </div>
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