import { useState, useRef, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import Navbar from './Navbar';
import './CreditScorePage.css';

interface RiskBand {
  label: string;
  color: string;
  description: string;
}

interface PredictionRow {
  id: string;
  score: number;
  probability?: number;
  risk_band: RiskBand;
  [key: string]: any;
}

interface ModelInfo {
  dataset_id: number;
  model_label: string;
  model_type: string;
  target?: string;
  selected_variables?: string[];
  saved_at?: string;
  artifact_file?: string;
  training_metrics?: Record<string, number | null>;
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
  const [predictionMethod, setPredictionMethod] = useState<'probability' | 'scorecard'>('scorecard');
  const [selectedIdentifier, setSelectedIdentifier] = useState<string>('');
  const [predictions, setPredictions] = useState<PredictionRow[]>([]);
  const [riskBands, setRiskBands] = useState<Array<{label: string, min: number, max: number, color: string, description: string}>>([]);
  const [isProcessing, setIsProcessing] = useState<boolean>(false);
  const [recordId, setRecordId] = useState<number | undefined>(
    location.state?.recordId
  );
  const [pageError, setPageError] = useState<string | null>(
    location.state?.recordId ? null : 'Select a dataset from the home page before checking credit scores.'
  );
  const [modelInfo, setModelInfo] = useState<ModelInfo | null>(null);
  const [modelLoading, setModelLoading] = useState<boolean>(false);
  const [modelFetchError, setModelFetchError] = useState<string | null>(null);
  const [availableModels, setAvailableModels] = useState<Array<{value: string, label: string}>>([]);
  const [availableModelsLoading, setAvailableModelsLoading] = useState<boolean>(false);

  useEffect(() => {
    if (recordId) {
      setPageError(null);
    }
  }, [recordId]);

  // Fetch all available models for the dataset
  useEffect(() => {
    if (!recordId) {
      setAvailableModels([]);
      setModelInfo(null);
      setModelFetchError(null);
      setModelLoading(false);
      setAvailableModelsLoading(false);
      return;
    }
    let isCancelled = false;
    setAvailableModelsLoading(true);
    setModelFetchError(null);
    
    // Fetch all available models
    fetch(`http://localhost:5000/api/datasets/${recordId}/models`)
      .then(async response => {
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(payload.error || 'Failed to load available models.');
        }
        return payload;
      })
      .then(payload => {
        if (!isCancelled) {
          const models = payload.available_models || [];
          const modelOptions = models.map((m: any) => ({
            value: m.model_type,
            label: m.model_name
          }));
          setAvailableModels(modelOptions);
          
          // If models are available, select the first one and load its metadata
          if (models.length > 0) {
            const firstModel = models[0];
            setSelectedModel(firstModel.model_type);
            setModelInfo(firstModel.metadata);
          } else {
            setAvailableModels([]);
            setModelInfo(null);
          }
        }
      })
      .catch(err => {
        if (!isCancelled) {
          setAvailableModels([]);
          setModelInfo(null);
          setModelFetchError(err.message);
        }
      })
      .finally(() => {
        if (!isCancelled) {
          setAvailableModelsLoading(false);
        }
      });
    return () => {
      isCancelled = true;
    };
  }, [recordId]);

  // Load metadata for selected model
  useEffect(() => {
    if (!recordId || !selectedModel) {
      return;
    }
    let isCancelled = false;
    setModelLoading(true);
    setModelFetchError(null);
    
    // Map frontend model type to backend model label
    const modelLabelMap: Record<string, string> = {
      'logistic': 'LR',
      'random_forest': 'RandomForest',
      'xgboost': 'XGBoost',
      'stacking_ensemble': 'stacking_ensemble'
    };
    
    const modelLabel = modelLabelMap[selectedModel];
    if (!modelLabel) {
      setModelLoading(false);
      return;
    }
    
    // Fetch specific model metadata
    fetch(`http://localhost:5000/api/datasets/${recordId}/model?model_label=${modelLabel}`)
      .then(async response => {
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(payload.error || 'Failed to load model metadata.');
        }
        return payload;
      })
      .then(payload => {
        if (!isCancelled) {
          setModelInfo(payload.model);
        }
      })
      .catch(err => {
        if (!isCancelled) {
          setModelInfo(null);
          setModelFetchError(err.message);
        }
      })
      .finally(() => {
        if (!isCancelled) {
          setModelLoading(false);
        }
      });
    return () => {
      isCancelled = true;
    };
  }, [recordId, selectedModel]);

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

  // Handle prediction
  const handlePredict = async () => {
    if (!uploadedFile) {
      setError('Please upload a CSV file first');
      return;
    }

    if (!selectedIdentifier) {
      setError('Please select an identifier column');
      return;
    }

    if (!recordId) {
      setError('No dataset selected for scoring. Please navigate from the home page and choose a scorecard.');
      return;
    }

    if (!modelInfo) {
      setError('No trained model is available for this dataset. Train a model first.');
      return;
    }

    setIsProcessing(true);
    setError(null);
    setPredictions([]);
    setRiskBands([]);

    try {
      // Validate CSV structure
      const isValid = await validateCsvStructure();
      if (!isValid) {
        setIsProcessing(false);
        return;
      }

      // Call prediction API
      const response = await fetch('http://localhost:5000/api/predict-credit-score', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          dataset_id: recordId,
          model_type: selectedModel,
          prediction_method: predictionMethod,
          csv_data: csvData,
          identifier_column: selectedIdentifier
        }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.error || 'Failed to generate predictions');
      }

      if (data.success && data.predictions) {
        setPredictions(data.predictions);
        if (data.risk_bands) {
          setRiskBands(data.risk_bands);
        }
      } else {
        throw new Error('Invalid response from server');
      }
    } catch (err) {
      setError('Error processing predictions: ' + (err as Error).message);
      setPredictions([]);
      setRiskBands([]);
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

        {pageError && (
          <div className="credit-score-page-alert">
            <span>{pageError}</span>
            <button className="credit-score-alert-link" onClick={() => navigate('/')}>
              Go to Home
            </button>
          </div>
        )}

        {recordId && (
          <div className="credit-score-meta">
            <div className="credit-score-meta-item">
              <span>Dataset ID</span>
              <strong>#{recordId}</strong>
            </div>
            <div className="credit-score-meta-item">
              <span>Model</span>
              <strong>
                {modelInfo ? modelInfo.model_label : modelLoading ? 'Loading...' : 'Not available'}
              </strong>
            </div>
            {modelInfo?.saved_at && (
              <div className="credit-score-meta-item">
                <span>Saved</span>
                <strong>{new Date(modelInfo.saved_at).toLocaleString()}</strong>
              </div>
            )}
            {modelLoading && (
              <div className="credit-score-meta-status">Loading model metadata...</div>
            )}
            {modelFetchError && !modelLoading && (
              <div className="credit-score-meta-status error">{modelFetchError}</div>
            )}
          </div>
        )}

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
                  {availableModelsLoading ? (
                    <div className="config-help">Loading available models...</div>
                  ) : availableModels.length > 0 ? (
                    <>
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
                      <p className="config-help">
                        {modelInfo
                          ? `Using ${modelInfo.model_label} model. Select a different model from the dropdown.`
                          : 'Select which trained model to use for scoring.'}
                      </p>
                    </>
                  ) : (
                    <>
                      <select className="config-select" disabled>
                        <option>No models available</option>
                      </select>
                      <p className="config-help">
                        No trained models found for this dataset. Train a model from the modeling workspace first.
                      </p>
                    </>
                  )}
                </div>

                {/* Prediction Method Selection */}
                <div className="config-item">
                  <label className="config-label">Prediction Method</label>
                  <select
                    className="config-select"
                    value={predictionMethod}
                    onChange={(e) => setPredictionMethod(e.target.value as 'probability' | 'scorecard')}
                  >
                    <option value="scorecard">Scorecard Method</option>
                    <option value="probability">Probability Method</option>
                  </select>
                  <p className="config-help">
                    {predictionMethod === 'scorecard' 
                      ? 'Uses scorecard bins for fast, interpretable scoring. Requires scorecard to be generated first.'
                      : 'Uses model probabilities for scoring. Works with any trained model.'}
                  </p>
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
                  disabled={isProcessing || !selectedIdentifier || !modelInfo}
                >
                  {isProcessing ? 'Processing...' : 'Generate Predictions'}
                </button>
                {!modelInfo && (
                  <p className="config-help">
                    Train a Logistic Regression or XGBoost model for this dataset before generating scores.
                  </p>
                )}
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
                        <span 
                          className="prediction-risk-band"
                          style={{
                            backgroundColor: prediction.risk_band.color,
                            color: '#fff',
                            padding: '4px 12px',
                            borderRadius: '4px',
                            fontSize: '0.85rem',
                            fontWeight: '500'
                          }}
                        >
                          {prediction.risk_band.label}
                        </span>
                      </div>
                      <div className="prediction-card-body">
                        <div className="prediction-metric">
                          <span className="prediction-metric-label">Credit Score:</span>
                          <span className="prediction-metric-value prediction-score">
                            {prediction.score.toFixed(0)}
                          </span>
                        </div>
                        {prediction.probability !== undefined && (
                          <div className="prediction-metric">
                            <span className="prediction-metric-label">Default Probability:</span>
                            <span className="prediction-metric-value">
                              {(prediction.probability * 100).toFixed(2)}%
                            </span>
                          </div>
                        )}
                        {prediction.risk_band.description && (
                          <div className="prediction-metric">
                            <span className="prediction-metric-label">Risk Level:</span>
                            <span className="prediction-metric-value">
                              {prediction.risk_band.description}
                            </span>
                          </div>
                        )}
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

