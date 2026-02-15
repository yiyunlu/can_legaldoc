-- Migration v4: Multi-Source Support
-- Adds source_type and document_type columns, inserts all 14 Canadian jurisdictions

-- 1. Add source_type to documents (tracks where data came from)
ALTER TABLE documents ADD COLUMN IF NOT EXISTS source_type TEXT DEFAULT 'canlii_legacy';

-- 2. Add document_type to documents (legislation vs case law vs regulation)
ALTER TABLE documents ADD COLUMN IF NOT EXISTS document_type TEXT DEFAULT 'legislation';

-- 3. Add source_type to scrape_targets
ALTER TABLE scrape_targets ADD COLUMN IF NOT EXISTS source_type TEXT DEFAULT 'canlii_legacy';

-- 4. Indexes for new columns
CREATE INDEX IF NOT EXISTS idx_documents_source_type ON documents(source_type);
CREATE INDEX IF NOT EXISTS idx_documents_document_type ON documents(document_type);
CREATE INDEX IF NOT EXISTS idx_documents_jurisdiction_source ON documents(jurisdiction_code, source_type);
CREATE INDEX IF NOT EXISTS idx_documents_jurisdiction_doctype ON documents(jurisdiction_code, document_type);

-- 5. Insert all 14 Canadian jurisdictions
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
