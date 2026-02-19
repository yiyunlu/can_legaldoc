#!/usr/bin/env python3
"""
v5.5 升级后验证脚本 — 确认升级成功
用法: docker exec canlii-platform python scripts/post_upgrade_check.py

验证项:
  1. API 健康检查 (version == 5.5)
  2. 适配器注册 (10 个)
  3. 数据库表结构 & 迁移状态
  4. 数据完整性 (对比升级前快照)
  5. 新省份适配器 discovery 快速测试 (dry-run)
  6. Playwright 可用性 (Ontario 需要)
"""
import os
import sys
import json
import time
from datetime import datetime

# ── DB 连接 ──
DB_URL = os.environ.get("DATABASE_URL", "")
if not DB_URL:
    pg_pass = os.environ.get("POSTGRES_PASSWORD", "canlii_secure_pwd_2024")
    DB_URL = f"postgresql://canlii:{pg_pass}@postgres:5432/canlii"

try:
    import psycopg2
except ImportError:
    print("❌ psycopg2 未安装")
    sys.exit(1)


def section(title):
    print(f"\n{'═'*60}")
    print(f"  {title}")
    print(f"{'═'*60}")


def main():
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()

    print("=" * 60)
    print("  v5.5 升级后验证报告")
    print(f"  时间: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print("=" * 60)

    passed = 0
    failed = 0
    warnings = 0

    def check_pass(msg):
        nonlocal passed
        passed += 1
        print(f"   ✅ {msg}")

    def check_fail(msg):
        nonlocal failed
        failed += 1
        print(f"   ❌ {msg}")

    def check_warn(msg):
        nonlocal warnings
        warnings += 1
        print(f"   ⚠️  {msg}")

    # ════════════════════════════════════════════════════════
    section("1. API 版本验证")
    # ════════════════════════════════════════════════════════
    version_found = None
    for p in ["/app/api/main.py", "api/main.py"]:
        if os.path.exists(p):
            with open(p) as f:
                for line in f:
                    if '"version"' in line:
                        # Extract version string like "5.5"
                        import re
                        m = re.search(r'"version"\s*:\s*"([^"]+)"', line)
                        if m:
                            version_found = m.group(1)
                            break
            break

    if version_found:
        if version_found.startswith("5.5"):
            check_pass(f"版本: {version_found}")
        else:
            check_fail(f"版本应为 5.5.x，实际: {version_found}")
    else:
        check_warn("无法读取版本号")

    # HTTP 健康检查
    try:
        import urllib.request
        resp = urllib.request.urlopen("http://localhost:8000/health", timeout=5)
        health = json.loads(resp.read())
        api_ver = health.get("version", "?")
        api_status = health.get("status", "?")
        if api_status == "ok":
            check_pass(f"API 健康: status={api_status}, version={api_ver}")
        else:
            check_fail(f"API 异常: {health}")
    except Exception as e:
        check_warn(f"API 健康检查失败 (可能容器内无法访问自身): {e}")

    # ════════════════════════════════════════════════════════
    section("2. 适配器注册验证")
    # ════════════════════════════════════════════════════════
    expected_adapters = [
        "justice_canada_xml",
        "bc_laws_api",
        "alberta_kings_printer",
        "a2aj_case_law",
        "canlii_legacy",
        "manitoba_laws",
        "newfoundland_laws",
        "nova_scotia_laws",
        "new_brunswick_laws",
        "ontario_elaws",
    ]

    try:
        from scraper.adapters import _ADAPTER_REGISTRY, _ensure_adapters_loaded
        _ensure_adapters_loaded()

        registered = sorted(_ADAPTER_REGISTRY.keys())
        print(f"\n   已注册适配器 ({len(registered)}):")
        for name in registered:
            is_new = name in ["manitoba_laws", "newfoundland_laws", "nova_scotia_laws",
                              "new_brunswick_laws", "ontario_elaws"]
            marker = " 🆕" if is_new else ""
            print(f"      ✓ {name}{marker}")

        missing = [a for a in expected_adapters if a not in registered]
        if missing:
            check_fail(f"缺少适配器: {missing}")
        elif len(registered) >= 10:
            check_pass(f"全部 {len(registered)} 个适配器已注册")
        else:
            check_warn(f"只有 {len(registered)} 个适配器（预期 ≥10）")

    except Exception as e:
        check_fail(f"适配器加载失败: {e}")

    # ════════════════════════════════════════════════════════
    section("3. 数据库结构验证")
    # ════════════════════════════════════════════════════════
    required_tables = [
        "documents", "document_versions", "scrape_jobs",
        "jurisdictions", "scrape_targets", "scheduler_config",
    ]
    cur.execute("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public' ORDER BY table_name
    """)
    existing_tables = [r[0] for r in cur.fetchall()]

    missing_tables = [t for t in required_tables if t not in existing_tables]
    if missing_tables:
        check_fail(f"缺少表: {missing_tables}")
    else:
        check_pass(f"核心表完整 ({len(required_tables)} 张)")

    # 检查关键索引
    cur.execute("""
        SELECT indexname FROM pg_indexes WHERE schemaname = 'public'
    """)
    indexes = [r[0] for r in cur.fetchall()]
    key_indexes = ["idx_documents_source_url", "idx_documents_source_type",
                   "idx_document_versions_document_id"]
    missing_idx = []
    for idx in key_indexes:
        # 模糊匹配（索引名可能略有不同）
        found = any(idx in i or i.startswith(idx.replace("idx_", "")) for i in indexes)
        if not found:
            # 也检查完全匹配
            found = idx in indexes
        if not found:
            missing_idx.append(idx)

    if missing_idx:
        check_warn(f"缺少索引: {missing_idx}")
    else:
        check_pass(f"关键索引存在")

    # ════════════════════════════════════════════════════════
    section("4. 数据完整性 (升级前后对比)")
    # ════════════════════════════════════════════════════════

    # 当前统计
    cur.execute("SELECT count(*) FROM documents")
    curr_docs = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM document_versions")
    curr_vers = cur.fetchone()[0]

    cur.execute("""
        SELECT source_type, count(*) FROM documents
        GROUP BY source_type ORDER BY count(*) DESC
    """)
    curr_by_source = dict(cur.fetchall())

    print(f"\n   当前文档: {curr_docs:,}  版本: {curr_vers:,}")
    print(f"\n   按来源:")
    for src, cnt in sorted(curr_by_source.items(), key=lambda x: -x[1]):
        print(f"      {src:<30s} {cnt:>7,}")

    # 加载升级前快照对比
    snapshot_path = "/app/data/pre_upgrade_snapshot.json"
    if os.path.exists(snapshot_path):
        with open(snapshot_path) as f:
            snapshot = json.load(f)

        prev_docs = snapshot.get("total_documents", 0)
        prev_vers = snapshot.get("total_versions", 0)
        prev_by_source = snapshot.get("by_source", {})

        print(f"\n   升级前快照 ({snapshot.get('timestamp', '?')[:19]}):")
        print(f"      文档: {prev_docs:,}  →  {curr_docs:,}  (差异: {curr_docs - prev_docs:+,})")
        print(f"      版本: {prev_vers:,}  →  {curr_vers:,}  (差异: {curr_vers - prev_vers:+,})")

        # 数据不应变少
        if curr_docs >= prev_docs:
            check_pass(f"文档数未减少 ({prev_docs:,} → {curr_docs:,})")
        else:
            check_fail(f"文档数减少了! ({prev_docs:,} → {curr_docs:,}, -{prev_docs - curr_docs:,})")

        if curr_vers >= prev_vers:
            check_pass(f"版本数未减少 ({prev_vers:,} → {curr_vers:,})")
        else:
            check_fail(f"版本数减少了! ({prev_vers:,} → {curr_vers:,}, -{prev_vers - curr_vers:,})")

        # 检查每个旧数据源的数量是否持平
        for src, prev_cnt in prev_by_source.items():
            curr_cnt = curr_by_source.get(src, 0)
            if curr_cnt < prev_cnt:
                check_warn(f"{src}: 数量减少 {prev_cnt} → {curr_cnt}")
    else:
        check_warn("升级前快照不存在 — 无法对比")
        print(f"      (提示: 升级前应先运行 pre_upgrade_check.py 生成快照)")

    # 通用完整性
    cur.execute("""
        SELECT count(*) FROM documents d
        LEFT JOIN document_versions dv ON d.id = dv.document_id
        WHERE dv.id IS NULL
    """)
    orphan_docs = cur.fetchone()[0]
    print(f"\n   无版本文档: {orphan_docs:,}")
    if orphan_docs == 0:
        check_pass("无空壳文档")
    elif orphan_docs < 100:
        check_warn(f"{orphan_docs} 个空壳文档 (可能是新 discovery 的)")
    else:
        check_warn(f"{orphan_docs:,} 个空壳文档 (如运行了 fix_before_upgrade.py 应为 0)")

    # ════════════════════════════════════════════════════════
    section("5. config.json 数据源配置")
    # ════════════════════════════════════════════════════════
    config_path = None
    for p in ["/app/config.json", "config.json"]:
        if os.path.exists(p):
            config_path = p
            break

    if config_path:
        with open(config_path) as f:
            cfg = json.load(f)
        sources = cfg.get("sources", [])
        print(f"\n   config.json 数据源 ({len(sources)}):")
        expected_sources = {
            "justice_canada_xml", "bc_laws_api", "alberta_kings_printer",
            "a2aj_case_law", "manitoba_laws", "newfoundland_laws",
            "nova_scotia_laws", "new_brunswick_laws", "ontario_elaws",
        }
        found_sources = set()
        for s in sources:
            st = s.get("source_type", "?")
            found_sources.add(st)
            is_new = st in ["manitoba_laws", "newfoundland_laws", "nova_scotia_laws",
                            "new_brunswick_laws", "ontario_elaws"]
            enabled = "✓" if s.get("enabled") else "✗"
            marker = " 🆕" if is_new else ""
            print(f"      [{enabled}] {st:<30s} {s.get('jurisdiction', '?'):<4s}{marker}")

        missing_src = expected_sources - found_sources
        if missing_src:
            check_fail(f"config.json 缺少: {missing_src}")
        else:
            check_pass(f"config.json 包含全部 {len(expected_sources)} 个数据源")
    else:
        check_fail("config.json 未找到")

    # ════════════════════════════════════════════════════════
    section("6. 新适配器 Discovery 快速测试")
    # ════════════════════════════════════════════════════════
    new_adapters = {
        "manitoba_laws": "Manitoba",
        "newfoundland_laws": "Newfoundland",
        "nova_scotia_laws": "Nova Scotia",
        "new_brunswick_laws": "New Brunswick",
        # Ontario 需要 Playwright，单独测试
    }

    try:
        from scraper.adapters import get_adapter

        for source_type, name in new_adapters.items():
            try:
                adapter = get_adapter(source_type)
                start_t = time.time()
                items = []
                for item in adapter.discover():
                    items.append(item)
                    if len(items) >= 3:
                        break
                elapsed = time.time() - start_t
                if items:
                    first_title = items[0].get("title", "?")[:50]
                    check_pass(f"{name}: 发现 {len(items)} 条 ({elapsed:.1f}s) 「{first_title}」")
                else:
                    check_fail(f"{name}: discover 返回 0 条")
            except Exception as e:
                check_fail(f"{name} discovery 失败: {e}")

    except ImportError as e:
        check_fail(f"无法导入适配器模块: {e}")

    # ════════════════════════════════════════════════════════
    section("7. Playwright 可用性 (Ontario)")
    # ════════════════════════════════════════════════════════
    try:
        from playwright.sync_api import sync_playwright
        p = sync_playwright().start()
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto("https://www.ontario.ca/laws", timeout=30000)
        title = page.title()
        browser.close()
        p.stop()
        check_pass(f"Playwright + Chromium 正常 (页面标题: {title[:40]})")
    except ImportError:
        check_warn("Playwright 未安装 (Ontario 适配器将不可用)")
        print("      提示: 构建时设置 INSTALL_PLAYWRIGHT=true")
    except Exception as e:
        check_warn(f"Playwright 测试失败: {e}")
        print("      Ontario 适配器可能不可用，其他适配器不受影响")

    # ════════════════════════════════════════════════════════
    section("8. 数据库连接池 & 环境")
    # ════════════════════════════════════════════════════════
    cur.execute("SELECT version()")
    pg_ver = cur.fetchone()[0].split(",")[0]
    print(f"   PostgreSQL: {pg_ver}")
    print(f"   Python: {sys.version.split()[0]}")

    # DatabaseClient 可用性
    try:
        from scraper.db_client import DatabaseClient
        db = DatabaseClient()
        check_pass("DatabaseClient 连接池正常")
    except Exception as e:
        check_fail(f"DatabaseClient 初始化失败: {e}")

    # ════════════════════════════════════════════════════════
    # Summary
    # ════════════════════════════════════════════════════════
    print()
    print("=" * 60)
    total = passed + failed + warnings
    print(f"  检查结果: {total} 项  ✅ {passed}  ❌ {failed}  ⚠️ {warnings}")
    print()
    if failed == 0:
        print("  🎉 v5.5 升级成功！")
        print()
        print("  下一步 — 采集新省份数据:")
        print("  docker exec canlii-platform python main_multi.py --source-type manitoba_laws --limit 10")
        print("  docker exec canlii-platform python main_multi.py --source-type newfoundland_laws --limit 10")
        print("  docker exec canlii-platform python main_multi.py --source-type nova_scotia_laws --limit 10")
        print("  docker exec canlii-platform python main_multi.py --source-type new_brunswick_laws --limit 10")
        print("  docker exec canlii-platform python main_multi.py --source-type ontario_elaws --limit 10")
    else:
        print(f"  ⚠️  有 {failed} 个检查未通过，请检查上方输出")
    print("=" * 60)

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
