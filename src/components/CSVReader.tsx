import { useState } from 'react';
import './CSVReader.css';

interface CSVReaderProps {
  onCSVUploaded: (headers: string[], rows: any[], datasetPath: string, datasetId?: number) => void;
}

const CSVReader = ({ onCSVUploaded }: CSVReaderProps) => {
  const [fileName, setFileName] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const processCSV = async (file: File) => {
    setIsLoading(true);
    try {
      const formData = new FormData();
      formData.append('file', file);

      const response = await fetch('http://localhost:5000/api/upload-csv', {
        method: 'POST',
        body: formData,
      });

      const data = await response.json();

      if (!response.ok || !data.success) {
        throw new Error(data.error || 'Failed to upload');
      }

      setFileName(file.name);
      onCSVUploaded(
        data.columns,
        data.rows || [],
        data.dataset_path || '',
        data.dataset_id
      );
    } catch (err: any) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="csv-reader-container">
      <label className="csv-upload-button" htmlFor="csv-upload">
        <div className="upload-icon-wrapper">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
            <polyline points="7 10 12 15 17 10"></polyline>
            <line x1="12" y1="15" x2="12" y2="3"></line>
          </svg>
        </div>
        <div className="upload-text">
          <span className="upload-text-main">Upload CSV File</span>
          <span className="upload-text-sub">Click or drag and drop your file here</span>
        </div>
      </label>
      <input
        id="csv-upload"
        type="file"
        accept=".csv"
        onChange={(e) => {
          setError(null);
          if (e.target.files?.length) {
            const file = e.target.files[0];
            processCSV(file);
          }
        }}
        style={{ display: 'none' }}
      />
      {fileName && <div className="file-name-display">{fileName}</div>}
      {isLoading && <div className="loading-indicator">Processing...</div>}
      {error && <div className="error-message">{error}</div>}
    </div>
  );
};

export default CSVReader;
