-- =============================================================
-- Migration v5: Full-Text Search (tsvector + GIN indexes)
-- Run on live database:
--   docker exec -i canlii-postgres psql -U canlii -d canlii < database/migration_v5_fulltext_search.sql
--
-- NOTE: CREATE INDEX CONCURRENTLY cannot run inside a transaction.
--       psql runs in autocommit mode by default, which is what we need.
-- =============================================================

-- 1. Add tsvector columns
ALTER TABLE documents ADD COLUMN IF NOT EXISTS search_vector tsvector;
ALTER TABLE document_versions ADD COLUMN IF NOT EXISTS content_search_vector tsvector;

-- 2. Trigger: auto-populate documents.search_vector (title=A, citation=B)
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

-- 3. Trigger: auto-populate document_versions.content_search_vector
--    Only compute for is_latest = true rows (saves space/CPU)
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

-- 4. Backfill existing rows
UPDATE documents
SET search_vector =
    setweight(to_tsvector('english', COALESCE(title, '')), 'A') ||
    setweight(to_tsvector('english', COALESCE(citation, '')), 'B')
WHERE search_vector IS NULL;

UPDATE document_versions
SET content_search_vector = to_tsvector('english', LEFT(content_text, 500000))
WHERE is_latest = true
  AND content_text IS NOT NULL AND content_text != ''
  AND content_search_vector IS NULL;

-- 5. GIN indexes (CONCURRENTLY = no table locks, safe on live DB)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_documents_search_vector
    ON documents USING gin(search_vector);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_doc_versions_content_search_vector
    ON document_versions USING gin(content_search_vector)
    WHERE is_latest = true;
