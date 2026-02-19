import React from 'react';

const JUR_NAMES = {
  ca: 'Federal', bc: 'British Columbia', ab: 'Alberta', on: 'Ontario',
  qc: 'Quebec', ns: 'Nova Scotia', nb: 'New Brunswick', mb: 'Manitoba',
  pe: 'PEI', sk: 'Saskatchewan', nl: 'Newfoundland', yt: 'Yukon',
  nt: 'NWT', nu: 'Nunavut',
};

const JUR_COLORS = {
  ca: '#4f6ef7', bc: '#34d399', ab: '#fbbf24', on: '#f87171',
  qc: '#a78bfa', ns: '#fb923c', nb: '#60a5fa', mb: '#f472b6',
};

const SOURCE_META = {
  justice_canada_xml:    { label: 'XML',  badge: 'badge-xml', name: 'Federal Legislation' },
  bc_laws_api:           { label: 'API',  badge: 'badge-api', name: 'BC Laws' },
  alberta_kings_printer: { label: 'GOV',  badge: 'badge-gov', name: 'Alberta Legislation' },
  a2aj_case_law:         { label: 'HF',   badge: 'badge-hf',  name: 'A2AJ Case Law' },
  canlii_legacy:         { label: 'Web',  badge: 'badge-web', name: 'CanLII Legacy' },
  manitoba_laws:         { label: 'GOV',  badge: 'badge-gov', name: 'Manitoba Laws' },
  newfoundland_laws:     { label: 'GOV',  badge: 'badge-gov', name: 'NL Laws' },
  nova_scotia_laws:      { label: 'GOV',  badge: 'badge-gov', name: 'NS Laws' },
  new_brunswick_laws:    { label: 'GOV',  badge: 'badge-gov', name: 'NB Laws' },
  ontario_elaws:         { label: 'GOV',  badge: 'badge-gov', name: 'Ontario e-Laws' },
};

export default function Dashboard({ status, stats }) {
  if (!stats) return <div style={{ padding: 20, color: 'var(--text-muted)' }}>Loading dashboard...</div>;

  const bySource = stats.by_source || {};
  const byJur = stats.by_jurisdiction || {};
  const byType = stats.by_type || {};
  const total = stats.total_documents || 0;
  const maxJur = Math.max(...Object.values(byJur).map(j => j.count), 1);
  const isRunning = status?.is_running || false;

  return (
    <div>
      <div className="page-header">
        <h2>Dashboard</h2>
        <p>Overview of all ingested Canadian legal data</p>
      </div>

      {/* Live run banner */}
      {isRunning && (
        <div className="alert alert-info">
          <span className="status-dot running" />
          Scraping: <strong>{status.current_source || 'starting...'}</strong>
          &nbsp;&mdash;&nbsp;
          {status.stats.success} success, {status.stats.failed} failed, {status.stats.skipped} skipped
          {status.scrape_limit > 0 && <span> / limit {status.scrape_limit}</span>}
        </div>
      )}

      {/* Top Stats */}
      <div className="stat-grid">
        <div className="stat-card">
          <div className="stat-value" style={{ color: 'var(--accent)' }}>{total.toLocaleString()}</div>
          <div className="stat-label">Total Documents</div>
        </div>
        <div className="stat-card">
          <div className="stat-value" style={{ color: 'var(--info)' }}>{(byType.legislation || 0).toLocaleString()}</div>
          <div className="stat-label">Legislation</div>
        </div>
        <div className="stat-card">
          <div className="stat-value" style={{ color: 'var(--orange)' }}>{(byType.regulation || 0).toLocaleString()}</div>
          <div className="stat-label">Regulations</div>
        </div>
        <div className="stat-card">
          <div className="stat-value" style={{ color: 'var(--purple)' }}>{(byType.case_law || 0).toLocaleString()}</div>
          <div className="stat-label">Case Law</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{Object.keys(byJur).length}</div>
          <div className="stat-label">Jurisdictions</div>
        </div>
      </div>

      <div className="dashboard-two-col" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        {/* Sources breakdown */}
        <div className="card">
          <div className="card-title" style={{ marginBottom: 16 }}>Documents by Source</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            {Object.entries(bySource)
              .sort((a, b) => b[1] - a[1])
              .map(([key, count]) => {
                const meta = SOURCE_META[key] || { label: '?', badge: '', name: key };
                const pct = total > 0 ? (count / total * 100) : 0;
                return (
                  <div key={key}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <span className={`badge ${meta.badge}`}>{meta.label}</span>
                        <span style={{ fontSize: 13, fontWeight: 500 }}>{meta.name}</span>
                      </div>
                      <span style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-primary)' }}>
                        {count.toLocaleString()}
                      </span>
                    </div>
                    <div className="source-progress">
                      <div className="source-progress-bar" style={{ width: `${pct}%` }} />
                    </div>
                    {stats.last_updated_by_source?.[key] && (
                      <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 2 }}>
                        Last updated: {new Date(stats.last_updated_by_source[key]).toLocaleString('en-CA', {
                          month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
                        })}
                      </div>
                    )}
                  </div>
                );
              })}
          </div>
        </div>

        {/* Jurisdiction breakdown */}
        <div className="card">
          <div className="card-title" style={{ marginBottom: 16 }}>Documents by Jurisdiction</div>
          <div className="jur-bar-wrap">
            {Object.entries(byJur)
              .sort((a, b) => b[1].count - a[1].count)
              .map(([code, data]) => (
                <div className="jur-bar-row" key={code}>
                  <div className="jur-bar-label">{JUR_NAMES[code] || data.name || code}</div>
                  <div className="jur-bar-track">
                    <div
                      className="jur-bar-fill"
                      style={{
                        width: `${(data.count / maxJur) * 100}%`,
                        background: JUR_COLORS[code] || 'var(--accent)',
                      }}
                    />
                  </div>
                  <div className="jur-bar-count">{data.count.toLocaleString()}</div>
                </div>
              ))}
          </div>
        </div>
      </div>

      {/* Live progress panel */}
      {isRunning && status && (
        <div className="card" style={{ marginTop: 16 }}>
          <div className="card-title" style={{ marginBottom: 16 }}>Live Progress</div>
          <div className="stat-grid">
            <div className="stat-card">
              <div className="stat-value" style={{ color: 'var(--success)' }}>{status.stats.success}</div>
              <div className="stat-label">Success</div>
            </div>
            <div className="stat-card">
              <div className="stat-value" style={{ color: 'var(--error)' }}>{status.stats.failed}</div>
              <div className="stat-label">Failed</div>
            </div>
            <div className="stat-card">
              <div className="stat-value" style={{ color: 'var(--text-muted)' }}>{status.stats.skipped}</div>
              <div className="stat-label">Skipped</div>
            </div>
            <div className="stat-card">
              <div className="stat-value">
                {status.scrape_limit ? Math.max(0, status.scrape_limit - status.stats.success - status.stats.failed) : '--'}
              </div>
              <div className="stat-label">Remaining</div>
            </div>
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-muted)', fontStyle: 'italic', marginTop: 4 }}>
            {status.message}
          </div>
        </div>
      )}
    </div>
  );
}
