import React, { useState, useEffect } from 'react';
import { api } from '../api';

/* ── Helper: format diagnostics JSON into a readable plain-text report ── */
function formatDiagReport(d) {
  const lines = [];
  const hr = '─'.repeat(60);
  lines.push(`Canadian Legal Data Platform — Database Diagnostic Report`);
  lines.push(`Generated: ${d.generated_at}`);
  lines.push(`Database Size: ${d.db_size}`);
  lines.push(`Checkpoint File: ${d.checkpoint_size}`);
  lines.push(hr);

  // Table sizes
  lines.push('');
  lines.push('TABLE SIZES');
  lines.push(pad('Table', 22) + pad('Rows', 10) + pad('Data', 12) + pad('Index', 12) + 'Total');
  lines.push('─'.repeat(68));
  for (const t of d.tables || []) {
    lines.push(
      pad(t.table_name, 22) +
      pad(String(t.row_count), 10) +
      pad(t.data_size, 12) +
      pad(t.index_size, 12) +
      t.total_size
    );
  }

  // Content storage
  const cs = d.content_stats || {};
  lines.push('');
  lines.push(hr);
  lines.push('CONTENT STORAGE');
  lines.push(`  Total versions: ${cs.total_versions ?? 0}  (latest: ${cs.latest_versions ?? 0})`);
  lines.push(`  With text: ${cs.with_text ?? 0}  |  With HTML: ${cs.with_html ?? 0}  |  Empty shells: ${cs.empty_shells ?? 0}`);
  lines.push(`  Text size: ${cs.total_text_size ?? '0 bytes'}  |  HTML size: ${cs.total_html_size ?? '0 bytes'}`);
  lines.push(`  Documents without any version: ${d.docs_without_versions ?? 0}`);

  // By source
  lines.push('');
  lines.push(hr);
  lines.push('DOCUMENTS BY SOURCE');
  for (const s of d.docs_by_source || []) {
    lines.push(`  ${pad(s.source_type, 28)} ${s.count}`);
  }

  // By jurisdiction
  lines.push('');
  lines.push(hr);
  lines.push('DOCUMENTS BY JURISDICTION');
  for (const j of d.docs_by_jurisdiction || []) {
    lines.push(`  ${pad(j.name || j.jurisdiction_code, 28)} ${j.count}`);
  }

  // By type
  lines.push('');
  lines.push(hr);
  lines.push('DOCUMENTS BY TYPE');
  for (const t of d.docs_by_type || []) {
    lines.push(`  ${pad(t.document_type, 28)} ${t.count}`);
  }

  // Recent jobs
  lines.push('');
  lines.push(hr);
  lines.push('RECENT JOBS (last 10)');
  for (const j of d.recent_jobs || []) {
    const dur = j.duration_secs != null ? `${j.duration_secs}s` : '—';
    const ts = j.started_at ? j.started_at.replace('T', ' ').slice(0, 19) : '—';
    lines.push(`  ${ts}  ${pad(j.status, 10)}  scraped:${j.items_scraped} failed:${j.items_failed}  (${dur})`);
  }

  // Indexes
  lines.push('');
  lines.push(hr);
  lines.push('INDEXES');
  for (const idx of d.indexes || []) {
    lines.push(`  ${pad(idx.indexname, 44)} ${pad(idx.tablename, 22)} ${idx.size}`);
  }

  lines.push('');
  lines.push(hr);
  return lines.join('\n');
}

function pad(s, n) {
  s = String(s || '');
  return s.length >= n ? s : s + ' '.repeat(n - s.length);
}

export default function Settings() {
  const [sources, setSources] = useState([]);
  const [adapters, setAdapters] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saved, setSaved] = useState(false);

  // Scheduler state
  const [sched, setSched] = useState(null);
  const [schedSaved, setSchedSaved] = useState(false);
  const [schedTriggering, setSchedTriggering] = useState(false);
  const [platformVersion, setPlatformVersion] = useState(null);

  // Database diagnostics state
  const [diagReport, setDiagReport] = useState(null);
  const [diagLoading, setDiagLoading] = useState(false);
  const [diagError, setDiagError] = useState(null);
  const [diagCopied, setDiagCopied] = useState(false);

  useEffect(() => {
    Promise.all([api.getSources(), api.getAvailableAdapters(), api.getSchedulerConfig(), api.getHealth()])
      .then(([srcRes, adpRes, schedRes, healthRes]) => {
        setSources(srcRes.sources || []);
        setAdapters(adpRes.adapters || []);
        setSched(schedRes || {});
        if (healthRes?.version) setPlatformVersion(healthRes.version);
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

  // --- Scheduler helpers ---
  const updateSched = (field, value) => {
    setSched(prev => ({ ...prev, [field]: value }));
  };

  const handleSchedSave = async () => {
    try {
      const payload = {
        enabled: sched.enabled,
        schedule_type: sched.schedule_type,
        daily_time: sched.daily_time,
        interval_hours: sched.interval_hours,
        scrape_limit: sched.scrape_limit,
        distribution_mode: sched.distribution_mode,
        supabase_keepalive: sched.supabase_keepalive,
        supabase_keepalive_interval_hours: sched.supabase_keepalive_interval_hours,
      };
      // Remove null/undefined so we don't overwrite with nulls
      Object.keys(payload).forEach(k => payload[k] == null && delete payload[k]);
      const res = await api.updateSchedulerConfig(payload);
      setSched(res.config || sched);
      setSchedSaved(true);
      setTimeout(() => setSchedSaved(false), 2000);
    } catch (e) {
      console.error(e);
    }
  };

  const handleRunNow = async () => {
    setSchedTriggering(true);
    try {
      await api.triggerScheduledRun();
    } catch (e) {
      console.error(e);
    } finally {
      setTimeout(() => setSchedTriggering(false), 2000);
    }
  };

  const formatTime = (iso) => {
    if (!iso) return '—';
    try {
      return new Date(iso).toLocaleString();
    } catch {
      return iso;
    }
  };

  // --- Database Diagnostics helpers ---
  const runDiagnostics = async () => {
    setDiagLoading(true);
    setDiagError(null);
    setDiagReport(null);
    setDiagCopied(false);
    try {
      const data = await api.getDbDiagnostics();
      setDiagReport(formatDiagReport(data));
    } catch (e) {
      setDiagError(e.message || 'Failed to run diagnostics');
    } finally {
      setDiagLoading(false);
    }
  };

  const copyDiagReport = () => {
    if (!diagReport) return;
    navigator.clipboard.writeText(diagReport).then(() => {
      setDiagCopied(true);
      setTimeout(() => setDiagCopied(false), 2000);
    });
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

            <div className="settings-grid-3" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12 }}>
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

      {/* ── Scheduler ── */}
      {sched && (
        <div className="card">
          <div className="card-header">
            <div className="card-title">Scheduler</div>
            <div style={{ display: 'flex', gap: 8 }}>
              <button
                className="btn btn-sm"
                style={{ background: 'var(--accent)', color: '#fff' }}
                onClick={handleRunNow}
                disabled={schedTriggering}
              >
                {schedTriggering ? 'Triggered!' : 'Run Now'}
              </button>
              <button className="btn btn-primary btn-sm" onClick={handleSchedSave}>
                {schedSaved ? 'Saved!' : 'Save'}
              </button>
            </div>
          </div>

          {/* Enable toggle */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '12px 0', borderBottom: '1px solid var(--border)' }}>
            <label className="toggle">
              <input
                type="checkbox"
                checked={sched.enabled || false}
                onChange={() => updateSched('enabled', !sched.enabled)}
              />
              <span className="toggle-track" />
              <span className="toggle-thumb" />
            </label>
            <span style={{ fontWeight: 600, fontSize: 14 }}>
              {sched.enabled ? 'Scheduler Enabled' : 'Scheduler Disabled'}
            </span>
          </div>

          {/* Schedule type */}
          <div style={{ padding: '12px 0', borderBottom: '1px solid var(--border)' }}>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 8 }}>Schedule Type</div>
            <div style={{ display: 'flex', gap: 16, alignItems: 'center', flexWrap: 'wrap' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
                <input
                  type="radio"
                  name="schedule_type"
                  checked={sched.schedule_type === 'daily'}
                  onChange={() => updateSched('schedule_type', 'daily')}
                />
                <span>Daily at</span>
                <input
                  className="input"
                  type="time"
                  value={sched.daily_time || '02:00'}
                  onChange={e => updateSched('daily_time', e.target.value)}
                  style={{ width: 100, fontSize: 12 }}
                  disabled={sched.schedule_type !== 'daily'}
                />
                <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>UTC</span>
              </label>

              <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
                <input
                  type="radio"
                  name="schedule_type"
                  checked={sched.schedule_type === 'interval'}
                  onChange={() => updateSched('schedule_type', 'interval')}
                />
                <span>Every</span>
                <input
                  className="input"
                  type="number"
                  min={1}
                  max={168}
                  value={sched.interval_hours || 24}
                  onChange={e => updateSched('interval_hours', parseInt(e.target.value) || 24)}
                  style={{ width: 60, fontSize: 12 }}
                  disabled={sched.schedule_type !== 'interval'}
                />
                <span>hours</span>
              </label>
            </div>
          </div>

          {/* Scrape settings */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, padding: '12px 0', borderBottom: '1px solid var(--border)' }}>
            <div>
              <label style={{ fontSize: 11, color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>
                Scrape Limit
              </label>
              <input
                className="input"
                type="number"
                min={10}
                max={50000}
                value={sched.scrape_limit || 500}
                onChange={e => updateSched('scrape_limit', parseInt(e.target.value) || 500)}
                style={{ width: '100%' }}
              />
            </div>
            <div>
              <label style={{ fontSize: 11, color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>
                Distribution Mode
              </label>
              <select
                className="input"
                value={sched.distribution_mode || 'proportional'}
                onChange={e => updateSched('distribution_mode', e.target.value)}
                style={{ width: '100%' }}
              >
                <option value="proportional">Proportional</option>
                <option value="equal">Equal</option>
                <option value="sequential">Sequential</option>
              </select>
            </div>
          </div>

          {/* Status display */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, padding: '12px 0', borderBottom: sched.has_supabase ? '1px solid var(--border)' : 'none' }}>
            <div>
              <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>Last Run</div>
              <div style={{ fontWeight: 600, fontSize: 13 }}>{formatTime(sched.last_run_at)}</div>
            </div>
            <div>
              <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>Next Run</div>
              <div style={{ fontWeight: 600, fontSize: 13 }}>{formatTime(sched.next_run_at)}</div>
            </div>
          </div>

          {/* Supabase Keepalive (only shown if SUPABASE_URL is set) */}
          {sched.has_supabase && (
            <div style={{ padding: '12px 0' }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', marginBottom: 8 }}>
                Supabase Keepalive
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
                <label className="toggle">
                  <input
                    type="checkbox"
                    checked={sched.supabase_keepalive || false}
                    onChange={() => updateSched('supabase_keepalive', !sched.supabase_keepalive)}
                  />
                  <span className="toggle-track" />
                  <span className="toggle-thumb" />
                </label>
                <span style={{ fontSize: 13 }}>Ping every</span>
                <input
                  className="input"
                  type="number"
                  min={1}
                  max={168}
                  value={sched.supabase_keepalive_interval_hours || 24}
                  onChange={e => updateSched('supabase_keepalive_interval_hours', parseInt(e.target.value) || 24)}
                  style={{ width: 60, fontSize: 12 }}
                  disabled={!sched.supabase_keepalive}
                />
                <span style={{ fontSize: 13 }}>hours</span>
                {sched.last_keepalive_at && (
                  <span style={{ fontSize: 11, color: 'var(--text-muted)', marginLeft: 8 }}>
                    Last: {formatTime(sched.last_keepalive_at)}
                  </span>
                )}
              </div>
            </div>
          )}
        </div>
      )}

      {/* System Info */}
      <div className="card">
        <div className="card-title" style={{ marginBottom: 12 }}>System Information</div>
        <div className="settings-row">
          <div className="settings-label">Platform Version</div>
          <div style={{ fontWeight: 600 }}>{platformVersion ? `v${platformVersion}` : '—'}</div>
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

      {/* ── Database Diagnostics ── */}
      <div className="card">
        <div className="card-header">
          <div className="card-title">Database Diagnostics</div>
          <div style={{ display: 'flex', gap: 8 }}>
            {diagReport && (
              <button className="btn btn-ghost btn-sm" onClick={copyDiagReport}>
                {diagCopied ? 'Copied!' : 'Copy Report'}
              </button>
            )}
            <button
              className="btn btn-sm"
              style={{ background: 'var(--info)', color: '#fff' }}
              onClick={runDiagnostics}
              disabled={diagLoading}
            >
              {diagLoading ? 'Running...' : 'Run Diagnostic'}
            </button>
          </div>
        </div>

        <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 12 }}>
          Run a full database health check. The report can be copied and shared with developers for debugging.
        </div>

        {diagError && (
          <div className="alert alert-error" style={{ marginBottom: 12 }}>{diagError}</div>
        )}

        {diagReport && (
          <pre style={{
            background: 'var(--bg-input)',
            padding: 16,
            borderRadius: 'var(--radius)',
            fontSize: 11,
            fontFamily: "'SF Mono', 'Fira Code', 'Consolas', monospace",
            whiteSpace: 'pre',
            overflowX: 'auto',
            maxHeight: 500,
            overflowY: 'auto',
            color: 'var(--text-secondary)',
            lineHeight: 1.5,
            border: '1px solid var(--border)',
          }}>
            {diagReport}
          </pre>
        )}

        {!diagReport && !diagError && !diagLoading && (
          <div style={{ textAlign: 'center', padding: '24px 0', color: 'var(--text-muted)', fontSize: 12 }}>
            Click "Run Diagnostic" to generate a database health report
          </div>
        )}
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
