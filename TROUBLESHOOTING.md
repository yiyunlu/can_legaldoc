# 问题排查

## Docker / 部署相关

### PostgreSQL 容器无法启动

```bash
# 检查容器状态
docker compose ps

# 查看 PostgreSQL 日志
docker compose logs postgres

# 常见原因: pgdata 卷损坏 → 重建
docker compose down -v   # ⚠️ 这会删除所有数据
docker compose up -d --build
```

### app 容器启动失败 / 连不上数据库

```bash
# 确认 PostgreSQL 先启动完成
docker compose logs app | grep "database"

# 手动测试数据库连接
docker exec canlii-postgres pg_isready -U canlii -d canlii

# 检查 DATABASE_URL 是否正确
docker exec canlii-platform env | grep DATABASE_URL
```

### 端口 8000 被占用

```bash
# 查看占用进程
lsof -i :8000

# 修改 docker-compose.yml 中的端口映射
# ports: - "8080:8000"
```

### Docker build 很慢 / Playwright 安装太大

如果不需要 Legacy CanLII 爬虫，可以跳过 Playwright 安装（节省 ~800 MB）：

```yaml
# docker-compose.yml
args:
  INSTALL_PLAYWRIGHT: "false"
```

---

## 采集相关

### 采集卡住 / 无进度

```bash
# 查看采集器状态
curl http://localhost:8000/api/status

# 查看容器日志
docker compose logs -f app --tail 100

# 强制停止正在运行的采集
curl -X POST http://localhost:8000/api/scraper/stop \
  -H "Content-Type: application/json" -d '{}'
```

### A2AJ 数据集下载慢

A2AJ Case Law 数据集 (~185K 文档) 来自 Hugging Face，首次加载可能需要几分钟。建议：
- 设置较小的 `scrape_limit`（如 500）分批采集
- 确保服务器网络可以访问 huggingface.co

### Alberta King's Printer 采集失败

Alberta 数据源依赖 open.alberta.ca (CKAN API) 和 Kings Printer 网站。检查：

```bash
# 测试 CKAN API 可达性
docker exec canlii-platform curl -s "https://open.alberta.ca/api/3/action/package_search?q=&rows=1" | head -100

# 测试 Kings Printer 可达性
docker exec canlii-platform curl -s "https://kings-printer.alberta.ca" | head -20
```

### 断点记录导致文档被跳过

SQLite 断点记录了已采集的 URL。如果需要重新采集：

```bash
# 清除指定源的断点记录
docker exec canlii-platform python main_multi.py --reset --source-type bc_laws_api

# 或删除整个断点数据库（重新采集所有源）
rm checkpoint.db
docker compose restart app
```

---

## Web 前端相关

### 页面加载空白 / API 无响应

```bash
# 检查后端健康状态
curl http://localhost:8000/health

# 检查前端是否正确构建
docker exec canlii-platform ls /app/web/dist/

# 查看 app 容器日志
docker compose logs app --tail 50
```

### Documents 页面搜索无结果

Documents 页面使用 PostgreSQL `ILIKE` 进行标题搜索。如果搜索无结果：
- 确认数据库中确实有文档：`curl http://localhost:8000/api/sources/stats`
- 尝试更简短的关键词（搜索基于标题匹配）
- 检查筛选器是否选择了错误的来源/辖区

### 调度器不触发

```bash
# 检查调度器状态
curl http://localhost:8000/api/scheduler

# 确认 enabled=true 且 next_run_at 有值
# 调度器每 60 秒检查一次，可能有最多 1 分钟延迟

# 手动触发测试
curl -X POST http://localhost:8000/api/scheduler/trigger \
  -H 'Content-Type: application/json' -d '{}'
```

---

## CanLII Legacy 爬虫 (⚠️ 有法律风险)

### DataDome 反爬虫 (403 错误)

CanLII 使用 DataDome 反爬虫系统。即使使用 Playwright Stealth 模式，仍可能被检测。

**解决方案: 连接到已手动验证的 Chrome 浏览器**

```bash
# 1. 启动 Chrome 调试模式
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9222 \
  --user-data-dir="/tmp/chrome_debug_profile" \
  --no-first-run \
  --no-default-browser-check

# 2. 在 Chrome 中手动访问 https://www.canlii.org 并完成验证

# 3. 运行爬虫连接到该浏览器
python3 main_playwright.py --limit 5 --cdp-url http://localhost:9222
```

> **注意:** 直接爬取 CanLII 存在法律风险。建议优先使用 Justice Canada XML、BC Laws API、A2AJ 等开放授权数据源。

---

## 数据库相关

### 查看数据库大小

```bash
docker exec canlii-postgres psql -U canlii -d canlii -c "
SELECT pg_size_pretty(pg_database_size('canlii')) AS db_size;
"
```

### 查看各表行数

```bash
docker exec canlii-postgres psql -U canlii -d canlii -c "
SELECT 'documents' AS table_name, COUNT(*) FROM documents
UNION ALL
SELECT 'document_versions', COUNT(*) FROM document_versions
UNION ALL
SELECT 'scrape_jobs', COUNT(*) FROM scrape_jobs;
"
```

### 备份与恢复

```bash
# 备份
docker exec canlii-postgres pg_dump -U canlii canlii > backup_$(date +%Y%m%d).sql

# 恢复
docker compose stop app
docker exec -i canlii-postgres psql -U canlii canlii < backup_20250217.sql
docker compose start app
```
