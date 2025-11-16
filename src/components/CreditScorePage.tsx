import { useState, useRef } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import Navbar from './Navbar';
import './CreditScorePage.css';

interface PredictionRow {
  id: string;
  score: number;
  probability: number;
  status: string;
  [key: string]: any;
}

const CreditScorePage = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const fileInputRef = useRef<HTMLInputElement>(null);
  
  const [uploadedFile, setUploadedFile] = useState<File | null>(null);
  const [fileName, setFileName] = useState<string>('');
  const [csvHeaders, setCsvHeaders] = useState<string[]>([]);
  const [csvData, setCsvData] = useState<any[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [selectedModel, setSelectedModel] = useState<string>('logistic');
  const [selectedIdentifier, setSelectedIdentifier] = useState<string>('');
  const [predictions, setPredictions] = useState<PredictionRow[]>([]);
  const [isProcessing, setIsProcessing] = useState<boolean>(false);
  const [recordId, setRecordId] = useState<number | undefined>(
    location.state?.recordId
  );

  // Available models
  const availableModels = [
    { value: 'logistic', label: 'Logistic Regression' },
    { value: 'random_forest', label: 'Random Forest' },
    { value: 'xgboost', label: 'XGBoost' },
  ];

  // Handle file upload
  const handleFileUpload = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    if (!file.name.endsWith('.csv')) {
      setError('Please upload a CSV file');
      return;
    }

    setUploadedFile(file);
    setFileName(file.name);
    setError(null);
    setPredictions([]);
    setSelectedIdentifier('');

    // Read CSV file
    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const text = e.target?.result as string;
        const lines = text.split('\n').filter(line => line.trim());
        
        if (lines.length === 0) {
          setError('CSV file is empty');
          return;
        }

        // Parse headers
        const headers = lines[0].split(',').map(h => h.trim());
        setCsvHeaders(headers);

        // Parse data rows
        const data = lines.slice(1).map(line => {
          const values = line.split(',').map(v => v.trim());
          const row: any = {};
          headers.forEach((header, index) => {
            row[header] = values[index] || '';
          });
          return row;
        });

        setCsvData(data);
        
        // Auto-select first column as identifier if available
        if (headers.length > 0) {
          setSelectedIdentifier(headers[0]);
        }
      } catch (err) {
        setError('Error parsing CSV file: ' + (err as Error).message);
      }
    };

    reader.onerror = () => {
      setError('Error reading file');
    };

    reader.readAsText(file);
  };

  // Validate CSV structure (placeholder - will be implemented later)
  const validateCsvStructure = async (): Promise<boolean> => {
    if (!recordId) {
      setError('No record ID found. Please go back and select a record first.');
      return false;
    }

    // TODO: Implement actual validation against training data structure
    // This should check if the CSV columns match the expected columns from the training data
    // For now, just return true
    // When implemented, it should:
    // 1. Fetch the expected columns from the backend using recordId
    // 2. Compare csvHeaders with expected columns
    // 3. Return false and set error message if they don't match
    
    return true;
  };

  // Handle prediction (placeholder - will be implemented later)
  const handlePredict = async () => {
    if (!uploadedFile) {
      setError('Please upload a CSV file first');
      return;
    }

    if (!selectedIdentifier) {
      setError('Please select an identifier column');
      return;
    }

    setIsProcessing(true);
    setError(null);

    try {
      // Validate CSV structure
      const isValid = await validateCsvStructure();
      if (!isValid) {
        setIsProcessing(false);
        return;
      }

      // TODO: Implement actual prediction API call
      // For now, create dummy predictions
      const dummyPredictions: PredictionRow[] = csvData.map((row, index) => ({
        id: row[selectedIdentifier] || `Row_${index + 1}`,
        score: Math.floor(Math.random() * 300) + 500, // Random score between 500-800
        probability: Math.random() * 0.3 + 0.1, // Random probability between 0.1-0.4
        status: Math.random() > 0.5 ? 'Approved' : 'Pending',
        ...row,
      }));

      setPredictions(dummyPredictions);
    } catch (err) {
      setError('Error processing predictions: ' + (err as Error).message);
    } finally {
      setIsProcessing(false);
    }
  };

  // Handle PDF download (placeholder - will be implemented later)
  const handleDownloadPDF = () => {
    if (predictions.length === 0) {
      setError('No predictions to download');
      return;
    }

    // TODO: Implement actual PDF generation
    alert('PDF download functionality will be implemented later');
  };

  // Trigger file input
  const handleUploadClick = () => {
    fileInputRef.current?.click();
  };

  return (
    <div className="credit-score-page-wrapper">
      <Navbar />
      
      <div className="credit-score-container">
        <div className="credit-score-header">
          <h1 className="credit-score-title">Credit Score Prediction</h1>
          <p className="credit-score-subtitle">
            Upload a CSV file with data to predict credit scores
          </p>
        </div>

        <div className="credit-score-content">
          {/* Left Column: Upload and Configuration */}
          <div className="credit-score-left">
            {/* Upload Section */}
            <div className="credit-score-section">
              <h2 className="section-title">Upload Data</h2>
              <div className="csv-upload-area" onClick={handleUploadClick}>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".csv"
                  onChange={handleFileUpload}
                  style={{ display: 'none' }}
                />
                <div className="upload-icon-wrapper">
                  <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                    <polyline points="7 10 12 15 17 10"></polyline>
                    <line x1="12" y1="15" x2="12" y2="3"></line>
                  </svg>
                </div>
                <div className="upload-text">
                  <div className="upload-text-main">
                    {fileName || 'Click to upload CSV file'}
                  </div>
                  <div className="upload-text-sub">
                    {fileName ? 'Click to change file' : 'Select a CSV file to upload'}
                  </div>
                </div>
              </div>

              {error && (
                <div className="error-message">
                  {error}
                </div>
              )}

              {fileName && !error && (
                <div className="file-info">
                  <div className="file-info-item">
                    <span className="file-info-label">File:</span>
                    <span className="file-info-value">{fileName}</span>
                  </div>
                  <div className="file-info-item">
                    <span className="file-info-label">Rows:</span>
                    <span className="file-info-value">{csvData.length}</span>
                  </div>
                  <div className="file-info-item">
                    <span className="file-info-label">Columns:</span>
                    <span className="file-info-value">{csvHeaders.length}</span>
                  </div>
                </div>
              )}
            </div>

            {/* Configuration Section */}
            {csvHeaders.length > 0 && (
              <div className="credit-score-section">
                <h2 className="section-title">Configuration</h2>
                
                {/* Model Selection */}
                <div className="config-item">
                  <label className="config-label">Select Model</label>
                  <select
                    className="config-select"
                    value={selectedModel}
                    onChange={(e) => setSelectedModel(e.target.value)}
                  >
                    {availableModels.map(model => (
                      <option key={model.value} value={model.value}>
                        {model.label}
                      </option>
                    ))}
                  </select>
                </div>

                {/* Identifier Selection */}
                <div className="config-item">
                  <label className="config-label">Select Identifier Column</label>
                  <select
                    className="config-select"
                    value={selectedIdentifier}
                    onChange={(e) => setSelectedIdentifier(e.target.value)}
                  >
                    <option value="">-- Select Identifier --</option>
                    {csvHeaders.map(header => (
                      <option key={header} value={header}>
                        {header}
                      </option>
                    ))}
                  </select>
                  <p className="config-help">
                    This column will be used to link predictions to each row
                  </p>
                </div>

                {/* Predict Button */}
                <button
                  className="predict-button"
                  onClick={handlePredict}
                  disabled={isProcessing || !selectedIdentifier}
                >
                  {isProcessing ? 'Processing...' : 'Generate Predictions'}
                </button>
              </div>
            )}

            {/* Download Section */}
            {predictions.length > 0 && (
              <div className="credit-score-section">
                <h2 className="section-title">Export Results</h2>
                <button
                  className="download-button"
                  onClick={handleDownloadPDF}
                >
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                    <polyline points="7 10 12 15 17 10"></polyline>
                    <line x1="12" y1="15" x2="12" y2="3"></line>
                  </svg>
                  Download PDF Report
                </button>
              </div>
            )}
          </div>

          {/* Right Column: Predictions */}
          <div className="credit-score-right">
            <div className="credit-score-section">
              <h2 className="section-title">
                Predictions
                {predictions.length > 0 && (
                  <span className="predictions-count">({predictions.length})</span>
                )}
              </h2>

              {predictions.length === 0 ? (
                <div className="predictions-empty">
                  {isProcessing ? (
                    <div className="loading-indicator">
                      Processing predictions...
                    </div>
                  ) : (
                    <div className="empty-state">
                      <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" opacity="0.3">
                        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                        <polyline points="14 2 14 8 20 8"></polyline>
                        <line x1="16" y1="13" x2="8" y2="13"></line>
                        <line x1="16" y1="17" x2="8" y2="17"></line>
                        <polyline points="10 9 9 9 8 9"></polyline>
                      </svg>
                      <p>No predictions yet. Upload a file and generate predictions to see results here.</p>
                    </div>
                  )}
                </div>
              ) : (
                <div className="predictions-list">
                  {predictions.map((prediction, index) => (
                    <div key={index} className="prediction-card">
                      <div className="prediction-card-header">
                        <span className="prediction-id">
                          {prediction.id}
                        </span>
                        <span className={`prediction-status prediction-status-${prediction.status.toLowerCase()}`}>
                          {prediction.status}
                        </span>
                      </div>
                      <div className="prediction-card-body">
                        <div className="prediction-metric">
                          <span className="prediction-metric-label">Credit Score:</span>
                          <span className="prediction-metric-value prediction-score">
                            {prediction.score}
                          </span>
                        </div>
                        <div className="prediction-metric">
                          <span className="prediction-metric-label">Default Probability:</span>
                          <span className="prediction-metric-value">
                            {(prediction.probability * 100).toFixed(2)}%
                          </span>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default CreditScorePage;

