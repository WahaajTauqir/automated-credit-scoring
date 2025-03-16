import { useState } from 'react';
import './CSVReader.css';

interface CSVReaderProps {
    onCSVUploaded: (headers: string[]) => void;
}

const CSVReader = ({ onCSVUploaded }: CSVReaderProps) => {
    const [fileName, setFileName] = useState<string>('');
    const [error, setError] = useState<string | null>(null);
    const [isLoading, setIsLoading] = useState<boolean>(false);

    const processCSV = async (file: File) => {
        setIsLoading(true);

        try {
            // Create a FormData object to send the file
            const formData = new FormData();
            formData.append('file', file);

            // Send the file to the backend
            const response = await fetch('http://localhost:5000/api/upload-csv', {
                method: 'POST',
                body: formData,
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || 'Failed to process CSV file');
            }

            const data = await response.json();

            if (data.success && data.columns) {
                // Call the callback with the headers received from the backend
                onCSVUploaded(data.columns);
            } else {
                throw new Error('Invalid response from the server');
            }
        } catch (error) {
            setError(error instanceof Error ? error.message : 'Error processing the CSV file');
            console.error('Error processing CSV:', error);
        } finally {
            setIsLoading(false);
        }
    };

    const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        setError(null);

        if (e.target.files && e.target.files.length > 0) {
            const file = e.target.files[0];
            if (file.type === 'text/csv' || file.name.endsWith('.csv')) {
                setFileName(file.name);
                processCSV(file);
            } else {
                setError('Please upload a CSV file');
            }
        }
    };

    return (
        <div className="csv-reader-container">
            <div className="file-upload-container">
                <p>Select a CSV file to upload:</p>
                <label className="upload-button" htmlFor="csv-upload">
                    Choose File
                </label>
                <input
                    id="csv-upload"
                    type="file"
                    accept=".csv"
                    onChange={handleFileChange}
                    style={{ display: 'none' }}
                />
                {fileName && <p className="file-name">Selected: {fileName}</p>}
            </div>
            {isLoading && <p className="loading-indicator">Processing CSV file...</p>}
            {error && <p className="error-message">{error}</p>}
        </div>
    );
};

export default CSVReader;