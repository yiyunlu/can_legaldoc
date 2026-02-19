#!/usr/bin/env python3
"""
v5.5 升级前修复脚本 — 处理生产环境发现的问题
用法: docker exec canlii-platform python /app/scripts/fix_before_upgrade.py [--dry-run]

修复项:
  1. 清理无版本空壳文档（仅 discovery 未 fetch 的文档）
  2. 修复 URL 编码（空格→%20, 逗号→%2C）
  3. 同步 Checkpoint 与 DB
  4. 清理测试数据

加 --dry-run 参数只看报告不执行修改。
"""
import os
import sys
import sqlite3
from urllib.parse import quote, urlsplit, urlunsplit, unquote

DRY_RUN = "--dry-run" in sys.argv

DB_URL = os.environ.get("DATABASE_URL", "")
if not DB_URL:
    pg_pass = os.environ.get("POSTGRES_PASSWORD", "canlii_secure_pwd_2024")
    DB_URL = f"postgresql://canlii:{pg_pass}@postgres:5432/canlii"

import psycopg2
conn = psycopg2.connect(DB_URL)
conn.autocommit = False
cur = conn.cursor()

mode = "🔍 DRY-RUN 模式（不修改数据）" if DRY_RUN else "🔧 执行模式（将修改数据）"
print("=" * 60)
print(f"  v5.5 升级前修复脚本")
print(f"  {mode}")
print("=" * 60)


def normalize_url(url):
    """Percent-encode spaces, commas, etc. Decode first to avoid double-encoding."""
    parts = urlsplit(url)
    decoded_path = unquote(parts.path)
    # safe 中不包含空格和逗号，它们会被编码
    clean_path = quote(decoded_path, safe="/:@!$&'()*+;=-._~")
    return urlunsplit((parts.scheme, parts.netloc, clean_path, parts.query, parts.fragment))


# ═══════════════════════════════════════════════════════════
print("\n─── 修复1: 清理无版本空壳文档 ───")
# ═══════════════════════════════════════════════════════════

cur.execute("""
    SELECT d.source_type, count(*) as cnt
    FROM documents d
    LEFT JOIN document_versions dv ON d.id = dv.document_id
    WHERE dv.id IS NULL
    GROUP BY d.source_type ORDER BY cnt DESC
""")
orphan_stats = cur.fetchall()
total_orphans = sum(r[1] for r in orphan_stats)

print(f"\n   发现 {total_orphans:,} 个无版本文档:")
for r in orphan_stats:
    print(f"      {r[0]:<28s} {r[1]:>7,}")

if total_orphans > 0:
    print(f"\n   这些文档只有元数据（标题、URL），没有实际内容。")
    print(f"   原因: discovery 注册了记录，但 fetch 内容未完成。")
    print(f"   处理: 删除空壳，升级后重新 discovery+fetch 会完整写入。")

    if not DRY_RUN:
        # 删除无版本的文档记录
        cur.execute("""
            DELETE FROM documents
            WHERE id IN (
                SELECT d.id FROM documents d
                LEFT JOIN document_versions dv ON d.id = dv.document_id
                WHERE dv.id IS NULL
            )
        """)
        deleted = cur.rowcount
        print(f"\n   ✅ 已删除 {deleted:,} 个空壳文档")
    else:
        print(f"\n   [DRY-RUN] 将删除 {total_orphans:,} 个空壳文档")


# ═══════════════════════════════════════════════════════════
print("\n─── 修复2: URL 编码规范化 ───")
# ═══════════════════════════════════════════════════════════

# 找出需要修复的 URL
cur.execute("""
    SELECT id, source_url FROM documents
    WHERE source_url LIKE '%% %%' OR source_url LIKE '%%,%%'
""")
bad_urls = cur.fetchall()
print(f"\n   需要修复的 URL: {len(bad_urls)} 条")

url_fixes = []
for doc_id, old_url in bad_urls:
    new_url = normalize_url(old_url)
    if old_url != new_url:
        url_fixes.append((doc_id, old_url, new_url))

if url_fixes:
    for doc_id, old, new in url_fixes[:10]:
        print(f"      旧: {old[:75]}")
        print(f"      新: {new[:75]}")
        print()
    if len(url_fixes) > 10:
        print(f"      ... 还有 {len(url_fixes) - 10} 条")

    if not DRY_RUN:
        for doc_id, old_url, new_url in url_fixes:
            # 检查新 URL 是否已存在（避免 UNIQUE 冲突）
            cur.execute("SELECT count(*) FROM documents WHERE source_url = %s AND id != %s",
                        (new_url, doc_id))
            if cur.fetchone()[0] > 0:
                print(f"   ⚠️  跳过 (新URL已存在): {new_url[:70]}")
                continue
            cur.execute("UPDATE documents SET source_url = %s WHERE id = %s",
                        (new_url, doc_id))
        print(f"\n   ✅ 已修复 {len(url_fixes)} 条 URL")
    else:
        print(f"   [DRY-RUN] 将修复 {len(url_fixes)} 条 URL")
else:
    print("   ✅ 无需修复")


# ═══════════════════════════════════════════════════════════
print("\n─── 修复3: 同步 Checkpoint ───")
# ═══════════════════════════════════════════════════════════

cp_path = None
for p in ["/app/checkpoint.db", "/app/data/checkpoint.db"]:
    if os.path.exists(p):
        cp_path = p
        break

if cp_path:
    sq = sqlite3.connect(cp_path)
    sqc = sq.cursor()

    # 3a. 修复 checkpoint 中的 URL 编码
    sqc.execute("SELECT url FROM checkpoints WHERE url LIKE '% %' OR url LIKE '%,%'")
    cp_bad = sqc.fetchall()
    cp_fix_count = 0
    for (old_url,) in cp_bad:
        new_url = normalize_url(old_url)
        if old_url != new_url:
            if not DRY_RUN:
                sqc.execute("UPDATE checkpoints SET url = ? WHERE url = ?", (new_url, old_url))
            cp_fix_count += 1

    print(f"   Checkpoint URL 修复: {cp_fix_count} 条")

    # 3b. 把 DB 中有但 checkpoint 没有的 URL 补进 checkpoint
    sqc.execute("SELECT url FROM checkpoints")
    cp_urls = set(r[0] for r in sqc.fetchall())

    cur.execute("SELECT source_url FROM documents")
    db_urls = set(r[0] for r in cur.fetchall())

    missing_in_cp = db_urls - cp_urls
    print(f"   DB有 Checkpoint没有: {len(missing_in_cp)} 条")

    if missing_in_cp and not DRY_RUN:
        from datetime import datetime
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        for url in missing_in_cp:
            sqc.execute("INSERT OR IGNORE INTO checkpoints (url, scraped_at) VALUES (?, ?)",
                        (url, now))
        print(f"   ✅ 已补入 {len(missing_in_cp)} 条到 Checkpoint")
    elif missing_in_cp:
        print(f"   [DRY-RUN] 将补入 {len(missing_in_cp)} 条到 Checkpoint")

    # 3c. 清理测试 URL
    sqc.execute("SELECT url FROM checkpoints WHERE url LIKE '%example.com%' OR url LIKE '%test.com%'")
    test_urls = sqc.fetchall()
    if test_urls:
        print(f"   测试 URL: {len(test_urls)} 条")
        if not DRY_RUN:
            sqc.execute("DELETE FROM checkpoints WHERE url LIKE '%example.com%' OR url LIKE '%test.com%'")
            print(f"   ✅ 已清理 {len(test_urls)} 条测试数据")
        else:
            print(f"   [DRY-RUN] 将清理 {len(test_urls)} 条测试数据")

    if not DRY_RUN:
        sq.commit()
    sq.close()
else:
    print("   ⚠️  checkpoint.db 未找到，跳过")


# ═══════════════════════════════════════════════════════════
print("\n─── 修复4: 数据一致性最终检查 ───")
# ═══════════════════════════════════════════════════════════

if not DRY_RUN:
    conn.commit()

# 重新统计
cur.execute("SELECT count(*) FROM documents")
final_docs = cur.fetchone()[0]
cur.execute("SELECT count(*) FROM document_versions")
final_vers = cur.fetchone()[0]
cur.execute("""
    SELECT count(*) FROM documents d
    LEFT JOIN document_versions dv ON d.id = dv.document_id
    WHERE dv.id IS NULL
""")
final_orphans = cur.fetchone()[0]
cur.execute("SELECT count(*) FROM documents WHERE source_url LIKE '%% %%' OR source_url LIKE '%%,%%'")
final_bad_urls = cur.fetchone()[0]

print(f"\n   修复后状态:")
print(f"      文档总数:     {final_docs:>8,}")
print(f"      版本总数:     {final_vers:>8,}")
print(f"      无版本文档:   {final_orphans:>8,}  {'✅' if final_orphans == 0 else '❌'}")
print(f"      问题URL:      {final_bad_urls:>8,}  {'✅' if final_bad_urls == 0 else '❌'}")

# 按来源最终分布
cur.execute("""
    SELECT source_type, count(*) FROM documents GROUP BY source_type ORDER BY count(*) DESC
""")
print(f"\n   最终来源分布:")
for r in cur.fetchall():
    print(f"      {r[0]:<28s} {r[1]:>7,}")


# ═══════════════════════════════════════════════════════════
print()
print("=" * 60)
if DRY_RUN:
    print("  🔍 DRY-RUN 完成 — 未修改任何数据")
    print("  去掉 --dry-run 参数以执行修复:")
    print("  docker exec canlii-platform python /app/scripts/fix_before_upgrade.py")
else:
    print("  ✅ 修复完成")
    print()
    print("  下一步: 升级到 v5.5")
    print("  cd /opt/canlii && git pull && docker compose up -d --build")
print("=" * 60)

cur.close()
conn.close()
