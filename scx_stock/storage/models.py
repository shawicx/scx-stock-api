"""
@description ORM 模型，存储慢变数据：股票/ETF 列表、历史 K 线、关注列表、分析报告、应用配置。
"""

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from scx_stock.storage.db import Base


class StockModel(Base):
    """股票/ETF 基础信息表。

    存储代码、简称、所属市场、上市状态等慢变字段，由 Scheduler 每日同步。
    """

    __tablename__ = "stock"
    __table_args__ = (UniqueConstraint("code", "type", name="uq_stock_code_type"),)

    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(64), index=True)
    market: Mapped[str] = mapped_column(String(16), index=True)
    pinyin: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    type: Mapped[str] = mapped_column(String(16), primary_key=True)  # stock / etf
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class KlineModel(Base):
    """历史 K 线表。

    按收盘后增量同步，用于趋势分析、AI 上下文。
    """

    __tablename__ = "kline"
    __table_args__ = (
        UniqueConstraint("code", "trade_date", name="uq_kline_code_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(16), index=True)
    trade_date: Mapped[date] = mapped_column(Date, index=True)
    open: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    volume: Mapped[float] = mapped_column(Float)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class MarketCalendarModel(Base):
    """市场交易日历表，标记是否交易日、收盘时间，供 Scheduler 调度判断。

    :param trade_date: 交易日。
    :param is_open: 是否开市。
    """

    __tablename__ = "market_calendar"

    trade_date: Mapped[date] = mapped_column(Date, primary_key=True)
    is_open: Mapped[bool] = mapped_column(default=True)


class StockIndustryModel(Base):
    """股票行业映射表，由 Scheduler 从板块成分股反查构建。

    存 code → industry（行业板块名）的映射，供行情列表查询时零开销补充行业字段。
    每日同步更新。
    """

    __tablename__ = "stock_industry"

    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    industry: Mapped[str] = mapped_column(String(64))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AppSettingModel(Base):
    """应用配置表（KV 结构），存储 LLM / SMTP 等运行时可修改的配置。

    运行时优先读此表，无对应 key 时回退 .env（Settings）。
    KV 结构便于未来扩展，新增配置项无需迁移。
    """

    __tablename__ = "app_setting"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(512))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class WatchlistModel(Base):
    """用户关注列表，定时任务分析的数据来源。

    单用户工具，无需 user_id。name 在添加时从 stock 表查询补全并冗余存储，
    避免定时任务重复联表查询。
    """

    __tablename__ = "watchlist"

    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(64), default="")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AnalysisReportModel(Base):
    """支撑位分析报告历史表，每日收盘后由 Scheduler 写入。

    标量列（close/change_pct/trend/ok）拍平用于查询/排序，
    完整结构（含 support/resistance/ma/summary）存 JSONB payload。
    按 (code, trade_date) upsert，日内多次触发幂等覆盖。
    """

    __tablename__ = "analysis_report"
    __table_args__ = (
        UniqueConstraint("code", "trade_date", name="uq_report_code_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(16), index=True)
    trade_date: Mapped[date] = mapped_column(Date, index=True)
    name: Mapped[str] = mapped_column(String(64), default="")
    close: Mapped[float | None] = mapped_column(Float, nullable=True)
    change_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    trend: Mapped[str] = mapped_column(String(16), default="", index=True)
    ok: Mapped[bool] = mapped_column(Boolean, default=True)
    payload: Mapped[dict] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
