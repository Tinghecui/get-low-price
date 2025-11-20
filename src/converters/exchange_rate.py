"""
汇率获取模块
"""
import requests
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional

from config.settings import EXCHANGE_RATE_API, EXCHANGE_RATE_CACHE_HOURS
from src.storage.database import db_manager

logger = logging.getLogger(__name__)


class ExchangeRateProvider:
    """汇率提供器"""

    def __init__(self, api_url: str = None, cache_hours: int = None):
        """
        初始化汇率提供器

        Args:
            api_url: 汇率 API URL
            cache_hours: 缓存时间（小时）
        """
        self.api_url = api_url or EXCHANGE_RATE_API
        self.cache_hours = cache_hours or EXCHANGE_RATE_CACHE_HOURS
        self._rates_cache: Dict[str, float] = {}
        self._last_fetch_time: Optional[datetime] = None

    def _is_cache_valid(self) -> bool:
        """检查缓存是否有效"""
        if not self._last_fetch_time:
            return False

        time_diff = datetime.utcnow() - self._last_fetch_time
        return time_diff < timedelta(hours=self.cache_hours)

    def _fetch_from_api(self) -> Dict[str, float]:
        """
        从 API 获取汇率

        Returns:
            汇率字典 {货币代码: 汇率}
        """
        try:
            logger.info(f"正在从 API 获取汇率: {self.api_url}")
            response = requests.get(self.api_url, timeout=10)
            response.raise_for_status()
            data = response.json()

            if "rates" in data:
                rates = data["rates"]
                # 添加 USD 本身的汇率（1.0）
                rates["USD"] = 1.0
                logger.info(f"成功获取 {len(rates)} 个货币的汇率")
                return rates
            else:
                raise ValueError("API 响应中没有 rates 字段")

        except requests.RequestException as e:
            logger.error(f"从 API 获取汇率失败: {e}")
            raise
        except ValueError as e:
            logger.error(f"解析汇率数据失败: {e}")
            raise

    def _fetch_from_database(self) -> Dict[str, float]:
        """
        从数据库获取最新汇率

        Returns:
            汇率字典 {货币代码: 汇率}
        """
        try:
            rates = db_manager.get_latest_exchange_rates()
            if rates:
                logger.info(f"从数据库获取到 {len(rates)} 个货币的汇率")
                # 确保包含 USD
                if "USD" not in rates:
                    rates["USD"] = 1.0
                return rates
            return {}
        except Exception as e:
            logger.error(f"从数据库获取汇率失败: {e}")
            return {}

    def _save_to_database(self, rates: Dict[str, float]):
        """
        保存汇率到数据库

        Args:
            rates: 汇率字典
        """
        try:
            fetch_time = datetime.utcnow()
            rates_data = [
                {
                    "base_currency": "USD",
                    "target_currency": currency,
                    "rate": rate,
                    "fetch_time": fetch_time
                }
                for currency, rate in rates.items()
            ]
            db_manager.save_exchange_rates_batch(rates_data)
            logger.info(f"成功保存 {len(rates_data)} 条汇率记录到数据库")
        except Exception as e:
            logger.error(f"保存汇率到数据库失败: {e}")

    def _get_default_rates(self) -> Dict[str, float]:
        """
        获取默认汇率（大约汇率，仅用于备用）

        Returns:
            默认汇率字典
        """
        # 这些是大约的汇率，仅在无法获取实时汇率时使用
        return {
            "USD": 1.0,
            "EUR": 0.92,
            "GBP": 0.79,
            "JPY": 149.0,
            "CNY": 7.24,
            "INR": 83.0,
            "TRY": 33.5,
            "ARS": 1000.0,
            "BRL": 4.97,
            "CAD": 1.39,
            "AUD": 1.53,
            "HKD": 7.83,
            "TWD": 31.5,
            "SGD": 1.34,
            "KRW": 1315.0,
            "MXN": 17.0,
            "RUB": 92.0,
            "ZAR": 18.5,
            "THB": 34.8,
            "IDR": 15650.0,
            "MYR": 4.65,
            "PHP": 56.0,
            "VND": 24500.0
        }

    def get_rates(self, force_refresh: bool = False) -> Dict[str, float]:
        """
        获取汇率（优先使用缓存，然后是数据库，最后是 API）

        Args:
            force_refresh: 是否强制刷新

        Returns:
            汇率字典 {货币代码: 汇率}
        """
        # 1. 检查内存缓存
        if not force_refresh and self._is_cache_valid() and self._rates_cache:
            logger.debug("使用内存缓存的汇率")
            return self._rates_cache

        # 2. 尝试从数据库获取
        db_rates = self._fetch_from_database()
        if db_rates:
            # 检查数据库中的汇率是否在缓存有效期内
            latest_rate = db_manager.get_latest_exchange_rate("EUR")  # 使用 EUR 作为参考
            if latest_rate:
                time_diff = datetime.utcnow() - latest_rate.fetch_time
                if time_diff < timedelta(hours=self.cache_hours):
                    self._rates_cache = db_rates
                    self._last_fetch_time = latest_rate.fetch_time
                    logger.info("使用数据库中的汇率")
                    return self._rates_cache

        # 3. 从 API 获取最新汇率
        try:
            api_rates = self._fetch_from_api()
            self._rates_cache = api_rates
            self._last_fetch_time = datetime.utcnow()

            # 保存到数据库
            self._save_to_database(api_rates)

            return self._rates_cache

        except Exception as e:
            # 如果 API 失败，尝试使用数据库中的旧数据
            if db_rates:
                logger.warning(f"API 获取失败，使用数据库中的旧汇率数据: {e}")
                self._rates_cache = db_rates
                self._last_fetch_time = datetime.utcnow()
                return self._rates_cache
            else:
                # 如果数据库也没有数据，返回一个包含常见货币的默认汇率
                logger.warning(f"无法从 API 或数据库获取汇率，使用默认汇率: {e}")
                default_rates = self._get_default_rates()
                self._rates_cache = default_rates
                self._last_fetch_time = datetime.utcnow()
                return self._rates_cache

    def get_rate(self, from_currency: str, to_currency: str = "USD",
                 force_refresh: bool = False) -> Optional[float]:
        """
        获取特定货币对的汇率

        Args:
            from_currency: 源货币代码
            to_currency: 目标货币代码（默认 USD）
            force_refresh: 是否强制刷新

        Returns:
            汇率，如果获取失败返回 None
        """
        try:
            rates = self.get_rates(force_refresh)

            from_currency = from_currency.upper()
            to_currency = to_currency.upper()

            # 如果源货币和目标货币相同，返回 1.0
            if from_currency == to_currency:
                return 1.0

            # 获取汇率（假设基准货币是 USD）
            if to_currency == "USD":
                # 转换为 USD
                if from_currency in rates:
                    return 1.0 / rates[from_currency] if rates[from_currency] != 0 else None
            elif from_currency == "USD":
                # 从 USD 转换
                return rates.get(to_currency)
            else:
                # 两个非 USD 货币之间的转换
                if from_currency in rates and to_currency in rates:
                    from_rate = rates[from_currency]
                    to_rate = rates[to_currency]
                    if from_rate != 0:
                        return to_rate / from_rate

            logger.warning(f"无法找到 {from_currency} 到 {to_currency} 的汇率")
            return None

        except Exception as e:
            logger.error(f"获取汇率失败: {e}")
            return None

    def clear_cache(self):
        """清除缓存"""
        self._rates_cache = {}
        self._last_fetch_time = None
        logger.info("汇率缓存已清除")


# 创建全局汇率提供器实例
exchange_rate_provider = ExchangeRateProvider()


if __name__ == "__main__":
    # 测试代码
    logging.basicConfig(level=logging.INFO)

    provider = ExchangeRateProvider()

    # 测试获取所有汇率
    print("\n获取所有汇率:")
    rates = provider.get_rates()
    for currency, rate in list(rates.items())[:10]:
        print(f"  {currency}: {rate}")

    # 测试获取特定汇率
    print("\n测试特定汇率:")
    print(f"  CNY to USD: {provider.get_rate('CNY', 'USD')}")
    print(f"  EUR to USD: {provider.get_rate('EUR', 'USD')}")
    print(f"  JPY to USD: {provider.get_rate('JPY', 'USD')}")
    print(f"  GBP to USD: {provider.get_rate('GBP', 'USD')}")
