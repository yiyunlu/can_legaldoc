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
  pe: '#2dd4bf', sk: '#facc15', nl: '#818cf8', yt: '#c084fc',
  nt: '#22d3ee', nu: '#e879f9',
};

const SOURCE_META = {
  justice_canada_xml:    { label: 'XML',  badge: 'badge-xml', name: 'Federal Legislation', est: 5795, type: 'leg' },
  bc_laws_api:           { label: 'API',  badge: 'badge-api', name: 'BC Laws', est: 882, type: 'leg' },
  alberta_kings_printer: { label: 'GOV',  badge: 'badge-gov', name: 'Alberta Legislation', est: 1415, type: 'leg' },
  a2aj_case_law:         { label: 'A2AJ', badge: 'badge-hf',  name: 'A2AJ Case Law', est: 184565, type: 'case' },
  canlii_legacy:         { label: 'Web',  badge: 'badge-web', name: 'CanLII Legacy', est: 1000, type: 'leg' },
  manitoba_laws:         { label: 'GOV',  badge: 'badge-gov', name: 'Manitoba Laws', est: 1926, type: 'leg' },
  newfoundland_laws:     { label: 'GOV',  badge: 'badge-gov', name: 'NL Laws', est: 2105, type: 'leg' },
  nova_scotia_laws:      { label: 'GOV',  badge: 'badge-gov', name: 'NS Laws', est: 790, type: 'leg' },
  new_brunswick_laws:    { label: 'GOV',  badge: 'badge-gov', name: 'NB Laws', est: 1560, type: 'leg' },
  ontario_elaws:         { label: 'GOV',  badge: 'badge-gov', name: 'Ontario e-Laws', est: 4400, type: 'leg' },
  yukon_laws:            { label: 'GOV',  badge: 'badge-gov', name: 'Yukon Laws', est: 200, type: 'leg' },
  nwt_laws:              { label: 'GOV',  badge: 'badge-gov', name: 'NWT Laws', est: 300, type: 'leg' },
  nunavut_laws:          { label: 'GOV',  badge: 'badge-gov', name: 'Nunavut Laws', est: 250, type: 'leg' },
  saskatchewan_laws:     { label: 'API',  badge: 'badge-api', name: 'Saskatchewan Laws', est: 1160, type: 'leg' },
  pei_laws:              { label: 'GOV',  badge: 'badge-gov', name: 'PEI Laws', est: 850, type: 'leg' },
  quebec_laws:           { label: 'GOV',  badge: 'badge-gov', name: 'Legis Québec', est: 4700, type: 'leg' },
};

const COURT_NAMES = {
  'SCC': 'Supreme Court of Canada',
  'SCC-L': 'SCC Leave Applications',
  'FCA': 'Federal Court of Appeal',
  'FC': 'Federal Court',
  'TCC': 'Tax Court of Canada',
  'CMAC': 'Court Martial Appeal',
  'CHRT': 'Human Rights Tribunal',
  'SST': 'Social Security Tribunal',
  'IRB-RAD': 'Refugee Appeal Division',
  'IRB-RPD': 'Refugee Protection Div.',
  'BCCA': 'BC Court of Appeal',
  'BCSC': 'BC Supreme Court',
  'ONCA': 'Ontario Court of Appeal',
  'ONSC': 'Ontario Superior Court',
  'YKCA': 'Yukon Court of Appeal',
};

const COURT_COLORS = {
  'SCC': '#ef4444', 'FCA': '#f97316', 'FC': '#f59e0b', 'TCC': '#eab308',
  'BCSC': '#22c55e', 'BCCA': '#10b981', 'ONCA': '#06b6d4', 'ONSC': '#0ea5e9',
  'SST': '#8b5cf6', 'IRB-RAD': '#a855f7', 'IRB-RPD': '#c084fc',
  'CHRT': '#ec4899', 'CMAC': '#f43f5e', 'YKCA': '#14b8a6',
};

export default function Dashboard({ status, stats }) {
  if (!stats) return <div style={{ padding: 20, color: 'var(--text-muted)' }}>Loading dashboard...</div>;

  const bySource = stats.by_source || {};
  const byJur = stats.by_jurisdiction || {};
  const byType = stats.by_type || {};
  const byCourt = stats.by_court || {};
  const total = stats.total_documents || 0;
  const maxJur = Math.max(...Object.values(byJur).map(j => j.count), 1);
  const isRunning = status?.is_running || false;

  const caseLawTotal = byType.case_law || 0;
  const legislationTotal = (byType.legislation || 0) + (byType.regulation || 0);
  const maxCourt = Math.max(...Object.values(byCourt), 1);

  // Coverage calculations
  const estLegislation = Object.entries(SOURCE_META)
    .filter(([k, m]) => m.type === 'leg' && k !== 'canlii_legacy')
    .reduce((s, [, m]) => s + (m.est || 0), 0);
  const legCoveragePct = estLegislation > 0 ? ((legislationTotal / estLegislation) * 100) : 0;
  const legCoverageDisplay = legCoveragePct >= 1 ? `${Math.round(legCoveragePct)}%` : legCoveragePct > 0 ? '< 1%' : '0%';

  const caseCoveragePct = 184565 > 0 ? ((caseLawTotal / 184565) * 100) : 0;
  const caseCoverageDisplay = caseCoveragePct >= 1 ? `${Math.round(caseCoveragePct)}%` : caseCoveragePct > 0 ? '< 1%' : '0%';

  return (
    <div>
      <div className="page-header">
        <h2>Dashboard</h2>
        <p>Canadian legislation, regulations, and court decisions</p>
      </div>

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
          <div className="stat-value" style={{ color: '#a855f7' }}>{caseLawTotal.toLocaleString()}</div>
          <div className="stat-label">Case Law</div>
        </div>
        <div className="stat-card">
          <div className="stat-value" style={{ color: legCoveragePct >= 50 ? 'var(--success)' : 'var(--orange)' }}>
            {legCoverageDisplay}
          </div>
          <div className="stat-label">Legislation Coverage</div>
        </div>
        <div className="stat-card">
          <div className="stat-value" style={{ color: caseCoveragePct >= 50 ? 'var(--success)' : '#a855f7' }}>
            {caseCoverageDisplay}
          </div>
          <div className="stat-label">Case Law Coverage</div>
        </div>
      </div>

      {/* Two-section layout: Legislation | Case Law */}
      <div className="dashboard-two-col">

        {/* LEFT: Legislation Sources */}
        <div className="card">
          <div className="card-title" style={{ marginBottom: 16, display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: 14 }}>Legislation Sources</span>
            <span style={{ fontSize: 11, color: 'var(--text-muted)', fontWeight: 400 }}>
              {legislationTotal.toLocaleString()} docs
            </span>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            {Object.entries(bySource)
              .filter(([key]) => (SOURCE_META[key] || {}).type !== 'case')
              .sort((a, b) => b[1] - a[1])
              .map(([key, count]) => {
                const meta = SOURCE_META[key] || { label: '?', badge: '', name: key };
                const pct = legislationTotal > 0 ? (count / legislationTotal * 100) : 0;
                return (
                  <div key={key}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <span className={`badge ${meta.badge}`}>{meta.label}</span>
                        <span style={{ fontSize: 13, fontWeight: 500 }}>{meta.name}</span>
                      </div>
                      <span style={{ fontSize: 14, fontWeight: 700 }}>{count.toLocaleString()}</span>
                    </div>
                    <div className="source-progress">
                      <div className="source-progress-bar" style={{ width: `${Math.min(100, pct)}%` }} />
                    </div>
                  </div>
                );
              })}
          </div>
        </div>

        {/* RIGHT: Case Law by Court */}
        <div className="card">
          <div className="card-title" style={{ marginBottom: 16, display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: 14 }}>Case Law by Court</span>
            <span style={{ fontSize: 11, color: 'var(--text-muted)', fontWeight: 400 }}>
              {caseLawTotal.toLocaleString()} decisions
            </span>
          </div>
          {Object.keys(byCourt).length > 0 ? (
            <div className="jur-bar-wrap">
              {Object.entries(byCourt)
                .sort((a, b) => b[1] - a[1])
                .map(([court, count]) => (
                  <div className="jur-bar-row" key={court}>
                    <div className="jur-bar-label court-label">
                      {COURT_NAMES[court] || court}
                    </div>
                    <div className="jur-bar-track">
                      <div
                        className="jur-bar-fill"
                        style={{
                          width: `${(count / maxCourt) * 100}%`,
                          background: COURT_COLORS[court] || '#a855f7',
                        }}
                      />
                    </div>
                    <div className="jur-bar-count">{count.toLocaleString()}</div>
                  </div>
                ))}
            </div>
          ) : (
            <div style={{ color: 'var(--text-muted)', fontSize: 13, padding: '20px 0', textAlign: 'center' }}>
              No case law data yet. Run A2AJ ingestion to populate court decisions.
            </div>
          )}
        </div>
      </div>

      {/* Jurisdiction breakdown */}
      <div className="card" style={{ marginTop: 16 }}>
        <div className="card-title" style={{ marginBottom: 16 }}>All Documents by Jurisdiction</div>
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
