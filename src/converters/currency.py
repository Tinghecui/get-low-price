"""
货币转换模块
"""
import re
import logging
from typing import Optional, Tuple

from .exchange_rate import exchange_rate_provider

logger = logging.getLogger(__name__)


class CurrencyConverter:
    """货币转换器"""

    # 货币符号映射
    CURRENCY_SYMBOLS = {
        "$": "USD",
        "€": "EUR",
        "£": "GBP",
        "¥": "JPY",  # 也可能是 CNY
        "₹": "INR",
        "R$": "BRL",
        "₺": "TRY",
        "₽": "RUB",
        "₩": "KRW",
        "A$": "AUD",
        "C$": "CAD",
        "HK$": "HKD",
        "NT$": "TWD",
        "S$": "SGD",
        "RM": "MYR",
        "₱": "PHP",
        "฿": "THB",
        "Rp": "IDR",
        "₫": "VND",
        "R": "ZAR",
    }

    def __init__(self):
        """初始化货币转换器"""
        self.exchange_rate_provider = exchange_rate_provider

    def parse_price_string(self, price_str: str, currency_code: str = None) -> Optional[float]:
        """
        解析价格字符串，提取数值

        Args:
            price_str: 价格字符串，如 "$19.99", "€15,99", "¥2,000"
            currency_code: 货币代码（可选，用于处理不同货币的格式差异）

        Returns:
            价格数值，如果解析失败返回 None

        Examples:
            >>> converter = CurrencyConverter()
            >>> converter.parse_price_string("$19.99")
            19.99
            >>> converter.parse_price_string("€15,99")
            15.99
            >>> converter.parse_price_string("¥2,000")
            2000.0
        """
        if not price_str:
            return None

        try:
            # 移除货币符号和空格
            cleaned = price_str.strip()

            # 移除常见的货币符号
            for symbol in self.CURRENCY_SYMBOLS.keys():
                cleaned = cleaned.replace(symbol, "")

            # 移除货币代码（如 USD, EUR 等）
            cleaned = re.sub(r'[A-Z]{3}', '', cleaned)

            # 移除空格
            cleaned = cleaned.strip()

            # 处理不同的数字格式
            # 例如: "1,234.56" (英文) 或 "1.234,56" (德语/西班牙语) 或 "1 234,56" (法语)

            # 统计逗号和点的数量
            comma_count = cleaned.count(',')
            dot_count = cleaned.count('.')
            space_count = cleaned.count(' ')

            # 移除所有空格
            cleaned = cleaned.replace(' ', '')

            # 判断小数分隔符
            if comma_count > 0 and dot_count > 0:
                # 如果同时有逗号和点，判断哪个是小数分隔符
                last_comma_pos = cleaned.rfind(',')
                last_dot_pos = cleaned.rfind('.')

                if last_comma_pos > last_dot_pos:
                    # 逗号是小数分隔符（欧洲格式）
                    cleaned = cleaned.replace('.', '').replace(',', '.')
                else:
                    # 点是小数分隔符（英文格式）
                    cleaned = cleaned.replace(',', '')
            elif comma_count > 0:
                # 只有逗号
                if comma_count == 1 and len(cleaned.split(',')[1]) <= 2:
                    # 逗号是小数分隔符
                    cleaned = cleaned.replace(',', '.')
                else:
                    # 逗号是千位分隔符
                    cleaned = cleaned.replace(',', '')
            elif dot_count > 1:
                # 多个点，是千位分隔符（欧洲格式）
                # 移除所有点
                cleaned = cleaned.replace('.', '')

            # 转换为浮点数
            price = float(cleaned)
            return price

        except (ValueError, AttributeError) as e:
            logger.warning(f"解析价格字符串失败: {price_str}, 错误: {e}")
            return None

    def detect_currency_from_symbol(self, price_str: str) -> Optional[str]:
        """
        从价格字符串中检测货币代码

        Args:
            price_str: 价格字符串

        Returns:
            货币代码，如果无法检测返回 None
        """
        if not price_str:
            return None

        for symbol, code in self.CURRENCY_SYMBOLS.items():
            if symbol in price_str:
                return code

        # 尝试匹配货币代码
        match = re.search(r'\b([A-Z]{3})\b', price_str)
        if match:
            return match.group(1)

        return None

    def convert(self, amount: float, from_currency: str, to_currency: str = "USD") -> Optional[float]:
        """
        转换货币

        Args:
            amount: 金额
            from_currency: 源货币代码
            to_currency: 目标货币代码（默认 USD）

        Returns:
            转换后的金额，如果转换失败返回 None
        """
        if amount is None or amount < 0:
            return None

        try:
            rate = self.exchange_rate_provider.get_rate(from_currency, to_currency)
            if rate is None:
                logger.error(f"无法获取 {from_currency} 到 {to_currency} 的汇率")
                return None

            converted = amount * rate
            return round(converted, 2)

        except Exception as e:
            logger.error(f"货币转换失败: {e}")
            return None

    def convert_price_string(self, price_str: str, from_currency: str,
                            to_currency: str = "USD") -> Tuple[Optional[float], Optional[float]]:
        """
        解析并转换价格字符串

        Args:
            price_str: 价格字符串
            from_currency: 源货币代码
            to_currency: 目标货币代码（默认 USD）

        Returns:
            (原始金额, 转换后的金额) 元组，如果失败返回 (None, None)
        """
        # 解析价格
        amount = self.parse_price_string(price_str, from_currency)
        if amount is None:
            return None, None

        # 转换货币
        converted = self.convert(amount, from_currency, to_currency)
        if converted is None:
            return amount, None

        return amount, converted

    def format_price(self, amount: float, currency: str) -> str:
        """
        格式化价格字符串

        Args:
            amount: 金额
            currency: 货币代码

        Returns:
            格式化后的价格字符串
        """
        # 找到对应的货币符号
        symbol = None
        for sym, code in self.CURRENCY_SYMBOLS.items():
            if code == currency:
                symbol = sym
                break

        if symbol:
            return f"{symbol}{amount:.2f}"
        else:
            return f"{amount:.2f} {currency}"


# 创建全局货币转换器实例
currency_converter = CurrencyConverter()


if __name__ == "__main__":
    # 测试代码
    logging.basicConfig(level=logging.INFO)

    converter = CurrencyConverter()

    print("\n测试价格解析:")
    test_prices = [
        "$19.99",
        "€15,99",
        "¥2,000",
        "₹1,299.00",
        "R$ 89,90",
        "1.234,56 €",
        "US$ 20.00",
    ]
    for price in test_prices:
        parsed = converter.parse_price_string(price)
        currency = converter.detect_currency_from_symbol(price)
        print(f"  {price:20} -> {parsed:10.2f} ({currency})")

    print("\n测试货币转换:")
    print(f"  100 CNY to USD: ${converter.convert(100, 'CNY', 'USD'):.2f}")
    print(f"  100 EUR to USD: ${converter.convert(100, 'EUR', 'USD'):.2f}")
    print(f"  10000 JPY to USD: ${converter.convert(10000, 'JPY', 'USD'):.2f}")
    print(f"  1000 INR to USD: ${converter.convert(1000, 'INR', 'USD'):.2f}")

    print("\n测试价格字符串转换:")
    test_conversions = [
        ("€15,99", "EUR"),
        ("¥2,000", "JPY"),
        ("₹1,299", "INR"),
    ]
    for price_str, currency in test_conversions:
        original, converted = converter.convert_price_string(price_str, currency)
        print(f"  {price_str} {currency} -> ${converted:.2f} USD")
