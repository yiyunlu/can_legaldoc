"""
BC Laws CiviX API adapter — fetches British Columbia legislation from the
official BC Laws API: bclaws.gov.bc.ca/civix/

The CiviX directory is structured as:
  /statreg/               → 25 alphabetical letter dirs (-- A --, -- B --, ...)
  /statreg/{letter_id}/   → statute/regulation dirs per letter
  /statreg/{letter_id}/{statute_id}/  → document + regulations + history

QP License 1.0 — worldwide, royalty-free, perpetual, non-exclusive.
"""
import time
import requests
from typing import List, Optional
from lxml import etree

from scraper.adapters import register_adapter
from scraper.adapters.base import BaseSourceAdapter, DocumentMetadata, DocumentContent
from utils.logger import logger
from utils.config import config


BASE_API = "https://www.bclaws.gov.bc.ca/civix"
DIRECTORY_URL = f"{BASE_API}/content/complete/statreg/"
DOCUMENT_URL_TEMPLATE = f"{BASE_API}/document/id/complete/statreg/{{doc_id}}/xml"
WEB_URL_TEMPLATE = "https://www.bclaws.gov.bc.ca/civix/document/id/complete/statreg/{doc_id}"


@register_adapter('bc_laws_api')
class BCLawsAPIAdapter(BaseSourceAdapter):
    """
    Adapter for BC legislation via the CiviX REST API.
    Provides full XML text of all BC statutes and regulations.
    """

    def __init__(self, base_api_url: str = None, **kwargs):
        self.base_api = base_api_url or BASE_API
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/xml",
            "User-Agent": "CanadaLegalDataPlatform/1.0",
        })

    def get_source_name(self) -> str:
        return "BC Laws API (CiviX)"

    def get_source_type(self) -> str:
        return "bc_laws_api"

    def get_jurisdiction(self) -> str:
        return "bc"

    def discover_documents(self, limit: Optional[int] = None) -> List[DocumentMetadata]:
        """
        Fetch the full directory listing from CiviX API by crawling
        into each alphabetical letter directory.
        Returns metadata for all BC statutes and regulations.
        """
        docs = []
        try:
            logger.info("Fetching BC Laws top-level directory from CiviX API...")
            resp = self.session.get(DIRECTORY_URL, timeout=config.TIMEOUT)
            resp.raise_for_status()
            root = etree.fromstring(resp.content)

            # Collect letter directories (-- A --, -- B --, etc.)
            letter_dirs = []
            for child in root:
                tag = self._local_tag(child)
                if tag != 'dir':
                    continue
                dir_id = self._get_child_text(child, 'CIVIX_DOCUMENT_ID')
                dir_title = self._get_child_text(child, 'CIVIX_DOCUMENT_TITLE')
                if dir_title.startswith('--'):
                    letter_dirs.append((dir_id, dir_title))

            logger.info(f"Found {len(letter_dirs)} letter directories, crawling each...")

            # Crawl each letter directory for statute entries
            for dir_id, dir_title in letter_dirs:
                if limit and len(docs) >= limit:
                    break

                letter_docs = self._fetch_letter_directory(dir_id, dir_title, limit, len(docs))
                docs.extend(letter_docs)
                time.sleep(0.3)  # Rate limiting between letter requests

            logger.info(f"Discovered {len(docs)} BC documents across {len(letter_dirs)} letter groups")

        except Exception as e:
            logger.error(f"Failed to discover BC Laws documents: {e}")

        return docs

    def _fetch_letter_directory(self, dir_id: str, dir_title: str,
                                global_limit: Optional[int], current_count: int) -> List[DocumentMetadata]:
        """Fetch all statute/regulation entries within one letter directory."""
        docs = []
        try:
            url = f"{self.base_api}/content/complete/statreg/{dir_id}/"
            resp = self.session.get(url, timeout=config.TIMEOUT)
            resp.raise_for_status()
            root = etree.fromstring(resp.content)

            for child in root:
                if global_limit and (current_count + len(docs)) >= global_limit:
                    break

                tag = self._local_tag(child)
                if tag != 'dir':
                    continue

                doc_id = self._get_child_text(child, 'CIVIX_DOCUMENT_ID')
                title = self._get_child_text(child, 'CIVIX_DOCUMENT_TITLE')

                if not doc_id or not title:
                    continue

                source_url = WEB_URL_TEMPLATE.format(doc_id=doc_id)

                # Infer type from title
                title_lower = title.lower()
                is_act = 'act' in title_lower and 'regulation' not in title_lower
                doc_type = "legislation" if is_act else "regulation"
                category = "Legislation" if is_act else "Regulation"

                docs.append(DocumentMetadata(
                    source_url=source_url,
                    title=title,
                    citation=doc_id,
                    jurisdiction_code="bc",
                    category=category,
                    document_type=doc_type,
                    is_active=True,
                    metadata={"civix_id": doc_id, "letter_dir_id": dir_id, "letter_group": dir_title},
                ))

            logger.debug(f"  {dir_title}: {len(docs)} items")

        except Exception as e:
            logger.error(f"Failed to fetch letter directory {dir_title} ({dir_id}): {e}")

        return docs

    def _local_tag(self, elem) -> str:
        """Get the local tag name, stripping any namespace."""
        return etree.QName(elem.tag).localname if '}' in str(elem.tag) else elem.tag

    def _get_child_text(self, elem, child_tag: str) -> str:
        """Get text of a direct child element by local tag name."""
        for child in elem:
            if self._local_tag(child) == child_tag:
                return (child.text or '').strip()
        return ''

    def _resolve_document_id(self, dir_id: str, letter_dir_id: str) -> Optional[str]:
        """Resolve the actual fetchable document ID from a statute directory.

        The CiviX directory uses directory IDs (e.g. '96001') but the actual
        document has a different ID (e.g. '96001_01' or '21033'). We fetch the
        statute directory listing to find the first <document> child.
        """
        try:
            stat_url = f"{self.base_api}/content/complete/statreg/{letter_dir_id}/{dir_id}/"
            resp = self.session.get(stat_url, timeout=config.TIMEOUT)
            resp.raise_for_status()
            root = etree.fromstring(resp.content)

            for child in root:
                if self._local_tag(child) == 'document':
                    real_id = self._get_child_text(child, 'CIVIX_DOCUMENT_ID')
                    if real_id:
                        return real_id
        except Exception as e:
            logger.debug(f"Failed to resolve document ID for {dir_id}: {e}")

        # Fallback: common convention {dir_id}_01
        return f"{dir_id}_01"

    def fetch_document(self, doc_meta: DocumentMetadata) -> Optional[DocumentContent]:
        """Fetch full XML content for a single BC statute/regulation."""
        dir_id = doc_meta.metadata.get("civix_id", doc_meta.citation)
        if not dir_id:
            logger.error(f"No CiviX ID for {doc_meta.title}")
            return None

        try:
            # Resolve the actual document ID from the directory
            letter_dir_id = doc_meta.metadata.get("letter_dir_id", "")
            real_doc_id = self._resolve_document_id(dir_id, letter_dir_id)

            url = DOCUMENT_URL_TEMPLATE.format(doc_id=real_doc_id)
            logger.debug(f"Fetching BC document: {dir_id} -> {real_doc_id}")

            resp = self.session.get(url, timeout=config.TIMEOUT)
            resp.raise_for_status()

            if not resp.content:
                logger.error(f"Empty content for BC document {dir_id} (resolved: {real_doc_id})")
                return None

            root = etree.fromstring(resp.content)
            content_html = etree.tostring(root, pretty_print=True, encoding='unicode')
            content_text = self._extract_text(root)

            time.sleep(0.5)  # Rate limiting

            return DocumentContent(
                source_url=doc_meta.source_url,
                title=doc_meta.title,
                citation=doc_meta.citation,
                content_html=content_html,
                content_text=content_text,
                jurisdiction_code="bc",
                category=doc_meta.category,
                document_type=doc_meta.document_type,
                is_active=True,
                metadata={**doc_meta.metadata, "real_doc_id": real_doc_id},
            )
        except Exception as e:
            logger.error(f"Failed to fetch BC document {dir_id}: {e}")
            return None

    def _extract_text(self, root) -> str:
        """Extract plain text from BC Laws XML."""
        parts = []
        for elem in root.iter():
            if elem.text and elem.text.strip():
                parts.append(elem.text.strip())
            if elem.tail and elem.tail.strip():
                parts.append(elem.tail.strip())
        return '\n'.join(parts)
