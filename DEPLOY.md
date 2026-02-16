# Deployment Guide — PVE + Cloudflare Tunnel

Deploy the Canadian Legal Data Platform on a Proxmox VE LXC container with Docker and Cloudflare Tunnel.

## Architecture

```
Internet → Cloudflare Tunnel → Docker (app:8000) → FastAPI + React SPA
                                                  → Supabase (cloud DB)
```

- **LXC container** on Proxmox VE (Debian 12 / Ubuntu 22.04)
- **Docker** runs the app + cloudflared sidecar
- **FastAPI** serves both the API (`/api/*`) and the built React frontend
- **Cloudflare Access** handles authentication (no app-level login needed)
- **systemd timer** runs daily automated scraping at 2 AM

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
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-supabase-key
CLOUDFLARE_TUNNEL_TOKEN=your-tunnel-token
ALLOWED_ORIGIN=https://canlii.your-domain.com
```

Ensure `config.json` has your desired data sources configured.

---

## 4. Database Migrations

If this is a fresh Supabase project, run the migrations in the **Supabase SQL Editor**:

1. `database/migration_v3_schema.sql` — creates base tables
2. `database/migration_v4_multi_source.sql` — adds multi-source columns + jurisdictions

If you already have data (from previous runs), only run the v4 migration.

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
# → {"status":"ok","service":"Canadian Legal Data Platform","version":"5.0"}

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

### Option A: systemd timer (recommended)

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

### Option B: crontab

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

### Backup checkpoint

```bash
cp /opt/canlii/checkpoint.db /opt/canlii/checkpoint.db.bak
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

## Verification Checklist

- [ ] `curl http://localhost:8000/health` returns `{"status":"ok"}`
- [ ] `curl http://localhost:8000/api/status` returns scraper status
- [ ] `http://localhost:8000` in browser shows the React dashboard
- [ ] All 4 pages load (Dashboard, Data Sources, Run History, Settings)
- [ ] `https://canlii.your-domain.com` loads behind Cloudflare Access
- [ ] `docker exec canlii-platform python main_multi.py --list-sources` works
- [ ] `systemctl list-timers | grep canlii` shows the daily timer
- [ ] Run a test scrape from the Data Sources page (click "Run" on any source)
