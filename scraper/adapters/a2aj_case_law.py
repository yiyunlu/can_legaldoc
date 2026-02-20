"""
A2AJ Case Law adapter — fetches Canadian court decisions from the A2AJ
project via REST API and Hugging Face Hub REST API.

REST API (api.a2aj.ca): coverage info, citation lookup, full-text search.
HF Hub API (datasets-server.huggingface.co): paginated row access for bulk
ingestion — zero local memory overhead, no datasets library needed.

Covers SCC, Federal Court, FCA, Tax Court, CHRT, IRB-RAD, SST,
and select BC/ON/YK courts.

License: MIT (code); upstream document licenses vary.
"""
import time
import threading
import requests
from typing import List, Optional, Generator, Dict

from scraper.adapters import register_adapter
from scraper.adapters.base import BaseSourceAdapter, DocumentMetadata, DocumentContent
from utils.logger import logger


A2AJ_API_BASE = "https://api.a2aj.ca"
HF_PARQUET_API = "https://datasets-server.huggingface.co/parquet"
HF_DATASET = "a2aj/canadian-case-law"

# Map A2AJ 'dataset' field values to jurisdiction codes.
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
    'IRB-RPD': 'ca',         # Immigration and Refugee Board - RPD
    'BCCA': 'bc',            # BC Court of Appeal
    'BCSC': 'bc',            # BC Supreme Court
    'ONCA': 'on',            # Ontario Court of Appeal
    'ONSC': 'on',            # Ontario Superior Court
    'ABCA': 'ab',            # Alberta Court of Appeal
    'ABKB': 'ab',            # Alberta King's Bench
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

# Human-readable court names for UI display
COURT_NAMES = {
    'SCC': 'Supreme Court of Canada',
    'SCC-L': 'SCC Leave Applications',
    'FCA': 'Federal Court of Appeal',
    'FC': 'Federal Court',
    'TCC': 'Tax Court of Canada',
    'CMAC': 'Court Martial Appeal Court',
    'CHRT': 'Canadian Human Rights Tribunal',
    'SST': 'Social Security Tribunal',
    'IRB-RAD': 'Refugee Appeal Division',
    'IRB-RPD': 'Refugee Protection Division',
    'BCCA': 'BC Court of Appeal',
    'BCSC': 'BC Supreme Court',
    'ONCA': 'Ontario Court of Appeal',
    'ONSC': 'Ontario Superior Court',
    'ABCA': 'Alberta Court of Appeal',
    'ABKB': 'Alberta King\'s Bench',
    'ABQB': 'Alberta Queen\'s Bench',
    'SKCA': 'Saskatchewan Court of Appeal',
    'MBCA': 'Manitoba Court of Appeal',
    'NBCA': 'New Brunswick Court of Appeal',
    'NSCA': 'Nova Scotia Court of Appeal',
    'PECA': 'PEI Court of Appeal',
    'NLCA': 'NL Court of Appeal',
    'YKCA': 'Yukon Court of Appeal',
    'NWTCA': 'NWT Court of Appeal',
    'NUCA': 'Nunavut Court of Appeal',
}


@register_adapter('a2aj_case_law')
class A2AJCaseLawAdapter(BaseSourceAdapter):
    """
    Adapter for Canadian case law from the A2AJ project.
    Uses REST API for coverage info and HF parquet files for bulk ingestion.
    """

    def __init__(self, **kwargs):
        self._coverage_cache = None
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "CanadaLegalDataPlatform/1.0",
            "Accept": "application/json",
        })

    def get_source_name(self) -> str:
        return "A2AJ Canadian Case Law"

    def get_source_type(self) -> str:
        return "a2aj_case_law"

    def get_jurisdiction(self) -> str:
        return "multi"

    # ========== REST API Methods ==========

    def get_coverage(self) -> List[Dict]:
        """Fetch coverage info from A2AJ REST API."""
        if self._coverage_cache:
            return self._coverage_cache
        try:
            resp = self.session.get(f"{A2AJ_API_BASE}/coverage", params={"doc_type": "cases"}, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            # API returns {"results": [...]} — extract the list
            if isinstance(data, dict) and "results" in data:
                self._coverage_cache = data["results"]
            elif isinstance(data, list):
                self._coverage_cache = data
            else:
                logger.warning(f"A2AJ coverage: unexpected response format: {type(data)}")
                self._coverage_cache = []
            logger.info(f"A2AJ API: {len(self._coverage_cache)} court datasets available")
            return self._coverage_cache
        except Exception as e:
            logger.warning(f"A2AJ coverage API failed: {e}")
            return []

    def fetch_by_citation(self, citation: str, language: str = "en") -> Optional[str]:
        """Fetch full text of a single decision by citation via REST API."""
        try:
            resp = self.session.get(
                f"{A2AJ_API_BASE}/fetch",
                params={"citation": citation, "doc_type": "cases", "output_language": language},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            # API wraps results in {"results": [...]}
            if isinstance(data, dict) and "results" in data:
                data = data["results"]
            if data and len(data) > 0:
                return data[0].get('unofficial_text_en', '') or data[0].get('unofficial_text_fr', '')
        except Exception as e:
            logger.debug(f"A2AJ fetch by citation failed for '{citation}': {e}")
        return None

    # ========== HF Parquet Streaming Methods ==========

    def _get_parquet_urls(self) -> list:
        """Get list of parquet file URLs from HF Hub."""
        try:
            resp = self.session.get(
                HF_PARQUET_API,
                params={"dataset": HF_DATASET},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            files = data.get("parquet_files", [])
            urls = [f["url"] for f in files if f.get("split") == "train"]
            logger.info(f"A2AJ: found {len(urls)} parquet files for train split")
            return urls
        except Exception as e:
            logger.warning(f"A2AJ parquet API failed: {e}")
            return []

    def _stream_parquet_file(self, url: str) -> Generator[dict, None, None]:
        """
        Stream records from a single parquet file using pyarrow.
        Downloads to a temp file, then reads in small batches (100 rows)
        to keep memory bounded regardless of file/row-group size.
        """
        import tempfile
        import os
        import pyarrow.parquet as pq

        tmp_path = None
        try:
            # Download parquet file to temp location (streaming to disk)
            resp = self.session.get(url, stream=True, timeout=300)
            resp.raise_for_status()

            file_size = 0
            with tempfile.NamedTemporaryFile(delete=False, suffix='.parquet') as tmp:
                tmp_path = tmp.name
                for chunk in resp.iter_content(chunk_size=65536):
                    tmp.write(chunk)
                    file_size += len(chunk)

            logger.info(f"A2AJ: downloaded parquet file ({file_size / 1e6:.1f} MB)")

            # Use iter_batches to read in small chunks — bounded memory
            pf = pq.ParquetFile(tmp_path)
            for batch in pf.iter_batches(batch_size=100):
                for row in batch.to_pylist():
                    yield row
                del batch  # free memory after each batch

        except Exception as e:
            logger.warning(f"A2AJ parquet stream error: {e}")
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass

    # ========== Field Parsing ==========

    def _resolve_jurisdiction(self, record: dict) -> str:
        """Map court identifier from dataset to jurisdiction code."""
        court = (record.get('dataset', '') or '').strip().upper()
        if court in COURT_TO_JURISDICTION:
            return COURT_TO_JURISDICTION[court]
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
        """Convert a dataset record to DocumentMetadata."""
        court = self._clean_field(record, 'dataset')
        url = self._clean_field(record, 'url_en') or self._clean_field(record, 'url_fr')
        title = self._clean_field(record, 'name_en') or self._clean_field(record, 'name_fr')
        citation = self._clean_field(record, 'citation_en') or self._clean_field(record, 'citation_fr')
        date = self._clean_field(record, 'document_date_en') or self._clean_field(record, 'document_date_fr')

        if not url and citation:
            url = f"a2aj://case/{citation.replace(' ', '_')}"

        court_name = COURT_NAMES.get(court.upper(), court)

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
                "court_name": court_name,
                "date": date,
            },
        )

    def _record_to_content(self, record: dict) -> DocumentContent:
        """Convert a dataset record to DocumentContent."""
        meta = self._record_to_metadata(record)

        content_text = self._clean_field(record, 'unofficial_text_en')
        if not content_text:
            content_text = self._clean_field(record, 'unofficial_text_fr')

        return DocumentContent(
            source_url=meta.source_url,
            title=meta.title,
            citation=meta.citation,
            content_html='',
            content_text=content_text,
            jurisdiction_code=meta.jurisdiction_code,
            category="Case Law",
            document_type="case_law",
            is_active=True,
            metadata=meta.metadata,
        )

    # ========== Adapter Interface ==========

    def discover_documents(self, limit: Optional[int] = None) -> List[DocumentMetadata]:
        """
        Return a lightweight placeholder list for A2AJ.

        Since the HF dataset contains full text, discovery and fetch are
        combined in fetch_documents_batch(). We return synthetic metadata
        entries so the manager knows how many documents to expect.
        This avoids loading 185K records into memory during discovery.
        """
        effective_limit = limit if limit is not None else 184565

        # Try to get real counts from REST API (cheap, no streaming)
        coverage = self.get_coverage()
        total_available = sum(c.get('number_of_documents', 0) for c in coverage) if coverage else 184565

        count = min(effective_limit, total_available)
        logger.info(f"A2AJ discovery: {count:,} documents available (limit={limit}, total={total_available:,})")

        # Return lightweight stubs — batch will stream the real data
        return [
            DocumentMetadata(
                source_url=f"a2aj://placeholder/{i}",
                title=f"A2AJ Case #{i}",
                citation="",
                jurisdiction_code="ca",
                category="Case Law",
                document_type="case_law",
            )
            for i in range(count)
        ]

    def fetch_document(self, doc_meta: DocumentMetadata) -> Optional[DocumentContent]:
        """
        Single document fetch via REST API (by citation).
        Used as fallback; batch mode is preferred.
        """
        citation = doc_meta.citation
        if not citation:
            return None

        text = self.fetch_by_citation(citation)
        if not text:
            return None

        return DocumentContent(
            source_url=doc_meta.source_url,
            title=doc_meta.title,
            citation=citation,
            content_html='',
            content_text=text,
            jurisdiction_code=doc_meta.jurisdiction_code,
            category="Case Law",
            document_type="case_law",
            is_active=True,
            metadata=doc_meta.metadata,
        )

    def fetch_documents_batch(
        self,
        docs: List[DocumentMetadata],
        limit: Optional[int] = None,
        stop_event: Optional[threading.Event] = None,
    ) -> Generator[DocumentContent, None, None]:
        """
        Batch loading via HF parquet file streaming.

        Downloads parquet files one at a time, reads row-group by row-group
        using pyarrow. Each row group is processed and freed — memory stays
        bounded regardless of dataset size. Handles the full 184K+ dataset
        on memory-constrained servers (3-4GB).

        When discovery returns placeholder stubs (lightweight mode),
        we iterate through all parquet files up to limit, letting the DB
        handle dedup via upsert.
        """
        count = 0
        skipped = 0

        # Detect placeholder mode
        is_placeholder = (
            docs and len(docs) > 0
            and docs[0].source_url.startswith('a2aj://placeholder/')
        )

        if is_placeholder:
            target_urls = None
        else:
            target_urls = {d.source_url for d in docs} if docs else None

        # Get parquet file URLs
        parquet_urls = self._get_parquet_urls()
        if not parquet_urls:
            logger.error("A2AJ: no parquet files found, cannot proceed with batch")
            return

        logger.info(f"A2AJ batch: streaming {len(parquet_urls)} parquet files, limit={limit or 'all'}")

        try:
            for file_idx, pq_url in enumerate(parquet_urls):
                if limit is not None and count >= limit:
                    break
                if stop_event and stop_event.is_set():
                    break

                logger.info(f"A2AJ: processing parquet file {file_idx + 1}/{len(parquet_urls)}")

                for record in self._stream_parquet_file(pq_url):
                    if limit is not None and count >= limit:
                        break
                    if stop_event and stop_event.is_set():
                        break

                    content = self._record_to_content(record)

                    # If we have a real target list, filter to only matching URLs
                    if target_urls and content.source_url not in target_urls:
                        skipped += 1
                        continue

                    if content.content_text or content.content_html:
                        yield content
                        count += 1

                        if count % 1000 == 0:
                            logger.info(f"A2AJ batch progress: {count:,} documents (file {file_idx + 1}/{len(parquet_urls)})")

        except Exception as e:
            logger.error(f"Error during A2AJ parquet batch fetch: {e}")

        logger.info(f"A2AJ batch complete: {count:,} documents yielded, {skipped:,} skipped")
