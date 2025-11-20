"""
价格分析模块
"""
import logging
from typing import List, Dict, Optional
from datetime import datetime

from src.storage.database import db_manager
from src.storage.models import AppPrice
from config.settings import APP_ID, SHOW_TOP_N_CHEAPEST

logger = logging.getLogger(__name__)


class PriceAnalyzer:
    """价格分析器"""

    def __init__(self, app_id: str = None):
        """
        初始化价格分析器

        Args:
            app_id: App Store ID
        """
        self.app_id = app_id or APP_ID

    def get_latest_prices(self) -> List[AppPrice]:
        """
        获取最新价格数据

        Returns:
            价格列表
        """
        return db_manager.get_latest_prices(self.app_id)

    def analyze_prices(self, prices: List[AppPrice] = None) -> Dict:
        """
        分析价格数据

        Args:
            prices: 价格列表，None 则从数据库获取最新价格

        Returns:
            分析结果字典
        """
        if prices is None:
            prices = self.get_latest_prices()

        if not prices:
            logger.warning("没有价格数据可供分析")
            return {
                "total_regions": 0,
                "cheapest": None,
                "most_expensive": None,
                "average_price": 0.0,
                "median_price": 0.0,
                "top_cheapest": [],
                "top_expensive": [],
                "price_range": 0.0,
                "analysis_time": datetime.utcnow().isoformat()
            }

        # 排序
        sorted_prices = sorted(prices, key=lambda x: x.price_usd)

        # 统计信息
        prices_usd = [p.price_usd for p in sorted_prices]
        total = len(prices_usd)
        avg_price = sum(prices_usd) / total if total > 0 else 0.0
        median_price = prices_usd[total // 2] if total > 0 else 0.0
        min_price = prices_usd[0] if total > 0 else 0.0
        max_price = prices_usd[-1] if total > 0 else 0.0
        price_range = max_price - min_price

        # 最便宜和最贵
        cheapest = sorted_prices[0] if sorted_prices else None
        most_expensive = sorted_prices[-1] if sorted_prices else None

        # Top N 最便宜和最贵
        top_n = min(SHOW_TOP_N_CHEAPEST, len(sorted_prices))
        top_cheapest = sorted_prices[:top_n]
        top_expensive = sorted_prices[-top_n:][::-1]  # 反转，最贵的排前面

        # 构建分析结果
        result = {
            "total_regions": total,
            "cheapest": {
                "region_code": cheapest.region_code,
                "region_name": cheapest.region_name,
                "region_name_cn": cheapest.region_name_cn,
                "currency": cheapest.currency,
                "price_local": cheapest.price_local,
                "price_usd": cheapest.price_usd,
            } if cheapest else None,
            "most_expensive": {
                "region_code": most_expensive.region_code,
                "region_name": most_expensive.region_name,
                "region_name_cn": most_expensive.region_name_cn,
                "currency": most_expensive.currency,
                "price_local": most_expensive.price_local,
                "price_usd": most_expensive.price_usd,
            } if most_expensive else None,
            "average_price": round(avg_price, 2),
            "median_price": round(median_price, 2),
            "price_range": round(price_range, 2),
            "top_cheapest": [
                {
                    "rank": i + 1,
                    "region_code": p.region_code,
                    "region_name": p.region_name,
                    "region_name_cn": p.region_name_cn,
                    "currency": p.currency,
                    "price_local": p.price_local,
                    "price_usd": p.price_usd,
                    "savings_vs_most_expensive": round(max_price - p.price_usd, 2),
                    "savings_percentage": round((max_price - p.price_usd) / max_price * 100, 1) if max_price > 0 else 0.0
                }
                for i, p in enumerate(top_cheapest)
            ],
            "top_expensive": [
                {
                    "rank": i + 1,
                    "region_code": p.region_code,
                    "region_name": p.region_name,
                    "region_name_cn": p.region_name_cn,
                    "currency": p.currency,
                    "price_local": p.price_local,
                    "price_usd": p.price_usd,
                    "extra_cost_vs_cheapest": round(p.price_usd - min_price, 2),
                    "extra_cost_percentage": round((p.price_usd - min_price) / min_price * 100, 1) if min_price > 0 else 0.0
                }
                for i, p in enumerate(top_expensive)
            ],
            "analysis_time": datetime.utcnow().isoformat()
        }

        return result

    def print_analysis(self, analysis: Dict = None):
        """
        打印分析结果

        Args:
            analysis: 分析结果字典，None 则重新分析
        """
        if analysis is None:
            analysis = self.analyze_prices()

        if analysis["total_regions"] == 0:
            print("\n❌ 没有价格数据")
            return

        print("\n" + "=" * 80)
        print("📊 Claude Max 订阅价格分析报告")
        print("=" * 80)

        print(f"\n📅 分析时间: {analysis['analysis_time']}")
        print(f"🌍 分析地区数: {analysis['total_regions']}")

        # 最便宜
        if analysis['cheapest']:
            c = analysis['cheapest']
            print(f"\n🏆 最便宜地区:")
            print(f"   地区: {c['region_name_cn']} ({c['region_name']}, {c['region_code'].upper()})")
            print(f"   价格: {c['price_local']:.2f} {c['currency']} = ${c['price_usd']:.2f} USD")

        # 最贵
        if analysis['most_expensive']:
            e = analysis['most_expensive']
            print(f"\n💸 最贵地区:")
            print(f"   地区: {e['region_name_cn']} ({e['region_name']}, {e['region_code'].upper()})")
            print(f"   价格: {e['price_local']:.2f} {e['currency']} = ${e['price_usd']:.2f} USD")

        # 统计信息
        print(f"\n📈 统计信息:")
        print(f"   平均价格: ${analysis['average_price']:.2f} USD")
        print(f"   中位数价格: ${analysis['median_price']:.2f} USD")
        print(f"   价格区间: ${analysis['price_range']:.2f} USD")

        # Top N 最便宜
        print(f"\n💰 前 {len(analysis['top_cheapest'])} 个最便宜的地区:")
        print(f"{'排名':<6} {'地区':<25} {'本地价格':<20} {'美元价格':<15} {'节省':<15}")
        print("-" * 80)
        for item in analysis['top_cheapest']:
            region_display = f"{item['region_name_cn']} ({item['region_code'].upper()})"
            local_price = f"{item['price_local']:.2f} {item['currency']}"
            usd_price = f"${item['price_usd']:.2f}"
            savings = f"-${item['savings_vs_most_expensive']:.2f} ({item['savings_percentage']:.1f}%)"
            print(f"{item['rank']:<6} {region_display:<25} {local_price:<20} {usd_price:<15} {savings:<15}")

        # Top N 最贵
        print(f"\n💸 前 {len(analysis['top_expensive'])} 个最贵的地区:")
        print(f"{'排名':<6} {'地区':<25} {'本地价格':<20} {'美元价格':<15} {'多花':<15}")
        print("-" * 80)
        for item in analysis['top_expensive']:
            region_display = f"{item['region_name_cn']} ({item['region_code'].upper()})"
            local_price = f"{item['price_local']:.2f} {item['currency']}"
            usd_price = f"${item['price_usd']:.2f}"
            extra = f"+${item['extra_cost_vs_cheapest']:.2f} ({item['extra_cost_percentage']:.1f}%)"
            print(f"{item['rank']:<6} {region_display:<25} {local_price:<20} {usd_price:<15} {extra:<15}")

        print("\n" + "=" * 80)

    def get_price_trends(self, region_code: str, days: int = 30) -> List[Dict]:
        """
        获取价格趋势

        Args:
            region_code: 地区代码
            days: 天数

        Returns:
            价格趋势列表
        """
        history = db_manager.get_price_history(self.app_id, region_code, days)

        return [
            {
                "date": p.scrape_time.strftime("%Y-%m-%d"),
                "price_local": p.price_local,
                "price_usd": p.price_usd,
                "currency": p.currency,
                "exchange_rate": p.exchange_rate
            }
            for p in history
        ]

    def compare_with_us(self, prices: List[AppPrice] = None) -> Dict:
        """
        与美国价格对比

        Args:
            prices: 价格列表

        Returns:
            对比结果
        """
        if prices is None:
            prices = self.get_latest_prices()

        # 找到美国价格
        us_price = None
        for p in prices:
            if p.region_code.lower() == "us":
                us_price = p
                break

        if not us_price:
            logger.warning("未找到美国价格数据")
            return {}

        # 计算与美国的价格差异
        comparisons = []
        for p in prices:
            if p.region_code.lower() == "us":
                continue

            diff = p.price_usd - us_price.price_usd
            diff_percentage = (diff / us_price.price_usd * 100) if us_price.price_usd > 0 else 0.0

            comparisons.append({
                "region_code": p.region_code,
                "region_name": p.region_name,
                "region_name_cn": p.region_name_cn,
                "price_local": p.price_local,
                "price_usd": p.price_usd,
                "currency": p.currency,
                "diff_vs_us": round(diff, 2),
                "diff_percentage": round(diff_percentage, 1),
                "is_cheaper": diff < 0
            })

        # 按价格差异排序
        comparisons.sort(key=lambda x: x['diff_vs_us'])

        return {
            "us_price": {
                "price_local": us_price.price_local,
                "price_usd": us_price.price_usd,
                "currency": us_price.currency
            },
            "comparisons": comparisons,
            "cheaper_count": sum(1 for c in comparisons if c['is_cheaper']),
            "more_expensive_count": sum(1 for c in comparisons if not c['is_cheaper'])
        }


if __name__ == "__main__":
    # 测试代码
    logging.basicConfig(level=logging.INFO)

    analyzer = PriceAnalyzer()

    # 分析价格
    print("\n开始分析价格...")
    analyzer.print_analysis()
