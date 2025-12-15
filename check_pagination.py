"""
检查法规列表页是否有分页或"加载更多"按钮
"""
from playwright.sync_api import sync_playwright
import time

def check_pagination():
    cdp_url = "http://localhost:9222"
    url = "https://www.canlii.org/ab/laws/stat"
    
    print(f"Connecting to {cdp_url}...")
    
    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(cdp_url)
            context = browser.contexts[0]
            page = context.new_page()
            
            print(f"Navigating to {url}...")
            page.goto(url, wait_until='networkidle')
            page.wait_for_timeout(3000)
            
            # 滚动到底部
            print("Scrolling to bottom...")
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(2000)
            
            # 检查常见的"加载更多"按钮选择器
            selectors = [
                "text='Show more results'",
                "text='Load more'",
                "button[id*='more']",
                ".load-more",
                "#loadMore"
            ]
            
            found = False
            for selector in selectors:
                if page.is_visible(selector):
                    print(f"FOUND Button with selector: {selector}")
                    found = True
                    # 尝试点击
                    # page.click(selector)
                    
            if not found:
                print("No obvious 'Show more' button found via text/standard selectors.")
                
            # 打印页面底部的文本以供人工分析
            print("\nPage footer text sample:")
            footer_text = page.evaluate("document.body.innerText.slice(-500)")
            print(footer_text)
            
            # 截图
            page.screenshot(path="pagination_check.png", full_page=False)
            print("\nScreenshot saved to pagination_check.png")
            
            page.close()
            
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    check_pagination()
