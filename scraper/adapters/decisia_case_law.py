"""
Decisia case law adapter — fetches Canadian court decisions from Lexum Decisia
instances (e.g. Nova Scotia Courts at decisia.lexum.com/nsc).

Config-driven: the same adapter class works for any Decisia instance by passing
different base_url, court_code, court_name, and jurisdiction params.

Decisia URL structure (confirmed via live inspection):
  Instance root:  https://decisia.lexum.com/{instance}
  Sub-courts:     /{instance}/{sub_court}/en/{year}/nav_date.do?iframe=true
  Pagination:     ...?page=2&iframe=true   (25 per page, 404 past last)
  Decision page:  /{instance}/{sub_court}/en/item/{id}/index.do?iframe=true

The outer pages are Drupal wrappers that embed the real Decisia content via
iframe.  Appending ?iframe=true returns the iframe content directly — clean
server-rendered HTML suitable for requests + lxml.

License: MIT (code); upstream document licenses vary by court.
"""
import re
import time
import threading
import requests
from datetime import datetime
from typing import List, Optional, Generator
from lxml import html as lxml_html

from scraper.adapters import register_adapter
from scraper.adapters.base import BaseSourceAdapter, DocumentMetadata, DocumentContent
from utils.logger import logger


# Map citation prefixes to jurisdiction codes
CITATION_TO_JURISDICTION = {
    'NSSC': 'ns',
    'NSCA': 'ns',
    'NSPC': 'ns',
    'NSSM': 'ns',
    'NSFC': 'ns',
    'NSWCAT': 'ns',
    'NSUARB': 'ns',
    'NSLB': 'ns',
    'NSLRB': 'ns',
}

# Human-readable court names
COURT_NAMES = {
    'NSSC': 'Nova Scotia Supreme Court',
    'NSCA': 'Nova Scotia Court of Appeal',
    'NSPC': 'Nova Scotia Provincial Court',
    'NSSM': 'Nova Scotia Small Claims Court',
    'NSFC': 'Nova Scotia Family Court',
}

# Nova Scotia Decisia sub-courts (URL path segment -> citation prefix)
NS_SUB_COURTS = ['nssc', 'nsca', 'nspc', 'nssm', 'nsfc']


@register_adapter('ns_courts')
class DecisiaCaseLawAdapter(BaseSourceAdapter):
    """
    Config-driven adapter for Lexum Decisia court decision platforms.

    Parameters (via config.json 'params'):
        base_url:    Decisia instance root, e.g. "https://decisia.lexum.com/nsc"
        court_code:  Instance path segment, e.g. "nsc"
        sub_courts:  List of sub-court codes, e.g. ["nssc", "nsca", "nspc"]
                     If not provided, defaults to NS_SUB_COURTS.
        court_name:  Human-readable name, e.g. "Nova Scotia Courts"
        jurisdiction: Default jurisdiction code, e.g. "ns"
        start_year:  Earliest year to crawl (default: 2003)
    """

    def __init__(self, base_url="https://decisia.lexum.com/nsc",
                 court_code="nsc", sub_courts=None,
                 court_name="Nova Scotia Courts",
                 jurisdiction="ns", start_year=2003, **kwargs):
        self.base_url = base_url.rstrip('/')
        self.court_code = court_code
        self.sub_courts = sub_courts or NS_SUB_COURTS
        self.court_name = court_name
        self.jurisdiction = jurisdiction
        self.start_year = int(start_year)

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "CanadaLegalDataPlatform/1.0",
            "Accept": "text/html,application/xhtml+xml",
        })

    def get_source_name(self) -> str:
        return f"{self.court_name} (Decisia)"

    def get_source_type(self) -> str:
        return "ns_courts"

    def get_jurisdiction(self) -> str:
        return self.jurisdiction

    # ========== URL Construction ==========

    def _year_url(self, sub_court: str, year: int, page: int = 1) -> str:
        """Build iframe URL for a year listing page."""
        url = f"{self.base_url}/{sub_court}/en/{year}/nav_date.do?iframe=true"
        if page > 1:
            url = f"{self.base_url}/{sub_court}/en/{year}/nav_date.do?page={page}&iframe=true"
        return url

    def _item_url(self, sub_court: str, item_id: str) -> str:
        """Build canonical URL for a single decision (no iframe param)."""
        return f"{self.base_url}/{sub_court}/en/item/{item_id}/index.do"

    def _item_iframe_url(self, sub_court: str, item_id: str) -> str:
        """Build iframe URL for fetching decision content."""
        return f"{self.base_url}/{sub_court}/en/item/{item_id}/index.do?iframe=true"

    # ========== Parsing ==========

    def _parse_listing_page(self, html_text: str, sub_court: str) -> List[dict]:
        """
        Parse a Decisia year listing page and extract decision entries.

        Actual HTML structure (confirmed via live inspection):
          <h3>
            <span class="title">
              <a target="_parent" href="/{inst}/{sc}/en/item/{id}/index.do">Case Name</a>
            </span>
            - <span class="citation">2024 NSSC 100</span>
            - <span class="publicationDate">2024-12-31</span>
          </h3>

        Returns list of dicts: item_id, title, citation, date, url, sub_court.
        """
        entries = []
        try:
            tree = lxml_html.fromstring(html_text)
        except Exception as e:
            logger.warning(f"Decisia: failed to parse listing HTML: {e}")
            return entries

        for h3 in tree.xpath('//h3'):
            links = h3.xpath('.//a[@href]')
            if not links:
                continue

            link = links[0]
            href = link.get('href', '')

            # Extract item_id from href like /nsc/nssc/en/item/522810/index.do
            id_match = re.search(r'/item/(\d+)/index\.do', href)
            if not id_match:
                continue

            item_id = id_match.group(1)
            title = (link.text_content() or '').strip()

            # Extract sub-court from href (e.g. /nsc/nssc/en/... -> nssc)
            sc_match = re.search(r'/' + re.escape(self.court_code) + r'/(\w+)/en/', href)
            entry_sub_court = sc_match.group(1) if sc_match else sub_court

            # Use dedicated span elements for citation and date (reliable)
            citation_spans = h3.xpath('.//span[@class="citation"]')
            date_spans = h3.xpath('.//span[@class="publicationDate"]')

            citation = (citation_spans[0].text_content().strip()) if citation_spans else ''
            date = (date_spans[0].text_content().strip()) if date_spans else ''

            # Clean date — extract just YYYY-MM-DD if present
            date_match = re.search(r'(\d{4}-\d{2}-\d{2})', date)
            date = date_match.group(1) if date_match else date.strip()

            source_url = self._item_url(entry_sub_court, item_id)

            entries.append({
                'item_id': item_id,
                'title': title,
                'citation': citation,
                'date': date,
                'url': source_url,
                'sub_court': entry_sub_court,
            })

        return entries

    def _get_total_results(self, html_text: str) -> Optional[int]:
        """Extract total result count from header like '387&nbsp;result(s)'."""
        # Handle both regular space and &nbsp;
        match = re.search(r'(\d[\d,]*)(?:\s|&nbsp;)+result', html_text)
        if match:
            return int(match.group(1).replace(',', ''))
        return None

    def _resolve_jurisdiction_from_citation(self, citation: str) -> str:
        """Detect jurisdiction from citation, e.g. '2024 NSSC 100' -> 'ns'."""
        if not citation:
            return self.jurisdiction
        parts = citation.split()
        if len(parts) >= 2:
            court_code = parts[1].upper()
            if court_code in CITATION_TO_JURISDICTION:
                return CITATION_TO_JURISDICTION[court_code]
        return self.jurisdiction

    def _court_from_citation(self, citation: str) -> str:
        """Extract court code from citation, e.g. '2024 NSSC 100' -> 'NSSC'."""
        if not citation:
            return ''
        parts = citation.split()
        if len(parts) >= 2:
            return parts[1].upper()
        return ''

    # ========== Discovery ==========

    def discover_documents(self, limit: Optional[int] = None) -> List[DocumentMetadata]:
        """
        Discover decisions by iterating sub-courts and year listing pages.

        For each sub-court (e.g. nssc, nsca, nspc), crawls from current year
        down to start_year, following pagination within each year.
        Rate limited to 0.3s between page requests.
        """
        current_year = datetime.now().year
        all_docs = []
        total_pages_fetched = 0

        logger.info(f"Decisia [{self.court_code}]: discovering from {len(self.sub_courts)} sub-courts, "
                     f"years {self.start_year}-{current_year}")

        for sub_court in self.sub_courts:
            if limit is not None and len(all_docs) >= limit:
                break

            sc_count = 0
            logger.info(f"Decisia [{self.court_code}]: scanning sub-court '{sub_court}'")

            for year in range(current_year, self.start_year - 1, -1):
                if limit is not None and len(all_docs) >= limit:
                    break

                page = 1

                while True:
                    if limit is not None and len(all_docs) >= limit:
                        break

                    url = self._year_url(sub_court, year, page)

                    try:
                        resp = self._request_with_retry(self.session, url, timeout=30)
                        if resp.status_code == 404:
                            break
                        resp.raise_for_status()
                    except Exception as e:
                        logger.warning(f"Decisia: failed {url}: {e}")
                        break

                    html_text = resp.text
                    total_pages_fetched += 1

                    # On first page, log total
                    if page == 1:
                        total = self._get_total_results(html_text)
                        if total is not None:
                            logger.info(f"  {sub_court.upper()} {year}: {total} result(s)")
                        else:
                            # Check if the page has any content at all
                            if '<h3' not in html_text:
                                break

                    entries = self._parse_listing_page(html_text, sub_court)
                    if not entries:
                        break

                    for entry in entries:
                        if limit is not None and len(all_docs) >= limit:
                            break

                        court_code = self._court_from_citation(entry['citation'])
                        court_name = COURT_NAMES.get(court_code, court_code or self.court_name)

                        doc = DocumentMetadata(
                            source_url=entry['url'],
                            title=entry['title'] or entry['citation'],
                            citation=entry['citation'],
                            jurisdiction_code=self._resolve_jurisdiction_from_citation(entry['citation']),
                            category="Case Law",
                            document_type="case_law",
                            is_active=True,
                            metadata={
                                'court': court_code,
                                'court_name': court_name,
                                'date': entry['date'],
                                'item_id': entry['item_id'],
                                'sub_court': entry['sub_court'],
                                'decisia_instance': self.court_code,
                            },
                        )
                        all_docs.append(doc)
                        sc_count += 1

                    page += 1
                    time.sleep(0.3)

            if sc_count > 0:
                logger.info(f"  {sub_court.upper()}: {sc_count} decisions total")

        logger.info(f"Decisia [{self.court_code}]: discovered {len(all_docs):,} decisions "
                     f"across {total_pages_fetched} pages")
        return all_docs

    # ========== Fetch ==========

    def fetch_document(self, doc_meta: DocumentMetadata) -> Optional[DocumentContent]:
        """
        Fetch full decision text from a Decisia item page.

        Uses ?iframe=true to get the inner content directly.
        Extracts text from div.documentcontent (primary Decisia content class).
        """
        url = doc_meta.source_url
        if not url:
            return None

        # Build iframe URL for fetching content
        iframe_url = url
        if '?' not in iframe_url:
            iframe_url += '?iframe=true'
        elif 'iframe=true' not in iframe_url:
            iframe_url += '&iframe=true'

        try:
            resp = self._request_with_retry(self.session, iframe_url, timeout=30)
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"Decisia: failed to fetch {iframe_url}: {e}")
            return None

        html_text = resp.text

        content_html = ''
        content_text = ''
        try:
            tree = lxml_html.fromstring(html_text)

            # Try content selectors in order of specificity
            content_el = None
            for selector in [
                '//div[contains(@class, "documentcontent")]',
                '//div[contains(@class, "decision-content")]',
                '//div[contains(@class, "document-content")]',
                '//div[@id="decision"]',
                '//div[@id="document"]',
                '//article',
                '//div[@role="main"]',
            ]:
                els = tree.xpath(selector)
                if els:
                    content_el = els[0]
                    break

            if content_el is not None:
                content_html = lxml_html.tostring(content_el, encoding='unicode', pretty_print=True)
                content_text = content_el.text_content().strip()
            else:
                # Fallback: extract body text, stripping nav/header/footer
                body = tree.xpath('//body')
                if body:
                    for tag in body[0].xpath('.//nav | .//header | .//footer | .//script | .//style | .//noscript'):
                        tag.getparent().remove(tag)
                    content_text = body[0].text_content().strip()
                    content_html = lxml_html.tostring(body[0], encoding='unicode', pretty_print=True)

        except Exception as e:
            logger.warning(f"Decisia: HTML parsing failed for {url}: {e}")
            content_html = html_text
            content_text = re.sub(r'<[^>]+>', ' ', html_text)
            content_text = re.sub(r'\s+', ' ', content_text).strip()

        if not content_text and not content_html:
            logger.debug(f"Decisia: no content from {url}")
            return None

        time.sleep(0.5)  # rate limit

        return DocumentContent(
            source_url=url,  # Store canonical URL (without iframe param)
            title=doc_meta.title,
            citation=doc_meta.citation,
            content_html=content_html,
            content_text=content_text,
            jurisdiction_code=doc_meta.jurisdiction_code,
            category="Case Law",
            document_type="case_law",
            is_active=True,
            metadata=doc_meta.metadata,
        )

    def fetch_documents_batch(
        self,
        docs: List[DocumentMetadata],
        limit: Optional[int] = None,
        stop_event: Optional[threading.Event] = None,
    ) -> Generator[DocumentContent, None, None]:
        """
        Batch fetch decisions with progress logging.
        Sequential with 0.5s rate limiting per document.
        """
        count = 0
        failed = 0

        for doc in docs:
            if limit is not None and count >= limit:
                break
            if stop_event and stop_event.is_set():
                break

            result = self.fetch_document(doc)
            if result:
                yield result
                count += 1
            else:
                failed += 1

            if (count + failed) % 50 == 0 and (count + failed) > 0:
                logger.info(f"Decisia [{self.court_code}] batch: {count} ok, {failed} fail")

        logger.info(f"Decisia [{self.court_code}] batch complete: {count} ok, {failed} fail")
