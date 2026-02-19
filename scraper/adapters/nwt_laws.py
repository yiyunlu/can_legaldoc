"""
Northwest Territories legislation adapter — fetches NWT consolidated
statutes and regulations from the Department of Justice website.

Discovery: Single tree-based listing page at justice.gov.nt.ca/en/legislation/
           Each act folder links to PDF files for the act and its regulations.
Content:   PDF files only (no HTML versions)

URL pattern:
  Acts:        /en/files/legislation/{slug}/{slug}.a.pdf
  Regulations: /en/files/legislation/{slug}/{slug}.r1.pdf, .r2.pdf, etc.

License:   Crown copyright — may be used for non-commercial purposes
           with acknowledgment of the Government of NWT
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

BASE_URL = "https://www.justice.gov.nt.ca"
LISTING_URL = f"{BASE_URL}/en/legislation/"


@register_adapter('nwt_laws')
class NWTLawsAdapter(BaseSourceAdapter):
    """Adapter for Northwest Territories legislation (statutes + regulations via PDF)."""

    def __init__(self, **kwargs):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "CanadaLegalDataPlatform/1.0",
        })

    def get_source_name(self) -> str:
        return "NWT Legislation"

    def get_source_type(self) -> str:
        return "nwt_laws"

    def get_jurisdiction(self) -> str:
        return "nt"

    def discover_documents(self, limit: Optional[int] = None) -> List[DocumentMetadata]:
        """Discover NWT legislation from the main listing page.

        The page uses a tree widget with folders for each letter (A-Z),
        and each folder contains act entries. We parse the full HTML page
        which contains all the tree data.
        """
        docs = []
        try:
            resp = self.session.get(LISTING_URL, timeout=config.TIMEOUT)
            resp.raise_for_status()
            tree = lxml_html.fromstring(resp.text)
            tree.make_links_absolute(LISTING_URL)

            # Find all PDF links in the file browser tree
            pdf_links = tree.xpath(
                '//a[contains(@href, "/en/files/legislation/") and contains(@href, ".pdf")]'
            )

            for link in pdf_links:
                if limit and len(docs) >= limit:
                    break

                href = link.get("href", "")
                title = (link.text_content() or "").strip()

                if not href or not title or len(title) < 3:
                    continue

                # Determine if this is an act or regulation
                is_regulation = self._is_regulation_url(href, title)
                doc_type = "regulation" if is_regulation else "legislation"
                category = "Regulation" if is_regulation else "Legislation"

                # Extract slug from URL
                slug = self._extract_slug(href)
                citation = self._build_citation(title, is_regulation)

                docs.append(DocumentMetadata(
                    source_url=href,
                    title=title,
                    citation=citation,
                    jurisdiction_code="nt",
                    category=category,
                    document_type=doc_type,
                    is_active=True,
                    metadata={
                        "doc_class": "regulation" if is_regulation else "statute",
                        "slug": slug,
                        "format": "pdf",
                    },
                ))

            # If the tree wasn't expanded (JS-rendered), try parsing folder links
            if not docs:
                docs = self._discover_from_folders(tree, limit)

        except Exception as e:
            logger.error(f"Failed to discover NWT legislation: {e}")

        logger.info(f"Discovered {len(docs)} NWT legislation documents")
        return docs

    def _discover_from_folders(self, tree, limit: Optional[int] = None) -> List[DocumentMetadata]:
        """Fallback: parse folder links and probe for PDF files."""
        docs = []
        # Find folder links (act names in the tree)
        folder_links = tree.xpath(
            '//a[contains(@href, "#gn-filebrowse-0:/") and not(contains(@href, "Complete"))]'
        )

        seen_slugs = set()
        for link in folder_links:
            if limit and len(docs) >= limit:
                break

            href = link.get("href", "")
            title = (link.text_content() or "").strip()

            if not title or len(title) < 2:
                continue

            # Skip letter-only entries (A, B, C...)
            if len(title) <= 2 and title.isalpha():
                continue

            # Extract slug from the anchor
            match = re.search(r'#gn-filebrowse-0:/[a-z]/([^/]+)/', href)
            if not match:
                continue

            slug = match.group(1)
            if slug in seen_slugs:
                continue
            seen_slugs.add(slug)

            # Construct the act PDF URL
            pdf_url = f"{BASE_URL}/en/files/legislation/{slug}/{slug}.a.pdf"

            # Get the department info if available
            dept_elem = link.getnext()
            department = ""
            if dept_elem is not None:
                department = (dept_elem.text_content() or "").strip()

            docs.append(DocumentMetadata(
                source_url=pdf_url,
                title=f"{title}",
                citation=f"RSNWT {title[:30]}",
                jurisdiction_code="nt",
                category="Legislation",
                document_type="legislation",
                is_active=True,
                metadata={
                    "doc_class": "statute",
                    "slug": slug,
                    "format": "pdf",
                    "department": department,
                },
            ))

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
                jurisdiction_code="nt",
                category=doc_meta.category,
                document_type=doc_meta.document_type,
                is_active=True,
                metadata={
                    **doc_meta.metadata,
                    "source": "justice_gov_nt",
                    "copyright": "Crown copyright — Government of the Northwest Territories",
                },
            )
        except Exception as e:
            logger.error(f"Failed to fetch NWT document {doc_meta.title}: {e}")
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

    def _is_regulation_url(self, url: str, title: str) -> bool:
        """Determine if a PDF link is for a regulation vs an act."""
        # URL-based: .r1.pdf, .r2.pdf etc. are regulations; .a.pdf is the act
        if re.search(r'\.r\d+\.pdf$', url):
            return True
        if url.endswith('.a.pdf'):
            return False
        # Title-based fallback
        t = title.lower()
        return any(kw in t for kw in ['regulation', 'rules', 'order']) and 'act' not in t

    def _extract_slug(self, url: str) -> str:
        """Extract the legislation slug from a PDF URL."""
        match = re.search(r'/legislation/([^/]+)/', url)
        return match.group(1) if match else ""

    def _build_citation(self, title: str, is_regulation: bool) -> str:
        """Build a citation string from the title."""
        prefix = "NWT Reg" if is_regulation else "RSNWT"
        return f"{prefix} — {title[:50]}"

    def _clean_text(self, text: str) -> str:
        """Normalize whitespace in extracted text."""
        lines = text.split('\n')
        cleaned = [line.strip() for line in lines if line.strip()]
        return '\n'.join(cleaned)
