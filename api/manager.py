import threading
import time
from typing import Optional, List
from utils.config import config
from utils.logger import logger
from scraper.supabase_client import SupabaseClient
from utils.checkpoint import Checkpoint

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
        self.job_id: Optional[int] = None
        self.db_client = SupabaseClient()
        self.active_scraper = None
        self.checkpoint = Checkpoint()
        # Multi-source fields
        self.source_type_filter: Optional[str] = None
        self.source_types_filter: Optional[List[str]] = None

        self._cleanup_stale_jobs()

    def start_scraping(self, engine: str = "fast", headless: bool = True,
                       cdp_url: Optional[str] = None, scrape_limit: int = 100,
                       source_type: Optional[str] = None,
                       source_types: Optional[List[str]] = None):
        if self.is_running:
            return False, "Scraper is already running"

        self.engine_type = engine
        self.headless = headless
        self.cdp_url = cdp_url
        self.scrape_limit = scrape_limit
        self.source_type_filter = source_type
        self.source_types_filter = source_types
        self.stats = {'total': 0, 'success': 0, 'failed': 0, 'skipped': 0}
        self.stop_event.clear()
        self.is_running = True

        # Decide which run loop to use
        if source_type or source_types:
            self.message = f"Starting multi-source ({source_type or source_types})..."
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

    def _cleanup_stale_jobs(self):
        """Mark stale 'running' jobs as failed on startup."""
        try:
            res = self.db_client.client.table('scrape_jobs')\
                .update({
                    "status": "failed",
                    "logs": "Interrupted: System restarted or script crashed",
                    "finished_at": "now()"
                })\
                .eq('status', 'running')\
                .execute()
            if res.data:
                logger.info(f"Cleaned up {len(res.data)} stale jobs.")
        except Exception as e:
            logger.warning(f"Failed to cleanup stale jobs: {e}")

    # ========== Multi-Source Run Loop ==========

    def _run_multi_source(self):
        """Run adapters from the sources config."""
        try:
            self.message = "Running (multi-source)"
            from scraper.adapters import get_adapter

            # Create job record
            self._create_job_record("multi-source")

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

            session_total = 0

            for source_cfg in sources:
                if self.stop_event.is_set():
                    break
                if self.scrape_limit and session_total >= self.scrape_limit:
                    logger.info(f"Global limit ({self.scrape_limit}) reached.")
                    break

                source_type = source_cfg['source_type']
                self.current_source = source_cfg.get('name', source_type)
                self.current_target = self.current_source
                logger.info(f"=== Starting source: {self.current_source} ({source_type}) ===")

                try:
                    adapter = get_adapter(source_type, **source_cfg.get('params', {}))
                except Exception as e:
                    logger.error(f"Failed to create adapter for {source_type}: {e}")
                    continue

                # Discover
                remaining = (self.scrape_limit - session_total) if self.scrape_limit else None
                try:
                    doc_list = adapter.discover_documents(limit=remaining)
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

                # Fetch documents
                for doc_content in adapter.fetch_documents_batch(
                    to_fetch, limit=remaining, stop_event=self.stop_event
                ):
                    if self.stop_event.is_set():
                        break

                    # Save to database
                    upsert_data = doc_content.to_upsert_dict(source_type=source_type)
                    self._ensure_jurisdiction(doc_content.jurisdiction_code)

                    try:
                        success = self.db_client.upsert_document_v3(upsert_data)
                        if success:
                            self.stats['success'] += 1
                            self.checkpoint.add(doc_content.source_url)
                            session_total += 1
                        else:
                            self.stats['failed'] += 1
                    except Exception as e:
                        logger.error(f"DB save failed: {e}")
                        self.stats['failed'] += 1

                    if (self.stats['success'] + self.stats['failed']) % 50 == 0:
                        self._update_job_stats()

                self._update_job_stats()
                logger.info(f"=== Finished source: {self.current_source} ===")

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

    def _ensure_jurisdiction(self, jur_code: str):
        """Ensure jurisdiction exists in DB."""
        if not jur_code:
            return
        try:
            self.db_client.client.table('jurisdictions').upsert({
                "code": jur_code, "name": jur_code.upper()
            }).execute()
        except Exception:
            pass

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
            self._create_job_record(self.engine_type)

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

            self.db_client.client.table('jurisdictions').upsert({
                "code": jur_code, "name": jur_code.upper()
            }).execute()

            target_entry = {
                "jurisdiction_code": jur_code,
                "category": category,
                "name": target['name'],
                "url": target['url']
            }
            res = self.db_client.client.table('scrape_targets').upsert(
                target_entry, on_conflict='url'
            ).execute()

            target_id = None
            if res.data:
                target_id = res.data[0]['id']
            else:
                res_sel = self.db_client.client.table('scrape_targets')\
                    .select('id').eq('url', target['url']).execute()
                if res_sel.data:
                    target_id = res_sel.data[0]['id']

            return {
                "jurisdiction_code": jur_code,
                "category": category,
                "target_id": target_id
            }
        except Exception as e:
            logger.error(f"Failed to prepare target context: {e}")
            return {}

    # ========== Job Tracking Helpers ==========

    def _create_job_record(self, engine_label: str):
        try:
            job_res = self.db_client.client.table('scrape_jobs').insert({
                "status": "running",
                "items_scraped": 0,
                "items_failed": 0,
                "logs": f"Engine: {engine_label} | Message: Started"
            }).execute()
            if job_res.data:
                self.job_id = job_res.data[0]['id']
                logger.info(f"Job record created: {self.job_id}")
        except Exception as e:
            logger.warning(f"Failed to create job record: {e}")

    def _update_job_stats(self):
        if not self.job_id:
            return
        try:
            self.db_client.client.table('scrape_jobs').update({
                "items_scraped": self.stats.get('success', 0),
                "items_failed": self.stats.get('failed', 0),
                "logs": f"Source: {self.current_source or self.engine_type} | Target: {self.current_target} | Msg: {self.message}"
            }).eq('id', self.job_id).execute()
        except Exception as e:
            logger.warning(f"Failed to update job stats: {e}")

    def _finalize_job(self):
        if not self.job_id:
            return
        try:
            status = "completed" if self.message == "Finished" else "failed"
            self.db_client.client.table('scrape_jobs').update({
                "status": status,
                "items_scraped": self.stats.get('success', 0),
                "items_failed": self.stats.get('failed', 0),
                "logs": f"Final: {self.message} | success={self.stats['success']} failed={self.stats['failed']} skipped={self.stats['skipped']}",
                "finished_at": "now()"
            }).eq('id', self.job_id).execute()
            logger.info(f"Job {self.job_id} marked as {status}")
        except Exception as e:
            logger.warning(f"Failed to finalize job: {e}")

    # ========== Status ==========

    def get_status(self):
        stats = self.stats.copy()

        if self.is_running and self.active_scraper:
            scraper_stats = self.active_scraper.stats.copy()
            current_total = scraper_stats.pop('total', 0)
            stats.update(scraper_stats)
            stats['total'] += current_total

        return {
            "is_running": self.is_running,
            "current_target": self.current_target,
            "current_source": self.current_source,
            "stats": stats,
            "message": self.message,
            "scrape_limit": self.scrape_limit
        }

scraper_manager = ScraperManager()
