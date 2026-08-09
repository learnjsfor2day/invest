from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from pit_radar.db.base import Base
from pit_radar.db.types import JSONBType
from pit_radar.time import utc_now


money_col = Numeric(24, 6)


class EstimateSnapshot(Base):
    __tablename__ = "estimate_snapshot"
    __table_args__ = (
        UniqueConstraint("security_id", "fiscal_period_end", "period_type", "data_hash", name="uq_estimate_content_hash"),
        Index("ix_estimate_asof", "security_id", "fiscal_period_end", "period_type", "fetched_at"),
        {"schema": "pit", "comment": "分析师EPS和营收预期每日快照。"},
    )

    estimate_id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="预期快照ID")
    security_id: Mapped[int] = mapped_column(ForeignKey("core.security.security_id"), nullable=False, comment="证券ID")
    fiscal_period_end: Mapped[date] = mapped_column(Date, nullable=False, comment="财报周期结束日")
    period_type: Mapped[str] = mapped_column(String(32), nullable=False, comment="周期类型：quarter/fiscal_year")
    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="快照业务时间")
    source_published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment="来源发布时间")
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="系统获取时间")
    eps_mean: Mapped[Decimal | None] = mapped_column(money_col, comment="EPS预期均值")
    eps_high: Mapped[Decimal | None] = mapped_column(money_col, comment="EPS预期最高值")
    eps_low: Mapped[Decimal | None] = mapped_column(money_col, comment="EPS预期最低值")
    analyst_count_eps: Mapped[int | None] = mapped_column(Integer, comment="EPS预测机构数量")
    revenue_mean: Mapped[Decimal | None] = mapped_column(money_col, comment="营收预期均值")
    revenue_high: Mapped[Decimal | None] = mapped_column(money_col, comment="营收预期最高值")
    revenue_low: Mapped[Decimal | None] = mapped_column(money_col, comment="营收预期最低值")
    analyst_count_revenue: Mapped[int | None] = mapped_column(Integer, comment="营收预测机构数量")
    currency: Mapped[str | None] = mapped_column(String(16), default="USD", comment="货币")
    source_id: Mapped[int] = mapped_column(ForeignKey("core.data_source.source_id"), nullable=False, comment="数据源ID")
    raw_payload_id: Mapped[int] = mapped_column(ForeignKey("raw.payload.payload_id"), nullable=False, comment="原始载荷ID")
    data_hash: Mapped[str] = mapped_column(String(64), nullable=False, comment="标准化数据哈希")
    quality_flags: Mapped[dict | None] = mapped_column(JSONBType, comment="数据质量标记")
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, comment="入库时间")


class AnalystSnapshot(Base):
    __tablename__ = "analyst_snapshot"
    __table_args__ = (
        UniqueConstraint("security_id", "data_hash", name="uq_analyst_content_hash"),
        Index("ix_analyst_asof", "security_id", "fetched_at"),
        {"schema": "pit", "comment": "目标价和评级分布快照。"},
    )

    analyst_snapshot_id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="分析师快照ID")
    security_id: Mapped[int] = mapped_column(ForeignKey("core.security.security_id"), nullable=False, comment="证券ID")
    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="快照业务时间")
    source_published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment="来源发布时间")
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="系统获取时间")
    target_mean: Mapped[Decimal | None] = mapped_column(money_col, comment="目标价均值")
    target_high: Mapped[Decimal | None] = mapped_column(money_col, comment="目标价最高值")
    target_low: Mapped[Decimal | None] = mapped_column(money_col, comment="目标价最低值")
    strong_buy_count: Mapped[int | None] = mapped_column(Integer, comment="强烈买入数量")
    buy_count: Mapped[int | None] = mapped_column(Integer, comment="买入数量")
    hold_count: Mapped[int | None] = mapped_column(Integer, comment="持有数量")
    sell_count: Mapped[int | None] = mapped_column(Integer, comment="卖出数量")
    strong_sell_count: Mapped[int | None] = mapped_column(Integer, comment="强烈卖出数量")
    source_id: Mapped[int] = mapped_column(ForeignKey("core.data_source.source_id"), nullable=False, comment="数据源ID")
    raw_payload_id: Mapped[int] = mapped_column(ForeignKey("raw.payload.payload_id"), nullable=False, comment="原始载荷ID")
    data_hash: Mapped[str] = mapped_column(String(64), nullable=False, comment="标准化数据哈希")
    quality_flags: Mapped[dict | None] = mapped_column(JSONBType, comment="数据质量标记")
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, comment="入库时间")


class EarningsCalendarSnapshot(Base):
    __tablename__ = "earnings_calendar_snapshot"
    __table_args__ = (
        UniqueConstraint("security_id", "fiscal_period_end", "data_hash", name="uq_earnings_content_hash"),
        Index("ix_earnings_asof", "security_id", "fiscal_period_end", "fetched_at"),
        {"schema": "pit", "comment": "财报日期和预期变化快照。"},
    )

    earnings_snapshot_id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="财报日历快照ID")
    security_id: Mapped[int] = mapped_column(ForeignKey("core.security.security_id"), nullable=False, comment="证券ID")
    fiscal_period_end: Mapped[date] = mapped_column(Date, nullable=False, comment="财报周期结束日")
    expected_report_date: Mapped[date | None] = mapped_column(Date, comment="预计披露日期")
    expected_report_session: Mapped[str] = mapped_column(String(32), default="unknown", comment="预计披露时段")
    estimated_eps: Mapped[Decimal | None] = mapped_column(money_col, comment="预计EPS")
    estimated_revenue: Mapped[Decimal | None] = mapped_column(money_col, comment="预计营收")
    actual_eps: Mapped[Decimal | None] = mapped_column(money_col, comment="实际EPS")
    actual_revenue: Mapped[Decimal | None] = mapped_column(money_col, comment="实际营收")
    eps_surprise: Mapped[Decimal | None] = mapped_column(money_col, comment="EPS超预期值")
    eps_surprise_percent: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), comment="EPS超预期百分比")
    revenue_surprise: Mapped[Decimal | None] = mapped_column(money_col, comment="营收超预期值")
    revenue_surprise_percent: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), comment="营收超预期百分比")
    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="快照业务时间")
    source_published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment="来源发布时间")
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="系统获取时间")
    source_id: Mapped[int] = mapped_column(ForeignKey("core.data_source.source_id"), nullable=False, comment="数据源ID")
    raw_payload_id: Mapped[int] = mapped_column(ForeignKey("raw.payload.payload_id"), nullable=False, comment="原始载荷ID")
    data_hash: Mapped[str] = mapped_column(String(64), nullable=False, comment="标准化数据哈希")
    quality_flags: Mapped[dict | None] = mapped_column(JSONBType, comment="数据质量标记")
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, comment="入库时间")


class SecFilingSnapshot(Base):
    __tablename__ = "sec_filing_snapshot"
    __table_args__ = (
        UniqueConstraint("security_id", "form_type", "accepted_at", "data_hash", name="uq_sec_filing_content_hash"),
        Index("ix_sec_filing_asof", "security_id", "form_type", "accepted_at", "fetched_at"),
        {"schema": "pit", "comment": "SEC文件快照，包含8-K、10-Q、10-K等文件链接。"},
    )

    sec_filing_id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="SEC文件快照ID")
    security_id: Mapped[int] = mapped_column(ForeignKey("core.security.security_id"), nullable=False, comment="证券ID")
    form_type: Mapped[str | None] = mapped_column(String(32), comment="SEC表格类型，例如8-K、10-Q、10-K")
    filing_date: Mapped[date | None] = mapped_column(Date, comment="文件披露日期")
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment="SEC接受时间")
    cik: Mapped[str | None] = mapped_column(String(32), comment="SEC CIK")
    filing_url: Mapped[str | None] = mapped_column(Text, comment="SEC filing index链接")
    final_url: Mapped[str | None] = mapped_column(Text, comment="SEC最终文件链接")
    has_financials: Mapped[bool | None] = mapped_column(Boolean, comment="是否包含财务数据")
    source_published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment="来源发布时间")
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="系统获取时间")
    value_json: Mapped[dict] = mapped_column(JSONBType, nullable=False, comment="来源SEC文件行JSON")
    source_id: Mapped[int] = mapped_column(ForeignKey("core.data_source.source_id"), nullable=False, comment="数据源ID")
    raw_payload_id: Mapped[int] = mapped_column(ForeignKey("raw.payload.payload_id"), nullable=False, comment="原始载荷ID")
    data_hash: Mapped[str] = mapped_column(String(64), nullable=False, comment="标准化数据哈希")
    quality_flags: Mapped[dict | None] = mapped_column(JSONBType, comment="数据质量标记")
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, comment="入库时间")


class EarningTranscriptSnapshot(Base):
    __tablename__ = "earning_transcript_snapshot"
    __table_args__ = (
        UniqueConstraint("security_id", "fiscal_year", "fiscal_period", "data_hash", name="uq_transcript_content_hash"),
        Index("ix_transcript_asof", "security_id", "fiscal_year", "fiscal_period", "fetched_at"),
        {"schema": "pit", "comment": "财报电话会原文快照。"},
    )

    transcript_id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="电话会原文快照ID")
    security_id: Mapped[int] = mapped_column(ForeignKey("core.security.security_id"), nullable=False, comment="证券ID")
    fiscal_year: Mapped[int | None] = mapped_column(Integer, comment="财年")
    fiscal_period: Mapped[str | None] = mapped_column(String(16), comment="财务期间，例如Q1/Q4")
    call_date: Mapped[date | None] = mapped_column(Date, comment="电话会日期")
    transcript_text: Mapped[str | None] = mapped_column(Text, comment="电话会全文")
    word_count: Mapped[int | None] = mapped_column(Integer, comment="全文词数")
    source_published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment="来源发布时间")
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="系统获取时间")
    value_json: Mapped[dict] = mapped_column(JSONBType, nullable=False, comment="来源电话会元数据JSON")
    source_id: Mapped[int] = mapped_column(ForeignKey("core.data_source.source_id"), nullable=False, comment="数据源ID")
    raw_payload_id: Mapped[int] = mapped_column(ForeignKey("raw.payload.payload_id"), nullable=False, comment="原始载荷ID")
    data_hash: Mapped[str] = mapped_column(String(64), nullable=False, comment="标准化数据哈希")
    quality_flags: Mapped[dict | None] = mapped_column(JSONBType, comment="数据质量标记")
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, comment="入库时间")


class SourceDocumentSnapshot(Base):
    __tablename__ = "source_document_snapshot"
    __table_args__ = (
        UniqueConstraint("security_id", "document_type", "document_key", name="uq_source_document_key"),
        Index("ix_source_document_asof", "security_id", "document_type", "source_event_at", "fetched_at"),
        {"schema": "pit", "comment": "新闻稿、SEC文件、电话会等来源原文或原文链接。"},
    )

    source_document_id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="来源文档ID")
    security_id: Mapped[int] = mapped_column(ForeignKey("core.security.security_id"), nullable=False, comment="证券ID")
    document_type: Mapped[str] = mapped_column(String(64), nullable=False, comment="文档类型：press_release/sec_filing/earning_transcript等")
    document_key: Mapped[str] = mapped_column(String(512), nullable=False, comment="文档天然去重键")
    title: Mapped[str | None] = mapped_column(String(512), comment="文档标题")
    source_url: Mapped[str | None] = mapped_column(Text, comment="来源原文链接")
    source_event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment="文档对应事件时间")
    source_published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment="来源发布时间")
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="系统获取时间")
    content_type: Mapped[str | None] = mapped_column(String(64), comment="原文内容类型")
    object_uri: Mapped[str | None] = mapped_column(Text, comment="gzip原文文件路径")
    content_hash: Mapped[str | None] = mapped_column(String(64), comment="原文内容SHA256")
    content_length: Mapped[int | None] = mapped_column(Integer, comment="原文内容字节数")
    text_excerpt: Mapped[str | None] = mapped_column(Text, comment="原文文本预览")
    metadata_json: Mapped[dict | None] = mapped_column(JSONBType, comment="来源文档元数据")
    source_id: Mapped[int] = mapped_column(ForeignKey("core.data_source.source_id"), nullable=False, comment="数据源ID")
    raw_payload_id: Mapped[int] = mapped_column(ForeignKey("raw.payload.payload_id"), nullable=False, comment="原始载荷ID")
    data_hash: Mapped[str] = mapped_column(String(64), nullable=False, comment="标准化数据哈希")
    quality_flags: Mapped[dict | None] = mapped_column(JSONBType, comment="数据质量标记")
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, comment="入库时间")


class MacroEventSnapshot(Base):
    __tablename__ = "macro_event_snapshot"
    __table_args__ = (
        UniqueConstraint("event_key", "payload_hash", name="uq_macro_event_key_payload_hash"),
        Index("ix_macro_event_release_at", "release_at_utc"),
        Index("ix_macro_event_country", "country"),
        Index("ix_macro_event_name", "event_name"),
        Index("ix_macro_event_key", "event_key"),
        Index("ix_macro_event_observed_at", "observed_at_utc"),
        {"schema": "pit", "comment": "宏观经济日历事件PIT快照。"},
    )

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, comment="宏观事件快照ID")
    source: Mapped[str] = mapped_column(String(32), default="fmp", nullable=False, comment="数据源代码")
    provider_event_id: Mapped[str | None] = mapped_column(String(128), comment="数据源原始事件ID")
    event_key: Mapped[str] = mapped_column(String(128), nullable=False, comment="事件稳定唯一键")
    event_name: Mapped[str] = mapped_column(String(255), nullable=False, comment="英文事件名称")
    event_name_cn: Mapped[str | None] = mapped_column(String(255), comment="中文事件名称")
    country: Mapped[str | None] = mapped_column(String(64), comment="国家")
    currency: Mapped[str | None] = mapped_column(String(16), comment="货币代码")
    release_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment="计划公布时间UTC")
    impact: Mapped[str | None] = mapped_column(String(32), comment="重要程度")
    actual_raw: Mapped[str | None] = mapped_column(String(128), comment="实际值原始文本")
    estimate_raw: Mapped[str | None] = mapped_column(String(128), comment="预期值原始文本")
    previous_raw: Mapped[str | None] = mapped_column(String(128), comment="前值原始文本")
    actual_value: Mapped[Decimal | None] = mapped_column(Numeric(24, 8), comment="可解析实际值")
    estimate_value: Mapped[Decimal | None] = mapped_column(Numeric(24, 8), comment="可解析预期值")
    previous_value: Mapped[Decimal | None] = mapped_column(Numeric(24, 8), comment="可解析前值")
    unit: Mapped[str | None] = mapped_column(String(32), comment="单位")
    observed_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="系统获取到该版本数据的时间")
    is_backfill: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, comment="是否历史回填")
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False, comment="规范化JSON SHA256")
    raw_json: Mapped[dict] = mapped_column(JSONBType, nullable=False, comment="FMP原始JSON")
    source_id: Mapped[int] = mapped_column(ForeignKey("core.data_source.source_id"), nullable=False, comment="数据源ID")
    raw_payload_id: Mapped[int] = mapped_column(ForeignKey("raw.payload.payload_id"), nullable=False, comment="原始载荷ID")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, comment="入库时间")


class NewsItemSnapshot(Base):
    __tablename__ = "news_item_snapshot"
    __table_args__ = (
        UniqueConstraint(
            "security_id",
            "news_type",
            "published_at",
            "data_hash",
            name="uq_news_content_hash",
        ),
        Index("ix_news_asof", "security_id", "published_at", "fetched_at"),
        {"schema": "pit", "comment": "新闻和公告事件快照。"},
    )

    news_snapshot_id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="新闻快照ID")
    security_id: Mapped[int] = mapped_column(ForeignKey("core.security.security_id"), nullable=False, comment="证券ID")
    news_type: Mapped[str] = mapped_column(String(32), default="stock_news", comment="新闻类型：stock_news/press_release")
    title: Mapped[str | None] = mapped_column(String(512), comment="标题")
    url: Mapped[str | None] = mapped_column(Text, comment="原文URL")
    publisher: Mapped[str | None] = mapped_column(String(128), comment="发布方")
    author: Mapped[str | None] = mapped_column(String(128), comment="作者")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment="新闻发布时间")
    summary: Mapped[str | None] = mapped_column(Text, comment="正文摘要")
    image_url: Mapped[str | None] = mapped_column(Text, comment="图片URL")
    sentiment_label: Mapped[str | None] = mapped_column(String(32), comment="情绪标签")
    sentiment_score: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), comment="情绪分数")
    source_published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment="来源发布时间")
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="系统获取时间")
    source_id: Mapped[int] = mapped_column(ForeignKey("core.data_source.source_id"), nullable=False, comment="数据源ID")
    raw_payload_id: Mapped[int] = mapped_column(ForeignKey("raw.payload.payload_id"), nullable=False, comment="原始载荷ID")
    data_hash: Mapped[str] = mapped_column(String(64), nullable=False, comment="标准化数据哈希")
    quality_flags: Mapped[dict | None] = mapped_column(JSONBType, comment="数据质量标记")
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, comment="入库时间")


class DailyMarketBar(Base):
    __tablename__ = "daily_market_bar"
    __table_args__ = (
        UniqueConstraint("security_id", "trade_date", "data_hash", name="uq_daily_bar_content_hash"),
        Index("ix_daily_bar_asof", "security_id", "trade_date", "fetched_at"),
        {"schema": "pit", "comment": "日线行情版本表，同一交易日修订追加新版本。"},
    )

    daily_bar_id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="日线ID")
    security_id: Mapped[int] = mapped_column(ForeignKey("core.security.security_id"), nullable=False, comment="证券ID")
    trade_date: Mapped[date] = mapped_column(Date, nullable=False, comment="美股交易日期")
    open: Mapped[Decimal | None] = mapped_column(money_col, comment="开盘价")
    high: Mapped[Decimal | None] = mapped_column(money_col, comment="最高价")
    low: Mapped[Decimal | None] = mapped_column(money_col, comment="最低价")
    close: Mapped[Decimal | None] = mapped_column(money_col, comment="收盘价")
    adjusted_close: Mapped[Decimal | None] = mapped_column(money_col, comment="复权收盘价")
    volume: Mapped[Decimal | None] = mapped_column(Numeric(30, 4), comment="成交量")
    source_id: Mapped[int] = mapped_column(ForeignKey("core.data_source.source_id"), nullable=False, comment="数据源ID")
    source_published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment="来源发布时间")
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="系统获取时间")
    raw_payload_id: Mapped[int] = mapped_column(ForeignKey("raw.payload.payload_id"), nullable=False, comment="原始载荷ID")
    revision_no: Mapped[int] = mapped_column(Integer, default=1, comment="同一交易日修订版本号")
    data_hash: Mapped[str] = mapped_column(String(64), nullable=False, comment="标准化数据哈希")
    quality_flags: Mapped[dict | None] = mapped_column(JSONBType, comment="数据质量标记")
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, comment="入库时间")


class FinancialFactSnapshot(Base):
    __tablename__ = "financial_fact_snapshot"
    __table_args__ = (
        UniqueConstraint(
            "security_id",
            "dataset_code",
            "period_type",
            "fiscal_period_end",
            "data_hash",
            name="uq_financial_fact_content_hash",
        ),
        Index("ix_financial_fact_asof", "security_id", "dataset_code", "fiscal_period_end", "fetched_at"),
        {"schema": "pit", "comment": "财报、财务比率、关键指标和增长指标事实快照。"},
    )

    financial_fact_id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="财务事实快照ID")
    security_id: Mapped[int] = mapped_column(ForeignKey("core.security.security_id"), nullable=False, comment="证券ID")
    dataset_code: Mapped[str] = mapped_column(String(64), nullable=False, comment="财务数据集代码")
    period_type: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown", comment="周期类型：quarter/fiscal_year/ttm/unknown")
    fiscal_period_end: Mapped[date | None] = mapped_column(Date, comment="财报周期结束日")
    fiscal_year: Mapped[int | None] = mapped_column(Integer, comment="财年")
    fiscal_period: Mapped[str | None] = mapped_column(String(16), comment="财务期间，例如 Q1/FY")
    reported_currency: Mapped[str | None] = mapped_column(String(16), comment="报表货币")
    filing_date: Mapped[date | None] = mapped_column(Date, comment="文件披露日期")
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment="文件接受时间")
    source_published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment="来源发布时间")
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="系统获取时间")
    value_json: Mapped[dict] = mapped_column(JSONBType, nullable=False, comment="财务行轻量字段JSON，完整原始响应保存在raw.payload对象文件。")
    source_id: Mapped[int] = mapped_column(ForeignKey("core.data_source.source_id"), nullable=False, comment="数据源ID")
    raw_payload_id: Mapped[int] = mapped_column(ForeignKey("raw.payload.payload_id"), nullable=False, comment="原始载荷ID")
    data_hash: Mapped[str] = mapped_column(String(64), nullable=False, comment="标准化数据哈希")
    quality_flags: Mapped[dict | None] = mapped_column(JSONBType, comment="数据质量标记")
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, comment="入库时间")


class MetricObservation(Base):
    __tablename__ = "metric_observation"
    __table_args__ = (
        UniqueConstraint("security_id", "metric_code", "period_end", "data_hash", name="uq_metric_content_hash"),
        Index("ix_metric_asof", "security_id", "metric_code", "period_end", "fetched_at"),
        {"schema": "pit", "comment": "通用指标观察值表。"},
    )

    observation_id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="观察值ID")
    security_id: Mapped[int] = mapped_column(ForeignKey("core.security.security_id"), nullable=False, comment="证券ID")
    metric_code: Mapped[str] = mapped_column(ForeignKey("core.metric_definition.metric_code"), nullable=False, comment="指标代码")
    period_end: Mapped[date | None] = mapped_column(Date, comment="指标周期结束日")
    event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment="事件时间")
    source_published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment="来源发布时间")
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="系统获取时间")
    value_numeric: Mapped[Decimal | None] = mapped_column(money_col, comment="数值型取值")
    value_text: Mapped[str | None] = mapped_column(String(512), comment="文本型取值")
    value_json: Mapped[dict | None] = mapped_column(JSONBType, comment="JSON取值")
    unit: Mapped[str | None] = mapped_column(String(32), comment="单位")
    currency: Mapped[str | None] = mapped_column(String(16), comment="货币")
    source_id: Mapped[int] = mapped_column(ForeignKey("core.data_source.source_id"), nullable=False, comment="数据源ID")
    raw_payload_id: Mapped[int] = mapped_column(ForeignKey("raw.payload.payload_id"), nullable=False, comment="原始载荷ID")
    data_hash: Mapped[str] = mapped_column(String(64), nullable=False, comment="标准化数据哈希")
    quality_flags: Mapped[dict | None] = mapped_column(JSONBType, comment="数据质量标记")
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, comment="入库时间")
