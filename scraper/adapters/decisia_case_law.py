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

Anti-bot resilience:
  - Realistic browser User-Agent (rotated)
  - Longer delays between requests (1-2s discovery, 2-3s fetch)
  - CAPTCHA detection with graceful abort
  - Optional proxy support via config params

License: MIT (code); upstream document licenses vary by court.
"""
import re
import time
import random
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

# Realistic browser User-Agents (Chrome on different platforms)
_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
]


class CaptchaBlockError(Exception):
    """Raised when Decisia returns a CAPTCHA challenge instead of content."""
    pass


@register_adapter('ns_courts')
class DecisiaCaseLawAdapter(BaseSourceAdapter):
    """
    Config-driven adapter for Lexum Decisia court decision platforms.

    Parameters (via config.json 'params'):
        base_url:      Decisia instance root, e.g. "https://decisia.lexum.com/nsc"
        court_code:    Instance path segment, e.g. "nsc"
        sub_courts:    List of sub-court codes, e.g. ["nssc", "nsca", "nspc"]
                       If not provided, defaults to NS_SUB_COURTS.
        court_name:    Human-readable name, e.g. "Nova Scotia Courts"
        jurisdiction:  Default jurisdiction code, e.g. "ns"
        start_year:    Earliest year to crawl (default: 2003)
        proxy_url:     Optional HTTP/SOCKS proxy URL for requests
        delay_range:   Optional [min, max] seconds between listing requests (default: [1.0, 2.0])
        fetch_delay:   Optional [min, max] seconds between document fetches (default: [2.0, 3.5])
    """

    def __init__(self, base_url="https://decisia.lexum.com/nsc",
                 court_code="nsc", sub_courts=None,
                 court_name="Nova Scotia Courts",
                 jurisdiction="ns", start_year=2003,
                 proxy_url=None, delay_range=None, fetch_delay=None,
                 **kwargs):
        self.base_url = base_url.rstrip('/')
        self.court_code = court_code
        self.sub_courts = sub_courts or NS_SUB_COURTS
        self.court_name = court_name
        self.jurisdiction = jurisdiction
        self.start_year = int(start_year)
        self.proxy_url = proxy_url
        self.delay_range = delay_range or [1.0, 2.0]
        self.fetch_delay = fetch_delay or [2.0, 3.5]
        self._captcha_detected = False

        self.session = requests.Session()

        # Use realistic browser headers
        ua = random.choice(_USER_AGENTS)
        self.session.headers.update({
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-CA,en-US;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0",
        })

        # Configure proxy if provided
        if self.proxy_url:
            self.session.proxies = {
                "http": self.proxy_url,
                "https": self.proxy_url,
            }
            logger.info(f"Decisia [{court_code}]: using proxy {self.proxy_url}")

    def get_source_name(self) -> str:
        return f"{self.court_name} (Decisia)"

    def get_source_type(self) -> str:
        return "ns_courts"

    def get_jurisdiction(self) -> str:
        return self.jurisdiction

    # ========== Anti-bot helpers ==========

    def _check_captcha(self, resp: requests.Response) -> bool:
        """Detect if a Decisia response is a CAPTCHA challenge instead of real content."""
        if resp.status_code == 403:
            body = resp.text[:2000].lower()
            if 'captcha' in body or 'jcaptcha' in body or 'challenge' in body:
                return True
        return False

    def _delay(self, delay_range: list):
        """Sleep a random duration within the given [min, max] range."""
        lo, hi = delay_range[0], delay_range[1]
        time.sleep(random.uniform(lo, hi))

    def _safe_request(self, url: str, context: str = "", timeout: int = 30) -> Optional[requests.Response]:
        """
        Make a request with CAPTCHA detection.  Returns Response or None.
        Raises CaptchaBlockError if server is returning CAPTCHA challenges.
        """
        if self._captcha_detected:
            return None

        try:
            resp = self._request_with_retry(self.session, url, timeout=timeout)

            if self._check_captcha(resp):
                self._captcha_detected = True
                logger.error(
                    f"Decisia [{self.court_code}]: CAPTCHA block detected! "
                    f"Server IP is flagged by Lexum anti-bot system. "
                    f"URL: {url}  |  Try again later or configure proxy_url."
                )
                raise CaptchaBlockError(
                    f"Decisia CAPTCHA block on {self.court_code}. "
                    f"Configure proxy_url in config.json params to bypass."
                )

            if resp.status_code == 404:
                return resp  # let caller handle 404 as "no data"

            resp.raise_for_status()
            return resp

        except CaptchaBlockError:
            raise
        except Exception as e:
            logger.warning(f"Decisia: {context} failed {url}: {e}")
            return None

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

        Rate limited with randomised delays (default 1-2s between listing pages)
        to avoid triggering Lexum's anti-bot CAPTCHA system.
        """
        current_year = datetime.now().year
        all_docs = []
        total_pages_fetched = 0
        self._captcha_detected = False

        logger.info(f"Decisia [{self.court_code}]: discovering from {len(self.sub_courts)} sub-courts, "
                     f"years {self.start_year}-{current_year}"
                     f"{' via proxy' if self.proxy_url else ''}")

        for sub_court in self.sub_courts:
            if limit is not None and len(all_docs) >= limit:
                break
            if self._captcha_detected:
                break

            sc_count = 0
            logger.info(f"Decisia [{self.court_code}]: scanning sub-court '{sub_court}'")

            for year in range(current_year, self.start_year - 1, -1):
                if limit is not None and len(all_docs) >= limit:
                    break
                if self._captcha_detected:
                    break

                page = 1

                while True:
                    if limit is not None and len(all_docs) >= limit:
                        break
                    if self._captcha_detected:
                        break

                    url = self._year_url(sub_court, year, page)

                    try:
                        resp = self._safe_request(url, context=f"discover {sub_court}/{year}/p{page}")
                    except CaptchaBlockError:
                        break

                    if resp is None:
                        break
                    if resp.status_code == 404:
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
                    self._delay(self.delay_range)

            if sc_count > 0:
                logger.info(f"  {sub_court.upper()}: {sc_count} decisions total")

        if self._captcha_detected:
            logger.warning(f"Decisia [{self.court_code}]: discovery aborted due to CAPTCHA block "
                          f"(got {len(all_docs)} docs before block)")

        logger.info(f"Decisia [{self.court_code}]: discovered {len(all_docs):,} decisions "
                     f"across {total_pages_fetched} pages")
        return all_docs

    # ========== Fetch ==========

    def fetch_document(self, doc_meta: DocumentMetadata) -> Optional[DocumentContent]:
        """
        Fetch full decision text from a Decisia item page.

        Uses ?iframe=true to get the inner content directly.
        Extracts text from div.documentcontent (primary Decisia content class).
        Includes CAPTCHA detection and randomised fetch delays.
        """
        url = doc_meta.source_url
        if not url:
            return None

        if self._captcha_detected:
            return None

        # Build iframe URL for fetching content
        iframe_url = url
        if '?' not in iframe_url:
            iframe_url += '?iframe=true'
        elif 'iframe=true' not in iframe_url:
            iframe_url += '&iframe=true'

        try:
            resp = self._safe_request(iframe_url, context=f"fetch {doc_meta.citation or url}")
        except CaptchaBlockError:
            return None

        if resp is None:
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

        # Randomised delay between fetches
        self._delay(self.fetch_delay)

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
        Sequential with randomised rate limiting (default 2-3.5s per document).
        Aborts early on CAPTCHA detection.
        """
        count = 0
        failed = 0
        self._captcha_detected = False

        for doc in docs:
            if limit is not None and count >= limit:
                break
            if stop_event and stop_event.is_set():
                break
            if self._captcha_detected:
                logger.warning(f"Decisia [{self.court_code}] batch: aborting — CAPTCHA detected")
                break

            result = self.fetch_document(doc)
            if result:
                yield result
                count += 1
            else:
                failed += 1

            if (count + failed) % 50 == 0 and (count + failed) > 0:
                logger.info(f"Decisia [{self.court_code}] batch: {count} ok, {failed} fail")

        logger.info(f"Decisia [{self.court_code}] batch complete: {count} ok, {failed} fail"
                    f"{' (CAPTCHA block)' if self._captcha_detected else ''}")
