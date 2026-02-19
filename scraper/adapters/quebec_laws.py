"""
Quebec legislation adapter — fetches QC consolidated statutes and regulations
from LegisQuebec (legisquebec.gouv.qc.ca).

Discovery: Listing pages at /fr/chapitres?corpus=lois|regs&selection=tout
Content:   Server-rendered HTML (no SPA framework)

URL patterns:
  Acts listing:       /fr/chapitres?corpus=lois&selection=tout&langCont=en
  Regulations listing:/fr/chapitres?corpus=regs&selection=tout&langCont=en
  Individual act:     /fr/document/lc/{chapter}?langCont=en
  Individual reg:     /fr/document/rc/{chapter}?langCont=en

License:   © Gouvernement du Québec — Éditeur officiel du Québec
Platform:  Cyberlex v2.2.9.0 (server-rendered, jQuery + Bootstrap)
"""
import re
import time
import requests
from typing import List, Optional
from urllib.parse import quote
from lxml import html as lxml_html

from scraper.adapters import register_adapter
from scraper.adapters.base import BaseSourceAdapter, DocumentMetadata, DocumentContent
from utils.logger import logger
from utils.config import config

BASE_URL = "https://www.legisquebec.gouv.qc.ca"
ACTS_LISTING = f"{BASE_URL}/fr/chapitres?corpus=lois&selection=tout&langCont=en"
REGS_LISTING = f"{BASE_URL}/fr/chapitres?corpus=regs&selection=tout&langCont=en"


@register_adapter('quebec_laws')
class QuebecLawsAdapter(BaseSourceAdapter):
    """Adapter for Quebec legislation (statutes + regulations via HTML)."""

    def __init__(self, **kwargs):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "CanadaLegalDataPlatform/1.0",
            "Accept-Language": "en-CA,en;q=0.9,fr;q=0.8",
        })

    def get_source_name(self) -> str:
        return "Legis Québec"

    def get_source_type(self) -> str:
        return "quebec_laws"

    def get_jurisdiction(self) -> str:
        return "qc"

    def discover_documents(self, limit: Optional[int] = None) -> List[DocumentMetadata]:
        """Discover QC acts and regulations from listing pages."""
        docs = []
        docs.extend(self._discover_corpus("lois", limit))
        remaining = (limit - len(docs)) if limit else None
        if remaining is None or remaining > 0:
            docs.extend(self._discover_corpus("regs", remaining))
        logger.info(f"Discovered {len(docs)} Quebec legislation documents")
        return docs

    def _discover_corpus(self, corpus: str, limit: Optional[int] = None) -> List[DocumentMetadata]:
        """Parse a listing page for acts (corpus=lois) or regulations (corpus=regs)."""
        docs = []
        is_regulation = corpus == "regs"
        listing_url = REGS_LISTING if is_regulation else ACTS_LISTING

        try:
            resp = self.session.get(listing_url, timeout=config.TIMEOUT)
            resp.raise_for_status()
            tree = lxml_html.fromstring(resp.text)
            tree.make_links_absolute(listing_url)

            # Rows in the listing table — each clickable <tr> is a document
            rows = tree.xpath('//table//tr[contains(@class, "clickable")]')
            if not rows:
                # Fallback: try any table row with a document link
                rows = tree.xpath('//table//tr[.//a[contains(@href, "/document/")]]')

            seen_urls = set()
            for row in rows:
                if limit and len(docs) >= limit:
                    break

                # Skip nested regulation rows when scraping acts
                row_classes = row.get("class", "")
                if not is_regulation and "nestedRow" in row_classes:
                    continue

                # Find the document link
                links = row.xpath('.//a[contains(@href, "/document/")]')
                if not links:
                    continue
                link = links[0]

                href = link.get("href", "").strip()
                title = (link.text_content() or "").strip()

                if not href or not title or len(title) < 3:
                    continue

                # Ensure English content parameter
                if "langCont=en" not in href:
                    sep = "&" if "?" in href else "?"
                    href = f"{href}{sep}langCont=en"

                if href in seen_urls:
                    continue
                seen_urls.add(href)

                # Extract chapter code from the URL path
                # e.g., /fr/document/lc/A-2.001 → "A-2.001"
                # e.g., /fr/document/rc/A-2.1,%20r.%201 → "A-2.1, r. 1"
                chapter_code = ""
                chapter_match = re.search(r'/document/(?:lc|rc)/([^?]+)', href)
                if chapter_match:
                    from urllib.parse import unquote
                    chapter_code = unquote(chapter_match.group(1)).strip()

                # Check for status badges (repealed / replaced)
                is_repealed = False
                status_text = row.text_content().lower()
                if "abrog" in status_text or "repealed" in status_text:
                    is_repealed = True
                is_replaced = "remplac" in status_text or "replaced" in status_text

                # Build citation
                citation = ""
                if chapter_code:
                    prefix = "CQLR" if not is_regulation else "CQLR"
                    citation = f"{prefix} c {chapter_code}" if not is_regulation else f"{prefix} {chapter_code}"

                doc_type = "regulation" if is_regulation else "legislation"
                category = "Regulation" if is_regulation else "Legislation"

                meta = {
                    "doc_class": "regulation" if is_regulation else "statute",
                    "format": "html",
                    "chapter_code": chapter_code,
                }
                if is_repealed:
                    meta["status"] = "repealed"
                if is_replaced:
                    meta["status"] = "replaced"

                docs.append(DocumentMetadata(
                    source_url=href,
                    title=title,
                    citation=citation,
                    jurisdiction_code="qc",
                    category=category,
                    document_type=doc_type,
                    is_active=not is_repealed,
                    metadata=meta,
                ))

        except Exception as e:
            logger.error(f"Failed to discover Quebec {corpus}: {e}")

        return docs

    def fetch_document(self, doc_meta: DocumentMetadata) -> Optional[DocumentContent]:
        """Fetch full HTML content for a single QC statute or regulation."""
        try:
            resp = self.session.get(doc_meta.source_url, timeout=config.TIMEOUT)
            resp.raise_for_status()

            if not resp.text or len(resp.text) < 500:
                logger.warning(f"Empty content for {doc_meta.title}")
                return None

            content_html, content_text = self._parse_html(resp.text)

            if not content_text or len(content_text) < 50:
                logger.warning(f"Could not extract text from {doc_meta.title}")
                return None

            time.sleep(0.5)  # Polite delay for government site

            return DocumentContent(
                source_url=doc_meta.source_url,
                title=doc_meta.title,
                citation=doc_meta.citation,
                content_html=content_html,
                content_text=content_text,
                jurisdiction_code="qc",
                category=doc_meta.category,
                document_type=doc_meta.document_type,
                is_active=doc_meta.is_active,
                metadata={
                    **doc_meta.metadata,
                    "source": "legisquebec_gouv_qc_ca",
                    "copyright": "© Gouvernement du Québec — Éditeur officiel du Québec",
                },
            )
        except Exception as e:
            logger.error(f"Failed to fetch QC document {doc_meta.title}: {e}")
            return None

    def _parse_html(self, raw_html: str) -> tuple:
        """Parse QC legislation HTML — extract the LegislativeDocument div."""
        try:
            tree = lxml_html.fromstring(raw_html)

            # Remove scripts, styles, navigation
            for tag in tree.xpath('//script | //style | //nav | //header | //footer'):
                tag.getparent().remove(tag)

            # Target the legislative content container
            content_div = tree.xpath('//div[contains(@class, "LegislativeDocument")]')
            if content_div:
                elem = content_div[0]
            else:
                # Fallback: try main content area
                main = tree.xpath('//main | //div[@id="content"] | //div[@class="content"]')
                elem = main[0] if main else tree.xpath('//body')[0] if tree.xpath('//body') else tree

            # Optionally strip historical notes for cleaner text
            for note in elem.xpath('.//*[contains(@class, "HistoricalNote")]'):
                note.getparent().remove(note)

            content_html = lxml_html.tostring(elem, encoding='unicode')
            content_text = self._clean_text(elem.text_content())
            return content_html, content_text

        except Exception as e:
            logger.error(f"HTML parse error: {e}")
            # Fallback: strip tags
            text = re.sub(r'<[^>]+>', ' ', raw_html)
            return raw_html, re.sub(r'\s+', ' ', text).strip()

    def _clean_text(self, text: str) -> str:
        """Normalize whitespace in extracted text."""
        lines = text.split('\n')
        cleaned = [line.strip() for line in lines if line.strip()]
        return '\n'.join(cleaned)
