"""
测试脚本
验证各个模块的基本功能
"""
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


def test_config():
    """测试配置模块"""
    print("=" * 60)
    print("测试配置模块")
    print("=" * 60)
    
    try:
        from utils.config import config
        
        print(f"✓ 配置模块加载成功")
        print(f"  - INDEX_URL: {config.INDEX_URL}")
        print(f"  - REQUEST_DELAY: {config.REQUEST_DELAY}")
        print(f"  - LOG_LEVEL: {config.LOG_LEVEL}")
        
        # 验证配置
        config.validate()
        print(f"✓ 配置验证通过")
        
        return True
    except Exception as e:
        print(f"✗ 配置模块测试失败: {e}")
        return False


def test_logger():
    """测试日志模块"""
    print("\n" + "=" * 60)
    print("测试日志模块")
    print("=" * 60)
    
    try:
        from utils.logger import logger
        
        logger.info("这是一条测试日志")
        print(f"✓ 日志模块工作正常")
        
        return True
    except Exception as e:
        print(f"✗ 日志模块测试失败: {e}")
        return False


def test_supabase_connection():
    """测试 Supabase 连接"""
    print("\n" + "=" * 60)
    print("测试 Supabase 连接")
    print("=" * 60)
    
    try:
        from scraper.supabase_client import SupabaseClient
        
        client = SupabaseClient()
        print(f"✓ Supabase 客户端创建成功")
        
        # 测试连接
        if client.test_connection():
            print(f"✓ 数据库连接测试通过")
            
            # 获取当前记录数
            count = client.get_statute_count()
            print(f"  - 当前数据库中有 {count} 条法规记录")
            
            return True
        else:
            print(f"✗ 数据库连接测试失败")
            return False
            
    except Exception as e:
        print(f"✗ Supabase 连接测试失败: {e}")
        return False


def test_html_parser():
    """测试 HTML 解析器"""
    print("\n" + "=" * 60)
    print("测试 HTML 解析器")
    print("=" * 60)
    
    try:
        from scraper.html_parser import HTMLParser
        
        # 读取示例页面
        sample_file = project_root / 'sample_page' / 'Consolidated Statutes of Alberta _ CanLII.html'
        
        if not sample_file.exists():
            print(f"✗ 示例文件不存在: {sample_file}")
            return False
        
        with open(sample_file, 'r', encoding='utf-8') as f:
            html_content = f.read()
        
        print(f"✓ 示例文件读取成功")
        
        # 解析法规列表
        parser = HTMLParser()
        statutes = parser.parse_statute_list(html_content)
        
        print(f"✓ 成功解析 {len(statutes)} 个法规")
        
        # 显示前3个
        print(f"\n前3个法规:")
        for i, statute in enumerate(statutes[:3], 1):
            print(f"  {i}. {statute['title']}")
            print(f"     引文: {statute['citation']}")
            print(f"     URL: {statute['url']}")
            print(f"     状态: {'有效' if statute.get('is_active') else '已废除'}")
        
        return True
        
    except Exception as e:
        print(f"✗ HTML 解析器测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("CanLII Alberta 爬虫 - 功能测试")
    print("=" * 60 + "\n")
    
    results = {
        '配置模块': test_config(),
        '日志模块': test_logger(),
        'HTML 解析器': test_html_parser(),
        'Supabase 连接': test_supabase_connection(),
    }
    
    # 总结
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)
    
    for name, result in results.items():
        status = "✓ 通过" if result else "✗ 失败"
        print(f"{name}: {status}")
    
    total = len(results)
    passed = sum(results.values())
    
    print(f"\n总计: {passed}/{total} 通过")
    
    if passed == total:
        print("\n✓ 所有测试通过！可以开始使用爬虫。")
        return 0
    else:
        print("\n✗ 部分测试失败，请检查配置和环境。")
        return 1


if __name__ == '__main__':
    sys.exit(main())
