"""
Alberta King's Printer adapter — fetches Alberta legislation from the
official King's Printer website via the Open Alberta CKAN API for discovery
and the King's Printer HTML view for content.

Discovery: CKAN API at open.alberta.ca/api/3/
Content:   King's Printer HTML view at kings-printer.alberta.ca

License:   Free to reproduce with attribution
           (c) Alberta King's Printer
"""
import re
import time
import requests
from typing import List, Optional
from lxml import html as lxml_html

from scraper.adapters import register_adapter
from scraper.adapters.base import BaseSourceAdapter, DocumentMetadata, DocumentContent
from utils.logger import logger
from utils.config import config


CKAN_API = "https://open.alberta.ca/api/3/action/package_search"
KP_CONTENT_URL = "https://kings-printer.alberta.ca/1266.cfm"
KP_BASE = "https://kings-printer.alberta.ca"

# Regex to detect regulation-style names: e.g., 2021_265, 2001_081
REG_NAME_PATTERN = re.compile(r'^\d{4}_\d{3}$')


@register_adapter('alberta_kings_printer')
class AlbertaKingsPrinterAdapter(BaseSourceAdapter):
    """
    Adapter for Alberta legislation via the Open Alberta CKAN API (discovery)
    and the King's Printer website (content).
    """

    def __init__(self, **kwargs):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "CanadaLegalDataPlatform/1.0",
        })

    def get_source_name(self) -> str:
        return "Alberta Legislation (King's Printer)"

    def get_source_type(self) -> str:
        return "alberta_kings_printer"

    def get_jurisdiction(self) -> str:
        return "ab"

    def discover_documents(self, limit: Optional[int] = None) -> List[DocumentMetadata]:
        """
        Discover Alberta legislation via the CKAN API.
        Paginates through all records with pubtype 'Legislation and Regulations'.
        """
        docs = []
        page_size = 100
        start = 0

        logger.info("Discovering Alberta legislation via CKAN API...")

        try:
            while True:
                if limit and len(docs) >= limit:
                    break

                params = {
                    "q": "*:*",
                    "fq": 'pubtype:"Legislation and Regulations"',
                    "rows": page_size,
                    "start": start,
                    "sort": "name asc",
                }

                resp = self.session.get(CKAN_API, params=params, timeout=config.TIMEOUT)
                resp.raise_for_status()
                data = resp.json()

                results = data.get("result", {}).get("results", [])
                total_count = data.get("result", {}).get("count", 0)

                if not results:
                    break

                for pkg in results:
                    if limit and len(docs) >= limit:
                        break

                    name = pkg.get("name", "")
                    title = pkg.get("title", name)
                    isbn = pkg.get("identifier-ISBN-print", "")

                    if not name:
                        continue

                    # Determine if this is an Act or Regulation
                    is_reg = bool(REG_NAME_PATTERN.match(name))
                    leg_type = "Regs" if is_reg else "Acts"
                    doc_type = "regulation" if is_reg else "legislation"
                    category = "Regulation" if is_reg else "Legislation"

                    # Build content URL
                    content_url = (
                        f"{KP_CONTENT_URL}?page={name}.cfm"
                        f"&leg_type={leg_type}"
                        f"&isbncln={isbn}"
                        f"&display=html"
                    )

                    # Build a stable source URL for deduplication
                    source_url = f"{KP_BASE}/570.cfm?frm_isbn={isbn}&search_by=link" if isbn else content_url

                    # Extract citation from title (e.g., "Chapter A-1.4")
                    citation = name.upper() if not is_reg else name

                    docs.append(DocumentMetadata(
                        source_url=source_url,
                        title=title,
                        citation=citation,
                        jurisdiction_code="ab",
                        category=category,
                        document_type=doc_type,
                        is_active=True,
                        metadata={
                            "ckan_name": name,
                            "isbn": isbn,
                            "leg_type": leg_type,
                            "content_url": content_url,
                            "date_modified": pkg.get("date_modified", ""),
                        },
                    ))

                start += page_size
                if start >= total_count:
                    break

                time.sleep(0.2)  # Rate limiting for CKAN API

        except Exception as e:
            logger.error(f"Failed to discover Alberta legislation: {e}")

        logger.info(f"Discovered {len(docs)} Alberta legislation documents")
        return docs

    def fetch_document(self, doc_meta: DocumentMetadata) -> Optional[DocumentContent]:
        """Fetch full HTML content for a single Alberta statute/regulation."""
        content_url = doc_meta.metadata.get("content_url", "")
        if not content_url:
            logger.error(f"No content URL for {doc_meta.title}")
            return None

        try:
            logger.debug(f"Fetching Alberta document: {doc_meta.title}")

            resp = self.session.get(content_url, timeout=config.TIMEOUT)
            resp.raise_for_status()

            if not resp.text or len(resp.text) < 200:
                logger.warning(f"Empty or too short content for {doc_meta.title}")
                return None

            # Detect error pages (KP returns 200 even for missing content)
            text_lower = resp.text.lower()
            if 'page not found' in text_lower or 'page you were looking for' in text_lower:
                logger.debug(f"Error page for {doc_meta.title} — content not available in HTML view")
                return None

            # Parse HTML and extract content
            content_html, content_text = self._parse_kp_html(resp.text, doc_meta.title)

            if not content_text or len(content_text) < 100:
                logger.warning(f"Could not extract meaningful text from {doc_meta.title}")
                return None

            time.sleep(0.5)  # Rate limiting for King's Printer

            return DocumentContent(
                source_url=doc_meta.source_url,
                title=doc_meta.title,
                citation=doc_meta.citation,
                content_html=content_html,
                content_text=content_text,
                jurisdiction_code="ab",
                category=doc_meta.category,
                document_type=doc_meta.document_type,
                is_active=True,
                metadata={
                    **doc_meta.metadata,
                    "source": "kings_printer_alberta",
                    "copyright": "(c) Alberta King's Printer",
                },
            )

        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                logger.debug(f"404 for {doc_meta.title} - may not have HTML view")
            else:
                logger.error(f"HTTP error fetching {doc_meta.title}: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to fetch Alberta document {doc_meta.title}: {e}")
            return None

    def _parse_kp_html(self, raw_html: str, title: str) -> tuple:
        """
        Parse the King's Printer HTML page and extract the legislation content.
        The KP renders Word-converted HTML with MsoNormal classes.
        Returns (content_html, content_text).
        """
        try:
            tree = lxml_html.fromstring(raw_html)

            # The legislation content is typically in the main content area
            # Try common content containers
            content_elem = None

            # Look for the main content div (KP uses various containers)
            for selector in [
                '//div[@id="content"]',
                '//div[@class="content"]',
                '//div[contains(@class, "WordSection")]',
                '//div[contains(@class, "MsoNormal")]/..',
                '//body',
            ]:
                elems = tree.xpath(selector)
                if elems:
                    content_elem = elems[0]
                    break

            if content_elem is None:
                content_elem = tree

            # Get HTML content
            content_html = lxml_html.tostring(content_elem, encoding='unicode')

            # Extract text
            content_text = self._extract_text(content_elem)

            # Clean up text
            content_text = self._clean_text(content_text)

            return content_html, content_text

        except Exception as e:
            logger.error(f"Failed to parse HTML for {title}: {e}")
            return raw_html, self._fallback_text_extract(raw_html)

    def _extract_text(self, elem) -> str:
        """Extract clean text from an lxml element."""
        return elem.text_content()

    def _clean_text(self, text: str) -> str:
        """Clean up extracted text: normalize whitespace, remove junk."""
        # Normalize whitespace
        lines = text.split('\n')
        cleaned = []
        for line in lines:
            line = line.strip()
            if line:
                cleaned.append(line)
        return '\n'.join(cleaned)

    def _fallback_text_extract(self, html: str) -> str:
        """Fallback text extraction using regex."""
        # Strip HTML tags
        text = re.sub(r'<[^>]+>', ' ', html)
        text = re.sub(r'\s+', ' ', text).strip()
        return text
