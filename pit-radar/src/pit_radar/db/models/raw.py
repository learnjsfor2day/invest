from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from pit_radar.db.base import Base
from pit_radar.db.types import JSONBType
from pit_radar.time import utc_now


class IngestRun(Base):
    __tablename__ = "ingest_run"
    __table_args__ = ({"schema": "raw", "comment": "采集任务运行记录表。"},)

    run_id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="采集运行ID")
    job_name: Mapped[str] = mapped_column(String(128), nullable=False, comment="任务名称")
    dataset_code: Mapped[str] = mapped_column(String(64), nullable=False, comment="数据集代码")
    source_id: Mapped[int] = mapped_column(ForeignKey("core.data_source.source_id"), nullable=False, comment="数据源ID")
    collection_mode: Mapped[str] = mapped_column(String(32), nullable=False, comment="采集模式：live/backfill/replay")
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment="计划执行时间")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment="开始时间")
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment="结束时间")
    status: Mapped[str] = mapped_column(String(32), default="pending", comment="任务状态")
    requested_count: Mapped[int] = mapped_column(Integer, default=0, comment="请求数量")
    success_count: Mapped[int] = mapped_column(Integer, default=0, comment="成功数量")
    failed_count: Mapped[int] = mapped_column(Integer, default=0, comment="失败数量")
    skipped_count: Mapped[int] = mapped_column(Integer, default=0, comment="跳过数量")
    error_message: Mapped[str | None] = mapped_column(Text, comment="错误信息")
    metadata_json: Mapped[dict | None] = mapped_column(JSONBType, comment="任务元数据")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, comment="创建时间")


class RawPayload(Base):
    __tablename__ = "payload"
    __table_args__ = (
        UniqueConstraint("source_id", "dataset_code", "request_key", "fetched_at", "content_hash", name="uq_payload_fetch_hash"),
        {"schema": "raw", "comment": "原始响应元数据表，原始JSON以gzip文件保存。"},
    )

    payload_id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="原始载荷ID")
    run_id: Mapped[int] = mapped_column(ForeignKey("raw.ingest_run.run_id"), nullable=False, index=True, comment="采集运行ID")
    source_id: Mapped[int] = mapped_column(ForeignKey("core.data_source.source_id"), nullable=False, comment="数据源ID")
    dataset_code: Mapped[str] = mapped_column(String(64), nullable=False, comment="数据集代码")
    request_key: Mapped[str] = mapped_column(String(255), nullable=False, comment="请求唯一键")
    source_published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment="来源发布时间")
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True, comment="系统获取时间")
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, comment="原始内容SHA256")
    object_uri: Mapped[str] = mapped_column(Text, nullable=False, comment="gzip原始文件路径")
    content_type: Mapped[str] = mapped_column(String(64), default="application/json", comment="内容类型")
    compression: Mapped[str] = mapped_column(String(16), default="gzip", comment="压缩方式")
    http_status: Mapped[int | None] = mapped_column(Integer, comment="HTTP状态码")
    parser_version: Mapped[str] = mapped_column(String(32), default="v1", comment="解析器版本")
    schema_version: Mapped[str] = mapped_column(String(32), default="v1", comment="数据结构版本")
    metadata_json: Mapped[dict | None] = mapped_column(JSONBType, comment="元数据")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, comment="创建时间")


class DatasetCoverage(Base):
    __tablename__ = "dataset_coverage"
    __table_args__ = (
        UniqueConstraint("source_code", "dataset_code", "symbol", name="uq_dataset_coverage_source_dataset_symbol"),
        Index("ix_dataset_coverage_status_retry", "source_code", "dataset_code", "status", "next_check_after"),
        {"schema": "raw", "comment": "采集覆盖状态表，记录已确认有数据、无数据或暂时失败的标的。"},
    )

    coverage_id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="覆盖状态ID")
    source_code: Mapped[str] = mapped_column(String(64), nullable=False, default="fmp", comment="数据源代码")
    dataset_code: Mapped[str] = mapped_column(String(64), nullable=False, comment="数据集代码")
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, comment="股票代码")
    security_id: Mapped[int | None] = mapped_column(ForeignKey("core.security.security_id"), comment="证券ID")
    status: Mapped[str] = mapped_column(String(32), nullable=False, comment="状态：ok/no_data/unsupported/transient_failed")
    last_checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="最近检查时间")
    next_check_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment="下次允许重试时间")
    failure_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False, comment="连续失败次数")
    last_error: Mapped[str | None] = mapped_column(Text, comment="最近错误或无数据原因")
    metadata_json: Mapped[dict | None] = mapped_column(JSONBType, comment="覆盖状态元数据")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, comment="更新时间")
