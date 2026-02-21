-- =============================================================
-- Canadian Legal Data Platform — Database Schema
-- Combined from migration_v3_schema.sql + migration_v4_multi_source.sql
-- Auto-runs on first Docker PostgreSQL container start
-- =============================================================

-- 1. Jurisdictions
CREATE TABLE IF NOT EXISTS jurisdictions (
    code TEXT PRIMARY KEY,
    name TEXT NOT NULL
);

INSERT INTO jurisdictions (code, name) VALUES
    ('ca', 'Canada (Federal)'),
    ('ab', 'Alberta'),
    ('bc', 'British Columbia'),
    ('on', 'Ontario'),
    ('qc', 'Quebec'),
    ('ns', 'Nova Scotia'),
    ('nb', 'New Brunswick'),
    ('mb', 'Manitoba'),
    ('pe', 'Prince Edward Island'),
    ('sk', 'Saskatchewan'),
    ('nl', 'Newfoundland and Labrador'),
    ('yt', 'Yukon'),
    ('nt', 'Northwest Territories'),
    ('nu', 'Nunavut')
ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name;

-- 2. Scrape targets (legacy CanLII discovery)
CREATE TABLE IF NOT EXISTS scrape_targets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    jurisdiction_code TEXT REFERENCES jurisdictions(code),
    category TEXT NOT NULL,
    name TEXT NOT NULL,
    url TEXT UNIQUE NOT NULL,
    source_type TEXT DEFAULT 'canlii_legacy',
    expected_item_count INTEGER,
    status TEXT DEFAULT 'active',
    last_discovered_at TIMESTAMPTZ DEFAULT now()
);

-- 3. Documents (core metadata)
CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    target_id UUID REFERENCES scrape_targets(id),
    jurisdiction_code TEXT REFERENCES jurisdictions(code),
    category TEXT NOT NULL,
    title TEXT NOT NULL,
    citation TEXT,
    source_url TEXT UNIQUE NOT NULL,
    source_type TEXT DEFAULT 'canlii_legacy',
    document_type TEXT DEFAULT 'legislation',
    is_active BOOLEAN DEFAULT true,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    last_checked_at TIMESTAMPTZ
);

-- 4. Document versions (content with version tracking)
CREATE TABLE IF NOT EXISTS document_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    content_html TEXT,
    content_text TEXT,
    content_hash TEXT,
    scraped_at TIMESTAMPTZ DEFAULT now(),
    version_number INTEGER NOT NULL,
    is_latest BOOLEAN DEFAULT false
);

-- 5. Document chunks (for future RAG / vector search)
CREATE TABLE IF NOT EXISTS document_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    version_id UUID REFERENCES document_versions(id) ON DELETE CASCADE,
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    heading TEXT,
    content_text TEXT NOT NULL,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- 6. Scrape jobs (job tracking / run history)
CREATE TABLE IF NOT EXISTS scrape_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    target_id UUID REFERENCES scrape_targets(id),
    status TEXT NOT NULL,
    started_at TIMESTAMPTZ DEFAULT now(),
    finished_at TIMESTAMPTZ,
    items_scraped INTEGER DEFAULT 0,
    items_failed INTEGER DEFAULT 0,
    logs TEXT
);

-- 7. Indexes
CREATE INDEX IF NOT EXISTS idx_documents_citation ON documents(citation);
CREATE INDEX IF NOT EXISTS idx_documents_title ON documents(title);
CREATE INDEX IF NOT EXISTS idx_documents_jurisdiction ON documents(jurisdiction_code);
CREATE INDEX IF NOT EXISTS idx_documents_source_type ON documents(source_type);
CREATE INDEX IF NOT EXISTS idx_documents_document_type ON documents(document_type);
CREATE INDEX IF NOT EXISTS idx_documents_jurisdiction_source ON documents(jurisdiction_code, source_type);
CREATE INDEX IF NOT EXISTS idx_documents_jurisdiction_doctype ON documents(jurisdiction_code, document_type);
CREATE INDEX IF NOT EXISTS idx_documents_source_checked ON documents(source_type, last_checked_at ASC NULLS FIRST);
CREATE INDEX IF NOT EXISTS idx_document_versions_latest ON document_versions(document_id) WHERE is_latest = true;
CREATE INDEX IF NOT EXISTS idx_document_chunks_version ON document_chunks(version_id);
CREATE INDEX IF NOT EXISTS idx_scrape_jobs_started_at ON scrape_jobs(started_at DESC);

-- 8. Scheduler configuration (singleton row)
CREATE TABLE IF NOT EXISTS scheduler_config (
    id INTEGER PRIMARY KEY DEFAULT 1,
    enabled BOOLEAN DEFAULT false,
    schedule_type TEXT DEFAULT 'daily',              -- 'daily' | 'interval'
    daily_time TEXT DEFAULT '02:00',                 -- HH:MM in UTC
    interval_hours INTEGER DEFAULT 24,
    scrape_limit INTEGER DEFAULT 500,
    source_types TEXT DEFAULT NULL,                  -- JSON array string, null = all enabled
    distribution_mode TEXT DEFAULT 'proportional',
    supabase_keepalive BOOLEAN DEFAULT false,
    supabase_keepalive_interval_hours INTEGER DEFAULT 24,
    last_run_at TIMESTAMPTZ,
    next_run_at TIMESTAMPTZ,
    last_keepalive_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT single_row CHECK (id = 1)
);
INSERT INTO scheduler_config (id) VALUES (1) ON CONFLICT DO NOTHING;

-- 9. Source sync log (per-source incremental tracking)
CREATE TABLE IF NOT EXISTS source_sync_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_type TEXT NOT NULL,
    mode TEXT DEFAULT 'full',
    trigger_source TEXT DEFAULT 'manual',
    started_at TIMESTAMPTZ DEFAULT now(),
    finished_at TIMESTAMPTZ,
    docs_discovered INTEGER DEFAULT 0,
    docs_checked INTEGER DEFAULT 0,
    docs_new INTEGER DEFAULT 0,
    docs_updated INTEGER DEFAULT 0,
    docs_unchanged INTEGER DEFAULT 0,
    docs_failed INTEGER DEFAULT 0,
    docs_skipped_fresh INTEGER DEFAULT 0,
    max_age_hours INTEGER,
    error_message TEXT,
    notes TEXT
);
CREATE INDEX IF NOT EXISTS idx_source_sync_log_source
    ON source_sync_log (source_type, started_at DESC);

-- 10. LZ4 compression for large text columns (PostgreSQL 14+)
ALTER TABLE document_versions ALTER COLUMN content_html SET COMPRESSION lz4;
ALTER TABLE document_versions ALTER COLUMN content_text SET COMPRESSION lz4;

-- 11. Full-text search columns
ALTER TABLE documents ADD COLUMN IF NOT EXISTS search_vector tsvector;
ALTER TABLE document_versions ADD COLUMN IF NOT EXISTS content_search_vector tsvector;

-- 12. Trigger: auto-maintain documents.search_vector (title=A, citation=B)
CREATE OR REPLACE FUNCTION documents_search_vector_update() RETURNS trigger AS $$
BEGIN
    NEW.search_vector :=
        setweight(to_tsvector('english', COALESCE(NEW.title, '')), 'A') ||
        setweight(to_tsvector('english', COALESCE(NEW.citation, '')), 'B');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_documents_search_vector ON documents;
CREATE TRIGGER trg_documents_search_vector
    BEFORE INSERT OR UPDATE OF title, citation ON documents
    FOR EACH ROW EXECUTE FUNCTION documents_search_vector_update();

-- 13. Trigger: auto-maintain document_versions.content_search_vector (latest only)
CREATE OR REPLACE FUNCTION doc_versions_search_vector_update() RETURNS trigger AS $$
BEGIN
    IF NEW.is_latest = true AND NEW.content_text IS NOT NULL AND NEW.content_text != '' THEN
        NEW.content_search_vector := to_tsvector('english', LEFT(NEW.content_text, 500000));
    ELSE
        NEW.content_search_vector := NULL;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_doc_versions_search_vector ON document_versions;
CREATE TRIGGER trg_doc_versions_search_vector
    BEFORE INSERT OR UPDATE OF content_text, is_latest ON document_versions
    FOR EACH ROW EXECUTE FUNCTION doc_versions_search_vector_update();

-- 14. GIN indexes for full-text search
CREATE INDEX IF NOT EXISTS idx_documents_search_vector
    ON documents USING gin(search_vector);
CREATE INDEX IF NOT EXISTS idx_doc_versions_content_search_vector
    ON document_versions USING gin(content_search_vector)
    WHERE is_latest = true;
