# CanLII Alberta 法规采集器

自动化爬虫工具，用于采集 CanLII 网站上的 Alberta（阿尔伯塔省）合并成文法（Consolidated Statutes），并将数据存储到 Supabase 数据库中。

## 功能特点

- ✅ 自动遍历所有 Alberta 法规
- ✅ 提取法规标题、引文、完整HTML内容
- ✅ 智能速率限制，避免被封禁
- ✅ 断点续传功能，支持中断后恢复
- ✅ 错误处理和自动重试
- ✅ 详细的日志记录
- ✅ Upsert 操作，避免重复数据

## 项目结构

```
CANLII_AB_legislation/
├── main.py                 # 程序入口
├── scraper/                # 爬虫模块
│   ├── __init__.py
│   ├── canlii_scraper.py  # 核心爬虫逻辑
│   ├── html_parser.py     # HTML 解析器
│   └── supabase_client.py # 数据库客户端
├── utils/                  # 工具模块
│   ├── __init__.py
│   ├── config.py          # 配置管理
│   ├── logger.py          # 日志配置
│   └── checkpoint.py      # 断点管理
├── database/               # 数据库
│   └── schema.sql         # 表结构
├── sample_page/            # 示例页面
├── requirements.txt        # Python 依赖
├── .env.example           # 环境变量模板
├── .gitignore             # Git 忽略文件
└── README.md              # 本文件
```

## 安装步骤

### 1. 克隆或下载项目

项目已位于：`/Volumes/Lexar_2T/Canada_DEV/CANLII_AB_legislation`

### 2. 创建虚拟环境（推荐）

```bash
cd /Volumes/Lexar_2T/Canada_DEV/CANLII_AB_legislation
python3 -m venv venv
source venv/bin/activate  # macOS/Linux
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

### 4. 配置环境变量

复制 `.env.example` 为 `.env`：

```bash
cp .env.example .env
```

编辑 `.env` 文件，填入你的 Supabase 凭证：

```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-service-role-key
REQUEST_DELAY=1.5
LOG_LEVEL=INFO
```

### 5. 创建数据库表

在 Supabase 控制台的 SQL Editor 中运行 `database/schema.sql` 文件中的 SQL 语句。

## 使用方法

### 基本用法

### 高级用法 (反爬虫模式 - 推荐)

为了绕过 CanLII 的 DataDome 反爬虫保护，**必须**使用 Chrome DevTools Protocol (CDP) 连接到一个手动启动的 Chrome 浏览器实例。

**步骤 1: 启动 Chrome (调试模式)**

请**完全关闭**所有现有的 Chrome 窗口，然后在终端运行以下命令（创建一个干净后的临时会话）：

```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222 --no-first-run --no-default-browser-check --user-data-dir=$(mktemp -d -t 'chrome-remote_data_dir')
```

**步骤 2: 运行爬虫**

保持上面的 Chrome 窗口打开，在新的终端窗口中运行：

```bash
# 爬取所有法规 (连接到端口 9222)
python3 main_playwright.py --cdp-url http://localhost:9222
```

### 其他常用命令

```bash
# 重置断点，从头开始
python main_playwright.py --reset --cdp-url http://localhost:9222

# 只爬取前 5 个（测试）
python main_playwright.py --limit 5 --cdp-url http://localhost:9222
```

### 命令行参数

| 参数 | 说明 |
|------|------|
| `--limit N` | 限制爬取数量为 N（用于测试） |
| `--reset` | 重置断点，从头开始爬取 |
| `--no-checkpoint` | 不使用断点功能 |
| `--include-inactive` | 包括已废除/未生效的法规 |

## 配置说明

### 环境变量

在 `.env` 文件中配置：

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `SUPABASE_URL` | Supabase 项目 URL | 必填 |
| `SUPABASE_KEY` | Supabase Service Role Key | 必填 |
| `REQUEST_DELAY` | 请求间隔（秒） | 1.5 |
| `LOG_LEVEL` | 日志级别 | INFO |
| `MAX_RETRIES` | 最大重试次数 | 3 |
| `TIMEOUT` | 请求超时时间（秒） | 30 |

### 获取 Supabase 凭证

1. 登录 [Supabase](https://supabase.com/)
2. 选择你的项目
3. 进入 Settings > API
4. 复制 `URL` 和 `service_role` key

## 数据库结构

### ab_statutes 表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| title | TEXT | 法规标题 |
| citation | TEXT | 引文编号（如 RSA 2000, c A-1） |
| content_html | TEXT | HTML 格式内容 |
| content_text | TEXT | 纯文本内容 |
| source_url | TEXT | 来源 URL（唯一） |
| scraped_at | TIMESTAMP | 爬取时间 |
| last_updated | TIMESTAMP | 最后更新时间 |

## 工作流程

1. **获取法规列表**
   - 访问索引页：`https://www.canlii.org/en/ab/laws/stat/`
   - 解析所有法规链接

2. **遍历每个法规**
   - 检查是否已爬取（断点功能）
   - 访问详情页
   - 提取标题、引文、内容

3. **清理和存储**
   - 清理 HTML（删除导航、脚本等）
   - 提取纯文本
   - Upsert 到 Supabase

4. **进度管理**
   - 保存断点
   - 记录日志
   - 显示统计信息

## 日志

日志输出到两个位置：

1. **控制台**：实时显示进度和重要信息
2. **文件**：`scraper.log`，包含详细的调试信息

日志格式：
```
2025-12-13 20:00:00 - canlii_scraper - INFO - 正在爬取: Business Corporations Act
```

## 断点续传

程序会自动保存进度到 `checkpoint.json`：

```json
{
  "scraped_urls": [
    "https://www.canlii.org/en/ab/laws/stat/rsa-2000-c-a-1/latest/...",
    ...
  ],
  "count": 150
}
```

如果程序中断，重新运行时会自动跳过已爬取的法规。

使用 `--reset` 参数可以清除断点，从头开始。

## 故障排除

### 403 错误（访问被拒绝）

**原因**：CanLII 的反爬虫机制

**解决方案**：
1. 增加 `REQUEST_DELAY`（如 2.0 或 3.0）
2. 检查 User-Agent 是否正确
3. 等待一段时间后重试

### 数据库连接失败

**检查**：
1. `SUPABASE_URL` 和 `SUPABASE_KEY` 是否正确
2. 网络连接是否正常
3. Supabase 项目是否激活

### 解析失败

**可能原因**：
1. CanLII 网站结构变化
2. 特定法规页面格式不同

**解决方案**：
1. 查看日志中的错误信息
2. 检查失败的 URL
3. 更新 `html_parser.py` 中的选择器

## 性能优化

- **速率限制**：默认 1.5 秒/请求，可根据需要调整
- **并发**：当前为单线程，可扩展为多线程（需谨慎）
- **缓存**：使用断点避免重复爬取

## 法律和道德考虑

⚠️ **重要提示**：

1. **遵守 robots.txt**：检查 CanLII 的爬虫政策
2. **合理使用**：设置适当的延迟，避免给服务器造成负担
3. **数据使用**：仅用于合法目的
4. **版权**：CanLII 内容可能受版权保护

## 开发者信息

- **版本**：1.0
- **创建日期**：2025-12-13
- **Python 版本**：3.10+

## 许可证

本项目仅供学习和研究使用。

## 更新日志

### v1.0 (2025-12-13)
- ✅ 初始版本
- ✅ 支持 Alberta Consolidated Statutes 爬取
- ✅ Supabase 集成
- ✅ 断点续传功能
- ✅ 完整的错误处理和日志记录

## 贡献

欢迎提交 Issue 和 Pull Request！

## 联系方式

如有问题，请通过 GitHub Issues 联系。
