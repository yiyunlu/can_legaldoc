"""
调试 Playwright 爬虫 - 保存页面内容
"""
from playwright.sync_api import sync_playwright
from utils.config import config
from utils.logger import logger
from pathlib import Path


def debug_fetch_page():
    """调试页面获取"""
    url = config.INDEX_URL
    
    logger.info(f"正在访问: {url}")
    
    with sync_playwright() as p:
        # 启动浏览器
        browser = p.chromium.launch(headless=False)  # 显示浏览器
        
        # 创建上下文
        context = browser.new_context(
            user_agent=config.USER_AGENT,
            viewport={'width': 1920, 'height': 1080}
        )
        
        # 创建新页面
        page = context.new_page()
        
        logger.info("正在加载页面...")
        
        # 访问URL
        page.goto(url, wait_until='networkidle', timeout=60000)
        
        logger.info("页面加载完成，等待3秒...")
        page.wait_for_timeout(3000)
        
        # 获取HTML内容
        content = page.content()
        
        # 保存到文件
        output_file = Path(__file__).parent / 'debug_page.html'
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(content)
        
        logger.info(f"页面内容已保存到: {output_file}")
        logger.info(f"页面长度: {len(content)} 字符")
        
        # 截图
        screenshot_file = Path(__file__).parent / 'debug_screenshot.png'
        page.screenshot(path=str(screenshot_file), full_page=True)
        logger.info(f"截图已保存到: {screenshot_file}")
        
        # 检查关键元素
        logger.info("\n检查关键元素:")
        
        # 检查 tbody
        tbody = page.query_selector('tbody#legislationsContainer')
        logger.info(f"  - tbody#legislationsContainer: {'找到' if tbody else '未找到'}")
        
        # 检查表格
        table = page.query_selector('table#filterableList')
        logger.info(f"  - table#filterableList: {'找到' if table else '未找到'}")
        
        # 检查所有 tbody
        all_tbody = page.query_selector_all('tbody')
        logger.info(f"  - 所有 tbody 元素数量: {len(all_tbody)}")
        
        # 检查所有表格
        all_tables = page.query_selector_all('table')
        logger.info(f"  - 所有 table 元素数量: {len(all_tables)}")
        
        # 保持浏览器打开5秒以便观察
        logger.info("\n浏览器将在5秒后关闭...")
        page.wait_for_timeout(5000)
        
        browser.close()
        
        logger.info("调试完成")


if __name__ == '__main__':
    debug_fetch_page()
