# Canadian Legal Data Platform (v5.8)

面向加拿大少数族裔的法律咨询 Chatbot 数据基础设施。采集全国 13 省/地区 + 联邦的法律法规及历史判例，构建支持 RAG 检索增强生成的大规模法律知识库。

> **全容器化部署** — Docker Compose 一键启动（PostgreSQL 16 + FastAPI + React），Cloudflare Tunnel 提供安全的外网访问。

---

## 📊 数据源一览

| 数据源 | 类型 | 覆盖范围 | 文档数量 | 接入方式 | 授权 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Justice Canada XML** | 联邦法律 | 联邦 (ca) | ~5,800 | GitHub XML 仓库 | Open Government Licence |
| **BC Laws CiviX API** | 省级法律 | BC 省 | ~880 | REST API | QP Licence 1.0 |
| **Alberta King's Printer** | 省级法律 | AB 省 | ~1,415 | CKAN API + HTML | 开放数据 |
| **Manitoba Laws** 🆕 | 省级法律 | MB 省 | ~1,926 | HTML 爬取 | OpenMB Licence |
| **Newfoundland Laws** 🆕 | 省级法律 | NL 省 | ~2,105 | HTML 爬取 | Crown Copyright |
| **Nova Scotia Laws** 🆕 | 省级法律 | NS 省 | ~790 | HTML 爬取 | Crown Copyright |
| **New Brunswick Laws** 🆕 | 省级法律 | NB 省 | ~1,560 | HTML 爬取 (Irosoft) | Crown Copyright |
| **Ontario e-Laws** 🆕 | 省级法律 | ON 省 | ~3,044 | REST API (逆向) | Crown Copyright |
| **Yukon Laws** 🆕 | 地区法律 | YT 地区 | ~200 | PDF 下载 (iLAWS) | Crown Copyright |
| **NWT Laws** 🆕 | 地区法律 | NT 地区 | ~300 | PDF 下载 | Crown Copyright |
| **Nunavut Laws** 🆕 | 地区法律 | NU 地区 | ~250 | PDF 下载 | Crown Copyright |
| **Saskatchewan Laws** 🆕 | 省级法律 | SK 省 | ~1,160 | REST API + PDF | Crown Copyright |
| **PEI Laws** 🆕 | 省级法律 | PE 省 | ~850 | PDF 下载 | Crown Copyright |
| **Legis Québec** 🆕 | 省级法律 | QC 省 | ~4,700 | HTML 爬取 (Cyberlex) | Crown Copyright |
| **A2AJ Case Law** | 历史判例 | 全国 13 辖区 | 185,000+ | Hugging Face 数据集 | MIT |
| **CanLII (Legacy)** | 法律法规 | AB / CA | 2,000+ | 网页爬虫 | ⚠️ 有法律风险 |

---

## 🚀 快速启动

### Docker 部署（推荐）

```bash
# 1. 克隆项目
git clone https://github.com/yiyunlu/can_legaldoc.git
cd can_legaldoc

# 2. 配置环境变量
cp .env.example .env
nano .env   # 设置 POSTGRES_PASSWORD

# 3. 一键启动
docker compose up -d --build

# 4. 验证
curl http://localhost:8000/health
# → {"status":"ok","service":"Canadian Legal Data Platform","version":"5.8"}
```

访问 `http://localhost:8000` 进入 Web 管理面板。

### 环境变量说明

| 变量 | 必填 | 说明 |
| :--- | :--- | :--- |
| `POSTGRES_PASSWORD` | ✅ | PostgreSQL 数据库密码 |
| `ADMIN_API_KEY` | 推荐 | 管理端 API 密钥（留空 = 开发模式，跳过认证） |
| `CLOUDFLARE_TUNNEL_TOKEN` | 否 | Cloudflare Tunnel token（外网访问） |
| `ALLOWED_ORIGIN` | 否 | CORS 允许的域名 |
| `SUPABASE_URL` / `SUPABASE_KEY` | 否 | 仅用于旧版迁移 / Keepalive |

> `DATABASE_URL` 由 `docker-compose.yml` 自动拼接，无需手动设置。

---

## 🖥️ Web 管理面板

5 页全功能管理面板（React 19 + Vite 7 暗色主题）：

| 页面 | 功能 |
| :--- | :--- |
| **Dashboard** | 总览：文档统计、来源分布、辖区分布、实时采集进度、每源最后更新时间 |
| **Data Sources** | 数据源管理：启用/禁用、触发采集、配置分发模式 |
| **Documents** | 文档浏览器：搜索、按来源/辖区/类型筛选、分页、本地存储状态图标、点击展开详情（含 Text/HTML 存储大小） |
| **Run History** | 运行历史：状态筛选（完成/失败/运行中）、分页、展开查看完整日志 |
| **Settings** | 设置：内置调度器（每日/间隔）、Supabase Keepalive、限额与分发模式、系统信息（动态版本号）、数据库诊断（一键生成报告 + 复制） |

---

## 📥 数据采集

### Web UI 方式（推荐）

1. 打开 Dashboard → **Data Sources** 页面
2. 选择要采集的数据源，点击 **Run**
3. 在 Dashboard 实时查看采集进度
4. 采集完成后在 **Documents** 页面浏览数据

### CLI 方式

```bash
# 在 Docker 容器内执行
docker exec canlii-platform python main_multi.py --list-sources
docker exec canlii-platform python main_multi.py --limit 100
docker exec canlii-platform python main_multi.py --source-type justice_canada_xml --limit 50
docker exec canlii-platform python main_multi.py --dry-run
```

| 参数 | 说明 |
| :--- | :--- |
| `--source-type TYPE` | 只运行指定数据源 |
| `--limit N` | 限制本次采集的文档总数 |
| `--dry-run` | 仅执行发现阶段，打印文档列表 |
| `--reset` | 清除 SQLite 断点记录 |
| `--list-sources` | 列出所有适配器和配置 |

### API 方式

```bash
# 启动采集 (需要 API Key)
curl -X POST http://localhost:8000/api/scraper/start \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -d '{"source_type": "justice_canada_xml", "scrape_limit": 100}'

# 查看状态 (公开)
curl http://localhost:8000/api/status

# 停止采集 (需要 API Key)
curl -X POST http://localhost:8000/api/scraper/stop \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_KEY" -d '{}'
```

### 自动调度

内置调度器支持定时自动采集，无需外部 cron/systemd：

```bash
# 启用每日自动采集（UTC 02:00，限额 500）
curl -X POST http://localhost:8000/api/scheduler \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer YOUR_API_KEY' \
  -d '{"enabled": true, "schedule_type": "daily", "daily_time": "02:00", "scrape_limit": 500}'

# 手动触发一次调度采集
curl -X POST http://localhost:8000/api/scheduler/trigger \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer YOUR_API_KEY' -d '{}'
```

也可以在 Web 面板的 **Settings** 页面图形化配置。

---

## 🗄️ 数据存储

### 存储架构

平台保存 **全量数据**（元数据 + 完整文档内容），使用两层表结构：

| 表 | 内容 | 说明 |
| :--- | :--- | :--- |
| `documents` | 元数据 | title, citation, source_url, jurisdiction_code, source_type, document_type, metadata (JSONB) |
| `document_versions` | 完整内容 | content_html, content_text (LZ4 压缩), SHA-256 内容哈希, 版本号 |
| `document_chunks` | 分块 | 预留给未来的 RAG / 向量搜索 |

### 版本控制

每次采集时对文档内容计算 SHA-256 哈希：
- **内容未变** → 跳过，不创建新版本（节省存储）
- **内容已变** → 旧版本标记 `is_latest=false`，创建新版本（保留完整变更历史）

### 完整 Schema

| 表 | 说明 |
| :--- | :--- |
| `jurisdictions` | 14 个辖区: ca, ab, bc, on, qc, ns, nb, mb, pe, sk, nl, yt, nt, nu |
| `documents` | 文档元数据 (source_url 唯一约束, source_type, document_type) |
| `document_versions` | 内容版本 (content_hash 防冗余, LZ4 压缩) |
| `document_chunks` | 文本分块 (预留 RAG) |
| `scrape_targets` | Legacy 采集入口配置 |
| `scrape_jobs` | 任务运行记录 |
| `scheduler_config` | 调度器配置 (单行表) |

---

## 🏗️ 系统架构

```
┌────────────────────────────────────────────────────────────┐
│               Docker Compose 容器编排                       │
├────────────────────────────────────────────────────────────┤
│  app (canlii-platform)                                     │
│  ├── FastAPI (api/main.py)         → /api/* 路由           │
│  ├── React SPA (web/)              → / 前端 (5 页面)       │
│  ├── ScraperManager (api/manager)  → 采集调度              │
│  ├── SchedulerService              → 定时自动采集           │
│  └── main_multi.py (CLI)           → 命令行采集入口         │
├────────────────────────────────────────────────────────────┤
│  postgres (canlii-postgres)        → PostgreSQL 16         │
│  └── LZ4 压缩 + 版本控制 + 全文存储                         │
├────────────────────────────────────────────────────────────┤
│  cloudflared (canlii-tunnel)       → Cloudflare Tunnel     │
│  └── 安全外网访问 (可选)                                    │
└────────────────────────────────────────────────────────────┘

适配器架构 (16 个数据源):
┌──────────┬──────────┬──────────┬───────────┬──────────┐
│ Justice  │ BC Laws  │ Alberta  │ A2AJ Case │ CanLII   │
│ Canada   │ CiviX    │ King's   │ Law (HF)  │ Legacy   │
│ XML      │ API      │ Printer  │           │          │
├──────────┼──────────┼──────────┼───────────┼──────────┤
│ Manitoba │ NL       │ NS       │ NB        │ Ontario  │
│ Laws     │ Laws     │ Laws     │ Laws      │ e-Laws   │
├──────────┼──────────┼──────────┼───────────┼──────────┤
│ Yukon    │ NWT      │ Nunavut  │ Sask.     │ PEI      │
│ Laws     │ Laws     │ Laws     │ Laws 🆕   │ Laws 🆕  │
├──────────┼──────────┴──────────┴───────────┴──────────┤
│ Legis    │                                            │
│ Québec🆕 │    (全 10 省 + 3 地区完整覆盖)               │
├──────────┴───────────────────────────────────────────┤
│              BaseSourceAdapter (base.py)               │
│   discover_documents() → fetch_documents_batch()       │
├───────────────────────────────────────────────────────┤
│   DatabaseClient (psycopg2)  │  SQLite Checkpoint     │
└───────────────────────────────────────────────────────┘
```

### 核心流程

1. **发现 (Discover)**: 适配器扫描数据源，返回 `DocumentMetadata` 列表
2. **去重 (Checkpoint)**: 与 SQLite 断点库比对，过滤已采集的 URL
3. **获取 (Fetch)**: 批量下载文档全文 (HTML + 纯文本)，返回 `DocumentContent`
4. **入库 (Upsert)**: 写入 PostgreSQL，SHA-256 内容哈希驱动版本控制

### 关键目录

```
├── scraper/
│   ├── adapters/                      # 多源适配器
│   │   ├── base.py                    # 抽象基类 BaseSourceAdapter
│   │   ├── __init__.py                # 适配器注册表
│   │   ├── justice_canada_xml.py      # 联邦法律 (GitHub XML)
│   │   ├── bc_laws_api.py             # BC 省法律 (CiviX REST API)
│   │   ├── alberta_kings_printer.py   # Alberta 省法律 (CKAN + HTML)
│   │   ├── manitoba_laws.py           # 🆕 Manitoba 省法律 (HTML)
│   │   ├── newfoundland_laws.py       # 🆕 NL 省法律 (HTML)
│   │   ├── nova_scotia_laws.py        # 🆕 NS 省法律 (HTML)
│   │   ├── new_brunswick_laws.py      # 🆕 NB 省法律 (Irosoft HTML)
│   │   ├── ontario_elaws.py           # 🆕 Ontario 省法律 (REST API)
│   │   ├── yukon_laws.py              # 🆕 Yukon 地区法律 (PDF)
│   │   ├── nwt_laws.py                # 🆕 NWT 地区法律 (PDF)
│   │   ├── nunavut_laws.py            # 🆕 Nunavut 地区法律 (PDF)
│   │   ├── saskatchewan_laws.py       # 🆕 SK 省法律 (REST API + PDF)
│   │   ├── pei_laws.py                # 🆕 PEI 省法律 (PDF)
│   │   ├── quebec_laws.py             # 🆕 QC 省法律 (HTML)
│   │   ├── a2aj_case_law.py           # 全国判例 (Hugging Face)
│   │   └── canlii_legacy.py           # Legacy CanLII 爬虫封装
│   └── db_client.py                   # PostgreSQL 交互层 (psycopg2 连接池)
├── api/
│   ├── main.py                        # FastAPI 路由
│   ├── manager.py                     # 采集调度中枢
│   ├── scheduler.py                   # 内置定时调度器
│   └── models.py                      # Pydantic 模型
├── utils/
│   ├── config.py                      # 配置管理
│   ├── checkpoint.py                  # SQLite 断点管理
│   └── logger.py
├── database/
│   └── init.sql                       # 完整 Schema (Docker 首次启动自动执行)
├── web/                               # React 19 + Vite 7 前端
│   └── src/pages/                     # 5 个页面组件
│       ├── Dashboard.jsx
│       ├── DataSources.jsx
│       ├── Documents.jsx
│       ├── RunHistory.jsx
│       └── Settings.jsx
├── scripts/
│   ├── migrate_supabase_to_local.py   # Supabase → PostgreSQL 迁移
│   ├── pre_upgrade_check.py           # 升级前诊断 (v5.4 兼容)
│   ├── fix_before_upgrade.py          # 升级前数据修复 (支持 --dry-run)
│   ├── post_upgrade_check.py          # 升级后验证
│   └── db_health_check.py             # 日常健康检查
├── main_multi.py                      # 多源采集 CLI 入口
├── config.json                        # 数据源配置
├── docker-compose.yml                 # 容器编排
├── Dockerfile                         # 应用镜像构建
└── start.sh                           # 容器启动脚本
```

---

## 🔌 API 端点

| 方法 | 路径 | 认证 | 说明 |
| :--- | :--- | :--- | :--- |
| GET | `/health` | — | 健康检查 + 版本号 |
| GET | `/api/auth/status` | — | 检查认证是否启用 |
| POST | `/api/auth/verify` | Bearer | 验证 API 密钥 |
| GET | `/api/status` | — | 采集器状态 + 调度器信息 |
| GET | `/api/sources` | — | 已配置数据源列表 |
| GET | `/api/sources/available` | — | 所有可用适配器 |
| GET | `/api/sources/stats` | — | 文档统计（按来源/辖区/类型） |
| POST | `/api/sources` | Bearer | 更新数据源配置 |
| POST | `/api/scraper/start` | Bearer | 启动采集 |
| POST | `/api/scraper/stop` | Bearer | 停止采集 |
| GET | `/api/scheduler` | — | 获取调度器配置 |
| POST | `/api/scheduler` | Bearer | 更新调度器配置 |
| POST | `/api/scheduler/trigger` | Bearer | 手动触发一次调度采集 |
| GET | `/api/jobs` | — | 分页查询运行历史 |
| GET | `/api/documents` | — | 分页查询文档列表（支持搜索/筛选） |
| GET | `/api/documents/{id}` | — | 文档详情（元数据 + 版本信息） |
| GET | `/api/debug/db` | Bearer | 数据库诊断报告（表大小、行数、内容统计、索引） |

> **认证说明**: 标记 "Bearer" 的端点需要 `Authorization: Bearer <ADMIN_API_KEY>` 请求头。未设置 `ADMIN_API_KEY` 时为开发模式，所有端点无需认证。

---

## 🔧 开发扩展

### 添加新数据源

1. 在 `scraper/adapters/` 下新建文件
2. 继承 `BaseSourceAdapter`，实现 5 个抽象方法
3. 用 `@register_adapter('your_source_type')` 装饰器注册

```python
from scraper.adapters import register_adapter
from scraper.adapters.base import BaseSourceAdapter, DocumentMetadata, DocumentContent

@register_adapter('your_source_type')
class YourSourceAdapter(BaseSourceAdapter):
    def get_source_name(self) -> str:
        return "Your Source Name"

    def get_source_type(self) -> str:
        return "your_source_type"

    def get_jurisdiction(self) -> str:
        return "xx"  # 辖区代码

    def discover_documents(self, limit=None):
        # 扫描文档列表 ...
        return [DocumentMetadata(...)]

    def fetch_document(self, doc_meta):
        # 下载单个文档全文 ...
        return DocumentContent(...)
```

4. 在 `scraper/adapters/__init__.py` 的 `_ensure_adapters_loaded()` 中添加模块路径
5. 在 `config.json` 的 `sources` 中添加配置项，或通过 Web 面板 Data Sources 页面添加

### 实施路线图

- [x] **Phase 1**: 核心重构 + Tier 1 数据源 (API/XML 批量接入)
- [x] **Phase 2**: Alberta King's Printer 适配器
- [x] **Phase 3**: 自托管 PostgreSQL + Docker 全容器化
- [x] **Phase 4**: 内置调度器 + 文档浏览器
- [x] **Phase 5**: 5 省适配器 — MB, NL, NS, NB, ON (v5.5)
- [x] **Phase 6a**: 3 地区 PDF 适配器 — YT, NT, NU (v5.6)
- [x] **Phase 6b**: 3 省适配器 — SK, PE, QC (v5.7) ✅ **全 10 省 + 3 地区完整覆盖**
- [x] **Phase 6c**: API Key 认证 + BC Laws 嵌套法案修复 (v5.8)
- [ ] **Phase 7**: RAG 向量搜索集成 (pgvector)

---

## ⚠️ 法律风险提示

- **CanLII 爬虫**: CanLII 于 2024 年 11 月起诉 Caseway AI 抓取 350 万条记录。直接爬取 CanLII 存在法律风险，Legacy 适配器仅作后备。
- **推荐方案**: 优先使用 Justice Canada XML (Open Government Licence)、BC Laws API (QP Licence 1.0)、A2AJ (MIT) 等开放授权数据源。

---

## 📄 文档

| 文件 | 说明 |
| :--- | :--- |
| [DEPLOY.md](./DEPLOY.md) | 部署指南（PVE + Docker + Cloudflare Tunnel） |
| [CHANGELOG.md](./CHANGELOG.md) | 版本更新日志 (v5.0 → v5.8) |
| [TROUBLESHOOTING.md](./TROUBLESHOOTING.md) | 常见问题排查 |
