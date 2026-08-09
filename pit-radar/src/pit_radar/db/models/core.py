from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pit_radar.db.base import Base
from pit_radar.time import utc_now


class Security(Base):
    __tablename__ = "security"
    __table_args__ = (
        UniqueConstraint("cik", name="uq_security_cik"),
        {"schema": "core", "comment": "证券主体表，内部统一使用 security_id，不使用 ticker 作为主键。"},
    )

    security_id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="证券内部稳定ID")
    company_name: Mapped[str] = mapped_column(String(255), comment="公司名称")
    primary_ticker: Mapped[str] = mapped_column(String(32), index=True, comment="当前主要展示 ticker")
    exchange: Mapped[str | None] = mapped_column(String(64), comment="交易所")
    cik: Mapped[str | None] = mapped_column(String(32), comment="SEC CIK")
    asset_type: Mapped[str] = mapped_column(String(32), default="stock", comment="资产类型")
    sector: Mapped[str | None] = mapped_column(String(128), comment="行业大类")
    industry: Mapped[str | None] = mapped_column(String(128), comment="细分行业")
    currency: Mapped[str | None] = mapped_column(String(16), default="USD", comment="交易货币")
    country: Mapped[str | None] = mapped_column(String(64), default="US", comment="国家或地区")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否活跃")
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, comment="首次发现时间")
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, comment="最近观察时间")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, comment="更新时间")

    identifiers: Mapped[list[SecurityIdentifier]] = relationship(back_populates="security")


class DataSource(Base):
    __tablename__ = "data_source"
    __table_args__ = (
        UniqueConstraint("source_code", name="uq_data_source_code"),
        {"schema": "core", "comment": "数据源定义表。"},
    )

    source_id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="数据源ID")
    source_code: Mapped[str] = mapped_column(String(64), nullable=False, comment="数据源代码")
    source_name: Mapped[str] = mapped_column(String(128), nullable=False, comment="数据源名称")
    source_type: Mapped[str] = mapped_column(String(64), nullable=False, comment="数据源类型")
    base_url: Mapped[str | None] = mapped_column(Text, comment="数据源基础URL")
    timezone: Mapped[str] = mapped_column(String(64), default="UTC", comment="数据源默认时区")
    priority: Mapped[int] = mapped_column(Integer, default=100, comment="数据源优先级")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否启用")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, comment="更新时间")


class SecurityIdentifier(Base):
    __tablename__ = "security_identifier"
    __table_args__ = (
        UniqueConstraint("identifier_type", "identifier_value", "valid_from", name="uq_security_identifier_value_from"),
        {"schema": "core", "comment": "证券历史标识符表，支持 ticker、CIK、FIGI、CUSIP、ISIN 等。"},
    )

    identifier_id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="标识符ID")
    security_id: Mapped[int] = mapped_column(ForeignKey("core.security.security_id"), nullable=False, index=True, comment="证券ID")
    identifier_type: Mapped[str] = mapped_column(String(32), nullable=False, comment="标识符类型")
    identifier_value: Mapped[str] = mapped_column(String(128), nullable=False, index=True, comment="标识符取值")
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="生效时间")
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment="失效时间")
    source_id: Mapped[int | None] = mapped_column(ForeignKey("core.data_source.source_id"), comment="来源ID")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, comment="创建时间")

    security: Mapped[Security] = relationship(back_populates="identifiers")


class MetricDefinition(Base):
    __tablename__ = "metric_definition"
    __table_args__ = ({"schema": "core", "comment": "通用指标定义表。"},)

    metric_code: Mapped[str] = mapped_column(String(64), primary_key=True, comment="指标代码")
    display_name_zh: Mapped[str] = mapped_column(String(128), comment="中文展示名")
    description_zh: Mapped[str | None] = mapped_column(Text, comment="中文说明")
    value_type: Mapped[str] = mapped_column(String(32), comment="值类型")
    unit: Mapped[str | None] = mapped_column(String(32), comment="单位")
    frequency: Mapped[str | None] = mapped_column(String(32), comment="频率")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, comment="更新时间")
