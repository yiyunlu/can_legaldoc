"""
断点续传模块 (SQLite 升级版)
保存和恢复爬取进度，支持海量数据去重
"""
import json
import sqlite3
import os
from pathlib import Path
from typing import Set, Dict
from .logger import logger


class Checkpoint:
    """断点管理类 (SQLite 实现)"""
    
    def __init__(self, db_name='checkpoint.db'):
        """
        初始化断点管理器
        
        Args:
            db_name: SQLite 数据库文件名
        """
        self.root_dir = Path(__file__).parent.parent
        self.db_path = self.root_dir / db_name
        self.json_path = self.root_dir / 'checkpoint.json'
        
        # 初始化数据库连接 (check_same_thread=False 允许在多线程爬虫中使用)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._init_table()
        
        # 自动执行迁移逻辑
        self._migrate_from_json()
    
    def _init_table(self):
        """初始化数据表"""
        try:
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS checkpoints (
                    url TEXT PRIMARY KEY,
                    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # 建立 URL 索引（虽然主键自带索引，但显式声明以示清晰）
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_url ON checkpoints(url)")
            self.conn.commit()
        except Exception as e:
            logger.error(f"初始化 SQLite 断点表失败: {e}")
    
    def _migrate_from_json(self):
        """从旧版 JSON 文件迁移数据"""
        if self.json_path.exists():
            try:
                logger.info(f"检测到旧版断点文件，正在执行 SQLite 迁移...")
                with open(self.json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    scraped_urls = data.get('scraped_urls', [])
                
                if scraped_urls:
                    # 批量插入以提升性能
                    self.conn.executemany(
                        "INSERT OR IGNORE INTO checkpoints (url) VALUES (?)",
                        [(url,) for url in scraped_urls]
                    )
                    self.conn.commit()
                    logger.info(f"成功迁移 {len(scraped_urls)} 条记录到 SQLite")
                
                # 迁移成功后，将旧文件重命名（保留作为备份，但不干扰以后加载）
                backup_path = self.json_path.with_suffix('.json.bak')
                self.json_path.rename(backup_path)
                logger.info(f"旧版断点文件已备份为: {backup_path.name}")
                
            except Exception as e:
                logger.error(f"迁移断点数据失败: {e}")

    def load(self):
        """兼容性方法：SQLite 模式下数据实时存储，无需手动 load"""
        pass
    
    def save(self):
        """兼容性方法：SQLite 模式下 add() 自动提交，无需手动 save"""
        pass
    
    def add(self, url: str):
        """
        添加已爬取的URL
        
        Args:
            url: 法规URL
        """
        try:
            self.conn.execute("INSERT OR IGNORE INTO checkpoints (url) VALUES (?)", (url,))
            self.conn.commit()
        except Exception as e:
            logger.error(f"添加断点失败: {url}, Error: {e}")
    
    def is_scraped(self, url: str) -> bool:
        """
        检查URL是否已爬取
        
        Args:
            url: 法规URL
            
        Returns:
            bool: 是否已爬取
        """
        try:
            cursor = self.conn.execute("SELECT 1 FROM checkpoints WHERE url = ? LIMIT 1", (url,))
            return cursor.fetchone() is not None
        except Exception as e:
            logger.error(f"查询断点失败: {url}, Error: {e}")
            return False
    
    def reset(self):
        """重置断点"""
        try:
            self.conn.execute("DELETE FROM checkpoints")
            self.conn.commit()
            logger.info("断点已重置")
        except Exception as e:
            logger.error(f"重置断点失败: {e}")
    
    def get_progress(self, total: int) -> dict:
        """
        获取进度信息
        
        Args:
            total: 总数
            
        Returns:
            dict: 进度信息
        """
        try:
            cursor = self.conn.execute("SELECT count(*) FROM checkpoints")
            scraped = cursor.fetchone()[0]
        except:
            scraped = 0
            
        remaining = total - scraped
        percentage = (scraped / total * 100) if total > 0 else 0
        
        return {
            'scraped': scraped,
            'remaining': remaining,
            'total': total,
            'percentage': percentage
        }

    def __del__(self):
        """关闭连接"""
        try:
            self.conn.close()
        except:
            pass
