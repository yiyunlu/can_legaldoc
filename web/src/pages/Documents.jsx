import React, { useState, useEffect, useCallback, useRef } from 'react';
import { api } from '../api';

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
  yukon_laws:            { label: 'GOV',  badge: 'badge-gov', name: 'Yukon Laws' },
  nwt_laws:              { label: 'GOV',  badge: 'badge-gov', name: 'NWT Laws' },
  nunavut_laws:          { label: 'GOV',  badge: 'badge-gov', name: 'Nunavut Laws' },
  saskatchewan_laws:     { label: 'API',  badge: 'badge-api', name: 'Saskatchewan Laws' },
  pei_laws:              { label: 'GOV',  badge: 'badge-gov', name: 'PEI Laws' },
  quebec_laws:           { label: 'GOV',  badge: 'badge-gov', name: 'Legis Québec' },
};

const JUR_NAMES = {
  ca: 'Federal', bc: 'British Columbia', ab: 'Alberta', on: 'Ontario',
  qc: 'Quebec', ns: 'Nova Scotia', nb: 'New Brunswick', mb: 'Manitoba',
  pe: 'PEI', sk: 'Saskatchewan', nl: 'Newfoundland', yt: 'Yukon',
  nt: 'NWT', nu: 'Nunavut',
};

function formatDate(iso) {
  if (!iso) return '--';
  const d = new Date(iso);
  return d.toLocaleDateString('en-CA', { year: 'numeric', month: 'short', day: 'numeric' })
    + ' ' + d.toLocaleTimeString('en-CA', { hour: '2-digit', minute: '2-digit' });
}

const PER_PAGE = 50;

export default function Documents({ stats }) {
  const [page, setPage] = useState(1);
  const [sourceType, setSourceType] = useState('');
  const [jurisdiction, setJurisdiction] = useState('');
  const [documentType, setDocumentType] = useState('');
  const [searchInput, setSearchInput] = useState('');
  const [search, setSearch] = useState('');
  const [data, setData] = useState({ documents: [], total: 0, total_pages: 0 });
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState(null);
  const [detail, setDetail] = useState(null);
  const debounceRef = useRef(null);

  // Debounce search input
  const handleSearchInput = (e) => {
    const val = e.target.value;
    setSearchInput(val);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      setSearch(val);
      setPage(1);
    }, 300);
  };

  const fetchDocs = useCallback(async () => {
    setLoading(true);
    try {
      const params = { page, per_page: PER_PAGE };
      if (sourceType) params.source_type = sourceType;
      if (jurisdiction) params.jurisdiction = jurisdiction;
      if (documentType) params.document_type = documentType;
      if (search) params.search = search;
      const result = await api.getDocuments(params);
      setData(result);
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }, [page, sourceType, jurisdiction, documentType, search]);

  useEffect(() => { fetchDocs(); }, [fetchDocs]);

  // Fetch document detail when expanding
  const toggleDetail = async (docId) => {
    if (expandedId === docId) {
      setExpandedId(null);
      setDetail(null);
      return;
    }
    setExpandedId(docId);
    try {
      const d = await api.getDocument(docId);
      setDetail(d);
    } catch {
      setDetail(null);
    }
  };

  // Reset page when filters change
  const resetFilter = (setter) => (e) => {
    setter(e.target.value);
    setPage(1);
  };

  // Build dropdown options from stats
  const sourceOptions = stats?.by_source ? Object.keys(stats.by_source) : [];
  const jurOptions = stats?.by_jurisdiction ? Object.keys(stats.by_jurisdiction) : [];
  const typeOptions = stats?.by_type ? Object.keys(stats.by_type) : [];

  const startIdx = (data.page - 1) * PER_PAGE + 1;
  const endIdx = Math.min(data.page * PER_PAGE, data.total);

  return (
    <div>
      <div className="page-header">
        <h2>Documents</h2>
        <p>Browse and search all ingested legal documents</p>
      </div>

      {/* Filter bar */}
      <div className="card" style={{ marginBottom: 16, padding: '12px 16px' }}>
        <div className="filter-bar">
          <input
            className="input"
            type="text"
            placeholder="Search titles..."
            value={searchInput}
            onChange={handleSearchInput}
            style={{ minWidth: 180, padding: '5px 10px', fontSize: 12 }}
          />
          <select className="select" value={sourceType} onChange={resetFilter(setSourceType)}
            style={{ padding: '4px 8px', fontSize: 12 }}>
            <option value="">All Sources</option>
            {sourceOptions.map(s => (
              <option key={s} value={s}>{SOURCE_META[s]?.name || s}</option>
            ))}
          </select>
          <select className="select" value={jurisdiction} onChange={resetFilter(setJurisdiction)}
            style={{ padding: '4px 8px', fontSize: 12 }}>
            <option value="">All Jurisdictions</option>
            {jurOptions.map(j => (
              <option key={j} value={j}>{JUR_NAMES[j] || j}</option>
            ))}
          </select>
          <select className="select" value={documentType} onChange={resetFilter(setDocumentType)}
            style={{ padding: '4px 8px', fontSize: 12 }}>
            <option value="">All Types</option>
            {typeOptions.map(t => (
              <option key={t} value={t}>{t.replace(/_/g, ' ')}</option>
            ))}
          </select>
          <span className="pagination-info">
            {data.total > 0 ? `${startIdx}–${endIdx} of ${data.total.toLocaleString()}` : '0 documents'}
          </span>
        </div>
      </div>

      {/* Results */}
      {loading && data.documents.length === 0 ? (
        <div className="card empty-state">Loading...</div>
      ) : data.documents.length === 0 ? (
        <div className="card empty-state">
          <div style={{ fontSize: 28, marginBottom: 8 }}>&#x1F4DA;</div>
          No documents found. {search && 'Try a different search term.'}
        </div>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th style={{ minWidth: 250 }}>Title</th>
                <th>Jurisdiction</th>
                <th>Type</th>
                <th>Source</th>
                <th>Updated</th>
                <th style={{ width: 60 }}></th>
              </tr>
            </thead>
            <tbody>
              {data.documents.map(doc => {
                const srcMeta = SOURCE_META[doc.source_type] || { label: '?', badge: '', name: doc.source_type };
                return (
                  <React.Fragment key={doc.id}>
                    <tr style={{ cursor: 'pointer' }} onClick={() => toggleDetail(doc.id)}>
                      <td>
                        <div style={{ fontSize: 13, fontWeight: 500, lineHeight: 1.3 }}>
                          {doc.title || '(untitled)'}
                        </div>
                        {doc.citation && (
                          <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 2 }}>
                            {doc.citation}
                          </div>
                        )}
                      </td>
                      <td style={{ fontSize: 12 }}>
                        {JUR_NAMES[doc.jurisdiction_code] || doc.jurisdiction_code || '--'}
                      </td>
                      <td style={{ fontSize: 12 }}>
                        {doc.document_type?.replace(/_/g, ' ') || '--'}
                      </td>
                      <td>
                        <span className={`badge ${srcMeta.badge}`} style={{ fontSize: 10 }}>
                          {srcMeta.label}
                        </span>
                      </td>
                      <td style={{ fontSize: 11, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>
                        {formatDate(doc.updated_at)}
                      </td>
                      <td>
                        <div style={{ display: 'flex', gap: 6, alignItems: 'center', justifyContent: 'flex-end' }}>
                          {doc.has_content ? (
                            <span title="Content stored locally" style={{ color: 'var(--success)', fontSize: 13, lineHeight: 1 }}>
                              <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor"><path d="M2 3a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v2a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V3zm0 4.5a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v2a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1v-2zm1 3.5a1 1 0 0 0-1 1v2a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1v-2a1 1 0 0 0-1-1H3z"/><circle cx="12" cy="4" r="1" fill="var(--bg-card)"/><circle cx="12" cy="8.5" r="1" fill="var(--bg-card)"/><circle cx="12" cy="13" r="1" fill="var(--bg-card)"/></svg>
                            </span>
                          ) : (
                            <span title="No local content" style={{ color: 'var(--text-muted)', fontSize: 13, lineHeight: 1, opacity: 0.4 }}>
                              <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor"><path d="M2 3a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v2a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V3zm0 4.5a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v2a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1v-2zm1 3.5a1 1 0 0 0-1 1v2a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1v-2a1 1 0 0 0-1-1H3z"/><circle cx="12" cy="4" r="1" fill="var(--bg-card)"/><circle cx="12" cy="8.5" r="1" fill="var(--bg-card)"/><circle cx="12" cy="13" r="1" fill="var(--bg-card)"/></svg>
                            </span>
                          )}
                          {doc.source_url && (
                            <a href={doc.source_url} target="_blank" rel="noopener noreferrer"
                              onClick={(e) => e.stopPropagation()}
                              title="Open original source" style={{ color: 'var(--accent)', fontSize: 14 }}>
                              ↗
                            </a>
                          )}
                        </div>
                      </td>
                    </tr>
                    {expandedId === doc.id && (
                      <tr className="doc-detail-row">
                        <td colSpan={6} style={{ padding: 0 }}>
                          <div className="doc-detail-content">
                            {detail ? (
                              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px 24px', fontSize: 12 }}>
                                <div><strong>ID:</strong> <span style={{ fontFamily: 'monospace', fontSize: 10 }}>{detail.id}</span></div>
                                <div><strong>Category:</strong> {detail.category || '--'}</div>
                                <div><strong>Citation:</strong> {detail.citation || '--'}</div>
                                <div><strong>Active:</strong> {detail.is_active ? 'Yes' : 'No'}</div>
                                <div><strong>Version:</strong> {detail.version_number ?? '--'}</div>
                                <div><strong>Last Scraped:</strong> {formatDate(detail.scraped_at)}</div>
                                <div>
                                  <strong>Local Storage:</strong>{' '}
                                  {detail.has_content ? (
                                    <span style={{ color: 'var(--success)' }}>
                                      Text ({detail.content_length ? `${(detail.content_length / 1024).toFixed(1)} KB` : '--'})
                                      {detail.has_html && <span> + HTML ({detail.content_html_length ? `${(detail.content_html_length / 1024).toFixed(1)} KB` : ''})</span>}
                                    </span>
                                  ) : (
                                    <span style={{ color: 'var(--text-muted)' }}>Not stored</span>
                                  )}
                                </div>
                                <div><strong>Content Hash:</strong> <span style={{ fontFamily: 'monospace', fontSize: 10 }}>{detail.content_hash ? detail.content_hash.substring(0, 16) + '...' : '--'}</span></div>
                                <div><strong>Created:</strong> {formatDate(detail.created_at)}</div>
                                <div><strong>Source URL:</strong> {detail.source_url ? (
                                  <a href={detail.source_url} target="_blank" rel="noopener noreferrer"
                                    style={{ color: 'var(--accent)', fontSize: 11, wordBreak: 'break-all' }}>
                                    {detail.source_url.length > 60 ? detail.source_url.substring(0, 60) + '...' : detail.source_url}
                                  </a>
                                ) : '--'}</div>
                                {detail.metadata && detail.metadata !== '{}' && (
                                  <div style={{ gridColumn: '1 / -1' }}>
                                    <strong>Metadata:</strong>
                                    <pre className="log-full" style={{ marginTop: 4, maxHeight: 150 }}>
                                      {typeof detail.metadata === 'string' ? detail.metadata : JSON.stringify(detail.metadata, null, 2)}
                                    </pre>
                                  </div>
                                )}
                              </div>
                            ) : (
                              <div style={{ color: 'var(--text-muted)', fontSize: 12 }}>Loading detail...</div>
                            )}
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                );
              })}
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
