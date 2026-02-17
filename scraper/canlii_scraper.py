"""
CanLII 爬虫核心模块
处理网页请求、解析和数据存储
"""
from curl_cffi import requests
import time
from typing import List, Dict, Optional
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from requests.exceptions import RequestException, Timeout, HTTPError # curl_cffi raises compatible exceptions or its own
import threading
from concurrent.futures import ThreadPoolExecutor

from utils.config import config
from utils.logger import logger
from utils.checkpoint import Checkpoint
from .html_parser import HTMLParser
from .db_client import DatabaseClient


class CanLIIScraper:
    """CanLII 爬虫类"""
    
    def __init__(self, use_checkpoint=True):
        """
        初始化爬虫
        
        Args:
            use_checkpoint: 是否使用断点续传
        """
        # 使用 curl_cffi 的 Session
        self.session = requests.Session()
        
        # 基础 Headers - 尽量简化，让 impersonate 处理核心指纹
        self.session.headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "max-age=0",
            "Connection": "keep-alive",
            "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"macOS"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1"
        }
        
        # 预热 Session (获取 DataDome Cookie)
        self._warm_up_session()

        self.parser = HTMLParser()
        self.db_client = DatabaseClient()
        self.checkpoint = Checkpoint() if use_checkpoint else None
        
        self.stats = {
            'total': 0,
            'success': 0,
            'failed': 0,
            'skipped': 0
        }
    
    def _warm_up_session(self):
        """访问主页及相关路径以获取必要的 Cookie 和建立连接指纹"""
        try:
            logger.info("正在预热 Session (模拟真实访问)...")
            # 1. 模拟从 Google 搜索跳转或直接输入
            self.session.get(
                "https://www.canlii.org/en/",
                impersonate="chrome124",
                timeout=config.TIMEOUT
            )
            time.sleep(1)
            # 2. 模拟点击一些静态资源或次级页面
            self.session.get(
                "https://www.canlii.org/static/canlii/css/canlii.css",
                impersonate="chrome124",
                timeout=config.TIMEOUT
            )
            logger.info("Session 预热完成")
            time.sleep(2)
        except Exception as e:
            logger.warning(f"Session 预热失败: {e}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type(Exception) # curl_cffi exceptions catch-all
    )
    def _fetch_page(self, url: str) -> Optional[str]:
        """
        获取网页内容（带重试）
        
        Args:
            url: 页面URL
            
        Returns:
            Optional[str]: HTML内容或None
        """
        try:
            logger.debug(f"正在获取: {url}")
            
            # 更新 Referer 为 CanLII 以通过同站检查
            headers = self.session.headers.copy()
            if "canlii.org" in url:
                headers["Referer"] = "https://www.canlii.org/"
                headers["Sec-Fetch-Site"] = "same-origin"
            
            # 发送请求 (curl_cffi)
            response = self.session.get(
                url, 
                impersonate="chrome124",
                headers=headers,
                timeout=config.TIMEOUT
            )
            
            # curl_cffi 的 response 没有 raise_for_status，需要手动检查
            if response.status_code >= 400:
                # 记录详细错误
                if response.status_code == 403:
                    logger.error(f"访问被拒绝 (403): {url}")
                    logger.debug(f"Response Body: {response.text[:200]}...")
                elif response.status_code == 404:
                    logger.warning(f"页面不存在 (404): {url}")
                else:
                    logger.error(f"HTTP错误 ({response.status_code}): {url}")
                
                # 只有 404 不抛出异常，其他都重试
                if response.status_code == 404:
                    return None
                raise Exception(f"HTTP {response.status_code}")
            
            # 延迟以遵守速率限制
            time.sleep(config.REQUEST_DELAY)
            
            return response.text
            
        except Exception as e:
            logger.error(f"请求失败: {e}")
            raise
    
    def fetch_statute_list(self, index_url: str = None) -> List[Dict[str, str]]:
        """
        获取法规列表 (优先尝试 JSON API)
        
        Args:
            index_url: 法规索引页面的URL (可选，默认使用配置中的URL)
        
        Returns:
            List[Dict]: 法规列表
        """
        target_url = index_url if index_url else getattr(config, 'INDEX_URL', None)
        if not target_url and config.targets:
             target_url = config.targets[0]['url']
        
        if not target_url:
             logger.error("未指定目标 URL")
             return []

        logger.info(f"正在获取法规列表: {target_url}")
        
        # 1. 尝试 JSON API (/items)
        try:
            # 移除末尾斜杠并添加 /items
            api_url = target_url.rstrip('/') + '/items'
            logger.info(f"尝试 JSON API: {api_url}")
            
            # 更新 Headers 为 same-origin
            headers = self.session.headers.copy()
            headers["Referer"] = "https://www.canlii.org/"
            headers["Sec-Fetch-Site"] = "same-origin"
            
            response = self.session.get(
                api_url, 
                impersonate="chrome124",
                headers=headers,
                timeout=config.TIMEOUT
            )
            
            if response.status_code == 200:
                logger.info("JSON API 获取成功")
                try:
                    json_data = response.json()
                    return self.parser.parse_statute_list_json(json_data)
                except Exception as e:
                    logger.error(f"JSON 解析失败: {e}")
            else:
                logger.warning(f"JSON API 请求失败: {response.status_code}")
                
        except Exception as e:
            logger.warning(f"JSON API 尝试失败: {e}")

        # 2. 只有在 JSON 失败时才回退到 HTML
        logger.info("回退到 HTML 解析模式...")
        try:
            html_content = self._fetch_page(target_url)
            if not html_content:
                logger.error("获取法规列表失败 (HTML)")
                return []
            
            statutes = self.parser.parse_statute_list(html_content)
            
            logger.info(f"成功获取 {len(statutes)} 个法规")
            
            return statutes
            
        except Exception as e:
            logger.error(f"获取法规列表时出错: {e}")
            return []
    
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
            html_content = self._fetch_page(url)
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
                    # self.checkpoint.save() # SQLite 自动提交
                return True
            else:
                self.stats['failed'] += 1
                return False
                
        except Exception as e:
            logger.error(f"爬取法规时出错: {e}")
            logger.error(f"法规: {title}")
            self.stats['failed'] += 1
            return False
    
    def run(self, limit: Optional[int] = None, only_active: bool = False, target_url: Optional[str] = None, context: Optional[Dict] = None, stop_event: Optional[threading.Event] = None):
        """
        运行爬虫
        
        Args:
            limit: 限制爬取数量（用于测试）
            only_active: 是否只爬取有效的法规（如果为False，则会爬取并标记已废除的法规）
            target_url: 指定爬取的目标URL，如果为None则使用默认配置
            context: 抓取上下文，用于保存到 v3 数据库
            stop_event: 停止信号
        """
        logger.info("=" * 60)
        logger.info("CanLII 法规爬虫启动")
        logger.info("=" * 60)
        
        # 测试数据库连接
        if not self.db_client.test_connection():
            logger.error("数据库连接失败，程序终止")
            return
        
        # 获取法规列表
        # 如果指定了 target_url，则使用它，否则使用 config 中的默认值 (如果存在)
        # 注意: config.INDEX_URL 可能在后续被移除，建议总是传入 target_url
        url_to_use = target_url  
        if not url_to_use:
             # Backward compatibility
             url_to_use = getattr(config, 'INDEX_URL', None)
             
        if not url_to_use and config.targets:
             # Fallback to first target
             url_to_use = config.targets[0]['url']
             logger.info(f"使用默认目标: {config.targets[0]['name']}")

        if not url_to_use:
             logger.error("未指定目标 URL")
             return

        statutes = self.fetch_statute_list(index_url=url_to_use)
        if not statutes:
            logger.error("未获取到法规列表，程序终止")
            return
        
        # 过滤
        if only_active:
            statutes = [s for s in statutes if s.get('is_active', True)]
            logger.info(f"过滤后剩余 {len(statutes)} 个有效法规")
        
        # statutes = statutes[:limit]  <-- REMOVED: Limit by actual scrapes, not list size
        # logger.info(f"限制爬取数量为 {limit}")
        
        self.stats['total'] = len(statutes)
        
        # 1. 高性能批量过滤 (Pre-filtering)
        logger.info("正在执行高性能本地去重扫描...")
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
            logger.info(f"✨ 瞬时跳过: 发现 {self.stats['skipped']} 个已抓取的 URL，已直接从任务中剔除。")
        
        # 2. 检查用户设置的数量限制
        if limit and len(to_scrape) > limit:
            logger.info(f"根据用户设置的限制 (Limit: {limit})，仅抓取前 {limit} 条新法规。")
            to_scrape = to_scrape[:limit]
            
        if not to_scrape:
            logger.info("所有法规均已爬取或无新增内容。")
            self._print_stats()
            return

        # 3. 多线程抓取 (Concurrency)
        # 默认使用 3 个并发，既能提速又不会因压力过大触发 403
        max_workers = 3 
        logger.info(f"🚀 启动并发采集引擎 (Threads: {max_workers})...")
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交所有任务
            futures = []
            for i, statute in enumerate(to_scrape, 1):
                if stop_event and stop_event.is_set():
                    break
                
                # 提交任务
                future = executor.submit(self.scrape_statute, statute, context)
                futures.append(future)
            
            # 等待完成并监控停止信号
            for i, future in enumerate(futures, 1):
                if stop_event and stop_event.is_set():
                    logger.info("检测到停止信号，正在取消剩余任务...")
                    # 尝试停止还没开始的任务
                    for f in futures[i:]:
                        f.cancel()
                    break
                
                # 等待单个任务完成
                try:
                    future.result()
                    if i % 5 == 0 or i == len(futures):
                        logger.info(f"实时进度: [{i}/{len(to_scrape)}] (总进度: {self.stats['success'] + self.stats['failed'] + self.stats['skipped']}/{self.stats['total']})")
                except Exception as e:
                    logger.error(f"任务执行失败: {e}")
        
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
