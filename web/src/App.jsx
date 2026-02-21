import React, { useState, useEffect, useCallback } from 'react';
import './App.css';
import { api, isBackendOnline, getStoredKey, setStoredKey, clearStoredKey } from './api';
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

/* ═════════════════════════════════════════════
   Login Gate — shown when auth is required
   and no valid key is stored
   ═════════════════════════════════════════════ */
function LoginGate({ onLogin }) {
  const [key, setKey] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!key.trim()) return;
    setLoading(true);
    setError('');
    try {
      await api.verifyKey(key.trim());
      setStoredKey(key.trim());
      onLogin();
    } catch (err) {
      setError(err.message || 'Invalid API key');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-overlay">
      <form className="login-box" onSubmit={handleSubmit}>
        <div className="login-brand">Canadian Legal Data</div>
        <div className="login-subtitle">Admin Authentication Required</div>
        <input
          className="input login-input"
          type="password"
          placeholder="Enter API key"
          value={key}
          onChange={e => setKey(e.target.value)}
          autoFocus
        />
        {error && <div className="login-error">{error}</div>}
        <button className="btn btn-primary login-btn" type="submit" disabled={loading || !key.trim()}>
          {loading ? 'Verifying...' : 'Unlock'}
        </button>
      </form>
    </div>
  );
}

/* ═════════════════════════════════════════════
   Main App
   ═════════════════════════════════════════════ */
export default function App() {
  const [tab, setTab] = useState('dashboard');
  const [status, setStatus] = useState(null);
  const [stats, setStats] = useState(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [online, setOnline] = useState(true);

  // Auth state: null = checking, true = needs login, false = ready
  const [authRequired, setAuthRequired] = useState(null);

  // Check if auth is required and whether stored key is valid
  useEffect(() => {
    (async () => {
      try {
        const { auth_required } = await api.getAuthStatus();
        if (!auth_required) {
          setAuthRequired(false);  // dev mode, no auth needed
          return;
        }
        // Auth is required — check if we have a stored key
        const stored = getStoredKey();
        if (!stored) {
          setAuthRequired(true);
          return;
        }
        // Verify the stored key
        await api.verifyKey(stored);
        setAuthRequired(false);
      } catch {
        // If auth check fails, check if we have a stored key
        if (getStoredKey()) {
          setAuthRequired(false);  // might be offline, allow through
        } else {
          setAuthRequired(true);
        }
      }
    })();
  }, []);

  const handleLogin = useCallback(() => {
    setAuthRequired(false);
  }, []);

  const handleLogout = useCallback(() => {
    clearStoredKey();
    setAuthRequired(true);
  }, []);

  // Poll scraper status — 2s when running, 5s idle, 10s offline
  useEffect(() => {
    if (authRequired !== false) return; // don't poll until authed
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
  }, [authRequired]);

  // Fetch DB stats on mount and when scraper finishes
  const refreshStats = () => api.getSourceStats().then(setStats).catch(() => {});
  useEffect(() => {
    if (authRequired !== false) return;
    refreshStats();
  }, [authRequired]);
  useEffect(() => {
    if (status && !status.is_running) refreshStats();
  }, [status?.is_running]);

  // ── Loading state ──
  if (authRequired === null) {
    return (
      <div className="login-overlay">
        <div className="login-box" style={{ textAlign: 'center' }}>
          <div className="login-brand">Canadian Legal Data</div>
          <div className="login-subtitle" style={{ marginTop: 12 }}>Loading...</div>
        </div>
      </div>
    );
  }

  // ── Login required ──
  if (authRequired === true) {
    return <LoginGate onLogin={handleLogin} />;
  }

  // ── Authenticated ──
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
          <div className="version">v5.8 Multi-Source Platform</div>
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
              Next: {new Date(status.scheduler.next_run_at).toLocaleString('en-CA', {
                month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
              })}
            </div>
          )}
          {getStoredKey() && (
            <button
              className="btn btn-ghost btn-sm"
              style={{ marginTop: 10, width: '100%', justifyContent: 'center', fontSize: 11 }}
              onClick={handleLogout}
            >
              Lock
            </button>
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
