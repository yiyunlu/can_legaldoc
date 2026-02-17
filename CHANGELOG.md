# Changelog

All notable changes to the Canadian Legal Data Platform are documented here.

## v5.1 — 2025-02-17

### Added
- **Mobile-responsive UI**: Hamburger menu, responsive grids, and optimized layouts for phones and tablets
- **Alberta King's Printer adapter** (`alberta_kings_printer`): Discovers ~1,415 Alberta statutes and regulations via the CKAN API (open.alberta.ca) and fetches HTML content from the official King's Printer website
- **Smart limit distribution**: Three modes for distributing scrape limits across sources:
  - `proportional` (default) — allocates based on estimated doc counts per source
  - `equal` — splits limit evenly among all enabled sources
  - `sequential` — legacy behavior, first-come-first-served

### Changed
- Data Sources controls bar: added distribution mode selector dropdown
- Dashboard and Data Sources: added `GOV` badge and metadata for Alberta source
- Stats API: now queries `alberta_kings_printer` source type

### Fixed
- API polling: adaptive intervals (2s running / 5s idle / 10s offline) instead of fixed 2s
- Backend offline indicator: sidebar shows amber "Offline" status with pulsing dot when API is unreachable
- Eliminated console error spam when backend is down (graceful error handling in `api.js`)

### Deployment
```bash
cd /opt/canlii && git pull && docker compose up -d --build
```
No database migration needed — v4 schema already supports new `source_type` values.

---

## v5.0 — 2025-02-15

### Added
- Modern dark dashboard UI (React 19 + Vite 7)
- Multi-source adapter architecture (pluggable adapters)
- Federal Legislation adapter (Justice Canada XML from GitHub)
- BC Laws adapter (CiviX REST API)
- A2AJ Case Law adapter (Hugging Face dataset streaming)
- Data Sources management page
- Docker deployment with Cloudflare Tunnel support
- SQLite checkpoint deduplication
- Document version tracking (SHA-256 content hash)
- systemd timer for daily automated scraping
