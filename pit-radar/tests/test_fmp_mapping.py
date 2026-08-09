from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select

from pit_radar.collectors.base import CollectionContext, CollectionResult, RawCollectionItem
from pit_radar.db.models import AnalystSnapshot, EarningsCalendarSnapshot, EstimateSnapshot, MetricObservation, Security, SecurityIdentifier
from pit_radar.services.ingest import IngestService


@dataclass
class SinglePayloadCollector:
    dataset_code: str
    data: dict[str, Any]
    source_code: str = "fmp"
    source_published_at: datetime | None = None

    async def collect(self, context: CollectionContext) -> CollectionResult:
        return CollectionResult(
            items=[
                RawCollectionItem(
                    request_key=f"fmp-test:{self.dataset_code}:{self.data['symbol']}",
                    data=self.data,
                    http_status=200,
                    source_published_at=self.source_published_at,
                )
            ]
        )


def test_fmp_estimates_ratings_and_profile_fields_are_mapped(session, store):
    fetched_at = datetime(2026, 7, 14, 13, 30, tzinfo=UTC)
    payload = {
        "symbol": "MU",
        "profile": {
            "symbol": "MU",
            "companyName": "Micron Technology, Inc.",
            "exchange": "NASDAQ Global Select",
            "cik": "0000723125",
            "cusip": "595112103",
            "isin": "US5951121038",
            "currency": "USD",
            "sector": "Technology",
            "industry": "Semiconductors",
            "country": "US",
            "marketCap": 123456789,
            "price": 153.42,
            "beta": 1.27,
            "averageVolume": 22000000,
        },
        "estimates": [
            {
                "symbol": "MU",
                "date": "2025-08-28",
                "period": "annual",
                "revenueAvg": 37194840113,
                "epsAvg": 8.09168,
                "numAnalystsRevenue": 20,
                "numAnalystsEps": 20,
            },
            {
                "symbol": "MU",
                "date": "2028-11-28",
                "period": "quarter",
                "revenueLow": 63621134724,
                "revenueHigh": 84555976786,
                "revenueAvg": 73252550000,
                "epsAvg": 44.585,
                "epsHigh": 53.52875,
                "epsLow": 36.96422,
                "numAnalystsRevenue": 14,
                "numAnalystsEps": 15,
            }
        ],
        "price_target": {
            "symbol": "MU",
            "targetHigh": 2200,
            "targetLow": 1100,
            "targetConsensus": 1569.09,
            "targetMedian": 1512.5,
        },
        "price_target_summary": {
            "symbol": "MU",
            "lastMonthCount": 25,
            "lastMonthAvgPriceTarget": 1538.8,
            "publishers": "[\"TheFly\",\"StreetInsider\"]",
        },
        "grades_consensus": {
            "symbol": "MU",
            "strongBuy": 7,
            "buy": 12,
            "hold": 4,
            "sell": 1,
            "strongSell": 0,
            "consensus": "Buy",
        },
        "ratings_snapshot": {
            "symbol": "MU",
            "rating": "A-",
            "overallScore": 4,
            "discountedCashFlowScore": 3,
            "returnOnEquityScore": 5,
        },
    }

    service = IngestService(session, store)
    service.ingest(SinglePayloadCollector("estimates", payload), CollectionContext("live", ["MU"], fetched_at))
    session.commit()

    assert len(session.scalars(select(EstimateSnapshot)).all()) == 1
    estimate = session.scalar(select(EstimateSnapshot))
    assert estimate.period_type == "quarter"
    assert estimate.eps_mean == Decimal("44.585000")
    assert estimate.eps_high == Decimal("53.528750")
    assert estimate.analyst_count_eps == 15
    assert estimate.revenue_mean == Decimal("73252550000.000000")
    assert estimate.analyst_count_revenue == 14

    analyst = session.scalar(select(AnalystSnapshot))
    assert analyst.target_mean == Decimal("1569.090000")
    assert analyst.target_high == Decimal("2200.000000")
    assert analyst.buy_count == 12

    identifiers = set(session.execute(select(SecurityIdentifier.identifier_type, SecurityIdentifier.identifier_value)).all())
    assert ("cusip", "595112103") in identifiers
    assert ("isin", "US5951121038") in identifiers

    metrics = {row.metric_code: row for row in session.scalars(select(MetricObservation)).all()}
    assert metrics["market_cap"].value_numeric == Decimal("123456789.000000")
    assert metrics["analyst_target_median"].value_numeric == Decimal("1512.500000")
    assert metrics["analyst_rating_consensus"].value_text == "Buy"
    assert metrics["fmp_rating"].value_text == "A-"
    assert metrics["fmp_rating_overall_score"].value_numeric == Decimal("4.000000")
    assert metrics["fmp_rating_scores"].value_json["discountedCashFlowScore"] == 3


def test_fmp_earnings_without_fiscal_period_end_keeps_quality_flag(session, store):
    fetched_at = datetime(2026, 7, 14, 13, 30, tzinfo=UTC)
    source_published_at = datetime(2026, 7, 14, tzinfo=UTC)
    payload = {
        "symbol": "MU",
        "profile": {
            "symbol": "MU",
            "companyName": "Micron Technology, Inc.",
            "exchange": "NASDAQ Global Select",
        },
        "earnings": [
            {
                "symbol": "MU",
                "date": "2025-09-22",
                "epsEstimated": 8.1,
                "revenueEstimated": 37194840113,
                "lastUpdated": "2026-07-14",
            },
            {
                "symbol": "MU",
                "date": "2026-09-22",
                "epsActual": None,
                "epsEstimated": 31.29,
                "revenueActual": None,
                "revenueEstimated": 50393100000,
                "lastUpdated": "2026-07-14",
            }
        ],
    }

    service = IngestService(session, store)
    service.ingest(
        SinglePayloadCollector("earnings", payload, source_published_at=source_published_at),
        CollectionContext("live", ["MU"], fetched_at),
    )
    session.commit()

    assert len(session.scalars(select(EarningsCalendarSnapshot)).all()) == 1
    earnings = session.scalar(select(EarningsCalendarSnapshot))
    assert str(earnings.expected_report_date) == "2026-09-22"
    assert str(earnings.fiscal_period_end) == "2026-09-22"
    assert earnings.estimated_eps == Decimal("31.290000")
    assert earnings.estimated_revenue == Decimal("50393100000.000000")
    assert earnings.source_published_at.replace(tzinfo=UTC) == source_published_at
    assert earnings.quality_flags["fiscal_period_end_missing_using_report_date"] is True


def test_fmp_earnings_actuals_are_kept_for_past_reports(session, store):
    fetched_at = datetime(2026, 7, 14, 13, 30, tzinfo=UTC)
    payload = {
        "symbol": "MU",
        "profile": {
            "symbol": "MU",
            "companyName": "Micron Technology, Inc.",
            "exchange": "NASDAQ Global Select",
        },
        "earnings": [
            {
                "symbol": "MU",
                "date": "2026-06-25",
                "epsActual": 1.91,
                "epsEstimated": 1.60,
                "revenueActual": 9370000000,
                "revenueEstimated": 8880000000,
                "epsSurprise": 0.31,
                "epsSurprisePercent": 19.375,
                "revenueSurprise": 490000000,
                "revenueSurprisePercent": 5.518,
                "lastUpdated": "2026-06-26",
            }
        ],
    }

    service = IngestService(session, store)
    service.ingest(SinglePayloadCollector("earnings", payload), CollectionContext("live", ["MU"], fetched_at))
    session.commit()

    earnings = session.scalar(select(EarningsCalendarSnapshot))
    assert str(earnings.expected_report_date) == "2026-06-25"
    assert earnings.actual_eps == Decimal("1.910000")
    assert earnings.estimated_eps == Decimal("1.600000")
    assert earnings.actual_revenue == Decimal("9370000000.000000")
    assert earnings.estimated_revenue == Decimal("8880000000.000000")
    assert earnings.eps_surprise == Decimal("0.310000")
    assert earnings.eps_surprise_percent == Decimal("19.37500000")
    assert earnings.revenue_surprise == Decimal("490000000.000000")


def test_missing_profile_does_not_overwrite_existing_security_name(session, store):
    fetched_at = datetime(2026, 7, 14, 13, 30, tzinfo=UTC)
    session.add(Security(primary_ticker="MU", company_name="Micron Technology, Inc.", currency="USD", country="US"))
    session.commit()

    payload = {
        "symbol": "MU",
        "earnings": [
            {
                "symbol": "MU",
                "date": "2026-09-22",
                "epsEstimated": 31.29,
                "revenueEstimated": 50393100000,
            }
        ],
    }

    service = IngestService(session, store)
    service.ingest(SinglePayloadCollector("earnings", payload), CollectionContext("live", ["MU"], fetched_at))
    session.commit()

    security = session.scalar(select(Security).where(Security.primary_ticker == "MU"))
    assert security.company_name == "Micron Technology, Inc."
