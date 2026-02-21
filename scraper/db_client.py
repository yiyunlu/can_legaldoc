"""
PostgreSQL database client module.
Drop-in replacement for supabase_client.py — same public API, direct psycopg2 backend.

Supports both local PostgreSQL (DATABASE_URL) and Supabase fallback (SUPABASE_URL).
"""
import os
import json
import hashlib
from typing import Dict, Optional, List
from contextlib import contextmanager

import psycopg2
import psycopg2.extras
from psycopg2.pool import ThreadedConnectionPool

from utils.logger import logger

# Register UUID adapter for psycopg2
psycopg2.extras.register_uuid()


class DatabaseClient:
    """PostgreSQL database client with connection pooling."""

    def __init__(self):
        db_url = os.getenv('DATABASE_URL')
        if not db_url:
            raise ValueError("DATABASE_URL is not set. Please configure your .env file.")

        try:
            self.pool = ThreadedConnectionPool(
                minconn=2,
                maxconn=20,
                dsn=db_url,
                connect_timeout=10,
            )
            logger.info("PostgreSQL connection pool initialized")
        except Exception as e:
            logger.error(f"PostgreSQL connection failed: {e}")
            raise

    @contextmanager
    def _get_conn(self):
        """Get a connection from the pool (context manager)."""
        conn = self.pool.getconn()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            self.pool.putconn(conn)

    # ========== Core Document Operations ==========

    def upsert_document_v3(self, doc_data: Dict) -> bool:
        """
        Insert or update a document + create content version if changed.
        Same logic as SupabaseClient.upsert_document_v3().
        """
        try:
            source_url = doc_data.get('source_url')
            if not source_url:
                logger.error("Missing source_url, cannot save document")
                return False

            with self._get_conn() as conn:
                cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

                # 1. Upsert documents table
                cur.execute("""
                    INSERT INTO documents
                        (title, citation, source_url, jurisdiction_code, category,
                         target_id, is_active, metadata, source_type, document_type,
                         updated_at, last_checked_at)
                    VALUES
                        (%(title)s, %(citation)s, %(source_url)s, %(jurisdiction_code)s,
                         %(category)s, %(target_id)s, %(is_active)s, %(metadata)s,
                         %(source_type)s, %(document_type)s, now(), now())
                    ON CONFLICT (source_url) DO UPDATE SET
                        title = EXCLUDED.title,
                        citation = EXCLUDED.citation,
                        jurisdiction_code = EXCLUDED.jurisdiction_code,
                        category = EXCLUDED.category,
                        is_active = EXCLUDED.is_active,
                        metadata = EXCLUDED.metadata,
                        source_type = EXCLUDED.source_type,
                        document_type = EXCLUDED.document_type,
                        updated_at = now(),
                        last_checked_at = now()
                    RETURNING id
                """, {
                    'title': doc_data.get('title'),
                    'citation': doc_data.get('citation'),
                    'source_url': source_url,
                    'jurisdiction_code': doc_data.get('jurisdiction_code', 'ab'),
                    'category': doc_data.get('category', 'Legislation'),
                    'target_id': doc_data.get('target_id'),
                    'is_active': doc_data.get('is_active', True),
                    'metadata': json.dumps(doc_data.get('metadata', {})),
                    'source_type': doc_data.get('source_type', 'canlii_legacy'),
                    'document_type': doc_data.get('document_type', 'legislation'),
                })

                row = cur.fetchone()
                if not row:
                    logger.error(f"Documents upsert failed: {source_url}")
                    return False
                document_id = row['id']

                # 2. Version control
                content_text = doc_data.get('content_text', '')
                content_html = doc_data.get('content_html', '')
                content_hash = hashlib.sha256(content_text.encode('utf-8')).hexdigest()

                # Check latest version
                cur.execute("""
                    SELECT id, content_hash, version_number
                    FROM document_versions
                    WHERE document_id = %s AND is_latest = true
                """, (document_id,))
                latest_ver = cur.fetchone()

                should_create_version = True
                if latest_ver:
                    if latest_ver['content_hash'] == content_hash:
                        logger.info(f"Content unchanged, skipping version: {doc_data.get('title')}")
                        should_create_version = False
                    else:
                        # Mark old version as non-latest
                        cur.execute("""
                            UPDATE document_versions SET is_latest = false WHERE id = %s
                        """, (latest_ver['id'],))

                # 3. Create new version
                if should_create_version:
                    version_number = (latest_ver['version_number'] + 1) if latest_ver else 1
                    cur.execute("""
                        INSERT INTO document_versions
                            (document_id, content_html, content_text, content_hash,
                             version_number, is_latest, scraped_at)
                        VALUES (%s, %s, %s, %s, %s, true, now())
                    """, (document_id, content_html, content_text, content_hash, version_number))
                    logger.info(f"Saved v{version_number}: {doc_data.get('title')}")

            return True

        except Exception as e:
            logger.error(f"Document save failed: {e}")
            return False

    def upsert_statute(self, statute_data: Dict) -> bool:
        """[DEPRECATED] Backward-compatible alias."""
        return self.upsert_document_v3(statute_data)

    # ========== Incremental Update Operations ==========

    def get_fresh_urls(self, urls: List[str], max_age_hours: int = 24) -> set:
        """Return subset of URLs that were checked within max_age_hours.
        These can be skipped in incremental mode.

        Args:
            urls: list of source_urls to check
            max_age_hours: how old a check can be before it's considered stale

        Returns:
            set of URLs that are still fresh (recently checked)
        """
        if not urls:
            return set()

        fresh_set = set()
        chunk_size = 500
        try:
            with self._get_conn() as conn:
                cur = conn.cursor()
                for i in range(0, len(urls), chunk_size):
                    chunk = urls[i:i + chunk_size]
                    placeholders = ','.join(['%s'] * len(chunk))
                    cur.execute(f"""
                        SELECT source_url FROM documents
                        WHERE source_url IN ({placeholders})
                          AND last_checked_at > now() - interval '{int(max_age_hours)} hours'
                    """, chunk)
                    for row in cur.fetchall():
                        fresh_set.add(row[0])
        except Exception as e:
            logger.error(f"get_fresh_urls failed: {e}")

        return fresh_set

    def get_known_urls_for_source(self, source_type: str) -> set:
        """Get all known source_urls for a given source_type.
        Used to detect new vs existing documents during discovery.

        Returns:
            set of source_urls
        """
        try:
            with self._get_conn() as conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT source_url FROM documents WHERE source_type = %s",
                    (source_type,)
                )
                return {row[0] for row in cur.fetchall()}
        except Exception as e:
            logger.error(f"get_known_urls_for_source failed: {e}")
            return set()

    def get_stale_urls_for_source(self, source_type: str,
                                   max_age_hours: int = 24,
                                   limit: Optional[int] = None) -> List[str]:
        """Get source_urls for docs that haven't been checked recently,
        ordered by oldest-checked first (priority queue).

        Args:
            source_type: adapter source_type
            max_age_hours: threshold for staleness
            limit: max URLs to return

        Returns:
            list of source_urls, oldest-checked first
        """
        try:
            with self._get_conn() as conn:
                cur = conn.cursor()
                limit_clause = f"LIMIT {int(limit)}" if limit else ""
                cur.execute(f"""
                    SELECT source_url FROM documents
                    WHERE source_type = %s
                      AND (last_checked_at IS NULL
                           OR last_checked_at < now() - interval '{int(max_age_hours)} hours')
                    ORDER BY last_checked_at ASC NULLS FIRST
                    {limit_clause}
                """, (source_type,))
                return [row[0] for row in cur.fetchall()]
        except Exception as e:
            logger.error(f"get_stale_urls_for_source failed: {e}")
            return []

    # ========== Source Sync Logging ==========

    def create_sync_log(self, source_type: str, mode: str = 'full',
                        trigger_source: str = 'manual',
                        max_age_hours: Optional[int] = None) -> Optional[str]:
        """Create a source_sync_log entry, return its ID."""
        try:
            with self._get_conn() as conn:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO source_sync_log
                        (source_type, mode, trigger_source, max_age_hours)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id
                """, (source_type, mode, trigger_source, max_age_hours))
                row = cur.fetchone()
                return str(row[0]) if row else None
        except Exception as e:
            logger.warning(f"Failed to create sync log: {e}")
            return None

    def update_sync_log(self, sync_id: str, **kwargs):
        """Update a source_sync_log entry with stats."""
        if not sync_id:
            return
        allowed = {
            'docs_discovered', 'docs_checked', 'docs_new', 'docs_updated',
            'docs_unchanged', 'docs_failed', 'docs_skipped_fresh',
            'error_message', 'notes',
        }
        filtered = {k: v for k, v in kwargs.items() if k in allowed}
        if not filtered:
            return
        try:
            set_clauses = [f"{k} = %s" for k in filtered]
            values = list(filtered.values())
            with self._get_conn() as conn:
                cur = conn.cursor()
                cur.execute(
                    f"UPDATE source_sync_log SET {', '.join(set_clauses)} WHERE id = %s",
                    values + [sync_id]
                )
        except Exception as e:
            logger.warning(f"Failed to update sync log: {e}")

    def finalize_sync_log(self, sync_id: str, **kwargs):
        """Mark sync log as finished with final stats."""
        if not sync_id:
            return
        allowed = {
            'docs_discovered', 'docs_checked', 'docs_new', 'docs_updated',
            'docs_unchanged', 'docs_failed', 'docs_skipped_fresh',
            'error_message', 'notes',
        }
        filtered = {k: v for k, v in kwargs.items() if k in allowed}
        try:
            set_clauses = ["finished_at = now()"]
            values = []
            for k, v in filtered.items():
                set_clauses.append(f"{k} = %s")
                values.append(v)
            with self._get_conn() as conn:
                cur = conn.cursor()
                cur.execute(
                    f"UPDATE source_sync_log SET {', '.join(set_clauses)} WHERE id = %s",
                    values + [sync_id]
                )
        except Exception as e:
            logger.warning(f"Failed to finalize sync log: {e}")

    def get_source_freshness(self) -> Dict:
        """Get per-source freshness summary for the dashboard.

        Returns dict with per-source stats:
          - total_docs, checked_24h, checked_7d, never_checked
          - oldest_check, newest_check
          - last_sync (from source_sync_log)
        """
        try:
            with self._get_conn() as conn:
                cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

                # Per-source freshness from documents table
                cur.execute("""
                    SELECT
                        source_type,
                        COUNT(*) AS total_docs,
                        COUNT(*) FILTER (
                            WHERE last_checked_at > now() - interval '24 hours'
                        ) AS checked_24h,
                        COUNT(*) FILTER (
                            WHERE last_checked_at > now() - interval '7 days'
                        ) AS checked_7d,
                        COUNT(*) FILTER (
                            WHERE last_checked_at IS NULL
                        ) AS never_checked,
                        MIN(last_checked_at) AS oldest_check,
                        MAX(last_checked_at) AS newest_check
                    FROM documents
                    WHERE source_type IS NOT NULL
                    GROUP BY source_type
                    ORDER BY source_type
                """)
                freshness = {}
                for r in cur.fetchall():
                    row = dict(r)
                    st = row.pop('source_type')
                    for k, v in row.items():
                        if hasattr(v, 'isoformat'):
                            row[k] = v.isoformat()
                    freshness[st] = row

                # Latest sync per source from source_sync_log
                cur.execute("""
                    SELECT DISTINCT ON (source_type)
                        source_type, mode, started_at, finished_at,
                        docs_discovered, docs_new, docs_updated,
                        docs_unchanged, docs_skipped_fresh, docs_failed
                    FROM source_sync_log
                    WHERE finished_at IS NOT NULL
                    ORDER BY source_type, started_at DESC
                """)
                for r in cur.fetchall():
                    row = self._serialize_row(r)
                    st = row.pop('source_type')
                    if st in freshness:
                        freshness[st]['last_sync'] = row

                return {"sources": freshness}
        except Exception as e:
            logger.error(f"get_source_freshness failed: {e}")
            return {"sources": {}}

    def get_sync_history(self, source_type: str = None, limit: int = 20) -> List[Dict]:
        """Get recent sync log entries."""
        try:
            with self._get_conn() as conn:
                cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                if source_type:
                    cur.execute("""
                        SELECT * FROM source_sync_log
                        WHERE source_type = %s
                        ORDER BY started_at DESC LIMIT %s
                    """, (source_type, limit))
                else:
                    cur.execute("""
                        SELECT * FROM source_sync_log
                        ORDER BY started_at DESC LIMIT %s
                    """, (limit,))
                return [self._serialize_row(r) for r in cur.fetchall()]
        except Exception as e:
            logger.error(f"get_sync_history failed: {e}")
            return []

    # ========== Query Operations ==========

    def get_statute_by_url(self, source_url: str) -> Optional[Dict]:
        """Get a document by source_url."""
        try:
            with self._get_conn() as conn:
                cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                cur.execute("SELECT * FROM documents WHERE source_url = %s", (source_url,))
                row = cur.fetchone()
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"Query document failed: {e}")
            return None

    def update_document_status(self, source_url: str, is_active: bool) -> bool:
        """Update a document's active status."""
        try:
            with self._get_conn() as conn:
                cur = conn.cursor()
                cur.execute("""
                    UPDATE documents SET is_active = %s, updated_at = now()
                    WHERE source_url = %s
                """, (is_active, source_url))
                return cur.rowcount > 0
        except Exception as e:
            logger.error(f"Update document status failed: {e}")
            return False

    def get_all_statutes(self) -> list:
        """Get all documents."""
        try:
            with self._get_conn() as conn:
                cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                cur.execute("SELECT * FROM documents")
                return [dict(r) for r in cur.fetchall()]
        except Exception as e:
            logger.error(f"Get all documents failed: {e}")
            return []

    def get_statute_count(self) -> int:
        """Get total document count."""
        try:
            with self._get_conn() as conn:
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM documents")
                return cur.fetchone()[0]
        except Exception as e:
            logger.error(f"Get document count failed: {e}")
            return 0

    def test_connection(self) -> bool:
        """Test database connectivity."""
        try:
            with self._get_conn() as conn:
                cur = conn.cursor()
                cur.execute("SELECT 1")
                logger.info("Database connection test passed")
                return True
        except Exception as e:
            logger.error(f"Database connection test failed: {e}")
            return False

    # ========== Stats Operations (used by api/main.py) ==========

    def get_source_stats(self) -> Dict:
        """Get comprehensive statistics for the dashboard.
        Uses a single CTE query for all document aggregations (was 5 separate queries).
        """
        try:
            with self._get_conn() as conn:
                cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

                # Merged: source_type count + last_updated in one query (was 2 separate)
                cur.execute("SELECT COUNT(*) AS cnt FROM documents")
                total_docs = cur.fetchone()['cnt']

                cur.execute("""
                    SELECT source_type, COUNT(*) AS cnt, MAX(updated_at) AS last_updated
                    FROM documents WHERE source_type IS NOT NULL
                    GROUP BY source_type
                """)
                source_counts = {}
                last_updated_by_source = {}
                for r in cur.fetchall():
                    source_counts[r['source_type']] = r['cnt']
                    val = r['last_updated']
                    last_updated_by_source[r['source_type']] = val.isoformat() if hasattr(val, 'isoformat') else str(val)

                # Jurisdiction counts with names
                cur.execute("""
                    SELECT d.jurisdiction_code, j.name, COUNT(*) AS cnt
                    FROM documents d
                    LEFT JOIN jurisdictions j ON d.jurisdiction_code = j.code
                    WHERE d.jurisdiction_code IS NOT NULL
                    GROUP BY d.jurisdiction_code, j.name
                """)
                jur_counts = {
                    r['jurisdiction_code']: {"name": r['name'] or r['jurisdiction_code'], "count": r['cnt']}
                    for r in cur.fetchall()
                }

                cur.execute("""
                    SELECT document_type, COUNT(*) AS cnt FROM documents
                    WHERE document_type IS NOT NULL GROUP BY document_type
                """)
                type_counts = {r['document_type']: r['cnt'] for r in cur.fetchall()}

                cur.execute("""
                    SELECT metadata->>'court' AS court, COUNT(*) AS cnt
                    FROM documents
                    WHERE document_type = 'case_law'
                      AND metadata->>'court' IS NOT NULL AND metadata->>'court' != ''
                    GROUP BY metadata->>'court' ORDER BY cnt DESC
                """)
                court_counts = {r['court']: r['cnt'] for r in cur.fetchall()}

                # Recent scrape jobs (last 10)
                cur.execute("""
                    SELECT * FROM scrape_jobs
                    ORDER BY started_at DESC NULLS LAST LIMIT 10
                """)
                recent_jobs = []
                for r in cur.fetchall():
                    row = dict(r)
                    for k, v in row.items():
                        if hasattr(v, 'isoformat'):
                            row[k] = v.isoformat()
                        elif hasattr(v, 'hex'):
                            row[k] = str(v)
                    recent_jobs.append(row)

                return {
                    "total_documents": total_docs,
                    "by_source": source_counts,
                    "by_jurisdiction": jur_counts,
                    "by_type": type_counts,
                    "by_court": court_counts,
                    "recent_jobs": recent_jobs,
                    "last_updated_by_source": last_updated_by_source,
                }
        except Exception as e:
            logger.error(f"Get source stats failed: {e}")
            raise

    # ========== Job Tracking (used by api/manager.py) ==========

    def create_job(self, engine_label: str) -> Optional[str]:
        """Create a scrape_jobs record, return the job ID."""
        try:
            with self._get_conn() as conn:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO scrape_jobs (status, items_scraped, items_failed, logs)
                    VALUES ('running', 0, 0, %s)
                    RETURNING id
                """, (f"Engine: {engine_label} | Message: Started",))
                row = cur.fetchone()
                job_id = str(row[0])
                logger.info(f"Job record created: {job_id}")
                return job_id
        except Exception as e:
            logger.warning(f"Failed to create job record: {e}")
            return None

    def update_job(self, job_id: str, items_scraped: int, items_failed: int, logs: str):
        """Update a running job's stats."""
        if not job_id:
            return
        try:
            with self._get_conn() as conn:
                cur = conn.cursor()
                cur.execute("""
                    UPDATE scrape_jobs
                    SET items_scraped = %s, items_failed = %s, logs = %s
                    WHERE id = %s
                """, (items_scraped, items_failed, logs, job_id))
        except Exception as e:
            logger.warning(f"Failed to update job: {e}")

    def finalize_job(self, job_id: str, status: str, items_scraped: int,
                     items_failed: int, logs: str):
        """Mark a job as completed or failed."""
        if not job_id:
            return
        try:
            with self._get_conn() as conn:
                cur = conn.cursor()
                cur.execute("""
                    UPDATE scrape_jobs
                    SET status = %s, items_scraped = %s, items_failed = %s,
                        logs = %s, finished_at = now()
                    WHERE id = %s
                """, (status, items_scraped, items_failed, logs, job_id))
                logger.info(f"Job {job_id} marked as {status}")
        except Exception as e:
            logger.warning(f"Failed to finalize job: {e}")

    def cleanup_stale_jobs(self):
        """Mark stale 'running' jobs as failed on startup."""
        try:
            with self._get_conn() as conn:
                cur = conn.cursor()
                cur.execute("""
                    UPDATE scrape_jobs
                    SET status = 'failed',
                        logs = 'Interrupted: System restarted or script crashed',
                        finished_at = now()
                    WHERE status = 'running'
                """)
                if cur.rowcount > 0:
                    logger.info(f"Cleaned up {cur.rowcount} stale jobs")
        except Exception as e:
            logger.warning(f"Failed to cleanup stale jobs: {e}")

    # ========== Paginated Queries (used by API endpoints) ==========

    def _serialize_row(self, row: Dict) -> Dict:
        """Convert UUIDs and datetimes to JSON-safe strings."""
        result = dict(row)
        for k, v in result.items():
            if hasattr(v, 'isoformat'):
                result[k] = v.isoformat()
            elif hasattr(v, 'hex'):  # UUID
                result[k] = str(v)
        return result

    def get_jobs_paginated(self, page: int = 1, per_page: int = 25,
                           status_filter: str = None) -> Dict:
        """Get paginated scrape jobs with optional status filter."""
        try:
            with self._get_conn() as conn:
                cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

                where_clause = ""
                params = []
                if status_filter and status_filter in ('completed', 'failed', 'running'):
                    where_clause = "WHERE status = %s"
                    params.append(status_filter)

                # Count total
                cur.execute(f"SELECT COUNT(*) AS cnt FROM scrape_jobs {where_clause}", params)
                total = cur.fetchone()['cnt']

                # Fetch page
                offset = (page - 1) * per_page
                cur.execute(f"""
                    SELECT * FROM scrape_jobs
                    {where_clause}
                    ORDER BY started_at DESC NULLS LAST
                    LIMIT %s OFFSET %s
                """, params + [per_page, offset])

                jobs = [self._serialize_row(r) for r in cur.fetchall()]

                return {
                    "jobs": jobs,
                    "total": total,
                    "page": page,
                    "per_page": per_page,
                    "total_pages": max(1, -(-total // per_page)),
                }
        except Exception as e:
            logger.error(f"Get jobs paginated failed: {e}")
            return {"jobs": [], "total": 0, "page": 1, "per_page": per_page, "total_pages": 0}

    def get_documents_paginated(self, page: int = 1, per_page: int = 50,
                                source_type: str = None,
                                jurisdiction: str = None,
                                document_type: str = None,
                                search: str = None) -> Dict:
        """Get paginated documents with filtering. Dispatches to full-text search when search term present."""
        # Full-text search path
        if search and search.strip():
            return self.search_documents(
                query=search.strip(), page=page, per_page=per_page,
                source_type=source_type, jurisdiction=jurisdiction,
                document_type=document_type,
            )

        # Standard browse path (no search term)
        try:
            with self._get_conn() as conn:
                cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

                conditions = []
                params = []

                if source_type:
                    conditions.append("d.source_type = %s")
                    params.append(source_type)
                if jurisdiction:
                    conditions.append("d.jurisdiction_code = %s")
                    params.append(jurisdiction)
                if document_type:
                    conditions.append("d.document_type = %s")
                    params.append(document_type)

                where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""

                # Count total matching
                cur.execute(f"SELECT COUNT(*) AS cnt FROM documents d {where_clause}", params)
                total = cur.fetchone()['cnt']

                # Fetch page (exclude large content columns, add has_content flag)
                offset = (page - 1) * per_page
                cur.execute(f"""
                    SELECT d.id, d.title, d.citation, d.source_url, d.jurisdiction_code,
                           d.source_type, d.document_type, d.category, d.is_active,
                           d.created_at, d.updated_at,
                           EXISTS(
                               SELECT 1 FROM document_versions dv
                               WHERE dv.document_id = d.id AND dv.is_latest = true
                                 AND (dv.content_text IS NOT NULL AND dv.content_text != '')
                           ) AS has_content
                    FROM documents d
                    {where_clause}
                    ORDER BY d.updated_at DESC
                    LIMIT %s OFFSET %s
                """, params + [per_page, offset])

                docs = [self._serialize_row(r) for r in cur.fetchall()]

                return {
                    "documents": docs,
                    "total": total,
                    "page": page,
                    "per_page": per_page,
                    "total_pages": max(1, -(-total // per_page)),
                }
        except Exception as e:
            logger.error(f"Get documents paginated failed: {e}")
            return {"documents": [], "total": 0, "page": 1, "per_page": per_page, "total_pages": 0}

    def search_documents(self, query: str, page: int = 1, per_page: int = 50,
                         source_type: str = None, jurisdiction: str = None,
                         document_type: str = None) -> Dict:
        """Full-text search across document titles, citations, and content.
        Uses PostgreSQL tsvector/tsquery with GIN indexes for relevance-ranked results.
        """
        try:
            with self._get_conn() as conn:
                cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

                # Build filter conditions
                conditions = []
                filter_params = []
                if source_type:
                    conditions.append("d.source_type = %s")
                    filter_params.append(source_type)
                if jurisdiction:
                    conditions.append("d.jurisdiction_code = %s")
                    filter_params.append(jurisdiction)
                if document_type:
                    conditions.append("d.document_type = %s")
                    filter_params.append(document_type)

                filter_clause = (" AND " + " AND ".join(conditions)) if conditions else ""

                # Count matching documents — UNION approach forces GIN index usage
                # (OR across two tables causes seq scan; UNION uses bitmap index scan)
                cur.execute(f"""
                    WITH q AS (SELECT plainto_tsquery('english', %s) AS tsq),
                    title_matches AS (
                        SELECT d.id FROM q, documents d
                        WHERE d.search_vector @@ q.tsq
                    ),
                    content_matches AS (
                        SELECT dv.document_id AS id FROM q, document_versions dv
                        WHERE dv.content_search_vector @@ q.tsq AND dv.is_latest = true
                    ),
                    all_matches AS (
                        SELECT id FROM title_matches
                        UNION
                        SELECT id FROM content_matches
                    )
                    SELECT COUNT(*) AS cnt FROM all_matches am
                    JOIN documents d ON d.id = am.id
                    WHERE true{filter_clause}
                """, [query] + filter_params)
                total = cur.fetchone()['cnt']

                offset = (page - 1) * per_page

                # Fetch ranked results with snippets — two-step strategy:
                # 1) Rank using title ts_rank + boolean content match (avoids TOAST reads)
                # 2) Only run ts_headline on the final page of results
                # filter_params are duplicated: once for all_ids filter, once for LIMIT/OFFSET
                cur.execute(f"""
                    WITH q AS (SELECT plainto_tsquery('english', %s) AS tsq),
                    title_matches AS (
                        SELECT d.id, ts_rank_cd(d.search_vector, q.tsq) AS title_rank
                        FROM q, documents d WHERE d.search_vector @@ q.tsq
                    ),
                    content_match_ids AS (
                        SELECT dv.document_id AS id
                        FROM q, document_versions dv
                        WHERE dv.content_search_vector @@ q.tsq AND dv.is_latest = true
                    ),
                    all_ids AS (
                        SELECT a.id FROM (
                            SELECT id FROM title_matches UNION SELECT id FROM content_match_ids
                        ) a
                        JOIN documents d ON d.id = a.id
                        WHERE true{filter_clause}
                    ),
                    ranked AS (
                        SELECT a.id,
                            COALESCE(t.title_rank, 0) * 4.0
                                + CASE WHEN c.id IS NOT NULL THEN 0.1 ELSE 0 END AS relevance
                        FROM all_ids a
                        LEFT JOIN title_matches t ON t.id = a.id
                        LEFT JOIN content_match_ids c ON c.id = a.id
                        ORDER BY relevance DESC
                        LIMIT %s OFFSET %s
                    )
                    SELECT r.relevance, d.id, d.title, d.citation, d.source_url,
                        d.jurisdiction_code, d.source_type, d.document_type,
                        d.category, d.is_active, d.created_at, d.updated_at,
                        (dv.content_text IS NOT NULL AND dv.content_text != '') AS has_content,
                        CASE WHEN dv.content_search_vector @@ q.tsq
                            THEN ts_headline('english', LEFT(dv.content_text, 10000), q.tsq,
                                'MaxWords=35, MinWords=15, StartSel=<mark>, StopSel=</mark>, MaxFragments=2, FragmentDelimiter= ... ')
                            ELSE NULL END AS snippet
                    FROM q, ranked r
                    JOIN documents d ON d.id = r.id
                    LEFT JOIN document_versions dv ON d.id = dv.document_id AND dv.is_latest = true
                    ORDER BY r.relevance DESC
                """, [query] + filter_params + [per_page, offset])

                docs = [self._serialize_row(r) for r in cur.fetchall()]

                return {
                    "documents": docs,
                    "total": total,
                    "page": page,
                    "per_page": per_page,
                    "total_pages": max(1, -(-total // per_page)),
                    "search_mode": "fulltext",
                }
        except Exception as e:
            logger.error(f"Full-text search failed: {e}")
            return {"documents": [], "total": 0, "page": 1, "per_page": per_page, "total_pages": 0}

    def get_document_detail(self, doc_id: str) -> Optional[Dict]:
        """Get document metadata + latest version info (no full content)."""
        try:
            with self._get_conn() as conn:
                cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                cur.execute("""
                    SELECT d.id, d.title, d.citation, d.source_url, d.jurisdiction_code,
                           d.source_type, d.document_type, d.category, d.is_active,
                           d.metadata, d.created_at, d.updated_at,
                           dv.version_number, dv.scraped_at, dv.content_hash,
                           length(dv.content_text) AS content_length,
                           length(dv.content_html) AS content_html_length,
                           COALESCE(dv.content_text IS NOT NULL AND dv.content_text != '', false) AS has_content,
                           COALESCE(dv.content_html IS NOT NULL AND dv.content_html != '', false) AS has_html
                    FROM documents d
                    LEFT JOIN document_versions dv
                        ON d.id = dv.document_id AND dv.is_latest = true
                    WHERE d.id = %s
                """, (doc_id,))
                row = cur.fetchone()
                if not row:
                    return None
                return self._serialize_row(row)
        except Exception as e:
            logger.error(f"Get document detail failed: {e}")
            return None

    def get_document_content(self, doc_id: str, max_length: int = 50000) -> Optional[Dict]:
        """Get document text/html content for preview (truncated)."""
        try:
            with self._get_conn() as conn:
                cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                cur.execute("""
                    SELECT d.title, d.citation,
                           LEFT(dv.content_text, %s) AS content_text,
                           length(dv.content_text) AS text_length,
                           length(dv.content_html) AS html_length,
                           dv.version_number,
                           COALESCE(dv.content_text IS NOT NULL AND dv.content_text != '', false) AS has_content
                    FROM documents d
                    LEFT JOIN document_versions dv
                        ON d.id = dv.document_id AND dv.is_latest = true
                    WHERE d.id = %s
                """, (max_length, doc_id))
                row = cur.fetchone()
                if not row:
                    return None
                return {
                    "title": row['title'],
                    "citation": row['citation'],
                    "content_text": row['content_text'] or '',
                    "text_length": row['text_length'] or 0,
                    "html_length": row['html_length'] or 0,
                    "truncated": (row['text_length'] or 0) > max_length,
                    "version": row['version_number'],
                }
        except Exception as e:
            logger.error(f"Get document content failed: {e}")
            return None

    # ========== Database Diagnostics ==========

    def get_db_diagnostics(self) -> Dict:
        """Run comprehensive database diagnostics — returns a structured report."""
        try:
            with self._get_conn() as conn:
                cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                report = {}

                # 1. Database size
                cur.execute("SELECT pg_size_pretty(pg_database_size(current_database())) AS db_size")
                report['db_size'] = cur.fetchone()['db_size']

                # 2. Table row counts + sizes
                table_info = []
                for tbl in ('documents', 'document_versions', 'document_chunks', 'scrape_jobs', 'scrape_targets', 'scheduler_config', 'jurisdictions'):
                    cur.execute(f"""
                        SELECT
                            '{tbl}' AS table_name,
                            (SELECT COUNT(*) FROM {tbl}) AS row_count,
                            pg_size_pretty(pg_total_relation_size('{tbl}')) AS total_size,
                            pg_size_pretty(pg_relation_size('{tbl}')) AS data_size,
                            pg_size_pretty(pg_total_relation_size('{tbl}') - pg_relation_size('{tbl}')) AS index_size
                    """)
                    table_info.append(dict(cur.fetchone()))
                report['tables'] = table_info

                # 3. Documents by source_type
                cur.execute("""
                    SELECT source_type, COUNT(*) AS count
                    FROM documents
                    GROUP BY source_type
                    ORDER BY count DESC
                """)
                report['docs_by_source'] = [dict(r) for r in cur.fetchall()]

                # 4. Documents by jurisdiction
                cur.execute("""
                    SELECT d.jurisdiction_code, j.name, COUNT(*) AS count
                    FROM documents d
                    LEFT JOIN jurisdictions j ON d.jurisdiction_code = j.code
                    GROUP BY d.jurisdiction_code, j.name
                    ORDER BY count DESC
                """)
                report['docs_by_jurisdiction'] = [dict(r) for r in cur.fetchall()]

                # 5. Documents by document_type
                cur.execute("""
                    SELECT document_type, COUNT(*) AS count
                    FROM documents
                    GROUP BY document_type
                    ORDER BY count DESC
                """)
                report['docs_by_type'] = [dict(r) for r in cur.fetchall()]

                # 6. Content storage stats
                cur.execute("""
                    SELECT
                        COUNT(*) AS total_versions,
                        COUNT(*) FILTER (WHERE content_text IS NOT NULL AND content_text != '') AS with_text,
                        COUNT(*) FILTER (WHERE content_html IS NOT NULL AND content_html != '') AS with_html,
                        COUNT(*) FILTER (WHERE (content_text IS NULL OR content_text = '') AND (content_html IS NULL OR content_html = '')) AS empty_shells,
                        pg_size_pretty(COALESCE(SUM(length(content_text)), 0)::bigint) AS total_text_size,
                        pg_size_pretty(COALESCE(SUM(length(content_html)), 0)::bigint) AS total_html_size,
                        COUNT(*) FILTER (WHERE is_latest = true) AS latest_versions
                    FROM document_versions
                """)
                row = cur.fetchone()
                report['content_stats'] = dict(row) if row else {}

                # 7. Documents without any version (empty metadata-only rows)
                cur.execute("""
                    SELECT COUNT(*) AS count
                    FROM documents d
                    WHERE NOT EXISTS (SELECT 1 FROM document_versions dv WHERE dv.document_id = d.id)
                """)
                report['docs_without_versions'] = cur.fetchone()['count']

                # 8. Recent scrape jobs (last 10)
                cur.execute("""
                    SELECT id, status, items_scraped, items_failed,
                           started_at, finished_at,
                           CASE WHEN finished_at IS NOT NULL AND started_at IS NOT NULL
                                THEN EXTRACT(EPOCH FROM (finished_at - started_at))::int
                                ELSE NULL END AS duration_secs,
                           LEFT(logs, 120) AS log_preview
                    FROM scrape_jobs
                    ORDER BY started_at DESC NULLS LAST
                    LIMIT 10
                """)
                report['recent_jobs'] = [self._serialize_row(r) for r in cur.fetchall()]

                # 9. Index info
                cur.execute("""
                    SELECT indexname, tablename,
                           pg_size_pretty(pg_relation_size(indexname::regclass)) AS size
                    FROM pg_indexes
                    WHERE schemaname = 'public'
                    ORDER BY pg_relation_size(indexname::regclass) DESC
                """)
                report['indexes'] = [dict(r) for r in cur.fetchall()]

                # 10. Checkpoint info (SQLite — just report file size if exists)
                import pathlib
                cp_path = pathlib.Path('checkpoint.db')
                if cp_path.exists():
                    size_bytes = cp_path.stat().st_size
                    if size_bytes > 1024 * 1024:
                        report['checkpoint_size'] = f"{size_bytes / (1024*1024):.1f} MB"
                    else:
                        report['checkpoint_size'] = f"{size_bytes / 1024:.1f} KB"
                else:
                    report['checkpoint_size'] = 'Not found'

                # 11. Generated at timestamp
                cur.execute("SELECT now() AT TIME ZONE 'UTC' AS generated_at")
                report['generated_at'] = cur.fetchone()['generated_at'].isoformat() + 'Z'

                return report

        except Exception as e:
            logger.error(f"DB diagnostics failed: {e}")
            raise

    # ========== Jurisdiction Helpers ==========

    def ensure_jurisdiction(self, code: str, name: str = None):
        """Upsert a jurisdiction."""
        if not code:
            return
        try:
            with self._get_conn() as conn:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO jurisdictions (code, name)
                    VALUES (%s, %s)
                    ON CONFLICT (code) DO NOTHING
                """, (code, name or code.upper()))
        except Exception:
            pass

    # ========== Scheduler Config ==========

    def ensure_scheduler_config_table(self):
        """Create scheduler_config table if it doesn't exist (for upgrades from v5.2)."""
        try:
            with self._get_conn() as conn:
                cur = conn.cursor()
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS scheduler_config (
                        id INTEGER PRIMARY KEY DEFAULT 1,
                        enabled BOOLEAN DEFAULT false,
                        schedule_type TEXT DEFAULT 'daily',
                        daily_time TEXT DEFAULT '02:00',
                        interval_hours INTEGER DEFAULT 24,
                        scrape_limit INTEGER DEFAULT 500,
                        source_types TEXT DEFAULT NULL,
                        distribution_mode TEXT DEFAULT 'proportional',
                        supabase_keepalive BOOLEAN DEFAULT false,
                        supabase_keepalive_interval_hours INTEGER DEFAULT 24,
                        last_run_at TIMESTAMPTZ,
                        next_run_at TIMESTAMPTZ,
                        last_keepalive_at TIMESTAMPTZ,
                        updated_at TIMESTAMPTZ DEFAULT now(),
                        CONSTRAINT single_row CHECK (id = 1)
                    )
                """)
                cur.execute("INSERT INTO scheduler_config (id) VALUES (1) ON CONFLICT DO NOTHING")
                logger.info("scheduler_config table ensured")
        except Exception as e:
            logger.warning(f"Failed to ensure scheduler_config table: {e}")

    def get_scheduler_config(self) -> Dict:
        """Get the scheduler configuration (singleton row)."""
        try:
            with self._get_conn() as conn:
                cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                cur.execute("SELECT * FROM scheduler_config WHERE id = 1")
                row = cur.fetchone()
                if row:
                    result = dict(row)
                    # Convert datetimes to ISO strings for JSON serialization
                    for k in ('last_run_at', 'next_run_at', 'last_keepalive_at', 'updated_at'):
                        if result.get(k) and hasattr(result[k], 'isoformat'):
                            result[k] = result[k].isoformat()
                    return result
                return {}
        except Exception as e:
            logger.error(f"Failed to get scheduler config: {e}")
            return {}

    def update_scheduler_config(self, updates: Dict):
        """Update scheduler configuration fields."""
        if not updates:
            return
        try:
            # Only allow known fields to prevent SQL injection
            allowed_fields = {
                'enabled', 'schedule_type', 'daily_time', 'interval_hours',
                'scrape_limit', 'source_types', 'distribution_mode',
                'supabase_keepalive', 'supabase_keepalive_interval_hours',
                'last_run_at', 'next_run_at', 'last_keepalive_at',
            }
            filtered = {k: v for k, v in updates.items() if k in allowed_fields}
            if not filtered:
                return

            # Always update the updated_at timestamp
            filtered['updated_at'] = 'now()'

            set_clauses = []
            values = []
            for k, v in filtered.items():
                if v == 'now()':
                    set_clauses.append(f"{k} = now()")
                else:
                    set_clauses.append(f"{k} = %s")
                    values.append(v)

            sql = f"UPDATE scheduler_config SET {', '.join(set_clauses)} WHERE id = 1"

            with self._get_conn() as conn:
                cur = conn.cursor()
                cur.execute(sql, values)
        except Exception as e:
            logger.error(f"Failed to update scheduler config: {e}")

    def upsert_scrape_target(self, target_data: Dict) -> Optional[str]:
        """Upsert a scrape_targets record, return the target ID."""
        try:
            with self._get_conn() as conn:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO scrape_targets (jurisdiction_code, category, name, url)
                    VALUES (%(jurisdiction_code)s, %(category)s, %(name)s, %(url)s)
                    ON CONFLICT (url) DO UPDATE SET
                        name = EXCLUDED.name,
                        category = EXCLUDED.category
                    RETURNING id
                """, target_data)
                row = cur.fetchone()
                return str(row[0]) if row else None
        except Exception as e:
            logger.error(f"Upsert scrape target failed: {e}")
            return None
