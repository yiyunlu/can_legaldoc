"""
A2AJ Case Law adapter — fetches Canadian court decisions from the A2AJ
Hugging Face dataset: huggingface.co/datasets/a2aj/canadian-case-law

185,000+ decisions covering SCC, Federal Court, FCA, Tax Court, CHRT,
IRB-RAD, SST, and select BC/ON courts.

License: MIT (code); upstream document licenses vary.
"""
import threading
from typing import List, Optional, Generator

from scraper.adapters import register_adapter
from scraper.adapters.base import BaseSourceAdapter, DocumentMetadata, DocumentContent
from utils.logger import logger


# Map A2AJ 'dataset' field values to jurisdiction codes.
# The dataset uses uppercase abbreviations like 'SCC', 'BCCA', 'FCA', etc.
COURT_TO_JURISDICTION = {
    'SCC': 'ca',             # Supreme Court of Canada
    'SCC-L': 'ca',           # SCC Leave applications
    'FCA': 'ca',             # Federal Court of Appeal
    'FC': 'ca',              # Federal Court
    'TCC': 'ca',             # Tax Court of Canada
    'CMAC': 'ca',            # Court Martial Appeal Court
    'CHRT': 'ca',            # Canadian Human Rights Tribunal
    'SST': 'ca',             # Social Security Tribunal
    'IRB-RAD': 'ca',         # Immigration and Refugee Board - RAD
    'BCCA': 'bc',            # BC Court of Appeal
    'BCSC': 'bc',            # BC Supreme Court
    'ONCA': 'on',            # Ontario Court of Appeal
    'ONSC': 'on',            # Ontario Superior Court
    'ABCA': 'ab',            # Alberta Court of Appeal
    'ABQB': 'ab',            # Alberta Court of Queen's/King's Bench
    'SKCA': 'sk',            # Saskatchewan Court of Appeal
    'MBCA': 'mb',            # Manitoba Court of Appeal
    'NBCA': 'nb',            # New Brunswick Court of Appeal
    'NSCA': 'ns',            # Nova Scotia Court of Appeal
    'PECA': 'pe',            # PEI Court of Appeal
    'NLCA': 'nl',            # Newfoundland Court of Appeal
    'YKCA': 'yt',            # Yukon Court of Appeal
    'NWTCA': 'nt',           # NWT Court of Appeal
    'NUCA': 'nu',            # Nunavut Court of Appeal
}


@register_adapter('a2aj_case_law')
class A2AJCaseLawAdapter(BaseSourceAdapter):
    """
    Adapter for Canadian case law from the A2AJ Hugging Face dataset.
    Uses streaming mode to handle 185K+ records efficiently.
    """

    def __init__(self, dataset_name: str = "a2aj/canadian-case-law",
                 streaming: bool = True, **kwargs):
        self.dataset_name = dataset_name
        self.streaming = streaming
        self._dataset = None

    def get_source_name(self) -> str:
        return "A2AJ Canadian Case Law (Hugging Face)"

    def get_source_type(self) -> str:
        return "a2aj_case_law"

    def get_jurisdiction(self) -> str:
        return "multi"

    def _load_dataset(self):
        """Lazy-load the Hugging Face dataset."""
        if self._dataset is None:
            try:
                from datasets import load_dataset
                logger.info(f"Loading dataset: {self.dataset_name} (streaming={self.streaming})")
                self._dataset = load_dataset(
                    self.dataset_name,
                    streaming=self.streaming,
                )
                logger.info("A2AJ dataset loaded successfully")
            except Exception as e:
                logger.error(f"Failed to load A2AJ dataset: {e}")
                raise
        return self._dataset

    def _resolve_jurisdiction(self, record: dict) -> str:
        """Map court identifier from dataset to jurisdiction code."""
        court = (record.get('dataset', '') or '').strip().upper()
        if court in COURT_TO_JURISDICTION:
            return COURT_TO_JURISDICTION[court]
        # Try partial match for variants
        for key, jur in COURT_TO_JURISDICTION.items():
            if key in court:
                return jur
        return 'ca'

    def _clean_field(self, record: dict, field: str) -> str:
        """Get a field value, treating 'None' strings as empty."""
        val = record.get(field, '') or ''
        if isinstance(val, str) and val.strip() == 'None':
            return ''
        return str(val).strip()

    def _record_to_metadata(self, record: dict) -> DocumentMetadata:
        """Convert a dataset record to DocumentMetadata.

        A2AJ fields: dataset, citation_en, citation2_en, name_en,
        document_date_en, url_en, unofficial_text_en (+ _fr variants).
        """
        court = self._clean_field(record, 'dataset')
        url = self._clean_field(record, 'url_en') or self._clean_field(record, 'url_fr')
        title = self._clean_field(record, 'name_en') or self._clean_field(record, 'name_fr')
        citation = self._clean_field(record, 'citation_en') or self._clean_field(record, 'citation_fr')
        date = self._clean_field(record, 'document_date_en') or self._clean_field(record, 'document_date_fr')

        # Use citation as fallback URL identifier
        if not url and citation:
            url = f"a2aj://case/{citation.replace(' ', '_')}"

        return DocumentMetadata(
            source_url=url,
            title=title or citation,
            citation=citation,
            jurisdiction_code=self._resolve_jurisdiction(record),
            category="Case Law",
            document_type="case_law",
            is_active=True,
            metadata={
                "court": court,
                "date": date,
            },
        )

    def _record_to_content(self, record: dict) -> DocumentContent:
        """Convert a dataset record to DocumentContent."""
        meta = self._record_to_metadata(record)

        # A2AJ provides text in 'unofficial_text_en' / 'unofficial_text_fr'
        content_text = self._clean_field(record, 'unofficial_text_en')
        if not content_text:
            content_text = self._clean_field(record, 'unofficial_text_fr')

        return DocumentContent(
            source_url=meta.source_url,
            title=meta.title,
            citation=meta.citation,
            content_html='',  # A2AJ only provides plain text
            content_text=content_text,
            jurisdiction_code=meta.jurisdiction_code,
            category="Case Law",
            document_type="case_law",
            is_active=True,
            metadata=meta.metadata,
        )

    def discover_documents(self, limit: Optional[int] = None) -> List[DocumentMetadata]:
        """
        Discover available case law documents.
        In streaming mode, only reads up to `limit` records.

        NOTE: Without a limit, this streams all 185K records. For full ingestion,
        prefer using fetch_documents_batch() directly which avoids holding all
        metadata in memory.
        """
        ds = self._load_dataset()
        docs = []

        # Default cap to prevent OOM when no limit specified
        effective_limit = limit if limit is not None else 185000

        try:
            split = ds.get('train') or ds.get('test') or next(iter(ds.values()))

            for record in split:
                if len(docs) >= effective_limit:
                    break
                meta = self._record_to_metadata(record)
                if meta.source_url:
                    docs.append(meta)

        except Exception as e:
            logger.error(f"Error during A2AJ discovery: {e}")

        logger.info(f"Discovered {len(docs)} case law documents from A2AJ")
        return docs

    def fetch_document(self, doc_meta: DocumentMetadata) -> Optional[DocumentContent]:
        """
        For A2AJ, discover_documents and fetch are combined since the dataset
        already contains full text. This method is for individual lookups.
        """
        # In batch mode, we use fetch_documents_batch which is more efficient.
        # This single-document fetch is a fallback.
        logger.warning("A2AJ single-document fetch is inefficient; use fetch_documents_batch")
        return None

    def fetch_documents_batch(
        self,
        docs: List[DocumentMetadata],
        limit: Optional[int] = None,
        stop_event: Optional[threading.Event] = None,
    ) -> Generator[DocumentContent, None, None]:
        """
        Efficient batch loading — streams directly from dataset.
        Since A2AJ includes full text, we can yield directly from the dataset
        without additional network requests.
        """
        ds = self._load_dataset()
        count = 0

        # Build a set of URLs we want to fetch for fast lookup
        target_urls = {d.source_url for d in docs} if docs else None

        try:
            split = ds.get('train') or ds.get('test') or next(iter(ds.values()))

            for record in split:
                if limit is not None and count >= limit:
                    break
                if stop_event and stop_event.is_set():
                    break

                content = self._record_to_content(record)

                # If we have a target list, filter to only matching URLs
                if target_urls and content.source_url not in target_urls:
                    continue

                if content.content_text or content.content_html:
                    yield content
                    count += 1

                    if count % 1000 == 0:
                        logger.info(f"A2AJ batch progress: {count} documents processed")

        except Exception as e:
            logger.error(f"Error during A2AJ batch fetch: {e}")

        logger.info(f"A2AJ batch complete: {count} documents yielded")
