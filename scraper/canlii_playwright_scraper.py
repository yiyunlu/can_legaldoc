"""
使用 Playwright 的 CanLII 爬虫
绕过反爬虫机制
"""
import os
import random
import subprocess
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
import threading
import time
from typing import List, Dict, Optional
from utils.config import config
from utils.logger import logger
from utils.checkpoint import Checkpoint
from scraper.html_parser import HTMLParser
from scraper.supabase_client import SupabaseClient


class CanLIIPlaywrightScraper:
    """使用 Playwright 的 CanLII 爬虫类 (支持持久化、人工介入、CDP与系统镜像)"""
    
    def __init__(self, use_checkpoint=True, headless=True, cdp_url: Optional[str] = None):
        """
        初始化爬虫
        
        Args:
            use_checkpoint: 是否使用断点续传
            headless: 是否使用无头模式
            cdp_url: 开了远程调试的 Chrome 地址 (如 http://127.0.0.1:9222)
        """
        self.headless = headless
        self.cdp_url = cdp_url
        self.parser = HTMLParser()
        self.db_client = SupabaseClient()
        self.checkpoint = Checkpoint() if use_checkpoint else None
        
        # 浏览器实例管理
        self.playwright = None
        self.browser_context = None
        self.user_data_dir = os.path.abspath(".browser_profile")
        
        self.stats = {
            'total': 0,
            'success': 0,
            'failed': 0,
            'skipped': 0
        }

    def start(self):
        """启动持久化浏览器环境或连接到 CDP"""
        if self.browser_context:
            return
            
        self.playwright = sync_playwright().start()

        if self.cdp_url and not self.headless:
            logger.info(f"正在连接到用户的真实浏览器 (CDP): {self.cdp_url}")
            try:
                # 连接到已打开的浏览器
                browser = self.playwright.chromium.connect_over_cdp(self.cdp_url)
                # 连接 CDP 时，通常直接使用第一个 Context
                if browser.contexts:
                    self.browser_context = browser.contexts[0]
                else:
                    self.browser_context = browser.new_context()
                logger.info("CDP 连接成功，由于是在真实浏览器操作，将共享您的所有登录状态。")
            except Exception as e:
                logger.error(f"CDP 连接失败: {e}")
                raise
        else:
            if self.headless:
                logger.info("启动纯后台模式 (Headless)，将忽略 CDP 设置以确保不弹出窗口。")
            else:
                logger.info(f"正在启动 Playwright 浏览器 (Channel: chrome, Headless: {self.headless})...")
            # 启动持久化上下文，优先使用系统 Chrome 通道
            self.browser_context = self.playwright.chromium.launch_persistent_context(
                user_data_dir=self.user_data_dir,
                headless=self.headless,
                channel="chrome", # 核心：使用本机的 Chrome 镜像
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                viewport={'width': 1366, 'height': 768},
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--no-sandbox',
                ],
                ignore_https_errors=True,
                java_script_enabled=True,
            )
        
        # 性能优化：禁止加载图片、字体、媒体资源（有头/无头都适用）
        self.browser_context.route(
            "**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,ttf,otf,mp4,webm}",
            lambda route: route.abort()
        )
        logger.info("已开启资源优化：禁止加载图片/字体/媒体资源。")

        # 添加 stealth 脚本 (如果不是 CDP)
        if not self.cdp_url or self.headless:
            self.browser_context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
            """)

    def stop(self):
        """关闭浏览器环境"""
        if self.browser_context:
            self.browser_context.close()
            self.browser_context = None
        if self.playwright:
            self.playwright.stop()
            self.playwright = None
        logger.info("浏览器环境已关闭")

    def _check_captcha(self, page) -> bool:
        """检查是否存在验证码或拦截页面"""
        captcha_indicators = [
            "Verify you are human",
            "Checking if the site connection is secure",
            "hcaptcha-container",
            "g-recaptcha",
            "Cloudflare",
            "DataDome",
            "Access Denied"
        ]
        
        content = page.content()
        for indicator in captcha_indicators:
            if indicator in content:
                logger.warning(f"检测到检测/验证码页面 (特征: {indicator})")
                return True
        return False

    def _handle_captcha(self, page):
        """
        处理验证码逻辑
        增加声音提醒 + 长时间冷却（10-15 分钟）后终止任务
        """
        if self.headless:
            logger.error("在无头模式下检测到验证码，无法自动通过。请切换到可视化模式并手动操作。")
            raise Exception("CAPTCHA_DETECTED")
        
        # 1. 声音报警 (macOS 特定指令)
        try:
            logger.info("🔊 正在播放验证码报警音...")
            subprocess.Popen(["afplay", "/System/Library/Sounds/Glass.aiff"])
        except Exception as se:
            logger.warning(f"无法播放报警音: {se}")

        logger.info("=" * 60)
        logger.info("🚨 检测到验证码！请在浏览器窗口手动完成验证。")
        logger.info("⏳ 将进入冷却期以降低风控概率，之后自动停止任务。")
        logger.info("=" * 60)

        cooldown_seconds = random.randint(600, 900)
        logger.warning(f"进入冷却期: {cooldown_seconds} 秒 (约 {cooldown_seconds // 60} 分钟)")
        start_time = time.time()
        while True:
            elapsed = int(time.time() - start_time)
            remaining = cooldown_seconds - elapsed

            if remaining <= 0:
                break

            if hasattr(self, 'stop_event') and self.stop_event and self.stop_event.is_set():
                logger.info("冷却期间检测到停止信号，中断等待。")
                raise Exception("STOP_REQUESTED")

            if remaining % 60 == 0:
                logger.info(f"冷却中... 剩余 {remaining // 60} 分钟")

            time.sleep(5)

        logger.error("❌ 验证码触发后冷却期结束，任务自动停止，请稍后重启。")
        raise Exception("CAPTCHA_COOLDOWN")
        
    def _fetch_page(self, url: str, wait_selector: str = None) -> Optional[str]:
        """使用现有的上下文获取网页内容"""
        if not self.browser_context:
            self.start()
            
        page = self.browser_context.new_page()
        try:
            logger.debug(f"正在访问: {url}")
            
            # 访问 URL
            try:
                page.goto(url, wait_until='networkidle', timeout=60000)
            except Exception:
                page.goto(url, wait_until='domcontentloaded', timeout=60000)
            
            # 检查验证码
            if self._check_captcha(page):
                self._handle_captcha(page)
            
            # 等待特定元素加载
            if wait_selector:
                try:
                    page.wait_for_selector(wait_selector, state='visible', timeout=10000)
                except Exception:
                    # 如果超时，再次检查是否是验证码
                    if self._check_captcha(page):
                        self._handle_captcha(page)
                        # 如果过完验证码，重新等待
                        page.wait_for_selector(wait_selector, state='visible', timeout=30000)
            else:
                page.wait_for_timeout(2000)
            
            # 模拟微小的人类滚动动作
            page.evaluate("window.scrollBy(0, 100)")
            page.wait_for_timeout(random.randint(800, 1800))
            
            content = page.content()
            return content
        except Exception as e:
            if "CAPTCHA" in str(e) or "STOP_REQUESTED" in str(e):
                raise
            logger.error(f"获取页面失败: {e}")
            return None
        finally:
            page.close()
            # 基础延迟
            time.sleep(config.REQUEST_DELAY)
            # 随机抖动延迟，降低节奏规律性
            time.sleep(random.uniform(1.5, 4.5))
    
    def fetch_statute_list(self, index_url: Optional[str] = None) -> List[Dict[str, str]]:
        """
        获取法规列表
        
        Returns:
            List[Dict]: 法规列表
        """
        target_url = index_url or config.INDEX_URL
        if not target_url:
            logger.error("未指定目标 URL")
            return []
            
        logger.info(f"正在获取法规列表: {target_url}")
        
        if not self.browser_context:
            self.start()
            
        page = self.browser_context.new_page()
        try:
            page.goto(target_url, wait_until='networkidle', timeout=60000)
            
            # 检查验证码
            if self._check_captcha(page):
                self._handle_captcha(page)
            
            # 等待列表容器
            page.wait_for_selector('#legislationsContainer', state='visible', timeout=60000)
            
            # 处理 "Show more results" 按钮
            while True:
                try:
                    button = page.get_by_text("Show more results", exact=True)
                    if button.is_visible(timeout=2000):
                        logger.info("发现 'Show more results' 按钮，正在点击...")
                        button.click()
                        page.wait_for_timeout(2000) 
                    else:
                        break
                except Exception:
                    break
            
            html_content = page.content()
            statutes = self.parser.parse_statute_list(html_content)
            logger.info(f"成功解析 {len(statutes)} 个法规")
            return statutes
            
        except Exception as e:
            logger.error(f"获取法规列表失败: {e}")
            return []
        finally:
            page.close()
    
    def scrape_statute(self, statute_info: Dict[str, str], context: Optional[Dict] = None) -> bool:
        """
        爬取单个法规
        
        Args:
            statute_info: 法规信息，包含 url, title, citation, is_active
            context: 抓取上下文，包含 jurisdiction_code, category, target_id
            
        Returns:
            bool: 是否成功
        """
        url = statute_info['url']
        title = statute_info['title']
        context = context or {}
        
        # 即使断点记录显示已爬取，我们也同步一下状态（因为列表页就能拿到状态，且速度很快）
        self.db_client.update_document_status(url, statute_info.get('is_active', True))
        
        # 检查是否已爬取
        if self.checkpoint and self.checkpoint.is_scraped(url):
            logger.info(f"跳过已爬取的法规内容: {title}")
            self.stats['skipped'] += 1
            return True
        
        try:
            logger.info(f"正在爬取: {title}")
            
            # 获取详情页
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
            
            # 合并上下文
            save_data = {
                **statute_data, 
                **context,
                "is_active": statute_info.get('is_active', True)
            }
            
            # 保存到数据库 (使用 v3 架构)
            success = self.db_client.upsert_document_v3(save_data)
            
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
            if "CAPTCHA_DETECTED" in str(e):
                # 重新抛出，让 run() 捕获并停止
                raise
            logger.error(f"爬取法规时出错: {e}")
            logger.error(f"法规: {title}")
            self.stats['failed'] += 1
            return False
    
    def run(self, limit: Optional[int] = None, only_active: bool = False, target_url: Optional[str] = None, context: Optional[Dict] = None, stop_event: Optional[threading.Event] = None):
        """
        运行爬虫
        
        Args:
            limit: 限制爬取数量（用于测试）
            only_active: 是否只爬取有效的法规（如果为False，则会记录并标记已废除的法规）
            target_url: 指定爬取的目标URL
            context: 抓取上下文，用于保存到 v3 数据库
            stop_event: 停止信号
        """
        self.stop_event = stop_event # 存储信号
        logger.info("=" * 60)
        logger.info(f"CanLII 采集启动 (Playwright & 持久会话)")
        logger.info("=" * 60)
        
        # 测试数据库连接
        if not self.db_client.test_connection():
            logger.error("数据库连接失败，程序终止")
            return
        
        try:
            # 确保浏览器已启动
            self.start()
            
            # 获取法规列表
            # 使用传入的 target_url 或从 config 获取
            statutes = self.fetch_statute_list(index_url=target_url)
            if not statutes:
                logger.error("未获取到法规列表，程序终止")
                return
            
            # 过滤
            if only_active:
                statutes = [s for s in statutes if s.get('is_active', True)]
                logger.info(f"过滤后剩余 {len(statutes)} 个有效法规")
            
            # statutes = statutes[:limit]  <-- REMOVED: Don't limit the list, limit the active scrapes
            # logger.info(f"限制爬取数量为 {limit}")
            
            self.stats['total'] = len(statutes)
            
            # 1. 高性能批量过滤 (Pre-filtering)
            logger.info("[Deep Engine] 正在执行高性能本地去重扫描...")
            statute_urls = [s['url'] for s in statutes]
            scraped_urls = self.checkpoint.filter_scraped_urls(statute_urls) if self.checkpoint else set()
            
            # 将列表分为：待爬取 和 已爬取
            to_scrape = []
            for s in statutes:
                if s['url'] in scraped_urls:
                    self.stats['skipped'] += 1
                else:
                    to_scrape.append(s)
            
            if self.stats['skipped'] > 0:
                logger.info(f"✨ [Deep Engine] 瞬时跳过: 发现 {self.stats['skipped']} 个已抓取的 URL。")
                
            # 2. 检查用户设置的数量限制
            if limit and len(to_scrape) > limit:
                logger.info(f"根据用户设置的限制 (Limit: {limit})，仅抓取前 {limit} 条新法规。")
                to_scrape = to_scrape[:limit]
                
            if not to_scrape:
                logger.info("所有法规均已爬取或无新增内容。")
                self._print_stats()
                return
                
            # 3. 串行抓取 (保持稳定性)
            logger.info(f"开始爬取 {len(to_scrape)} 个新法规...")
            
            # 随机化长休眠节奏
            next_long_rest = random.randint(20, 30)
            processed_since_rest = 0

            for i, statute in enumerate(to_scrape, 1):
                if stop_event and stop_event.is_set():
                    logger.info("检测到停止信号，正在中断采集...")
                    break
                    
                logger.info(f"进度: [{i}/{len(to_scrape)}] (总进度: {self.stats['success'] + self.stats['failed'] + self.stats['skipped']}/{self.stats['total']})")
                
                try:
                    self.scrape_statute(statute, context=context)
                    processed_since_rest += 1
                except Exception as e:
                    if "CAPTCHA_COOLDOWN" in str(e):
                        logger.error("❌ 验证码触发冷却后停止，请稍后重启任务。")
                        break
                    if "CAPTCHA_DETECTED" in str(e):
                        logger.error("检测到验证码拦截，任务终止。请切换模式或手动处理后重试。")
                        break 
                    if "STOP_REQUESTED" in str(e):
                        logger.info("由于停止请求，任务已提前终止。")
                        break
                    raise 

                # 每条法规后随机小延迟
                time.sleep(random.uniform(1.5, 4.5))

                # 长休眠：每 20-30 条随机休眠 40-120 秒
                if processed_since_rest >= next_long_rest:
                    long_rest = random.randint(40, 120)
                    logger.info(f"触发长休眠: {long_rest} 秒 (已处理 {processed_since_rest} 条)")
                    time.sleep(long_rest)
                    processed_since_rest = 0
                    next_long_rest = random.randint(20, 30)
            
            # 显示统计信息
            self._print_stats()
            
        finally:
            # 只有在 run 结束后才关闭浏览器
            self.stop()
    
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
