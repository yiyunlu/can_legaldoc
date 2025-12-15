"""
Supabase 数据库客户端模块
处理与 Supabase 的所有交互
"""
from supabase import create_client, Client
from typing import Dict, Optional
from utils.config import config
from utils.logger import logger


class SupabaseClient:
    """Supabase 数据库客户端"""
    
    def __init__(self):
        """初始化 Supabase 客户端"""
        try:
            self.client: Client = create_client(
                config.SUPABASE_URL,
                config.SUPABASE_KEY
            )
            logger.info("Supabase 客户端初始化成功")
        except Exception as e:
            logger.error(f"Supabase 客户端初始化失败: {e}")
            raise
    
    def upsert_statute(self, statute_data: Dict) -> bool:
        """
        插入或更新法规记录
        
        Args:
            statute_data: 法规数据字典，包含:
                - title: 标题
                - citation: 引文
                - content_html: HTML内容
                - content_text: 纯文本内容
                - source_url: 来源URL
                - last_updated: 最后更新时间
        
        Returns:
            bool: 是否成功
        """
        try:
            # 使用 upsert 操作（基于 source_url 的唯一约束）
            response = self.client.table('ab_statutes').upsert(
                statute_data,
                on_conflict='source_url'
            ).execute()
            
            if response.data:
                logger.info(f"成功保存法规: {statute_data.get('title', 'Unknown')}")
                return True
            else:
                logger.warning(f"保存法规时无数据返回: {statute_data.get('title', 'Unknown')}")
                return False
                
        except Exception as e:
            logger.error(f"保存法规失败: {e}")
            logger.error(f"法规数据: {statute_data.get('title', 'Unknown')}")
            return False
    
    def get_statute_by_url(self, source_url: str) -> Optional[Dict]:
        """
        根据URL获取法规
        
        Args:
            source_url: 法规URL
            
        Returns:
            Optional[Dict]: 法规数据或None
        """
        try:
            response = self.client.table('ab_statutes').select('*').eq(
                'source_url', source_url
            ).execute()
            
            if response.data and len(response.data) > 0:
                return response.data[0]
            return None
            
        except Exception as e:
            logger.error(f"查询法规失败: {e}")
            return None
    
    def get_all_statutes(self) -> list:
        """
        获取所有法规
        
        Returns:
            list: 法规列表
        """
        try:
            response = self.client.table('ab_statutes').select('*').execute()
            return response.data if response.data else []
        except Exception as e:
            logger.error(f"获取所有法规失败: {e}")
            return []
    
    def get_statute_count(self) -> int:
        """
        获取法规总数
        
        Returns:
            int: 法规数量
        """
        try:
            response = self.client.table('ab_statutes').select(
                'id', count='exact'
            ).execute()
            return response.count if response.count else 0
        except Exception as e:
            logger.error(f"获取法规数量失败: {e}")
            return 0
    
    def test_connection(self) -> bool:
        """
        测试数据库连接
        
        Returns:
            bool: 连接是否成功
        """
        try:
            # 尝试查询表
            response = self.client.table('ab_statutes').select(
                'id', count='exact'
            ).limit(1).execute()
            logger.info("数据库连接测试成功")
            return True
        except Exception as e:
            logger.error(f"数据库连接测试失败: {e}")
            return False
