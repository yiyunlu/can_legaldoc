const API_BASE = '/api';

async function request(url, options = {}) {
    const res = await fetch(`${API_BASE}${url}`, options);
    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || 'Request failed');
    }
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

    // Legacy (kept for backward compat)
    getConfig:            ()       => request('/config'),
    updateConfig:         (targets)=> post('/config', { targets }),
};
