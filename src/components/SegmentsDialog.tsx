import { useState, useEffect } from 'react';
import './SegmentsDialog.css';

interface SegmentsDialogProps {
    isOpen: boolean;
    onClose: () => void;
    selectedColumns: string[];
}

interface ClusterInfo {
    id: number;
    count: number;
    center: Record<string, number>;
    column_stats: Record<string, {
        center: number;
        min: number;
        max: number;
        mean: number;
    }>;
    sample_data: Array<Record<string, unknown>>;
    description?: string;
    top_features?: string[];
}

interface Explanations {
    feature_importance: Record<number, Record<string, number>>;
    cluster_descriptions: Array<{
        cluster_id: number;
        description: string;
        top_features: string[];
    }>;
    profile_plot: string;
}

interface ClusterResult {
    k: number;
    cluster_info: ClusterInfo[];
    plot: string;
    explanations: Explanations;
}

const SegmentsDialog = ({ isOpen, onClose, selectedColumns }: SegmentsDialogProps) => {
    const [isLoading, setIsLoading] = useState<boolean>(true);
    const [error, setError] = useState<string | null>(null);
    const [result, setResult] = useState<ClusterResult | null>(null);

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

            const data = await response.json();

            if (!data.success) {
                throw new Error(data.error || 'Unknown error occurred during clustering');
            }

            if (data.combined_result && selectedColumns.length > 1) {
                setResult(data.combined_result);
            } else if (Object.keys(data.individual_results).length > 0) {
                const firstKey = Object.keys(data.individual_results)[0];
                setResult(data.individual_results[firstKey]);
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
            <div className="dialog-content segments-dialog">
                <div className="dialog-header">
                    <h2>Data Segments</h2>
                    <button className="close-button" onClick={onClose}>×</button>
                </div>
                <div className="dialog-body">
                    <h3>K-means Clustering Results</h3>

                    {isLoading ? (
                        <div className="loading-container">
                            <p>Generating clusters...</p>
                        </div>
                    ) : error ? (
                        <div className="error-container">
                            <p>Error: {error}</p>
                        </div>
                    ) : result ? (
                        <>
                            {result.plot && (
                                <div className="plot-container">
                                    <h4>Scatter Plot</h4>
                                    <img
                                        src={`data:image/png;base64,${result.plot}`}
                                        alt="Scatter Plot"
                                        className="plot-image"
                                    />
                                </div>
                            )}

                            {result.explanations && (
                                <div className="explanations-container">
                                    <h4 className="explanations-title">Cluster Explanations</h4>

                                    {result.explanations.profile_plot && (
                                        <div className="profile-plot-container">
                                            <h5>Cluster Profiles</h5>
                                            <img
                                                src={`data:image/png;base64,${result.explanations.profile_plot}`}
                                                alt="Cluster Profile"
                                                className="profile-image"
                                            />
                                        </div>
                                    )}

                                    <div className="clusters-grid">
                                        {result.explanations.cluster_descriptions.map((desc) => (
                                            <div key={`desc-${desc.cluster_id}`} className="cluster-card">
                                                <div className="cluster-header">
                                                    <h5 className="cluster-title">
                                                        Cluster {desc.cluster_id + 1}
                                                    </h5>
                                                    <span className="cluster-count">
                                                        {result.cluster_info.find(c => c.id === desc.cluster_id)?.count} records
                                                    </span>
                                                </div>

                                                <p className="cluster-description">
                                                    {desc.description}
                                                </p>

                                                <div className="features-section">
                                                    <p className="features-title">Key Features:</p>
                                                    <div className="features-container">
                                                        {desc.top_features.map((feature, i) => (
                                                            <span key={i} className="feature-tag">
                                                                {feature}
                                                            </span>
                                                        ))}
                                                    </div>
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )}

                            <div className="clusters-table-container">
                                <div className="clusters-grid">
                                    {result.cluster_info.map((cluster, idx) => (
                                        <div key={idx} className="cluster-data-card">
                                            <h4>Cluster {cluster.id + 1}</h4>
                                            <div className="cluster-center">
                                                {Object.entries(cluster.center).map(([col, value], i) => (
                                                    <div key={i} className="center-item">
                                                        <strong>{col}:</strong> {value.toFixed(2)}
                                                    </div>
                                                ))}
                                            </div>
                                            <div className="cluster-count-badge">
                                                {cluster.count} records
                                            </div>

                                            <div className="sample-data-container">
                                                <table className="sample-data-table">
                                                    <thead>
                                                    <tr>
                                                        <th>#</th>
                                                        {selectedColumns.map((column, i) => (
                                                            <th key={i}>{column}</th>
                                                        ))}
                                                    </tr>
                                                    </thead>
                                                    <tbody>
                                                    {cluster.sample_data.map((point, i) => (
                                                        <tr key={i} className={i % 2 === 0 ? 'even-row' : 'odd-row'}>
                                                            <td>{i + 1}</td>
                                                            {selectedColumns.map((column, j) => (
                                                                <td key={j}>
                                                                    {point[column] === null ||
                                                                    point[column] === undefined
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
                    ) : null}
                </div>
                <div className="dialog-footer">
                    <button className="ok-button" onClick={onClose}>Close</button>
                </div>
            </div>
        </div>
    );
};

export default SegmentsDialog;