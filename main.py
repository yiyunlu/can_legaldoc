"""
CanLII Alberta 法规采集器
主入口文件

使用方法:
    python main.py                    # 爬取所有法规
    python main.py --limit 10         # 只爬取前10个法规（测试用）
    python main.py --reset            # 重置断点，从头开始
    python main.py --no-checkpoint    # 不使用断点功能
    python main.py --include-inactive # 包括已废除的法规
"""
import argparse
import sys
from scraper.canlii_scraper import CanLIIScraper
from utils.config import config
from utils.logger import logger


def parse_arguments():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description='CanLII Alberta 法规采集器',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python main.py                    # 爬取所有有效法规
  python main.py --limit 5          # 只爬取前5个法规（测试）
  python main.py --reset            # 重置断点，从头开始
  python main.py --include-inactive # 包括已废除的法规
        """
    )
    
    parser.add_argument(
        '--limit',
        type=int,
        default=None,
        help='限制爬取数量（用于测试）'
    )
    
    parser.add_argument(
        '--reset',
        action='store_true',
        help='重置断点，从头开始爬取'
    )
    
    parser.add_argument(
        '--no-checkpoint',
        action='store_true',
        help='不使用断点功能'
    )
    
    parser.add_argument(
        '--include-inactive',
        action='store_true',
        help='包括已废除/未生效的法规'
    )
    
    return parser.parse_args()


def main():
    """主函数"""
    # 解析参数
    args = parse_arguments()
    
    try:
        # 验证配置
        config.validate()
        
        # 创建爬虫实例
        use_checkpoint = not args.no_checkpoint
        scraper = CanLIIScraper(use_checkpoint=use_checkpoint)
        
        # 重置断点（如果需要）
        if args.reset and scraper.checkpoint:
            logger.info("正在重置断点...")
            scraper.checkpoint.reset()
        
        # 运行爬虫
        scraper.run(
            limit=args.limit,
            only_active=not args.include_inactive
        )
        
        logger.info("程序执行完成")
        
    except ValueError as e:
        logger.error(f"配置错误: {e}")
        logger.error("请检查 .env 文件中的配置")
        sys.exit(1)
        
    except KeyboardInterrupt:
        logger.info("\n程序被用户中断")
        sys.exit(0)
        
    except Exception as e:
        logger.error(f"程序执行出错: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
