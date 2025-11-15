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

  // When view is clicked, fetch the full record and navigate to selected columns page with state
  const handleView = async (id: number) => {
    try {
      // Fetch the record
      const res = await fetch(`http://localhost:5000/api/record/${id}`);
      const data = await res.json();
      
      console.log('📊 Loaded record:', data);
      
      // Load columns from the dataset file for this specific record
      let columns: string[] = [];
      try {
        const loadDatasetRes = await fetch(`http://localhost:5000/api/record/${id}/load-dataset`);
        if (loadDatasetRes.ok) {
          const loadDatasetData = await loadDatasetRes.json();
          columns = loadDatasetData.columns || [];
          console.log('✅ Loaded columns from dataset:', columns.length, 'columns');
        }
      } catch (e) {
        console.error('❌ Failed to load dataset columns:', e);
      }
      
      // Fallback: infer columns from record data
      if (columns.length === 0) {
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
        console.log('⚠️ Using inferred columns:', columns.length, 'columns');
      }
      
      // Extract binning results from new format
      const univariateResults: Record<string, any> = {};
      const fineBinResults: Record<string, any> = {};
      const woeIvResults: Record<string, any> = {};
      
      console.log('🔍 Checking binning_data:', {
        hasBinningData: !!data.binning_data,
        binningDataKeys: data.binning_data ? Object.keys(data.binning_data).length : 0,
        sampleColumn: data.binning_data ? Object.keys(data.binning_data)[0] : 'none'
      });
      
      if (data.binning_data) {
        Object.entries(data.binning_data).forEach(([column, binning]: [string, any]) => {
          console.log(`   Column ${column}:`, {
            hasCoarse: !!binning.coarse,
            hasFine: !!binning.fine,
            hasWoe: !!binning.woe_iv,
            coarseBins: binning.coarse?.bins?.length || 0,
            fineBins: binning.fine?.bins?.length || 0,
            woeBins: binning.woe_iv?.bins?.length || 0
          });
          
          if (binning.coarse && binning.coarse.bins && binning.coarse.bins.length > 0) {
            univariateResults[column] = binning.coarse;
          }
          if (binning.fine && binning.fine.bins && binning.fine.bins.length > 0) {
            fineBinResults[column] = binning.fine.bins;
          }
          if (binning.woe_iv && binning.woe_iv.bins && binning.woe_iv.bins.length > 0) {
            woeIvResults[column] = binning.woe_iv;
          }
        });
      }
      
      console.log('📈 Extracted results:', {
        univariate: Object.keys(univariateResults).length,
        fineBin: Object.keys(fineBinResults).length,
        woeIv: Object.keys(woeIvResults).length
      });
      
      // Build state and navigate to SelectedColumnsPage directly
      const state = {
        selectedColumns: data.selected_columns || [],
        discreteColumns: data.discrete_columns || [],
        continuousColumns: data.continuous_columns || [],
        targetVariable: data.target_variable || '',
        recordId: id,
        datasetPath: data.dataset_path || '',
        univariateResults,
        fineBinResults,
        woeIvResults,
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
