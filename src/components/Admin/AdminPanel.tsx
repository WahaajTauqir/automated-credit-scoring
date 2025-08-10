import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import './AdminPanel.css';

// Example record type (adjust fields as needed for your DB)
type AnalysisRecord = {
  id: number;
  name: string;
  date: string;
  description?: string;
};

const AdminPanel: React.FC = () => {
  const navigate = useNavigate();

  const [records, setRecords] = useState<AnalysisRecord[]>([]);
  const [loading, setLoading] = useState<boolean>(true);

  useEffect(() => {
    setLoading(true);

    setTimeout(() => {
      setRecords([
        { id: 1, name: 'Credit Scoring Q1', date: '2025-07-01', description: 'Analysis for Q1 data' },
        { id: 2, name: 'Credit Scoring Q2', date: '2025-08-01', description: 'Analysis for Q2 data' },
      ]);
      setLoading(false);
    }, 800);
  }, []);

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
              <th>ID</th>
              <th>Name</th>
              <th>Date</th>
              <th>Description</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {records.map((rec) => (
              <tr key={rec.id}>
                <td>{rec.id}</td>
                <td>{rec.name}</td>
                <td>{rec.date}</td>
                <td>{rec.description || '-'}</td>
                <td>
                  <button className="admin-action-btn" title="View">View</button>
                  <button className="admin-action-btn" title="Delete">Delete</button>
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
