from __future__ import annotations

import asyncio
import gzip
import hashlib
import json
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from pit_radar.collectors.base import CollectionContext, DataCollector, RawCollectionItem
from pit_radar.db.models import (
    AnalystSnapshot,
    DailyMarketBar,
    DataSource,
    EarningsCalendarSnapshot,
    EarningTranscriptSnapshot,
    EstimateSnapshot,
    FinancialFactSnapshot,
    IngestRun,
    MacroEventSnapshot,
    MetricDefinition,
    MetricObservation,
    NewsItemSnapshot,
    RawPayload,
    SecFilingSnapshot,
    Security,
    SecurityIdentifier,
    SourceDocumentSnapshot,
)
from pit_radar.parsers.base import (
    AnalystRecord,
    DailyBarRecord,
    EarningsRecord,
    EstimateRecord,
    FinancialFactRecord,
    MacroEventRecord,
    MetricRecord,
    NewsRecord,
    ParsedPayload,
    SecFilingRecord,
    SecurityRecord,
    SourceDocumentRecord,
    TranscriptRecord,
)
from pit_radar.parsers.fmp_like import parse_fmp_like_payload
from pit_radar.storage.base import RawObjectStore
from pit_radar.time import ensure_utc, to_new_york, utc_now


RESERVED_METRIC_DEFINITIONS = [
    MetricRecord(
        symbol="",
        metric_code="option_iv",
        display_name_zh="期权隐含波动率",
        description_zh="预留字段：FMP stable API 当前未提供期权链IV，后续接入专用期权数据源。",
        value_type="numeric",
        unit="ratio",
        frequency="daily",
    ),
    MetricRecord(
        symbol="",
        metric_code="borrow_fee",
        display_name_zh="借券费率",
        description_zh="预留字段：借券费通常需要券商或专门证券借贷数据源。",
        value_type="numeric",
        unit="ratio",
        frequency="daily",
    ),
    MetricRecord(
        symbol="",
        metric_code="short_interest",
        display_name_zh="空头持仓量",
        description_zh="预留字段：FMP FAQ 表示不提供 short interest，后续接入交易所或专门数据源。",
        value_type="numeric",
        unit="shares",
        frequency="semi_monthly",
    ),
]


class IngestService:
    def __init__(self, session: Session, store: RawObjectStore):
        self.session = session
        self.store = store

    def ingest(self, collector: DataCollector, context: CollectionContext) -> IngestRun:
        source = self._get_or_create_source(collector.source_code)
        self._ensure_reserved_metric_definitions()
        started_at = ensure_utc(utc_now())
        run = IngestRun(
            job_name=f"{collector.source_code}:{collector.dataset_code}",
            dataset_code=collector.dataset_code,
            source_id=source.source_id,
            collection_mode=context.collection_mode,
            scheduled_at=context.fetched_at,
            started_at=started_at,
            status="running",
            metadata_json={"symbols": context.symbols},
        )
        self.session.add(run)
        self.session.flush()

        result = asyncio.run(collector.collect(context))
        run.requested_count = len(context.symbols)
        run.failed_count = len(result.errors)
        run.error_message = "\n".join(result.errors) if result.errors else None

        for item in result.items:
            payload = self._store_payload(run, source, collector.dataset_code, item, context.fetched_at)
            parsed = parse_fmp_like_payload(collector.dataset_code, item.data, context.fetched_at)
            parsed, live_filter = _filter_forward_looking_live_records(parsed, context.collection_mode, context.fetched_at)
            if live_filter:
                metadata = dict(run.metadata_json or {})
                metadata["live_filter"] = _merge_live_filter(metadata.get("live_filter"), live_filter)
                run.metadata_json = metadata
            security_map = self._upsert_securities(parsed.securities, source.source_id, context.fetched_at)
            inserted = 0
            inserted += self._insert_estimates(parsed.estimates, security_map, source.source_id, payload)
            inserted += self._insert_analysts(parsed.analysts, security_map, source.source_id, payload)
            inserted += self._insert_earnings(parsed.earnings, security_map, source.source_id, payload)
            inserted += self._insert_daily_bars(parsed.daily_bars, security_map, source.source_id, payload)
            inserted += self._insert_news(parsed.news, security_map, source.source_id, payload)
            inserted += self._insert_financial_facts(parsed.financial_facts, security_map, source.source_id, payload)
            inserted += self._insert_sec_filings(parsed.sec_filings, security_map, source.source_id, payload)
            inserted += self._insert_transcripts(parsed.transcripts, security_map, source.source_id, payload)
            inserted += self._insert_source_documents(parsed.source_documents, security_map, source.source_id, payload)
            inserted += self._insert_macro_events(parsed.macro_events, source.source_id, payload, context.collection_mode)
            inserted += self._insert_metrics(parsed.metrics, security_map, source.source_id, payload)
            if inserted == 0:
                run.skipped_count += 1
            else:
                run.success_count += 1

        run.finished_at = ensure_utc(utc_now())
        if run.failed_count and run.success_count:
            run.status = "partial_success"
        elif run.failed_count and not run.success_count:
            run.status = "failed"
        else:
            run.status = "success"
        self.session.flush()
        return run

    def _get_or_create_source(self, source_code: str) -> DataSource:
        existing = self.session.scalar(select(DataSource).where(DataSource.source_code == source_code))
        if existing:
            return existing
        source = DataSource(
            source_code=source_code,
            source_name="Financial Modeling Prep" if source_code == "fmp" else "Mock Data Source",
            source_type="api" if source_code == "fmp" else "mock",
            base_url="https://fmp-distribution.onrender.com/api/fmp" if source_code == "fmp" else None,
            timezone="America/New_York" if source_code == "fmp" else "UTC",
        )
        self.session.add(source)
        self.session.flush()
        return source

    def _store_payload(
        self,
        run: IngestRun,
        source: DataSource,
        dataset_code: str,
        item: RawCollectionItem,
        fetched_at: datetime,
    ) -> RawPayload:
        raw_bytes = json.dumps(item.data, ensure_ascii=False, sort_keys=True, default=_json_default).encode("utf-8")
        content_hash = hashlib.sha256(raw_bytes).hexdigest()
        existing = self.session.scalar(
            select(RawPayload).where(
                RawPayload.source_id == source.source_id,
                RawPayload.dataset_code == dataset_code,
                RawPayload.request_key == item.request_key,
                RawPayload.fetched_at == ensure_utc(fetched_at),
                RawPayload.content_hash == content_hash,
            )
        )
        if existing:
            return existing

        compressed = gzip.compress(raw_bytes)
        fetched_utc = ensure_utc(fetched_at)
        path = (
            f"{dataset_code}/{source.source_code}/{fetched_utc.year:04d}/"
            f"{fetched_utc.month:02d}/{fetched_utc.day:02d}/{content_hash}.json.gz"
        )
        object_uri = self.store.put_bytes(path, compressed)
        payload = RawPayload(
            run_id=run.run_id,
            source_id=source.source_id,
            dataset_code=dataset_code,
            request_key=item.request_key,
            source_published_at=item.source_published_at,
            fetched_at=fetched_utc,
            content_hash=content_hash,
            object_uri=object_uri,
            http_status=item.http_status,
            metadata_json=item.metadata,
        )
        self.session.add(payload)
        self.session.flush()
        return payload

    def _upsert_securities(
        self,
        securities: list[SecurityRecord],
        source_id: int,
        observed_at: datetime,
    ) -> dict[str, Security]:
        output: dict[str, Security] = {}
        observed_at = ensure_utc(observed_at)
        for record in securities:
            security = None
            if record.cik:
                security = self.session.scalar(select(Security).where(Security.cik == record.cik))
            if security is None:
                security = self.session.scalar(select(Security).where(Security.primary_ticker == record.symbol))
            if security is None:
                security = Security(
                    company_name=record.company_name or record.symbol,
                    primary_ticker=record.symbol,
                    exchange=record.exchange,
                    cik=record.cik,
                    sector=record.sector,
                    industry=record.industry,
                    currency=record.currency,
                    country=record.country,
                    first_seen_at=observed_at,
                    last_seen_at=observed_at,
                )
                self.session.add(security)
                self.session.flush()
            else:
                security.company_name = record.company_name or security.company_name
                security.primary_ticker = record.symbol or security.primary_ticker
                security.exchange = record.exchange or security.exchange
                security.cik = record.cik or security.cik
                security.sector = record.sector or security.sector
                security.industry = record.industry or security.industry
                security.currency = record.currency or security.currency
                security.country = record.country or security.country
                security.last_seen_at = observed_at

            self._ensure_identifier(security.security_id, "ticker", record.symbol, source_id, observed_at)
            if record.cik:
                self._ensure_identifier(security.security_id, "cik", record.cik, source_id, observed_at)
            if record.cusip:
                self._ensure_identifier(security.security_id, "cusip", record.cusip, source_id, observed_at)
            if record.isin:
                self._ensure_identifier(security.security_id, "isin", record.isin, source_id, observed_at)
            output[record.symbol] = security
        self.session.flush()
        return output

    def _ensure_identifier(self, security_id: int, identifier_type: str, value: str, source_id: int, observed_at: datetime) -> None:
        existing = self.session.scalar(
            select(SecurityIdentifier).where(
                SecurityIdentifier.security_id == security_id,
                SecurityIdentifier.identifier_type == identifier_type,
                SecurityIdentifier.identifier_value == value,
                SecurityIdentifier.valid_to.is_(None),
            )
        )
        if existing is None:
            self.session.add(
                SecurityIdentifier(
                    security_id=security_id,
                    identifier_type=identifier_type,
                    identifier_value=value,
                    valid_from=observed_at,
                    source_id=source_id,
                )
            )

    def _insert_estimates(self, records: list[EstimateRecord], securities: dict[str, Security], source_id: int, payload: RawPayload) -> int:
        inserted = 0
        for record in records:
            security = securities.get(record.symbol)
            if not security:
                continue
            data_hash = _record_hash(record, exclude_fields={"snapshot_at"})
            exists = self.session.scalar(
                select(EstimateSnapshot.estimate_id).where(
                    EstimateSnapshot.security_id == security.security_id,
                    EstimateSnapshot.fiscal_period_end == record.fiscal_period_end,
                    EstimateSnapshot.period_type == record.period_type,
                    EstimateSnapshot.data_hash == data_hash,
                )
            )
            if exists:
                continue
            self.session.add(
                EstimateSnapshot(
                    security_id=security.security_id,
                    fiscal_period_end=record.fiscal_period_end,
                    period_type=record.period_type,
                    snapshot_at=record.snapshot_at,
                    source_published_at=payload.source_published_at,
                    fetched_at=payload.fetched_at,
                    eps_mean=record.eps_mean,
                    eps_high=record.eps_high,
                    eps_low=record.eps_low,
                    analyst_count_eps=record.analyst_count_eps,
                    revenue_mean=record.revenue_mean,
                    revenue_high=record.revenue_high,
                    revenue_low=record.revenue_low,
                    analyst_count_revenue=record.analyst_count_revenue,
                    currency=record.currency,
                    source_id=source_id,
                    raw_payload_id=payload.payload_id,
                    data_hash=data_hash,
                    quality_flags=record.quality_flags,
                )
            )
            inserted += 1
        return inserted

    def _insert_metrics(self, records: list[MetricRecord], securities: dict[str, Security], source_id: int, payload: RawPayload) -> int:
        inserted = 0
        for record in records:
            security = securities.get(record.symbol)
            if not security:
                continue
            self._ensure_metric_definition(record)
            data_hash = _record_hash(record, exclude_fields={"event_at"})
            exists = self.session.scalar(
                select(MetricObservation.observation_id).where(
                    MetricObservation.security_id == security.security_id,
                    MetricObservation.metric_code == record.metric_code,
                    MetricObservation.period_end == record.period_end,
                    MetricObservation.data_hash == data_hash,
                )
            )
            if exists:
                continue
            self.session.add(
                MetricObservation(
                    security_id=security.security_id,
                    metric_code=record.metric_code,
                    period_end=record.period_end,
                    event_at=record.event_at,
                    source_published_at=payload.source_published_at,
                    fetched_at=payload.fetched_at,
                    value_numeric=record.value_numeric,
                    value_text=record.value_text,
                    value_json=record.value_json,
                    unit=record.unit,
                    currency=record.currency,
                    source_id=source_id,
                    raw_payload_id=payload.payload_id,
                    data_hash=data_hash,
                    quality_flags=record.quality_flags,
                )
            )
            inserted += 1
        return inserted

    def _ensure_metric_definition(self, record: MetricRecord) -> None:
        existing = self.session.get(MetricDefinition, record.metric_code)
        if existing:
            return
        self.session.add(
            MetricDefinition(
                metric_code=record.metric_code,
                display_name_zh=record.display_name_zh or record.metric_code,
                description_zh=record.description_zh,
                value_type=record.value_type,
                unit=record.unit,
                frequency=record.frequency,
            )
        )
        self.session.flush()

    def _ensure_reserved_metric_definitions(self) -> None:
        for record in RESERVED_METRIC_DEFINITIONS:
            self._ensure_metric_definition(record)

    def _insert_analysts(self, records: list[AnalystRecord], securities: dict[str, Security], source_id: int, payload: RawPayload) -> int:
        inserted = 0
        for record in records:
            security = securities.get(record.symbol)
            if not security:
                continue
            data_hash = _record_hash(record, exclude_fields={"snapshot_at"})
            exists = self.session.scalar(
                select(AnalystSnapshot.analyst_snapshot_id).where(
                    AnalystSnapshot.security_id == security.security_id,
                    AnalystSnapshot.data_hash == data_hash,
                )
            )
            if exists:
                continue
            self.session.add(
                AnalystSnapshot(
                    security_id=security.security_id,
                    snapshot_at=record.snapshot_at,
                    source_published_at=payload.source_published_at,
                    fetched_at=payload.fetched_at,
                    target_mean=record.target_mean,
                    target_high=record.target_high,
                    target_low=record.target_low,
                    strong_buy_count=record.strong_buy_count,
                    buy_count=record.buy_count,
                    hold_count=record.hold_count,
                    sell_count=record.sell_count,
                    strong_sell_count=record.strong_sell_count,
                    source_id=source_id,
                    raw_payload_id=payload.payload_id,
                    data_hash=data_hash,
                    quality_flags=record.quality_flags,
                )
            )
            inserted += 1
        return inserted

    def _insert_earnings(self, records: list[EarningsRecord], securities: dict[str, Security], source_id: int, payload: RawPayload) -> int:
        inserted = 0
        for record in records:
            security = securities.get(record.symbol)
            if not security:
                continue
            data_hash = _record_hash(record, exclude_fields={"snapshot_at"})
            exists = self.session.scalar(
                select(EarningsCalendarSnapshot.earnings_snapshot_id).where(
                    EarningsCalendarSnapshot.security_id == security.security_id,
                    EarningsCalendarSnapshot.fiscal_period_end == record.fiscal_period_end,
                    EarningsCalendarSnapshot.data_hash == data_hash,
                )
            )
            if exists:
                continue
            self.session.add(
                EarningsCalendarSnapshot(
                    security_id=security.security_id,
                    fiscal_period_end=record.fiscal_period_end,
                    expected_report_date=record.expected_report_date,
                    expected_report_session=record.expected_report_session,
                    estimated_eps=record.estimated_eps,
                    estimated_revenue=record.estimated_revenue,
                    actual_eps=record.actual_eps,
                    actual_revenue=record.actual_revenue,
                    eps_surprise=record.eps_surprise,
                    eps_surprise_percent=record.eps_surprise_percent,
                    revenue_surprise=record.revenue_surprise,
                    revenue_surprise_percent=record.revenue_surprise_percent,
                    snapshot_at=record.snapshot_at,
                    source_published_at=payload.source_published_at,
                    fetched_at=payload.fetched_at,
                    source_id=source_id,
                    raw_payload_id=payload.payload_id,
                    data_hash=data_hash,
                    quality_flags=record.quality_flags,
                )
            )
            inserted += 1
        return inserted

    def _insert_daily_bars(self, records: list[DailyBarRecord], securities: dict[str, Security], source_id: int, payload: RawPayload) -> int:
        inserted = 0
        for record in records:
            security = securities.get(record.symbol)
            if not security:
                continue
            data_hash = _record_hash(record)
            exists = self.session.scalar(
                select(DailyMarketBar.daily_bar_id).where(
                    DailyMarketBar.security_id == security.security_id,
                    DailyMarketBar.trade_date == record.trade_date,
                    DailyMarketBar.data_hash == data_hash,
                )
            )
            if exists:
                continue
            revision = (
                self.session.scalar(
                    select(func.max(DailyMarketBar.revision_no)).where(
                        DailyMarketBar.security_id == security.security_id,
                        DailyMarketBar.trade_date == record.trade_date,
                    )
                )
                or 0
            ) + 1
            self.session.add(
                DailyMarketBar(
                    security_id=security.security_id,
                    trade_date=record.trade_date,
                    open=record.open,
                    high=record.high,
                    low=record.low,
                    close=record.close,
                    adjusted_close=record.adjusted_close,
                    volume=record.volume,
                    source_id=source_id,
                    source_published_at=payload.source_published_at,
                    fetched_at=payload.fetched_at,
                    raw_payload_id=payload.payload_id,
                    revision_no=revision,
                    data_hash=data_hash,
                    quality_flags=record.quality_flags,
                )
            )
            inserted += 1
        return inserted

    def _insert_sec_filings(
        self,
        records: list[SecFilingRecord],
        securities: dict[str, Security],
        source_id: int,
        payload: RawPayload,
    ) -> int:
        inserted = 0
        for record in records:
            security = securities.get(record.symbol)
            if not security:
                continue
            data_hash = _record_hash(record)
            exists = self._sec_filing_exists(security.security_id, record)
            if exists:
                continue
            self.session.add(
                SecFilingSnapshot(
                    security_id=security.security_id,
                    form_type=record.form_type,
                    filing_date=record.filing_date,
                    accepted_at=record.accepted_at,
                    cik=record.cik,
                    filing_url=record.filing_url,
                    final_url=record.final_url,
                    has_financials=record.has_financials,
                    source_published_at=record.source_published_at or payload.source_published_at,
                    fetched_at=payload.fetched_at,
                    value_json=record.value_json,
                    source_id=source_id,
                    raw_payload_id=payload.payload_id,
                    data_hash=data_hash,
                    quality_flags=record.quality_flags,
                )
            )
            inserted += 1
        return inserted

    def _sec_filing_exists(self, security_id: int, record: SecFilingRecord) -> int | None:
        if record.final_url:
            return self.session.scalar(
                select(SecFilingSnapshot.sec_filing_id).where(
                    SecFilingSnapshot.security_id == security_id,
                    SecFilingSnapshot.final_url == record.final_url,
                )
            )
        if record.filing_url:
            return self.session.scalar(
                select(SecFilingSnapshot.sec_filing_id).where(
                    SecFilingSnapshot.security_id == security_id,
                    SecFilingSnapshot.filing_url == record.filing_url,
                )
            )
        return self.session.scalar(
            select(SecFilingSnapshot.sec_filing_id).where(
                SecFilingSnapshot.security_id == security_id,
                SecFilingSnapshot.form_type == record.form_type,
                SecFilingSnapshot.accepted_at == record.accepted_at,
            )
        )

    def _insert_transcripts(
        self,
        records: list[TranscriptRecord],
        securities: dict[str, Security],
        source_id: int,
        payload: RawPayload,
    ) -> int:
        inserted = 0
        for record in records:
            security = securities.get(record.symbol)
            if not security:
                continue
            data_hash = _record_hash(record)
            exists = self.session.scalar(
                select(EarningTranscriptSnapshot.transcript_id).where(
                    EarningTranscriptSnapshot.security_id == security.security_id,
                    EarningTranscriptSnapshot.fiscal_year == record.fiscal_year,
                    EarningTranscriptSnapshot.fiscal_period == record.fiscal_period,
                )
            )
            if exists:
                continue
            self.session.add(
                EarningTranscriptSnapshot(
                    security_id=security.security_id,
                    fiscal_year=record.fiscal_year,
                    fiscal_period=record.fiscal_period,
                    call_date=record.call_date,
                    transcript_text=record.transcript_text,
                    word_count=record.word_count,
                    source_published_at=record.source_published_at or payload.source_published_at,
                    fetched_at=payload.fetched_at,
                    value_json=record.value_json,
                    source_id=source_id,
                    raw_payload_id=payload.payload_id,
                    data_hash=data_hash,
                    quality_flags=record.quality_flags,
                )
            )
            inserted += 1
        return inserted

    def _insert_source_documents(
        self,
        records: list[SourceDocumentRecord],
        securities: dict[str, Security],
        source_id: int,
        payload: RawPayload,
    ) -> int:
        inserted = 0
        for record in records:
            security = securities.get(record.symbol)
            if not security:
                continue
            exists = self.session.scalar(
                select(SourceDocumentSnapshot.source_document_id).where(
                    SourceDocumentSnapshot.security_id == security.security_id,
                    SourceDocumentSnapshot.document_type == record.document_type,
                    SourceDocumentSnapshot.document_key == record.document_key,
                )
            )
            if exists:
                continue
            content = record.content_text.encode("utf-8") if record.content_text else None
            content_hash = hashlib.sha256(content).hexdigest() if content else None
            object_uri = self._store_source_document_bytes(payload, record.document_type, content_hash, content) if content and content_hash else None
            quality_flags = dict(record.quality_flags or {})
            if content is None:
                quality_flags.setdefault("content_not_stored_link_only", True)
            data_hash = _record_hash(record)
            self.session.add(
                SourceDocumentSnapshot(
                    security_id=security.security_id,
                    document_type=record.document_type,
                    document_key=record.document_key,
                    title=record.title,
                    source_url=record.source_url,
                    source_event_at=record.source_event_at,
                    source_published_at=record.source_published_at or payload.source_published_at,
                    fetched_at=payload.fetched_at,
                    content_type=record.content_type,
                    object_uri=object_uri,
                    content_hash=content_hash,
                    content_length=len(content) if content else None,
                    text_excerpt=_excerpt(record.content_text),
                    metadata_json=record.metadata_json,
                    source_id=source_id,
                    raw_payload_id=payload.payload_id,
                    data_hash=data_hash,
                    quality_flags=quality_flags,
                )
            )
            inserted += 1
        return inserted

    def _store_source_document_bytes(self, payload: RawPayload, document_type: str, content_hash: str, content: bytes) -> str:
        fetched_utc = ensure_utc(payload.fetched_at)
        safe_type = "".join(char if char.isalnum() or char in {"_", "-"} else "_" for char in document_type)
        path = (
            f"source_documents/{safe_type}/{fetched_utc.year:04d}/"
            f"{fetched_utc.month:02d}/{fetched_utc.day:02d}/{content_hash}.txt.gz"
        )
        return self.store.put_bytes(path, gzip.compress(content))

    def _insert_macro_events(
        self,
        records: list[MacroEventRecord],
        source_id: int,
        payload: RawPayload,
        collection_mode: str,
    ) -> int:
        inserted = 0
        for record in records:
            exists = self.session.scalar(
                select(MacroEventSnapshot.id).where(
                    MacroEventSnapshot.event_key == record.event_key,
                    MacroEventSnapshot.payload_hash == record.payload_hash,
                )
            )
            if exists:
                continue
            self.session.add(
                MacroEventSnapshot(
                    source=record.source,
                    provider_event_id=record.provider_event_id,
                    event_key=record.event_key,
                    event_name=record.event_name,
                    event_name_cn=record.event_name_cn,
                    country=record.country,
                    currency=record.currency,
                    release_at_utc=record.release_at_utc,
                    impact=record.impact,
                    actual_raw=record.actual_raw,
                    estimate_raw=record.estimate_raw,
                    previous_raw=record.previous_raw,
                    actual_value=record.actual_value,
                    estimate_value=record.estimate_value,
                    previous_value=record.previous_value,
                    unit=record.unit,
                    observed_at_utc=record.observed_at_utc,
                    is_backfill=collection_mode == "backfill",
                    payload_hash=record.payload_hash,
                    raw_json=record.raw_json,
                    source_id=source_id,
                    raw_payload_id=payload.payload_id,
                )
            )
            inserted += 1
        return inserted

    def _insert_news(self, records: list[NewsRecord], securities: dict[str, Security], source_id: int, payload: RawPayload) -> int:
        inserted = 0
        for record in records:
            security = securities.get(record.symbol)
            if not security:
                continue
            data_hash = _record_hash(record)
            exists = self._news_exists(security.security_id, record)
            if exists:
                continue
            self.session.add(
                NewsItemSnapshot(
                    security_id=security.security_id,
                    news_type=record.news_type,
                    title=record.title,
                    url=record.url,
                    publisher=record.publisher,
                    author=record.author,
                    published_at=record.published_at,
                    summary=record.summary,
                    image_url=record.image_url,
                    sentiment_label=record.sentiment_label,
                    sentiment_score=record.sentiment_score,
                    source_published_at=record.source_published_at or payload.source_published_at,
                    fetched_at=payload.fetched_at,
                    source_id=source_id,
                    raw_payload_id=payload.payload_id,
                    data_hash=data_hash,
                    quality_flags=record.quality_flags,
                )
            )
            inserted += 1
        return inserted

    def _news_exists(self, security_id: int, record: NewsRecord) -> int | None:
        if record.url:
            return self.session.scalar(
                select(NewsItemSnapshot.news_snapshot_id).where(
                    NewsItemSnapshot.security_id == security_id,
                    NewsItemSnapshot.news_type == record.news_type,
                    NewsItemSnapshot.url == record.url,
                )
            )
        return self.session.scalar(
            select(NewsItemSnapshot.news_snapshot_id).where(
                NewsItemSnapshot.security_id == security_id,
                NewsItemSnapshot.news_type == record.news_type,
                NewsItemSnapshot.title == record.title,
                NewsItemSnapshot.published_at == record.published_at,
            )
        )

    def _insert_financial_facts(
        self,
        records: list[FinancialFactRecord],
        securities: dict[str, Security],
        source_id: int,
        payload: RawPayload,
    ) -> int:
        inserted = 0
        for record in records:
            security = securities.get(record.symbol)
            if not security:
                continue
            data_hash = _record_hash(record)
            exists = self.session.scalar(
                select(FinancialFactSnapshot.financial_fact_id).where(
                    FinancialFactSnapshot.security_id == security.security_id,
                    FinancialFactSnapshot.dataset_code == record.dataset_code,
                    FinancialFactSnapshot.period_type == record.period_type,
                    FinancialFactSnapshot.fiscal_period_end == record.fiscal_period_end,
                    FinancialFactSnapshot.data_hash == data_hash,
                )
            )
            if exists:
                continue
            self.session.add(
                FinancialFactSnapshot(
                    security_id=security.security_id,
                    dataset_code=record.dataset_code,
                    period_type=record.period_type,
                    fiscal_period_end=record.fiscal_period_end,
                    fiscal_year=record.fiscal_year,
                    fiscal_period=record.fiscal_period,
                    reported_currency=record.reported_currency,
                    filing_date=record.filing_date,
                    accepted_at=record.accepted_at,
                    source_published_at=record.source_published_at or payload.source_published_at,
                    fetched_at=payload.fetched_at,
                    value_json=record.value_json,
                    source_id=source_id,
                    raw_payload_id=payload.payload_id,
                    data_hash=data_hash,
                    quality_flags=record.quality_flags,
                )
            )
            inserted += 1
        return inserted


def _record_hash(record: object, exclude_fields: set[str] | None = None) -> str:
    if is_dataclass(record):
        value = asdict(record)
    else:
        value = record
    if exclude_fields and isinstance(value, dict):
        value = {key: item for key, item in value.items() if key not in exclude_fields}
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, default=_json_default).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def _filter_forward_looking_live_records(
    parsed: ParsedPayload,
    collection_mode: str,
    fetched_at: datetime,
) -> tuple[ParsedPayload, dict[str, int | str]]:
    if collection_mode != "live":
        return parsed, {}

    business_date = to_new_york(ensure_utc(fetched_at)).date()
    estimate_count = len(parsed.estimates)
    earnings_count = len(parsed.earnings)
    estimates = [record for record in parsed.estimates if record.fiscal_period_end >= business_date]
    earnings = [
        record
        for record in parsed.earnings
        if (record.expected_report_date or record.fiscal_period_end) >= business_date or _has_earnings_actuals(record)
    ]
    filtered = ParsedPayload(
        securities=parsed.securities,
        estimates=estimates,
        analysts=parsed.analysts,
        earnings=earnings,
        daily_bars=parsed.daily_bars,
        news=parsed.news,
        financial_facts=parsed.financial_facts,
        sec_filings=parsed.sec_filings,
        transcripts=parsed.transcripts,
        source_documents=parsed.source_documents,
        macro_events=parsed.macro_events,
        metrics=parsed.metrics,
    )
    skipped = {
        "business_date": business_date.isoformat(),
        "skipped_past_estimates": estimate_count - len(estimates),
        "skipped_past_earnings": earnings_count - len(earnings),
    }
    return filtered, {key: value for key, value in skipped.items() if value}


def _merge_live_filter(existing: Any, incoming: dict[str, int | str]) -> dict[str, int | str]:
    merged = dict(existing) if isinstance(existing, dict) else {}
    if "business_date" in incoming:
        merged["business_date"] = incoming["business_date"]
    for key in ("skipped_past_estimates", "skipped_past_earnings"):
        merged[key] = int(merged.get(key, 0) or 0) + int(incoming.get(key, 0) or 0)
        if merged[key] == 0:
            merged.pop(key)
    return merged


def _has_earnings_actuals(record: EarningsRecord) -> bool:
    return any(
        value is not None
        for value in (
            record.actual_eps,
            record.actual_revenue,
            record.eps_surprise,
            record.eps_surprise_percent,
            record.revenue_surprise,
            record.revenue_surprise_percent,
        )
    )


def _excerpt(value: str | None, limit: int = 1200) -> str | None:
    if not value:
        return None
    compact = " ".join(value.split())
    return compact[:limit]
