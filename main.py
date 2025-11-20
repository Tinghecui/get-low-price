#!/usr/bin/env python3
"""
App Store Price Scraper - 主程序入口
用于爬取全球各国 App Store 中 Claude Max 的订阅价格
"""
import argparse
import logging
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent))

from src.scrapers.app_store import AppStoreScraper
from src.analyzers.price_analyzer import PriceAnalyzer
from src.scheduler.tasks import PriceScraperScheduler
from config.settings import LOG_LEVEL, LOG_FORMAT, LOG_FILE

# 配置日志
def setup_logging(verbose: bool = False):
    """设置日志配置"""
    level = logging.DEBUG if verbose else getattr(logging, LOG_LEVEL)

    # 创建日志目录
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    # 配置日志处理器
    handlers = [
        logging.StreamHandler(sys.stdout),  # 控制台输出
        logging.FileHandler(LOG_FILE, encoding='utf-8')  # 文件输出
    ]

    logging.basicConfig(
        level=level,
        format=LOG_FORMAT,
        handlers=handlers
    )


def cmd_scrape(args):
    """执行爬取命令"""
    logger = logging.getLogger(__name__)
    logger.info("开始爬取 App Store 价格...")

    scraper = AppStoreScraper()

    # 解析地区代码
    region_codes = None
    if args.regions:
        region_codes = [r.strip() for r in args.regions.split(',')]
        logger.info(f"爬取指定地区: {region_codes}")
    else:
        logger.info("爬取所有地区")

    # 执行爬取
    results = scraper.scrape_all_regions_sync(
        region_codes=region_codes,
        save_to_db=not args.no_save
    )

    # 显示结果
    success_count = sum(1 for r in results if r.get('success', 0) == 1)
    failed_count = len(results) - success_count

    logger.info(f"\n爬取完成!")
    logger.info(f"  总计: {len(results)} 个地区")
    logger.info(f"  成功: {success_count}")
    logger.info(f"  失败: {failed_count}")

    # 如果指定了分析选项，则显示分析结果
    if args.analyze and success_count > 0:
        logger.info("\n正在分析价格...")
        analyzer = PriceAnalyzer()
        analyzer.print_analysis()


def cmd_analyze(args):
    """执行分析命令"""
    logger = logging.getLogger(__name__)
    logger.info("开始分析价格数据...")

    analyzer = PriceAnalyzer()

    # 显示分析结果
    analyzer.print_analysis()

    # 如果指定了与美国对比
    if args.compare_us:
        logger.info("\n与美国价格对比:")
        comparison = analyzer.compare_with_us()

        if comparison:
            us_price = comparison['us_price']
            logger.info(f"\n美国价格: ${us_price['price_usd']:.2f} USD")
            logger.info(f"比美国便宜的地区数: {comparison['cheaper_count']}")
            logger.info(f"比美国贵的地区数: {comparison['more_expensive_count']}")

            # 显示前 5 个比美国便宜的地区
            cheaper = [c for c in comparison['comparisons'] if c['is_cheaper']][:5]
            if cheaper:
                logger.info("\n前 5 个比美国便宜的地区:")
                for c in cheaper:
                    logger.info(f"  {c['region_name_cn']:15} ${c['price_usd']:7.2f} (节省 ${-c['diff_vs_us']:.2f}, {-c['diff_percentage']:.1f}%)")


def cmd_schedule(args):
    """执行定时任务命令"""
    logger = logging.getLogger(__name__)
    logger.info("启动定时任务调度器...")

    scheduler = PriceScraperScheduler(hour=args.hour, minute=args.minute)

    logger.info(f"定时任务配置: 每天 {args.hour:02d}:{args.minute:02d} 运行")
    logger.info("按 Ctrl+C 停止\n")

    # 如果指定立即运行
    if args.run_now:
        logger.info("立即运行一次任务...")
        scheduler.scrape_and_analyze()

    scheduler.start()


def cmd_list_regions(args):
    """列出所有支持的地区"""
    from src.scrapers.regions import region_manager

    regions = region_manager.get_all_regions()

    print(f"\n支持的地区列表 (共 {len(regions)} 个):")
    print(f"{'代码':<6} {'国家/地区':<20} {'英文名称':<25} {'货币':<6}")
    print("-" * 60)

    for region in regions:
        print(f"{region.code:<6} {region.name_cn:<20} {region.name:<25} {region.currency:<6}")

    print()


def cmd_test(args):
    """测试命令 - 爬取单个地区进行测试"""
    logger = logging.getLogger(__name__)

    test_region = args.region or "us"
    logger.info(f"测试爬取地区: {test_region}")

    scraper = AppStoreScraper()
    results = scraper.scrape_all_regions_sync(
        region_codes=[test_region],
        save_to_db=False
    )

    if results:
        result = results[0]
        logger.info("\n测试结果:")
        logger.info(f"  地区: {result['region_name_cn']} ({result['region_code']})")
        logger.info(f"  货币: {result['currency']}")
        logger.info(f"  本地价格: {result['price_local']}")
        logger.info(f"  美元价格: ${result['price_usd']:.2f}")
        logger.info(f"  成功: {'是' if result['success'] else '否'}")
        if result.get('error_message'):
            logger.error(f"  错误信息: {result['error_message']}")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='App Store Price Scraper - Claude Max 订阅价格爬虫',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 爬取所有地区价格
  python main.py scrape

  # 爬取指定地区
  python main.py scrape -r us,cn,jp

  # 爬取并分析
  python main.py scrape -a

  # 仅分析已有数据
  python main.py analyze

  # 与美国价格对比
  python main.py analyze --compare-us

  # 启动定时任务（每天 9:00）
  python main.py schedule --hour 9 --minute 0

  # 列出所有支持的地区
  python main.py list-regions

  # 测试爬取（美国）
  python main.py test -r us
        """
    )

    parser.add_argument('-v', '--verbose', action='store_true', help='详细输出模式')

    subparsers = parser.add_subparsers(dest='command', help='可用命令')

    # scrape 命令
    scrape_parser = subparsers.add_parser('scrape', help='爬取价格')
    scrape_parser.add_argument('-r', '--regions', help='指定地区代码，用逗号分隔 (如: us,cn,jp)')
    scrape_parser.add_argument('-a', '--analyze', action='store_true', help='爬取后立即分析')
    scrape_parser.add_argument('--no-save', action='store_true', help='不保存到数据库')
    scrape_parser.set_defaults(func=cmd_scrape)

    # analyze 命令
    analyze_parser = subparsers.add_parser('analyze', help='分析价格数据')
    analyze_parser.add_argument('--compare-us', action='store_true', help='与美国价格对比')
    analyze_parser.set_defaults(func=cmd_analyze)

    # schedule 命令
    schedule_parser = subparsers.add_parser('schedule', help='启动定时任务')
    schedule_parser.add_argument('--hour', type=int, default=9, help='每天运行的小时 (0-23)')
    schedule_parser.add_argument('--minute', type=int, default=0, help='每天运行的分钟 (0-59)')
    schedule_parser.add_argument('--run-now', action='store_true', help='启动时立即运行一次')
    schedule_parser.set_defaults(func=cmd_schedule)

    # list-regions 命令
    list_parser = subparsers.add_parser('list-regions', help='列出所有支持的地区')
    list_parser.set_defaults(func=cmd_list_regions)

    # test 命令
    test_parser = subparsers.add_parser('test', help='测试爬取单个地区')
    test_parser.add_argument('-r', '--region', default='us', help='要测试的地区代码 (默认: us)')
    test_parser.set_defaults(func=cmd_test)

    # 解析参数
    args = parser.parse_args()

    # 如果没有指定命令，显示帮助
    if not args.command:
        parser.print_help()
        sys.exit(0)

    # 设置日志
    setup_logging(args.verbose)

    # 执行命令
    try:
        args.func(args)
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("\n\n程序被用户中断")
        sys.exit(0)
    except Exception as e:
        logging.getLogger(__name__).error(f"程序执行出错: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
