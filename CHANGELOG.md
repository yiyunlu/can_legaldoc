# Changelog

All notable changes to the Canadian Legal Data Platform are documented here.

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
