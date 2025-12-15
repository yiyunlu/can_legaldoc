"""
断点续传模块
保存和恢复爬取进度
"""
import json
from pathlib import Path
from typing import Set
from .logger import logger


class Checkpoint:
    """断点管理类"""
    
    def __init__(self, checkpoint_file='checkpoint.json'):
        """
        初始化断点管理器
        
        Args:
            checkpoint_file: 断点文件路径
        """
        self.checkpoint_file = Path(__file__).parent.parent / checkpoint_file
        self.scraped_urls: Set[str] = set()
        self.load()
    
    def load(self):
        """从文件加载断点"""
        if self.checkpoint_file.exists():
            try:
                with open(self.checkpoint_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.scraped_urls = set(data.get('scraped_urls', []))
                logger.info(f"加载断点: 已爬取 {len(self.scraped_urls)} 个法规")
            except Exception as e:
                logger.error(f"加载断点失败: {e}")
                self.scraped_urls = set()
        else:
            logger.info("未找到断点文件，从头开始")
    
    def save(self):
        """保存断点到文件"""
        try:
            data = {
                'scraped_urls': list(self.scraped_urls),
                'count': len(self.scraped_urls)
            }
            with open(self.checkpoint_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.debug(f"保存断点: {len(self.scraped_urls)} 个URL")
        except Exception as e:
            logger.error(f"保存断点失败: {e}")
    
    def add(self, url: str):
        """
        添加已爬取的URL
        
        Args:
            url: 法规URL
        """
        self.scraped_urls.add(url)
    
    def is_scraped(self, url: str) -> bool:
        """
        检查URL是否已爬取
        
        Args:
            url: 法规URL
            
        Returns:
            bool: 是否已爬取
        """
        return url in self.scraped_urls
    
    def reset(self):
        """重置断点"""
        self.scraped_urls = set()
        if self.checkpoint_file.exists():
            self.checkpoint_file.unlink()
        logger.info("断点已重置")
    
    def get_progress(self, total: int) -> dict:
        """
        获取进度信息
        
        Args:
            total: 总数
            
        Returns:
            dict: 进度信息
        """
        scraped = len(self.scraped_urls)
        remaining = total - scraped
        percentage = (scraped / total * 100) if total > 0 else 0
        
        return {
            'scraped': scraped,
            'remaining': remaining,
            'total': total,
            'percentage': percentage
        }
