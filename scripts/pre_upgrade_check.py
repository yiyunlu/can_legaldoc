#!/usr/bin/env python3
"""
v5.5 升级前诊断脚本 — 在 v5.4 环境下运行
检查生产数据库健康状态，为升级提供基线报告。

用法:
  docker exec canlii-platform python scripts/pre_upgrade_check.py

无外部依赖 — 只用 psycopg2 + sqlite3（Docker 容器内已有）
"""
import os
import sys
import json
import sqlite3
from datetime import datetime

# ── DB连接 ──
# 复用环境变量，不依赖任何项目模块
DB_URL = os.environ.get("DATABASE_URL", "")
if not DB_URL:
    # docker-compose 默认值
    pg_pass = os.environ.get("POSTGRES_PASSWORD", "canlii_secure_pwd_2024")
    DB_URL = f"postgresql://canlii:{pg_pass}@postgres:5432/canlii"

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    print("❌ psycopg2 未安装，无法连接数据库")
    sys.exit(1)


def connect():
    try:
        conn = psycopg2.connect(DB_URL)
        conn.autocommit = False
        return conn
    except Exception as e:
        print(f"❌ 数据库连接失败: {e}")
        sys.exit(1)


def section(title):
    print(f"\n{'─'*60}")
    print(f"  {title}")
    print(f"{'─'*60}")


def main():
    conn = connect()
    cur = conn.cursor()

    print("=" * 60)
    print("  升级前诊断报告 (v5.4 → v5.5)")
    print(f"  时间: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print("=" * 60)

    issues = []
    warnings = []

    # ════════════════════════════════════════════════════════
    section("1. 表结构验证")
    # ════════════════════════════════════════════════════════
    expected_tables = [
        "documents", "document_versions", "scrape_jobs",
        "jurisdictions", "scrape_targets", "scheduler_config",
    ]
    cur.execute("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public' ORDER BY table_name
    """)
    existing = [r[0] for r in cur.fetchall()]
    for t in expected_tables:
        status = "✅" if t in existing else "❌"
        if t not in existing:
            issues.append(f"缺少表: {t}")
        print(f"   {status} {t}")
    extra = set(existing) - set(expected_tables)
    if extra:
        print(f"   ℹ️  额外表: {', '.join(sorted(extra))}")

    # documents 列检查
    cur.execute("""
        SELECT column_name, data_type FROM information_schema.columns
        WHERE table_name = 'documents' ORDER BY ordinal_position
    """)
    doc_cols = {r[0]: r[1] for r in cur.fetchall()}
    required_cols = ["id", "source_url", "title", "citation",
                     "jurisdiction_code", "source_type", "document_type",
                     "category", "is_active", "metadata"]
    missing_cols = [c for c in required_cols if c not in doc_cols]
    if missing_cols:
        issues.append(f"documents 缺少列: {missing_cols}")
        print(f"   ❌ documents 缺少列: {missing_cols}")
    else:
        print(f"   ✅ documents 列完整 ({len(doc_cols)} 列)")

    # ════════════════════════════════════════════════════════
    section("2. 数据量统计")
    # ════════════════════════════════════════════════════════
    cur.execute("SELECT count(*) FROM documents")
    total_docs = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM document_versions")
    total_vers = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM scrape_jobs")
    total_jobs = cur.fetchone()[0]
    print(f"   文档总数:   {total_docs:>8,}")
    print(f"   版本总数:   {total_vers:>8,}")
    print(f"   采集任务:   {total_jobs:>8,}")

    if total_docs == 0:
        warnings.append("数据库为空 — 还没有采集过任何数据")
        print("   ⚠️  数据库为空")

    # 按 source_type
    print()
    cur.execute("""
        SELECT source_type, count(*) as cnt
        FROM documents GROUP BY source_type ORDER BY cnt DESC
    """)
    source_counts = cur.fetchall()
    print(f"   {'来源':<30s} {'数量':>8s}")
    print(f"   {'─'*30} {'─'*8}")
    for r in source_counts:
        print(f"   {r[0]:<30s} {r[1]:>8,}")

    # 按 jurisdiction
    print()
    cur.execute("""
        SELECT jurisdiction_code, count(*) FROM documents
        GROUP BY jurisdiction_code ORDER BY count(*) DESC
    """)
    for r in cur.fetchall():
        print(f"   辖区 {r[0]:<6s} {r[1]:>8,}")

    # ════════════════════════════════════════════════════════
    section("3. 数据完整性")
    # ════════════════════════════════════════════════════════
    integrity_checks = [
        ("NULL/空标题",      "title IS NULL OR title = ''"),
        ("NULL/空 URL",      "source_url IS NULL OR source_url = ''"),
        ("NULL 引用号",      "citation IS NULL"),
        ("NULL 辖区",        "jurisdiction_code IS NULL"),
        ("NULL 来源类型",    "source_type IS NULL"),
        ("NULL 文档类型",    "document_type IS NULL"),
    ]
    for label, cond in integrity_checks:
        cur.execute(f"SELECT count(*) FROM documents WHERE {cond}")
        cnt = cur.fetchone()[0]
        status = "✅" if cnt == 0 else "❌"
        if cnt > 0:
            issues.append(f"{label}: {cnt} 条")
        print(f"   {status} {label}: {cnt}")

    # 重复 URL
    cur.execute("""
        SELECT source_url, count(*) FROM documents
        GROUP BY source_url HAVING count(*) > 1
    """)
    dupes = cur.fetchall()
    status = "✅" if len(dupes) == 0 else "❌"
    if dupes:
        issues.append(f"重复 URL: {len(dupes)} 组")
    print(f"   {status} 重复 URL: {len(dupes)} 组")
    for d in dupes[:5]:
        print(f"      {d[0][:80]} (x{d[1]})")

    # 孤儿版本
    cur.execute("""
        SELECT count(*) FROM document_versions dv
        LEFT JOIN documents d ON d.id = dv.document_id
        WHERE d.id IS NULL
    """)
    orphans = cur.fetchone()[0]
    status = "✅" if orphans == 0 else "❌"
    if orphans > 0:
        issues.append(f"孤儿版本: {orphans}")
    print(f"   {status} 孤儿版本 (version无对应document): {orphans}")

    # 无版本文档
    cur.execute("""
        SELECT count(*) FROM documents d
        LEFT JOIN document_versions dv ON d.id = dv.document_id
        WHERE dv.id IS NULL
    """)
    no_ver = cur.fetchone()[0]
    status = "✅" if no_ver == 0 else "❌"
    if no_ver > 0:
        issues.append(f"无版本文档: {no_ver}")
    print(f"   {status} 无版本文档 (document无对应version): {no_ver}")

    # ════════════════════════════════════════════════════════
    section("4. URL 质量")
    # ════════════════════════════════════════════════════════
    cur.execute("SELECT count(*) FROM documents WHERE source_url LIKE '%% %%'")
    spaces = cur.fetchone()[0]
    if spaces > 0:
        warnings.append(f"{spaces} 条 URL 含原始空格（v5.5 会自动编码）")
    print(f"   {'⚠️' if spaces else '✅'} 含原始空格: {spaces}")
    if spaces > 0:
        cur.execute("SELECT source_url FROM documents WHERE source_url LIKE '%% %%' LIMIT 3")
        for r in cur.fetchall():
            print(f"      {r[0][:90]}")

    cur.execute("SELECT count(*) FROM documents WHERE source_url LIKE '%%,%%'")
    commas = cur.fetchone()[0]
    if commas > 0:
        warnings.append(f"{commas} 条 URL 含原始逗号（v5.5 会自动编码）")
    print(f"   {'⚠️' if commas else '✅'} 含原始逗号: {commas}")
    if commas > 0:
        cur.execute("SELECT source_url FROM documents WHERE source_url LIKE '%%,%%' LIMIT 3")
        for r in cur.fetchall():
            print(f"      {r[0][:90]}")

    cur.execute("SELECT count(*) FROM documents WHERE source_url NOT LIKE 'http%%'")
    bad_proto = cur.fetchone()[0]
    if bad_proto > 0:
        issues.append(f"{bad_proto} 条 URL 非 http 开头")
    print(f"   {'❌' if bad_proto else '✅'} 非 HTTP(S) URL: {bad_proto}")

    # ════════════════════════════════════════════════════════
    section("5. 标题质量")
    # ════════════════════════════════════════════════════════
    cur.execute("""
        SELECT title, source_type, source_url FROM documents
        WHERE lower(trim(title)) IN (
            'general', 'forms', 'fees', 'exemptions', 'exemption',
            'administration', 'procedures', 'designation', 'enforcement',
            'standards', 'licensing', 'inspection', 'appeal', 'board'
        )
        ORDER BY title, source_type
    """)
    generics = cur.fetchall()
    if generics:
        warnings.append(f"{len(generics)} 条通用标题（v5.5 NB适配器会自动限定）")
    print(f"   {'⚠️' if generics else '✅'} 未限定通用标题: {len(generics)}")
    for g in generics[:10]:
        print(f"      [{g[1]}] \"{g[0]}\"  {g[2][:60]}")
    if len(generics) > 10:
        print(f"      ... 还有 {len(generics) - 10} 条")

    # 同源重复标题
    cur.execute("""
        SELECT title, source_type, count(*) FROM documents
        GROUP BY title, source_type HAVING count(*) > 1
        ORDER BY count(*) DESC LIMIT 10
    """)
    title_dupes = cur.fetchall()
    if title_dupes:
        warnings.append(f"{len(title_dupes)} 组同源重复标题")
        print(f"   ⚠️  同源重复标题: {len(title_dupes)} 组")
        for t in title_dupes[:5]:
            print(f"      [{t[1]}] \"{t[0][:50]}\" (x{t[2]})")
    else:
        print(f"   ✅ 同源重复标题: 0")

    # ════════════════════════════════════════════════════════
    section("6. 内容质量")
    # ════════════════════════════════════════════════════════
    cur.execute("""
        SELECT count(*) FROM document_versions
        WHERE content_text IS NULL OR length(content_text) = 0
    """)
    no_text = cur.fetchone()[0]
    if no_text > 0:
        issues.append(f"{no_text} 条版本无文本内容")
    print(f"   {'❌' if no_text else '✅'} 无文本内容: {no_text}")

    cur.execute("""
        SELECT count(*) FROM document_versions
        WHERE content_html IS NULL OR length(content_html) = 0
    """)
    no_html = cur.fetchone()[0]
    print(f"   {'⚠️' if no_html else '✅'} 无 HTML 内容: {no_html}")

    cur.execute("SELECT count(*) FROM document_versions WHERE length(content_text) < 100")
    tiny = cur.fetchone()[0]
    if tiny > 0:
        warnings.append(f"{tiny} 条极短内容(<100字符)")
    print(f"   {'⚠️' if tiny else '✅'} 极短内容 (<100字符): {tiny}")
    if tiny > 0:
        cur.execute("""
            SELECT d.source_type, d.title, length(dv.content_text) as len
            FROM documents d JOIN document_versions dv ON d.id = dv.document_id
            WHERE length(dv.content_text) < 100
            ORDER BY len LIMIT 5
        """)
        for r in cur.fetchall():
            print(f"      [{r[0]}] {r[1][:45]} ({r[2]} chars)")

    # 内容大小分布
    if total_docs > 0:
        cur.execute("""
            SELECT source_type,
                   count(*) as cnt,
                   min(length(dv.content_text)) as min_l,
                   avg(length(dv.content_text))::int as avg_l,
                   max(length(dv.content_text)) as max_l,
                   sum(length(dv.content_text)) as total_l
            FROM documents d
            JOIN document_versions dv ON d.id = dv.document_id
            GROUP BY source_type ORDER BY cnt DESC
        """)
        print()
        print(f"   {'来源':<28s} {'数量':>5s} {'最短':>7s} {'平均':>8s} {'最长':>9s} {'总计MB':>7s}")
        print(f"   {'─'*28} {'─'*5} {'─'*7} {'─'*8} {'─'*9} {'─'*7}")
        for r in cur.fetchall():
            total_mb = round((r[5] or 0) / 1024 / 1024, 1)
            print(f"   {r[0]:<28s} {r[1]:>5,} {(r[2] or 0):>7,} {(r[3] or 0):>8,} {(r[4] or 0):>9,} {total_mb:>6.1f}M")

    # ════════════════════════════════════════════════════════
    section("7. 最近采集任务")
    # ════════════════════════════════════════════════════════
    # 兼容不同版本的 scrape_jobs 列名
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'scrape_jobs' ORDER BY ordinal_position
    """)
    job_cols = [r[0] for r in cur.fetchall()]
    print(f"   scrape_jobs 列: {', '.join(job_cols)}")

    if "scrape_jobs" in existing:
        # 用通用查询
        cur.execute(f"SELECT * FROM scrape_jobs ORDER BY started_at DESC LIMIT 5")
        jobs = cur.fetchall()
        print(f"   最近 {len(jobs)} 条任务:")
        for j in jobs:
            row = dict(zip(job_cols, j))
            job_id = str(row.get("id", "?"))[:8]
            status = row.get("status", "?")
            started = str(row.get("started_at", "?"))[:19]
            scraped = row.get("items_scraped", row.get("documents_scraped", "?"))
            failed = row.get("items_failed", row.get("errors", "?"))
            logs = str(row.get("logs", row.get("log", "")))[:80]
            print(f"   {job_id}.. {status:10s} {started}  ok={scraped} err={failed}")
            if logs:
                print(f"      {logs}")

    # ════════════════════════════════════════════════════════
    section("8. Checkpoint (SQLite)")
    # ════════════════════════════════════════════════════════
    cp_path = None
    for p in ["/app/checkpoint.db", "/app/data/checkpoint.db", "checkpoint.db"]:
        if os.path.exists(p):
            cp_path = p
            break

    if cp_path:
        sq = sqlite3.connect(cp_path)
        sqc = sq.cursor()
        sqc.execute("SELECT count(*) FROM checkpoints")
        cp_total = sqc.fetchone()[0]
        sqc.execute("SELECT min(scraped_at), max(scraped_at) FROM checkpoints")
        dates = sqc.fetchone()
        print(f"   路径: {cp_path}")
        print(f"   条目: {cp_total:,}")
        print(f"   时间: {dates[0]} → {dates[1]}")

        # 按域名分类
        sqc.execute("""
            SELECT
                CASE
                    WHEN url LIKE '%canlii.org%' THEN 'canlii'
                    WHEN url LIKE '%laws-lois.justice%' THEN 'justice_canada'
                    WHEN url LIKE '%bclaws%' THEN 'bc_laws'
                    WHEN url LIKE '%kings-printer.alberta%' OR url LIKE '%open.alberta%' THEN 'alberta'
                    WHEN url LIKE '%gov.mb.ca%' THEN 'manitoba'
                    WHEN url LIKE '%assembly.nl.ca%' THEN 'newfoundland'
                    WHEN url LIKE '%nslegislature%' OR url LIKE '%novascotia%' THEN 'nova_scotia'
                    WHEN url LIKE '%laws.gnb%' THEN 'new_brunswick'
                    WHEN url LIKE '%ontario.ca%' THEN 'ontario'
                    ELSE 'other'
                END as source, count(*)
            FROM checkpoints GROUP BY source ORDER BY count(*) DESC
        """)
        for r in sqc.fetchall():
            print(f"      {r[0]:<20s} {r[1]:>6,}")

        # Checkpoint vs DB 一致性
        sqc.execute("SELECT url FROM checkpoints")
        cp_urls = set(r[0] for r in sqc.fetchall())
        sq.close()

        cur.execute("SELECT source_url FROM documents")
        db_urls = set(r[0] for r in cur.fetchall())

        in_db_not_cp = db_urls - cp_urls
        in_cp_not_db = cp_urls - db_urls

        if in_db_not_cp:
            warnings.append(f"{len(in_db_not_cp)} 条 DB URL 不在 Checkpoint 中")
        print(f"\n   {'⚠️' if in_db_not_cp else '✅'} DB有 Checkpoint没有: {len(in_db_not_cp)}")
        for u in sorted(in_db_not_cp)[:3]:
            print(f"      {u[:90]}")
        print(f"   ℹ️  Checkpoint有 DB没有: {len(in_cp_not_db)}")
    else:
        print("   ⚠️  checkpoint.db 未找到")
        warnings.append("checkpoint.db 未找到")

    # ════════════════════════════════════════════════════════
    section("9. 数据库大小 & 索引")
    # ════════════════════════════════════════════════════════
    cur.execute("""
        SELECT pg_size_pretty(pg_database_size(current_database()))
    """)
    print(f"   数据库总大小: {cur.fetchone()[0]}")

    cur.execute("""
        SELECT relname, pg_size_pretty(pg_total_relation_size(relid))
        FROM pg_catalog.pg_statio_user_tables
        ORDER BY pg_total_relation_size(relid) DESC
    """)
    for r in cur.fetchall():
        print(f"      {r[0]:<30s} {r[1]}")

    # 索引
    cur.execute("""
        SELECT indexname, tablename
        FROM pg_indexes WHERE schemaname = 'public'
        ORDER BY tablename, indexname
    """)
    indexes = cur.fetchall()
    print(f"\n   索引 ({len(indexes)} 个):")
    for r in indexes:
        print(f"      [{r[1]}] {r[0]}")

    # ════════════════════════════════════════════════════════
    section("10. 环境信息")
    # ════════════════════════════════════════════════════════
    cur.execute("SELECT version()")
    pg_ver = cur.fetchone()[0].split(",")[0]
    print(f"   PostgreSQL: {pg_ver}")
    print(f"   Python: {sys.version.split()[0]}")
    print(f"   DATABASE_URL: ...@{DB_URL.split('@')[-1] if '@' in DB_URL else '(masked)'}")

    # 检查当前版本
    version_file = None
    for p in ["/app/api/main.py", "api/main.py"]:
        if os.path.exists(p):
            version_file = p
            break
    if version_file:
        with open(version_file) as f:
            for line in f:
                if '"version"' in line and ":" in line:
                    ver = line.strip()
                    print(f"   当前版本: {ver}")
                    break

    # ════════════════════════════════════════════════════════
    # 升级前数据快照 (JSON) — 供升级后对比
    # ════════════════════════════════════════════════════════
    snapshot = {
        "timestamp": datetime.utcnow().isoformat(),
        "total_documents": total_docs,
        "total_versions": total_vers,
        "total_jobs": total_jobs,
        "by_source": {r[0]: r[1] for r in source_counts},
        "issues": issues,
        "warnings": warnings,
    }
    snapshot_path = "/app/data/pre_upgrade_snapshot.json"
    try:
        os.makedirs(os.path.dirname(snapshot_path), exist_ok=True)
        with open(snapshot_path, "w") as f:
            json.dump(snapshot, f, indent=2, default=str)
        print(f"\n   📋 快照已保存: {snapshot_path}")
    except Exception as e:
        print(f"\n   ⚠️  快照保存失败: {e}")

    # ════════════════════════════════════════════════════════
    # Summary
    # ════════════════════════════════════════════════════════
    print()
    print("=" * 60)
    if issues:
        print(f"  ❌ 发现 {len(issues)} 个问题 (建议升级前修复):")
        for i, issue in enumerate(issues, 1):
            print(f"     {i}. {issue}")
    if warnings:
        print(f"  ⚠️  {len(warnings)} 个提示 (v5.5 会自动处理):")
        for i, w in enumerate(warnings, 1):
            print(f"     {i}. {w}")
    if not issues and not warnings:
        print("  ✅ 所有检查通过 — 可以安全升级到 v5.5")
    elif not issues:
        print("  ✅ 无阻塞问题 — 可以安全升级到 v5.5")
    print("=" * 60)
    print()
    print("升级命令:")
    print("  cd /opt/canlii && git pull && docker compose up -d --build")
    print()
    print("升级后验证:")
    print("  docker exec canlii-platform python scripts/db_health_check.py")
    print()

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
