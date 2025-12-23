# CanLII Legal Data Platform (v3.1)

这是一个工业级的全栈法律数据采集与管理平台，专为构建支持 RAG (检索增强生成) 的大规模加拿大法律数据库而设计。

> [!IMPORTANT]
> **🤖 AI 开发者注意**: 项目已实现全系统集成与性能调优。核心架构、API 规范及 RAG 优化说明，请务必阅读 [AI_CONTEXT.md](./AI_CONTEXT.md)。

## ✨ 核心特性

*   **v3.0 工业级架构**: 支持全加拿大辖区 (Jurisdiction) 扩展，采用内容哈希 (`SHA-256`) 驱动的版本控制系统，从源头杜绝冗余数据。
*   **统一双引擎调度**:
    *   **快速模式 (Fast)**: 基于 `curl_cffi` 的协议级模拟，实现亚秒级的数据抓取与 JSON API 支持。
    *   **深度模式 (Deep)**: 集成 `Playwright` 的强力模式。支持开启 **Visual Mode** 人工介入验证码，或在后台静默运行。
*   **极限性能优化**:
    *   **SQLite 断点库**: 采用高性能 SQLite B-Tree 索引替代传统 JSON 存储，支持百万级 URL 瞬间去重。
    *   **Headless 2.0**: 无头模式下自动拦截图片、样式和字体加载，显著降低 CPU 和带宽消耗。
*   **实时全栈监控**: 极简而现代的仪表盘，实时展示采集详情、倒计时任务及系统运行状态。

## 🚀 快速启动

### 1. 环境准备
配置 `.env` 文件：
```bash
SUPABASE_URL=你的Supabase项目地址
SUPABASE_KEY=你的API密钥
```

### 2. 启动系统
**后端服务**:
```bash
# 在项目根目录
uvicorn api.main:app --reload --port 8000
```

**前端 UI**:
```bash
cd web
npm run dev
```
访问 `http://localhost:5173` 即可进入工作台。

## 🛠️ 推荐工作流

1.  **目标扫描**: 在 "Discovery" 页面一键探测全省法律列表。
2.  **引擎选择**:
    *   **常规抓取**: 使用 **Fast Engine**。
    *   **反爬顽固期**: 使用 **Deep Engine**，开启 **Visual Mode** 协助浏览器通过验证码。
3.  **数量控制**: 在高级设置中配置 `Scrape Limit`，实现精准的增量或定量采集。

## 📂 技术文档

- [AI_CONTEXT.md](./AI_CONTEXT.md): 详细的数据库 Schema 定义、引擎协作原理及开发规范（**重要**）。
- [walkthrough.md](./walkthrough.md): 详尽的功能迭代日志与验证记录，包含所有关键修复的复盘。
- [database/migration_v3_schema.sql](./database/migration_v3_schema.sql): 核心数据库初始化脚本。

---
*本项目完全遵循 AI 友好型架构开发。*
