import React, { useState, useEffect } from 'react';
import { api } from '../api';

export default function Settings() {
  const [sources, setSources] = useState([]);
  const [adapters, setAdapters] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    Promise.all([api.getSources(), api.getAvailableAdapters()])
      .then(([srcRes, adpRes]) => {
        setSources(srcRes.sources || []);
        setAdapters(adpRes.adapters || []);
      })
      .catch(e => console.error(e))
      .finally(() => setLoading(false));
  }, []);

  const updateField = (idx, field, value) => {
    const updated = [...sources];
    updated[idx] = { ...updated[idx], [field]: value };
    setSources(updated);
  };

  const handleSave = async () => {
    try {
      await api.updateSources(sources);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (e) {
      console.error(e);
    }
  };

  if (loading) return <div style={{ padding: 20, color: 'var(--text-muted)' }}>Loading...</div>;

  return (
    <div>
      <div className="page-header">
        <h2>Settings</h2>
        <p>Configure data sources and platform parameters</p>
      </div>

      {saved && <div className="alert alert-success">Settings saved</div>}

      {/* Source Configuration */}
      <div className="card">
        <div className="card-header">
          <div className="card-title">Source Configuration</div>
          <button className="btn btn-primary btn-sm" onClick={handleSave}>Save Changes</button>
        </div>

        {sources.map((src, idx) => (
          <div key={src.source_type} style={{
            padding: '16px 0',
            borderBottom: idx < sources.length - 1 ? '1px solid var(--border)' : 'none',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
              <div style={{ fontWeight: 600, fontSize: 14 }}>{src.name}</div>
              <span style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'monospace' }}>
                {src.source_type}
              </span>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12 }}>
              <div>
                <label style={{ fontSize: 11, color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>
                  Jurisdiction
                </label>
                <input
                  className="input"
                  value={src.jurisdiction}
                  onChange={e => updateField(idx, 'jurisdiction', e.target.value)}
                  style={{ width: '100%' }}
                />
              </div>
              <div>
                <label style={{ fontSize: 11, color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>
                  Category
                </label>
                <input
                  className="input"
                  value={src.category}
                  onChange={e => updateField(idx, 'category', e.target.value)}
                  style={{ width: '100%' }}
                />
              </div>
              <div>
                <label style={{ fontSize: 11, color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>
                  Enabled
                </label>
                <label className="toggle" style={{ marginTop: 6 }}>
                  <input
                    type="checkbox"
                    checked={src.enabled}
                    onChange={() => updateField(idx, 'enabled', !src.enabled)}
                  />
                  <span className="toggle-track" />
                  <span className="toggle-thumb" />
                </label>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* System Info */}
      <div className="card">
        <div className="card-title" style={{ marginBottom: 12 }}>System Information</div>
        <div className="settings-row">
          <div className="settings-label">Platform Version</div>
          <div style={{ fontWeight: 600 }}>v5.0</div>
        </div>
        <div className="settings-row">
          <div className="settings-label">Registered Adapters</div>
          <div style={{ fontWeight: 600 }}>{adapters.length}</div>
        </div>
        <div className="settings-row">
          <div className="settings-label">Active Sources</div>
          <div style={{ fontWeight: 600 }}>{sources.filter(s => s.enabled).length} / {sources.length}</div>
        </div>
        <div className="settings-row">
          <div className="settings-label">Backend API</div>
          <div style={{ fontWeight: 600, fontFamily: 'monospace', fontSize: 12 }}>http://localhost:8000</div>
        </div>
      </div>

      {/* Adapter Registry */}
      <div className="card">
        <div className="card-title" style={{ marginBottom: 12 }}>Adapter Registry</div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Source Type</th>
                <th>Class</th>
                <th>Configured</th>
              </tr>
            </thead>
            <tbody>
              {adapters.map(a => {
                const configured = sources.some(s => s.source_type === a.source_type);
                return (
                  <tr key={a.source_type}>
                    <td style={{ fontFamily: 'monospace', fontSize: 12 }}>{a.source_type}</td>
                    <td style={{ fontSize: 12 }}>{a.class}</td>
                    <td>
                      {configured
                        ? <span style={{ color: 'var(--success)', fontWeight: 600 }}>Yes</span>
                        : <span style={{ color: 'var(--text-muted)' }}>No</span>
                      }
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
