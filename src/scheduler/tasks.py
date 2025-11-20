"""
定时任务调度器
"""
import logging
from datetime import datetime
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from src.scrapers.app_store import AppStoreScraper
from src.analyzers.price_analyzer import PriceAnalyzer
from config.settings import SCHEDULE_HOUR, SCHEDULE_MINUTE

logger = logging.getLogger(__name__)


class PriceScraperScheduler:
    """价格爬虫调度器"""

    def __init__(self, hour: int = None, minute: int = None):
        """
        初始化调度器

        Args:
            hour: 每天运行的小时（0-23）
            minute: 每天运行的分钟（0-59）
        """
        self.hour = hour if hour is not None else SCHEDULE_HOUR
        self.minute = minute if minute is not None else SCHEDULE_MINUTE
        self.scheduler = BlockingScheduler()
        self.scraper = AppStoreScraper()
        self.analyzer = PriceAnalyzer()

    def scrape_and_analyze(self):
        """爬取并分析价格（定时任务函数）"""
        logger.info("=" * 80)
        logger.info(f"开始定时任务: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("=" * 80)

        try:
            # 爬取所有地区价格
            logger.info("正在爬取所有地区的价格...")
            results = self.scraper.scrape_all_regions_sync(save_to_db=True)

            # 分析价格
            logger.info("正在分析价格...")
            self.analyzer.print_analysis()

            logger.info("定时任务完成!")

        except Exception as e:
            logger.error(f"定时任务执行失败: {e}", exc_info=True)

    def start(self):
        """启动调度器"""
        # 添加定时任务（每天指定时间运行）
        trigger = CronTrigger(hour=self.hour, minute=self.minute)
        self.scheduler.add_job(
            self.scrape_and_analyze,
            trigger=trigger,
            id='scrape_prices',
            name='爬取 App Store 价格',
            replace_existing=True
        )

        logger.info(f"定时任务已配置: 每天 {self.hour:02d}:{self.minute:02d} 运行")
        logger.info("调度器启动中...")

        # 可选：启动时立即运行一次
        # logger.info("立即运行一次任务...")
        # self.scrape_and_analyze()

        try:
            self.scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            logger.info("调度器已停止")
            self.scheduler.shutdown()

    def stop(self):
        """停止调度器"""
        logger.info("正在停止调度器...")
        self.scheduler.shutdown()
        logger.info("调度器已停止")


if __name__ == "__main__":
    # 测试代码
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # 创建调度器（每天 9:00 运行）
    scheduler = PriceScraperScheduler(hour=9, minute=0)

    # 启动调度器
    print("\n启动定时任务调度器...")
    print(f"任务将在每天 {scheduler.hour:02d}:{scheduler.minute:02d} 运行")
    print("按 Ctrl+C 停止\n")

    scheduler.start()
