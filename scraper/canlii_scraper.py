"""
CanLII 爬虫核心模块
处理网页请求、解析和数据存储
"""
import requests
import time
from typing import List, Dict, Optional
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from requests.exceptions import RequestException, Timeout, HTTPError

from utils.config import config
from utils.logger import logger
from utils.checkpoint import Checkpoint
from .html_parser import HTMLParser
from .supabase_client import SupabaseClient


class CanLIIScraper:
    """CanLII 爬虫类"""
    
    def __init__(self, use_checkpoint=True):
        """
        初始化爬虫
        
        Args:
            use_checkpoint: 是否使用断点续传
        """
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': config.USER_AGENT,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        })
        
        self.parser = HTMLParser()
        self.db_client = SupabaseClient()
        self.checkpoint = Checkpoint() if use_checkpoint else None
        
        self.stats = {
            'total': 0,
            'success': 0,
            'failed': 0,
            'skipped': 0
        }
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((RequestException, Timeout))
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
            response = self.session.get(url, timeout=config.TIMEOUT)
            response.raise_for_status()
            
            # 延迟以遵守速率限制
            time.sleep(config.REQUEST_DELAY)
            
            return response.text
            
        except HTTPError as e:
            if e.response.status_code == 403:
                logger.error(f"访问被拒绝 (403): {url}")
                logger.error("可能被反爬虫机制拦截，请检查 User-Agent 或增加延迟")
            elif e.response.status_code == 404:
                logger.warning(f"页面不存在 (404): {url}")
            else:
                logger.error(f"HTTP错误 ({e.response.status_code}): {url}")
            raise
            
        except Timeout:
            logger.error(f"请求超时: {url}")
            raise
            
        except RequestException as e:
            logger.error(f"请求失败: {e}")
            raise
    
    def fetch_statute_list(self) -> List[Dict[str, str]]:
        """
        获取法规列表
        
        Returns:
            List[Dict]: 法规列表
        """
        logger.info(f"正在获取法规列表: {config.INDEX_URL}")
        
        try:
            html_content = self._fetch_page(config.INDEX_URL)
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
        logger.info("CanLII Alberta 法规爬虫启动")
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
