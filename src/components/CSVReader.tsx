import { useState } from 'react';
import './CSVReader.css';

interface CSVReaderProps {
  onCSVUploaded: (headers: string[], rows: any[]) => void;
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
      onCSVUploaded(data.columns, data.rows);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="csv-reader-container">
      <div className="file-upload-container">
        <p>Select a CSV file to upload:</p>
        <label className="upload-button" htmlFor="csv-upload">Choose File</label>
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
        {fileName && <p className="file-name">{fileName}</p>}
        {isLoading && <p className="loading-indicator">Processing...</p>}
        {error && <p className="error-message">{error}</p>}
      </div>
    </div>
  );
};

export default CSVReader;
