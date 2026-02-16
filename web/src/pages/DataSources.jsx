import React, { useState, useEffect } from 'react';
import { api } from '../api';

const JUR_NAMES = {
  ca: 'Federal', bc: 'British Columbia', ab: 'Alberta', on: 'Ontario',
  qc: 'Quebec', multi: 'All Jurisdictions',
};

const SOURCE_META = {
  justice_canada_xml: { label: 'XML', badge: 'badge-xml', total: '~5,795' },
  bc_laws_api:        { label: 'API', badge: 'badge-api', total: '~882' },
  a2aj_case_law:      { label: 'HF',  badge: 'badge-hf',  total: '~184,565' },
  canlii_legacy:      { label: 'Web', badge: 'badge-web', total: 'varies' },
};

export default function DataSources({ status, stats, onRefreshStats }) {
  const [sources, setSources] = useState([]);
  const [adapters, setAdapters] = useState([]);
  const [loading, setLoading] = useState(true);
  const [scrapeLimit, setScrapeLimit] = useState(100);
  const [message, setMessage] = useState(null);

  useEffect(() => {
    Promise.all([api.getSources(), api.getAvailableAdapters()])
      .then(([srcRes, adpRes]) => {
        setSources(srcRes.sources || []);
        setAdapters(adpRes.adapters || []);
      })
      .catch(e => console.error(e))
      .finally(() => setLoading(false));
  }, []);

  const isRunning = status?.is_running || false;
  const bySource = stats?.by_source || {};

  const toggleSource = async (idx) => {
    const updated = [...sources];
    updated[idx] = { ...updated[idx], enabled: !updated[idx].enabled };
    setSources(updated);
    try { await api.updateSources(updated); } catch (e) { console.error(e); }
  };

  const handleRun = async (sourceType) => {
    setMessage(null);
    try {
      await api.startMultiSource({ source_type: sourceType, scrape_limit: parseInt(scrapeLimit) || 100 });
      setMessage({ type: 'success', text: `Started ${sourceType}` });
    } catch (e) {
      setMessage({ type: 'error', text: e.message });
    }
  };

  const handleRunAll = async () => {
    setMessage(null);
    try {
      const enabledTypes = sources.filter(s => s.enabled).map(s => s.source_type);
      await api.startMultiSource({ source_types: enabledTypes, scrape_limit: parseInt(scrapeLimit) || 100 });
      setMessage({ type: 'success', text: `Started ${enabledTypes.length} sources` });
    } catch (e) {
      setMessage({ type: 'error', text: e.message });
    }
  };

  const handleStop = async () => {
    try { await api.stopScraper(); } catch (e) { console.error(e); }
  };

  if (loading) return <div style={{ padding: 20, color: 'var(--text-muted)' }}>Loading...</div>;

  const enabledCount = sources.filter(s => s.enabled).length;

  return (
    <div>
      <div className="page-header">
        <h2>Data Sources</h2>
        <p>Configure and run multi-source data ingestion</p>
      </div>

      {/* Controls bar */}
      <div className="card" style={{ marginBottom: 20 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <label style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Limit</label>
            <input
              className="input input-sm"
              type="number"
              value={scrapeLimit}
              onChange={e => setScrapeLimit(e.target.value)}
              disabled={isRunning}
            />
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            {isRunning ? (
              <button className="btn btn-danger" onClick={handleStop}>Stop</button>
            ) : (
              <button className="btn btn-primary" onClick={handleRunAll} disabled={enabledCount === 0}>
                Run All ({enabledCount})
              </button>
            )}
          </div>
        </div>
      </div>

      {message && (
        <div className={`alert ${message.type === 'success' ? 'alert-success' : 'alert-error'}`}>
          {message.text}
        </div>
      )}

      {/* Source Cards */}
      <div className="source-grid">
        {sources.map((src, idx) => {
          const meta = SOURCE_META[src.source_type] || { label: '?', badge: '', total: '?' };
          const docCount = bySource[src.source_type] || 0;
          const isActive = isRunning && status?.current_source === src.name;

          return (
            <div
              key={src.source_type}
              className={`source-card ${!src.enabled ? 'disabled' : ''} ${isActive ? 'active-source' : ''}`}
            >
              {/* Header */}
              <div className="source-card-header">
                <div>
                  <div className="source-name">{src.name}</div>
                  <div className="source-meta">
                    <span>{JUR_NAMES[src.jurisdiction] || src.jurisdiction}</span>
                    <span>{src.category}</span>
                  </div>
                </div>
                <span className={`badge ${meta.badge}`}>{meta.label}</span>
              </div>

              {/* Stats */}
              <div className="source-stats">
                <div className="source-stat">
                  <div className="source-stat-value" style={{ color: 'var(--accent)' }}>
                    {docCount.toLocaleString()}
                  </div>
                  <div className="source-stat-label">In DB</div>
                </div>
                <div className="source-stat">
                  <div className="source-stat-value" style={{ color: 'var(--text-secondary)' }}>
                    {meta.total}
                  </div>
                  <div className="source-stat-label">Available</div>
                </div>
                <div className="source-stat">
                  <div className="source-stat-value" style={{ color: 'var(--success)' }}>
                    {src.enabled ? 'ON' : 'OFF'}
                  </div>
                  <div className="source-stat-label">Status</div>
                </div>
              </div>

              {/* Progress (if active) */}
              {isActive && (
                <div className="source-progress" style={{ marginBottom: 14 }}>
                  <div
                    className="source-progress-bar"
                    style={{
                      width: status.scrape_limit
                        ? `${Math.min(100, ((status.stats.success + status.stats.failed) / status.scrape_limit) * 100)}%`
                        : '50%',
                      background: 'var(--success)',
                    }}
                  />
                </div>
              )}

              {/* Actions */}
              <div className="source-actions">
                <label className="toggle">
                  <input
                    type="checkbox"
                    checked={src.enabled}
                    onChange={() => toggleSource(idx)}
                  />
                  <span className="toggle-track" />
                  <span className="toggle-thumb" />
                </label>
                <button
                  className="btn btn-sm btn-ghost"
                  onClick={() => handleRun(src.source_type)}
                  disabled={isRunning || !src.enabled}
                >
                  {isActive ? 'Running...' : 'Run'}
                </button>
              </div>
            </div>
          );
        })}

        {/* Unconfigured adapters */}
        {adapters
          .filter(a => !sources.some(s => s.source_type === a.source_type))
          .map(a => {
            const meta = SOURCE_META[a.source_type] || { label: '?', badge: '', total: '?' };
            return (
              <div key={a.source_type} className="source-card disabled" style={{ opacity: 0.35 }}>
                <div className="source-card-header">
                  <div>
                    <div className="source-name">{a.source_type}</div>
                    <div className="source-meta"><span>{a.class}</span></div>
                  </div>
                  <span className={`badge ${meta.badge}`}>{meta.label}</span>
                </div>
                <div style={{ fontSize: 12, color: 'var(--text-muted)', padding: '12px 0' }}>
                  Not configured. Add to <code style={{ color: 'var(--accent)' }}>config.json</code> to enable.
                </div>
              </div>
            );
          })}
      </div>
    </div>
  );
}
