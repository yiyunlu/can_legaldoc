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

    // Legacy (kept for backward compat)
    getConfig:            ()       => request('/config'),
    updateConfig:         (targets)=> post('/config', { targets }),
};
