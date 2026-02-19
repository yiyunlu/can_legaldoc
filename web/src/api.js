const API_BASE = '/api';

/* Track backend reachability to avoid console spam */
let _backendOnline = true;
export function isBackendOnline() { return _backendOnline; }

async function request(url, options = {}) {
    let res;
    try {
        res = await fetch(`${API_BASE}${url}`, options);
    } catch (e) {
        /* Network error (backend unreachable) — swallow to avoid console spam */
        _backendOnline = false;
        throw new Error('Backend unreachable');
    }
    if (!res.ok) {
        /* Proxy returns 500/502/503 when backend is down */
        if (res.status >= 500) _backendOnline = false;
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || 'Request failed');
    }
    _backendOnline = true;
    return res.json();
}

function post(url, body) {
    return request(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
    });
}

export const api = {
    // Health / version (uses /health which is outside /api prefix)
    getHealth:            ()       => fetch('/health').then(r => r.ok ? r.json() : null).catch(() => null),

    // Status
    getStatus:            ()       => request('/status'),
    getSourceStats:       ()       => request('/sources/stats'),

    // Sources
    getSources:           ()       => request('/sources'),
    getAvailableAdapters: ()       => request('/sources/available'),
    updateSources:        (sources)=> post('/sources', { sources }),

    // Scraper control
    startMultiSource:     (payload)=> post('/scraper/start', payload),
    stopScraper:          ()       => post('/scraper/stop', {}),

    // Scheduler
    getSchedulerConfig:    ()      => request('/scheduler'),
    updateSchedulerConfig: (cfg)   => post('/scheduler', cfg),
    triggerScheduledRun:   ()      => post('/scheduler/trigger', {}),

    // Jobs (paginated history)
    getJobs: (page = 1, perPage = 25, status = null) => {
        let url = `/jobs?page=${page}&per_page=${perPage}`;
        if (status) url += `&status=${status}`;
        return request(url);
    },

    // Documents (paginated browser)
    getDocuments: (params = {}) => {
        const qs = new URLSearchParams();
        if (params.page) qs.set('page', params.page);
        if (params.per_page) qs.set('per_page', params.per_page);
        if (params.source_type) qs.set('source_type', params.source_type);
        if (params.jurisdiction) qs.set('jurisdiction', params.jurisdiction);
        if (params.document_type) qs.set('document_type', params.document_type);
        if (params.search) qs.set('search', params.search);
        return request(`/documents?${qs.toString()}`);
    },
    getDocument: (id) => request(`/documents/${id}`),

    // Legacy (kept for backward compat)
    getConfig:            ()       => request('/config'),
    updateConfig:         (targets)=> post('/config', { targets }),
};
