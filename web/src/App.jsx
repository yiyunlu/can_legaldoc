import React, { useState, useEffect } from 'react';
import './App.css';
import { api } from './api';
import Dashboard from './pages/Dashboard';
import DataSources from './pages/DataSources';
import RunHistory from './pages/RunHistory';
import Settings from './pages/Settings';

const TABS = [
  { id: 'dashboard',  label: 'Dashboard',    icon: '\u2302' },
  { id: 'sources',    label: 'Data Sources',  icon: '\u29C9' },
  { id: 'history',    label: 'Run History',   icon: '\u29D6' },
  { id: 'settings',   label: 'Settings',      icon: '\u2699' },
];

export default function App() {
  const [tab, setTab] = useState('dashboard');
  const [status, setStatus] = useState(null);
  const [stats, setStats] = useState(null);

  // Poll scraper status every 2s
  useEffect(() => {
    const poll = () => api.getStatus().then(setStatus).catch(() => {});
    poll();
    const id = setInterval(poll, 2000);
    return () => clearInterval(id);
  }, []);

  // Fetch DB stats on mount and when scraper finishes
  const refreshStats = () => api.getSourceStats().then(setStats).catch(() => {});
  useEffect(() => { refreshStats(); }, []);
  useEffect(() => {
    if (status && !status.is_running) refreshStats();
  }, [status?.is_running]);

  const isRunning = status?.is_running || false;
  const statusClass = isRunning ? 'running' : (status?.message?.startsWith('Error') ? 'error' : 'idle');

  return (
    <div className="app-layout">
      {/* ── Sidebar ── */}
      <nav className="sidebar">
        <div className="sidebar-brand">
          <h1>Canadian Legal Data</h1>
          <div className="version">v5.0 Multi-Source Platform</div>
        </div>

        <div className="sidebar-nav">
          {TABS.map(t => (
            <a
              key={t.id}
              className={`nav-item ${tab === t.id ? 'active' : ''}`}
              onClick={() => setTab(t.id)}
            >
              <span className="nav-icon">{t.icon}</span>
              {t.label}
            </a>
          ))}
        </div>

        <div className="sidebar-status">
          <div className="status-indicator">
            <span className={`status-dot ${statusClass}`} />
            {isRunning ? 'Running' : 'Idle'}
          </div>
          {isRunning && status?.current_source && (
            <div className="status-detail">{status.current_source}</div>
          )}
          {isRunning && (
            <div className="status-detail" style={{ marginTop: 2 }}>
              {status.stats.success} done / {status.stats.total} total
            </div>
          )}
        </div>
      </nav>

      {/* ── Main Content ── */}
      <main className="main-content">
        {tab === 'dashboard' && <Dashboard status={status} stats={stats} />}
        {tab === 'sources'   && <DataSources status={status} stats={stats} onRefreshStats={refreshStats} />}
        {tab === 'history'   && <RunHistory stats={stats} />}
        {tab === 'settings'  && <Settings />}
      </main>
    </div>
  );
}
