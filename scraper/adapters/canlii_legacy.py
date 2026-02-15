"""
Legacy CanLII adapter — wraps existing CanLIIScraper and CanLIIPlaywrightScraper
behind the BaseSourceAdapter interface with zero changes to original code.
"""
import threading
from typing import List, Optional, Generator

from scraper.adapters import register_adapter
from scraper.adapters.base import BaseSourceAdapter, DocumentMetadata, DocumentContent
from utils.logger import logger


@register_adapter('canlii_legacy')
class CanLIILegacyAdapter(BaseSourceAdapter):
    """
    Wraps the existing CanLII scrapers (Fast/Deep) as a BaseSourceAdapter.
    This allows the legacy scrapers to run through the new multi-source manager.
    """

    def __init__(self, engine: str = "fast", url: str = "", jurisdiction: str = "ab",
                 headless: bool = True, cdp_url: str = None, **kwargs):
        self.engine = engine
        self.url = url
        self.jurisdiction = jurisdiction
        self.headless = headless
        self.cdp_url = cdp_url
        self._scraper = None

    def _get_scraper(self):
        """Lazy-init the underlying scraper."""
        if self._scraper is None:
            if self.engine == "deep":
                from scraper.canlii_playwright_scraper import CanLIIPlaywrightScraper
                self._scraper = CanLIIPlaywrightScraper(
                    use_checkpoint=True,
                    headless=self.headless,
                    cdp_url=self.cdp_url
                )
            else:
                from scraper.canlii_scraper import CanLIIScraper
                self._scraper = CanLIIScraper(use_checkpoint=True)
        return self._scraper

    def get_source_name(self) -> str:
        return f"CanLII ({self.engine})"

    def get_source_type(self) -> str:
        return "canlii_legacy"

    def get_jurisdiction(self) -> str:
        return self.jurisdiction

    def discover_documents(self, limit: Optional[int] = None) -> List[DocumentMetadata]:
        scraper = self._get_scraper()
        raw_list = scraper.fetch_statute_list(index_url=self.url)
        docs = []
        for item in raw_list:
            if limit and len(docs) >= limit:
                break
            docs.append(DocumentMetadata(
                source_url=item['url'],
                title=item.get('title', ''),
                citation=item.get('citation', ''),
                jurisdiction_code=self.jurisdiction,
                category="Legislation",
                is_active=item.get('is_active', True),
            ))
        return docs

    def fetch_document(self, doc_meta: DocumentMetadata) -> Optional[DocumentContent]:
        scraper = self._get_scraper()
        statute_info = {
            'url': doc_meta.source_url,
            'title': doc_meta.title,
            'citation': doc_meta.citation,
            'is_active': doc_meta.is_active,
        }
        context = {
            'jurisdiction_code': doc_meta.jurisdiction_code,
            'category': doc_meta.category,
        }
        success = scraper.scrape_statute(statute_info, context)
        if success:
            # The legacy scraper already saved to DB internally.
            # Return a minimal DocumentContent so the manager knows it succeeded.
            return DocumentContent(
                source_url=doc_meta.source_url,
                title=doc_meta.title,
                citation=doc_meta.citation,
                jurisdiction_code=doc_meta.jurisdiction_code,
                category=doc_meta.category,
                is_active=doc_meta.is_active,
            )
        return None

    def fetch_documents_batch(
        self,
        docs: List[DocumentMetadata],
        limit: Optional[int] = None,
        stop_event: Optional[threading.Event] = None,
    ) -> Generator[DocumentContent, None, None]:
        """
        For legacy adapter, delegate to the original scraper.run() which handles
        concurrency and checkpointing internally. We yield results post-hoc.
        """
        # For backward compatibility, use the default sequential approach
        yield from super().fetch_documents_batch(docs, limit, stop_event)
