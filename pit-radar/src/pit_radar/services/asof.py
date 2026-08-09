from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import Row, and_, desc, func, or_, select
from sqlalchemy.orm import Session

from pit_radar.db.models import (
    AnalystSnapshot,
    DailyMarketBar,
    EarningsCalendarSnapshot,
    EarningTranscriptSnapshot,
    EstimateSnapshot,
    FinancialFactSnapshot,
    IngestRun,
    MetricObservation,
    NewsItemSnapshot,
    RawPayload,
    SecFilingSnapshot,
    Security,
    SecurityIdentifier,
    SourceDocumentSnapshot,
)
from pit_radar.time import ensure_utc


class AsOfService:
    def __init__(self, session: Session):
        self.session = session

    def resolve_security_id(self, ticker: str, cutoff_time: datetime | None = None) -> int | None:
        cutoff = ensure_utc(cutoff_time) if cutoff_time else None
        stmt = select(SecurityIdentifier.security_id).where(
            SecurityIdentifier.identifier_type == "ticker",
            SecurityIdentifier.identifier_value == ticker.upper(),
        )
        if cutoff:
            stmt = stmt.where(SecurityIdentifier.valid_from <= cutoff).where(
                or_(SecurityIdentifier.valid_to.is_(None), SecurityIdentifier.valid_to > cutoff)
            )
        stmt = stmt.order_by(desc(SecurityIdentifier.valid_from))
        return self.session.scalar(stmt)

    def get_identifier_as_of(self, security_id: int, cutoff_time: datetime, identifier_type: str = "ticker") -> SecurityIdentifier | None:
        cutoff = ensure_utc(cutoff_time)
        return self.session.scalar(
            select(SecurityIdentifier)
            .where(
                SecurityIdentifier.security_id == security_id,
                SecurityIdentifier.identifier_type == identifier_type,
                SecurityIdentifier.valid_from <= cutoff,
                or_(SecurityIdentifier.valid_to.is_(None), SecurityIdentifier.valid_to > cutoff),
            )
            .order_by(desc(SecurityIdentifier.valid_from))
        )

    def get_estimates_as_of(
        self,
        security_ids: list[int],
        cutoff_time: datetime,
        fiscal_period_end: date | None = None,
        strict_live: bool = True,
    ) -> list[EstimateSnapshot]:
        stmt = self._latest_stmt(
            EstimateSnapshot,
            [EstimateSnapshot.security_id, EstimateSnapshot.fiscal_period_end, EstimateSnapshot.period_type],
            cutoff_time,
            strict_live,
        ).where(EstimateSnapshot.security_id.in_(security_ids))
        if fiscal_period_end:
            stmt = stmt.where(EstimateSnapshot.fiscal_period_end == fiscal_period_end)
        return list(self.session.scalars(stmt))

    def get_analyst_snapshot_as_of(
        self,
        security_ids: list[int],
        cutoff_time: datetime,
        strict_live: bool = True,
    ) -> list[AnalystSnapshot]:
        stmt = self._latest_stmt(
            AnalystSnapshot,
            [AnalystSnapshot.security_id],
            cutoff_time,
            strict_live,
        ).where(AnalystSnapshot.security_id.in_(security_ids))
        return list(self.session.scalars(stmt))

    def get_earnings_calendar_as_of(
        self,
        security_ids: list[int],
        cutoff_time: datetime,
        strict_live: bool = True,
    ) -> list[EarningsCalendarSnapshot]:
        stmt = self._latest_stmt(
            EarningsCalendarSnapshot,
            [EarningsCalendarSnapshot.security_id, EarningsCalendarSnapshot.fiscal_period_end],
            cutoff_time,
            strict_live,
        ).where(EarningsCalendarSnapshot.security_id.in_(security_ids))
        return list(self.session.scalars(stmt))

    def get_daily_market_bars_as_of(
        self,
        security_ids: list[int],
        cutoff_time: datetime,
        strict_live: bool = True,
    ) -> list[DailyMarketBar]:
        stmt = self._latest_stmt(
            DailyMarketBar,
            [DailyMarketBar.security_id, DailyMarketBar.trade_date],
            cutoff_time,
            strict_live,
        ).where(DailyMarketBar.security_id.in_(security_ids))
        return list(self.session.scalars(stmt))

    def get_metrics_as_of(
        self,
        security_ids: list[int],
        cutoff_time: datetime,
        metric_code: str | None = None,
        strict_live: bool = True,
    ) -> list[MetricObservation]:
        stmt = self._latest_stmt(
            MetricObservation,
            [MetricObservation.security_id, MetricObservation.metric_code, MetricObservation.period_end],
            cutoff_time,
            strict_live,
        ).where(MetricObservation.security_id.in_(security_ids))
        if metric_code:
            stmt = stmt.where(MetricObservation.metric_code == metric_code)
        return list(self.session.scalars(stmt))

    def get_news_as_of(
        self,
        security_ids: list[int],
        cutoff_time: datetime,
        strict_live: bool = True,
        limit: int = 50,
    ) -> list[NewsItemSnapshot]:
        stmt = self._latest_stmt(
            NewsItemSnapshot,
            [
                NewsItemSnapshot.security_id,
                NewsItemSnapshot.news_type,
                NewsItemSnapshot.url,
                NewsItemSnapshot.title,
                NewsItemSnapshot.published_at,
            ],
            cutoff_time,
            strict_live,
        ).where(NewsItemSnapshot.security_id.in_(security_ids))
        stmt = stmt.order_by(desc(NewsItemSnapshot.published_at), desc(NewsItemSnapshot.fetched_at)).limit(limit)
        return list(self.session.scalars(stmt))

    def get_financial_facts_as_of(
        self,
        security_ids: list[int],
        cutoff_time: datetime,
        dataset_code: str | None = None,
        strict_live: bool = True,
    ) -> list[FinancialFactSnapshot]:
        stmt = self._latest_stmt(
            FinancialFactSnapshot,
            [
                FinancialFactSnapshot.security_id,
                FinancialFactSnapshot.dataset_code,
                FinancialFactSnapshot.period_type,
                FinancialFactSnapshot.fiscal_period_end,
            ],
            cutoff_time,
            strict_live,
        ).where(FinancialFactSnapshot.security_id.in_(security_ids))
        if dataset_code:
            stmt = stmt.where(FinancialFactSnapshot.dataset_code == dataset_code)
        stmt = stmt.order_by(FinancialFactSnapshot.dataset_code, desc(FinancialFactSnapshot.fiscal_period_end))
        return list(self.session.scalars(stmt))

    def get_sec_filings_as_of(
        self,
        security_ids: list[int],
        cutoff_time: datetime,
        form_type: str | None = None,
        strict_live: bool = True,
        limit: int = 50,
    ) -> list[SecFilingSnapshot]:
        stmt = self._latest_stmt(
            SecFilingSnapshot,
            [SecFilingSnapshot.security_id, SecFilingSnapshot.form_type, SecFilingSnapshot.accepted_at],
            cutoff_time,
            strict_live,
        ).where(SecFilingSnapshot.security_id.in_(security_ids))
        if form_type:
            stmt = stmt.where(SecFilingSnapshot.form_type == form_type)
        stmt = stmt.order_by(desc(SecFilingSnapshot.accepted_at), desc(SecFilingSnapshot.fetched_at)).limit(limit)
        return list(self.session.scalars(stmt))

    def get_transcripts_as_of(
        self,
        security_ids: list[int],
        cutoff_time: datetime,
        strict_live: bool = True,
        limit: int = 20,
    ) -> list[EarningTranscriptSnapshot]:
        stmt = self._latest_stmt(
            EarningTranscriptSnapshot,
            [EarningTranscriptSnapshot.security_id, EarningTranscriptSnapshot.fiscal_year, EarningTranscriptSnapshot.fiscal_period],
            cutoff_time,
            strict_live,
        ).where(EarningTranscriptSnapshot.security_id.in_(security_ids))
        stmt = stmt.order_by(desc(EarningTranscriptSnapshot.fiscal_year), desc(EarningTranscriptSnapshot.fiscal_period)).limit(limit)
        return list(self.session.scalars(stmt))

    def get_source_documents_as_of(
        self,
        security_ids: list[int],
        cutoff_time: datetime,
        strict_live: bool = True,
        limit: int = 100,
    ) -> list[SourceDocumentSnapshot]:
        stmt = self._latest_stmt(
            SourceDocumentSnapshot,
            [SourceDocumentSnapshot.security_id, SourceDocumentSnapshot.document_type, SourceDocumentSnapshot.document_key],
            cutoff_time,
            strict_live,
        ).where(SourceDocumentSnapshot.security_id.in_(security_ids))
        stmt = stmt.order_by(desc(SourceDocumentSnapshot.source_event_at), desc(SourceDocumentSnapshot.fetched_at)).limit(limit)
        return list(self.session.scalars(stmt))

    def snapshot_for_ticker(self, ticker: str, cutoff_time: datetime, strict_live: bool = True) -> dict[str, Any]:
        security_id = self.resolve_security_id(ticker, cutoff_time)
        if security_id is None:
            return {"ticker": ticker.upper(), "security": None}
        security = self.session.get(Security, security_id)
        return {
            "ticker": ticker.upper(),
            "security": security,
            "identifier": self.get_identifier_as_of(security_id, cutoff_time),
            "estimates": self.get_estimates_as_of([security_id], cutoff_time, strict_live=strict_live),
            "analyst": self.get_analyst_snapshot_as_of([security_id], cutoff_time, strict_live=strict_live),
            "earnings": self.get_earnings_calendar_as_of([security_id], cutoff_time, strict_live=strict_live),
            "daily_bars": self.get_daily_market_bars_as_of([security_id], cutoff_time, strict_live=strict_live),
            "news": self.get_news_as_of([security_id], cutoff_time, strict_live=strict_live),
            "financial_facts": self.get_financial_facts_as_of([security_id], cutoff_time, strict_live=strict_live),
            "sec_filings": self.get_sec_filings_as_of([security_id], cutoff_time, strict_live=strict_live),
            "transcripts": self.get_transcripts_as_of([security_id], cutoff_time, strict_live=strict_live),
            "source_documents": self.get_source_documents_as_of([security_id], cutoff_time, strict_live=strict_live),
            "metrics": self.get_metrics_as_of([security_id], cutoff_time, strict_live=strict_live),
        }

    def _latest_stmt(self, model, partition_cols: list, cutoff_time: datetime, strict_live: bool):
        cutoff = ensure_utc(cutoff_time)
        pk_col = list(model.__table__.primary_key.columns)[0]
        row_number = func.row_number().over(
            partition_by=partition_cols,
            order_by=(desc(model.fetched_at), desc(model.recorded_at)),
        ).label("rn")
        subq = (
            select(model.__table__.c, row_number)
            .join(RawPayload, model.raw_payload_id == RawPayload.payload_id)
            .join(IngestRun, RawPayload.run_id == IngestRun.run_id)
            .where(model.fetched_at <= cutoff)
        )
        if strict_live:
            subq = subq.where(IngestRun.collection_mode == "live")
        ranked = subq.subquery()
        return select(model).join(ranked, pk_col == ranked.c[pk_col.name]).where(ranked.c.rn == 1)
