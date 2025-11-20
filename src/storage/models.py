"""
数据模型定义
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, Index, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

Base = declarative_base()


class AppPrice(Base):
    """应用价格数据模型"""
    __tablename__ = "app_prices"

    id = Column(Integer, primary_key=True, autoincrement=True)
    app_id = Column(String(50), nullable=False, index=True)  # App Store ID
    app_name = Column(String(200), nullable=False)  # 应用名称
    region_code = Column(String(10), nullable=False, index=True)  # 地区代码
    region_name = Column(String(100), nullable=False)  # 地区名称
    region_name_cn = Column(String(100))  # 地区中文名称
    currency = Column(String(10), nullable=False)  # 货币代码
    price_local = Column(Float, nullable=False)  # 本地价格
    price_usd = Column(Float, nullable=False, index=True)  # 美元价格
    exchange_rate = Column(Float, nullable=False)  # 汇率
    subscription_type = Column(String(50))  # 订阅类型 (monthly/yearly)
    scrape_time = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)  # 爬取时间
    success = Column(Integer, default=1)  # 是否成功获取 (1: 成功, 0: 失败)
    error_message = Column(String(500))  # 错误信息

    # 复合索引，用于快速查询特定时间范围内的价格
    __table_args__ = (
        Index('idx_app_region_time', 'app_id', 'region_code', 'scrape_time'),
    )

    def __repr__(self):
        return (f"<AppPrice(region={self.region_code}, "
                f"price_local={self.price_local} {self.currency}, "
                f"price_usd=${self.price_usd:.2f})>")

    def to_dict(self):
        """转换为字典"""
        return {
            "id": self.id,
            "app_id": self.app_id,
            "app_name": self.app_name,
            "region_code": self.region_code,
            "region_name": self.region_name,
            "region_name_cn": self.region_name_cn,
            "currency": self.currency,
            "price_local": self.price_local,
            "price_usd": self.price_usd,
            "exchange_rate": self.exchange_rate,
            "subscription_type": self.subscription_type,
            "scrape_time": self.scrape_time.isoformat() if self.scrape_time else None,
            "success": self.success,
            "error_message": self.error_message
        }


class ExchangeRate(Base):
    """汇率数据模型"""
    __tablename__ = "exchange_rates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    base_currency = Column(String(10), nullable=False, default="USD")  # 基准货币
    target_currency = Column(String(10), nullable=False, index=True)  # 目标货币
    rate = Column(Float, nullable=False)  # 汇率
    fetch_time = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)  # 获取时间

    __table_args__ = (
        Index('idx_currency_time', 'target_currency', 'fetch_time'),
    )

    def __repr__(self):
        return f"<ExchangeRate({self.base_currency} -> {self.target_currency}: {self.rate})>"

    def to_dict(self):
        """转换为字典"""
        return {
            "id": self.id,
            "base_currency": self.base_currency,
            "target_currency": self.target_currency,
            "rate": self.rate,
            "fetch_time": self.fetch_time.isoformat() if self.fetch_time else None
        }


class ScrapeLog(Base):
    """爬取日志模型"""
    __tablename__ = "scrape_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    start_time = Column(DateTime, nullable=False, index=True)  # 开始时间
    end_time = Column(DateTime)  # 结束时间
    total_regions = Column(Integer)  # 总地区数
    success_count = Column(Integer)  # 成功数量
    failed_count = Column(Integer)  # 失败数量
    status = Column(String(20))  # 状态: running, completed, failed
    error_message = Column(String(1000))  # 错误信息

    def __repr__(self):
        return f"<ScrapeLog(start={self.start_time}, status={self.status})>"

    def to_dict(self):
        """转换为字典"""
        return {
            "id": self.id,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "total_regions": self.total_regions,
            "success_count": self.success_count,
            "failed_count": self.failed_count,
            "status": self.status,
            "error_message": self.error_message
        }


def init_database(database_url: str):
    """
    初始化数据库

    Args:
        database_url: 数据库连接 URL
    """
    engine = create_engine(database_url, echo=False)
    Base.metadata.create_all(engine)
    return engine


def get_session_maker(engine):
    """
    获取 Session 工厂

    Args:
        engine: 数据库引擎

    Returns:
        SessionMaker
    """
    return sessionmaker(bind=engine)
