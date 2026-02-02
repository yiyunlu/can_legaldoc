import React, { useState, useEffect } from 'react';
import { api } from '../api';

function Discovery() {
    const [results, setResults] = useState([]);
    const [loading, setLoading] = useState(false);
    const [progress, setProgress] = useState({ message: '', percent: 0 });
    const [error, setError] = useState(null);
    const [existingTargets, setExistingTargets] = useState([]);
    const [filters, setFilters] = useState({
        Statutes: true,
        Regulations: true,
        Courts: true,
        'Boards and Tribunals': true
    });

    useEffect(() => {
        loadConfig();
        loadCache();
    }, []);

    const loadCache = async () => {
        try {
            const data = await api.getDiscoveryCache();
            if (data.results && data.results.length > 0) {
                setResults(data.results);
            }
        } catch (err) {
            console.error("Failed to load discovery cache", err);
        }
    };

    const loadConfig = async () => {
        try {
            const config = await api.getConfig();
            setExistingTargets(config.targets || []);
        } catch (err) {
            console.error("Failed to load config", err);
        }
    };

    const handleExplore = async () => {
        setLoading(true);
        setError(null);
        // Don't clear results immediately if we want to append, 
        // but if we are starting fresh scan, maybe we should clear or overwrite?
        // User requested "Show real time". 
        // Let's clear to show fresh scan, or keep existing?
        // Usually invalidating old cache is better for fresh scan.
        setResults([]);
        setProgress({ message: 'Starting scan...', percent: 0 });

        try {
            // refresh config just in case
            await loadConfig();

            await api.exploreTargetsStream((event) => {
                if (event.type === 'progress') {
                    setProgress({ message: event.message, percent: event.percent });
                } else if (event.type === 'found') {
                    setResults(prev => {
                        // Avoid duplicates if using React.StrictMode double-invokes or network retries
                        if (prev.some(r => r.url === event.data.url)) return prev;
                        return [...prev, event.data];
                    });
                } else if (event.type === 'complete') {
                    // Final sync just in case
                    setResults(event.results);
                } else if (event.type === 'error') {
                    setError("Discovery error: " + event.message);
                }
            });
        } catch (err) {
            setError("Discovery failed: " + err.message);
        } finally {
            setLoading(false);
            setProgress({ message: '', percent: 0 });
        }
    };

    const [addingIndex, setAddingIndex] = useState(null);

    const handleAddTarget = async (item) => {
        try {
            const currentConfig = await api.getConfig();
            // Check again for duplicate before adding
            if (currentConfig.targets.some(t => t.url === item.url)) {
                alert("Already exists!");
                await loadConfig();
                setAddingIndex(null);
                return;
            }

            const newTargets = [...currentConfig.targets, item];
            await api.updateConfig(newTargets);
            setExistingTargets(newTargets); // Update local state immediately
            setAddingIndex(null);
        } catch (err) {
            alert("Failed to add target");
            setAddingIndex(null);
        }
    };



    // Helper to check existence
    const isExisting = (url) => existingTargets.some(t => t.url === url);

    // Apply filters to results
    const filteredResults = results.filter(item => {
        const type = item.type;
        if (filters[type] !== undefined) {
            return filters[type];
        }
        return true; // Keep others by default
    });

    const toggleFilter = (cat) => {
        setFilters(prev => ({ ...prev, [cat]: !prev[cat] }));
    };

    return (
        <div>
            <div style={{ marginBottom: '15px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '15px', marginBottom: '10px' }}>
                    <button onClick={handleExplore} disabled={loading}>
                        {loading ? 'Scanning...' : 'Scan CanLII'}
                    </button>
                    {loading && (
                        <div style={{ flex: 1, display: 'flex', alignItems: 'center', gap: '10px' }}>
                            <div style={{
                                flex: 1,
                                height: '10px',
                                background: '#eee',
                                borderRadius: '5px',
                                overflow: 'hidden'
                            }}>
                                <div style={{
                                    width: `${progress.percent}%`,
                                    height: '100%',
                                    background: 'var(--primary)',
                                    transition: 'width 0.3s ease'
                                }} />
                            </div>
                            <span style={{ fontSize: '0.9em', color: '#666', minWidth: '150px' }}>
                                {progress.message}
                            </span>
                        </div>
                    )}
                </div>
                {error && <div style={{ color: 'var(--error)', marginTop: '5px' }}>{error}</div>}

                <div style={{
                    display: 'flex',
                    gap: '20px',
                    fontSize: '0.85em',
                    background: 'var(--bg-subtle)',
                    padding: '8px 12px',
                    borderRadius: '6px',
                    border: '1px solid var(--border-subtle)',
                    marginTop: '10px'
                }}>
                    <span style={{ fontWeight: 'bold', color: 'var(--text-secondary)' }}>Filters:</span>
                    {Object.keys(filters).map(cat => (
                        <label key={cat} style={{ display: 'flex', alignItems: 'center', gap: '5px', cursor: 'pointer' }}>
                            <input
                                type="checkbox"
                                checked={filters[cat]}
                                onChange={() => toggleFilter(cat)}
                            />
                            {cat}
                        </label>
                    ))}
                    <span style={{ marginLeft: 'auto', color: 'var(--text-secondary)' }}>
                        Showing {filteredResults.length} / {results.length}
                    </span>
                </div>
            </div>

            {filteredResults.length > 0 && (
                <div>
                    <h3 style={{ margin: '15px 0 10px 0', borderBottom: '1px solid var(--border-subtle)', paddingBottom: '10px' }}>
                        Discovered items
                    </h3>
                    <div style={{ overflowX: 'auto' }}>
                        <table className="dense-table" style={{ width: '100%' }}>
                            <thead>
                                <tr>
                                    <th style={{ width: '45%' }}>Name</th>
                                    <th style={{ width: '20%' }}>Province</th>
                                    <th style={{ width: '15%' }}>Type</th>
                                    <th style={{ width: '10%' }}>Details</th>
                                    <th style={{ width: '10%' }}>Actions</th>
                                </tr>
                            </thead>
                            <tbody>
                                {filteredResults.map((item, idx) => {
                                    const exists = isExisting(item.url);
                                    return (
                                        <tr key={idx}>
                                            <td>{item.type_name || item.name}</td>
                                            <td>{item.province_name} ({item.province})</td>
                                            <td>{item.type}</td>
                                            <td>
                                                {item.item_count !== undefined && item.item_count !== null
                                                    ? (item.item_count === "Browse" ? "Browse" : `${item.item_count} items`)
                                                    : 'Checking...'}
                                                <br />
                                                <a href={item.url} target="_blank" style={{ fontSize: '0.9em', color: 'var(--link-color)' }}>Link</a>
                                            </td>
                                            <td>
                                                {exists ? (
                                                    <span style={{
                                                        padding: '2px 6px',
                                                        fontSize: '0.8em',
                                                        background: 'var(--success)',
                                                        color: 'white',
                                                        borderRadius: '4px',
                                                        opacity: 0.8
                                                    }}>
                                                        Existing
                                                    </span>
                                                ) : addingIndex === idx ? (
                                                    <div style={{ display: 'flex', gap: '5px' }}>
                                                        <span className="action-link" onClick={() => handleAddTarget(item)} style={{ color: 'var(--success)', fontWeight: 'bold' }}>Sure?</span>
                                                        <span className="action-link" onClick={() => setAddingIndex(null)} style={{ color: 'gray' }}>Cancel</span>
                                                    </div>
                                                ) : (
                                                    <span className="action-link"
                                                        onClick={(e) => { e.stopPropagation(); setAddingIndex(idx); }}
                                                        style={{ color: 'var(--link-color)' }}
                                                    >
                                                        Add
                                                    </span>
                                                )}
                                            </td>
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}
        </div>
    );
}

export default Discovery;
