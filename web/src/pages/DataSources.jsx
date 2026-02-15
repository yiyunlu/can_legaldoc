import React, { useState, useEffect } from 'react';
import { api } from '../api';

const JURISDICTION_NAMES = {
  ca: 'Federal', bc: 'British Columbia', ab: 'Alberta', on: 'Ontario',
  qc: 'Quebec', ns: 'Nova Scotia', nb: 'New Brunswick', mb: 'Manitoba',
  pe: 'PEI', sk: 'Saskatchewan', nl: 'Newfoundland', yt: 'Yukon',
  nt: 'NWT', nu: 'Nunavut', multi: 'All Jurisdictions'
};

const SOURCE_ICONS = {
  justice_canada_xml: { label: 'XML', color: '#3498db' },
  bc_laws_api: { label: 'API', color: '#2ecc71' },
  a2aj_case_law: { label: 'HF', color: '#9b59b6' },
  canlii_legacy: { label: 'Web', color: '#e67e22' },
};

export default function DataSources({ status, onStartScraper }) {
  const [sources, setSources] = useState([]);
  const [adapters, setAdapters] = useState([]);
  const [loading, setLoading] = useState(true);
  const [runningSource, setRunningSource] = useState(null);
  const [scrapeLimit, setScrapeLimit] = useState(100);
  const [message, setMessage] = useState(null);

  const fetchData = async () => {
    try {
      const [srcRes, adapterRes] = await Promise.all([
        api.getSources(),
        api.getAvailableAdapters()
      ]);
      setSources(srcRes.sources || []);
      setAdapters(adapterRes.adapters || []);
    } catch (e) {
      console.error('Failed to load sources:', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchData(); }, []);

  const toggleSource = async (idx) => {
    const updated = [...sources];
    updated[idx] = { ...updated[idx], enabled: !updated[idx].enabled };
    setSources(updated);
    try {
      await api.updateSources(updated);
    } catch (e) {
      console.error('Failed to update sources:', e);
    }
  };

  const handleRun = async (sourceType) => {
    setRunningSource(sourceType);
    setMessage(null);
    try {
      await api.startMultiSource({
        source_type: sourceType,
        scrape_limit: parseInt(scrapeLimit) || 100
      });
      setMessage({ type: 'success', text: `Started ${sourceType}` });
    } catch (e) {
      setMessage({ type: 'error', text: e.message });
    } finally {
      setRunningSource(null);
    }
  };

  const handleRunAll = async () => {
    setRunningSource('__all__');
    setMessage(null);
    try {
      const enabledTypes = sources.filter(s => s.enabled).map(s => s.source_type);
      await api.startMultiSource({
        source_types: enabledTypes,
        scrape_limit: parseInt(scrapeLimit) || 100
      });
      setMessage({ type: 'success', text: `Started ${enabledTypes.length} sources` });
    } catch (e) {
      setMessage({ type: 'error', text: e.message });
    } finally {
      setRunningSource(null);
    }
  };

  if (loading) return <div style={{ padding: '20px' }}>Loading sources...</div>;

  const enabledCount = sources.filter(s => s.enabled).length;

  return (
    <div style={{ padding: '20px' }}>
      {/* Header */}
      <div className="card" style={{ marginBottom: '20px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '15px' }}>
          <h2 style={{ margin: 0 }}>Data Sources</h2>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
              Limit:
              <input
                type="number"
                value={scrapeLimit}
                onChange={(e) => setScrapeLimit(e.target.value)}
                style={{
                  width: '70px', marginLeft: '6px', padding: '4px 8px',
                  borderRadius: '4px', border: '1px solid var(--border-color)',
                  background: 'var(--bg-primary)', color: 'var(--text-primary)',
                  fontSize: '12px'
                }}
              />
            </div>
            <button
              className="primary"
              onClick={handleRunAll}
              disabled={status?.is_running || enabledCount === 0}
              style={{ fontSize: '13px' }}
            >
              {runningSource === '__all__' ? 'Starting...' : `Run All (${enabledCount})`}
            </button>
          </div>
        </div>

        {message && (
          <div style={{
            padding: '8px 12px', borderRadius: '6px', fontSize: '13px', marginBottom: '10px',
            background: message.type === 'success' ? 'rgba(46,204,113,0.1)' : 'rgba(231,76,60,0.1)',
            color: message.type === 'success' ? '#27ae60' : '#e74c3c',
            border: `1px solid ${message.type === 'success' ? 'rgba(46,204,113,0.3)' : 'rgba(231,76,60,0.3)'}`
          }}>
            {message.text}
          </div>
        )}

        {/* Sources Table */}
        <table className="dense-table" style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr>
              <th style={{ width: '40px', textAlign: 'center' }}>On</th>
              <th>Source</th>
              <th>Type</th>
              <th>Jurisdiction</th>
              <th>Category</th>
              <th style={{ width: '100px', textAlign: 'center' }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {sources.map((src, idx) => {
              const icon = SOURCE_ICONS[src.source_type] || { label: '?', color: '#999' };
              return (
                <tr key={src.source_type}>
                  <td style={{ textAlign: 'center' }}>
                    <input
                      type="checkbox"
                      checked={src.enabled}
                      onChange={() => toggleSource(idx)}
                    />
                  </td>
                  <td>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <span style={{
                        display: 'inline-block', padding: '2px 6px', borderRadius: '4px',
                        fontSize: '10px', fontWeight: 'bold', color: '#fff',
                        background: icon.color, minWidth: '28px', textAlign: 'center'
                      }}>
                        {icon.label}
                      </span>
                      <span>{src.name}</span>
                    </div>
                  </td>
                  <td style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                    {src.source_type}
                  </td>
                  <td>
                    <span style={{
                      padding: '2px 8px', borderRadius: '10px', fontSize: '11px',
                      background: 'var(--bg-secondary)', border: '1px solid var(--border-color)'
                    }}>
                      {JURISDICTION_NAMES[src.jurisdiction] || src.jurisdiction}
                    </span>
                  </td>
                  <td>{src.category}</td>
                  <td style={{ textAlign: 'center' }}>
                    <button
                      className="text-link"
                      onClick={() => handleRun(src.source_type)}
                      disabled={status?.is_running || !src.enabled}
                      style={{
                        fontSize: '12px', padding: '3px 10px',
                        color: src.enabled ? '#3498db' : 'gray',
                        cursor: src.enabled && !status?.is_running ? 'pointer' : 'not-allowed'
                      }}
                    >
                      {runningSource === src.source_type ? '...' : 'Run'}
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Available Adapters */}
      <div className="card">
        <h2 style={{ marginBottom: '10px' }}>Available Adapters</h2>
        <p style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '15px' }}>
          All registered adapters in the system. Add new ones to <code>config.json</code> to enable them.
        </p>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: '10px' }}>
          {adapters.map(a => {
            const configured = sources.some(s => s.source_type === a.source_type);
            const icon = SOURCE_ICONS[a.source_type] || { label: '?', color: '#999' };
            return (
              <div key={a.source_type} style={{
                padding: '12px', borderRadius: '8px',
                border: `1px solid ${configured ? 'rgba(46,204,113,0.3)' : 'var(--border-color)'}`,
                background: configured ? 'rgba(46,204,113,0.05)' : 'var(--bg-secondary)'
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
                  <span style={{
                    padding: '2px 6px', borderRadius: '4px', fontSize: '10px',
                    fontWeight: 'bold', color: '#fff', background: icon.color
                  }}>
                    {icon.label}
                  </span>
                  <span style={{ fontWeight: 'bold', fontSize: '13px' }}>{a.source_type}</span>
                </div>
                <div style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
                  {a.class}
                </div>
                <div style={{ fontSize: '11px', marginTop: '4px' }}>
                  {configured
                    ? <span style={{ color: '#27ae60' }}>Configured</span>
                    : <span style={{ color: 'gray' }}>Not configured</span>
                  }
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
