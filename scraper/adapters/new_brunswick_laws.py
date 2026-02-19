"""
New Brunswick legislation adapter — fetches NB statutes and regulations
from the official laws.gnb.ca website (Irosoft LIMS platform).

Discovery: The statutes index page lists BOTH statutes and their associated
           regulations in order. Regulations follow their parent Act.
           A separate regulations index is also parsed for any regs not
           appearing in the statutes page.

Content:   Server-rendered HTML via Irosoft LIMS

License:   Crown copyright — free for non-commercial use
"""
import re
import time
import requests
from typing import List, Optional, Set
from urllib.parse import urljoin, quote, urlsplit, urlunsplit
from lxml import html as lxml_html

from scraper.adapters import register_adapter
from scraper.adapters.base import BaseSourceAdapter, DocumentMetadata, DocumentContent
from utils.logger import logger
from utils.config import config

BASE_URL = "https://laws.gnb.ca"
STATUTES_URL = f"{BASE_URL}/en/titles?corpus=statutes&selection=all"
REGS_URL = f"{BASE_URL}/en/titles?corpus=regs&selection=all"

# Patterns to distinguish statutes from regulations by chapter format
# Statutes: "2024, c.27", "2011, c.101", "2016, c.28, s.1"
RE_STATUTE_CHAPTER = re.compile(r'^\d{4},\s*c\.')
# Regulations: "2022-80", "84-295", "Rule-57"
RE_REGULATION_CHAPTER = re.compile(r'^\d{2,4}-\d+|^Rule-', re.IGNORECASE)
# Old RSNB style: "A-5.11", "M-17"
RE_RSNB_CHAPTER = re.compile(r'^[A-Z]-[\d.]+$', re.IGNORECASE)

# Generic regulation titles that need parent Act qualification
GENERIC_TITLES = frozenset({
    'general', 'forms', 'fees', 'exemptions', 'exemption',
    'administration', 'procedures', 'procedural', 'designation',
    'enforcement', 'standards', 'licensing', 'inspection',
    'appeal', 'board', 'regions', 'documents', 'qualifications',
})


def _normalize_url(url: str) -> str:
    """Percent-encode commas, spaces, and special chars in URL path for DB consistency.
    Handles already partially-encoded URLs by decoding first to avoid double-encoding."""
    from urllib.parse import unquote
    parts = urlsplit(url)
    # Decode first to avoid double-encoding (e.g. %20 → %2520)
    decoded_path = unquote(parts.path)
    clean_path = quote(decoded_path, safe='/:@!$&\'()*+;=-._~')
    return urlunsplit((parts.scheme, parts.netloc, clean_path, parts.query, parts.fragment))


def _is_statute_chapter(chapter: str) -> bool:
    """Check if chapter format indicates a statute."""
    return bool(RE_STATUTE_CHAPTER.match(chapter)) or bool(RE_RSNB_CHAPTER.match(chapter))


def _is_regulation_chapter(chapter: str) -> bool:
    """Check if chapter format indicates a regulation."""
    return bool(RE_REGULATION_CHAPTER.match(chapter))


def _qualify_title(title: str, chapter: str, parent_act: str) -> str:
    """
    Qualify generic regulation titles with parent Act name.
    e.g. "General" under "Agricultural Development Act" →
         "General — Agricultural Development Act (NB Reg. 84-295)"
    """
    if parent_act and title.lower().strip() in GENERIC_TITLES:
        return f"{title} — {parent_act} (NB Reg. {chapter})"
    return title


@register_adapter('new_brunswick_laws')
class NewBrunswickLawsAdapter(BaseSourceAdapter):
    """Adapter for New Brunswick legislation via Irosoft LIMS."""

    def __init__(self, **kwargs):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "CanadaLegalDataPlatform/1.0",
            "Accept-Language": "en-CA,en;q=0.9",
        })

    def get_source_name(self) -> str:
        return "NB Legislation (Irosoft)"

    def get_source_type(self) -> str:
        return "new_brunswick_laws"

    def get_jurisdiction(self) -> str:
        return "nb"

    def discover_documents(self, limit: Optional[int] = None) -> List[DocumentMetadata]:
        """
        Discover NB statutes and regulations.

        The statutes index page lists both statutes AND their regulations in
        order, so we parse it as a unified list tracking parent Acts. We then
        supplement from the standalone regulations index for any regs not
        already found.
        """
        seen_urls: Set[str] = set()
        docs = []

        # Phase 1: Parse statutes page (contains both statutes + their regs)
        docs.extend(self._discover_from_statutes_page(limit, seen_urls))

        # Phase 2: Parse standalone regs page for any extras
        remaining = (limit - len(docs)) if limit else None
        if remaining is None or remaining > 0:
            docs.extend(self._discover_from_regs_page(remaining, seen_urls))

        logger.info(f"Discovered {len(docs)} NB legislation documents")
        return docs

    def _discover_from_statutes_page(self, limit: Optional[int], seen: Set[str]) -> List[DocumentMetadata]:
        """
        Parse the statutes index page which interleaves statutes and regulations.
        Tracks parent Act name for qualifying generic regulation titles.
        """
        docs = []
        current_act_name = ""

        try:
            resp = self.session.get(STATUTES_URL, timeout=config.TIMEOUT)
            resp.raise_for_status()
            tree = lxml_html.fromstring(resp.text)
            tree.make_links_absolute(STATUTES_URL)

            rows = tree.xpath('//table//tbody//tr')
            if not rows:
                rows = tree.xpath('//table//tr')

            for row in rows:
                if limit and len(docs) >= limit:
                    break
                cells = row.xpath('td | th')
                if len(cells) < 2:
                    continue

                chapter = (cells[0].text_content() or "").strip()
                if not chapter:
                    continue

                title_links = cells[1].xpath('.//a')
                if not title_links:
                    continue
                title_link = title_links[0]
                raw_title = (title_link.text_content() or "").strip()
                href = title_link.get("href", "")

                if not raw_title or not href:
                    continue
                if raw_title.lower() in ('title', 'titre', 'chapter'):
                    continue

                # Determine if this is a statute or regulation
                if _is_statute_chapter(chapter):
                    is_reg = False
                    current_act_name = raw_title
                    doc_prefix = "cs"
                elif _is_regulation_chapter(chapter):
                    is_reg = True
                    doc_prefix = "cr"
                else:
                    # Old-style chapter or ambiguous — treat as statute
                    is_reg = False
                    current_act_name = raw_title
                    doc_prefix = "cs"

                # Qualify generic titles for regulations
                title = _qualify_title(raw_title, chapter, current_act_name) if is_reg else raw_title

                # Build canonical source URL (normalize to percent-encode commas/spaces)
                if f"/en/document/{doc_prefix}/" not in href:
                    source_url = f"{BASE_URL}/en/document/{doc_prefix}/{quote(chapter, safe='')}"
                else:
                    source_url = _normalize_url(href)

                if source_url in seen:
                    continue
                seen.add(source_url)

                docs.append(DocumentMetadata(
                    source_url=source_url,
                    title=title,
                    citation=chapter,
                    jurisdiction_code="nb",
                    category="Regulation" if is_reg else "Legislation",
                    document_type="regulation" if is_reg else "legislation",
                    is_active=True,
                    metadata={
                        "doc_class": "regulation" if is_reg else "statute",
                        "chapter": chapter,
                        "corpus": "regs" if is_reg else "statutes",
                        "content_url": href,
                        "parent_act": current_act_name if is_reg else "",
                    },
                ))

            time.sleep(0.3)

        except Exception as e:
            logger.error(f"Failed to discover NB statutes page: {e}")
        return docs

    def _discover_from_regs_page(self, limit: Optional[int], seen: Set[str]) -> List[DocumentMetadata]:
        """
        Parse the standalone regulations index for any regs not already
        found in the statutes page. These won't have parent Act context.
        """
        docs = []
        try:
            resp = self.session.get(REGS_URL, timeout=config.TIMEOUT)
            resp.raise_for_status()
            tree = lxml_html.fromstring(resp.text)
            tree.make_links_absolute(REGS_URL)

            rows = tree.xpath('//table//tbody//tr')
            if not rows:
                rows = tree.xpath('//table//tr')

            for row in rows:
                if limit and len(docs) >= limit:
                    break
                cells = row.xpath('td | th')
                if len(cells) < 2:
                    continue

                chapter = (cells[0].text_content() or "").strip()
                if not chapter:
                    continue

                title_links = cells[1].xpath('.//a')
                if not title_links:
                    continue
                title_link = title_links[0]
                title = (title_link.text_content() or "").strip()
                href = title_link.get("href", "")

                if not title or not href:
                    continue
                if title.lower() in ('title', 'titre', 'regulation number'):
                    continue

                # Build canonical source URL (normalize to percent-encode commas/spaces)
                if "/en/document/cr/" not in href:
                    source_url = f"{BASE_URL}/en/document/cr/{quote(chapter, safe='')}"
                else:
                    source_url = _normalize_url(href)

                if source_url in seen:
                    continue
                seen.add(source_url)

                # No parent Act context available from the regs-only page,
                # so qualify with chapter number only
                if title.lower().strip() in GENERIC_TITLES:
                    title = f"{title} (NB Reg. {chapter})"

                docs.append(DocumentMetadata(
                    source_url=source_url,
                    title=title,
                    citation=chapter,
                    jurisdiction_code="nb",
                    category="Regulation",
                    document_type="regulation",
                    is_active=True,
                    metadata={
                        "doc_class": "regulation",
                        "chapter": chapter,
                        "corpus": "regs",
                        "content_url": href,
                        "parent_act": "",
                    },
                ))

            time.sleep(0.3)

        except Exception as e:
            logger.error(f"Failed to discover NB regs page: {e}")
        return docs

    def fetch_document(self, doc_meta: DocumentMetadata) -> Optional[DocumentContent]:
        """Fetch full HTML content for a single NB statute or regulation."""
        content_url = doc_meta.metadata.get("content_url", doc_meta.source_url)
        try:
            resp = self.session.get(content_url, timeout=config.TIMEOUT)
            resp.raise_for_status()

            if not resp.text or len(resp.text) < 300:
                logger.warning(f"Empty content for {doc_meta.title}")
                return None

            content_html, content_text = self._parse_html(resp.text)

            if not content_text or len(content_text) < 50:
                logger.warning(f"Could not extract text from {doc_meta.title}")
                return None

            time.sleep(0.5)

            return DocumentContent(
                source_url=doc_meta.source_url,
                title=doc_meta.title,
                citation=doc_meta.citation,
                content_html=content_html,
                content_text=content_text,
                jurisdiction_code="nb",
                category=doc_meta.category,
                document_type=doc_meta.document_type,
                is_active=True,
                metadata={
                    **doc_meta.metadata,
                    "source": "laws_gnb_ca",
                    "platform": "irosoft_lims",
                    "copyright": "Crown copyright — Province of New Brunswick",
                },
            )
        except Exception as e:
            logger.error(f"Failed to fetch NB document {doc_meta.title}: {e}")
            return None

    def _parse_html(self, raw_html: str) -> tuple:
        """Parse Irosoft LIMS document page — extract legislation content."""
        try:
            tree = lxml_html.fromstring(raw_html)
            # Remove scripts, styles, nav
            for tag in tree.xpath('//script | //style | //nav | //header | //footer'):
                tag.getparent().remove(tag)

            # Irosoft puts content in various containers
            content_elem = None
            for selector in [
                '//div[contains(@class, "document-content")]',
                '//div[contains(@class, "legisdoc")]',
                '//div[@id="docContent"]',
                '//div[contains(@class, "content-area")]',
                '//article',
                '//main',
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
