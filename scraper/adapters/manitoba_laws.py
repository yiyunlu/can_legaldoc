"""
Manitoba legislation adapter — fetches Manitoba statutes (CCSM) and
regulations from the official government website.

Discovery: Index tables at web2.gov.mb.ca/laws/
Content:   Server-rendered PHP pages (plain HTML)

License:   OpenMB Licence — free for commercial and non-commercial use
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

BASE_URL = "https://web2.gov.mb.ca/laws"
STATUTES_INDEX = f"{BASE_URL}/statutes/index_ccsm.php"
REGS_INDEX = f"{BASE_URL}/regs/index.php"


@register_adapter('manitoba_laws')
class ManitobaLawsAdapter(BaseSourceAdapter):
    """Adapter for Manitoba legislation (CCSM statutes + regulations)."""

    def __init__(self, **kwargs):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "CanadaLegalDataPlatform/1.0",
        })

    def get_source_name(self) -> str:
        return "Manitoba Legislation (CCSM)"

    def get_source_type(self) -> str:
        return "manitoba_laws"

    def get_jurisdiction(self) -> str:
        return "mb"

    def discover_documents(self, limit: Optional[int] = None) -> List[DocumentMetadata]:
        """Discover Manitoba statutes and regulations."""
        docs = []
        docs.extend(self._discover_statutes(limit))
        remaining = (limit - len(docs)) if limit else None
        if remaining is None or remaining > 0:
            docs.extend(self._discover_regulations(remaining))
        logger.info(f"Discovered {len(docs)} Manitoba legislation documents")
        return docs

    def _discover_statutes(self, limit: Optional[int] = None) -> List[DocumentMetadata]:
        """Parse CCSM statutes index table."""
        docs = []
        try:
            resp = self.session.get(STATUTES_INDEX, timeout=config.TIMEOUT)
            resp.raise_for_status()
            tree = lxml_html.fromstring(resp.text)
            tree.make_links_absolute(STATUTES_INDEX)

            rows = tree.xpath('//table[@id="myTable"]//tr')
            for row in rows:
                if limit and len(docs) >= limit:
                    break
                cells = row.xpath('td')
                if len(cells) < 2:
                    continue

                # Column 1: Chapter number (e.g. "A1.5")
                chapter = (cells[0].text_content() or "").strip()
                if not chapter or chapter.lower() in ('c.c.s.m.', 'chapter'):
                    continue

                # Column 2: Title with link to the act
                title_links = cells[1].xpath('.//a')
                if not title_links:
                    continue
                title_link = title_links[0]
                title = (title_link.text_content() or "").strip()
                href = title_link.get("href", "")

                if not href or not title:
                    continue
                # Skip info links and non-act links
                if "_info" in href or "index" in href:
                    continue

                docs.append(DocumentMetadata(
                    source_url=href,
                    title=title,
                    citation=f"CCSM c {chapter}",
                    jurisdiction_code="mb",
                    category="Legislation",
                    document_type="legislation",
                    is_active=True,
                    metadata={"doc_class": "statute", "chapter": chapter},
                ))
        except Exception as e:
            logger.error(f"Failed to discover Manitoba statutes: {e}")
        return docs

    def _discover_regulations(self, limit: Optional[int] = None) -> List[DocumentMetadata]:
        """Parse regulations index table."""
        docs = []
        try:
            resp = self.session.get(REGS_INDEX, timeout=config.TIMEOUT)
            resp.raise_for_status()
            tree = lxml_html.fromstring(resp.text)
            tree.make_links_absolute(REGS_INDEX)

            rows = tree.xpath('//table[@id="myTable"]//tr')
            for row in rows:
                if limit and len(docs) >= limit:
                    break
                cells = row.xpath('td')
                if len(cells) < 2:
                    continue

                # Look for regulation links in the cells
                reg_links = row.xpath('.//a[contains(@href, "current/") and contains(@href, ".php")]')
                if not reg_links:
                    continue

                link = reg_links[0]
                href = link.get("href", "")
                title = (link.text_content() or "").strip()

                if not href or not title:
                    continue

                # Extract regulation number from URL (e.g. 171-2015.php)
                reg_match = re.search(r'current/(.+?)\.php', href)
                reg_num = reg_match.group(1) if reg_match else ""

                docs.append(DocumentMetadata(
                    source_url=href,
                    title=title,
                    citation=f"Man Reg {reg_num}" if reg_num else "",
                    jurisdiction_code="mb",
                    category="Regulation",
                    document_type="regulation",
                    is_active=True,
                    metadata={"doc_class": "regulation", "reg_number": reg_num},
                ))
        except Exception as e:
            logger.error(f"Failed to discover Manitoba regulations: {e}")
        return docs

    def fetch_document(self, doc_meta: DocumentMetadata) -> Optional[DocumentContent]:
        """Fetch full HTML content for a single Manitoba statute or regulation."""
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
                jurisdiction_code="mb",
                category=doc_meta.category,
                document_type=doc_meta.document_type,
                is_active=True,
                metadata={
                    **doc_meta.metadata,
                    "source": "gov_mb_laws",
                    "licence": "OpenMB Licence",
                },
            )
        except Exception as e:
            logger.error(f"Failed to fetch Manitoba document {doc_meta.title}: {e}")
            return None

    def _parse_html(self, raw_html: str) -> tuple:
        """Parse Manitoba legislation page — extract main content div."""
        try:
            tree = lxml_html.fromstring(raw_html)
            # Remove navigation, scripts, styles
            for tag in tree.xpath('//script | //style | //nav | //header | //footer'):
                tag.getparent().remove(tag)

            # Try to find main content container
            content_elem = None
            for selector in [
                '//div[@id="content"]',
                '//div[@class="content"]',
                '//div[@id="main-content"]',
                '//article',
                '//body',
            ]:
                elems = tree.xpath(selector)
                if elems:
                    content_elem = elems[0]
                    break

            if content_elem is None:
                content_elem = tree

            content_html = lxml_html.tostring(content_elem, encoding='unicode')
            content_text = self._clean_text(content_elem.text_content())
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
