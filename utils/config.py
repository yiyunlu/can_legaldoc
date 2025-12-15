"""
配置管理模块
从环境变量加载配置
"""
import os
from dotenv import load_dotenv
from pathlib import Path

# 加载 .env 文件
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(dotenv_path=env_path)


class Config:
    """配置类"""
    
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
    INDEX_URL = 'https://www.canlii.org/ab/laws/stat'
    
    # User Agent
    USER_AGENT = (
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/120.0.0.0 Safari/537.36'
    )
    
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
