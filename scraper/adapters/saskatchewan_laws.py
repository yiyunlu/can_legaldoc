"""
Saskatchewan legislation adapter — fetches SK consolidated statutes and
regulations from the Publications Saskatchewan Freelaw API.

Discovery: REST API at publications.saskatchewan.ca/api/v1/freelaw/acts
Content:   PDF files only (no HTML versions)

API endpoints:
  Acts + Regulations listing: /api/v1/freelaw/acts
  Product details:            /api/v1/products/{productId}
  PDF download:               /api/v1/products/{productId}/formats/{formatId}/download

License:   © Government of Saskatchewan — Office of the King's Printer
"""
import re
import time
import requests
from typing import List, Optional

from scraper.adapters import register_adapter
from scraper.adapters.base import BaseSourceAdapter, DocumentMetadata, DocumentContent
from utils.logger import logger
from utils.config import config

BASE_URL = "https://publications.saskatchewan.ca"
API_BASE = f"{BASE_URL}/api/v1"
FREELAW_ACTS_URL = f"{API_BASE}/freelaw/acts"


@register_adapter('saskatchewan_laws')
class SaskatchewanLawsAdapter(BaseSourceAdapter):
    """Adapter for Saskatchewan legislation (statutes + regulations via PDF)."""

    def __init__(self, **kwargs):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "CanadaLegalDataPlatform/1.0",
            "Accept": "application/json",
        })

    def get_source_name(self) -> str:
        return "Saskatchewan Legislation"

    def get_source_type(self) -> str:
        return "saskatchewan_laws"

    def get_jurisdiction(self) -> str:
        return "sk"

    def discover_documents(self, limit: Optional[int] = None) -> List[DocumentMetadata]:
        """Discover SK acts and regulations via the Freelaw REST API.

        The /api/v1/freelaw/acts endpoint returns all consolidated acts
        with their associated regulations in a single JSON response.
        """
        docs = []
        try:
            resp = self.session.get(FREELAW_ACTS_URL, timeout=config.TIMEOUT)
            resp.raise_for_status()
            data = resp.json()

            for entry in data:
                if limit and len(docs) >= limit:
                    break

                act = entry.get("act", {})
                regulations = entry.get("regulations") or []

                # Process the act
                act_doc = self._build_doc_meta(act, is_regulation=False)
                if act_doc:
                    docs.append(act_doc)

                # Process associated regulations
                for reg in regulations:
                    if limit and len(docs) >= limit:
                        break
                    reg_doc = self._build_doc_meta(reg, is_regulation=True)
                    if reg_doc:
                        docs.append(reg_doc)

        except Exception as e:
            logger.error(f"Failed to discover Saskatchewan legislation: {e}")

        logger.info(f"Discovered {len(docs)} Saskatchewan legislation documents")
        return docs

    def _build_doc_meta(self, product: dict, is_regulation: bool) -> Optional[DocumentMetadata]:
        """Build DocumentMetadata from a product JSON object."""
        product_id = product.get("productId")
        name = (product.get("name") or "").strip()
        if not product_id or not name:
            return None

        # Build a stable source URL using the product page
        source_url = f"{BASE_URL}/#/products/{product_id}"

        # Extract citation — prefer customIdentifier from API, fallback to name parsing
        custom_id = (product.get("customIdentifier") or "").strip()
        citation = self._extract_citation(name, is_regulation, custom_id)

        # Clean up title — remove citation suffix for cleaner display
        title = self._clean_title(name)

        doc_type = "regulation" if is_regulation else "legislation"
        category = "Regulation" if is_regulation else "Legislation"

        return DocumentMetadata(
            source_url=source_url,
            title=title,
            citation=citation,
            jurisdiction_code="sk",
            category=category,
            document_type=doc_type,
            is_active=True,
            metadata={
                "doc_class": "regulation" if is_regulation else "statute",
                "format": "pdf",
                "product_id": product_id,
            },
        )

    def fetch_document(self, doc_meta: DocumentMetadata) -> Optional[DocumentContent]:
        """Fetch product details and download PDF for text extraction."""
        product_id = doc_meta.metadata.get("product_id")
        if not product_id:
            logger.warning(f"No product_id for {doc_meta.title}")
            return None

        try:
            # Step 1: Get product details to find the PDF format ID
            detail_url = f"{API_BASE}/products/{product_id}"
            resp = self.session.get(detail_url, timeout=config.TIMEOUT)
            resp.raise_for_status()
            product = resp.json()

            # Find the digital PDF format
            format_id = None
            for fmt in product.get("productFormats", []):
                if (fmt.get("productFormatMediumType") == "DIGITAL" and
                        "PDF" in (fmt.get("productFormatType") or "").upper()):
                    format_id = fmt.get("productFormatId")
                    break

            if not format_id:
                logger.warning(f"No PDF format found for {doc_meta.title}")
                return None

            # Step 2: Download the PDF
            time.sleep(0.3)
            pdf_url = f"{API_BASE}/products/{product_id}/formats/{format_id}/download"
            pdf_resp = self.session.get(pdf_url, timeout=60)
            pdf_resp.raise_for_status()

            if len(pdf_resp.content) < 200:
                logger.warning(f"Empty PDF for {doc_meta.title}")
                return None

            if not pdf_resp.content[:5].startswith(b'%PDF'):
                logger.warning(f"Not a PDF file: {doc_meta.title}")
                return None

            content_text = self._extract_pdf_text(pdf_resp.content)

            if not content_text or len(content_text) < 50:
                logger.warning(f"Could not extract text from PDF: {doc_meta.title}")
                return None

            # Get description as supplementary HTML content
            desc = (product.get("shortDescriptionEnglish") or
                    product.get("longDescriptionEnglish") or "")

            time.sleep(0.3)

            return DocumentContent(
                source_url=doc_meta.source_url,
                title=doc_meta.title,
                citation=doc_meta.citation,
                content_html=desc,
                content_text=content_text,
                jurisdiction_code="sk",
                category=doc_meta.category,
                document_type=doc_meta.document_type,
                is_active=True,
                metadata={
                    **doc_meta.metadata,
                    "source": "publications_saskatchewan_ca",
                    "copyright": "© Government of Saskatchewan — King's Printer",
                    "pdf_url": pdf_url,
                },
            )
        except Exception as e:
            logger.error(f"Failed to fetch SK document {doc_meta.title}: {e}")
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

    def _extract_citation(self, name: str, is_regulation: bool, custom_id: str = "") -> str:
        """Extract citation from the full product name or customIdentifier.

        Examples:
          "Accounting Profession Act, SS 1986, c A-3.1" → "SS 1986, c A-3.1"
          "Accessible Saskatchewan Regulations, SR 108/2023" → "SR 108/2023"
          "The Animal Products Act, RSS 1978, c A-20" → "RSS 1978, c A-20"
          customIdentifier="A-3.1" → "RSPEI c A-3.1"
        """
        # Try: ", SS YYYY, c X-N.N" or ", RSS YYYY, c X-N"
        m = re.search(r',\s*((?:SS|RSS|RRS)\s+\d{4},\s*c\s+[\w.-]+)$', name)
        if m:
            return m.group(1).strip()
        # Try: ", SR NNN/YYYY"
        m = re.search(r',\s*(SR\s+\d+/\d+)$', name)
        if m:
            return m.group(1).strip()
        # Try: ", RRS c X-N Reg N"
        m = re.search(r',\s*(RRS\s+c\s+[\w.-]+\s+Reg\s+\d+)$', name)
        if m:
            return m.group(1).strip()
        # Fallback: use customIdentifier from API
        if custom_id:
            prefix = "RSS" if not is_regulation else "SK Reg"
            return f"{prefix} c {custom_id}"
        return ""

    def _clean_title(self, name: str) -> str:
        """Remove citation suffix from title for cleaner display."""
        # Remove ", SS YYYY, c..." or ", RSS ..., c..." or ", RRS ..." or ", SR ..."
        title = re.sub(r',\s*(?:SS|RSS|RRS|SR)\s+.*$', '', name).strip()
        # Remove leading "The " — standard SK convention
        return title

    def _clean_text(self, text: str) -> str:
        """Normalize whitespace in extracted text."""
        lines = text.split('\n')
        cleaned = [line.strip() for line in lines if line.strip()]
        return '\n'.join(cleaned)
