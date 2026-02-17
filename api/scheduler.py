"""
Built-in scheduler for automated scraping and Supabase keepalive.

Runs as daemon threads inside the Docker container — no external cron needed.
Config is stored in the scheduler_config DB table (singleton row).
"""
import os
import json
import threading
import time
from datetime import datetime, timedelta, timezone

from utils.logger import logger
from scraper.db_client import DatabaseClient

# Tick interval: how often the scheduler checks if it's time to run (seconds)
TICK_INTERVAL = 60


class SchedulerService:
    """Daemon-thread scheduler that triggers scraping and Supabase keepalive."""

    def __init__(self):
        self._db: DatabaseClient = None
        self._stop_event = threading.Event()
        self._main_thread: threading.Thread = None
        self._keepalive_thread: threading.Thread = None
        self._started = False

    def start(self):
        """Start the scheduler threads. Safe to call multiple times."""
        if self._started:
            return

        try:
            self._db = DatabaseClient()
            self._db.ensure_scheduler_config_table()
        except Exception as e:
            logger.error(f"Scheduler failed to init DB: {e}")
            return

        self._stop_event.clear()
        self._started = True

        # Main scheduler thread
        self._main_thread = threading.Thread(
            target=self._run_loop, name="scheduler-main", daemon=True
        )
        self._main_thread.start()
        logger.info("Scheduler service started")

        # Supabase keepalive thread (only if SUPABASE_URL is set)
        if os.getenv("SUPABASE_URL"):
            self._keepalive_thread = threading.Thread(
                target=self._keepalive_loop, name="scheduler-keepalive", daemon=True
            )
            self._keepalive_thread.start()
            logger.info("Supabase keepalive thread started")

    def stop(self):
        """Stop the scheduler threads."""
        self._stop_event.set()
        self._started = False
        logger.info("Scheduler service stopped")

    # ========== Main Scheduler Loop ==========

    def _run_loop(self):
        """Main loop: wakes every TICK_INTERVAL seconds, checks if it's time to scrape."""
        # On startup: check if we missed a scheduled run
        self._check_missed_run()

        while not self._stop_event.is_set():
            try:
                config = self._db.get_scheduler_config()
                if not config:
                    self._stop_event.wait(TICK_INTERVAL)
                    continue

                if not config.get('enabled', False):
                    self._stop_event.wait(TICK_INTERVAL)
                    continue

                # Ensure next_run_at is set
                next_run = config.get('next_run_at')
                if not next_run:
                    next_run_dt = self._compute_next_run(config)
                    self._db.update_scheduler_config({'next_run_at': next_run_dt.isoformat()})
                    logger.info(f"Scheduler: set initial next_run_at = {next_run_dt.isoformat()}")
                    self._stop_event.wait(TICK_INTERVAL)
                    continue

                # Parse next_run_at
                if isinstance(next_run, str):
                    next_run_dt = datetime.fromisoformat(next_run.replace('Z', '+00:00'))
                else:
                    next_run_dt = next_run
                if next_run_dt.tzinfo is None:
                    next_run_dt = next_run_dt.replace(tzinfo=timezone.utc)

                now = datetime.now(timezone.utc)

                if now >= next_run_dt:
                    # Time to run!
                    self._trigger_scrape(config)

            except Exception as e:
                logger.error(f"Scheduler loop error: {e}")

            self._stop_event.wait(TICK_INTERVAL)

    def _check_missed_run(self):
        """On startup, if next_run_at has passed and scheduler is enabled, fire immediately."""
        try:
            config = self._db.get_scheduler_config()
            if not config or not config.get('enabled'):
                return

            next_run = config.get('next_run_at')
            if not next_run:
                return

            if isinstance(next_run, str):
                next_run_dt = datetime.fromisoformat(next_run.replace('Z', '+00:00'))
            else:
                next_run_dt = next_run
            if next_run_dt.tzinfo is None:
                next_run_dt = next_run_dt.replace(tzinfo=timezone.utc)

            now = datetime.now(timezone.utc)
            if now >= next_run_dt:
                logger.info(f"Scheduler: missed run at {next_run_dt.isoformat()}, triggering now")
                self._trigger_scrape(config)
        except Exception as e:
            logger.error(f"Scheduler check_missed_run error: {e}")

    def _trigger_scrape(self, config: dict):
        """Start a scrape via ScraperManager, then advance next_run_at."""
        from api.manager import scraper_manager

        # Don't start if already running
        if scraper_manager.is_running:
            logger.info("Scheduler: scraper already running, will retry next tick")
            return

        # Parse source_types filter
        source_types = None
        st_raw = config.get('source_types')
        if st_raw:
            try:
                source_types = json.loads(st_raw) if isinstance(st_raw, str) else st_raw
            except (json.JSONDecodeError, TypeError):
                pass

        # If no specific source_types configured, use all enabled sources
        # This ensures the scheduler always uses the multi-source path
        if not source_types:
            from utils.config import config as app_config
            source_types = [
                s['source_type'] for s in app_config.sources
                if s.get('enabled', True)
            ]

        limit = config.get('scrape_limit', 500)
        dist_mode = config.get('distribution_mode', 'proportional')

        logger.info(f"Scheduler: triggering scrape (limit={limit}, mode={dist_mode}, sources={source_types})")

        success, msg = scraper_manager.start_scraping(
            engine="fast",
            scrape_limit=limit,
            source_types=source_types,
            distribution_mode=dist_mode,
            trigger_source="scheduler",
        )

        now = datetime.now(timezone.utc)

        if success:
            # Advance next_run_at
            next_run = self._compute_next_run(config, from_time=now)
            self._db.update_scheduler_config({
                'last_run_at': now.isoformat(),
                'next_run_at': next_run.isoformat(),
            })
            logger.info(f"Scheduler: scrape triggered. Next run at {next_run.isoformat()}")
        else:
            logger.warning(f"Scheduler: failed to start scrape: {msg}")

    def _compute_next_run(self, config: dict, from_time: datetime = None) -> datetime:
        """Compute the next run time based on schedule_type."""
        now = from_time or datetime.now(timezone.utc)

        schedule_type = config.get('schedule_type', 'daily')

        if schedule_type == 'interval':
            interval_hours = config.get('interval_hours', 24)
            return now + timedelta(hours=interval_hours)

        # daily — parse HH:MM
        daily_time = config.get('daily_time', '02:00')
        try:
            hour, minute = map(int, daily_time.split(':'))
        except (ValueError, AttributeError):
            hour, minute = 2, 0

        next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if next_run <= now:
            next_run += timedelta(days=1)

        return next_run

    # ========== Manual Trigger ==========

    def trigger_now(self) -> tuple:
        """Manually trigger a scheduled run. Returns (success, message)."""
        try:
            config = self._db.get_scheduler_config()
            if not config:
                return False, "Scheduler config not found"

            from api.manager import scraper_manager
            if scraper_manager.is_running:
                return False, "Scraper is already running"

            self._trigger_scrape(config)
            return True, "Scheduled run triggered"
        except Exception as e:
            return False, str(e)

    # ========== Supabase Keepalive ==========

    def _keepalive_loop(self):
        """Ping Supabase periodically to prevent free-tier project pause."""
        while not self._stop_event.is_set():
            try:
                config = self._db.get_scheduler_config()
                if not config or not config.get('supabase_keepalive', False):
                    self._stop_event.wait(300)  # Check again in 5 minutes
                    continue

                interval_hours = config.get('supabase_keepalive_interval_hours', 24)

                # Check if it's time to ping
                last_ping = config.get('last_keepalive_at')
                if last_ping:
                    if isinstance(last_ping, str):
                        last_ping_dt = datetime.fromisoformat(last_ping.replace('Z', '+00:00'))
                    else:
                        last_ping_dt = last_ping
                    if last_ping_dt.tzinfo is None:
                        last_ping_dt = last_ping_dt.replace(tzinfo=timezone.utc)

                    next_ping = last_ping_dt + timedelta(hours=interval_hours)
                    if datetime.now(timezone.utc) < next_ping:
                        self._stop_event.wait(300)
                        continue

                self._ping_supabase()

            except Exception as e:
                logger.error(f"Keepalive loop error: {e}")

            self._stop_event.wait(300)  # Check every 5 minutes

    def _ping_supabase(self):
        """Send a lightweight query to Supabase REST API to keep the project alive."""
        import requests

        supabase_url = os.getenv("SUPABASE_URL", "").rstrip("/")
        supabase_key = os.getenv("SUPABASE_KEY", "")

        if not supabase_url or not supabase_key:
            logger.warning("Keepalive: SUPABASE_URL or SUPABASE_KEY not set")
            return

        try:
            resp = requests.get(
                f"{supabase_url}/rest/v1/jurisdictions?select=code&limit=1",
                headers={
                    "apikey": supabase_key,
                    "Authorization": f"Bearer {supabase_key}",
                },
                timeout=15,
            )
            now = datetime.now(timezone.utc)
            self._db.update_scheduler_config({'last_keepalive_at': now.isoformat()})
            logger.info(f"Supabase keepalive ping: {resp.status_code}")
        except Exception as e:
            logger.warning(f"Supabase keepalive failed: {e}")

    # ========== Status ==========

    def get_status(self) -> dict:
        """Get scheduler status for the API."""
        try:
            if not self._db:
                return {"enabled": False, "started": False}

            config = self._db.get_scheduler_config()
            return {
                "started": self._started,
                **config,
                "has_supabase": bool(os.getenv("SUPABASE_URL")),
            }
        except Exception:
            return {"enabled": False, "started": self._started}


# Module-level singleton
scheduler_service = SchedulerService()
