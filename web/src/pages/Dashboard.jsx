import React, { useEffect, useState } from 'react';
import { api } from '../api';

function Dashboard() {
    const [status, setStatus] = useState(null);
    const [loading, setLoading] = useState(true);

    const fetchStatus = async () => {
        try {
            const data = await api.getStatus();
            setStatus(data);
        } catch (error) {
            console.error("Failed to fetch status", error);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchStatus();
        const interval = setInterval(fetchStatus, 2000); // Poll every 2s
        return () => clearInterval(interval);
    }, []);

    const handleStart = async () => {
        try {
            await api.startScraper();
            fetchStatus();
        } catch (e) {
            alert("Error starting scraper: " + e.message);
        }
    };

    const handleStop = async () => {
        try {
            await api.stopScraper();
            fetchStatus();
        } catch (e) {
            alert("Error stopping scraper: " + e.message);
        }
    };

    if (loading && !status) return <div>Loading...</div>;

    return (
        <div>
            <div className="card">
                <h2>System Status</h2>
                <div style={{ display: 'flex', alignItems: 'center', gap: '20px', marginBottom: '20px' }}>
                    <div className={`status-badge ${status?.is_running ? 'status-active' : 'status-inactive'}`}>
                        {status?.is_running ? 'RUNNING' : 'IDLE'}
                    </div>
                    <div>{status?.message}</div>
                </div>

                <div style={{ display: 'flex', gap: '10px' }}>
                    {!status?.is_running ? (
                        <button className="btn" onClick={handleStart}>Start Scraping</button>
                    ) : (
                        <button className="btn btn-danger" onClick={handleStop}>Stop Scraping</button>
                    )}
                </div>
            </div>

            <div className="card">
                <h2>Statistics</h2>
                <div className="stats-grid">
                    <div className="stat-item">
                        <div className="stat-value">{status?.stats?.total || 0}</div>
                        <div className="stat-label">Total Found</div>
                    </div>
                    <div className="stat-item">
                        <div className="stat-value" style={{ color: 'var(--success)' }}>{status?.stats?.success || 0}</div>
                        <div className="stat-label">Successfully Scraped</div>
                    </div>
                    <div className="stat-item">
                        <div className="stat-value" style={{ color: 'var(--error)' }}>{status?.stats?.failed || 0}</div>
                        <div className="stat-label">Failed</div>
                    </div>
                    <div className="stat-item">
                        <div className="stat-value" style={{ color: 'var(--text-secondary)' }}>{status?.stats?.skipped || 0}</div>
                        <div className="stat-label">Skipped (Already Exists)</div>
                    </div>
                </div>
            </div>

            {status?.current_target && (
                <div className="card">
                    <h2>Current Activity</h2>
                    <p>Processing Target: <strong>{status.current_target}</strong></p>
                </div>
            )}
        </div>
    );
}

export default Dashboard;
