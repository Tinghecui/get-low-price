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
                    'Compras en la app',  # 西班牙语（替代）
                    'Compras in-app',  # 西班牙语（简短版）
                    'Compras',  # 西班牙语（最简版）
                    'Acquisti in-app',  # 意大利语
                    'App 내 구입',  # 韩语
                    'アプリ内課金',  # 日语
                    'In-app-aankopen',  # 荷兰语
                    'Kjøp i appen',  # 挪威语
                    'Покупки в приложении',  # 俄语
                ]

                iap_section_found = False
                for heading_text in iap_heading_texts:
                    try:
                        # 查找包含标题文本的元素（使用更宽松的匹配）
                        heading = await page.query_selector(f'h2:has-text("{heading_text}"), h3:has-text("{heading_text}"), [class*="heading"]:has-text("{heading_text}")')
                        if heading:
                            logger.info(f"找到 In-App Purchases 标题: {heading_text}")
                            # 滚动到该元素
                            await heading.scroll_into_view_if_needed()
                            await asyncio.sleep(1.5)  # 等待滚动动画完成
                            iap_section_found = True
                            break
                    except Exception as e:
                        continue

                # 如果没有找到标题，尝试多次滚动页面（逐步向下）
                if not iap_section_found:
                    logger.info("未找到 In-App Purchases 标题，尝试滚动页面...")
                    # 分多次滚动，每次滚动一部分，增加找到IAP部分的机会
                    # 增加滚动到页面底部，确保能看到所有内容
                    for scroll_position in [0.3, 0.5, 0.7, 0.9, 1.0]:
                        await page.evaluate(f'window.scrollTo(0, document.body.scrollHeight * {scroll_position})')
                        await asyncio.sleep(1.5)  # 增加等待时间，确保动态内容加载
                        # 尝试查找价格元素
                        test_elements = await page.query_selector_all('li, dd, div[class*="lockup"]')
                        if len(test_elements) > 10:  # 如果找到足够多的元素，可能已经到了IAP部分
                            logger.debug(f"在滚动位置 {scroll_position} 找到 {len(test_elements)} 个元素")

                    # 额外滚动：从底部向上一点，有时IAP在页面底部之前
                    await page.evaluate('window.scrollTo(0, document.body.scrollHeight - 500)')
                    await asyncio.sleep(1)

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
                        'div[class*="product"]',  # 产品容器
                        'div[class*="subscription"]',  # 订阅容器
                        'ul > li',  # 明确的列表项
                        'ol > li',  # 有序列表项
                    ]

                    for container_selector in price_containers:
                        try:
                            containers = await page.query_selector_all(container_selector)
                            logger.debug(f"找到 {len(containers)} 个 {container_selector} 元素")

                            for container in containers:
                                try:
                                    text = await container.inner_text()
                                    text_lower = text.lower()

                                    # 检查是否包含 Claude 相关关键词或订阅相关词（确保是订阅项）
                                    subscription_keywords = [
                                        'claude', 'pro', 'max', 'team',
                                        'monthly', 'annual', 'month', 'year',
                                        'mensual', 'anual', 'mes', 'año',  # 西班牙语
                                        'mensal', 'ano',  # 葡萄牙语
                                        'monatlich', 'jährlich',  # 德语
                                        'mensuel', 'annuel',  # 法语
                                        'subscription', 'suscripción', 'assinatura', 'abonnement'
                                    ]

                                    if any(keyword in text_lower for keyword in subscription_keywords):
                                        # 检查是否包含价格
                                        if re.search(r'[\d.,]+', text):
                                            # 过滤掉无效文本
                                            if any(invalid in text.upper() for invalid in ['PDF', 'DOWNLOAD', 'GET', 'OPEN', 'RATING', 'EDAD']):
                                                continue

                                            # 解析价格
                                            price_local = currency_converter.parse_price_string(text, region.currency, silent=True)
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
                            logger.debug(f"处理容器 {container_selector} 时出错: {e}")
                            continue

                except Exception as e:
                    logger.debug(f"方法 1a 提取 IAP 价格失败: {e}")

            except Exception as e:
                logger.debug(f"滚动到 In-App Purchases 失败: {e}")

            # 方法 2: 使用正则表达式在页面内容中搜索价格模式（排除评论和版本历史区域）
            if not all_prices:
                try:
                    logger.info("方法 1 未找到价格，尝试在页面内容中搜索...")
                    page_content = await page.content()

                    # 移除评论区域和版本历史区域（这些区域经常包含误匹配的数字）
                    import html
                    from bs4 import BeautifulSoup

                    soup = BeautifulSoup(page_content, 'html.parser')

                    # 移除已知的非价格区域
                    for selector in [
                        '[class*="review"]',  # 评论区
                        '[class*="rating"]',  # 评分区
                        '[class*="version"]',  # 版本历史
                        '[class*="whats-new"]',  # 更新说明
                        '[class*="description"]',  # 描述区
                    ]:
                        for element in soup.select(selector):
                            element.decompose()

                    # 提取剩余的文本内容
                    text_content = soup.get_text(separator=' ')
                    text_content = html.unescape(text_content)

                    # 查找价格模式（货币符号 + 数字）
                    # 支持多种货币格式，包括 ARS (阿根廷比索), BRL (巴西雷亚尔) 等
                    currency_patterns = [
                        r'[\$€£¥₹₺₽₩]\s*[\d.,]+',  # 货币符号在前（美元、欧元等）
                        r'R\$\s*[\d.,]+',  # 巴西雷亚尔
                        r'ARS?\s*[\d.,]+',  # 阿根廷比索 (AR$ 或 ARS)
                        r'US\$\s*[\d.,]+',  # 美元（US$格式）
                        r'[\d.,]+\s*(?:USD|EUR|GBP|JPY|CNY|ARS|BRL|MXN|COP|CLP)',  # 货币代码在后
                        r'[\d.,]+\s*[\$€£¥₹₺₽₩]',  # 货币符号在后
                    ]

                    for pattern in currency_patterns:
                        matches = re.findall(pattern, text_content, re.IGNORECASE)
                        for match in matches:
                            # 过滤掉无效的价格（太大或太小）
                            price_local = currency_converter.parse_price_string(match, region.currency, silent=True)
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
                    # 验证价格合理性（Claude订阅价格应该在10-500美元之间）
                    if price_usd < 10:
                        logger.warning(f"价格过低: {price_usd} USD，可能提取错误，继续尝试其他价格")
                        # 尝试使用次高的价格
                        if len(all_prices) > 1:
                            sorted_prices = sorted(all_prices, key=lambda x: x['price'], reverse=True)
                            for price_info in sorted_prices[1:]:
                                alt_price_local = price_info['price']
                                alt_price_usd = currency_converter.convert(alt_price_local, region.currency, "USD")
                                if alt_price_usd and 10 <= alt_price_usd <= 500:
                                    logger.info(f"使用次高价格: {alt_price_local} {region.currency} = ${alt_price_usd:.2f} USD")
                                    price_local = alt_price_local
                                    price_usd = alt_price_usd
                                    max_price_info = price_info
                                    break

                    # 再次检查价格是否合理
                    if price_usd >= 10 and price_usd <= 500:
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
                    else:
                        logger.warning(f"价格不在合理范围内: {price_usd} USD")
                        # 继续执行，保存截图等后续操作

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
