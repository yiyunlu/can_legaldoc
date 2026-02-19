"""
Yukon legislation adapter — fetches YT consolidated statutes and
regulations from the Yukon Legislation website (iLAWS CMS).

Discovery: Single alphabetical listing page at laws.yukon.ca
Content:   PDF files only (no HTML versions)

URL pattern:
  Acts:        /cms/images/LEGISLATION/PRINCIPAL/{YEAR}/{YEAR}-{ID}/{YEAR}-{ID}_{VER}.pdf
  Regulations: /cms/images/LEGISLATION/SUBORDINATE/{YEAR}/{YEAR}-{ID}/{YEAR}-{ID}_{VER}.pdf

License:   © Government of Yukon — unofficial consolidation for information only
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

BASE_URL = "https://laws.yukon.ca"
LISTING_URL = f"{BASE_URL}/cms/legislation-by-title.html"


@register_adapter('yukon_laws')
class YukonLawsAdapter(BaseSourceAdapter):
    """Adapter for Yukon legislation (statutes + regulations via PDF)."""

    def __init__(self, **kwargs):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "CanadaLegalDataPlatform/1.0",
        })

    def get_source_name(self) -> str:
        return "Yukon Legislation"

    def get_source_type(self) -> str:
        return "yukon_laws"

    def get_jurisdiction(self) -> str:
        return "yt"

    def discover_documents(self, limit: Optional[int] = None) -> List[DocumentMetadata]:
        """Discover Yukon acts and regulations from the title listing page.

        The iLAWS page lists all acts (A-Z) in a single HTML table.
        Each act row contains a link to the PDF. Some acts have an
        "Expand Act" button that reveals subordinate regulations,
        but those are loaded via JS — we parse main act PDFs from the
        static HTML, then also scrape regulation PDFs if visible.
        """
        docs = []
        try:
            resp = self.session.get(LISTING_URL, timeout=config.TIMEOUT)
            resp.raise_for_status()
            tree = lxml_html.fromstring(resp.text)
            tree.make_links_absolute(LISTING_URL)

            # Find all PDF links in the legislation table
            pdf_links = tree.xpath(
                '//a[contains(@href, "/LEGISLATION/") and contains(@href, ".pdf")]'
            )

            seen_urls = set()
            for link in pdf_links:
                if limit and len(docs) >= limit:
                    break

                href = link.get("href", "")
                title = (link.text_content() or "").strip()

                if not href or not title or len(title) < 3:
                    continue

                # Normalize URL
                href = href.strip()
                if href in seen_urls:
                    continue
                seen_urls.add(href)

                # Remove " Open PDF" suffix from title
                title = re.sub(r'\s*Open\s*PDF\s*$', '', title).strip()

                # Split bilingual title: "English Title (French Title)"
                title_en = title
                title_fr = ""
                paren_match = re.match(r'^(.+?)\s*\(([^)]+)\)\s*$', title)
                if paren_match:
                    title_en = paren_match.group(1).strip()
                    title_fr = paren_match.group(2).strip()

                # Determine type from URL path
                is_regulation = '/SUBORDINATE/' in href
                doc_type = "regulation" if is_regulation else "legislation"
                category = "Regulation" if is_regulation else "Legislation"

                # Extract year and ID from URL for citation
                citation = self._extract_citation(href, is_regulation)

                # Title case if all caps
                if title_en.isupper():
                    title_en = title_en.title()

                metadata = {
                    "doc_class": "regulation" if is_regulation else "statute",
                    "format": "pdf",
                }
                if title_fr:
                    metadata["title_fr"] = title_fr

                docs.append(DocumentMetadata(
                    source_url=href,
                    title=title_en,
                    citation=citation,
                    jurisdiction_code="yt",
                    category=category,
                    document_type=doc_type,
                    is_active=True,
                    metadata=metadata,
                ))

        except Exception as e:
            logger.error(f"Failed to discover Yukon legislation: {e}")

        logger.info(f"Discovered {len(docs)} Yukon legislation documents")
        return docs

    def fetch_document(self, doc_meta: DocumentMetadata) -> Optional[DocumentContent]:
        """Fetch a PDF document and extract its text content."""
        try:
            resp = self.session.get(doc_meta.source_url, timeout=60)
            if resp.status_code == 404:
                logger.warning(f"PDF not found: {doc_meta.source_url}")
                return None
            resp.raise_for_status()

            if len(resp.content) < 200:
                logger.warning(f"Empty PDF for {doc_meta.title}")
                return None

            # Verify it's actually a PDF
            if not resp.content[:5].startswith(b'%PDF'):
                logger.warning(f"Not a PDF file: {doc_meta.source_url}")
                return None

            content_text = self._extract_pdf_text(resp.content)

            if not content_text or len(content_text) < 50:
                logger.warning(f"Could not extract text from PDF: {doc_meta.title}")
                return None

            time.sleep(0.3)

            return DocumentContent(
                source_url=doc_meta.source_url,
                title=doc_meta.title,
                citation=doc_meta.citation,
                content_html="",  # PDFs don't have HTML
                content_text=content_text,
                jurisdiction_code="yt",
                category=doc_meta.category,
                document_type=doc_meta.document_type,
                is_active=True,
                metadata={
                    **doc_meta.metadata,
                    "source": "laws_yukon_ca",
                    "copyright": "© Government of Yukon — unofficial consolidation",
                },
            )
        except Exception as e:
            logger.error(f"Failed to fetch Yukon document {doc_meta.title}: {e}")
            return None

    def _extract_pdf_text(self, pdf_bytes: bytes) -> str:
        """Extract text from PDF bytes using pymupdf or fallback."""
        try:
            import fitz  # pymupdf
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            text_parts = []
            for page in doc:
                text_parts.append(page.get_text())
            doc.close()
            return self._clean_text('\n'.join(text_parts))
        except ImportError:
            logger.warning("pymupdf not installed — using rough PDF extraction")
            return self._rough_pdf_text(pdf_bytes)

    def _rough_pdf_text(self, pdf_bytes: bytes) -> str:
        """Very basic PDF text extraction without external libraries."""
        try:
            text = pdf_bytes.decode('latin-1', errors='ignore')
            parts = re.findall(r'\(([^)]+)\)', text)
            result = ' '.join(p for p in parts if len(p) > 2 and p.isprintable())
            return self._clean_text(result) if len(result) > 50 else ""
        except Exception:
            return ""

    def _extract_citation(self, url: str, is_regulation: bool) -> str:
        """Extract citation from the PDF URL.

        URLs look like: .../PRINCIPAL/2018/2018-0009/2018-0009_2.pdf
        """
        match = re.search(r'/(\d{4})-(\w+)/\1-\2_(\d+)\.pdf$', url)
        if match:
            year = match.group(1)
            num = match.group(2)
            prefix = "YT OIC" if is_regulation else "SY"
            return f"{prefix} {year}, c.{num}"
        return ""

    def _clean_text(self, text: str) -> str:
        """Normalize whitespace in extracted text."""
        lines = text.split('\n')
        cleaned = [line.strip() for line in lines if line.strip()]
        return '\n'.join(cleaned)
