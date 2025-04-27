import React, { useState } from 'react';
import './CSVReader.css';

interface CSVReaderProps {
    onCSVUploaded: (headers: string[]) => void;
}

const CSVReader: React.FC<CSVReaderProps> = ({ onCSVUploaded }) => {
    const [isUploading, setIsUploading] = useState<boolean>(false);
    const [hasError, setHasError] = useState<boolean>(false);
    const [filename, setFilename] = useState<string>('');

    const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
        const file = event.target.files?.[0];
        if (!file) return;

        setFilename(file.name);
        setIsUploading(true);
        setHasError(false);

        const formData = new FormData();
        formData.append('file', file);

        try {
            const response = await fetch('http://localhost:5000/api/upload-csv', {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                throw new Error(`HTTP error! Status: ${response.status}`);
            }

            const data = await response.json();

            if (data.success && data.columns) {
                // Store the parsed CSV data in localStorage for clustering
                localStorage.setItem('csvData', JSON.stringify(data.data || []));

                // Call the callback with the headers received from the backend
                onCSVUploaded(data.columns);
            } else {
                throw new Error(data.error || 'Failed to parse CSV');
            }
        } catch (error) {
            console.error('Error uploading CSV:', error);
            setHasError(true);
        } finally {
            setIsUploading(false);
        }
    };

    const handleDragOver = (event: React.DragEvent<HTMLDivElement>) => {
        event.preventDefault();
    };

    const handleDrop = (event: React.DragEvent<HTMLDivElement>) => {
        event.preventDefault();
        const files = event.dataTransfer.files;
        if (files.length > 0) {
            const fileInput = document.getElementById('csv-file') as HTMLInputElement;
            if (fileInput) {
                fileInput.files = files;
                const changeEvent = new Event('change', { bubbles: true });
                fileInput.dispatchEvent(changeEvent);
            }
        }
    };

    const handleResetClick = () => {
        setFilename('');
        const fileInput = document.getElementById('csv-file') as HTMLInputElement;
        if (fileInput) {
            fileInput.value = '';
        }
    };

    return (
        <div
            className="csv-reader-container"
            onDragOver={handleDragOver}
            onDrop={handleDrop}
        >
            <div className="csv-reader-card">
                <div className="csv-reader-upload-area">
                    <input
                        type="file"
                        id="csv-file"
                        accept=".csv"
                        onChange={handleFileUpload}
                        hidden
                    />

                    {!filename && (
                        <div className="csv-reader-empty-state">
                            <svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                                <polyline points="14 2 14 8 20 8"></polyline>
                                <line x1="10" y1="12" x2="14" y2="12"></line>
                                <line x1="10" y1="16" x2="14" y2="16"></line>
                                <line x1="10" y1="8" x2="11" y2="8"></line>
                            </svg>
                            <p>Drop your CSV file here or <label htmlFor="csv-file">browse</label></p>
                            <p className="csv-reader-subtitle">Supports .csv files</p>
                        </div>
                    )}

                    {filename && (
                        <div className="csv-reader-file-selected">
                            <div className="csv-reader-file-info">
                                <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                                    <polyline points="14 2 14 8 20 8"></polyline>
                                    <line x1="16" y1="13" x2="8" y2="13"></line>
                                    <line x1="16" y1="17" x2="8" y2="17"></line>
                                    <polyline points="10 9 9 9 8 9"></polyline>
                                </svg>
                                <span className="csv-reader-filename">{filename}</span>
                            </div>
                            <button
                                className="csv-reader-reset-button"
                                onClick={handleResetClick}
                                disabled={isUploading}
                            >
                                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                    <line x1="18" y1="6" x2="6" y2="18"></line>
                                    <line x1="6" y1="6" x2="18" y2="18"></line>
                                </svg>
                            </button>
                        </div>
                    )}

                    {isUploading && (
                        <div className="csv-reader-loading">
                            <div className="csv-reader-spinner"></div>
                            <p>Uploading...</p>
                        </div>
                    )}

                    {hasError && (
                        <div className="csv-reader-error">
                            <p>Error uploading file. Please try again.</p>
                        </div>
                    )}
                </div>

                <div className="csv-reader-actions">
                    <label
                        htmlFor="csv-file"
                        className="csv-reader-button"
                        style={{
                            opacity: isUploading ? 0.5 : 1,
                            pointerEvents: isUploading ? 'none' : 'auto'
                        }}
                    >
                        Select CSV File
                    </label>
                </div>
            </div>
        </div>
    );
};

export default CSVReader;