"""
访问一个详情页并截图，用于查看是否被 403
"""
from playwright.sync_api import sync_playwright
import time

def diagnose():
    cdp_url = "http://localhost:9222"
    url = "https://www.canlii.org/en/ab/laws/stat/sa-2002-c-a-4.5/latest/sa-2002-c-a-4.5.html" # 一个失败的 URL
    
    print(f"Connecting to {cdp_url}...")
    
    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(cdp_url)
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            page = context.new_page()
            
            print(f"Navigating to {url}...")
            
            try:
                page.goto(url, wait_until='domcontentloaded', timeout=30000)
            except Exception as e:
                print(f"Goto Exception: {e}")
            
            # 等待几秒
            time.sleep(5)
            
            # 打印标题
            title = page.title()
            print(f"Page Title: {title}")
            
            # 检查是否有特定文本 (DataDome 常见)
            content = page.content()
            if "blocked" in content.lower() or "forbidden" in content.lower() or "captcha" in content.lower():
                print("⚠️ 可能被拦截了 (Check screenshot)")
            
            # 截图
            page.screenshot(path="diagnosis_error.png")
            print("Screenshot saved to 'diagnosis_error.png'. Please check it.")
            
            page.close()
            
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    diagnose()
