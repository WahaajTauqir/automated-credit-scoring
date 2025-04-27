import './ColumnsDialog.css';

interface SelectedColumnsDialogProps {
    columns: string[];
    isOpen: boolean;
    onClose: () => void;
}

const SelectedColumnsDialog = ({ columns, isOpen, onClose }: SelectedColumnsDialogProps) => {
    if (!isOpen) return null;

    return (
        <div className="dialog-overlay">
            <div className="dialog-content">
                <div className="dialog-header">
                    <h2>Selected Columns</h2>
                    <button className="close-button" onClick={onClose}>×</button>
                </div>
                <div className="dialog-body">
                    {columns.length === 0 ? (
                        <p>No columns selected. Please select columns first.</p>
                    ) : (
                        <>
                            <p>You have selected the following {columns.length} columns:</p>
                            <div className="columns-container">
                                {columns.map((column, index) => (
                                    <div
                                        key={index}
                                        className="column-item"
                                        style={{
                                            backgroundColor: '#f5f7fa',
                                            padding: '10px',
                                            borderRadius: '6px',
                                            marginBottom: '6px'
                                        }}
                                    >
                                        {column || <em>(Empty column)</em>}
                                    </div>
                                ))}
                            </div>
                        </>
                    )}
                </div>
                <div className="dialog-footer">
                    <button className="ok-button" onClick={onClose}>Close</button>
                </div>
            </div>
        </div>
    );
};

export default SelectedColumnsDialog;