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
  justice_canada_xml:    { est: 5795, type: 'leg' },
  bc_laws_api:           { est: 882, type: 'leg' },
  alberta_kings_printer: { est: 1415, type: 'leg' },
  a2aj_case_law:         { est: 184565, type: 'case' },
  canlii_legacy:         { est: 1000, type: 'leg' },
  manitoba_laws:         { est: 1926, type: 'leg' },
  newfoundland_laws:     { est: 2105, type: 'leg' },
  nova_scotia_laws:      { est: 790, type: 'leg' },
  new_brunswick_laws:    { est: 1560, type: 'leg' },
  ontario_elaws:         { est: 4400, type: 'leg' },
  yukon_laws:            { est: 200, type: 'leg' },
  nwt_laws:              { est: 300, type: 'leg' },
  nunavut_laws:          { est: 250, type: 'leg' },
  saskatchewan_laws:     { est: 1160, type: 'leg' },
  pei_laws:              { est: 850, type: 'leg' },
  quebec_laws:           { est: 4700, type: 'leg' },
  ns_courts:             { est: 8000, type: 'case' },
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
  'NSSC': 'NS Supreme Court',
  'NSCA': 'NS Court of Appeal',
  'NSPC': 'NS Provincial Court',
  'NSSM': 'NS Small Claims Court',
  'NSFC': 'NS Family Court',
};

const COURT_COLORS = {
  'SCC': '#ef4444', 'FCA': '#f97316', 'FC': '#f59e0b', 'TCC': '#eab308',
  'BCSC': '#22c55e', 'BCCA': '#10b981', 'ONCA': '#06b6d4', 'ONSC': '#0ea5e9',
  'SST': '#8b5cf6', 'IRB-RAD': '#a855f7', 'IRB-RPD': '#c084fc',
  'CHRT': '#ec4899', 'CMAC': '#f43f5e', 'YKCA': '#14b8a6',
  'NSSC': '#fb923c', 'NSCA': '#f97316', 'NSPC': '#fdba74',
  'NSSM': '#fed7aa', 'NSFC': '#ffedd5',
};

export default function Dashboard({ status, stats }) {
  if (!stats) return <div style={{ padding: 20, color: 'var(--text-muted)' }}>Loading dashboard...</div>;

  const bySource = stats.by_source || {};
  const byJur = stats.by_jurisdiction || {};
  const byType = stats.by_type || {};
  const byCourt = stats.by_court || {};
  const total = stats.total_documents || 0;
  const isRunning = status?.is_running || false;

  const caseLawTotal = byType.case_law || 0;
  const legislationTotal = byType.legislation || 0;
  const regulationTotal = byType.regulation || 0;

  const numSources = Object.keys(bySource).length;
  const numJurisdictions = Object.keys(byJur).length;
  const numCourts = Object.keys(byCourt).length;

  // Coverage calculation
  const estLeg = Object.entries(SOURCE_META)
    .filter(([k, m]) => m.type === 'leg' && k !== 'canlii_legacy')
    .reduce((s, [, m]) => s + (m.est || 0), 0);
  const legCovPct = estLeg > 0 ? Math.round(((legislationTotal + regulationTotal) / estLeg) * 100) : 0;

  const maxJur = Math.max(...Object.values(byJur).map(j => j.count), 1);
  const maxCourt = Math.max(...Object.values(byCourt), 1);

  // Top 10 courts
  const topCourts = Object.entries(byCourt)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 12);

  return (
    <div>
      <div className="page-header">
        <h2>Platform Overview</h2>
        <p>Canada's comprehensive legal document aggregation platform</p>
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

      {/* ── Hero Metrics ── */}
      <div className="hero-stats">
        <div className="hero-stat">
          <div className="hero-value" style={{ color: 'var(--accent)' }}>{total.toLocaleString()}</div>
          <div className="hero-label">Total Documents</div>
        </div>
        <div className="hero-stat">
          <div className="hero-value" style={{ color: 'var(--success)' }}>{numSources}</div>
          <div className="hero-label">Data Pipelines</div>
        </div>
        <div className="hero-stat">
          <div className="hero-value" style={{ color: 'var(--info)' }}>{numJurisdictions}</div>
          <div className="hero-label">Jurisdictions</div>
        </div>
        <div className="hero-stat">
          <div className="hero-value" style={{ color: legCovPct >= 90 ? 'var(--success)' : 'var(--orange)' }}>
            {legCovPct}%
          </div>
          <div className="hero-label">Legislation Coverage</div>
        </div>
      </div>

      {/* ── Data Pipeline Overview ── */}
      <div className="pipeline-grid">
        <div className="pipeline-card">
          <div className="pipeline-header">
            <span className="pipeline-dot" style={{ background: 'var(--info)' }} />
            <span className="pipeline-title">Legislation</span>
          </div>
          <div className="pipeline-value">{legislationTotal.toLocaleString()}</div>
          <div className="pipeline-sub">
            {Object.entries(SOURCE_META).filter(([k, m]) => m.type === 'leg' && k !== 'canlii_legacy').length} sources &middot; All provinces & territories
          </div>
          <div className="pipeline-bar-track">
            <div className="pipeline-bar-fill" style={{
              width: `${Math.min(100, estLeg > 0 ? (legislationTotal / estLeg) * 100 : 0)}%`,
              background: 'var(--info)',
            }} />
          </div>
        </div>

        <div className="pipeline-card">
          <div className="pipeline-header">
            <span className="pipeline-dot" style={{ background: 'var(--orange)' }} />
            <span className="pipeline-title">Regulations</span>
          </div>
          <div className="pipeline-value">{regulationTotal.toLocaleString()}</div>
          <div className="pipeline-sub">Federal regulations via Justice Canada XML</div>
          <div className="pipeline-bar-track">
            <div className="pipeline-bar-fill" style={{
              width: regulationTotal > 0 ? '100%' : '0%',
              background: 'var(--orange)',
            }} />
          </div>
        </div>

        <div className="pipeline-card">
          <div className="pipeline-header">
            <span className="pipeline-dot" style={{ background: 'var(--purple)' }} />
            <span className="pipeline-title">Case Law</span>
          </div>
          <div className="pipeline-value">{caseLawTotal.toLocaleString()}</div>
          <div className="pipeline-sub">
            {numCourts} courts &middot; Federal, BC, ON, NS + tribunals
          </div>
          <div className="pipeline-bar-track">
            <div className="pipeline-bar-fill" style={{
              width: '100%',
              background: 'var(--purple)',
            }} />
          </div>
        </div>
      </div>

      {/* ── Two-Column: Jurisdictions + Courts ── */}
      <div className="dashboard-two-col">
        <div className="card">
          <div className="card-title" style={{ marginBottom: 14 }}>Jurisdiction Coverage</div>
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

        <div className="card">
          <div className="card-title" style={{ marginBottom: 14, display: 'flex', alignItems: 'center', gap: 8 }}>
            <span>Court Distribution</span>
            <span style={{
              fontSize: 11, color: 'var(--text-muted)', fontWeight: 400,
              textTransform: 'none', letterSpacing: 0,
            }}>
              {caseLawTotal.toLocaleString()} decisions
            </span>
          </div>
          {topCourts.length > 0 ? (
            <div className="jur-bar-wrap">
              {topCourts.map(([court, count]) => (
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

      {/* ── Live Progress ── */}
      {isRunning && status && (
        <div className="card" style={{ marginTop: 16 }}>
          <div className="card-title" style={{ marginBottom: 16 }}>Live Progress</div>
          <div className="stat-grid" style={{ gridTemplateColumns: 'repeat(4, 1fr)' }}>
            <div className="stat-card">
              <div className="stat-value" style={{ color: 'var(--success)', fontSize: 22 }}>{status.stats.success}</div>
              <div className="stat-label">Success</div>
            </div>
            <div className="stat-card">
              <div className="stat-value" style={{ color: 'var(--error)', fontSize: 22 }}>{status.stats.failed}</div>
              <div className="stat-label">Failed</div>
            </div>
            <div className="stat-card">
              <div className="stat-value" style={{ color: 'var(--text-muted)', fontSize: 22 }}>{status.stats.skipped}</div>
              <div className="stat-label">Skipped</div>
            </div>
            <div className="stat-card">
              <div className="stat-value" style={{ fontSize: 22 }}>
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
