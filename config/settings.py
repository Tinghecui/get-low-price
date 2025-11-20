"""
系统配置文件
"""
import os
from pathlib import Path

# 项目根目录
BASE_DIR = Path(__file__).resolve().parent.parent

# 数据目录
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

# 数据库配置
DATABASE_PATH = DATA_DIR / "prices.db"
DATABASE_URL = f"sqlite:///{DATABASE_PATH}"

# Claude App Store ID
APP_ID = "6473753684"  # Claude by Anthropic 的实际 App Store ID
APP_NAME = "claude-by-anthropic"
APP_SLUG = "claude-by-anthropic"  # URL 中的应用名称
SUBSCRIPTION_TYPE = "monthly"  # 订阅类型: monthly, yearly

# 爬虫配置
SCRAPE_TIMEOUT = 30000  # 超时时间（毫秒）
SCRAPE_RETRY_TIMES = 3  # 重试次数
SCRAPE_DELAY_MIN = 2  # 最小延迟（秒）
SCRAPE_DELAY_MAX = 5  # 最大延迟（秒）

# 浏览器配置
HEADLESS = True  # 是否使用无头浏览器
BROWSER_VIEWPORT = {"width": 1920, "height": 1080}

# 代理配置
USE_PROXY = False  # 是否使用代理
PROXY_URL = os.getenv("PROXY_URL", None)  # 代理地址

# 汇率 API 配置
EXCHANGE_RATE_API = "https://api.exchangerate-api.com/v4/latest/USD"
EXCHANGE_RATE_CACHE_HOURS = 24  # 汇率缓存时间（小时）

# 定时任务配置
SCHEDULE_ENABLED = False  # 是否启用定时任务
SCHEDULE_HOUR = 9  # 每天运行时间（小时）
SCHEDULE_MINUTE = 0  # 每天运行时间（分钟）

# 日志配置
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_FILE = DATA_DIR / "scraper.log"

# 价格分析配置
SHOW_TOP_N_CHEAPEST = 10  # 显示最便宜的前 N 个地区
PRICE_DIFFERENCE_THRESHOLD = 0.05  # 价格差异阈值（5%）

# User Agent
USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]
