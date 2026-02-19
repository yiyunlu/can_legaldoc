"""
Nunavut legislation adapter — fetches NU consolidated statutes and
regulations from the official Nunavut Legislation website.

Discovery: Alphabetical pages at nunavutlegislation.ca/en/consolidated-law/current?title=A..Z
Content:   Individual HTML pages with embedded PDF viewer; download link gives PDF
           We parse the listing pages for metadata + download PDFs for content.

License:   Crown copyright — consolidations are unofficial unless marked "Official"
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

BASE_URL = "https://www.nunavutlegislation.ca"
LISTING_URL = f"{BASE_URL}/en/consolidated-law/current"


@register_adapter('nunavut_laws')
class NunavutLawsAdapter(BaseSourceAdapter):
    """Adapter for Nunavut consolidated legislation (statutes + regulations)."""

    def __init__(self, **kwargs):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "CanadaLegalDataPlatform/1.0",
        })

    def get_source_name(self) -> str:
        return "Nunavut Legislation"

    def get_source_type(self) -> str:
        return "nunavut_laws"

    def get_jurisdiction(self) -> str:
        return "nu"

    def discover_documents(self, limit: Optional[int] = None) -> List[DocumentMetadata]:
        """Discover Nunavut statutes and regulations from A-Z listing pages."""
        docs = []
        letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

        for letter in letters:
            if limit and len(docs) >= limit:
                break
            remaining = (limit - len(docs)) if limit else None
            new_docs = self._discover_letter(letter, remaining)
            docs.extend(new_docs)
            if new_docs:
                time.sleep(0.3)

        logger.info(f"Discovered {len(docs)} Nunavut legislation documents")
        return docs

    def _discover_letter(self, letter: str, limit: Optional[int] = None) -> List[DocumentMetadata]:
        """Parse one alphabetical listing page."""
        docs = []
        url = f"{LISTING_URL}?title={letter}"
        try:
            resp = self.session.get(url, timeout=config.TIMEOUT)
            if resp.status_code == 404:
                return docs
            resp.raise_for_status()
            tree = lxml_html.fromstring(resp.text)
            tree.make_links_absolute(url)

            # Each act/regulation is an <article> containing a link
            for article in tree.xpath('//div[@class="view-content"]//article'):
                if limit and len(docs) >= limit:
                    break

                # Find the main link (act or regulation title)
                link = article.xpath('.//a[contains(@href, "/en/consolidated-law/")]')
                if not link:
                    continue
                link = link[0]
                href = link.get("href", "")
                title = (link.text_content() or "").strip()

                if not href or not title or len(title) < 3:
                    continue

                # Skip duplicate links (French/Inuktitut versions)
                if "/fr/" in href or "/iu/" in href:
                    continue

                # Determine document type from title
                is_regulation = self._is_regulation(title)
                doc_type = "regulation" if is_regulation else "legislation"
                category = "Regulation" if is_regulation else "Legislation"

                # Clean up the title
                clean_title = self._clean_title(title)

                # Extract citation hint from title
                citation = self._extract_citation(title)

                docs.append(DocumentMetadata(
                    source_url=href,
                    title=clean_title,
                    citation=citation,
                    jurisdiction_code="nu",
                    category=category,
                    document_type=doc_type,
                    is_active=True,
                    metadata={
                        "doc_class": "regulation" if is_regulation else "statute",
                        "letter": letter,
                    },
                ))

        except Exception as e:
            logger.error(f"Failed to discover Nunavut docs for letter {letter}: {e}")
        return docs

    def fetch_document(self, doc_meta: DocumentMetadata) -> Optional[DocumentContent]:
        """Fetch content from a Nunavut legislation page.

        The page embeds a PDF viewer. We try to find the PDF download link
        and extract text from it. If that fails, we extract whatever text
        is available from the HTML page itself.
        """
        try:
            resp = self.session.get(doc_meta.source_url, timeout=config.TIMEOUT)
            resp.raise_for_status()

            tree = lxml_html.fromstring(resp.text)
            tree.make_links_absolute(doc_meta.source_url)

            # Try to find the PDF download link
            pdf_url = None
            download_links = tree.xpath('//a[contains(@href, "file-download")]/@href')
            if download_links:
                pdf_url = download_links[0]

            content_text = ""
            content_html = ""

            if pdf_url:
                # Download and extract text from PDF
                content_text = self._extract_pdf_text(pdf_url)
                content_html = ""  # PDFs don't have useful HTML

            if not content_text or len(content_text) < 50:
                # Fallback: try to extract text from the embedded PDF viewer
                # or from the page content
                iframe = tree.xpath('//iframe/@src')
                if iframe:
                    pdf_direct = iframe[0]
                    if '.pdf' in pdf_direct:
                        content_text = self._extract_pdf_text(pdf_direct)

            if not content_text or len(content_text) < 50:
                # Last fallback: extract any text from the page body
                body = tree.xpath('//article')
                if body:
                    content_text = self._clean_text(body[0].text_content())
                    content_html = lxml_html.tostring(body[0], encoding='unicode')

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
                jurisdiction_code="nu",
                category=doc_meta.category,
                document_type=doc_meta.document_type,
                is_active=True,
                metadata={
                    **doc_meta.metadata,
                    "source": "nunavut_legislation_ca",
                    "copyright": "Crown copyright — Government of Nunavut",
                    "has_pdf": bool(pdf_url),
                },
            )
        except Exception as e:
            logger.error(f"Failed to fetch Nunavut document {doc_meta.title}: {e}")
            return None

    def _extract_pdf_text(self, pdf_url: str) -> str:
        """Download a PDF and extract its text content."""
        try:
            resp = self.session.get(pdf_url, timeout=60)
            resp.raise_for_status()

            if len(resp.content) < 100:
                return ""

            # Try pymupdf first (fast, accurate)
            try:
                import fitz  # pymupdf
                doc = fitz.open(stream=resp.content, filetype="pdf")
                text_parts = []
                for page in doc:
                    text_parts.append(page.get_text())
                doc.close()
                return self._clean_text('\n'.join(text_parts))
            except ImportError:
                pass

            # Fallback: basic text extraction from PDF binary
            # (very rough, but works for simple text PDFs)
            return self._rough_pdf_text(resp.content)

        except Exception as e:
            logger.warning(f"PDF extraction failed for {pdf_url}: {e}")
            return ""

    def _rough_pdf_text(self, pdf_bytes: bytes) -> str:
        """Very basic PDF text extraction without external libraries."""
        try:
            text = pdf_bytes.decode('latin-1', errors='ignore')
            # Extract text between BT and ET markers (PDF text objects)
            parts = re.findall(r'\(([^)]+)\)', text)
            result = ' '.join(p for p in parts if len(p) > 2 and p.isprintable())
            return self._clean_text(result) if len(result) > 50 else ""
        except Exception:
            return ""

    def _is_regulation(self, title: str) -> bool:
        """Check if a title refers to a regulation rather than an act."""
        t = title.lower()
        return any(kw in t for kw in [
            'regulation', 'order', 'rules', 'by-law',
        ]) and 'act' not in t.split(',')[0].lower()

    def _clean_title(self, title: str) -> str:
        """Clean and normalize a legislation title."""
        # Remove "Consolidation of" / "Official Consolidation of" suffix/prefix
        title = re.sub(r',?\s*(Official\s+)?Consolidation\s+of\s*$', '', title, flags=re.I)
        title = re.sub(r'^Consolidation\s+of\s+', '', title, flags=re.I)
        # Title-case if ALL CAPS
        if title.isupper():
            title = title.title()
        return title.strip()

    def _extract_citation(self, title: str) -> str:
        """Extract a citation hint from the title."""
        # Look for patterns like "S.N.W.T. 1994,c.26" in the title
        match = re.search(r'(S\.(?:Nu|N\.W\.T)\.\s*\d{4}\s*,\s*c\.\s*\d+)', title)
        if match:
            return match.group(1)
        return ""

    def _clean_text(self, text: str) -> str:
        """Normalize whitespace in extracted text."""
        lines = text.split('\n')
        cleaned = [line.strip() for line in lines if line.strip()]
        return '\n'.join(cleaned)
