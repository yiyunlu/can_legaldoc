"""
Nova Scotia legislation adapter — fetches NS statutes from nslegislature.ca
and regulations from novascotia.ca/just/regulations/.

Discovery: Statutes at nslegislature.ca, Regulations at novascotia.ca
Content:   Static HTML files (.htm)

License:   Crown copyright — Province of Nova Scotia
Note:      Statutes and regulations are on two different websites.
"""
import re
import time
import requests
from typing import List, Optional
from urllib.parse import urljoin, quote, urlsplit, urlunsplit
from lxml import html as lxml_html

from scraper.adapters import register_adapter
from scraper.adapters.base import BaseSourceAdapter, DocumentMetadata, DocumentContent
from utils.logger import logger
from utils.config import config

STATUTES_BASE = "https://nslegislature.ca"
STATUTES_INDEX = f"{STATUTES_BASE}/legislative-business/bills-statutes/consolidated-public-statutes"
REGS_BASE = "https://novascotia.ca"
REGS_INDEX = f"{REGS_BASE}/just/regulations/regsbyact.htm"
REGS_SUBPAGES = [
    f"{REGS_BASE}/just/regulations/rxaa-l.htm",
    f"{REGS_BASE}/just/regulations/rxam-z.htm",
]


def _normalize_url(url: str) -> str:
    """Percent-encode spaces and special chars in URL path for DB consistency.
    Handles already partially-encoded URLs by decoding first to avoid double-encoding."""
    from urllib.parse import unquote
    parts = urlsplit(url)
    # Decode first to avoid double-encoding (e.g. %20 → %2520)
    decoded_path = unquote(parts.path)
    clean_path = quote(decoded_path, safe='/:@!$&\'()*+,;=-._~')
    return urlunsplit((parts.scheme, parts.netloc, clean_path, parts.query, parts.fragment))


@register_adapter('nova_scotia_laws')
class NovaScotiaLawsAdapter(BaseSourceAdapter):
    """Adapter for Nova Scotia legislation (statutes + regulations with HTML)."""

    def __init__(self, **kwargs):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "CanadaLegalDataPlatform/1.0",
        })

    def get_source_name(self) -> str:
        return "NS Legislation (Legislature)"

    def get_source_type(self) -> str:
        return "nova_scotia_laws"

    def get_jurisdiction(self) -> str:
        return "ns"

    def discover_documents(self, limit: Optional[int] = None) -> List[DocumentMetadata]:
        """Discover NS statutes and regulations."""
        docs = []
        docs.extend(self._discover_statutes(limit))
        remaining = (limit - len(docs)) if limit else None
        if remaining is None or remaining > 0:
            docs.extend(self._discover_regulations(remaining))
        logger.info(f"Discovered {len(docs)} NS legislation documents")
        return docs

    def _discover_statutes(self, limit: Optional[int] = None) -> List[DocumentMetadata]:
        """Parse consolidated public statutes page (nslegislature.ca Drupal)."""
        docs = []
        try:
            resp = self.session.get(STATUTES_INDEX, timeout=config.TIMEOUT)
            resp.raise_for_status()
            tree = lxml_html.fromstring(resp.text)
            tree.make_links_absolute(STATUTES_INDEX)

            # The statutes are listed as <li> elements containing HTML links
            # Pattern: <a href="/sites/default/files/legc/statutes HTML/{name}.htm">HTML</a>
            for link in tree.xpath('//a[contains(@href, "statutes") and contains(@href, ".htm")]'):
                if limit and len(docs) >= limit:
                    break
                href = link.get("href", "")
                if not href or ".htm" not in href:
                    continue
                # Skip PDF links — we only want HTML
                if ".pdf" in href.lower():
                    continue

                # Extract title from parent <li> text
                parent_li = link.getparent()
                while parent_li is not None and parent_li.tag != 'li':
                    parent_li = parent_li.getparent()

                if parent_li is not None:
                    # Get all text from <li> except the link labels (HTML/PDF)
                    full_text = parent_li.text_content().strip()
                    # Remove "HTML" and "PDF" labels at the end
                    title = re.sub(r'\s*(HTML|PDF)\s*', '', full_text).strip()
                    title = re.sub(r'\s+', ' ', title)
                else:
                    title = link.text_content().strip()

                if not title or len(title) < 3:
                    continue
                # Skip "not proclaimed in force" duplicates
                if title.lower().startswith('*'):
                    title = title.lstrip('* ')

                # Extract filename for citation
                filename = href.rsplit('/', 1)[-1].replace('.htm', '')

                docs.append(DocumentMetadata(
                    source_url=_normalize_url(href),
                    title=title,
                    citation=f"RSNS {filename}",
                    jurisdiction_code="ns",
                    category="Legislation",
                    document_type="legislation",
                    is_active=True,
                    metadata={"doc_class": "statute", "filename": filename},
                ))
        except Exception as e:
            logger.error(f"Failed to discover NS statutes: {e}")
        return docs

    def _discover_regulations(self, limit: Optional[int] = None) -> List[DocumentMetadata]:
        """Parse regulations from novascotia.ca subpages."""
        docs = []
        seen_urls = set()
        try:
            for subpage_url in REGS_SUBPAGES:
                if limit and len(docs) >= limit:
                    break
                time.sleep(0.3)
                resp = self.session.get(subpage_url, timeout=config.TIMEOUT)
                resp.raise_for_status()
                tree = lxml_html.fromstring(resp.text)
                tree.make_links_absolute(subpage_url)

                # Look for .htm regulation links (skip PDF-only)
                for link in tree.xpath('//a[contains(@href, ".htm")]'):
                    if limit and len(docs) >= limit:
                        break
                    href = link.get("href", "")
                    title = (link.text_content() or "").strip()
                    if not href or not title or len(title) < 3:
                        continue
                    if _normalize_url(href) in seen_urls:
                        continue
                    # Only include regulation content pages
                    if "/just/regulations/" not in href.lower() and "/legc/" not in href.lower():
                        continue
                    # Skip index/navigation pages
                    if "regsbyact" in href or "rxaa-" in href or "rxam-" in href or "consregs" in href:
                        continue
                    # Skip site navigation links (not actual regulation content)
                    nav_pages = {'index.htm', 'aboutrr.htm', 'regsbydept.htm', 'order.htm',
                                 'search.htm', 'rg1.htm', 'rg1issues.htm', 'rg2.htm',
                                 'rg2issues.htm', 'publicat.htm', 'relsites.htm',
                                 'contacts.htm', 'advertising.htm'}
                    page_name = href.rsplit('/', 1)[-1].lower()
                    if page_name in nav_pages:
                        continue

                    normalized = _normalize_url(href)
                    seen_urls.add(normalized)
                    filename = href.rsplit('/', 1)[-1].replace('.htm', '')

                    docs.append(DocumentMetadata(
                        source_url=normalized,
                        title=title,
                        citation=f"NS Reg {filename}",
                        jurisdiction_code="ns",
                        category="Regulation",
                        document_type="regulation",
                        is_active=True,
                        metadata={"doc_class": "regulation", "filename": filename},
                    ))
        except Exception as e:
            logger.error(f"Failed to discover NS regulations: {e}")
        return docs

    def fetch_document(self, doc_meta: DocumentMetadata) -> Optional[DocumentContent]:
        """Fetch full HTML content for a single NS statute or regulation."""
        try:
            resp = self.session.get(doc_meta.source_url, timeout=config.TIMEOUT)
            resp.raise_for_status()

            if not resp.text or len(resp.text) < 200:
                logger.warning(f"Empty content for {doc_meta.title}")
                return None

            content_html, content_text = self._parse_html(resp.text)

            if not content_text or len(content_text) < 50:
                logger.warning(f"Could not extract text from {doc_meta.title}")
                return None

            time.sleep(0.3)

            return DocumentContent(
                source_url=doc_meta.source_url,
                title=doc_meta.title,
                citation=doc_meta.citation,
                content_html=content_html,
                content_text=content_text,
                jurisdiction_code="ns",
                category=doc_meta.category,
                document_type=doc_meta.document_type,
                is_active=True,
                metadata={
                    **doc_meta.metadata,
                    "source": "nslegislature_ca" if "nslegislature" in doc_meta.source_url else "novascotia_ca",
                    "copyright": "Crown copyright — Province of Nova Scotia",
                },
            )
        except Exception as e:
            logger.error(f"Failed to fetch NS document {doc_meta.title}: {e}")
            return None

    def _parse_html(self, raw_html: str) -> tuple:
        """Parse NS legislation HTML."""
        try:
            tree = lxml_html.fromstring(raw_html)
            for tag in tree.xpath('//script | //style | //nav | //header | //footer'):
                tag.getparent().remove(tag)

            body = tree.xpath('//body')
            elem = body[0] if body else tree

            content_html = lxml_html.tostring(elem, encoding='unicode')
            content_text = self._clean_text(elem.text_content())
            return content_html, content_text
        except Exception as e:
            logger.error(f"HTML parse error: {e}")
            text = re.sub(r'<[^>]+>', ' ', raw_html)
            return raw_html, re.sub(r'\s+', ' ', text).strip()

    def _clean_text(self, text: str) -> str:
        """Normalize whitespace."""
        lines = text.split('\n')
        cleaned = [line.strip() for line in lines if line.strip()]
        return '\n'.join(cleaned)
