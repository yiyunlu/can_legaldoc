#!/usr/bin/env python3
"""
v5.5 数据库健康诊断脚本
用法: docker exec canlii-platform python scripts/db_health_check.py
"""
import sys
import os
import sqlite3
from collections import defaultdict

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scraper.db_client import DatabaseClient


def main():
    db = DatabaseClient()
    conn = db.pool.getconn()
    cur = conn.cursor()

    print("=" * 70)
    print("  v5.5 数据库健康诊断报告")
    print("=" * 70)

    # ── 1. 基本统计 ──
    print("\n📊 1. 基本统计")
    cur.execute("SELECT count(*) FROM documents")
    total_docs = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM document_versions")
    total_vers = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM scrape_jobs")
    total_jobs = cur.fetchone()[0]
    print(f"   文档: {total_docs:,}  版本: {total_vers:,}  任务: {total_jobs:,}")

    # ── 2. 按来源分布 ──
    print("\n📂 2. 按来源分布")
    cur.execute("""
        SELECT source_type, count(*) as cnt,
               min(length(dv.content_text)) as min_len,
               avg(length(dv.content_text))::int as avg_len,
               max(length(dv.content_text)) as max_len
        FROM documents d
        LEFT JOIN document_versions dv ON d.id = dv.document_id AND dv.is_latest = true
        GROUP BY source_type ORDER BY cnt DESC
    """)
    rows = cur.fetchall()
    print(f"   {'来源':<30s} {'数量':>6s} {'最短':>8s} {'平均':>8s} {'最长':>10s}")
    print(f"   {'-'*30} {'-'*6} {'-'*8} {'-'*8} {'-'*10}")
    for r in rows:
        min_l = r[2] if r[2] is not None else 0
        avg_l = r[3] if r[3] is not None else 0
        max_l = r[4] if r[4] is not None else 0
        print(f"   {r[0]:<30s} {r[1]:>6,} {min_l:>8,} {avg_l:>8,} {max_l:>10,}")

    # ── 3. 按辖区分布 ──
    print("\n🗺️  3. 按辖区分布")
    cur.execute("SELECT jurisdiction_code, count(*) FROM documents GROUP BY jurisdiction_code ORDER BY count(*) DESC")
    for r in cur.fetchall():
        print(f"   {r[0]:<10s} {r[1]:>6,}")

    # ── 4. 完整性检查 ──
    print("\n✅ 4. 完整性检查")
    issues = []

    checks = [
        ("NULL/空标题", "title IS NULL OR title = ''"),
        ("NULL/空URL", "source_url IS NULL OR source_url = ''"),
        ("NULL引用号", "citation IS NULL"),
        ("NULL辖区", "jurisdiction_code IS NULL"),
        ("NULL来源类型", "source_type IS NULL"),
    ]
    for label, cond in checks:
        cur.execute(f"SELECT count(*) FROM documents WHERE {cond}")
        cnt = cur.fetchone()[0]
        status = "✅" if cnt == 0 else "❌"
        if cnt > 0:
            issues.append(f"{label}: {cnt}")
        print(f"   {status} {label}: {cnt}")

    # Duplicate URLs
    cur.execute("SELECT source_url, count(*) FROM documents GROUP BY source_url HAVING count(*) > 1")
    dupes = cur.fetchall()
    status = "✅" if len(dupes) == 0 else "❌"
    if dupes:
        issues.append(f"重复URL: {len(dupes)}")
    print(f"   {status} 重复URL: {len(dupes)}")
    for d in dupes[:5]:
        print(f"      {d[0][:80]} (x{d[1]})")

    # Orphan versions
    cur.execute("SELECT count(*) FROM document_versions dv LEFT JOIN documents d ON d.id = dv.document_id WHERE d.id IS NULL")
    orphans = cur.fetchone()[0]
    status = "✅" if orphans == 0 else "❌"
    if orphans > 0:
        issues.append(f"孤儿版本: {orphans}")
    print(f"   {status} 孤儿版本: {orphans}")

    # Docs without versions
    cur.execute("SELECT count(*) FROM documents d LEFT JOIN document_versions dv ON d.id = dv.document_id WHERE dv.id IS NULL")
    no_ver = cur.fetchone()[0]
    status = "✅" if no_ver == 0 else "❌"
    if no_ver > 0:
        issues.append(f"无版本文档: {no_ver}")
    print(f"   {status} 无版本文档: {no_ver}")

    # ── 5. URL质量 ──
    print("\n🔗 5. URL质量")
    url_checks = [
        ("含原始空格", "source_url LIKE '%% %%'"),
        ("含原始逗号", "source_url LIKE '%%,%%'"),
        ("非HTTP开头", "source_url NOT LIKE 'http%%'"),
    ]
    for label, cond in url_checks:
        cur.execute(f"SELECT count(*) FROM documents WHERE {cond}")
        cnt = cur.fetchone()[0]
        status = "✅" if cnt == 0 else "⚠️"
        if cnt > 0:
            issues.append(f"URL{label}: {cnt}")
        print(f"   {status} {label}: {cnt}")
        if cnt > 0 and cnt <= 10:
            cur.execute(f"SELECT source_url FROM documents WHERE {cond} LIMIT 5")
            for r in cur.fetchall():
                print(f"      {r[0][:90]}")

    # ── 6. 标题质量 ──
    print("\n📝 6. 标题质量")
    cur.execute("""
        SELECT title, source_type FROM documents
        WHERE lower(trim(title)) IN ('general', 'forms', 'fees', 'exemptions',
            'exemption', 'administration', 'procedures', 'designation')
    """)
    generics = cur.fetchall()
    status = "✅" if len(generics) == 0 else "⚠️"
    if generics:
        issues.append(f"未限定通用标题: {len(generics)}")
    print(f"   {status} 未限定通用标题: {len(generics)}")
    for g in generics[:10]:
        print(f"      [{g[1]}] {g[0]}")

    # Duplicate titles within same source
    cur.execute("""
        SELECT title, source_type, count(*) FROM documents
        GROUP BY title, source_type HAVING count(*) > 1
        ORDER BY count(*) DESC LIMIT 10
    """)
    title_dupes = cur.fetchall()
    if title_dupes:
        print(f"   ⚠️  同源重复标题: {len(title_dupes)}")
        for t in title_dupes:
            print(f"      [{t[1]}] {t[0][:50]} (x{t[2]})")

    # ── 7. 内容质量 ──
    print("\n📄 7. 内容质量")
    cur.execute("""
        SELECT count(*) FROM document_versions
        WHERE content_html IS NULL OR length(content_html) = 0
    """)
    no_html = cur.fetchone()[0]
    cur.execute("""
        SELECT count(*) FROM document_versions
        WHERE content_text IS NULL OR length(content_text) = 0
    """)
    no_text = cur.fetchone()[0]
    print(f"   {'✅' if no_html == 0 else '❌'} 无HTML内容: {no_html}")
    print(f"   {'✅' if no_text == 0 else '❌'} 无Text内容: {no_text}")

    # Very short content
    cur.execute("""
        SELECT count(*) FROM document_versions WHERE length(content_text) < 100
    """)
    tiny = cur.fetchone()[0]
    if tiny > 0:
        print(f"   ⚠️  极短内容(<100字符): {tiny}")
        cur.execute("""
            SELECT d.source_type, d.title, length(dv.content_text)
            FROM documents d JOIN document_versions dv ON d.id = dv.document_id
            WHERE length(dv.content_text) < 100
            ORDER BY length(dv.content_text) LIMIT 5
        """)
        for r in cur.fetchall():
            print(f"      [{r[0]}] {r[1][:50]} ({r[2]} chars)")
    else:
        print(f"   ✅ 极短内容(<100字符): 0")

    # Content hash duplicates
    cur.execute("""
        SELECT content_hash, count(*) FROM document_versions
        GROUP BY content_hash HAVING count(*) > 1
    """)
    hash_dupes = cur.fetchall()
    if hash_dupes:
        print(f"   ⚠️  相同内容hash: {len(hash_dupes)}组")
        for h in hash_dupes[:5]:
            cur.execute("""
                SELECT d.title, d.source_type FROM document_versions dv
                JOIN documents d ON d.id = dv.document_id
                WHERE dv.content_hash = %s LIMIT 3
            """, (h[0],))
            for doc in cur.fetchall():
                print(f"      [{doc[1]}] {doc[0][:50]}")
    else:
        print(f"   ✅ 内容hash唯一: 无重复")

    # ── 8. 任务历史 ──
    print("\n🔄 8. 最近采集任务")
    cur.execute("""
        SELECT id, status, started_at, finished_at, items_scraped, items_failed, logs
        FROM scrape_jobs ORDER BY started_at DESC LIMIT 5
    """)
    jobs = cur.fetchall()
    if jobs:
        for j in jobs:
            duration = ""
            if j[3] and j[2]:
                dur = (j[3] - j[2]).total_seconds()
                duration = f" ({dur:.0f}s)"
            log_preview = (j[6] or "")[:80]
            print(f"   {str(j[0])[:8]}.. {j[1]:10s} {str(j[2])[:19]} scraped={j[4]} failed={j[5]}{duration}")
            if log_preview:
                print(f"      {log_preview}")
    else:
        print("   无任务记录")

    # ── 9. Checkpoint 一致性 ──
    print("\n🔖 9. Checkpoint 一致性")
    cp_path = None
    for p in ["/app/checkpoint.db", "/app/data/checkpoint.db"]:
        if os.path.exists(p):
            cp_path = p
            break

    if cp_path:
        sq = sqlite3.connect(cp_path)
        sqc = sq.cursor()
        sqc.execute("SELECT count(*) FROM checkpoints")
        cp_total = sqc.fetchone()[0]
        print(f"   Checkpoint条目: {cp_total:,}")

        sqc.execute("SELECT min(scraped_at), max(scraped_at) FROM checkpoints")
        dates = sqc.fetchone()
        print(f"   时间范围: {dates[0]} → {dates[1]}")

        # Checkpoint URLs by domain
        sqc.execute("SELECT url FROM checkpoints")
        cp_urls = set(r[0] for r in sqc.fetchall())
        sq.close()

        cur.execute("SELECT source_url FROM documents")
        db_urls = set(r[0] for r in cur.fetchall())

        in_cp_not_db = cp_urls - db_urls
        in_db_not_cp = db_urls - cp_urls

        status1 = "✅" if len(in_db_not_cp) == 0 else "⚠️"
        status2 = "ℹ️" if len(in_cp_not_db) > 0 else "✅"
        print(f"   {status1} DB有Checkpoint没有: {len(in_db_not_cp)}")
        if in_db_not_cp:
            issues.append(f"DB有{len(in_db_not_cp)}条URL不在Checkpoint中（再次采集可能重复）")
            for u in sorted(in_db_not_cp)[:5]:
                print(f"      {u[:90]}")
        print(f"   {status2} Checkpoint有DB没有: {len(in_cp_not_db)}")
        if in_cp_not_db:
            # Categorize
            cats = defaultdict(int)
            for u in in_cp_not_db:
                if "canlii.org" in u:
                    cats["canlii_legacy"] += 1
                elif "test" in u or "example" in u:
                    cats["test_data"] += 1
                else:
                    cats["other"] += 1
            for cat, cnt in sorted(cats.items(), key=lambda x: -x[1]):
                print(f"      {cat}: {cnt}")
    else:
        print("   ⚠️  checkpoint.db 未找到")

    # ── 10. 数据库大小 ──
    print("\n💾 10. 数据库大小")
    cur.execute("""
        SELECT pg_size_pretty(pg_database_size(current_database())),
               pg_database_size(current_database())
    """)
    r = cur.fetchone()
    print(f"   总大小: {r[0]}")

    cur.execute("""
        SELECT relname, pg_size_pretty(pg_total_relation_size(relid))
        FROM pg_catalog.pg_statio_user_tables
        ORDER BY pg_total_relation_size(relid) DESC LIMIT 5
    """)
    for r in cur.fetchall():
        print(f"   {r[0]:<30s} {r[1]}")

    # ── 11. 适配器注册 ──
    print("\n🔌 11. 适配器注册")
    try:
        from scraper.adapters import _ADAPTER_REGISTRY, _ensure_adapters_loaded
        _ensure_adapters_loaded()
        for name in sorted(_ADAPTER_REGISTRY.keys()):
            print(f"   ✓ {name}")
        print(f"   共 {len(_ADAPTER_REGISTRY)} 个适配器")
    except Exception as e:
        print(f"   ❌ 加载失败: {e}")

    # ── Summary ──
    print("\n" + "=" * 70)
    if issues:
        print(f"  ⚠️  发现 {len(issues)} 个问题:")
        for i, issue in enumerate(issues, 1):
            print(f"     {i}. {issue}")
    else:
        print("  ✅ 所有检查通过 — 数据库健康")
    print("=" * 70)

    cur.close()
    db.pool.putconn(conn)


if __name__ == "__main__":
    main()
