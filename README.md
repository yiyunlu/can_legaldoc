# Canadian Legal Data Platform (v4.0)

面向加拿大少数族裔的法律咨询 Chatbot 数据基础设施。采集全国 13 省/地区 + 联邦的法律法规及历史判例，构建支持 RAG 检索增强生成的大规模法律知识库。

> [!IMPORTANT]
> **🤖 AI 开发者注意**: 核心架构、API 规范及 RAG 优化说明，请阅读 [AI_CONTEXT.md](./AI_CONTEXT.md)。

---

## 📊 数据源一览

| 数据源 | 类型 | 覆盖范围 | 文档数量 | 接入方式 |
| :--- | :--- | :--- | :--- | :--- |
| **Justice Canada XML** | 联邦法律 | 联邦 (ca) | ~5,800 | GitHub XML 仓库 |
| **BC Laws CiviX API** | 省级法律 | BC 省 | ~880 | REST API |
| **A2AJ Case Law** | 历史判例 | 全国 13 辖区 | 185,000+ | Hugging Face 数据集 |
| **CanLII (Legacy)** | 法律法规 | AB / CA | 2,000+ | 网页爬虫 (有法律风险) |

---

## 🚀 快速启动

### 1. 环境准备

```bash
# 克隆项目
git clone https://github.com/yiyunlu/can_legaldoc.git
cd can_legaldoc

# 安装依赖
pip install -r requirements.txt
```

配置 `.env` 文件：
```bash
SUPABASE_URL=你的Supabase项目URL
SUPABASE_KEY=你的Supabase API密钥
```

### 2. 初始化数据库

在 Supabase Dashboard SQL Editor 中依次执行：
```
database/migration_v3_schema.sql        # 基础 schema
database/migration_v4_multi_source.sql  # 多源支持 + 全国辖区
```

### 3. 验证环境

```bash
# 查看所有已注册的数据源和配置
python main_multi.py --list-sources
```

输出示例：
```
=== Registered Adapters ===
  justice_canada_xml: JusticeCanadaXMLAdapter
  bc_laws_api: BCLawsAPIAdapter
  a2aj_case_law: A2AJCaseLawAdapter
  canlii_legacy: CanLIILegacyAdapter

=== Configured Sources ===
  [ENABLED] justice_canada_xml: Federal Legislation (XML) (ca)
  [ENABLED] bc_laws_api: BC Legislation (CiviX API) (bc)
  [ENABLED] a2aj_case_law: A2AJ Case Law (Hugging Face) (multi)
```

---

## 📥 数据采集

### CLI 方式 (`main_multi.py`)

```bash
# 试运行 -- 仅发现文档，不下载不入库
python main_multi.py --dry-run

# 采集指定数据源，限制数量
python main_multi.py --source-type justice_canada_xml --limit 100
python main_multi.py --source-type bc_laws_api --limit 50
python main_multi.py --source-type a2aj_case_law --limit 500

# 采集全部已启用数据源
python main_multi.py

# 清除断点记录后重新采集
python main_multi.py --reset --source-type bc_laws_api
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
# 启动后端
uvicorn api.main:app --reload --port 8000
```

```bash
# 查看已配置数据源
curl http://localhost:8000/sources

# 查看所有可用适配器
curl http://localhost:8000/sources/available

# 启动多源采集
curl -X POST http://localhost:8000/scraper/start \
  -H "Content-Type: application/json" \
  -d '{"source_type": "justice_canada_xml", "scrape_limit": 100}'

# 查看采集状态
curl http://localhost:8000/status
```

### Web UI 方式

```bash
cd web && npm run dev
```

访问 `http://localhost:5173` 进入可视化工作台。

---

## ⚙️ 数据源配置

编辑 `config.json` 中的 `sources` 数组来管理数据源：

```json
{
  "sources": [
    {
      "source_type": "justice_canada_xml",
      "name": "Federal Legislation (XML)",
      "jurisdiction": "ca",
      "category": "Legislation",
      "enabled": true,
      "params": {}
    },
    {
      "source_type": "a2aj_case_law",
      "name": "A2AJ Case Law (Hugging Face)",
      "jurisdiction": "multi",
      "category": "Case Law",
      "enabled": true,
      "params": {
        "dataset_name": "a2aj/canadian-case-law",
        "streaming": true
      }
    }
  ]
}
```

- `enabled`: 设为 `false` 可暂时禁用某数据源
- `params`: 传递给适配器构造函数的参数

---

## 🏗️ 系统架构

```
┌────────────────────────────────────────────────────┐
│                  main_multi.py (CLI)                │
│                  api/main.py (FastAPI)              │
├────────────────────────────────────────────────────┤
│               Adapter Registry (__init__.py)        │
├──────────┬──────────┬───────────┬─────────────────┤
│ Justice  │ BC Laws  │ A2AJ Case │ CanLII Legacy   │
│ Canada   │ CiviX    │ Law (HF)  │ (Fast/Deep)     │
│ XML      │ API      │           │                 │
├──────────┴──────────┴───────────┴─────────────────┤
│         BaseSourceAdapter (base.py)                │
│  discover_documents() → fetch_documents_batch()    │
├────────────────────────────────────────────────────┤
│  Supabase Client        │  SQLite Checkpoint       │
│  (documents + versions) │  (URL 去重)              │
└────────────────────────────────────────────────────┘
```

### 核心流程

1. **发现 (Discover)**: 适配器扫描数据源，返回 `DocumentMetadata` 列表
2. **去重 (Checkpoint)**: 与 SQLite 断点库比对，过滤已采集的 URL
3. **获取 (Fetch)**: 批量下载文档全文，返回 `DocumentContent`
4. **入库 (Upsert)**: 写入 Supabase，SHA-256 内容哈希驱动版本控制

### 关键目录

```
├── scraper/
│   ├── adapters/                      # 多源适配器
│   │   ├── base.py                    # 抽象基类 BaseSourceAdapter
│   │   ├── __init__.py                # 适配器注册表
│   │   ├── justice_canada_xml.py      # 联邦法律 (GitHub XML)
│   │   ├── bc_laws_api.py             # BC 省法律 (CiviX REST API)
│   │   ├── a2aj_case_law.py           # 全国判例 (Hugging Face)
│   │   └── canlii_legacy.py           # Legacy CanLII 爬虫封装
│   ├── supabase_client.py             # 数据库交互层
│   ├── canlii_scraper.py              # Legacy Fast Engine
│   └── canlii_playwright_scraper.py   # Legacy Deep Engine
├── api/
│   ├── main.py                        # FastAPI 路由 (v4.0)
│   ├── manager.py                     # 调度中枢 (双模式)
│   └── models.py                      # Pydantic 模型
├── utils/
│   ├── config.py                      # 配置管理 (targets + sources)
│   ├── checkpoint.py                  # SQLite 断点管理
│   └── logger.py
├── database/
│   ├── migration_v3_schema.sql        # v3 基础 Schema
│   └── migration_v4_multi_source.sql  # v4 多源扩展
├── web/                               # React + Vite 前端
├── main_multi.py                      # 多源采集 CLI 入口
└── config.json                        # 数据源 + 采集目标配置
```

---

## 📂 数据库 Schema (v4.0)

| 表 | 说明 |
| :--- | :--- |
| `jurisdictions` | 14 个辖区: ca, ab, bc, on, qc, ns, nb, mb, pe, sk, nl, yt, nt, nu |
| `documents` | 文档元数据 (source_url 唯一约束, source_type, document_type) |
| `document_versions` | 内容版本 (content_hash 防冗余) |
| `scrape_targets` | Legacy 采集入口配置 |
| `scrape_jobs` | 任务流水线 |

`documents` 表关键字段:
- `source_type`: 数据来源 (`justice_canada_xml`, `bc_laws_api`, `a2aj_case_law`, `canlii_legacy`)
- `document_type`: 文档类型 (`legislation`, `regulation`, `case_law`)
- `jurisdiction_code`: 辖区代码 (`ca`, `bc`, `on`, ...)

---

## 🔧 开发扩展

### 添加新数据源

1. 在 `scraper/adapters/` 下新建文件
2. 继承 `BaseSourceAdapter`，实现 5 个抽象方法
3. 用 `@register_adapter('your_source_type')` 装饰器注册

```python
from scraper.adapters import register_adapter
from scraper.adapters.base import BaseSourceAdapter, DocumentMetadata, DocumentContent

@register_adapter('alberta_kings_printer')
class AlbertaKingsPrinterAdapter(BaseSourceAdapter):
    def get_source_name(self) -> str:
        return "Alberta King's Printer"

    def get_source_type(self) -> str:
        return "alberta_kings_printer"

    def get_jurisdiction(self) -> str:
        return "ab"

    def discover_documents(self, limit=None):
        # 扫描文档列表 ...
        return [DocumentMetadata(...)]

    def fetch_document(self, doc_meta):
        # 下载单个文档全文 ...
        return DocumentContent(...)
```

4. 在 `scraper/adapters/__init__.py` 的 `_ensure_adapters_loaded()` 中添加模块路径
5. 在 `config.json` 的 `sources` 中添加配置项

### 实施路线图

- [x] **Phase 1**: 核心重构 + Tier 1 数据源 (API/XML 批量接入)
- [ ] **Phase 2**: HTML 爬虫适配器 (AB, SK, MB, NB, NL, YT)
- [ ] **Phase 3**: PDF 提取适配器 (ON, QC, NS, PE, NT, NU)
- [ ] **前端更新**: Sources 管理面板

---

## ⚠️ 法律风险提示

- **CanLII 爬虫**: CanLII 于 2024 年 11 月起诉 Caseway AI 抓取 350 万条记录。直接爬取 CanLII 存在法律风险，Legacy 适配器仅作后备。
- **推荐方案**: 优先使用 Justice Canada XML (Open Government Licence)、BC Laws API (QP Licence 1.0)、A2AJ (MIT) 等开放授权数据源。

---

## 📄 技术文档

- [AI_CONTEXT.md](./AI_CONTEXT.md): 数据库 Schema、引擎协作原理及开发规范
- [walkthrough.md](./walkthrough.md): 功能迭代日志与验证记录
- [database/migration_v3_schema.sql](./database/migration_v3_schema.sql): v3 基础 Schema
- [database/migration_v4_multi_source.sql](./database/migration_v4_multi_source.sql): v4 多源扩展
