"""
配置管理模块
从环境变量加载配置
"""
import os
import json
from dotenv import load_dotenv
from pathlib import Path
from typing import List, Dict

# 加载 .env 文件
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(dotenv_path=env_path)


class Config:
    """配置类"""
    
    # 配置文件路径
    CONFIG_FILE = Path(__file__).parent.parent / 'config.json'

    # Supabase 配置
    SUPABASE_URL = os.getenv('SUPABASE_URL')
    SUPABASE_KEY = os.getenv('SUPABASE_KEY')
    
    # 爬虫配置
    REQUEST_DELAY = float(os.getenv('REQUEST_DELAY', '1.5'))
    MAX_RETRIES = int(os.getenv('MAX_RETRIES', '3'))
    TIMEOUT = int(os.getenv('TIMEOUT', '30'))
    
    # 日志配置
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    
    # CanLII URLs
    BASE_URL = 'https://www.canlii.org'
    # 默认目标 - 为了向后兼容，初始化时如果没有 config.json，可以使用这个
    DEFAULT_TARGETS = [
        {
            "province": "ab",
            "type": "statutes",
            "url": "https://www.canlii.org/ab/laws/stat",
            "name": "Alberta Statutes"
        }
    ]
    
    # User Agent
    USER_AGENT = (
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/120.0.0.0 Safari/537.36'
    )
    
    # Default sources for multi-source architecture
    DEFAULT_SOURCES = [
        {
            "source_type": "justice_canada_xml",
            "name": "Federal Legislation (XML)",
            "jurisdiction": "ca",
            "category": "Legislation",
            "enabled": True,
            "params": {}
        },
        {
            "source_type": "bc_laws_api",
            "name": "BC Legislation (CiviX API)",
            "jurisdiction": "bc",
            "category": "Legislation",
            "enabled": True,
            "params": {}
        },
        {
            "source_type": "a2aj_case_law",
            "name": "A2AJ Case Law (Hugging Face)",
            "jurisdiction": "multi",
            "category": "Case Law",
            "enabled": True,
            "params": {"dataset_name": "a2aj/canadian-case-law", "streaming": True}
        }
    ]

    def __init__(self):
        self.targets = self.load_targets()
        self.sources = self.load_sources()

    def load_targets(self) -> List[Dict]:
        """从文件加载目标配置，如果不存在则使用默认值 (legacy CanLII targets)"""
        if self.CONFIG_FILE.exists():
            try:
                with open(self.CONFIG_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get('targets', self.DEFAULT_TARGETS)
            except Exception as e:
                print(f"Error loading config file: {e}")
                return self.DEFAULT_TARGETS
        return self.DEFAULT_TARGETS

    def load_sources(self) -> List[Dict]:
        """加载多源配置 (new multi-source architecture)"""
        if self.CONFIG_FILE.exists():
            try:
                with open(self.CONFIG_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get('sources', self.DEFAULT_SOURCES)
            except Exception as e:
                print(f"Error loading sources from config: {e}")
                return self.DEFAULT_SOURCES
        return self.DEFAULT_SOURCES

    def save_targets(self, targets: List[Dict]):
        """保存目标配置到文件"""
        self.targets = targets
        self._save_config()

    def save_sources(self, sources: List[Dict]):
        """保存多源配置到文件"""
        self.sources = sources
        self._save_config()

    def _save_config(self):
        """Save both targets and sources to config.json"""
        try:
            with open(self.CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump({
                    'targets': self.targets,
                    'sources': self.sources,
                }, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving config file: {e}")
            raise e

    @classmethod
    def validate(cls):
        """验证必需的配置项"""
        if not cls.SUPABASE_URL:
            raise ValueError("SUPABASE_URL 未设置")
        if not cls.SUPABASE_KEY:
            raise ValueError("SUPABASE_KEY 未设置")
        
        return True


# 导出配置实例
config = Config()
