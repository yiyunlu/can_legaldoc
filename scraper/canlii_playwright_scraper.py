"""
使用 Playwright 的 CanLII 爬虫
绕过反爬虫机制
"""
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
import time
from typing import List, Dict, Optional
from utils.config import config
from utils.logger import logger
from utils.checkpoint import Checkpoint
from scraper.html_parser import HTMLParser
from scraper.supabase_client import SupabaseClient


class CanLIIPlaywrightScraper:
    """使用 Playwright 的 CanLII 爬虫类"""
    
    def __init__(self, use_checkpoint=True, headless=True, cdp_url: Optional[str] = None):
        """
        初始化爬虫
        
        Args:
            use_checkpoint: 是否使用断点续传
            headless: 是否使用无头模式
            cdp_url: Chrome 远程调试地址 (例如 http://localhost:9222)
        """
        self.headless = headless
        self.cdp_url = cdp_url
        self.parser = HTMLParser()
        self.db_client = SupabaseClient()
        self.checkpoint = Checkpoint() if use_checkpoint else None
        
        self.stats = {
            'total': 0,
            'success': 0,
            'failed': 0,
            'skipped': 0
        }
    
    def _fetch_page(self, url: str, wait_time: int = 2000, wait_selector: str = None) -> Optional[str]:
        """
        使用 Playwright 获取网页内容
        
        Args:
            url: 页面URL
            wait_time: 等待时间（毫秒）
            wait_selector: 等待出现的CSS选择器
            
        Returns:
            Optional[str]: HTML内容或None
        """
        try:
            logger.debug(f"正在获取: {url}")
            
            with sync_playwright() as p:
                if self.cdp_url:
                    # 连接到现有的浏览器实例
                    logger.info(f"正在连接到现有浏览器: {self.cdp_url}")
                    browser = p.chromium.connect_over_cdp(self.cdp_url)
                    # 使用第一个上下文或创建新的
                    context = browser.contexts[0] if browser.contexts else browser.new_context()
                else:
                    # 启动浏览器 - 添加反爬虫参数
                    browser_args = [
                        '--disable-blink-features=AutomationControlled',
                        '--no-sandbox',
                        '--disable-setuid-sandbox',
                        '--disable-infobars',
                        '--window-position=0,0',
                        '--ignore-certificate-errors',
                        '--ignore-ssl-errors',
                        '--disable-translate',
                    ]
                    
                    browser = p.chromium.launch(
                        headless=self.headless,
                        args=browser_args
                    )
                    
                    # 创建上下文
                    context = browser.new_context(
                        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                        viewport={'width': 1366, 'height': 768},
                        locale='en-US',
                        timezone_id='America/Edmonton',
                        geolocation={'latitude': 53.5461, 'longitude': -113.4938}, # Edmonton coordinates
                        permissions=['geolocation'],
                        java_script_enabled=True,
                    )
                    
                    # 添加 stealth 脚本
                    context.add_init_script("""
                        Object.defineProperty(navigator, 'webdriver', {
                            get: () => undefined
                        });
                    """)
                
                # 创建新页面
                page = context.new_page()
                
                # 访问URL
                try:
                    page.goto(url, wait_until='networkidle', timeout=60000)
                except Exception:
                    page.goto(url, wait_until='domcontentloaded', timeout=60000)
                
                # 等待特定元素加载
                if wait_selector:
                    try:
                        logger.info(f"正在等待元素加载: {wait_selector}")
                        page.wait_for_selector(wait_selector, state='visible', timeout=60000)
                        logger.info("元素已加载")
                    except Exception as e:
                        logger.warning(f"等待元素 {wait_selector} 超时: {e}")
                else:
                    # 默认等待时间
                    page.wait_for_timeout(wait_time)
                
                # 额外的稳定等待
                page.wait_for_timeout(2000)
                
                # 模拟人类行为
                if not self.headless:
                    # 只有在有头模式下才需要模拟鼠标
                    try:
                        page.mouse.move(100, 100)
                        page.mouse.down()
                        page.wait_for_timeout(200)
                        page.mouse.up()
                    except Exception:
                        pass
                
                # 获取HTML内容
                content = page.content()
                
                # 关闭浏览器
                browser.close()
                
                # 延迟以遵守速率限制
                time.sleep(config.REQUEST_DELAY)
                
                return content
            return None
            
        except Exception as e:
            logger.error(f"获取页面失败: {e}")
            logger.error(f"URL: {url}")
            return None
    
    def fetch_statute_list(self) -> List[Dict[str, str]]:
        """
        获取法规列表
        
        Returns:
            List[Dict]: 法规列表
        """
        logger.info(f"正在获取法规列表: {config.INDEX_URL}")
        
        try:
            # 使用自定义逻辑获取列表页，处理"显示更多"按钮
            logger.debug(f"正在获取: {config.INDEX_URL}")
            
            with sync_playwright() as p:
                if self.cdp_url:
                    logger.info(f"正在连接到现有浏览器: {self.cdp_url}")
                    browser = p.chromium.connect_over_cdp(self.cdp_url)
                    context = browser.contexts[0] if browser.contexts else browser.new_context()
                else:
                    browser = p.chromium.launch(headless=self.headless)
                    context = browser.new_context(
                        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                    )
                
                page = context.new_page()
                page.goto(config.INDEX_URL, wait_until='networkidle', timeout=60000)
                
                # 等待列表容器
                page.wait_for_selector('#legislationsContainer', state='visible', timeout=60000)
                
                # 处理 "Show more results" 按钮
                while True:
                    try:
                        # 查找按钮（支持多种可能的文本）
                        button = page.get_by_text("Show more results", exact=True)
                        
                        if button.is_visible(timeout=2000):
                            logger.info("发现 'Show more results' 按钮，正在点击...")
                            button.click()
                            # 等待加载
                            page.wait_for_timeout(2000) 
                        else:
                            break
                    except Exception:
                        break
                
                # 获取完整 HTML
                html_content = page.content()
                
                if not self.cdp_url:
                    browser.close()
                else:
                    page.close()

            if not html_content:
                logger.error("获取法规列表失败")
                return []
            
            statutes = self.parser.parse_statute_list(html_content)
            logger.info(f"成功获取 {len(statutes)} 个法规")
            
            return statutes
            
        except Exception as e:
            logger.error(f"获取法规列表时出错: {e}")
            return []
    
    def scrape_statute(self, statute_info: Dict[str, str]) -> bool:
        """
        爬取单个法规
        
        Args:
            statute_info: 法规信息，包含 url, title, citation
            
        Returns:
            bool: 是否成功
        """
        url = statute_info['url']
        title = statute_info['title']
        
        # 检查是否已爬取
        if self.checkpoint and self.checkpoint.is_scraped(url):
            logger.info(f"跳过已爬取的法规: {title}")
            self.stats['skipped'] += 1
            return True
        
        try:
            logger.info(f"正在爬取: {title}")
            
            # 获取详情页
            # 使用较短的等待时间，或者等待特定的内容容器
            html_content = self._fetch_page(url, wait_selector='#originalDocument')
            if not html_content:
                logger.error(f"获取详情页失败: {title}")
                self.stats['failed'] += 1
                return False
            
            # 解析内容
            statute_data = self.parser.parse_statute_detail(html_content, url)
            if not statute_data:
                logger.error(f"解析详情页失败: {title}")
                self.stats['failed'] += 1
                return False
            
            # 保存到数据库
            success = self.db_client.upsert_statute(statute_data)
            
            if success:
                self.stats['success'] += 1
                # 记录到断点
                if self.checkpoint:
                    self.checkpoint.add(url)
                    self.checkpoint.save()
                return True
            else:
                self.stats['failed'] += 1
                return False
                
        except Exception as e:
            logger.error(f"爬取法规时出错: {e}")
            logger.error(f"法规: {title}")
            self.stats['failed'] += 1
            return False
    
    def run(self, limit: Optional[int] = None, only_active: bool = True):
        """
        运行爬虫
        
        Args:
            limit: 限制爬取数量（用于测试）
            only_active: 是否只爬取有效的法规（排除已废除的）
        """
        logger.info("=" * 60)
        logger.info("CanLII Alberta 法规爬虫启动 (Playwright 版本)")
        logger.info("=" * 60)
        
        # 测试数据库连接
        if not self.db_client.test_connection():
            logger.error("数据库连接失败，程序终止")
            return
        
        # 获取法规列表
        statutes = self.fetch_statute_list()
        if not statutes:
            logger.error("未获取到法规列表，程序终止")
            return
        
        # 过滤
        if only_active:
            statutes = [s for s in statutes if s.get('is_active', True)]
            logger.info(f"过滤后剩余 {len(statutes)} 个有效法规")
        
        # 限制数量
        if limit:
            statutes = statutes[:limit]
            logger.info(f"限制爬取数量为 {limit}")
        
        self.stats['total'] = len(statutes)
        
        # 显示进度
        if self.checkpoint:
            progress = self.checkpoint.get_progress(len(statutes))
            logger.info(f"进度: {progress['scraped']}/{progress['total']} "
                       f"({progress['percentage']:.1f}%)")
        
        # 爬取每个法规
        logger.info(f"开始爬取 {len(statutes)} 个法规...")
        
        for i, statute in enumerate(statutes, 1):
            logger.info(f"\n进度: [{i}/{len(statutes)}]")
            self.scrape_statute(statute)
        
        # 显示统计信息
        self._print_stats()
    
    def _print_stats(self):
        """打印统计信息"""
        logger.info("\n" + "=" * 60)
        logger.info("爬取完成 - 统计信息")
        logger.info("=" * 60)
        logger.info(f"总计: {self.stats['total']}")
        logger.info(f"成功: {self.stats['success']}")
        logger.info(f"失败: {self.stats['failed']}")
        logger.info(f"跳过: {self.stats['skipped']}")
        
        if self.stats['total'] > 0:
            success_rate = (self.stats['success'] / self.stats['total']) * 100
            logger.info(f"成功率: {success_rate:.1f}%")
        
        logger.info("=" * 60)
