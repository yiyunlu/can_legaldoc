"""
Supabase 数据库客户端模块
处理与 Supabase 的所有交互
"""
import hashlib
from supabase import create_client, Client
from typing import Dict, Optional, List
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
    
    def upsert_document_v3(self, doc_data: Dict) -> bool:
        """
        v3.0 架构下的文档插入/更新逻辑
        包含 documents 元数据更新和 document_versions 内容版本控制
        
        Args:
            doc_data: 包含:
                - title, citation, source_url, content_html, content_text
                - jurisdiction_code, category, target_id (可选)
                - metadata (可选)
        """
        try:
            source_url = doc_data.get('source_url')
            if not source_url:
                logger.error("缺失 source_url，无法保存文档")
                return False

            # 1. 准备 documents 表数据
            document_entry = {
                "title": doc_data.get('title'),
                "citation": doc_data.get('citation'),
                "source_url": source_url,
                "jurisdiction_code": doc_data.get('jurisdiction_code', 'ab'),
                "category": doc_data.get('category', 'Legislation'),
                "target_id": doc_data.get('target_id'),
                "is_active": doc_data.get('is_active', True),
                "metadata": doc_data.get('metadata', {}),
                "updated_at": "now()"
            }
            # v4 multi-source fields — added if columns exist in DB
            v4_fields = {}
            if doc_data.get('source_type'):
                v4_fields['source_type'] = doc_data['source_type']
            if doc_data.get('document_type'):
                v4_fields['document_type'] = doc_data['document_type']

            # 2. Upsert documents (try with v4 fields first, fallback without)
            entry_with_v4 = {**document_entry, **v4_fields}
            try:
                doc_res = self.client.table('documents').upsert(
                    entry_with_v4, on_conflict='source_url'
                ).execute()
            except Exception as v4_err:
                if 'PGRST204' in str(v4_err) or 'column' in str(v4_err).lower():
                    # v4 columns not yet added — retry without them
                    if not hasattr(self, '_v4_warned'):
                        logger.warning("v4 columns (source_type/document_type) not in DB yet, saving without them")
                        self._v4_warned = True
                    doc_res = self.client.table('documents').upsert(
                        document_entry, on_conflict='source_url'
                    ).execute()
                else:
                    raise
            
            if not doc_res.data:
                logger.error(f"Documents 表 Upsert 失败: {source_url}")
                return False
            
            document_id = doc_res.data[0]['id']

            # 3. 处理版本控制
            content_text = doc_data.get('content_text', '')
            content_html = doc_data.get('content_html', '')
            # 计算内容哈希 (SHA-256)
            content_hash = hashlib.sha256(content_text.encode('utf-8')).hexdigest()

            # 检查最新版本
            latest_ver_res = self.client.table('document_versions').select('*').eq(
                'document_id', document_id
            ).eq('is_latest', True).execute()

            should_create_version = True
            if latest_ver_res.data:
                latest_ver = latest_ver_res.data[0]
                if latest_ver.get('content_hash') == content_hash:
                    logger.info(f"内容未发生变化，跳过版本创建: {doc_data.get('title')}")
                    should_create_version = False
                else:
                    # 将旧版本标记为非最新
                    self.client.table('document_versions').update(
                        {'is_latest': False}
                    ).eq('id', latest_ver['id']).execute()

            # 4. 创建新版本
            if should_create_version:
                version_number = (latest_ver.get('version_number', 0) + 1) if latest_ver_res.data else 1
                version_entry = {
                    "document_id": document_id,
                    "content_html": content_html,
                    "content_text": content_text,
                    "content_hash": content_hash,
                    "version_number": version_number,
                    "is_latest": True,
                    "scraped_at": "now()"
                }
                self.client.table('document_versions').insert(version_entry).execute()
                logger.info(f"成功保存 v{version_number} 版本: {doc_data.get('title')}")

            return True

        except Exception as e:
            logger.error(f"v3.0 异步保存文档失败: {e}")
            return False

    def upsert_statute(self, statute_data: Dict) -> bool:
        """
        [DEPRECATED] 向后兼容旧方法的别名
        """
        return self.upsert_document_v3(statute_data)
    
    def get_statute_by_url(self, source_url: str) -> Optional[Dict]:
        """
        从 v3 架构根据 URL 获取文档
        """
        try:
            response = self.client.table('documents').select('*').eq(
                'source_url', source_url
            ).execute()
            
            if response.data:
                return response.data[0]
            return None
            
        except Exception as e:
            logger.error(f"查询文档失败: {e}")
            return None
    
    def update_document_status(self, source_url: str, is_active: bool) -> bool:
        """
        仅更新文档的活跃状态
        
        Args:
            source_url: 文档URL
            is_active: 是否活跃
        Returns:
            bool: 是否成功
        """
        try:
            res = self.client.table('documents').update({
                "is_active": is_active,
                "updated_at": "now()"
            }).eq("source_url", source_url).execute()
            return len(res.data) > 0
        except Exception as e:
            logger.error(f"更新文档状态失败: {e}")
            return False
    
    def get_all_statutes(self) -> list:
        """
        获取所有文档 (v3)
        
        Returns:
            list: 文档列表
        """
        try:
            response = self.client.table('documents').select('*').execute()
            return response.data if response.data else []
        except Exception as e:
            logger.error(f"获取所有文档失败: {e}")
            return []
    
    def get_statute_count(self) -> int:
        """
        获取文档总数 (v3)
        
        Returns:
            int: 数量
        """
        try:
            response = self.client.table('documents').select(
                'id', count='exact'
            ).execute()
            return response.count if response.count else 0
        except Exception as e:
            logger.error(f"获取文档数量失败: {e}")
            return 0
    
    def test_connection(self) -> bool:
        """
        测试数据库连接
        
        Returns:
            bool: 连接是否成功
        """
        try:
            # 尝试查询 documents 表
            self.client.table('documents').select(
                'id'
            ).limit(1).execute()
            logger.info("数据库连接测试成功 (v3)")
            return True
        except Exception as e:
            logger.error(f"数据库连接测试失败: {e}")
            return False
