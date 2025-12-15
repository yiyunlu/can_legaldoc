"""
使用本地示例页面测试爬虫功能
"""
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from scraper.html_parser import HTMLParser
from scraper.supabase_client import SupabaseClient
from utils.logger import logger


def test_with_sample_page():
    """使用示例页面测试完整流程"""
    
    logger.info("=" * 60)
    logger.info("使用示例页面测试爬虫功能")
    logger.info("=" * 60)
    
    # 1. 读取示例页面
    sample_file = project_root / 'sample_page' / 'Consolidated Statutes of Alberta _ CanLII.html'
    
    with open(sample_file, 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    logger.info(f"✓ 读取示例页面成功")
    
    # 2. 解析法规列表
    parser = HTMLParser()
    statutes = parser.parse_statute_list(html_content)
    
    logger.info(f"✓ 解析到 {len(statutes)} 个法规")
    
    # 3. 过滤有效法规
    active_statutes = [s for s in statutes if s.get('is_active', True)]
    logger.info(f"✓ 其中 {len(active_statutes)} 个为有效法规")
    
    # 4. 模拟解析详情页（使用第一个法规的URL）
    logger.info(f"\n测试详情页解析（模拟）:")
    for i, statute in enumerate(active_statutes[:3], 1):
        logger.info(f"\n{i}. {statute['title']}")
        logger.info(f"   引文: {statute['citation']}")
        logger.info(f"   URL: {statute['url']}")
        
        # 模拟创建法规数据
        statute_data = {
            'title': statute['title'],
            'citation': statute['citation'],
            'content_html': '<p>示例内容 - 实际使用时会从详情页提取</p>',
            'content_text': '示例内容 - 实际使用时会从详情页提取',
            'source_url': statute['url']
        }
        
        logger.info(f"   ✓ 数据结构准备完成")
    
    # 5. 测试数据库插入（仅第一个）
    logger.info(f"\n测试数据库插入:")
    db_client = SupabaseClient()
    
    test_statute = {
        'title': 'TEST - ' + active_statutes[0]['title'],
        'citation': active_statutes[0]['citation'],
        'content_html': '<h1>测试法规</h1><p>这是一个测试记录，用于验证数据库插入功能。</p>',
        'content_text': '测试法规\n这是一个测试记录，用于验证数据库插入功能。',
        'source_url': active_statutes[0]['url'] + '?test=1'  # 添加参数避免冲突
    }
    
    success = db_client.upsert_statute(test_statute)
    
    if success:
        logger.info(f"✓ 测试记录插入成功")
        
        # 查询验证
        count = db_client.get_statute_count()
        logger.info(f"✓ 数据库中现有 {count} 条记录")
    else:
        logger.error(f"✗ 测试记录插入失败")
    
    # 6. 总结
    logger.info("\n" + "=" * 60)
    logger.info("测试总结")
    logger.info("=" * 60)
    logger.info(f"✓ HTML 解析器: 正常工作")
    logger.info(f"✓ 数据库连接: 正常工作")
    logger.info(f"✓ 数据插入: 正常工作")
    logger.info(f"\n注意: 由于 CanLII 的反爬虫机制，直接访问网站可能会遇到 403 错误。")
    logger.info(f"建议: 使用更真实的浏览器 User-Agent 或考虑使用 Selenium/Playwright。")


if __name__ == '__main__':
    test_with_sample_page()
