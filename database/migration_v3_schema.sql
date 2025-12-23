-- 0. 开启 pgvector 扩展 (支持向量存储)
CREATE EXTENSION IF NOT EXISTS vector;

-- 1. 创建辖区与类别表
CREATE TABLE IF NOT EXISTS jurisdictions (
    code TEXT PRIMARY KEY, -- 如 'ab', 'ca', 'bc'
    name TEXT NOT NULL
);

-- 2. 爬取目标表 (由 DiscoveryEngine 发现)
CREATE TABLE IF NOT EXISTS scrape_targets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    jurisdiction_code TEXT REFERENCES jurisdictions(code),
    category TEXT NOT NULL, -- 'Legislation' (立法), 'Courts' (法院), 'Tribunals' (论坛)
    name TEXT NOT NULL,
    url TEXT UNIQUE NOT NULL,
    expected_item_count INTEGER,
    status TEXT DEFAULT 'active', -- 'active' (活跃), 'paused' (暂停), 'deprecated' (废弃)
    last_discovered_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

-- 3. 核心文档存储表
CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    target_id UUID REFERENCES scrape_targets(id),
    jurisdiction_code TEXT REFERENCES jurisdictions(code),
    category TEXT NOT NULL,
    title TEXT NOT NULL,
    citation TEXT, -- 引文 (例如: RSA 2000, c A-1)
    source_url TEXT UNIQUE NOT NULL,
    is_active BOOLEAN DEFAULT true,
    metadata JSONB DEFAULT '{}'::jsonb, -- 用于扩展字段（例如：法官、当事人、颁布日期）
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

-- 4. 内容版本控制表 (支持追踪法律随时间的变化)
CREATE TABLE IF NOT EXISTS document_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID REFERENCES documents(id),
    content_html TEXT,
    content_text TEXT,
    content_hash TEXT, -- SHA-256 用于变化检测
    scraped_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    version_number INTEGER NOT NULL,
    is_latest BOOLEAN DEFAULT false
);

-- 5. 文档分块表 (用于 RAG)
-- 注意：在 Supabase 中运行前请确保已开启 pgvector 扩展：CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS document_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    version_id UUID REFERENCES document_versions(id),
    document_id UUID REFERENCES documents(id),
    chunk_index INTEGER NOT NULL, -- 排序
    heading TEXT, -- 章节标题 (如 "Section 5")
    content_text TEXT NOT NULL,
    embedding vector(1536), -- 存储向量 (需 pgvector 扩展)
    metadata JSONB DEFAULT '{}'::jsonb, -- 存储层级上下文
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

-- 6. 调度与任务管理表 (Job Tracking)
CREATE TABLE IF NOT EXISTS scrape_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    target_id UUID REFERENCES scrape_targets(id),
    status TEXT NOT NULL, -- 'running' (进行中), 'completed' (已完成), 'failed' (失败)
    started_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    finished_at TIMESTAMP WITH TIME ZONE,
    items_scraped INTEGER DEFAULT 0,
    items_failed INTEGER DEFAULT 0,
    logs TEXT
);

-- 7. 索引优化
CREATE INDEX IF NOT EXISTS idx_documents_citation ON documents(citation);
CREATE INDEX IF NOT EXISTS idx_documents_title ON documents(title);
CREATE INDEX IF NOT EXISTS idx_documents_jurisdiction ON documents(jurisdiction_code);
CREATE INDEX IF NOT EXISTS idx_document_versions_latest ON document_versions(document_id) WHERE is_latest = true;
CREATE INDEX IF NOT EXISTS idx_document_chunks_version ON document_chunks(version_id);

-- 8. 启用行级安全 (Row Level Security)
ALTER TABLE jurisdictions ENABLE ROW LEVEL SECURITY;
ALTER TABLE scrape_targets ENABLE ROW LEVEL SECURITY;
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE scrape_jobs ENABLE ROW LEVEL SECURITY;

-- 9. 创建安全策略 (Security Policies)
DO $$
DECLARE
    tbl_name TEXT;
    all_tables TEXT[] := ARRAY['jurisdictions', 'scrape_targets', 'documents', 'document_versions', 'document_chunks', 'scrape_jobs'];
BEGIN
    FOREACH tbl_name IN ARRAY all_tables LOOP
        -- 为 service_role 提供全权限
        EXECUTE format('CREATE POLICY "service_role_all" ON %I FOR ALL TO service_role USING (true) WITH CHECK (true)', tbl_name);
        -- 为 authenticated 提供全权限
        EXECUTE format('CREATE POLICY "authenticated_all" ON %I FOR ALL TO authenticated USING (true) WITH CHECK (true)', tbl_name);
        -- 为 anon 提供只读权限
        EXECUTE format('CREATE POLICY "anon_select" ON %I FOR SELECT TO anon USING (true)', tbl_name);
    END LOOP;
END $$;

-- 数据迁移步骤 (逻辑示意，需手动执行)：
-- 1. 插入初始辖区
-- INSERT INTO jurisdictions (code, name) VALUES ('ab', 'Alberta') ON CONFLICT DO NOTHING;

-- 2. 插入初始目标 (假设 ab_statutes 的来源)
-- INSERT INTO scrape_targets (jurisdiction_code, category, name, url) 
-- VALUES ('ab', 'Legislation', 'Alberta Statutes', 'https://www.canlii.org/ab/laws/stat')
-- ON CONFLICT DO NOTHING;

-- 3. 迁移现有数据 (由于涉及到 UUID 关联，建议通过脚本迁移或使用以下逻辑)
-- 迁移 documents
-- INSERT INTO documents (target_id, jurisdiction_code, category, title, citation, source_url, metadata)
-- SELECT (SELECT id FROM scrape_targets WHERE jurisdiction_code = 'ab' LIMIT 1), 'ab', 'Legislation', title, citation, source_url, jsonb_build_object('last_updated', last_updated)
-- FROM ab_statutes
-- ON CONFLICT (source_url) DO NOTHING;

-- 4. 迁移 document_versions
-- INSERT INTO document_versions (document_id, content_html, content_text, version_number, is_latest, scraped_at)
-- SELECT d.id, s.content_html, s.content_text, 1, true, s.scraped_at
-- FROM ab_statutes s
-- JOIN documents d ON s.source_url = d.source_url;
