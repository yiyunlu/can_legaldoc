const API_BASE = '/api';

export const api = {
    async getStatus() {
        const res = await fetch(`${API_BASE}/status`);
        return res.json();
    },

    async getConfig() {
        const res = await fetch(`${API_BASE}/config`);
        return res.json();
    },

    async updateConfig(targets) {
        const res = await fetch(`${API_BASE}/config`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ targets })
        });
        return res.json();
    },

    async startScraper(payload) {
        const res = await fetch(`${API_BASE}/scraper/start`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || 'Failed to start');
        }
        return res.json();
    },

    async stopScraper() {
        const res = await fetch(`${API_BASE}/scraper/stop`, { method: 'POST' });
        return res.json();
    },

    async exploreTargetsStream(onEvent) {
        const res = await fetch(`${API_BASE}/discovery/explore`);
        if (!res.ok) throw new Error("Discovery failed");

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split("\n");

            // Allow processing all lines except the last incomplete one
            buffer = lines.pop(); // Keep the last incomplete fragment in buffer (or empty string if last char was \n)

            for (const line of lines) {
                if (!line.trim()) continue;
                try {
                    const event = JSON.parse(line);
                    onEvent(event);
                } catch (err) {
                    console.error("Parse error:", err, line);
                }
            }
        }
    },

    async getDiscoveryCache() {
        const res = await fetch(`${API_BASE}/discovery/cache`);
        if (!res.ok) return { results: [] };
        return res.json();
    }
};
