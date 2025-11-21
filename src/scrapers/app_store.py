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
        从页面提取价格信息（提取所有价格并返回最高的）

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

            # 用于存储所有找到的价格
            all_prices = []

            # 方法 1: 滚动到 "In-App Purchases" 部分并提取价格
            try:
                logger.info(f"尝试查找 In-App Purchases 部分...")

                # 尝试多种可能的标题文本（不同语言）
                iap_heading_texts = [
                    'In-App Purchases',
                    'App 内购买项目',  # 中文
                    'Compras no app',  # 葡萄牙语
                    'Achats intégrés',  # 法语
                    'In-App-Käufe',  # 德语
                    'Compras dentro de la app',  # 西班牙语
                    'Acquisti in-app',  # 意大利语
                    'App 내 구입',  # 韩语
                    'アプリ内課金',  # 日语
                ]

                iap_section_found = False
                for heading_text in iap_heading_texts:
                    try:
                        # 查找包含标题文本的元素
                        heading = await page.query_selector(f'h2:has-text("{heading_text}"), h3:has-text("{heading_text}"), [class*="heading"]:has-text("{heading_text}")')
                        if heading:
                            logger.info(f"找到 In-App Purchases 标题: {heading_text}")
                            # 滚动到该元素
                            await heading.scroll_into_view_if_needed()
                            await asyncio.sleep(1)  # 等待滚动动画完成
                            iap_section_found = True
                            break
                    except Exception as e:
                        continue

                # 如果没有找到标题，尝试滚动到页面中部（In-App Purchases 通常在中部）
                if not iap_section_found:
                    logger.info("未找到 In-App Purchases 标题，尝试滚动页面...")
                    await page.evaluate('window.scrollTo(0, document.body.scrollHeight / 2)')
                    await asyncio.sleep(2)

                # 等待价格元素加载
                await asyncio.sleep(1)

                # 提取 In-App Purchases 部分的价格
                # 方法 1a: 查找包含价格的列表项或行
                try:
                    # App Store 的 In-App Purchases 通常在一个列表中
                    # 每个项目包含名称和价格
                    price_containers = [
                        'li',  # 列表项
                        '[class*="in-app-purchase"]',
                        '[class*="iap"]',
                        'dd',  # 定义列表
                        'div[class*="lockup"]',  # App Store 使用的布局类
                    ]

                    for container_selector in price_containers:
                        try:
                            containers = await page.query_selector_all(container_selector)
                            for container in containers:
                                text = await container.inner_text()

                                # 检查是否包含 Claude 相关关键词（确保是订阅项）
                                if any(keyword in text for keyword in ['Claude', 'Pro', 'Max', 'Team', 'Monthly', 'Annual', 'month', 'year']):
                                    # 检查是否包含价格
                                    if re.search(r'[\d.,]+', text):
                                        # 过滤掉无效文本
                                        if any(invalid in text.upper() for invalid in ['PDF', 'DOWNLOAD', 'GET', 'OPEN', 'RATING']):
                                            continue

                                        # 解析价格
                                        price_local = currency_converter.parse_price_string(text, region.currency)
                                        if price_local and price_local > 0:
                                            all_prices.append({
                                                'text': text.replace('\n', ' ').strip(),
                                                'price': price_local,
                                                'source': f'iap_container: {container_selector}'
                                            })
                                            logger.debug(f"找到 IAP 价格: {price_local} ({text[:50]}...)")
                        except Exception as e:
                            continue

                except Exception as e:
                    logger.debug(f"方法 1a 提取 IAP 价格失败: {e}")

            except Exception as e:
                logger.debug(f"滚动到 In-App Purchases 失败: {e}")

            # 方法 2: 使用正则表达式在页面内容中搜索价格模式
            if not all_prices:
                try:
                    logger.info("方法 1 未找到价格，尝试在页面内容中搜索...")
                    page_content = await page.content()

                    # 移除 HTML 标签，保留文本内容
                    import html
                    text_content = re.sub(r'<[^>]+>', ' ', page_content)
                    text_content = html.unescape(text_content)

                    # 查找价格模式（货币符号 + 数字）
                    # 支持多种货币格式
                    currency_patterns = [
                        r'[\$€£¥₹₺₽₩R\$]\s*[\d.,]+',  # 货币符号在前
                        r'[\d.,]+\s*[\$€£¥₹₺₽₩R\$]',  # 货币符号在后
                    ]

                    for pattern in currency_patterns:
                        matches = re.findall(pattern, text_content)
                        for match in matches:
                            # 过滤掉无效的价格（太大或太小）
                            price_local = currency_converter.parse_price_string(match, region.currency)
                            if price_local and 10 <= price_local <= 100000:  # 合理的价格范围
                                all_prices.append({
                                    'text': match,
                                    'price': price_local,
                                    'source': 'page_content_regex'
                                })
                                logger.debug(f"在页面内容中找到价格: {price_local} ({match})")

                except Exception as e:
                    logger.debug(f"方法 2 提取价格失败: {e}")

            # 如果找到价格，选择最高的
            if all_prices:
                # 去重（相同价格只保留一个）
                unique_prices = {}
                for price_info in all_prices:
                    price = price_info['price']
                    if price not in unique_prices:
                        unique_prices[price] = price_info

                all_prices = list(unique_prices.values())

                # 按价格排序，取最高的
                max_price_info = max(all_prices, key=lambda x: x['price'])
                price_local = max_price_info['price']

                logger.info(f"找到 {len(all_prices)} 个不同价格，选择最高: {price_local} {region.currency} (来源: {max_price_info['source']})")

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
                        "subscription_type": "max",  # 标记为最高价格
                        "scrape_time": datetime.utcnow(),
                        "success": 1,
                        "error_message": None
                    }

            # 方法 3: 截图保存以便调试
            try:
                screenshot_path = f"data/debug_{region.code}_{int(time.time())}.png"
                await page.screenshot(path=screenshot_path, full_page=True)
                logger.info(f"未找到价格，已保存截图: {screenshot_path}")
            except Exception as e:
                logger.debug(f"保存截图失败: {e}")

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
