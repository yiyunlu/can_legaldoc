import React from 'react';

function formatDate(iso) {
  if (!iso) return '--';
  const d = new Date(iso);
  return d.toLocaleDateString('en-CA', { year: 'numeric', month: 'short', day: 'numeric' })
    + ' ' + d.toLocaleTimeString('en-CA', { hour: '2-digit', minute: '2-digit' });
}

function duration(start, end) {
  if (!start || !end) return '--';
  const ms = new Date(end) - new Date(start);
  if (ms < 1000) return '<1s';
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  const rs = s % 60;
  return `${m}m ${rs}s`;
}

export default function RunHistory({ stats }) {
  const jobs = stats?.recent_jobs || [];

  return (
    <div>
      <div className="page-header">
        <h2>Run History</h2>
        <p>Recent scrape job executions</p>
      </div>

      {jobs.length === 0 ? (
        <div className="card empty-state">
          <div style={{ fontSize: 28, marginBottom: 8 }}>&#x1F4CB;</div>
          No scrape jobs recorded yet.
        </div>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Status</th>
                <th>Started</th>
                <th>Duration</th>
                <th style={{ textAlign: 'right' }}>Scraped</th>
                <th style={{ textAlign: 'right' }}>Failed</th>
                <th>Details</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map(job => (
                <tr key={job.id}>
                  <td>
                    <span className={`job-status job-${job.status}`}>
                      {job.status}
                    </span>
                  </td>
                  <td style={{ fontSize: 12 }}>{formatDate(job.started_at)}</td>
                  <td style={{ fontSize: 12, fontFamily: 'monospace' }}>
                    {duration(job.started_at, job.finished_at)}
                  </td>
                  <td style={{ textAlign: 'right', fontWeight: 600, color: 'var(--success)' }}>
                    {job.items_scraped}
                  </td>
                  <td style={{ textAlign: 'right', fontWeight: 600, color: job.items_failed > 0 ? 'var(--error)' : 'var(--text-muted)' }}>
                    {job.items_failed}
                  </td>
                  <td style={{ fontSize: 11, color: 'var(--text-muted)', maxWidth: 300, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {job.logs}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
