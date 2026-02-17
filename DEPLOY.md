# Deployment Guide — PVE + Cloudflare Tunnel

Deploy the Canadian Legal Data Platform on a Proxmox VE LXC container with Docker and Cloudflare Tunnel.

## Architecture

```
Internet → Cloudflare Tunnel → Docker (app:8000) → FastAPI + React SPA
                                                  → PostgreSQL 16 (local, Docker)
```

- **LXC container** on Proxmox VE (Debian 12 / Ubuntu 22.04)
- **Docker** runs the app + PostgreSQL + cloudflared sidecar
- **PostgreSQL 16** stores all data locally (no cloud DB dependency)
- **FastAPI** serves both the API (`/api/*`) and the built React frontend
- **Cloudflare Access** handles authentication (no app-level login needed)
- **Built-in scheduler** runs automated scraping (configurable daily/interval, no external cron needed)
- **systemd timer** available as an alternative for automated scraping

---

## 1. Create LXC Container in Proxmox

### Via Proxmox GUI

1. **Download template**: local storage > CT Templates > Download `debian-12-standard`
2. **Create CT**:
   - Template: `debian-12-standard`
   - CPU: **2 cores** (minimum)
   - RAM: **4 GB** (minimum; 8 GB recommended for large HF datasets)
   - Disk: **20 GB** (minimum; 40 GB if using Playwright)
   - Network: DHCP or static IP on your LAN
3. **Enable nesting** (required for Docker):
   - Container > Options > Features > check **Nesting**

### Via CLI

```bash
# On Proxmox host
pct create 200 local:vztmpl/debian-12-standard_12.7-1_amd64.tar.zst \
  --hostname canlii \
  --cores 2 --memory 4096 --swap 512 \
  --rootfs local-lvm:20 \
  --net0 name=eth0,bridge=vmbr0,ip=dhcp \
  --features nesting=1,keyctl=1 \
  --unprivileged 1

pct start 200
```

---

## 2. Install Docker in LXC

```bash
# Enter the container
pct enter 200    # or: ssh root@<container-ip>

# Install Docker (Debian)
apt update && apt install -y ca-certificates curl gnupg

install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/debian/gpg \
  | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg

echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/debian $(. /etc/os-release && echo $VERSION_CODENAME) stable" \
  > /etc/apt/sources.list.d/docker.list

apt update
apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
systemctl enable docker
```

Verify: `docker run hello-world`

---

## 3. Clone Repo & Configure

```bash
cd /opt
git clone https://github.com/yiyunlu/can_legaldoc.git canlii
cd canlii
git checkout claude/mystifying-wilson    # or the deployment branch

# Create .env from template
cp .env.example .env
nano .env
```

Fill in your values:

```env
POSTGRES_PASSWORD=your_secure_password
CLOUDFLARE_TUNNEL_TOKEN=your-tunnel-token
ALLOWED_ORIGIN=https://canlii.your-domain.com
```

> **Note:** `DATABASE_URL` is auto-constructed by `docker-compose.yml` from `POSTGRES_PASSWORD`. You only need to set `POSTGRES_PASSWORD` in `.env`.

Ensure `config.json` has your desired data sources configured.

---

## 4. Database Setup

PostgreSQL initializes automatically on first container start. The schema in `database/init.sql` is mounted into the container's `docker-entrypoint-initdb.d/` directory.

**Fresh install:** No manual migration needed — `docker compose up` handles everything.

**Migrating from Supabase (v5.1 or earlier):** Add your Supabase credentials to `.env`, then run:
```bash
docker exec canlii-platform python scripts/migrate_supabase_to_local.py
```

---

## 5. Build & Run

```bash
cd /opt/canlii

# Build and start (first time takes 3-5 min)
docker compose up -d --build

# Watch logs
docker compose logs -f app
```

Verify locally:

```bash
# Health check
curl http://localhost:8000/health
# → {"status":"ok","service":"Canadian Legal Data Platform","version":"5.4"}

# API status
curl http://localhost:8000/api/status

# Dashboard (should return HTML)
curl -s http://localhost:8000/ | head -5
```

---

## 6. Set Up Cloudflare Tunnel

### Create the Tunnel

1. Go to [Cloudflare Zero Trust Dashboard](https://one.dash.cloudflare.com)
2. **Networks** > **Tunnels** > **Create a tunnel**
3. Name it (e.g., `canlii-platform`)
4. Copy the **tunnel token**
5. Paste it into `.env` as `CLOUDFLARE_TUNNEL_TOKEN`

### Configure Public Hostname

In the tunnel settings:

| Field | Value |
|-------|-------|
| Public hostname | `canlii.your-domain.com` |
| Service | `http://app:8000` |

> The service hostname is `app` (not `localhost`) because cloudflared runs as a Docker container on the same network as the app.

### Restart cloudflared

```bash
docker compose restart cloudflared
docker compose logs -f cloudflared
# Look for: "Connection registered" / "Registered tunnel connection"
```

Verify: open `https://canlii.your-domain.com` in your browser.

---

## 7. Set Up Cloudflare Access (Authentication)

1. Cloudflare Zero Trust > **Access** > **Applications** > **Add an application**
2. Type: **Self-hosted**
3. Application domain: `canlii.your-domain.com`
4. Create a **policy**:
   - Allow: Emails ending in `@your-domain.com`
   - Or: specific email addresses
5. Save

Now visiting `https://canlii.your-domain.com` will prompt for Cloudflare login before showing the dashboard.

---

## 8. Set Up Automated Scraping

### Option A: Built-in Scheduler (recommended, v5.3+)

The platform includes a built-in scheduler that runs inside the Docker container. No external cron or systemd setup needed.

1. Open the dashboard → **Settings** page
2. Find the **Scheduler** card
3. Toggle **Enabled**
4. Choose schedule type:
   - **Daily at HH:MM UTC** (e.g., 02:00)
   - **Every N hours** (e.g., every 12 hours)
5. Set **Scrape Limit** (default 500) and **Distribution Mode**
6. Click **Save**

The scheduler automatically:
- Runs scraping at the configured time
- Recovers missed runs after container restarts
- Tags jobs as `[scheduled]` in Run History
- Reloads config changes within 1 minute

**Via API:**
```bash
# Enable scheduler
curl -X POST http://localhost:8000/api/scheduler \
  -H 'Content-Type: application/json' \
  -d '{"enabled": true, "schedule_type": "daily", "daily_time": "02:00", "scrape_limit": 500}'

# Check scheduler status
curl http://localhost:8000/api/scheduler

# Manually trigger a run
curl -X POST http://localhost:8000/api/scheduler/trigger \
  -H 'Content-Type: application/json' -d '{}'
```

### Option B: systemd timer (legacy)

```bash
# Copy units
cp /opt/canlii/cron/canlii-daily-scrape.service /etc/systemd/system/
cp /opt/canlii/cron/canlii-daily-scrape.timer /etc/systemd/system/

# Make script executable
chmod +x /opt/canlii/cron/daily-scrape.sh

# Enable and start
systemctl daemon-reload
systemctl enable canlii-daily-scrape.timer
systemctl start canlii-daily-scrape.timer

# Verify
systemctl list-timers | grep canlii
```

### Option C: crontab (legacy)

```bash
chmod +x /opt/canlii/cron/daily-scrape.sh
echo "0 2 * * * /opt/canlii/cron/daily-scrape.sh" | crontab -
```

### Manual test run

```bash
docker exec canlii-platform python main_multi.py --list-sources
docker exec canlii-platform python main_multi.py --limit 10
```

---

## 9. Log Rotation

Create `/etc/logrotate.d/canlii`:

```
/var/log/canlii-scrape.log {
    daily
    rotate 14
    compress
    missingok
    notifempty
}
```

---

## 10. Maintenance

### Update the app

```bash
cd /opt/canlii
git pull
docker compose up -d --build
```

### View scraper logs

```bash
# Container logs (API + uvicorn)
docker compose logs -f app

# Scraping history
docker exec canlii-platform python main_multi.py --list-sources

# Cron logs
tail -f /var/log/canlii-scrape.log
```

### Backup database

```bash
# Full PostgreSQL dump
docker exec canlii-postgres pg_dump -U canlii canlii > /opt/canlii/backup_$(date +%Y%m%d).sql

# Backup checkpoint
cp /opt/canlii/checkpoint.db /opt/canlii/checkpoint.db.bak
```

### Restore database from backup

```bash
# Stop the app first
docker compose stop app

# Restore
docker exec -i canlii-postgres psql -U canlii canlii < /opt/canlii/backup_20250217.sql

# Restart
docker compose start app
```

### Skip Playwright (smaller image)

If you only use the multi-source adapters (XML, API, HuggingFace) and don't need the legacy CanLII deep scraper:

```yaml
# In docker-compose.yml, change:
args:
  INSTALL_PLAYWRIGHT: "false"
```

Then rebuild: `docker compose up -d --build`

This saves ~800 MB in image size.

---

## Version Upgrade History

When upgrading the deployed instance at `canlegal.ecomm101.cc`, follow these steps:

### Standard Upgrade Procedure

```bash
cd /opt/canlii
git pull
docker compose up -d --build
```

### v5.3 → v5.4 (2025-02-17)

**What changed:**
- New Document Browser page (5th tab: Documents) with paginated search, filtering, and inline detail
- Run History upgraded from hardcoded 10-job view to paginated, filterable, with expandable logs
- Dashboard shows per-source "Last updated" timestamps
- Sidebar shows next scheduled run time when idle
- 3 new API endpoints: `GET /api/jobs`, `GET /api/documents`, `GET /api/documents/{id}`
- New DB index: `idx_scrape_jobs_started_at`

**Upgrade steps:**
1. `cd /opt/canlii && git pull`
2. `docker compose up -d --build`
3. No manual DB migration needed — new index auto-creates on fresh installs
4. For existing installs, optionally add the index manually for better job query performance:
   ```bash
   docker exec canlii-postgres psql -U canlii -d canlii -c "CREATE INDEX IF NOT EXISTS idx_scrape_jobs_started_at ON scrape_jobs(started_at DESC);"
   ```

**Verify:**
```bash
# Health check should return version 5.4
curl http://localhost:8000/health

# Jobs endpoint should return paginated results
curl "http://localhost:8000/api/jobs?page=1&per_page=5"

# Documents endpoint should return paginated results
curl "http://localhost:8000/api/documents?page=1&per_page=5"

# Stats should include last_updated_by_source
curl http://localhost:8000/api/sources/stats | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('last_updated_by_source',{}))"
```

### v5.2 → v5.3 (2025-02-17)

**What changed:**
- Built-in scheduler replaces external systemd/cron for automated scraping
- `scheduler_config` table added to PostgreSQL (auto-created on startup)
- Supabase keepalive daemon prevents free-tier project pause
- Scrape jobs tagged with `[manual]` or `[scheduled]` trigger source
- 3 new API endpoints: `GET/POST /api/scheduler`, `POST /api/scheduler/trigger`
- Scheduler UI card in Settings page

**Upgrade steps:**
1. `cd /opt/canlii && git pull`
2. `docker compose up -d --build`
3. No manual DB migration needed — `scheduler_config` table auto-creates on app startup

**Verify:**
```bash
# Health check should return version 5.3
curl http://localhost:8000/health

# Scheduler config should exist
curl http://localhost:8000/api/scheduler

# Check scheduler_config table
docker exec canlii-postgres psql -U canlii -d canlii -c "SELECT enabled, schedule_type, daily_time FROM scheduler_config;"
```

**Optional:** If you had a systemd timer set up from v5.1/v5.2, you can now disable it and use the built-in scheduler instead:
```bash
systemctl disable canlii-daily-scrape.timer
systemctl stop canlii-daily-scrape.timer
```
Then enable the built-in scheduler via the Settings page.

### v5.1 → v5.2 (2025-02-17)

**What changed:**
- Database migrated from Supabase (cloud) to self-hosted PostgreSQL 16 (Docker)
- `SupabaseClient` replaced by `DatabaseClient` (psycopg2 + connection pooling)
- `docker-compose.yml` now includes `postgres` service with health checks
- `DATABASE_URL` replaces `SUPABASE_URL`/`SUPABASE_KEY` as the required env var

**Upgrade steps:**
1. `cd /opt/canlii && git pull`
2. Add `POSTGRES_PASSWORD=your_secure_password` to `.env`
3. `docker compose up -d --build` (PostgreSQL container starts + auto-initializes schema)
4. Migrate existing data from Supabase:
   ```bash
   docker exec canlii-platform python scripts/migrate_supabase_to_local.py
   ```
5. Verify data migrated: check Dashboard shows same document counts

**Verify:**
```bash
# Health check should return version 5.2
curl http://localhost:8000/health

# Check PostgreSQL is running
docker exec canlii-postgres pg_isready -U canlii -d canlii

# Verify document count
docker exec canlii-postgres psql -U canlii -d canlii -c "SELECT COUNT(*) FROM documents;"
```

### v5.0 → v5.1 (2025-02-17)

**What changed:**
- Mobile-responsive UI (hamburger menu, responsive grids)
- New data source: Alberta King's Printer (`alberta_kings_printer`)
- Smart limit distribution (proportional/equal/sequential modes)

**Upgrade steps:**
1. `cd /opt/canlii && git pull`
2. `docker compose up -d --build`
3. No DB migration needed — v4 schema supports new `source_type` values automatically

**Verify:**
```bash
# Health check should return version 5.1
curl http://localhost:8000/health

# Should list 5 adapters (including alberta_kings_printer)
docker exec canlii-platform python main_multi.py --list-sources

# Test Alberta adapter
docker exec canlii-platform python main_multi.py --source alberta_kings_printer --limit 5
```

---

## Verification Checklist

- [ ] `curl http://localhost:8000/health` returns `{"status":"ok","version":"5.4"}`
- [ ] `curl http://localhost:8000/api/status` returns scraper status with `scheduler` field
- [ ] `curl http://localhost:8000/api/scheduler` returns scheduler config
- [ ] `curl http://localhost:8000/api/jobs?page=1&per_page=5` returns paginated jobs
- [ ] `curl http://localhost:8000/api/documents?page=1&per_page=5` returns paginated documents
- [ ] `http://localhost:8000` in browser shows the React dashboard
- [ ] All 5 pages load (Dashboard, Data Sources, Documents, Run History, Settings)
- [ ] Documents page: search, filter by source/jurisdiction/type, pagination, click-to-expand detail
- [ ] Run History: status filter, pagination, expandable logs
- [ ] Dashboard shows "Last updated" timestamps under each source
- [ ] Sidebar shows "Next: ..." when scheduler is enabled and scraper is idle
- [ ] Settings page shows Scheduler card with enable toggle and schedule config
- [ ] Mobile layout works (resize browser or test on phone)
- [ ] `https://canlegal.ecomm101.cc` loads behind Cloudflare Access
- [ ] `docker exec canlii-platform python main_multi.py --list-sources` works
- [ ] Run a test scrape from the Data Sources page (click "Run" on any source)
- [ ] Scheduler "Run Now" button triggers a scrape
- [ ] Scheduled jobs appear in Run History with `[scheduled]` tag
- [ ] Alberta King's Printer source appears in Data Sources page
