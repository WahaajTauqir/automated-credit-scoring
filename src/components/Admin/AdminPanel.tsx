import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { authGet, authDelete } from '../../utils/api';
import './AdminPanel.css';
import { AnalysisRecord } from '../../types/analysis';
import { buildBinningState, buildTypeLookup } from '../../utils/binning';

const AdminPanel: React.FC = () => {
  const navigate = useNavigate();
  const [records, setRecords] = useState<AnalysisRecord[]>([]);
  const [loading, setLoading] = useState<boolean>(true);

  useEffect(() => {
    setLoading(true);
    authGet('/api/records')
      .then(data => {
        setRecords(Array.isArray(data) ? data : []);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  // When view is clicked, fetch the full record and navigate to selected columns page with state
  const handleView = async (id: number) => {
    try {
      // Fetch the record with auth token
      const data = await authGet(`/api/record/${id}`);
      
      console.log('📊 Loaded record:', data);
      
      // Get columns from record data
      // If all_columns is provided (for unclassified datasets), use that
      // Otherwise, infer from discrete/continuous/selected columns
      let columns: string[] = [];
      if (Array.isArray(data.all_columns) && data.all_columns.length > 0) {
        // Use columns from CSV (for unclassified datasets)
        columns = data.all_columns;
        console.log('✅ Using all_columns from CSV:', columns.length, 'columns');
      } else {
        // Infer columns from classified features
        const allCols = new Set<string>();
        if (Array.isArray(data.discrete_columns)) {
          data.discrete_columns.forEach((col: string) => allCols.add(col));
        }
        if (Array.isArray(data.continuous_columns)) {
          data.continuous_columns.forEach((col: string) => allCols.add(col));
        }
        if (Array.isArray(data.selected_columns)) {
          data.selected_columns.forEach((col: string) => allCols.add(col));
        }
        columns = Array.from(allCols);
        console.log('✅ Using columns from classified features:', columns.length, 'columns');
      }
      
      const typeLookup = buildTypeLookup(
        data.discrete_columns || [],
        data.continuous_columns || []
      );
      const binningState = buildBinningState(data.binning_data, typeLookup);
      
      // Build state and navigate to SelectedColumnsPage directly
      const state = {
        selectedColumns: data.selected_columns || [],
        discreteColumns: data.discrete_columns || [],
        continuousColumns: data.continuous_columns || [],
        targetVariable: data.target_variable || '',
        recordId: id,
        datasetPath: data.dataset_path || '',
        columns: columns, // Include inferred columns for faster loading
        univariateResults: binningState.univariate,
        fineBinResults: binningState.fine,
        woeIvResults: binningState.woe,
        binningState,
        modelReadyColumns: Array.isArray(data.dashboard_selected_columns) ? data.dashboard_selected_columns : [],
        finalSelectedColumns: Array.isArray(data.final_selected_columns) ? data.final_selected_columns : [],
      };
      
      console.log('🚀 Navigating to /selected-columns with state');
      navigate('/selected-columns', { state });
    } catch (error) {
      console.error('❌ Error loading record:', error);
      alert('Failed to load record: ' + error);
    }
  };

  // Delete record
  const handleDelete = (id: number) => {
    if (!window.confirm('Are you sure you want to delete this record?')) return;
    authDelete(`/api/record/${id}`)
      .then(() => {
          setRecords(records => records.filter(r => r.id !== id));
      })
      .catch(err => console.error('Failed to delete record:', err));
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
                  {rec.selected_columns.join(', ')}
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
