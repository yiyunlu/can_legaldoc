"""
Base adapter interface for all data sources.
All source adapters must subclass BaseSourceAdapter.
"""
from abc import ABC, abstractmethod
from typing import List, Optional, Generator
from dataclasses import dataclass, field
import threading


@dataclass
class DocumentMetadata:
    """Standard document metadata returned by discover_documents()."""
    source_url: str
    title: str
    citation: str = ""
    jurisdiction_code: str = ""
    category: str = "Legislation"
    document_type: str = "legislation"   # legislation, regulation, case_law, constitutional
    is_active: bool = True
    metadata: dict = field(default_factory=dict)


@dataclass
class DocumentContent:
    """Standard document content returned by fetch_document()."""
    source_url: str
    title: str
    citation: str = ""
    content_html: str = ""
    content_text: str = ""
    jurisdiction_code: str = ""
    category: str = "Legislation"
    document_type: str = "legislation"
    is_active: bool = True
    metadata: dict = field(default_factory=dict)

    def to_upsert_dict(self, target_id=None, source_type=None) -> dict:
        """Convert to dict compatible with SupabaseClient.upsert_document_v3()."""
        d = {
            "title": self.title,
            "citation": self.citation,
            "source_url": self.source_url,
            "content_html": self.content_html,
            "content_text": self.content_text,
            "jurisdiction_code": self.jurisdiction_code,
            "category": self.category,
            "is_active": self.is_active,
            "metadata": self.metadata,
        }
        if target_id:
            d["target_id"] = target_id
        if source_type:
            d["source_type"] = source_type
        if self.document_type:
            d["document_type"] = self.document_type
        return d


class BaseSourceAdapter(ABC):
    """
    Abstract base class for all data source adapters.

    Subclasses must implement:
      - get_source_name()
      - get_source_type()
      - get_jurisdiction()
      - discover_documents()
      - fetch_document()

    Optionally override:
      - fetch_documents_batch() for custom bulk loading
    """

    @abstractmethod
    def get_source_name(self) -> str:
        """Human-readable name, e.g. 'Justice Canada XML'."""

    @abstractmethod
    def get_source_type(self) -> str:
        """Machine identifier, e.g. 'justice_canada_xml'."""

    @abstractmethod
    def get_jurisdiction(self) -> str:
        """Primary jurisdiction code, e.g. 'ca', 'bc'. Use 'multi' for cross-jurisdiction sources."""

    @abstractmethod
    def discover_documents(self, limit: Optional[int] = None) -> List[DocumentMetadata]:
        """
        Return a list of available documents (index scan).
        Should be relatively fast — no full content fetching.

        Args:
            limit: max number of documents to discover (None = all)
        """

    @abstractmethod
    def fetch_document(self, doc_meta: DocumentMetadata) -> Optional[DocumentContent]:
        """
        Fetch full content for a single document.

        Args:
            doc_meta: document metadata from discover_documents()

        Returns:
            DocumentContent with full text, or None on failure
        """

    def fetch_documents_batch(
        self,
        docs: List[DocumentMetadata],
        limit: Optional[int] = None,
        stop_event: Optional[threading.Event] = None,
    ) -> Generator[DocumentContent, None, None]:
        """
        Batch fetch documents. Default: sequential.
        Subclasses may override for parallel/bulk fetching.

        Args:
            docs: list of document metadata
            limit: max documents to fetch
            stop_event: threading event to signal stop

        Yields:
            DocumentContent for each successfully fetched document
        """
        count = 0
        for doc in docs:
            if limit is not None and count >= limit:
                break
            if stop_event and stop_event.is_set():
                break
            result = self.fetch_document(doc)
            if result:
                yield result
                count += 1
