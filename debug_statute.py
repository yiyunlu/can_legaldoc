"""
调试法规详情页结构
连接到现有 Chrome 调试端口，抓取一个法规页面并保存 HTML 和截图
"""
from playwright.sync_api import sync_playwright
import time
from pathlib import Path

# 使用一个已知的法规 URL
TEST_URL = "https://www.canlii.org/en/ab/laws/stat/rsa-2000-c-a-1/latest/rsa-2000-c-a-1.html"
CDP_URL = "http://localhost:9222"

def debug_statute_page():
    print(f"正在连接到浏览器: {CDP_URL}")
    print(f"目标 URL: {TEST_URL}")
    
    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(CDP_URL)
            context = browser.contexts[0]
            page = context.new_page()
            
            print("正在访问页面...")
            page.goto(TEST_URL)
            
            print("等待 5 秒让内容加载...")
            page.wait_for_timeout(5000)
            
            # 保存截图
            screenshot_path = Path("debug_statute_full.png")
            page.screenshot(path=screenshot_path, full_page=True)
            print(f"已保存截图: {screenshot_path.absolute()}")
            
            # 保存 HTML
            html_path = Path("debug_statute.html")
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(page.content())
            print(f"已保存 HTML: {html_path.absolute()}")
            
            # 打印一些结构信息
            print("\n--- 页面结构分析 ---")
            
            # 检查常见容器
            selectors = [
                '#mainContent',
                '.canliiContent',
                '.documentContent',
                '#documentContent',
                'div[class*="content"]',
                'iframe'
            ]
            
            for selector in selectors:
                count = page.locator(selector).count()
                print(f"选择器 '{selector}': 找到 {count} 个")
                if count > 0:
                    # 打印第一个元素的文本开头
                    text = page.locator(selector).first.inner_text()[:100].replace('\n', ' ')
                    print(f"  -> 内容预览: {text}...")
            
            page.close()
            
        except Exception as e:
            print(f"发生错误: {e}")

if __name__ == "__main__":
    debug_statute_page()
