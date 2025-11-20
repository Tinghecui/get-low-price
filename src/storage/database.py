"""
数据库操作模块
"""
from datetime import datetime, timedelta
from typing import List, Optional, Dict
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_, func

from .models import AppPrice, ExchangeRate, ScrapeLog, init_database, get_session_maker
from config.settings import DATABASE_URL


class DatabaseManager:
    """数据库管理器"""

    def __init__(self, database_url: str = None):
        """
        初始化数据库管理器

        Args:
            database_url: 数据库连接 URL
        """
        self.database_url = database_url or DATABASE_URL
        self.engine = init_database(self.database_url)
        self.SessionMaker = get_session_maker(self.engine)

    def get_session(self) -> Session:
        """获取数据库 Session"""
        return self.SessionMaker()

    # ==================== AppPrice 相关操作 ====================

    def save_price(self, price_data: Dict) -> AppPrice:
        """
        保存价格数据

        Args:
            price_data: 价格数据字典

        Returns:
            AppPrice 对象
        """
        session = self.get_session()
        try:
            price = AppPrice(**price_data)
            session.add(price)
            session.commit()
            session.refresh(price)
            return price
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def save_prices_batch(self, prices_data: List[Dict]) -> List[AppPrice]:
        """
        批量保存价格数据

        Args:
            prices_data: 价格数据字典列表

        Returns:
            AppPrice 对象列表
        """
        session = self.get_session()
        try:
            prices = [AppPrice(**data) for data in prices_data]
            session.add_all(prices)
            session.commit()
            return prices
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def get_latest_prices(self, app_id: str) -> List[AppPrice]:
        """
        获取最新的价格数据（每个地区最新的一条）

        Args:
            app_id: App Store ID

        Returns:
            AppPrice 对象列表
        """
        session = self.get_session()
        try:
            # 使用子查询获取每个地区的最新时间
            subquery = session.query(
                AppPrice.region_code,
                func.max(AppPrice.scrape_time).label('max_time')
            ).filter(
                AppPrice.app_id == app_id
            ).group_by(
                AppPrice.region_code
            ).subquery()

            # 获取最新的价格记录
            prices = session.query(AppPrice).join(
                subquery,
                and_(
                    AppPrice.region_code == subquery.c.region_code,
                    AppPrice.scrape_time == subquery.c.max_time
                )
            ).filter(
                AppPrice.app_id == app_id,
                AppPrice.success == 1
            ).order_by(
                AppPrice.price_usd
            ).all()

            return prices
        finally:
            session.close()

    def get_price_history(self, app_id: str, region_code: str,
                         days: int = 30) -> List[AppPrice]:
        """
        获取指定地区的价格历史

        Args:
            app_id: App Store ID
            region_code: 地区代码
            days: 查询天数

        Returns:
            AppPrice 对象列表
        """
        session = self.get_session()
        try:
            start_time = datetime.utcnow() - timedelta(days=days)
            prices = session.query(AppPrice).filter(
                AppPrice.app_id == app_id,
                AppPrice.region_code == region_code,
                AppPrice.scrape_time >= start_time,
                AppPrice.success == 1
            ).order_by(
                desc(AppPrice.scrape_time)
            ).all()
            return prices
        finally:
            session.close()

    def get_cheapest_regions(self, app_id: str, limit: int = 10) -> List[AppPrice]:
        """
        获取最便宜的地区（基于最新价格）

        Args:
            app_id: App Store ID
            limit: 返回数量

        Returns:
            AppPrice 对象列表
        """
        prices = self.get_latest_prices(app_id)
        return sorted(prices, key=lambda x: x.price_usd)[:limit]

    # ==================== ExchangeRate 相关操作 ====================

    def save_exchange_rate(self, rate_data: Dict) -> ExchangeRate:
        """
        保存汇率数据

        Args:
            rate_data: 汇率数据字典

        Returns:
            ExchangeRate 对象
        """
        session = self.get_session()
        try:
            rate = ExchangeRate(**rate_data)
            session.add(rate)
            session.commit()
            session.refresh(rate)
            return rate
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def save_exchange_rates_batch(self, rates_data: List[Dict]) -> List[ExchangeRate]:
        """
        批量保存汇率数据

        Args:
            rates_data: 汇率数据字典列表

        Returns:
            ExchangeRate 对象列表
        """
        session = self.get_session()
        try:
            rates = [ExchangeRate(**data) for data in rates_data]
            session.add_all(rates)
            session.commit()
            return rates
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def get_latest_exchange_rate(self, target_currency: str,
                                 base_currency: str = "USD") -> Optional[ExchangeRate]:
        """
        获取最新的汇率

        Args:
            target_currency: 目标货币
            base_currency: 基准货币

        Returns:
            ExchangeRate 对象或 None
        """
        session = self.get_session()
        try:
            rate = session.query(ExchangeRate).filter(
                ExchangeRate.base_currency == base_currency,
                ExchangeRate.target_currency == target_currency
            ).order_by(
                desc(ExchangeRate.fetch_time)
            ).first()
            return rate
        finally:
            session.close()

    def get_latest_exchange_rates(self, base_currency: str = "USD") -> Dict[str, float]:
        """
        获取所有货币的最新汇率

        Args:
            base_currency: 基准货币

        Returns:
            汇率字典 {货币代码: 汇率}
        """
        session = self.get_session()
        try:
            # 获取每个货币的最新汇率
            subquery = session.query(
                ExchangeRate.target_currency,
                func.max(ExchangeRate.fetch_time).label('max_time')
            ).filter(
                ExchangeRate.base_currency == base_currency
            ).group_by(
                ExchangeRate.target_currency
            ).subquery()

            rates = session.query(ExchangeRate).join(
                subquery,
                and_(
                    ExchangeRate.target_currency == subquery.c.target_currency,
                    ExchangeRate.fetch_time == subquery.c.max_time
                )
            ).filter(
                ExchangeRate.base_currency == base_currency
            ).all()

            return {rate.target_currency: rate.rate for rate in rates}
        finally:
            session.close()

    # ==================== ScrapeLog 相关操作 ====================

    def create_scrape_log(self, log_data: Dict) -> ScrapeLog:
        """
        创建爬取日志

        Args:
            log_data: 日志数据字典

        Returns:
            ScrapeLog 对象
        """
        session = self.get_session()
        try:
            log = ScrapeLog(**log_data)
            session.add(log)
            session.commit()
            session.refresh(log)
            return log
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def update_scrape_log(self, log_id: int, update_data: Dict) -> ScrapeLog:
        """
        更新爬取日志

        Args:
            log_id: 日志 ID
            update_data: 更新数据字典

        Returns:
            更新后的 ScrapeLog 对象
        """
        session = self.get_session()
        try:
            log = session.query(ScrapeLog).filter(ScrapeLog.id == log_id).first()
            if log:
                for key, value in update_data.items():
                    setattr(log, key, value)
                session.commit()
                session.refresh(log)
            return log
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def get_recent_scrape_logs(self, limit: int = 10) -> List[ScrapeLog]:
        """
        获取最近的爬取日志

        Args:
            limit: 返回数量

        Returns:
            ScrapeLog 对象列表
        """
        session = self.get_session()
        try:
            logs = session.query(ScrapeLog).order_by(
                desc(ScrapeLog.start_time)
            ).limit(limit).all()
            return logs
        finally:
            session.close()


# 创建全局数据库管理器实例
db_manager = DatabaseManager()
