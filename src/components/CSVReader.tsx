import { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import LoginPanel from './LoginPanel';
import './CSVReader.css';

interface CSVReaderProps {
  onCSVUploaded: (headers: string[], rows: any[], datasetPath: string, datasetId?: number) => void;
}

const CSVReader = ({ onCSVUploaded }: CSVReaderProps) => {
  const { isAuthenticated, token } = useAuth();
  const [fileName, setFileName] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [showLoginPanel, setShowLoginPanel] = useState(false);

  const processCSV = async (file: File) => {
    // Check if user is authenticated before uploading
    if (!isAuthenticated || !token) {
      setError('Please log in to upload files');
      setShowLoginPanel(true);
      return;
    }

    setIsLoading(true);
    setError(null);
    try {
      const formData = new FormData();
      formData.append('file', file);

      const response = await fetch('http://localhost:5000/api/upload-csv', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
        },
        body: formData,
      });

      const data = await response.json();

      if (response.status === 401) {
        setError('Please log in to upload files');
        setShowLoginPanel(true);
        return;
      }

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

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    setError(null);
    if (e.target.files?.length) {
      const file = e.target.files[0];
      processCSV(file);
    }
  };

  const handleUploadClick = () => {
    if (!isAuthenticated) {
      setError('Please log in to upload files');
      setShowLoginPanel(true);
      return;
    }
    // Let the native file input handle it
    document.getElementById('csv-upload')?.click();
  };

  return (
    <div className="csv-reader-container">
      {!isAuthenticated && (
        <div className="csv-login-required">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect>
            <path d="M7 11V7a5 5 0 0 1 10 0v4"></path>
          </svg>
          <span>Login required to upload files</span>
        </div>
      )}
      <div 
        className={`csv-upload-button ${!isAuthenticated ? 'csv-upload-disabled' : ''}`}
        onClick={handleUploadClick}
      >
        <div className="upload-icon-wrapper">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
            <polyline points="7 10 12 15 17 10"></polyline>
            <line x1="12" y1="15" x2="12" y2="3"></line>
          </svg>
        </div>
        <div className="upload-text">
          <span className="upload-text-main">Upload CSV File</span>
          <span className="upload-text-sub">
            {isAuthenticated 
              ? 'Click or drag and drop your file here'
              : 'Please log in first to upload files'
            }
          </span>
        </div>
      </div>
      <input
        id="csv-upload"
        type="file"
        accept=".csv"
        onChange={handleFileSelect}
        style={{ display: 'none' }}
        disabled={!isAuthenticated}
      />
      {fileName && <div className="file-name-display">{fileName}</div>}
      {isLoading && <div className="loading-indicator">Processing...</div>}
      {error && <div className="error-message">{error}</div>}
      
      <LoginPanel 
        isOpen={showLoginPanel} 
        onClose={() => setShowLoginPanel(false)}
        onSuccess={() => setShowLoginPanel(false)}
      />
    </div>
  );
};

export default CSVReader;
