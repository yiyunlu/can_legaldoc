# 问题解决方案

## 问题 1: Supabase RLS 策略错误 ✅

已修复。

## 问题 2: CanLII 反爬虫机制（403 错误）⚠️

**更新 (2025-12-13)**: 即使使用 Playwright Stealth 模式，DataDome 仍然非常严格。

### 终极解决方案：连接到现有 Chrome 浏览器

最有效的方法是人工启动一个 Chrome 浏览器，手动通过验证，然后让爬虫接管该浏览器。

#### 步骤 1: 启动 Chrome 调试模式

在终端中运行以下命令（请确保端口 9222 未被占用）：

```bash
# 启动一个新的 Chrome 实例，使用临时配置文件
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9222 \
  --user-data-dir="/tmp/chrome_debug_profile" \
  --no-first-run \
  --no-default-browser-check
```

一个新的 Chrome 窗口将会打开。

#### 步骤 2: 手动通过验证

1. 在新打开的 Chrome 窗口中，访问 `https://www.canlii.org/en/ab/laws/stat/`
2. 如果出现验证码，**请手动完成验证**。
3. 确保你能看到法规列表页面。

#### 步骤 3: 运行爬虫链接到该浏览器

保持 Chrome 窗口打开，在原来的终端中运行爬虫：

```bash
cd /Users/eddielu/Canada_DEV/CANLII_AB_legislation
python3 main_playwright.py --limit 5 --cdp-url http://localhost:9222
```

---

## 其他调试命令

显示浏览器窗口运行（不连接现有浏览器）：
```bash
python3 main_playwright.py --limit 2 --visible
```
