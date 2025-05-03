import { useState, useEffect } from 'react';
import './ColumnsDialog.css';

interface SegmentsDialogProps {
    isOpen: boolean;
    onClose: () => void;
    selectedColumns: string[];
}

interface ClusterInfo {
    id: number;
    count: number;
    center: Record<string, number>;
    sample_data: Array<Record<string, unknown>>;
}

const SegmentsDialog = ({ isOpen, onClose, selectedColumns }: SegmentsDialogProps) => {
    const [isLoading, setIsLoading] = useState<boolean>(true);
    const [error, setError] = useState<string | null>(null);
    const [clusterData, setClusterData] = useState<ClusterInfo[] | null>(null);
    const [scatterPlot, setElbowPlot] = useState<string | null>(null);

    useEffect(() => {
        if (isOpen && selectedColumns.length > 0) {
            fetchClusterData();
        }
    }, [isOpen, selectedColumns]);

    const fetchClusterData = async () => {
        setIsLoading(true);
        setError(null);

        try {
            const csvData = JSON.parse(localStorage.getItem('csvData') || '[]');

            if (!csvData || csvData.length === 0) {
                throw new Error('No CSV data available. Please upload a CSV file first.');
            }

            const response = await fetch('http://localhost:5000/api/cluster', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    data: csvData,
                    columns: selectedColumns,
                    max_k: 10,
                    find_optimal_k: true
                }),
            });

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                throw new Error(errorData.error || `Server responded with status ${response.status}`);
            }

            const result = await response.json();

            if (!result.success) {
                throw new Error(result.error || 'Unknown error occurred during clustering');
            }

            if (result.combined_result && selectedColumns.length > 1) {
                setClusterData(result.combined_result.cluster_info);
                setElbowPlot(result.combined_result.plot);
            } else if (Object.keys(result.individual_results).length > 0) {
                const firstKey = Object.keys(result.individual_results)[0];
                setClusterData(result.individual_results[firstKey].cluster_info);
                setElbowPlot(result.individual_results[firstKey].plot);
            } else {
                throw new Error('No clustering results returned from server');
            }
        } catch (err) {
            console.error('Error fetching cluster data:', err);
            setError(err instanceof Error ? err.message : 'Error fetching cluster data');
        } finally {
            setIsLoading(false);
        }
    };

    if (!isOpen) return null;

    return (
        <div className="dialog-overlay">
            <div className="dialog-content" style={{ width: '90%', maxWidth: '1200px' }}>
                <div className="dialog-header">
                    <h2>Data Segments</h2>
                    <button className="close-button" onClick={onClose}>×</button>
                </div>
                <div className="dialog-body">
                    <h3>K-means Clustering Results</h3>

                    {isLoading ? (
                        <div style={{ textAlign: 'center', padding: '20px' }}>
                            <p>Generating clusters...</p>
                        </div>
                    ) : error ? (
                        <div style={{ color: 'red', padding: '20px' }}>
                            <p>Error: {error}</p>
                        </div>
                    ) : (
                        <>
                            {scatterPlot && (
                                <div style={{ textAlign: 'center', marginBottom: '20px' }}>
                                    <h4>Scatter Plot</h4>
                                    <img
                                        src={`data:image/png;base64,${scatterPlot}`}
                                        alt="Scatter Plot"
                                        style={{ maxWidth: '100%', height: 'auto' }}
                                    />
                                </div>
                            )}

                            <div style={{ overflowX: 'auto', width: '100%' }}>
                                <div style={{
                                    display: 'grid',
                                    gridTemplateColumns: `repeat(${Math.min(clusterData?.length || 1, 4)}, 1fr)`,
                                    gap: '10px',
                                    marginBottom: '20px'
                                }}>
                                    {clusterData?.map((cluster, idx) => (
                                        <div key={idx} style={{
                                            padding: '15px',
                                            backgroundColor: '#f0f7ff',
                                            borderRadius: '8px',
                                            textAlign: 'center',
                                            border: '1px solid #d0e3ff'
                                        }}>
                                            <h4>Cluster {cluster.id + 1}</h4>
                                            <div style={{ marginBottom: '10px' }}>
                                                {Object.entries(cluster.center).map(([col, value], i) => (
                                                    <div key={i} style={{ marginBottom: '5px', textAlign: 'left' }}>
                                                        <strong>{col}:</strong> {typeof value === 'number' ? value.toFixed(2) : value}
                                                    </div>
                                                ))}
                                            </div>
                                            <div style={{
                                                fontSize: '1.2em',
                                                fontWeight: 'bold',
                                                backgroundColor: '#0066cc',
                                                color: 'white',
                                                padding: '5px 10px',
                                                borderRadius: '4px',
                                                marginBottom: '15px'
                                            }}>
                                                {cluster.count} records
                                            </div>

                                            <div style={{
                                                height: '200px',
                                                overflowY: 'auto',
                                                border: '1px solid #ddd',
                                                borderRadius: '4px',
                                                backgroundColor: 'white'
                                            }}>
                                                <table style={{
                                                    width: '100%',
                                                    borderCollapse: 'collapse'
                                                }}>
                                                    <thead style={{
                                                        position: 'sticky',
                                                        top: 0,
                                                        backgroundColor: '#f0f0f0',
                                                        zIndex: 1
                                                    }}>
                                                    <tr>
                                                        <th style={{
                                                            padding: '8px',
                                                            borderBottom: '1px solid #ddd',
                                                            textAlign: 'center'
                                                        }}>#</th>
                                                        {selectedColumns.map((column, i) => (
                                                            <th key={i} style={{
                                                                padding: '8px',
                                                                borderBottom: '1px solid #ddd',
                                                                textAlign: 'center'
                                                            }}>
                                                                {column}
                                                            </th>
                                                        ))}
                                                    </tr>
                                                    </thead>
                                                    <tbody>
                                                    {cluster.sample_data.map((point, i) => (
                                                        <tr key={i} style={{
                                                            backgroundColor: i % 2 === 0 ? '#f9f9f9' : 'white'
                                                        }}>
                                                            <td style={{
                                                                padding: '6px',
                                                                borderBottom: '1px solid #ddd',
                                                                textAlign: 'center'
                                                            }}>{i+1}</td>
                                                            {selectedColumns.map((column, j) => (
                                                                <td key={j} style={{
                                                                    padding: '6px',
                                                                    borderBottom: '1px solid #ddd',
                                                                    textAlign: 'center'
                                                                }}>
                                                                    {point[column] === null || point[column] === undefined
                                                                        ? 'N/A'
                                                                        : typeof point[column] === 'number'
                                                                            ? (point[column] as number).toFixed(2)
                                                                            : String(point[column])}
                                                                </td>
                                                            ))}
                                                        </tr>
                                                    ))}
                                                    </tbody>
                                                </table>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        </>
                    )}
                </div>
                <div className="dialog-footer">
                    <button className="ok-button" onClick={onClose}>Close</button>
                </div>
            </div>
        </div>
    );
};

export default SegmentsDialog;