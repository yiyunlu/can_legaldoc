import React, { useState, useEffect } from 'react';
import './App.css';
import { api, isBackendOnline } from './api';
import Dashboard from './pages/Dashboard';
import DataSources from './pages/DataSources';
import RunHistory from './pages/RunHistory';
import Settings from './pages/Settings';
import Documents from './pages/Documents';

const TABS = [
  { id: 'dashboard',  label: 'Dashboard',    icon: '\u2302' },
  { id: 'sources',    label: 'Data Sources',  icon: '\u29C9' },
  { id: 'documents',  label: 'Documents',     icon: '\u2630' },
  { id: 'history',    label: 'Run History',   icon: '\u29D6' },
  { id: 'settings',   label: 'Settings',      icon: '\u2699' },
];

export default function App() {
  const [tab, setTab] = useState('dashboard');
  const [status, setStatus] = useState(null);
  const [stats, setStats] = useState(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [online, setOnline] = useState(true);

  // Poll scraper status — 2s when running, 5s idle, 10s offline
  useEffect(() => {
    let timer;
    const poll = async () => {
      try {
        const s = await api.getStatus();
        setStatus(s);
        setOnline(true);
      } catch {
        setOnline(isBackendOnline());
      }
      const interval = (!isBackendOnline()) ? 10000 : (status?.is_running ? 2000 : 5000);
      timer = setTimeout(poll, interval);
    };
    poll();
    return () => clearTimeout(timer);
  }, []);

  // Fetch DB stats on mount and when scraper finishes
  const refreshStats = () => api.getSourceStats().then(setStats).catch(() => {});
  useEffect(() => { refreshStats(); }, []);
  useEffect(() => {
    if (status && !status.is_running) refreshStats();
  }, [status?.is_running]);

  const isRunning = status?.is_running || false;
  const statusClass = !online ? 'offline' : isRunning ? 'running' : (status?.message?.startsWith('Error') ? 'error' : 'idle');
  const statusLabel = !online ? 'Offline' : isRunning ? 'Running' : 'Idle';

  const switchTab = (id) => {
    setTab(id);
    setMenuOpen(false);
  };

  return (
    <div className="app-layout">
      {/* ── Mobile Header ── */}
      <div className="mobile-header">
        <button className={`hamburger ${menuOpen ? 'open' : ''}`} onClick={() => setMenuOpen(!menuOpen)}>
          <span /><span /><span />
        </button>
        <span className="mobile-brand">Canadian Legal Data</span>
        <span className={`status-dot ${statusClass} mobile-status-dot`} />
      </div>

      {/* ── Sidebar Overlay (mobile) ── */}
      <div className={`sidebar-overlay ${menuOpen ? 'visible' : ''}`} onClick={() => setMenuOpen(false)} />

      {/* ── Sidebar ── */}
      <nav className={`sidebar ${menuOpen ? 'open' : ''}`}>
        <div className="sidebar-brand">
          <h1>Canadian Legal Data</h1>
          <div className="version">v5.7 Multi-Source Platform</div>
        </div>

        <div className="sidebar-nav">
          {TABS.map(t => (
            <a
              key={t.id}
              className={`nav-item ${tab === t.id ? 'active' : ''}`}
              onClick={() => switchTab(t.id)}
            >
              <span className="nav-icon">{t.icon}</span>
              {t.label}
            </a>
          ))}
        </div>

        <div className="sidebar-status">
          <div className="status-indicator">
            <span className={`status-dot ${statusClass}`} />
            {statusLabel}
          </div>
          {isRunning && status?.current_source && (
            <div className="status-detail">{status.current_source}</div>
          )}
          {isRunning && (
            <div className="status-detail" style={{ marginTop: 2 }}>
              {status.stats.success} done / {status.stats.total} total
            </div>
          )}
          {!isRunning && status?.scheduler?.enabled && status?.scheduler?.next_run_at && (
            <div className="status-detail" style={{ marginTop: 4, fontSize: 10, color: 'var(--text-muted)' }}>
              ⏱ Next: {new Date(status.scheduler.next_run_at).toLocaleString('en-CA', {
                month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
              })}
            </div>
          )}
        </div>
      </nav>

      {/* ── Main Content ── */}
      <main className="main-content">
        {tab === 'dashboard' && <Dashboard status={status} stats={stats} />}
        {tab === 'sources'   && <DataSources status={status} stats={stats} onRefreshStats={refreshStats} />}
        {tab === 'documents' && <Documents stats={stats} />}
        {tab === 'history'   && <RunHistory stats={stats} />}
        {tab === 'settings'  && <Settings />}
      </main>
    </div>
  );
}
