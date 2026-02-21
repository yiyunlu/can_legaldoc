-- =============================================================
-- Migration v6: Incremental Update Infrastructure
-- Adds per-document freshness tracking and source sync logging
-- Run: docker exec -i canlii-postgres psql -U canlii -d canlii < database/migration_v6_incremental.sql
-- =============================================================

BEGIN;

-- 1. Add last_checked_at to documents — tracks when each doc was last fetched/verified
ALTER TABLE documents ADD COLUMN IF NOT EXISTS last_checked_at TIMESTAMPTZ;

-- 2. Backfill from latest document_versions.scraped_at (best available data)
UPDATE documents d
SET last_checked_at = dv.scraped_at
FROM document_versions dv
WHERE dv.document_id = d.id
  AND dv.is_latest = true
  AND d.last_checked_at IS NULL;

-- For documents without versions, use updated_at as fallback
UPDATE documents
SET last_checked_at = updated_at
WHERE last_checked_at IS NULL;

-- 3. Index for efficient freshness queries
--    "Give me stale docs for source_type X, ordered by oldest-checked first"
CREATE INDEX IF NOT EXISTS idx_documents_source_checked
    ON documents (source_type, last_checked_at ASC NULLS FIRST);

-- 4. Source sync log — granular per-source history (replaces scrape_jobs for multi-source)
CREATE TABLE IF NOT EXISTS source_sync_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_type TEXT NOT NULL,
    mode TEXT DEFAULT 'full',               -- 'full' | 'incremental'
    trigger_source TEXT DEFAULT 'manual',    -- 'manual' | 'scheduler' | 'cli'
    started_at TIMESTAMPTZ DEFAULT now(),
    finished_at TIMESTAMPTZ,
    -- Discovery stats
    docs_discovered INTEGER DEFAULT 0,
    -- Fetch/upsert stats
    docs_checked INTEGER DEFAULT 0,         -- total docs processed (fetched + verified)
    docs_new INTEGER DEFAULT 0,             -- brand new documents
    docs_updated INTEGER DEFAULT 0,         -- existing docs with content changes
    docs_unchanged INTEGER DEFAULT 0,       -- existing docs, same content hash
    docs_failed INTEGER DEFAULT 0,          -- fetch or save errors
    docs_skipped_fresh INTEGER DEFAULT 0,   -- skipped because recently checked
    -- Metadata
    max_age_hours INTEGER,                  -- NULL for full mode
    error_message TEXT,
    notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_source_sync_log_source
    ON source_sync_log (source_type, started_at DESC);

COMMIT;

-- Verify migration
SELECT 'documents.last_checked_at' AS check_item,
       COUNT(*) AS total,
       COUNT(last_checked_at) AS with_value,
       COUNT(*) - COUNT(last_checked_at) AS null_count
FROM documents
UNION ALL
SELECT 'source_sync_log table',
       (SELECT COUNT(*) FROM source_sync_log), 0, 0;
