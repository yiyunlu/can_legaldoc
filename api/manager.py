import threading
import time
from typing import Optional
from utils.config import config
from utils.logger import logger
from scraper.canlii_scraper import CanLIIScraper
from scraper.canlii_playwright_scraper import CanLIIPlaywrightScraper
from scraper.supabase_client import SupabaseClient

class ScraperManager:
    """
    管理爬虫的运行状态
    Manage the scraper execution state
    """
    def __init__(self):
        self.is_running = False
        self.current_target: Optional[str] = None
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
        self.active_scraper = None # Reference to currently running scraper
        
        # 启动时自动清理上一次遗留的 "running" 任务 (Startup Cleanup)
        self._cleanup_stale_jobs()

    def start_scraping(self, engine: str = "fast", headless: bool = True, cdp_url: Optional[str] = None, scrape_limit: int = 100):
        if self.is_running:
            return False, "Scraper is already running"
        
        self.engine_type = engine
        self.headless = headless
        self.cdp_url = cdp_url
        self.scrape_limit = scrape_limit
        # Reset stats for the new session
        self.stats = {
            'total': 0,
            'success': 0,
            'failed': 0,
            'skipped': 0
        }
        self.stop_event.clear()
        self.is_running = True
        self.message = f"Starting ({engine}, headless={headless}, cdp={cdp_url})..."
        self.thread = threading.Thread(target=self._run_loop)
        self.thread.start()
        return True, f"Scraper started with {engine} engine"

    def stop_scraping(self):
        if not self.is_running:
            return False, "Scraper is not running"
        
        self.stop_event.set()
        self.message = "Stopping..."
        # We don't join here to avoid blocking the API request
        return True, "Stop signal sent"

    def _cleanup_stale_jobs(self):
        """将由于系统重启导致的悬挂状态任务标记为失败 (Mark stale jobs as failed)"""
        try:
            # 找到所有状态为 'running' 的任务并标记为 'failed'
            res = self.db_client.client.table('scrape_jobs')\
                .update({
                    "status": "failed", 
                    "logs": "Interrupted: System restarted or script crashed",
                    "finished_at": "now()"
                })\
                .eq('status', 'running')\
                .execute()
            
            if res.data:
                logger.info(f"Cleaned up {len(res.data)} stale jobs from database.")
        except Exception as e:
            logger.warning(f"Failed to cleanup stale jobs: {e}")

    def _run_loop(self):
        """
        Background loop to process configured targets
        """
        try:
            self.message = "Running"
            # Choose engine
            if self.engine_type == "deep":
                logger.info("Initializing Playwright Engine (Deep Mode)")
                scraper = CanLIIPlaywrightScraper(use_checkpoint=True, headless=self.headless, cdp_url=self.cdp_url)
            else:
                logger.info("Initializing curl_cffi Engine (Fast Mode)")
                scraper = CanLIIScraper(use_checkpoint=True)
            
            self.active_scraper = scraper # Make it available for get_status
            
            # 1. 创建任务记录 (Create Job Record)
            try:
                job_res = self.db_client.client.table('scrape_jobs').insert({
                    "status": "running",
                    "items_scraped": 0,
                    "items_failed": 0,
                    "logs": f"Engine: {self.engine_type} | Message: Scraper loop started"
                }).execute()
                if job_res.data:
                    self.job_id = job_res.data[0]['id']
                    logger.info(f"Job record created: ID {self.job_id}")
            except Exception as eje:
                logger.warning(f"Failed to create job record: {eje}")

            # Load targets from config
            targets = config.targets
            
            # Global counter for newly scraped items across all targets
            session_newly_scraped = 0
            
            for target in targets:
                if self.stop_event.is_set():
                    break
                
                # Check if we reached global limit
                if self.scrape_limit and session_newly_scraped >= self.scrape_limit:
                    logger.info(f"Global scrape limit ({self.scrape_limit}) reached, skipping remaining targets.")
                    break
                
                self.current_target = target['name']
                # Create context for v3 schema
                context = self._prepare_target_context(target)
                
                logger.info(f"Manager switching to target: {self.current_target} ({target['url']}) with engine {self.engine_type}")
                
                # Calculate remaining limit for this target
                remaining_limit = self.scrape_limit - session_newly_scraped if self.scrape_limit else None
                
                # We need to track how many items this specific run scraped to update our session counter
                # The scraper instance accumulates its success/failed counts internally.
                # To get 'newly scraped' since last target, we check the delta.
                prev_scraped = scraper.stats['success'] + scraper.stats['failed']
                
                # Run scraper for this target
                scraper.run(
                    target_url=target['url'], 
                    context=context, 
                    stop_event=self.stop_event,
                    limit=remaining_limit
                )
                
                # Calculate newly scraped in this run
                curr_scraped = scraper.stats['success'] + scraper.stats['failed']
                session_newly_scraped += (curr_scraped - prev_scraped)
                
                # Sync stats to manager for UI (Accumulate instead of update)
                self.stats['success'] = scraper.stats['success']
                self.stats['failed'] = scraper.stats['failed']
                self.stats['skipped'] = scraper.stats['skipped']
                self.stats['total'] += scraper.stats.get('total', 0) 
                
                # Update job record with latest stats
                if self.job_id:
                    try:
                        self.db_client.client.table('scrape_jobs').update({
                            "items_scraped": self.stats.get('success', 0),
                            "items_failed": self.stats.get('failed', 0),
                            "logs": f"Engine: {self.engine_type} | Current: {self.current_target} | Last msg: {self.message}"
                        }).eq('id', self.job_id).execute()
                    except Exception as ese:
                        logger.warning(f"Failed to update job stats: {ese}")
                
            self.message = "Finished"
        except Exception as e:
            logger.error(f"Scraper Manager Error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self.message = f"Error: {e}"
        finally:
            # 2. 更新任务记录为完成/失败 (Update Job Record)
            if self.job_id:
                try:
                    status = "completed" if self.message == "Finished" else "failed"
                    self.db_client.client.table('scrape_jobs').update({
                        "status": status,
                        "items_scraped": self.stats.get('success', 0),
                        "items_failed": self.stats.get('failed', 0),
                        "logs": f"Engine: {self.engine_type} | Final Message: {self.message}",
                        "finished_at": "now()"
                    }).eq('id', self.job_id).execute()
                    logger.info(f"Job {self.job_id} marked as {status}")
                except Exception as eje:
                    logger.warning(f"Failed to update job record: {eje}")

            self.is_running = False
            self.current_target = None
            self.thread = None
            self.job_id = None
            self.active_scraper = None

    def _prepare_target_context(self, target: dict) -> dict:
        """
        Prepare metadata context for the scraper, ensuring jurisdiction and target exist in DB.
        """
        try:
            jur_code = target.get('province', 'ab').lower()
            category = target.get('type', 'Legislation')
            
            # Ensure jurisdiction exists
            self.db_client.client.table('jurisdictions').upsert({
                "code": jur_code,
                "name": jur_code.upper() # Fallback name
            }).execute()
            
            # Ensure target exists
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
                # Fallback: Upsert might not return data if no change, try select
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

    def get_status(self):
        # Base stats from manager (includes cumulative success/failed/skipped and 
        # total count of PREVIOUSLY FINISHED targets)
        stats = self.stats.copy()
        
        # If scraper is running, get live stats from the scraper instance
        if self.is_running and self.active_scraper:
            # We want to show the absolute totals (success + failed + skipped)
            # which are already cumulative in the scraper instance.
            scraper_stats = self.active_scraper.stats.copy()
            
            # The 'total' in scraper_stats is ONLY for the current target.
            # We need to add it to the manager's 'total' which represents finished targets.
            # However, since manager.stats['total'] only updates AFTER a target is done,
            # and stats.update would overwrite it, we manually add them.
            current_total = scraper_stats.pop('total', 0)
            stats.update(scraper_stats)
            stats['total'] += current_total
            
        return {
            "is_running": self.is_running,
            "current_target": self.current_target,
            "stats": stats,
            "message": self.message,
            "scrape_limit": self.scrape_limit
        }

scraper_manager = ScraperManager()
