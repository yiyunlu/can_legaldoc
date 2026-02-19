"""
Prince Edward Island legislation adapter — fetches PEI consolidated statutes
and regulations from princeedwardisland.ca.

Discovery: Single listing page at /en/legislation (all 800+ docs, no pagination)
Content:   PDF files only (no HTML versions)

URL pattern:
  /sites/default/files/legislation/{filename}.pdf

License:   Crown copyright — Province of Prince Edward Island
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

BASE_URL = "https://www.princeedwardisland.ca"
LISTING_URL = f"{BASE_URL}/en/legislation"


@register_adapter('pei_laws')
class PEILawsAdapter(BaseSourceAdapter):
    """Adapter for PEI legislation (statutes + regulations via PDF)."""

    def __init__(self, **kwargs):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "CanadaLegalDataPlatform/1.0",
        })

    def get_source_name(self) -> str:
        return "PEI Legislation"

    def get_source_type(self) -> str:
        return "pei_laws"

    def get_jurisdiction(self) -> str:
        return "pe"

    def discover_documents(self, limit: Optional[int] = None) -> List[DocumentMetadata]:
        """Discover PEI acts and regulations from the single listing page.

        The page lists all ~444 statutes and ~409 regulations in one HTML page.
        Acts appear directly; regulations are indented under their parent act
        via Tailwind CSS class tw-ml-8.5 / tw-ml-9.5.
        """
        docs = []
        try:
            resp = self.session.get(LISTING_URL, timeout=config.TIMEOUT)
            resp.raise_for_status()
            tree = lxml_html.fromstring(resp.text)
            tree.make_links_absolute(LISTING_URL)

            # Find all article elements with PDF download cards
            articles = tree.xpath('//article[@data-component-id="gpei:card-download"]')

            current_act_title = None
            seen_urls = set()

            for article in articles:
                if limit and len(docs) >= limit:
                    break

                # Find the PDF link
                link = article.xpath('.//a[contains(@href, ".pdf")]')
                if not link:
                    continue
                link = link[0]

                href = link.get("href", "").strip()
                title = (link.text_content() or "").strip()

                if not href or not title or len(title) < 3:
                    continue

                if href in seen_urls:
                    continue
                seen_urls.add(href)

                # Determine if this is a regulation by checking parent div indentation
                parent_div = article.getparent()
                is_regulation = False
                if parent_div is not None:
                    parent_classes = parent_div.get("class", "")
                    if "tw-ml-8" in parent_classes or "tw-ml-9" in parent_classes:
                        is_regulation = True

                if not is_regulation:
                    current_act_title = title

                # Clean up title
                title = title.strip()
                # Remove "(Repealed)" suffix but track it
                is_repealed = "(Repealed)" in title or "(repealed)" in title

                # Extract chapter code from PDF filename
                # e.g., /legislation/A-01-Acadian%20Purchase%20Trust%20Act.pdf → "A-01"
                citation = self._extract_citation(href, is_regulation)

                doc_type = "regulation" if is_regulation else "legislation"
                category = "Regulation" if is_regulation else "Legislation"

                meta = {
                    "doc_class": "regulation" if is_regulation else "statute",
                    "format": "pdf",
                }
                if is_regulation and current_act_title:
                    meta["parent_act"] = current_act_title
                if is_repealed:
                    meta["status"] = "repealed"

                docs.append(DocumentMetadata(
                    source_url=href,
                    title=title,
                    citation=citation,
                    jurisdiction_code="pe",
                    category=category,
                    document_type=doc_type,
                    is_active=not is_repealed,
                    metadata=meta,
                ))

        except Exception as e:
            logger.error(f"Failed to discover PEI legislation: {e}")

        logger.info(f"Discovered {len(docs)} PEI legislation documents")
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
                jurisdiction_code="pe",
                category=doc_meta.category,
                document_type=doc_meta.document_type,
                is_active=doc_meta.is_active,
                metadata={
                    **doc_meta.metadata,
                    "source": "princeedwardisland_ca",
                    "copyright": "Crown copyright — Province of Prince Edward Island",
                },
            )
        except Exception as e:
            logger.error(f"Failed to fetch PEI document {doc_meta.title}: {e}")
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
        """Extract chapter code from the PDF filename.

        Examples:
          /legislation/A-01-Acadian%20Purchase%20Trust%20Act.pdf → "RSPEI A-01"
          /legislation/a-04-1-adoption_act.pdf → "RSPEI a-04-1"
          /legislation/A%2608-01-Agricultural%20Crop%20Rotation%20Act.pdf → "PE Reg A&08-01"
        """
        from urllib.parse import unquote
        filename = unquote(url.rsplit('/', 1)[-1]).replace('.pdf', '')

        # Try to extract chapter code at start of filename
        # Patterns: "A-01-...", "a-04-1-...", "A&08-01-..."
        m = re.match(r'^([A-Za-z&]+[-.]?\d+(?:[-.]\d+)*)', filename)
        if m:
            code = m.group(1)
            prefix = "PE Reg" if is_regulation else "RSPEI"
            return f"{prefix} {code}"
        return ""

    def _clean_text(self, text: str) -> str:
        """Normalize whitespace in extracted text."""
        lines = text.split('\n')
        cleaned = [line.strip() for line in lines if line.strip()]
        return '\n'.join(cleaned)
