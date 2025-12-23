import React, { useState, useEffect } from 'react';
import './App.css';
import { api } from './api';

function App() {
  const [activeTab, setActiveTab] = useState('dashboard'); // dashboard, config, discovery
  const [status, setStatus] = useState(null);

  const fetchStatus = async () => {
    try {
      const data = await api.getStatus();
      setStatus(data);
    } catch (e) {
      console.error(e);
    }
  };

  // Scraper Status Polling
  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 2000);
    return () => clearInterval(interval);
  }, []);

  const [visualMode, setVisualMode] = useState(false);
  const [cdpUrl, setCdpUrl] = useState('');
  const [scrapeLimit, setScrapeLimit] = useState(100);
  const [showAdvanced, setShowAdvanced] = useState(false);

  const handleStartScraper = async (engine) => {
    try {
      await api.startScraper({
        engine,
        headless: !visualMode,
        cdp_url: cdpUrl || null,
        scrape_limit: parseInt(scrapeLimit) || 100
      });
      fetchStatus();
    } catch (error) {
      console.error("Failed to start scraper", error);
    }
  };

  const handleStopScraper = async () => {
    try {
      await api.stopScraper();
      fetchStatus();
    } catch (error) {
      console.error("Failed to stop scraper", error);
    }
  };

  return (
    <div className="app-container">
      {/* Sidebar - Controls & Navigation */}
      <div className="sidebar">
        <h1 style={{ fontSize: '16px', margin: '0 0 10px 0' }}>CanLII Manager</h1>

        <div className="sidebar-section">
          <h2>Status</h2>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span className={status?.is_running ? 'status-valid' : 'status-invalid'}>
              {status?.is_running ? 'RUNNING' : 'IDLE'}
            </span>
            {/* The toggleScraper button is replaced by controls in DashboardView */}
          </div>
          {status?.current_target && (
            <div style={{ marginTop: '5px', fontSize: '11px', color: 'gray' }}>
              Current: {status.current_target}
            </div>
          )}
          <div style={{ marginTop: '10px' }}>
            <div>Success: {status?.stats?.success || 0}</div>
            <div>Failed: {status?.stats?.failed || 0}</div>
            <div>Total: {status?.stats?.total || 0}</div>
          </div>
        </div>

        <div className="sidebar-section">
          <h2>Navigation</h2>
          <div className="filter-group">
            <a href="#" className={`nav-link ${activeTab === 'dashboard' ? 'active' : ''}`} onClick={(e) => { e.preventDefault(); setActiveTab('dashboard'); }}>Overview</a>
            <a href="#" className={`nav-link ${activeTab === 'config' ? 'active' : ''}`} onClick={(e) => { e.preventDefault(); setActiveTab('config'); }}>Configuration</a>
            <a href="#" className={`nav-link ${activeTab === 'discovery' ? 'active' : ''}`} onClick={(e) => { e.preventDefault(); setActiveTab('discovery'); }}>Auto Discovery</a>
          </div>
        </div>

        {/* Future Filters could go here */}
        <div className="sidebar-section">
          <h2>Filters (Future)</h2>
          <div className="filter-group">
            <label><input type="checkbox" checked readOnly /> Statutes</label>
            <label><input type="checkbox" checked readOnly /> Regulations</label>
          </div>
        </div>
      </div>

      {/* Main Content Area */}
      <div className="main-content">
        {activeTab === 'dashboard' && (
          <DashboardView
            status={status}
            handleStartScraper={handleStartScraper}
            handleStopScraper={handleStopScraper}
            visualMode={visualMode}
            setVisualMode={setVisualMode}
            cdpUrl={cdpUrl}
            setCdpUrl={setCdpUrl}
            showAdvanced={showAdvanced}
            setShowAdvanced={setShowAdvanced}
            scrapeLimit={scrapeLimit}
            setScrapeLimit={setScrapeLimit}
          />
        )}
        {activeTab === 'config' && <ConfigView />}
        {activeTab === 'discovery' && <DiscoveryView />}
      </div>
    </div>
  );
}

// Sub-components for Views (kept in same file for density/simplicity or imported)
// For this refactor, I'll keep them simple inline or import existing logic if complex.
// Let's rewrite them to be "Dense" style.

function DashboardView({
  status, handleStartScraper, handleStopScraper,
  visualMode, setVisualMode, cdpUrl, setCdpUrl,
  showAdvanced, setShowAdvanced,
  scrapeLimit, setScrapeLimit
}) {
  if (!status) return <div>Loading...</div>;
  return (
    <div style={{ padding: '20px' }}>
      <div className="card" style={{ marginBottom: '20px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '15px' }}>
          <h2 style={{ margin: 0 }}>Scraper Controls</h2>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px', background: 'var(--bg-secondary)', padding: '4px 10px', borderRadius: '20px', border: '1px solid var(--border-color)' }}>
            <input
              type="checkbox"
              checked={visualMode}
              onChange={(e) => setVisualMode(e.target.checked)}
              id="visual-mode-toggle"
            />
            <label htmlFor="visual-mode-toggle" style={{ cursor: 'pointer' }}>Visual Mode (Headful)</label>
          </div>
        </div>

        <div className="control-group" style={{ display: 'flex', gap: '10px' }}>
          <button
            className="primary"
            onClick={() => handleStartScraper('fast')}
            disabled={status.is_running}
          >
            Start Fast Engine
          </button>
          <button
            className="secondary"
            onClick={() => handleStartScraper('deep')}
            disabled={status.is_running}
          >
            Start Deep Engine
          </button>
          <button
            className="error"
            onClick={handleStopScraper}
            disabled={!status.is_running}
          >
            Stop Scraper
          </button>
        </div>

        <div style={{ marginTop: '15px' }}>
          <button
            className="text-link"
            style={{ fontSize: '12px', padding: 0, color: 'var(--text-secondary)' }}
            onClick={() => setShowAdvanced(!showAdvanced)}
          >
            {showAdvanced ? '▼ Hide Advanced Settings' : '▶ Advanced Settings (CDP)'}
          </button>

          {showAdvanced && (
            <div style={{ marginTop: '10px', padding: '15px', border: '1px solid var(--border-color)', borderRadius: '8px', background: 'var(--bg-secondary)' }}>
              <div className="form-group">
                <label style={{ fontSize: '12px', display: 'block', marginBottom: '5px' }}>
                  CDP URL (Connect to your real Chrome)
                </label>
                <div style={{ display: 'flex', gap: '8px', marginBottom: '10px' }}>
                  <input
                    type="text"
                    value={cdpUrl}
                    onChange={(e) => setCdpUrl(e.target.value)}
                    placeholder="e.g. http://127.0.0.1:9222"
                    style={{ flex: 1, padding: '8px', borderRadius: '4px', border: '1px solid var(--border-color)', background: 'var(--bg-primary)', color: 'var(--text-primary)' }}
                  />
                  <button
                    onClick={() => setCdpUrl('http://127.0.0.1:9222')}
                    style={{ padding: '0 10px', fontSize: '11px' }}
                  >
                    Set Default
                  </button>
                </div>

                <div style={{ marginTop: '15px' }}>
                  <label style={{ fontSize: '12px', display: 'block', marginBottom: '5px' }}>
                    Scrape Limit (Max NEW items to scrape)
                  </label>
                  <input
                    type="number"
                    value={scrapeLimit}
                    onChange={(e) => setScrapeLimit(e.target.value)}
                    style={{ padding: '8px', borderRadius: '4px', border: '1px solid var(--border-color)', background: 'var(--bg-primary)', color: 'var(--text-primary)', width: '80px' }}
                  />
                  <span style={{ fontSize: '11px', color: 'var(--text-secondary)', marginLeft: '10px' }}>
                    (Skips existing data, stops after {scrapeLimit} new items)
                  </span>
                </div>

                <div style={{ marginTop: '15px', fontSize: '11px', color: 'var(--text-secondary)' }}>
                  <strong>How to use Real Browser:</strong>
                  <p style={{ margin: '5px 0' }}>1. Close all Chrome windows.</p>
                  <p style={{ margin: '5px 0' }}>2. Run this command in your terminal:</p>
                  <div style={{
                    position: 'relative',
                    background: '#1e1e1e',
                    color: '#d4d4d4',
                    padding: '10px',
                    borderRadius: '4px',
                    fontFamily: 'monospace',
                    fontSize: '10px',
                    marginTop: '5px',
                    wordBreak: 'break-all',
                    border: '1px solid #333'
                  }}>
                    {`/Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome --remote-debugging-port=9222 --user-data-dir="${window.location.protocol === 'file:' ? '.' : ''}${"./.chrome_data"}"`}
                    <button
                      onClick={() => {
                        const cmd = `/Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome --remote-debugging-port=9222 --user-data-dir="./.chrome_data"`;
                        navigator.clipboard.writeText(cmd);
                        alert('Command copied to clipboard!');
                      }}
                      style={{
                        position: 'absolute',
                        right: '5px',
                        top: '5px',
                        padding: '2px 5px',
                        fontSize: '9px',
                        background: '#333',
                        color: '#eee',
                        border: 'none',
                        borderRadius: '2px',
                        cursor: 'pointer'
                      }}
                    >
                      Copy
                    </button>
                  </div>
                  <p style={{ marginTop: '8px', color: 'var(--primary)', fontStyle: 'italic' }}>
                    Tip: Using <code>./.chrome_data</code> ensures your login/cookies are remembered, so you won't see CAPTCHAs again!
                  </p>
                </div>
              </div>
            </div>
          )}
        </div>

        {visualMode && !cdpUrl && (
          <div style={{
            marginTop: '15px',
            padding: '10px',
            background: 'rgba(52, 152, 219, 0.1)',
            borderRadius: '6px',
            fontSize: '13px',
            color: 'var(--text-primary)',
            borderLeft: '4px solid #3498db'
          }}>
            <strong>💡 Anti-Captcha Mode:</strong> A browser window will open. If you see a verification screen, please solve it manually in that window. The scraper will wait for you!
          </div>
        )}
      </div>

      <div className="card">
        <h2>Live Statistics</h2>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: '15px', marginTop: '15px' }}>
          <div style={{ textAlign: 'center', padding: '15px', background: 'var(--bg-secondary)', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
            <div style={{ fontSize: '11px', color: 'gray', marginBottom: '5px' }}>REMAINING</div>
            <div style={{ fontSize: '22px', fontWeight: 'bold', color: 'var(--primary)' }}>
              {status.scrape_limit ? Math.max(0, status.scrape_limit - (status.stats.success + status.stats.failed)) : '--'}
            </div>
          </div>
          <div style={{ textAlign: 'center', padding: '15px', background: 'var(--bg-secondary)', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
            <div style={{ fontSize: '11px', color: 'gray', marginBottom: '5px' }}>TOTAL TARGETS</div>
            <div style={{ fontSize: '22px', fontWeight: 'bold' }}>{status.stats.total}</div>
          </div>
          <div style={{ textAlign: 'center', padding: '15px', background: 'rgba(46, 204, 113, 0.05)', borderRadius: '8px', border: '1px solid rgba(46, 204, 113, 0.2)' }}>
            <div style={{ fontSize: '11px', color: '#27ae60', marginBottom: '5px' }}>SUCCESS</div>
            <div style={{ fontSize: '22px', fontWeight: 'bold', color: '#2ecc71' }}>{status.stats.success}</div>
          </div>
          <div style={{ textAlign: 'center', padding: '15px', background: 'rgba(231, 76, 60, 0.05)', borderRadius: '8px', border: '1px solid rgba(231, 76, 60, 0.2)' }}>
            <div style={{ fontSize: '11px', color: '#c0392b', marginBottom: '5px' }}>FAILED</div>
            <div style={{ fontSize: '22px', fontWeight: 'bold', color: '#e74c3c' }}>{status.stats.failed}</div>
          </div>
          <div style={{ textAlign: 'center', padding: '15px', background: 'var(--bg-secondary)', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
            <div style={{ fontSize: '11px', color: 'gray', marginBottom: '5px' }}>SKIPPED</div>
            <div style={{ fontSize: '22px', fontWeight: 'bold' }}>{status.stats.skipped}</div>
          </div>
        </div>

        <div style={{ marginTop: '20px' }}>
          <div style={{ fontSize: '13px', color: 'gray', marginBottom: '5px' }}>System Message</div>
          <div style={{ padding: '10px', background: 'var(--bg-secondary)', borderRadius: '4px', fontStyle: 'italic' }}>
            {status.message}
          </div>
        </div>
      </div>
    </div>
  );
}

import ConfigViewComponent from './pages/Configuration'; // Reuse logic but might need style tweaks
// Actually, let's just re-implement a dense version here to match the style perfectly
// or wrap the existing standard logic if it allows custom styling. 
// Given the radical style change, it's safer to rewrite the render part or adapt the css.
// Adaptation via CSS (.table, .input classes) should work if we reused class names.

function ConfigView() {
  // We can reuse the existing `pages/Configuration.jsx` if we updated its classNames or if it uses standard HTML elements we styled in App.css.
  // Let's try importing it first, but we might need to strip the "Card" wrappers.
  return <ConfigViewComponent />;
}

import DiscoveryViewComponent from './pages/Discovery';
function DiscoveryView() {
  return <DiscoveryViewComponent />;
}

export default App;
