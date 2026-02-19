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
                minconn=1,
                maxconn=5,
                dsn=db_url,
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
                         target_id, is_active, metadata, source_type, document_type, updated_at)
                    VALUES
                        (%(title)s, %(citation)s, %(source_url)s, %(jurisdiction_code)s,
                         %(category)s, %(target_id)s, %(is_active)s, %(metadata)s,
                         %(source_type)s, %(document_type)s, now())
                    ON CONFLICT (source_url) DO UPDATE SET
                        title = EXCLUDED.title,
                        citation = EXCLUDED.citation,
                        jurisdiction_code = EXCLUDED.jurisdiction_code,
                        category = EXCLUDED.category,
                        is_active = EXCLUDED.is_active,
                        metadata = EXCLUDED.metadata,
                        source_type = EXCLUDED.source_type,
                        document_type = EXCLUDED.document_type,
                        updated_at = now()
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
        """Get comprehensive statistics for the dashboard."""
        try:
            with self._get_conn() as conn:
                cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

                # Total count
                cur.execute("SELECT COUNT(*) AS cnt FROM documents")
                total_docs = cur.fetchone()['cnt']

                # Per source_type counts
                cur.execute("""
                    SELECT source_type, COUNT(*) AS cnt FROM documents
                    WHERE source_type IS NOT NULL
                    GROUP BY source_type
                """)
                source_counts = {r['source_type']: r['cnt'] for r in cur.fetchall()}

                # Per source_type last updated timestamps
                cur.execute("""
                    SELECT source_type, MAX(updated_at) AS last_updated
                    FROM documents
                    WHERE source_type IS NOT NULL
                    GROUP BY source_type
                """)
                last_updated_by_source = {}
                for r in cur.fetchall():
                    val = r['last_updated']
                    last_updated_by_source[r['source_type']] = val.isoformat() if hasattr(val, 'isoformat') else str(val)

                # Per jurisdiction counts
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

                # Per document_type counts
                cur.execute("""
                    SELECT document_type, COUNT(*) AS cnt FROM documents
                    WHERE document_type IS NOT NULL
                    GROUP BY document_type
                """)
                type_counts = {r['document_type']: r['cnt'] for r in cur.fetchall()}

                # Recent scrape jobs (last 10)
                cur.execute("""
                    SELECT * FROM scrape_jobs
                    ORDER BY started_at DESC NULLS LAST
                    LIMIT 10
                """)
                recent_jobs = []
                for r in cur.fetchall():
                    row = dict(r)
                    # Convert UUIDs and datetimes to strings for JSON serialization
                    for k, v in row.items():
                        if hasattr(v, 'isoformat'):
                            row[k] = v.isoformat()
                        elif hasattr(v, 'hex'):  # UUID
                            row[k] = str(v)
                    recent_jobs.append(row)

                return {
                    "total_documents": total_docs,
                    "by_source": source_counts,
                    "by_jurisdiction": jur_counts,
                    "by_type": type_counts,
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
        """Get paginated documents with filtering and title search."""
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
                if search:
                    conditions.append("d.title ILIKE %s")
                    params.append(f"%{search}%")

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
