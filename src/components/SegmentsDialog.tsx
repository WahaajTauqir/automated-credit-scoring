import { useState, useEffect } from 'react';
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
                    ) : result ? (
                        <>
                            {result.plot && (
                                <div style={{ textAlign: 'center', marginBottom: '20px' }}>
                                    <h4>Scatter Plot</h4>
                                    <img
                                        src={`data:image/png;base64,${result.plot}`}
                                        alt="Scatter Plot"
                                        style={{ maxWidth: '100%', height: 'auto' }}
                                    />
                                </div>
                            )}

                            {result.explanations && (
                                <div style={{ marginBottom: '30px' }}>
                                    <h4>Cluster Explanations</h4>

                                    {result.explanations.profile_plot && (
                                        <div style={{ textAlign: 'center', marginBottom: '20px' }}>
                                            <h5>Cluster Profiles</h5>
                                            <img
                                                src={`data:image/png;base64,${result.explanations.profile_plot}`}
                                                alt="Cluster Profile"
                                                style={{ maxWidth: '100%', height: 'auto' }}
                                            />
                                        </div>
                                    )}

                                    <div style={{ marginBottom: '20px' }}>
                                        <h5>Key Characteristics</h5>
                                        {result.explanations.cluster_descriptions.map((desc) => (
                                            <div
                                                key={`desc-${desc.cluster_id}`}
                                                style={{
                                                    backgroundColor: '#f8f9fa',
                                                    padding: '15px',
                                                    borderRadius: '8px',
                                                    marginBottom: '10px'
                                                }}
                                            >
                                                <p style={{ fontWeight: 'bold' }}>Cluster {desc.cluster_id + 1}:</p>
                                                <p>{desc.description}</p>
                                                <div style={{ marginTop: '10px' }}>
                                                    <p style={{ fontWeight: 'bold' }}>Top Features:</p>
                                                    <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
                                                        {desc.top_features.map((feature, i) => (
                                                            <span
                                                                key={i}
                                                                style={{
                                                                    backgroundColor: '#e9f5ff',
                                                                    padding: '5px 10px',
                                                                    borderRadius: '20px',
                                                                    fontSize: '0.9em'
                                                                }}
                                                            >
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

                            <div style={{ overflowX: 'auto', width: '100%' }}>
                                <div
                                    style={{
                                        display: 'grid',
                                        gridTemplateColumns: `repeat(${Math.min(result.cluster_info.length, 4)}, 1fr)`,
                                        gap: '10px',
                                        marginBottom: '20px'
                                    }}
                                >
                                    {result.cluster_info.map((cluster, idx) => (
                                        <div
                                            key={idx}
                                            style={{
                                                padding: '15px',
                                                backgroundColor: '#f0f7ff',
                                                borderRadius: '8px',
                                                textAlign: 'center',
                                                border: '1px solid #d0e3ff'
                                            }}
                                        >
                                            <h4>Cluster {cluster.id + 1}</h4>
                                            <div style={{ marginBottom: '10px' }}>
                                                {Object.entries(cluster.center).map(([col, value], i) => (
                                                    <div
                                                        key={i}
                                                        style={{ marginBottom: '5px', textAlign: 'left' }}
                                                    >
                                                        <strong>{col}:</strong> {value.toFixed(2)}
                                                    </div>
                                                ))}
                                            </div>
                                            <div
                                                style={{
                                                    fontSize: '1.2em',
                                                    fontWeight: 'bold',
                                                    backgroundColor: '#0066cc',
                                                    color: 'white',
                                                    padding: '5px 10px',
                                                    borderRadius: '4px',
                                                    marginBottom: '15px'
                                                }}
                                            >
                                                {cluster.count} records
                                            </div>

                                            <div
                                                style={{
                                                    height: '200px',
                                                    overflowY: 'auto',
                                                    border: '1px solid #ddd',
                                                    borderRadius: '4px',
                                                    backgroundColor: 'white'
                                                }}
                                            >
                                                <table
                                                    style={{
                                                        width: '100%',
                                                        borderCollapse: 'collapse'
                                                    }}
                                                >
                                                    <thead
                                                        style={{
                                                            position: 'sticky',
                                                            top: 0,
                                                            backgroundColor: '#f0f0f0',
                                                            zIndex: 1
                                                        }}
                                                    >
                                                    <tr>
                                                        <th
                                                            style={{
                                                                padding: '8px',
                                                                borderBottom: '1px solid #ddd',
                                                                textAlign: 'center'
                                                            }}
                                                        >
                                                            #
                                                        </th>
                                                        {selectedColumns.map((column, i) => (
                                                            <th
                                                                key={i}
                                                                style={{
                                                                    padding: '8px',
                                                                    borderBottom: '1px solid #ddd',
                                                                    textAlign: 'center'
                                                                }}
                                                            >
                                                                {column}
                                                            </th>
                                                        ))}
                                                    </tr>
                                                    </thead>
                                                    <tbody>
                                                    {cluster.sample_data.map((point, i) => (
                                                        <tr
                                                            key={i}
                                                            style={{
                                                                backgroundColor: i % 2 === 0 ? '#f9f9f9' : 'white'
                                                            }}
                                                        >
                                                            <td
                                                                style={{
                                                                    padding: '6px',
                                                                    borderBottom: '1px solid #ddd',
                                                                    textAlign: 'center'
                                                                }}
                                                            >
                                                                {i + 1}
                                                            </td>
                                                            {selectedColumns.map((column, j) => (
                                                                <td
                                                                    key={j}
                                                                    style={{
                                                                        padding: '6px',
                                                                        borderBottom: '1px solid #ddd',
                                                                        textAlign: 'center'
                                                                    }}
                                                                >
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
