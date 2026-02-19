#!/usr/bin/env python3
"""
v5.5 升级前深度诊断 — 针对生产环境发现的问题逐一排查
用法: docker exec canlii-platform python /app/scripts/pre_upgrade_deep_check.py
"""
import os
import sys
import sqlite3
from collections import defaultdict

DB_URL = os.environ.get("DATABASE_URL", "")
if not DB_URL:
    pg_pass = os.environ.get("POSTGRES_PASSWORD", "canlii_secure_pwd_2024")
    DB_URL = f"postgresql://canlii:{pg_pass}@postgres:5432/canlii"

import psycopg2
conn = psycopg2.connect(DB_URL)
cur = conn.cursor()


def section(title):
    print(f"\n{'='*65}")
    print(f"  {title}")
    print(f"{'='*65}")


# ════════════════════════════════════════════════════════════════
section("问题1: 11,761 个无版本文档 — 根因分析")
# ════════════════════════════════════════════════════════════════

# 按来源拆分
cur.execute("""
    SELECT d.source_type, count(*) as total,
           sum(CASE WHEN dv.id IS NULL THEN 1 ELSE 0 END) as no_version,
           sum(CASE WHEN dv.id IS NOT NULL THEN 1 ELSE 0 END) as has_version
    FROM documents d
    LEFT JOIN document_versions dv ON d.id = dv.document_id
    GROUP BY d.source_type ORDER BY no_version DESC
""")
print("\n   来源                         总数   无版本   有版本   无版本率")
print("   " + "─"*62)
for r in cur.fetchall():
    rate = round(r[2] / r[1] * 100, 1) if r[1] > 0 else 0
    flag = "❌" if r[2] > 0 else "✅"
    print(f"   {flag} {r[0]:<28s} {r[1]:>6,} {r[2]:>7,} {r[3]:>7,} {rate:>6.1f}%")

# 看无版本文档的特征
cur.execute("""
    SELECT d.source_type, d.title, d.source_url, d.created_at
    FROM documents d
    LEFT JOIN document_versions dv ON d.id = dv.document_id
    WHERE dv.id IS NULL
    ORDER BY d.source_type, d.created_at
    LIMIT 15
""")
print("\n   无版本文档样本:")
for r in cur.fetchall():
    print(f"   [{r[0]}] {r[1][:50]}")
    print(f"      URL: {r[2][:80]}")
    print(f"      创建时间: {r[3]}")

# 检查是否是 discovery-only 文档（只做了发现没有采集内容）
cur.execute("""
    SELECT d.source_type, count(*)
    FROM documents d
    LEFT JOIN document_versions dv ON d.id = dv.document_id
    WHERE dv.id IS NULL
    GROUP BY d.source_type ORDER BY count(*) DESC
""")
print("\n   无版本文档按来源分布:")
for r in cur.fetchall():
    print(f"      {r[0]:<28s} {r[1]:>7,}")

# 检查 document_versions 的总量和对应关系
cur.execute("SELECT count(DISTINCT document_id) FROM document_versions")
unique_doc_ids = cur.fetchone()[0]
cur.execute("SELECT count(*) FROM document_versions")
total_versions = cur.fetchone()[0]
print(f"\n   document_versions 总数: {total_versions:,}")
print(f"   其中关联的唯一 document_id: {unique_doc_ids:,}")
print(f"   documents 总数: 15,690")
print(f"   差值 (无版本): {15690 - unique_doc_ids:,}")


# ════════════════════════════════════════════════════════════════
section("问题2: 3,929 条无 HTML 内容 — 分析")
# ════════════════════════════════════════════════════════════════

cur.execute("""
    SELECT d.source_type, count(*) as cnt,
           sum(CASE WHEN dv.content_html IS NULL OR length(dv.content_html) = 0 THEN 1 ELSE 0 END) as no_html,
           sum(CASE WHEN dv.content_text IS NULL OR length(dv.content_text) = 0 THEN 1 ELSE 0 END) as no_text
    FROM document_versions dv
    JOIN documents d ON d.id = dv.document_id
    GROUP BY d.source_type ORDER BY cnt DESC
""")
print("\n   来源                         版本数  无HTML  无Text")
print("   " + "─"*55)
for r in cur.fetchall():
    print(f"   {r[0]:<28s} {r[1]:>7,} {r[2]:>7,} {r[3]:>7,}")

# A2AJ 内容格式检查
cur.execute("""
    SELECT length(content_html), length(content_text),
           substring(content_html, 1, 100) as html_head,
           substring(content_text, 1, 100) as text_head
    FROM document_versions dv
    JOIN documents d ON d.id = dv.document_id
    WHERE d.source_type = 'a2aj_case_law'
    LIMIT 3
""")
print("\n   A2AJ 内容样本:")
for r in cur.fetchall():
    html_len = r[0] if r[0] else 0
    text_len = r[1] if r[1] else 0
    print(f"   HTML长度={html_len}, Text长度={text_len}")
    if r[2]:
        print(f"      HTML头: {r[2][:80]}")
    else:
        print(f"      HTML头: (NULL)")
    if r[3]:
        print(f"      Text头: {r[3][:80]}")


# ════════════════════════════════════════════════════════════════
section("问题3: 13条URL含空格 + 43条含逗号 — 详情")
# ════════════════════════════════════════════════════════════════

cur.execute("""
    SELECT source_type, source_url FROM documents
    WHERE source_url LIKE '%% %%'
    ORDER BY source_type
""")
rows = cur.fetchall()
print(f"\n   URL含空格 ({len(rows)} 条):")
for r in rows[:15]:
    print(f"   [{r[0]}] {r[1][:90]}")

cur.execute("""
    SELECT source_type, count(*) FROM documents
    WHERE source_url LIKE '%%,%%'
    GROUP BY source_type ORDER BY count(*) DESC
""")
print(f"\n   URL含逗号 (按来源):")
for r in cur.fetchall():
    print(f"   {r[0]:<28s} {r[1]:>5}")

cur.execute("""
    SELECT source_type, source_url FROM documents
    WHERE source_url LIKE '%%,%%'
    ORDER BY source_type LIMIT 10
""")
print(f"\n   URL含逗号样本:")
for r in cur.fetchall():
    print(f"   [{r[0]}] {r[1][:90]}")


# ════════════════════════════════════════════════════════════════
section("问题4: 10组同源重复标题 — 详情")
# ════════════════════════════════════════════════════════════════

cur.execute("""
    SELECT title, source_type, count(*) as cnt
    FROM documents
    GROUP BY title, source_type HAVING count(*) > 1
    ORDER BY cnt DESC
""")
print()
for r in cur.fetchall():
    print(f"   [{r[1]}] \"{r[0][:55]}\" × {r[2]}")
    # 显示每个重复的 URL
    cur.execute("""
        SELECT source_url, jurisdiction_code, citation
        FROM documents
        WHERE title = %s AND source_type = %s
        ORDER BY source_url
    """, (r[0], r[1]))
    for d in cur.fetchall():
        print(f"      {d[2] or '(no citation)':<20s} {d[0][:70]}")


# ════════════════════════════════════════════════════════════════
section("问题5: 3013条 DB URL 不在 Checkpoint — 分析")
# ════════════════════════════════════════════════════════════════

cp_path = None
for p in ["/app/checkpoint.db", "/app/data/checkpoint.db"]:
    if os.path.exists(p):
        cp_path = p
        break

if cp_path:
    sq = sqlite3.connect(cp_path)
    sqc = sq.cursor()
    sqc.execute("SELECT url FROM checkpoints")
    cp_urls = set(r[0] for r in sqc.fetchall())
    sq.close()

    cur.execute("SELECT source_url, source_type FROM documents")
    db_rows = cur.fetchall()
    db_urls = set(r[0] for r in db_rows)
    db_url_to_type = {r[0]: r[1] for r in db_rows}

    in_db_not_cp = db_urls - cp_urls

    # 按来源分类
    cats = defaultdict(int)
    for u in in_db_not_cp:
        cats[db_url_to_type.get(u, "unknown")] += 1

    print(f"\n   DB有 Checkpoint没有: {len(in_db_not_cp)} 条")
    print(f"   按来源:")
    for cat, cnt in sorted(cats.items(), key=lambda x: -x[1]):
        print(f"      {cat:<28s} {cnt:>6,}")

    # 这些文档是什么时候创建的?
    if in_db_not_cp:
        sample = list(in_db_not_cp)[:500]
        placeholders = ",".join(["%s"] * len(sample))
        cur.execute(f"""
            SELECT source_type,
                   min(created_at)::date as earliest,
                   max(created_at)::date as latest,
                   count(*)
            FROM documents
            WHERE source_url IN ({placeholders})
            GROUP BY source_type
        """, sample)
        print(f"\n   这些文档的创建时间:")
        for r in cur.fetchall():
            print(f"      {r[0]:<28s} {r[1]} → {r[2]}  ({r[3]} 条)")

    # 反向: 检查 checkpoint 中 URL 和 DB URL 的差异模式
    # 可能是 URL 格式不同导致匹配不上
    print(f"\n   URL格式差异检查:")
    # 找同一来源中 checkpoint 和 DB 的 URL 格式区别
    for src_type in ["canlii_legacy", "justice_canada_xml", "bc_laws_api"]:
        cur.execute("SELECT source_url FROM documents WHERE source_type = %s LIMIT 2", (src_type,))
        db_samples = [r[0] for r in cur.fetchall()]
        if db_samples:
            print(f"   [{src_type}]")
            for s in db_samples:
                in_cp = s in cp_urls
                print(f"      DB: {s[:75]} {'✅在CP' if in_cp else '❌不在CP'}")
else:
    print("   checkpoint.db 未找到")


# ════════════════════════════════════════════════════════════════
section("问题6: 版本数(3929) vs 文档数(15690) 大比例差异")
# ════════════════════════════════════════════════════════════════

cur.execute("""
    SELECT d.source_type,
           count(DISTINCT d.id) as doc_count,
           count(dv.id) as ver_count
    FROM documents d
    LEFT JOIN document_versions dv ON d.id = dv.document_id
    GROUP BY d.source_type
    ORDER BY doc_count DESC
""")
print(f"\n   {'来源':<28s} {'文档数':>7s} {'版本数':>7s} {'覆盖率':>7s}")
print("   " + "─"*52)
for r in cur.fetchall():
    rate = round(r[2] / r[1] * 100, 1) if r[1] > 0 else 0
    flag = "✅" if rate > 90 else ("⚠️" if rate > 0 else "❌")
    print(f"   {flag} {r[0]:<28s} {r[1]:>7,} {r[2]:>7,} {rate:>6.1f}%")

# 检查是否 a2aj 只存了部分版本
cur.execute("""
    SELECT count(DISTINCT document_id) FROM document_versions dv
    JOIN documents d ON d.id = dv.document_id
    WHERE d.source_type = 'a2aj_case_law'
""")
a2aj_with_ver = cur.fetchone()[0]
cur.execute("SELECT count(*) FROM documents WHERE source_type = 'a2aj_case_law'")
a2aj_total = cur.fetchone()[0]
print(f"\n   A2AJ: {a2aj_total:,} 文档, {a2aj_with_ver:,} 有版本 ({round(a2aj_with_ver/a2aj_total*100,1) if a2aj_total else 0}%)")

# 检查 canlii_legacy 状况
cur.execute("""
    SELECT count(DISTINCT document_id) FROM document_versions dv
    JOIN documents d ON d.id = dv.document_id
    WHERE d.source_type = 'canlii_legacy'
""")
cl_with_ver = cur.fetchone()[0]
cur.execute("SELECT count(*) FROM documents WHERE source_type = 'canlii_legacy'")
cl_total = cur.fetchone()[0]
print(f"   CanLII: {cl_total:,} 文档, {cl_with_ver:,} 有版本 ({round(cl_with_ver/cl_total*100,1) if cl_total else 0}%)")


# ════════════════════════════════════════════════════════════════
section("数据来源时间线")
# ════════════════════════════════════════════════════════════════

cur.execute("""
    SELECT source_type,
           min(created_at)::date as first_created,
           max(created_at)::date as last_created,
           count(*) as cnt
    FROM documents
    GROUP BY source_type
    ORDER BY min(created_at)
""")
print()
for r in cur.fetchall():
    print(f"   {r[0]:<28s} {r[1]} → {r[2]}  ({r[3]:>6,} 条)")


# ════════════════════════════════════════════════════════════════
section("建议")
# ════════════════════════════════════════════════════════════════

print("""
   基于以上分析，在升级 v5.5 之前的建议:

   1. [关键] 11,761 个无版本文档
      这些文档只有元数据（标题、URL），没有实际内容。
      大概率是 discovery 阶段注册了文档记录，但 fetch 内容没有完成。
      → 选项A: 保留，后续重新采集时会补上版本
      → 选项B: 清理掉这些空壳文档（重新发现+采集更干净）

   2. [低风险] URL 编码问题
      v5.5 适配器已自动处理，升级后重新采集会覆盖。
      已入库的 56 条（13空格+43逗号）可在升级后用修复脚本处理。

   3. [低风险] Checkpoint 不一致
      3013 条 DB URL 不在 checkpoint 中意味着:
      重新采集时这些 URL 不会被跳过（会重新 fetch，效率略低但不丢数据）。
      升级后运行一次全量采集即可自动对齐。
""")

cur.close()
conn.close()
