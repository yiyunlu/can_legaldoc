"""
Ontario e-Laws adapter — fetches Ontario statutes and regulations
from the official e-Laws website (ontario.ca/laws).

Uses the undocumented e-Laws REST API (Elasticsearch-backed) for both
discovery and content fetching. No browser/Playwright required.

Discovery: GET /laws/api/v2/legislation/en/browse-search (A-Z)
Content:   GET /laws/api/v2/legislation/en/doc-search/{type}/{id}

License:   Crown copyright — free to reproduce if not represented as official
"""
import re
import time
import string
import requests
from typing import List, Optional
from lxml import html as lxml_html

from scraper.adapters import register_adapter
from scraper.adapters.base import BaseSourceAdapter, DocumentMetadata, DocumentContent
from utils.logger import logger
from utils.config import config

BASE_URL = "https://www.ontario.ca"
API_BASE = f"{BASE_URL}/laws/api/v2/legislation/en"
BROWSE_URL = f"{API_BASE}/browse-search"
DOC_URL_TEMPLATE = f"{API_BASE}/doc-search/{{type}}/{{id}}"

REQUEST_DELAY = config.REQUEST_DELAY
TIMEOUT = config.TIMEOUT
MAX_RETRIES = config.MAX_RETRIES


def _get(url, params=None, retries=MAX_RETRIES):
    """GET with retries and Accept: application/json."""
    headers = {"Accept": "application/json", "User-Agent": "CanadianLegalDataPlatform/5.5"}
    for attempt in range(retries + 1):
        try:
            r = requests.get(url, params=params, headers=headers, timeout=TIMEOUT)
            if r.status_code == 200:
                return r
            if r.status_code >= 500 and attempt < retries:
                time.sleep(2 ** attempt)
                continue
            return r
        except requests.RequestException as e:
            if attempt < retries:
                time.sleep(2 ** attempt)
                continue
            raise
    return None


@register_adapter('ontario_elaws')
class OntarioELawsAdapter(BaseSourceAdapter):
    """
    Adapter for Ontario e-Laws using the REST API.
    No Playwright or headless browser required.
    """

    def get_source_name(self) -> str:
        return "Ontario e-Laws"

    def get_source_type(self) -> str:
        return "ontario_elaws"

    def get_jurisdiction(self) -> str:
        return "on"

    def discover_documents(self, limit: Optional[int] = None) -> List[DocumentMetadata]:
        """
        Discover Ontario statutes and regulations via the browse-search API.
        Iterates A-Z for each document type.
        """
        docs = []
        seen_aliases = set()

        for doc_type in ["statute", "regulation"]:
            if limit and len(docs) >= limit:
                break
            remaining = (limit - len(docs)) if limit else None
            found = self._discover_by_type(doc_type, remaining, seen_aliases)
            docs.extend(found)

        logger.info(f"Discovered {len(docs)} Ontario e-Laws documents")
        return docs

    def _discover_by_type(self, doc_type: str, limit: Optional[int], seen: set) -> List[DocumentMetadata]:
        """Browse A-Z for statutes or regulations."""
        docs = []

        for letter in string.ascii_uppercase:
            if limit and len(docs) >= limit:
                break

            try:
                params = {
                    "text": letter,
                    "selection": "current",
                    "result": doc_type,
                    "page": 1,
                    "pageSize": 500,  # max aggregation inner window
                    "sort": "AZ",
                }
                resp = _get(BROWSE_URL, params=params)
                if not resp or resp.status_code != 200:
                    logger.warning(f"Ontario browse-search failed for {letter}/{doc_type}: HTTP {resp.status_code if resp else 'N/A'}")
                    continue

                data = resp.json()
                buckets = (data.get("aggregations", {})
                               .get("act", {})
                               .get("buckets", []))

                for bucket in buckets:
                    if limit and len(docs) >= limit:
                        break

                    # Each bucket has statute.statute_hits and regulation.regulation_hits
                    hits_key = f"{doc_type}_hits"
                    container = bucket.get(doc_type, {}).get(hits_key, {}).get("hits", {}).get("hits", [])

                    for hit in container:
                        if limit and len(docs) >= limit:
                            break

                        source = hit.get("_source", {})
                        alias = source.get("alias", {}).get("en", "")
                        title = source.get("title", {}).get("en", "")

                        if not alias or not title:
                            continue
                        if alias in seen:
                            continue
                        seen.add(alias)

                        # alias format: "statute/90a02" or "regulation/990"
                        full_url = f"{BASE_URL}/laws/{alias}"
                        parts = alias.split("/", 1)
                        url_id = parts[1] if len(parts) > 1 else alias

                        is_reg = doc_type == "regulation"

                        docs.append(DocumentMetadata(
                            source_url=full_url,
                            title=title,
                            citation=url_id.upper(),
                            jurisdiction_code="on",
                            category="Regulation" if is_reg else "Legislation",
                            document_type="regulation" if is_reg else "legislation",
                            is_active=True,
                            metadata={
                                "doc_class": doc_type,
                                "url_id": url_id,
                                "alias": alias,
                                "letter": letter,
                                "state": source.get("state", {}).get("en", ""),
                                "date_from": source.get("dateFrom", {}).get("en", ""),
                            },
                        ))

                logger.debug(f"  Letter {letter}/{doc_type}: {len(buckets)} acts → total {len(docs)}")

            except Exception as e:
                logger.warning(f"Ontario browse failed for {letter}/{doc_type}: {e}")
                continue

            time.sleep(REQUEST_DELAY * 0.3)

        return docs

    def fetch_document(self, doc_meta: DocumentMetadata) -> Optional[DocumentContent]:
        """Fetch full HTML content via the doc-search API."""
        alias = doc_meta.metadata.get("alias", "")
        if not alias:
            # Try to reconstruct from URL: /laws/statute/90a02 → statute/90a02
            path = doc_meta.source_url.replace(f"{BASE_URL}/laws/", "")
            alias = path

        parts = alias.split("/", 1)
        if len(parts) != 2:
            logger.warning(f"Invalid alias format: {alias}")
            return None

        doc_type, doc_id = parts

        url = DOC_URL_TEMPLATE.format(type=doc_type, id=doc_id)

        try:
            resp = _get(url)
            if not resp or resp.status_code != 200:
                logger.warning(f"Ontario doc-search failed for {alias}: HTTP {resp.status_code if resp else 'N/A'}")
                return None

            data = resp.json()
            content_html = data.get("content", "")
            title = data.get("title", doc_meta.title)
            chapter = data.get("chapter", "")

            if not content_html or len(content_html) < 50:
                logger.warning(f"Insufficient content for {doc_meta.title}")
                return None

            # Extract plain text from the HTML content
            content_text = self._html_to_text(content_html)

            if not content_text or len(content_text) < 30:
                logger.warning(f"Could not extract text for {doc_meta.title}")
                return None

            # Add chapter info to content_html if present
            if chapter:
                content_html = chapter + "\n" + content_html

            time.sleep(REQUEST_DELAY)

            return DocumentContent(
                source_url=doc_meta.source_url,
                title=title,
                citation=doc_meta.citation,
                content_html=content_html,
                content_text=content_text,
                jurisdiction_code="on",
                category=doc_meta.category,
                document_type=doc_meta.document_type,
                is_active=True,
                metadata={
                    **doc_meta.metadata,
                    "source": "ontario_elaws",
                    "copyright": "Crown copyright — Province of Ontario",
                    "act_name": data.get("actName", {}).get("en", ""),
                    "state": data.get("state", ""),
                    "date_from": data.get("dateFrom", ""),
                    "doc_source": data.get("docSource", ""),
                },
            )

        except Exception as e:
            logger.error(f"Failed to fetch Ontario document {doc_meta.title}: {e}")
            return None

    @staticmethod
    def _html_to_text(raw_html: str) -> str:
        """Convert HTML content to plain text."""
        try:
            tree = lxml_html.fromstring(raw_html)
            # Remove script/style
            for el in tree.iter("script", "style"):
                el.drop_tree()
            text = tree.text_content()
        except Exception:
            text = re.sub(r'<[^>]+>', ' ', raw_html)

        lines = text.split('\n')
        cleaned = [line.strip() for line in lines if line.strip()]
        return '\n'.join(cleaned)
