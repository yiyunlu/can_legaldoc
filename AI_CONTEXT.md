# CanLII Legal Data Platform - AI Developer Context (v3.1)

> **文档目的**: 为后续 AI 开发者提供项目的最新核心上下文。记录了 v1.0 与 v2.0 的深度融合结果、全新的 SQLite 断点管理架构以及针对海量数据的优化实践。

## 1. 项目架构演进 (Project Evolution)

### Phase 1: 核心爬虫 (v1.0)
*   **特性**: 建立了基于 Playwright 的强力采集能力，通过 CDP 连接真实浏览器绕过 DataDome。

### Phase 2: Web 平台化 (v2.0)
*   **特性**: 引入了 FastAPI + React 架构，实现了目标发现机制，但采集引擎与 Web 面板处于分离状态。

### Phase 3: 深度集成与工程优化 (v3.0 - Current)
*   **深度融合**: 成功将 Playwright (Deep Mode) 接入 `api/manager.py`。现在用户可以直接从 Web UI 调度双引擎，架构断层已彻底消除。
*   **性能飞跃**: 废弃了 `checkpoint.json`，升级为 **SQLite (B-Tree 索引)** 断点库，支持百万量级 URL 的秒级去重。
*   **Headless 2.0**: 实现了无头模式下的资源拦截优化（禁止加载图片/CSS/字体），使 Deep Engine 的资源占用降低 70%。

---

## 2. 核心架构：双引擎调度中心 (Integrated Dual-Engine)

系统已通过策略模式在 `api/manager.py` 中完美集成了两种采集路径，不再存在 CLI 与 Web 的功能偏差。

| 引擎 | 技术栈 | 核心优势 | 适用场景 |
| :--- | :--- | :--- | :--- |
| **Fast Mode** | `curl_cffi` | **极速**、协议级指纹模拟、支持 JSON API。 | 用于日常增量更新、目标发现。 |
| **Deep Mode** | `Playwright` | **强抗干扰**、执行 JS、支持 Visual Mode (人工干预)。 | 遭遇 403 封锁或需抓取复杂动态加载页面。 |

### 关键优化逻辑：
*   **协同工作**: 两个引擎共享同一个 **SQLite Checkpoint**。
*   **资源保护**: Deep Mode 在静默（Headless）运行时会自动拦截多媒体资源。
*   **状态同步**: 实时统计通过 FastAPI 透传至 UI，支持 Scrape Limit 倒计时。

---

## 3. 数据库与数据治理 (v3.0 Logic)

### 3.1 核心 Schema (Supabase)
项目完全运行在 v3.0 规范下。旧表 `ab_statutes` 已清理。

*   `jurisdictions`: 辖区（如 `ab`, `ca`）。
*   `scrape_targets`: 采集入口配置。
*   `documents`: 文档元数据（Unique URL 约束）。
*   `document_versions`: **核心数据表**，存储 HTML/Content，通过 `content_hash` 实现防冗余。
*   `scrape_jobs`: 任务流水线。

### 3.2 本地断点库 (SQLite)
*   **文件**: `checkpoint.db`
*   **作用**: 代替了过往的内存 Set/JSON 方案。
*   **查询**: `SELECT 1 FROM checkpoints WHERE url = ?` (通过 PRIMARY KEY 索引实现 O(log N) 性能)。

---

## 4. 数据清洗标准 (HTML Cleaning)

所有采集到的 HTML 必须经过 `scraper/html_parser.py` 清洗：
*   **保留**: 正文核心容器（如 `#originalDocument`）。
*   **移除**: 所有的 `<nav>`, `<header>`, `<footer>`, 打印无关元素 (`.d-print-none`)。
*   **哈希生成**: 对清洗后的 `content_text` 进行 SHA-256 计算，对比数据库决定是否产生新版本。

---

## 5. 项目文件地图

*   `api/`
    *   `manager.py`: **调度中枢**。控制双引擎启动、任务状态上报。
    *   `discovery.py`: 目标自动探测逻辑。
*   `scraper/`
    *   `canlii_playwright_scraper.py`: Deep Engine 实现。
    *   `canlii_scraper.py`: Fast Engine 实现。
    *   `supabase_client.py`: v3 架构下的数据库交互层。
    *   `html_parser.py`: 通用解析逻辑。
*   `utils/`
    *   `checkpoint.py`: **SQLite 断点管理**（包含自动迁移逻辑）。
*   `web/`: React + Vite 前端。

---

## 6. AI 开发规范 (AI Developer Rules)

*   **唯一语言**: 交互、注释及文档必须使用**简体中文**。
*   **架构优先**: 修改任何采集逻辑前，优先检查 `api/manager.py` 的调度链条。
*   **性能思维**: 考虑到未来百万量级的案例数据，禁止引入任何会导致 O(N) 内存遍历的本地存储逻辑。
