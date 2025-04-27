import { useState } from 'react';
import CSVReader from './components/CSVReader';
import ColumnsDialog from './components/ColumnsDialog';
import SelectedColumnsDialog from './components/SelectedColumnsDialog';
import SegmentsDialog from './components/SegmentsDialog';
import './App.css';

function App() {
    const [columns, setColumns] = useState<string[]>([]);
    const [selectedColumns, setSelectedColumns] = useState<string[]>([]);
    const [isDialogOpen, setIsDialogOpen] = useState<boolean>(false);
    const [isSelectedColumnsDialogOpen, setIsSelectedColumnsDialogOpen] = useState<boolean>(false);
    const [isSegmentsDialogOpen, setIsSegmentsDialogOpen] = useState<boolean>(false);
    const [isFileSelected, setIsFileSelected] = useState<boolean>(false);

    const handleCSVUploaded = (headers: string[]) => {
        setColumns(headers);
        setIsDialogOpen(true);
        setIsFileSelected(true);
    };

    const handleCloseDialog = () => {
        setIsDialogOpen(false);
    };

    const handleOpenDialog = () => {
        setIsDialogOpen(true);
    };

    const handleSelectColumns = (selected: string[]) => {
        console.log("Selected columns:", selected); // Debug logging
        setSelectedColumns(selected);
    };

    const handleOpenSelectedColumnsDialog = () => {
        console.log("Opening selected columns dialog. Columns:", selectedColumns); // Debug logging
        setIsSelectedColumnsDialogOpen(true);
    };

    const handleCloseSelectedColumnsDialog = () => {
        setIsSelectedColumnsDialogOpen(false);
    };

    const handleCreateSegments = () => {
        setIsSegmentsDialogOpen(true);
    };

    const handleCloseSegmentsDialog = () => {
        setIsSegmentsDialogOpen(false);
    };

    return (
        <div className="app-container">
            <h1>Automated Credit Scoring</h1>
            <h2>CSV File Reader</h2>
            <div style={{ width: '100%', display: 'flex', justifyContent: 'center' }}>
                <CSVReader onCSVUploaded={handleCSVUploaded} />
            </div>

            {isFileSelected && !isDialogOpen && (
                <div className="view-columns-button-container" style={{ display: 'flex', gap: '10px', justifyContent: 'center', flexWrap: 'wrap' }}>
                    <button className="view-columns-button" onClick={handleOpenDialog}>
                        View Selected File Columns
                    </button>
                    <button
                        className="view-columns-button"
                        onClick={handleOpenSelectedColumnsDialog}
                        disabled={selectedColumns.length === 0}
                    >
                        View Selected Columns {selectedColumns.length > 0 ? `(${selectedColumns.length})` : ''}
                    </button>
                    <button
                        className="view-columns-button"
                        onClick={handleCreateSegments}
                        disabled={selectedColumns.length === 0}
                    >
                        Create Segments
                    </button>
                </div>
            )}

            <ColumnsDialog
                columns={columns}
                isOpen={isDialogOpen}
                onClose={handleCloseDialog}
                onSelectColumns={handleSelectColumns}
            />

            <SelectedColumnsDialog
                columns={selectedColumns}
                isOpen={isSelectedColumnsDialogOpen}
                onClose={handleCloseSelectedColumnsDialog}
            />

            <SegmentsDialog
                isOpen={isSegmentsDialogOpen}
                onClose={handleCloseSegmentsDialog}
                selectedColumns={selectedColumns}
            />
        </div>
    );
}

export default App;