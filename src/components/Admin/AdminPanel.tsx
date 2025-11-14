import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import './AdminPanel.css';

type AnalysisRecord = {
  id: number;
  dataset_path: string;
  discrete_columns: string[];  // Changed to array
  continuous_columns: string[];  // Changed to array
  selected_columns: string[];  // Changed to array
  target_variable: string;
  created_at: string;
  total_features?: number;
  discrete_features?: number;
  continuous_features?: number;
  binning_data?: Record<string, any>;
};

const AdminPanel: React.FC = () => {
  const navigate = useNavigate();
  const [records, setRecords] = useState<AnalysisRecord[]>([]);
  const [loading, setLoading] = useState<boolean>(true);

  useEffect(() => {
    setLoading(true);
    fetch('http://localhost:5000/api/records')
      .then(res => res.json())
      .then(data => {
        setRecords(data);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  // When view is clicked, fetch the full record and navigate to main page with state
  const handleView = (id: number) => {
    fetch(`http://localhost:5000/api/record/${id}`)
      .then(res => res.json())
      .then(async data => {
        // Load columns from uploaded.csv (first row)
        let columns: string[] = [];
        try {
          const csvRes = await fetch('http://localhost:5000/api/uploaded-csv-columns');
          if (csvRes.ok) {
            const csvData = await csvRes.json();
            columns = csvData.columns || [];
          }
        } catch {}
        
        // Extract binning results from new format
        const univariateResults: Record<string, any> = {};
        const fineBinResults: Record<string, any> = {};
        const woeIvResults: Record<string, any> = {};
        
        if (data.binning_data) {
          Object.entries(data.binning_data).forEach(([column, binning]: [string, any]) => {
            if (binning.coarse) {
              univariateResults[column] = binning.coarse;
            }
            if (binning.fine) {
              fineBinResults[column] = binning.fine.bins;
            }
            if (binning.woe_iv) {
              woeIvResults[column] = binning.woe_iv;
            }
          });
        }
        
        // Build state with NEW format (arrays instead of comma-separated strings)
        const state = {
          columns,
          discreteColumns: data.discrete_columns || [],  // Already an array
          continuousColumns: data.continuous_columns || [],  // Already an array
          selectedForUnivariate: data.selected_columns || [],  // Already an array
          targetVariable: data.target_variable,
          univariateResults,
          fineBinResults,
          woeIvResults,
          recordId: id,
        };
        navigate('/', { state });
      });
  };

  // Delete record
  const handleDelete = (id: number) => {
    if (!window.confirm('Are you sure you want to delete this record?')) return;
    fetch(`http://localhost:5000/api/record/${id}`, { method: 'DELETE' })
      .then(res => {
        if (res.ok) {
          setRecords(records => records.filter(r => r.id !== id));
        }
      });
  };

  return (
    <div className="admin-panel-container">
      <button className="back-button" onClick={() => navigate('/')}>Back</button>
      <h2 style={{ textAlign: 'center' }}>Record</h2>
      {loading ? (
        <div className="admin-loading">Loading...</div>
      ) : records.length === 0 ? (
        <div className="admin-empty">No analyses found.</div>
      ) : (
        <table className="admin-table">
          <thead>
            <tr>
              <th style={{ textAlign: 'center' }}>ID</th>
              <th style={{ textAlign: 'center' }}>Dataset</th>
              <th style={{ textAlign: 'center' }}>Selected Columns</th>
              <th style={{ textAlign: 'center' }}>Date</th>
              <th style={{ textAlign: 'center' }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {records.map((rec) => (
              <tr key={rec.id}>
                <td style={{ textAlign: 'center' }}>{rec.id}</td>
                <td style={{ textAlign: 'center' }}>{rec.dataset_path}</td>
                <td style={{ textAlign: 'center', whiteSpace: 'pre-wrap', wordBreak: 'break-word', maxWidth: 200 }}>
                  {Array.isArray(rec.selected_columns) ? rec.selected_columns.join(', ') : rec.selected_columns}
                </td>
                <td style={{ textAlign: 'center' }}>{rec.created_at}</td>
                <td style={{ textAlign: 'center' }}>
                  <div style={{ display: 'inline-flex', gap: '8px' }}>
                    <button className="admin-action-btn" title="View" onClick={() => handleView(rec.id)}>View</button>
                    <button className="admin-action-btn" title="Delete" onClick={() => handleDelete(rec.id)}>Delete</button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
};

export default AdminPanel;
