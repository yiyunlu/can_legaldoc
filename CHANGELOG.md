# Changelog

All notable changes to the Canadian Legal Data Platform are documented here.

## v5.5 — 2025-02-18

### Added
- **5 new provincial legislation adapters** — expands coverage from 4 jurisdictions to 9:
  - **Manitoba** (`manitoba_laws`): ~1,926 statutes & regulations from `web2.gov.mb.ca/laws` (OpenMB Licence)
  - **Newfoundland & Labrador** (`newfoundland_laws`): ~2,105 statutes & regulations from `assembly.nl.ca` (Crown copyright)
  - **New Brunswick** (`new_brunswick_laws`): ~1,560 statutes & regulations from `laws.gnb.ca` Irosoft LIMS (Crown copyright)
  - **Nova Scotia** (`nova_scotia_laws`): ~790 statutes & regulations from `nslegislature.ca` + `novascotia.ca` (Crown copyright)
  - **Ontario** (`ontario_elaws`): ~3,044 statutes & regulations from `ontario.ca/laws` e-Laws (Crown copyright)
- **Ontario REST API discovery**: Reverse-engineered the e-Laws Elasticsearch-backed API (`/laws/api/v2/legislation/en/browse-search` + `/doc-search`) — no Playwright required despite the site being a React SPA
- All 5 adapters use `requests` + `lxml` — no new Python dependencies, no headless browser needed

### Changed
- Adapter count: 5 → 10 registered adapters
- `config.json`: 5 new data source entries (all enabled by default)
- Dashboard + Documents pages: `SOURCE_META` updated with 5 new provincial sources (GOV badge)

### Deployment
```bash
cd /opt/canlii && git pull && docker compose up -d --build
# No database migration needed — existing schema supports new source_type values
# No Playwright required — all 5 new adapters use HTTP APIs
```

---

## v5.4 — 2025-02-17

### Added
- **Document Browser page**: New "Documents" tab for browsing, searching, and filtering all ingested legal documents
  - Paginated table with 50 docs per page
  - Filter by source type, jurisdiction, document type
  - Title search (debounced, uses PostgreSQL ILIKE)
  - Inline detail expansion: click any row to see version info, content hash, metadata, content length
  - External link to source URL for each document
- **Paginated Run History**: Dedicated `/api/jobs` endpoint replaces hardcoded 10-job limit
  - Status filter dropdown (All / Completed / Failed / Running)
  - Prev/Next pagination with page indicator
  - Expandable log details: click to view full job logs
- **Per-source "Last Updated" timestamps** on Dashboard — shows when each data source was last scraped
- **Sidebar scheduler info**: Shows next scheduled run time when scraper is idle and scheduler is enabled

### Changed
- Stats API (`/api/sources/stats`): now includes `last_updated_by_source` map with per-source timestamps
- Run History: component now self-fetches from `/api/jobs` instead of relying on `stats.recent_jobs` (10-job limit)
- Database: added `idx_scrape_jobs_started_at` index for paginated job queries

### New API Endpoints
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/jobs` | Paginated job history with status filter |
| GET | `/api/documents` | Paginated document listing with filters |
| GET | `/api/documents/{id}` | Document detail with version info |

### Deployment
```bash
cd /opt/canlii && git pull && docker compose up -d --build
# New index auto-creates on fresh install; for existing: runs on next init.sql execution
# No manual migration needed
```

---

## v5.3 — 2025-02-17

### Added
- **Built-in Scheduler**: Automated scraping runs inside the Docker container — no external systemd/cron needed
  - `scheduler_config` table (singleton row) stores all schedule settings
  - `SchedulerService` daemon thread ticks every 60s, checks `next_run_at`
  - Two schedule modes: **daily at HH:MM UTC** or **every N hours**
  - Configurable scrape limit and distribution mode per scheduled run
  - Container-restart recovery: missed runs fire immediately on startup
  - Hot-reload: config changes from the UI apply within 1 minute
- **Supabase Keepalive**: Lightweight periodic ping to Supabase REST API prevents free-tier project pause (7-day inactivity limit)
  - Separate daemon thread, configurable interval (default 24h)
  - Only active when `SUPABASE_URL` env var is set
- **Scheduler UI** in Settings page: enable/disable toggle, schedule type selector, scrape limit, distribution mode, Run Now button, last/next run display
- **Scheduler API endpoints**: `GET/POST /api/scheduler`, `POST /api/scheduler/trigger`
- **Job tagging**: Scrape jobs now tagged with `[manual]` or `[scheduled]` trigger source in Run History

### Changed
- ScraperManager: new `trigger_source` parameter tracks how each scrape was initiated
- Status API: includes `scheduler.enabled` and `scheduler.next_run_at` in response

### Deployment
```bash
cd /opt/canlii && git pull && docker compose up -d --build
# scheduler_config table auto-creates on startup (existing installs) or via init.sql (fresh)
# Scheduler starts disabled by default — enable via Settings page
```

---

## v5.2 — 2025-02-17

### Changed
- **Database: Supabase → self-hosted PostgreSQL 16** — eliminates 500 MB free-tier limit, supports unlimited local storage with LZ4 TOAST compression (~60% savings on text columns)
- New `DatabaseClient` (`scraper/db_client.py`) replaces `SupabaseClient` — uses `psycopg2` with `ThreadedConnectionPool` (direct SQL, no REST overhead)
- `docker-compose.yml` now includes a `postgres` service with health checks, named volume (`pgdata`), and auto-init via `database/init.sql`
- `DATABASE_URL` is the single required env var (auto-set by docker-compose); Supabase vars are now optional (kept only for migration)
- Stats API endpoint (`/api/sources/stats`) uses efficient SQL `GROUP BY` queries instead of N+1 Supabase REST calls

### Added
- `database/init.sql` — combined schema (jurisdictions, scrape_targets, documents, document_versions, document_chunks, scrape_jobs) with indexes and LZ4 compression
- `scripts/migrate_supabase_to_local.py` — one-time migration script to copy all data from Supabase to local PostgreSQL

### Removed
- Runtime dependency on `supabase` Python SDK (kept in requirements.txt only for migration script)
- `SUPABASE_URL` / `SUPABASE_KEY` no longer required to start the application

### Deployment
```bash
# First time (fresh install):
cd /opt/canlii && git pull
echo "POSTGRES_PASSWORD=your_secure_password" >> .env
docker compose up -d --build
# PostgreSQL auto-initializes schema on first start

# Upgrade from v5.1 (with existing Supabase data):
cd /opt/canlii && git pull
echo "POSTGRES_PASSWORD=your_secure_password" >> .env
docker compose up -d --build
# Run migration:
docker exec canlii-platform python scripts/migrate_supabase_to_local.py
```

---

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
