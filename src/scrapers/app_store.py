"""
App Store 爬虫核心模块
"""
import asyncio
import logging
import random
import time
import re
from datetime import datetime
from typing import Dict, List, Optional
from playwright.async_api import async_playwright, Page, Browser

from .regions import region_manager, Region
from src.converters.currency import currency_converter
from src.converters.exchange_rate import exchange_rate_provider
from src.storage.database import db_manager
from config.settings import (
    APP_ID, APP_SLUG, SUBSCRIPTION_TYPE,
    SCRAPE_TIMEOUT, SCRAPE_RETRY_TIMES,
    SCRAPE_DELAY_MIN, SCRAPE_DELAY_MAX,
    HEADLESS, BROWSER_VIEWPORT, USER_AGENTS
)

logger = logging.getLogger(__name__)


class AppStoreScraper:
    """App Store 价格爬虫"""

    def __init__(self, app_id: str = None, app_slug: str = None):
        """
        初始化爬虫

        Args:
            app_id: App Store ID
            app_slug: 应用 URL slug
        """
        self.app_id = app_id or APP_ID
        self.app_slug = app_slug or APP_SLUG
        self.subscription_type = SUBSCRIPTION_TYPE
        self.timeout = SCRAPE_TIMEOUT
        self.retry_times = SCRAPE_RETRY_TIMES
        self.headless = HEADLESS
        self.viewport = BROWSER_VIEWPORT

        self.browser: Optional[Browser] = None
        self.playwright = None

    def _build_url(self, region: Region) -> str:
        """
        构建 App Store URL

        Args:
            region: 地区对象

        Returns:
            App Store URL
        """
        # URL 格式: https://apps.apple.com/{region_code}/app/{app_slug}/id{app_id}
        return f"https://apps.apple.com/{region.code}/app/{self.app_slug}/id{self.app_id}"

    async def _init_browser(self):
        """初始化浏览器"""
        if not self.playwright:
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(
                headless=self.headless
            )
            logger.info("浏览器已启动")

    async def _close_browser(self):
        """关闭浏览器"""
        if self.browser:
            await self.browser.close()
            self.browser = None
        if self.playwright:
            await self.playwright.stop()
            self.playwright = None
            logger.info("浏览器已关闭")

    async def _random_delay(self):
        """随机延迟"""
        delay = random.uniform(SCRAPE_DELAY_MIN, SCRAPE_DELAY_MAX)
        await asyncio.sleep(delay)

    async def _extract_price_from_page(self, page: Page, region: Region) -> Optional[Dict]:
        """
        从页面提取价格信息

        Args:
            page: Playwright Page 对象
            region: 地区对象

        Returns:
            价格信息字典，失败返回 None
        """
        try:
            # 等待页面加载
            await page.wait_for_load_state('networkidle', timeout=self.timeout)

            # 等待一下确保内容加载完成
            await asyncio.sleep(2)

            # 尝试多种选择器来查找价格信息
            price_text = None

            # 方法 1: 查找包含 "In-App Purchases" 的区域
            try:
                # 查找所有包含价格的元素
                # App Store 的价格通常在 button 或特定的 div 中
                price_selectors = [
                    'button[aria-label*="purchase"]',
                    'button[aria-label*="subscription"]',
                    'button:has-text("month")',
                    'button:has-text("year")',
                    '[class*="in-app-purchase"] button',
                    '[class*="iap"] button',
                    'li:has-text("Claude") button',
                    'button[type="button"]:has-text("month")',
                ]

                for selector in price_selectors:
                    try:
                        elements = await page.query_selector_all(selector)
                        for element in elements:
                            text = await element.inner_text()
                            # 检查是否包含价格信息
                            if re.search(r'[\d.,]+', text) and ('month' in text.lower() or self.subscription_type in text.lower()):
                                price_text = text
                                logger.debug(f"找到价格文本 (选择器: {selector}): {price_text}")
                                break
                        if price_text:
                            break
                    except Exception as e:
                        continue

            except Exception as e:
                logger.debug(f"方法 1 提取价格失败: {e}")

            # 方法 2: 使用正则表达式在整个页面内容中搜索
            if not price_text:
                try:
                    page_content = await page.content()
                    # 根据货币符号和数字模式搜索
                    currency_patterns = [
                        r'[\$€£¥₹₺₽₩]\s*[\d.,]+',  # 货币符号开头
                        r'[\d.,]+\s*[\$€£¥₹₺₽₩]',  # 货币符号结尾
                        r'[A-Z]{3}\s*[\d.,]+',  # 货币代码开头
                        r'[\d.,]+\s*[A-Z]{3}',  # 货币代码结尾
                    ]

                    for pattern in currency_patterns:
                        matches = re.findall(pattern, page_content)
                        if matches:
                            # 取第一个匹配
                            price_text = matches[0]
                            logger.debug(f"在页面内容中找到价格: {price_text}")
                            break

                except Exception as e:
                    logger.debug(f"方法 2 提取价格失败: {e}")

            # 方法 3: 截图保存以便调试
            if not price_text:
                try:
                    screenshot_path = f"data/debug_{region.code}_{int(time.time())}.png"
                    await page.screenshot(path=screenshot_path, full_page=True)
                    logger.info(f"未找到价格，已保存截图: {screenshot_path}")
                except Exception as e:
                    logger.debug(f"保存截图失败: {e}")

            # 解析价格
            if price_text:
                # 提取数字部分
                price_local = currency_converter.parse_price_string(price_text, region.currency)

                if price_local:
                    # 转换为美元
                    price_usd = currency_converter.convert(
                        price_local,
                        region.currency,
                        "USD"
                    )

                    if price_usd:
                        # 获取汇率
                        exchange_rate = exchange_rate_provider.get_rate(
                            region.currency,
                            "USD"
                        )

                        return {
                            "app_id": self.app_id,
                            "app_name": "Claude",
                            "region_code": region.code,
                            "region_name": region.name,
                            "region_name_cn": region.name_cn,
                            "currency": region.currency,
                            "price_local": price_local,
                            "price_usd": price_usd,
                            "exchange_rate": exchange_rate or 1.0,
                            "subscription_type": self.subscription_type,
                            "scrape_time": datetime.utcnow(),
                            "success": 1,
                            "error_message": None
                        }

            logger.warning(f"无法从页面提取价格信息: {region.code}")
            return None

        except Exception as e:
            logger.error(f"提取价格时发生错误: {e}")
            return None

    async def scrape_region(self, region: Region, retry: int = 0) -> Optional[Dict]:
        """
        爬取单个地区的价格

        Args:
            region: 地区对象
            retry: 当前重试次数

        Returns:
            价格信息字典，失败返回 None
        """
        url = self._build_url(region)
        logger.info(f"正在爬取 {region.name_cn} ({region.code}): {url}")

        try:
            # 确保浏览器已初始化
            await self._init_browser()

            # 创建新页面
            context = await self.browser.new_context(
                viewport=self.viewport,
                user_agent=random.choice(USER_AGENTS),
                locale=region.locale
            )
            page = await context.new_page()

            # 访问页面
            response = await page.goto(url, wait_until='domcontentloaded', timeout=self.timeout)

            if not response or response.status != 200:
                logger.warning(f"页面加载失败: {region.code}, 状态码: {response.status if response else 'None'}")
                await context.close()

                # 重试
                if retry < self.retry_times:
                    logger.info(f"重试 {region.code} ({retry + 1}/{self.retry_times})")
                    await self._random_delay()
                    return await self.scrape_region(region, retry + 1)
                return None

            # 提取价格
            price_data = await self._extract_price_from_page(page, region)

            await context.close()

            if price_data:
                logger.info(f"成功: {region.name_cn} - {price_data['price_local']} {price_data['currency']} = ${price_data['price_usd']:.2f} USD")
                return price_data
            else:
                # 重试
                if retry < self.retry_times:
                    logger.info(f"重试 {region.code} ({retry + 1}/{self.retry_times})")
                    await self._random_delay()
                    return await self.scrape_region(region, retry + 1)

                # 记录失败
                return {
                    "app_id": self.app_id,
                    "app_name": "Claude",
                    "region_code": region.code,
                    "region_name": region.name,
                    "region_name_cn": region.name_cn,
                    "currency": region.currency,
                    "price_local": 0.0,
                    "price_usd": 0.0,
                    "exchange_rate": 1.0,
                    "subscription_type": self.subscription_type,
                    "scrape_time": datetime.utcnow(),
                    "success": 0,
                    "error_message": "无法提取价格信息"
                }

        except Exception as e:
            logger.error(f"爬取失败: {region.code}, 错误: {e}")

            # 重试
            if retry < self.retry_times:
                logger.info(f"重试 {region.code} ({retry + 1}/{self.retry_times})")
                await self._random_delay()
                return await self.scrape_region(region, retry + 1)

            # 记录失败
            return {
                "app_id": self.app_id,
                "app_name": "Claude",
                "region_code": region.code,
                "region_name": region.name,
                "region_name_cn": region.name_cn,
                "currency": region.currency,
                "price_local": 0.0,
                "price_usd": 0.0,
                "exchange_rate": 1.0,
                "subscription_type": self.subscription_type,
                "scrape_time": datetime.utcnow(),
                "success": 0,
                "error_message": str(e)
            }

    async def scrape_all_regions(self, region_codes: List[str] = None,
                                 save_to_db: bool = True) -> List[Dict]:
        """
        爬取所有地区的价格

        Args:
            region_codes: 要爬取的地区代码列表，None 表示爬取所有地区
            save_to_db: 是否保存到数据库

        Returns:
            价格信息字典列表
        """
        # 获取要爬取的地区
        if region_codes:
            regions = [region_manager.get_region_by_code(code) for code in region_codes]
            regions = [r for r in regions if r]  # 移除 None
        else:
            regions = region_manager.get_all_regions()

        logger.info(f"开始爬取 {len(regions)} 个地区的价格")

        # 创建爬取日志
        log = db_manager.create_scrape_log({
            "start_time": datetime.utcnow(),
            "total_regions": len(regions),
            "status": "running"
        })

        # 初始化浏览器
        await self._init_browser()

        # 获取汇率（提前获取，避免每次都请求）
        logger.info("正在获取最新汇率...")
        exchange_rate_provider.get_rates(force_refresh=True)

        # 爬取所有地区
        results = []
        success_count = 0
        failed_count = 0

        try:
            for i, region in enumerate(regions, 1):
                logger.info(f"进度: {i}/{len(regions)}")

                # 爬取单个地区
                price_data = await self.scrape_region(region)

                if price_data:
                    results.append(price_data)

                    if price_data["success"]:
                        success_count += 1
                    else:
                        failed_count += 1

                    # 保存到数据库
                    if save_to_db:
                        try:
                            db_manager.save_price(price_data)
                        except Exception as e:
                            logger.error(f"保存价格数据失败: {e}")

                # 随机延迟
                if i < len(regions):
                    await self._random_delay()

            # 更新日志
            db_manager.update_scrape_log(log.id, {
                "end_time": datetime.utcnow(),
                "success_count": success_count,
                "failed_count": failed_count,
                "status": "completed"
            })

            logger.info(f"爬取完成! 成功: {success_count}, 失败: {failed_count}")

        except Exception as e:
            logger.error(f"爬取过程中发生错误: {e}")
            db_manager.update_scrape_log(log.id, {
                "end_time": datetime.utcnow(),
                "success_count": success_count,
                "failed_count": failed_count,
                "status": "failed",
                "error_message": str(e)
            })

        finally:
            # 关闭浏览器
            await self._close_browser()

        return results

    def scrape_all_regions_sync(self, region_codes: List[str] = None,
                                save_to_db: bool = True) -> List[Dict]:
        """
        同步版本的 scrape_all_regions（用于在非异步环境中调用）

        Args:
            region_codes: 要爬取的地区代码列表
            save_to_db: 是否保存到数据库

        Returns:
            价格信息字典列表
        """
        return asyncio.run(self.scrape_all_regions(region_codes, save_to_db))


if __name__ == "__main__":
    # 测试代码
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # 创建爬虫实例
    scraper = AppStoreScraper()

    # 测试爬取单个地区（美国）
    print("\n测试爬取美国地区:")
    results = scraper.scrape_all_regions_sync(region_codes=["us"], save_to_db=False)

    for result in results:
        print(f"\n地区: {result['region_name_cn']} ({result['region_code']})")
        print(f"货币: {result['currency']}")
        print(f"本地价格: {result['price_local']}")
        print(f"美元价格: ${result['price_usd']:.2f}")
        print(f"成功: {result['success']}")
