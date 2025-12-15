-- CanLII Alberta 法规数据库架构（修复版）
-- 创建时间: 2025-12-13
-- 更新: 修复 RLS 策略问题

-- 创建法规表
CREATE TABLE IF NOT EXISTS ab_statutes (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    title TEXT NOT NULL,
    citation TEXT,
    content_html TEXT,
    content_text TEXT,
    source_url TEXT UNIQUE NOT NULL,
    scraped_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()),
    last_updated TIMESTAMP WITH TIME ZONE
);

-- 创建索引以提高查询性能
CREATE INDEX IF NOT EXISTS idx_ab_statutes_citation ON ab_statutes(citation);
CREATE INDEX IF NOT EXISTS idx_ab_statutes_title ON ab_statutes(title);
CREATE INDEX IF NOT EXISTS idx_ab_statutes_scraped_at ON ab_statutes(scraped_at);

-- 启用行级安全 (Row Level Security)
ALTER TABLE ab_statutes ENABLE ROW LEVEL SECURITY;

-- 删除旧策略（如果存在）
DROP POLICY IF EXISTS "Allow all actions for service role" ON ab_statutes;
DROP POLICY IF EXISTS "Allow read access for anon" ON ab_statutes;

-- 创建新策略：允许服务角色进行所有操作
CREATE POLICY "service_role_all" ON ab_statutes
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

-- 创建策略：允许认证用户进行所有操作
CREATE POLICY "authenticated_all" ON ab_statutes
    FOR ALL
    TO authenticated
    USING (true)
    WITH CHECK (true);

-- 创建策略：允许匿名用户只读访问
CREATE POLICY "anon_select" ON ab_statutes
    FOR SELECT
    TO anon
    USING (true);

-- 添加注释
COMMENT ON TABLE ab_statutes IS 'Alberta Consolidated Statutes from CanLII';
COMMENT ON COLUMN ab_statutes.id IS '主键 UUID';
COMMENT ON COLUMN ab_statutes.title IS '法规标题';
COMMENT ON COLUMN ab_statutes.citation IS '法规引文编号 (例如: RSA 2000, c A-1)';
COMMENT ON COLUMN ab_statutes.content_html IS '法规完整HTML内容';
COMMENT ON COLUMN ab_statutes.content_text IS '法规纯文本内容（用于搜索）';
COMMENT ON COLUMN ab_statutes.source_url IS '来源URL（唯一）';
COMMENT ON COLUMN ab_statutes.scraped_at IS '爬取时间';
COMMENT ON COLUMN ab_statutes.last_updated IS '最后更新时间';

-- 查看当前策略
SELECT schemaname, tablename, policyname, roles, cmd 
FROM pg_policies 
WHERE tablename = 'ab_statutes';
