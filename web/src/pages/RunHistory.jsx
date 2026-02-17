import React, { useState, useEffect, useCallback } from 'react';
import { api } from '../api';

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

const PER_PAGE = 25;

export default function RunHistory() {
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState('');
  const [data, setData] = useState({ jobs: [], total: 0, total_pages: 0 });
  const [expandedId, setExpandedId] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchJobs = useCallback(async () => {
    setLoading(true);
    try {
      const result = await api.getJobs(page, PER_PAGE, statusFilter || null);
      setData(result);
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }, [page, statusFilter]);

  useEffect(() => { fetchJobs(); }, [fetchJobs]);

  // Reset to page 1 when filter changes
  const handleFilterChange = (e) => {
    setStatusFilter(e.target.value);
    setPage(1);
  };

  const startIdx = (data.page - 1) * PER_PAGE + 1;
  const endIdx = Math.min(data.page * PER_PAGE, data.total);

  return (
    <div>
      <div className="page-header">
        <h2>Run History</h2>
        <p>Scrape job executions with filtering and pagination</p>
      </div>

      {/* Filter bar */}
      <div className="card" style={{ marginBottom: 16, padding: '12px 16px' }}>
        <div className="filter-bar">
          <label style={{ fontSize: 12, color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: 6 }}>
            Status:
            <select className="select" value={statusFilter} onChange={handleFilterChange}
              style={{ padding: '4px 8px', fontSize: 12 }}>
              <option value="">All</option>
              <option value="completed">Completed</option>
              <option value="failed">Failed</option>
              <option value="running">Running</option>
            </select>
          </label>
          <span className="pagination-info">
            {data.total > 0 ? `Showing ${startIdx}–${endIdx} of ${data.total} jobs` : 'No jobs found'}
          </span>
        </div>
      </div>

      {loading && data.jobs.length === 0 ? (
        <div className="card empty-state">Loading...</div>
      ) : data.jobs.length === 0 ? (
        <div className="card empty-state">
          <div style={{ fontSize: 28, marginBottom: 8 }}>&#x1F4CB;</div>
          {statusFilter ? `No ${statusFilter} jobs found.` : 'No scrape jobs recorded yet.'}
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
              {data.jobs.map(job => (
                <React.Fragment key={job.id}>
                  <tr>
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
                    <td>
                      <span
                        className="log-expand"
                        onClick={() => setExpandedId(expandedId === job.id ? null : job.id)}
                        title="Click to expand"
                      >
                        {expandedId === job.id ? '▼ collapse' : '▶ view logs'}
                      </span>
                    </td>
                  </tr>
                  {expandedId === job.id && (
                    <tr className="doc-detail-row">
                      <td colSpan={6} style={{ padding: 0 }}>
                        <pre className="log-full">{job.logs || '(no logs)'}</pre>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Pagination */}
      {data.total_pages > 1 && (
        <div className="pagination">
          <button className="btn btn-ghost btn-sm" disabled={page <= 1}
            onClick={() => setPage(p => Math.max(1, p - 1))}>
            ← Prev
          </button>
          <span>Page {data.page} of {data.total_pages}</span>
          <button className="btn btn-ghost btn-sm" disabled={page >= data.total_pages}
            onClick={() => setPage(p => p + 1)}>
            Next →
          </button>
        </div>
      )}
    </div>
  );
}
