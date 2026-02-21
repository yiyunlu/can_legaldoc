import threading
import time
from typing import Dict, Optional, List
from utils.config import config
from utils.logger import logger
from scraper.db_client import DatabaseClient
from utils.checkpoint import Checkpoint

# Default estimated doc counts per source (used for proportional distribution)
DEFAULT_ESTIMATES = {
    'justice_canada_xml': 5795,
    'bc_laws_api': 882,
    'alberta_kings_printer': 1415,
    'a2aj_case_law': 184565,
    'canlii_legacy': 1000,
}


class ScraperManager:
    """
    管理爬虫的运行状态 — supports both legacy CanLII engines and new multi-source adapters.
    """
    def __init__(self):
        self.is_running = False
        self.current_target: Optional[str] = None
        self.current_source: Optional[str] = None
        self.stats = {
            'total': 0,
            'success': 0,
            'failed': 0,
            'skipped': 0
        }
        self.stop_event = threading.Event()
        self.message = "Ready"
        self.engine_type = "fast"
        self.headless = True
        self.cdp_url: Optional[str] = None
        self.scrape_limit: int = 100
        self.job_id: Optional[str] = None
        self.db_client = DatabaseClient()
        self.active_scraper = None
        self.checkpoint = Checkpoint()
        # Multi-source fields
        self.source_type_filter: Optional[str] = None
        self.source_types_filter: Optional[List[str]] = None
        self.distribution_mode: str = "proportional"
        self.source_estimates: Optional[Dict[str, int]] = None

        self.trigger_source: str = "manual"
        self.db_client.cleanup_stale_jobs()

    def start_scraping(self, engine: str = "fast", headless: bool = True,
                       cdp_url: Optional[str] = None, scrape_limit: int = 100,
                       source_type: Optional[str] = None,
                       source_types: Optional[List[str]] = None,
                       distribution_mode: Optional[str] = "proportional",
                       source_estimates: Optional[Dict[str, int]] = None,
                       trigger_source: str = "manual"):
        if self.is_running:
            return False, "Scraper is already running"

        self.engine_type = engine
        self.headless = headless
        self.cdp_url = cdp_url
        self.scrape_limit = scrape_limit
        self.source_type_filter = source_type
        self.source_types_filter = source_types
        self.distribution_mode = distribution_mode or "proportional"
        self.source_estimates = source_estimates
        self.trigger_source = trigger_source
        self.stats = {'total': 0, 'success': 0, 'failed': 0, 'skipped': 0}
        self.stop_event.clear()
        self.is_running = True

        # Decide which run loop to use
        # Default to multi-source when config.sources exist (v5.x standard)
        use_multi = bool(source_type or source_types or config.sources)
        if use_multi:
            self.message = f"Starting multi-source ({source_type or source_types or 'all'})..."
            self.thread = threading.Thread(target=self._run_multi_source)
        else:
            self.message = f"Starting ({engine}, headless={headless})..."
            self.thread = threading.Thread(target=self._run_legacy_loop)

        self.thread.start()
        return True, f"Scraper started"

    def stop_scraping(self):
        if not self.is_running:
            return False, "Scraper is not running"
        self.stop_event.set()
        self.message = "Stopping..."
        return True, "Stop signal sent"

    # ========== Limit Distribution ==========

    def _calculate_source_limits(self, sources: list) -> Dict[str, Optional[int]]:
        """Calculate per-source limits based on distribution_mode.

        Modes:
          - sequential: no per-source limit, global limit only (old behavior)
          - equal: global limit split equally among sources
          - proportional: balanced split using log-scaled estimates so large
            sources don't monopolize the limit (e.g. 184K case law vs 882 BC laws)
        """
        if not self.scrape_limit:
            return {s['source_type']: None for s in sources}

        mode = self.distribution_mode
        num_sources = len(sources)

        if mode == "sequential" or num_sources <= 1:
            # Old behavior: each source gets the full remaining limit
            return {s['source_type']: None for s in sources}

        if mode == "equal":
            per_source = max(1, self.scrape_limit // num_sources)
            limits = {s['source_type']: per_source for s in sources}
            # Give leftover to first source
            leftover = self.scrape_limit - (per_source * num_sources)
            if leftover > 0:
                limits[sources[0]['source_type']] += leftover
            logger.info(f"Equal distribution: {limits}")
            return limits

        # proportional (default) — uses log-scale to balance large vs small sources
        import math
        estimates = self.source_estimates or DEFAULT_ESTIMATES
        source_types = [s['source_type'] for s in sources]
        est_totals = {st: estimates.get(st, 1000) for st in source_types}

        # Log-scale the estimates to prevent one huge source from dominating
        # log(1000)=6.9, log(5000)=8.5, log(185000)=12.1 — much more balanced
        log_weights = {st: math.log(max(est, 10)) for st, est in est_totals.items()}
        total_weight = sum(log_weights.values())

        if total_weight == 0:
            total_weight = len(source_types)

        limits = {}
        allocated = 0
        for i, st in enumerate(source_types):
            if i == len(source_types) - 1:
                limits[st] = max(1, self.scrape_limit - allocated)
            else:
                share = max(1, int(self.scrape_limit * log_weights[st] / total_weight))
                limits[st] = share
                allocated += share

        logger.info(f"Proportional distribution (log-scaled): {limits}")
        return limits

    # ========== Multi-Source Run Loop ==========

    def _run_multi_source(self):
        """Run adapters from the sources config."""
        try:
            self.message = "Running (multi-source)"
            from scraper.adapters import get_adapter

            # Create job record
            mode_label = f"[{self.trigger_source}] multi-source ({self.distribution_mode})"
            self.job_id = self.db_client.create_job(mode_label)

            # Filter sources
            sources = config.sources
            if self.source_type_filter:
                sources = [s for s in sources if s['source_type'] == self.source_type_filter]
            elif self.source_types_filter:
                sources = [s for s in sources if s['source_type'] in self.source_types_filter]

            # Only run enabled sources
            sources = [s for s in sources if s.get('enabled', True)]

            if not sources:
                self.message = "No enabled sources found"
                logger.warning("No enabled sources matching filter")
                return

            # Calculate per-source limits
            source_limits = self._calculate_source_limits(sources)
            session_total = 0

            for source_cfg in sources:
                if self.stop_event.is_set():
                    break
                if self.scrape_limit and session_total >= self.scrape_limit:
                    logger.info(f"Global limit ({self.scrape_limit}) reached.")
                    break

                source_type = source_cfg['source_type']
                per_source_limit = source_limits.get(source_type)
                self.current_source = source_cfg.get('name', source_type)
                self.current_target = self.current_source
                logger.info(f"=== Starting source: {self.current_source} ({source_type}) | limit={per_source_limit} ===")

                try:
                    adapter = get_adapter(source_type, **source_cfg.get('params', {}))
                except Exception as e:
                    logger.error(f"Failed to create adapter for {source_type}: {e}")
                    continue

                # Determine discovery limit
                if per_source_limit is not None:
                    discover_limit = per_source_limit
                elif self.scrape_limit:
                    discover_limit = self.scrape_limit - session_total
                else:
                    discover_limit = None

                try:
                    doc_list = adapter.discover_documents(limit=discover_limit)
                    logger.info(f"Discovered {len(doc_list)} documents from {source_type}")
                except Exception as e:
                    logger.error(f"Discovery failed for {source_type}: {e}")
                    continue

                self.stats['total'] += len(doc_list)

                # Filter already-checkpointed URLs
                doc_urls = [d.source_url for d in doc_list]
                already_scraped = self.checkpoint.filter_scraped_urls(doc_urls)
                to_fetch = [d for d in doc_list if d.source_url not in already_scraped]
                skipped = len(doc_list) - len(to_fetch)
                self.stats['skipped'] += skipped
                if skipped:
                    logger.info(f"Skipped {skipped} already-processed documents")

                # Determine fetch limit
                fetch_limit = per_source_limit if per_source_limit is not None else (
                    (self.scrape_limit - session_total) if self.scrape_limit else None
                )
                source_fetched = 0

                # Fetch documents
                for doc_content in adapter.fetch_documents_batch(
                    to_fetch, limit=fetch_limit, stop_event=self.stop_event
                ):
                    if self.stop_event.is_set():
                        break
                    if self.scrape_limit and session_total >= self.scrape_limit:
                        break

                    # Save to database
                    upsert_data = doc_content.to_upsert_dict(source_type=source_type)
                    self.db_client.ensure_jurisdiction(doc_content.jurisdiction_code)

                    try:
                        success = self.db_client.upsert_document_v3(upsert_data)
                        if success:
                            self.stats['success'] += 1
                            self.checkpoint.add(doc_content.source_url)
                            session_total += 1
                            source_fetched += 1
                        else:
                            self.stats['failed'] += 1
                    except Exception as e:
                        logger.error(f"DB save failed: {e}")
                        self.stats['failed'] += 1

                    if (self.stats['success'] + self.stats['failed']) % 50 == 0:
                        self._update_job_stats()

                self._update_job_stats()
                logger.info(f"=== Finished source: {self.current_source} | fetched={source_fetched} ===")

            self.message = "Finished"
        except Exception as e:
            logger.error(f"Multi-source error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self.message = f"Error: {e}"
        finally:
            self._finalize_job()
            self.is_running = False
            self.current_target = None
            self.current_source = None
            self.thread = None
            self.job_id = None

    # ========== Legacy CanLII Run Loop ==========

    def _run_legacy_loop(self):
        """Original CanLII-only run loop (backward compatible)."""
        try:
            self.message = "Running"
            if self.engine_type == "deep":
                from scraper.canlii_playwright_scraper import CanLIIPlaywrightScraper
                logger.info("Initializing Playwright Engine (Deep Mode)")
                scraper = CanLIIPlaywrightScraper(use_checkpoint=True, headless=self.headless, cdp_url=self.cdp_url)
            else:
                from scraper.canlii_scraper import CanLIIScraper
                logger.info("Initializing curl_cffi Engine (Fast Mode)")
                scraper = CanLIIScraper(use_checkpoint=True)

            self.active_scraper = scraper
            self.job_id = self.db_client.create_job(f"[{self.trigger_source}] {self.engine_type}")

            targets = config.targets
            session_newly_scraped = 0

            for target in targets:
                if self.stop_event.is_set():
                    break
                if self.scrape_limit and session_newly_scraped >= self.scrape_limit:
                    logger.info(f"Global scrape limit ({self.scrape_limit}) reached.")
                    break

                self.current_target = target['name']
                context = self._prepare_target_context(target)
                logger.info(f"Manager switching to target: {self.current_target} ({target['url']})")

                remaining_limit = self.scrape_limit - session_newly_scraped if self.scrape_limit else None
                prev_scraped = scraper.stats['success'] + scraper.stats['failed']

                scraper.run(
                    target_url=target['url'],
                    context=context,
                    stop_event=self.stop_event,
                    limit=remaining_limit
                )

                curr_scraped = scraper.stats['success'] + scraper.stats['failed']
                session_newly_scraped += (curr_scraped - prev_scraped)

                self.stats['success'] = scraper.stats['success']
                self.stats['failed'] = scraper.stats['failed']
                self.stats['skipped'] = scraper.stats['skipped']
                self.stats['total'] += scraper.stats.get('total', 0)

                self._update_job_stats()

            self.message = "Finished"
        except Exception as e:
            logger.error(f"Scraper Manager Error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self.message = f"Error: {e}"
        finally:
            self._finalize_job()
            self.is_running = False
            self.current_target = None
            self.current_source = None
            self.thread = None
            self.job_id = None
            self.active_scraper = None

    def _prepare_target_context(self, target: dict) -> dict:
        """Prepare metadata context for legacy CanLII scraper."""
        try:
            jur_code = target.get('province', 'ab').lower()
            category = target.get('type', 'Legislation')

            self.db_client.ensure_jurisdiction(jur_code)

            target_entry = {
                "jurisdiction_code": jur_code,
                "category": category,
                "name": target['name'],
                "url": target['url']
            }
            target_id = self.db_client.upsert_scrape_target(target_entry)

            return {
                "jurisdiction_code": jur_code,
                "category": category,
                "target_id": target_id
            }
        except Exception as e:
            logger.error(f"Failed to prepare target context: {e}")
            return {}

    # ========== Job Tracking Helpers ==========

    def _update_job_stats(self):
        if not self.job_id:
            return
        logs = f"Source: {self.current_source or self.engine_type} | Target: {self.current_target} | Msg: {self.message}"
        self.db_client.update_job(
            self.job_id,
            items_scraped=self.stats.get('success', 0),
            items_failed=self.stats.get('failed', 0),
            logs=logs
        )

    def _finalize_job(self):
        if not self.job_id:
            return
        status = "completed" if self.message == "Finished" else "failed"
        logs = f"[{self.trigger_source}] Final: {self.message} | success={self.stats['success']} failed={self.stats['failed']} skipped={self.stats['skipped']}"
        self.db_client.finalize_job(
            self.job_id,
            status=status,
            items_scraped=self.stats.get('success', 0),
            items_failed=self.stats.get('failed', 0),
            logs=logs
        )

    # ========== Status ==========

    def get_status(self):
        stats = self.stats.copy()

        if self.is_running and self.active_scraper:
            scraper_stats = self.active_scraper.stats.copy()
            current_total = scraper_stats.pop('total', 0)
            stats.update(scraper_stats)
            stats['total'] += current_total

        # Include lightweight scheduler summary
        scheduler_info = None
        try:
            sched_cfg = self.db_client.get_scheduler_config()
            if sched_cfg:
                scheduler_info = {
                    "enabled": sched_cfg.get("enabled", False),
                    "next_run_at": sched_cfg.get("next_run_at"),
                }
        except Exception:
            pass

        return {
            "is_running": self.is_running,
            "current_target": self.current_target,
            "current_source": self.current_source,
            "stats": stats,
            "message": self.message,
            "scrape_limit": self.scrape_limit,
            "scheduler": scheduler_info,
        }

scraper_manager = ScraperManager()
