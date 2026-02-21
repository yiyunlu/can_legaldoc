const API_BASE = '/api';

/* ── Auth helpers ────────────────────────────────────── */
const AUTH_KEY = 'canlegal_api_key';

export function getStoredKey() {
    return localStorage.getItem(AUTH_KEY) || '';
}

export function setStoredKey(key) {
    if (key) localStorage.setItem(AUTH_KEY, key);
    else localStorage.removeItem(AUTH_KEY);
}

export function clearStoredKey() {
    localStorage.removeItem(AUTH_KEY);
}

function authHeaders() {
    const key = getStoredKey();
    return key ? { Authorization: `Bearer ${key}` } : {};
}

/* Track backend reachability to avoid console spam */
let _backendOnline = true;
export function isBackendOnline() { return _backendOnline; }

async function request(url, options = {}, _retries = 3) {
    // Merge auth headers into every request
    options.headers = { ...authHeaders(), ...options.headers };

    let res;
    try {
        res = await fetch(`${API_BASE}${url}`, options);
    } catch (e) {
        /* Network error — retry if attempts remain */
        if (_retries > 1) {
            await new Promise(r => setTimeout(r, 800));
            return request(url, options, _retries - 1);
        }
        _backendOnline = false;
        throw new Error('Backend unreachable');
    }
    if (!res.ok) {
        /* Tunnel 502/503 — retry automatically */
        if (res.status >= 502 && res.status <= 504 && _retries > 1) {
            await new Promise(r => setTimeout(r, 800));
            return request(url, options, _retries - 1);
        }
        if (res.status >= 500) _backendOnline = false;
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        const error = new Error(err.detail || 'Request failed');
        error.status = res.status;
        throw error;
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

    // Auth
    getAuthStatus:        ()       => request('/auth/status'),
    verifyKey: (key)      => fetch(`${API_BASE}/auth/verify`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${key}` },
    }).then(async r => {
        if (!r.ok) {
            const err = await r.json().catch(() => ({ detail: r.statusText }));
            throw new Error(err.detail || 'Invalid key');
        }
        return r.json();
    }),

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

    // Database diagnostics
    getDbDiagnostics:     ()       => request('/debug/db'),

    // Legacy (kept for backward compat)
    getConfig:            ()       => request('/config'),
    updateConfig:         (targets)=> post('/config', { targets }),
};
