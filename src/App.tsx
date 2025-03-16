import { useState } from 'react';
import CSVReader from './components/CSVReader';
import ColumnsDialog from './components/ColumnsDialog';
import './App.css';

function App() {
    const [columns, setColumns] = useState<string[]>([]);
    const [isDialogOpen, setIsDialogOpen] = useState<boolean>(false);
    const [isFileSelected, setIsFileSelected] = useState<boolean>(false);

    const handleCSVUploaded = (headers: string[]) => {
        setColumns(headers);
        setIsDialogOpen(true);
        setIsFileSelected(true); // Mark that a file has been selected
    };

    const handleCloseDialog = () => {
        setIsDialogOpen(false);
        // We don't reset isFileSelected here so that the button remains visible
    };

    const handleOpenDialog = () => {
        setIsDialogOpen(true);
    };

    return (
        <div className="app-container">
            <h1>Automated Credit Scoring</h1>
            <h2>CSV File Reader</h2>
            <div style={{ width: '100%', display: 'flex', justifyContent: 'center' }}>
                <CSVReader onCSVUploaded={handleCSVUploaded} />
            </div>

            {isFileSelected && !isDialogOpen && (
                <div className="view-columns-button-container">
                    <button className="view-columns-button" onClick={handleOpenDialog}>
                        View Selected File Columns
                    </button>
                </div>
            )}

            {isDialogOpen && (
                <ColumnsDialog
                    columns={columns}
                    isOpen={isDialogOpen}
                    onClose={handleCloseDialog}
                />
            )}
        </div>
    );
}

export default App;