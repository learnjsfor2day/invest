from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class SecurityRecord:
    symbol: str
    company_name: str | None = None
    exchange: str | None = None
    cik: str | None = None
    cusip: str | None = None
    isin: str | None = None
    sector: str | None = None
    industry: str | None = None
    currency: str | None = "USD"
    country: str | None = "US"


@dataclass(frozen=True)
class EstimateRecord:
    symbol: str
    fiscal_period_end: date
    period_type: str
    snapshot_at: datetime
    eps_mean: Decimal | None = None
    eps_high: Decimal | None = None
    eps_low: Decimal | None = None
    analyst_count_eps: int | None = None
    revenue_mean: Decimal | None = None
    revenue_high: Decimal | None = None
    revenue_low: Decimal | None = None
    analyst_count_revenue: int | None = None
    currency: str | None = "USD"
    quality_flags: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AnalystRecord:
    symbol: str
    snapshot_at: datetime
    target_mean: Decimal | None = None
    target_high: Decimal | None = None
    target_low: Decimal | None = None
    strong_buy_count: int | None = None
    buy_count: int | None = None
    hold_count: int | None = None
    sell_count: int | None = None
    strong_sell_count: int | None = None
    quality_flags: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EarningsRecord:
    symbol: str
    fiscal_period_end: date
    snapshot_at: datetime
    expected_report_date: date | None = None
    expected_report_session: str = "unknown"
    estimated_eps: Decimal | None = None
    estimated_revenue: Decimal | None = None
    actual_eps: Decimal | None = None
    actual_revenue: Decimal | None = None
    eps_surprise: Decimal | None = None
    eps_surprise_percent: Decimal | None = None
    revenue_surprise: Decimal | None = None
    revenue_surprise_percent: Decimal | None = None
    quality_flags: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DailyBarRecord:
    symbol: str
    trade_date: date
    open: Decimal | None
    high: Decimal | None
    low: Decimal | None
    close: Decimal | None
    adjusted_close: Decimal | None
    volume: Decimal | None
    quality_flags: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class NewsRecord:
    symbol: str
    news_type: str
    published_at: datetime | None = None
    title: str | None = None
    url: str | None = None
    publisher: str | None = None
    author: str | None = None
    summary: str | None = None
    image_url: str | None = None
    sentiment_label: str | None = None
    sentiment_score: Decimal | None = None
    source_published_at: datetime | None = None
    quality_flags: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FinancialFactRecord:
    symbol: str
    dataset_code: str
    period_type: str
    fiscal_period_end: date | None = None
    fiscal_year: int | None = None
    fiscal_period: str | None = None
    reported_currency: str | None = None
    filing_date: date | None = None
    accepted_at: datetime | None = None
    source_published_at: datetime | None = None
    value_json: dict[str, Any] = field(default_factory=dict)
    quality_flags: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SecFilingRecord:
    symbol: str
    form_type: str | None = None
    filing_date: date | None = None
    accepted_at: datetime | None = None
    cik: str | None = None
    filing_url: str | None = None
    final_url: str | None = None
    has_financials: bool | None = None
    source_published_at: datetime | None = None
    value_json: dict[str, Any] = field(default_factory=dict)
    quality_flags: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TranscriptRecord:
    symbol: str
    fiscal_year: int | None = None
    fiscal_period: str | None = None
    call_date: date | None = None
    transcript_text: str | None = None
    word_count: int | None = None
    source_published_at: datetime | None = None
    value_json: dict[str, Any] = field(default_factory=dict)
    quality_flags: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SourceDocumentRecord:
    symbol: str
    document_type: str
    document_key: str
    title: str | None = None
    source_url: str | None = None
    source_event_at: datetime | None = None
    source_published_at: datetime | None = None
    content_text: str | None = None
    content_type: str | None = "text/plain"
    metadata_json: dict[str, Any] = field(default_factory=dict)
    quality_flags: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MacroEventRecord:
    source: str
    provider_event_id: str | None
    event_key: str
    event_name: str
    event_name_cn: str | None
    country: str | None
    currency: str | None
    release_at_utc: datetime | None
    impact: str | None
    actual_raw: str | None
    estimate_raw: str | None
    previous_raw: str | None
    actual_value: Decimal | None
    estimate_value: Decimal | None
    previous_value: Decimal | None
    unit: str | None
    observed_at_utc: datetime
    payload_hash: str
    raw_json: dict[str, Any]


@dataclass(frozen=True)
class MetricRecord:
    symbol: str
    metric_code: str
    event_at: datetime | None = None
    period_end: date | None = None
    value_numeric: Decimal | None = None
    value_text: str | None = None
    value_json: dict[str, Any] | None = None
    unit: str | None = None
    currency: str | None = None
    display_name_zh: str | None = None
    description_zh: str | None = None
    value_type: str = "numeric"
    frequency: str | None = "snapshot"
    quality_flags: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ParsedPayload:
    securities: list[SecurityRecord] = field(default_factory=list)
    estimates: list[EstimateRecord] = field(default_factory=list)
    analysts: list[AnalystRecord] = field(default_factory=list)
    earnings: list[EarningsRecord] = field(default_factory=list)
    daily_bars: list[DailyBarRecord] = field(default_factory=list)
    news: list[NewsRecord] = field(default_factory=list)
    financial_facts: list[FinancialFactRecord] = field(default_factory=list)
    sec_filings: list[SecFilingRecord] = field(default_factory=list)
    transcripts: list[TranscriptRecord] = field(default_factory=list)
    source_documents: list[SourceDocumentRecord] = field(default_factory=list)
    macro_events: list[MacroEventRecord] = field(default_factory=list)
    metrics: list[MetricRecord] = field(default_factory=list)
