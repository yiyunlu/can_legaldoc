"""
Newfoundland and Labrador legislation adapter — fetches NL statutes and
regulations from the House of Assembly website.

Discovery: Index pages at assembly.nl.ca/legislation/sr/
Content:   Static .htm files (plain HTML)

License:   Crown copyright — online version is the official version
"""
import re
import time
import requests
from typing import List, Optional
from urllib.parse import urljoin
from lxml import html as lxml_html

from scraper.adapters import register_adapter
from scraper.adapters.base import BaseSourceAdapter, DocumentMetadata, DocumentContent
from utils.logger import logger
from utils.config import config

BASE_URL = "https://www.assembly.nl.ca"
STATUTES_INDEX = f"{BASE_URL}/legislation/sr/titleindex.htm"
REGS_INDEX = f"{BASE_URL}/legislation/sr/"


@register_adapter('newfoundland_laws')
class NewfoundlandLawsAdapter(BaseSourceAdapter):
    """Adapter for Newfoundland and Labrador legislation (statutes + regulations)."""

    def __init__(self, **kwargs):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "CanadaLegalDataPlatform/1.0",
        })

    def get_source_name(self) -> str:
        return "NL Legislation (Assembly)"

    def get_source_type(self) -> str:
        return "newfoundland_laws"

    def get_jurisdiction(self) -> str:
        return "nl"

    def discover_documents(self, limit: Optional[int] = None) -> List[DocumentMetadata]:
        """Discover NL statutes and regulations from index pages."""
        docs = []
        docs.extend(self._discover_statutes(limit))
        remaining = (limit - len(docs)) if limit else None
        if remaining is None or remaining > 0:
            docs.extend(self._discover_regulations(remaining))
        logger.info(f"Discovered {len(docs)} NL legislation documents")
        return docs

    def _discover_statutes(self, limit: Optional[int] = None) -> List[DocumentMetadata]:
        """Parse statutes index page."""
        docs = []
        try:
            resp = self.session.get(STATUTES_INDEX, timeout=config.TIMEOUT)
            resp.raise_for_status()
            tree = lxml_html.fromstring(resp.text)
            tree.make_links_absolute(STATUTES_INDEX)

            for link in tree.xpath('//a[contains(@href, "statutes/") and contains(@href, ".htm")]'):
                if limit and len(docs) >= limit:
                    break
                href = link.get("href", "")
                title = (link.text_content() or "").strip()
                if not href or not title or len(title) < 3:
                    continue
                # Skip non-statute links (e.g. navigation anchors)
                if "/statutes/" not in href:
                    continue
                # Extract citation from filename (e.g. a01-01.htm → A01-01)
                filename = href.rsplit("/", 1)[-1].replace(".htm", "")
                citation = filename.upper()

                docs.append(DocumentMetadata(
                    source_url=href,
                    title=title.title() if title.isupper() else title,
                    citation=f"SNL {citation}",
                    jurisdiction_code="nl",
                    category="Legislation",
                    document_type="legislation",
                    is_active=True,
                    metadata={"doc_class": "statute", "filename": filename},
                ))
        except Exception as e:
            logger.error(f"Failed to discover NL statutes: {e}")
        return docs

    def _discover_regulations(self, limit: Optional[int] = None) -> List[DocumentMetadata]:
        """Parse regulations index page."""
        docs = []
        try:
            resp = self.session.get(REGS_INDEX, timeout=config.TIMEOUT)
            resp.raise_for_status()
            tree = lxml_html.fromstring(resp.text)
            tree.make_links_absolute(REGS_INDEX)

            for link in tree.xpath('//a[contains(@href, "regulations/") and contains(@href, ".htm")]'):
                if limit and len(docs) >= limit:
                    break
                href = link.get("href", "")
                title = (link.text_content() or "").strip()
                if not href or not title or len(title) < 3:
                    continue
                if "/regulations/" not in href:
                    continue
                filename = href.rsplit("/", 1)[-1].replace(".htm", "")
                citation = filename.upper()

                docs.append(DocumentMetadata(
                    source_url=href,
                    title=title.title() if title.isupper() else title,
                    citation=f"NLR {citation}",
                    jurisdiction_code="nl",
                    category="Regulation",
                    document_type="regulation",
                    is_active=True,
                    metadata={"doc_class": "regulation", "filename": filename},
                ))
        except Exception as e:
            logger.error(f"Failed to discover NL regulations: {e}")
        return docs

    def fetch_document(self, doc_meta: DocumentMetadata) -> Optional[DocumentContent]:
        """Fetch full HTML content for a single NL statute or regulation."""
        try:
            resp = self.session.get(doc_meta.source_url, timeout=config.TIMEOUT)
            resp.raise_for_status()

            if not resp.text or len(resp.text) < 200:
                logger.warning(f"Empty content for {doc_meta.title}")
                return None

            content_html, content_text = self._parse_html(resp.text, doc_meta.source_url)

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
                jurisdiction_code="nl",
                category=doc_meta.category,
                document_type=doc_meta.document_type,
                is_active=True,
                metadata={
                    **doc_meta.metadata,
                    "source": "assembly_nl",
                    "copyright": "Crown copyright — Government of Newfoundland and Labrador",
                },
            )
        except Exception as e:
            logger.error(f"Failed to fetch NL document {doc_meta.title}: {e}")
            return None

    def _parse_html(self, raw_html: str, base_url: str) -> tuple:
        """Parse NL legislation HTML — skip style blocks, extract body content."""
        try:
            tree = lxml_html.fromstring(raw_html)
            # Remove all <style> elements (NL pages have huge embedded CSS)
            for style in tree.xpath('//style'):
                style.getparent().remove(style)
            # Remove script tags
            for script in tree.xpath('//script'):
                script.getparent().remove(script)

            body = tree.xpath('//body')
            elem = body[0] if body else tree

            content_html = lxml_html.tostring(elem, encoding='unicode')
            content_text = self._clean_text(elem.text_content())
            return content_html, content_text
        except Exception as e:
            logger.error(f"HTML parse error: {e}")
            text = re.sub(r'<[^>]+>', ' ', raw_html)
            text = re.sub(r'\s+', ' ', text).strip()
            return raw_html, text

    def _clean_text(self, text: str) -> str:
        """Normalize whitespace in extracted text."""
        lines = text.split('\n')
        cleaned = [line.strip() for line in lines if line.strip()]
        return '\n'.join(cleaned)
