-- 修复权限问题，允许所有用户（包括anon key）访问 ab_statutes 表
-- 请在 Supabase 控制台的 SQL Editor 中执行此操作

-- 1. 禁用 RLS (暂时解决方案，最简单)
ALTER TABLE ab_statutes DISABLE ROW LEVEL SECURITY;

-- 或者 2. 允许匿名访问 (如果必须保持 RLS)
-- CREATE POLICY "Enable access to all users" ON ab_statutes FOR ALL USING (true) WITH CHECK (true);
