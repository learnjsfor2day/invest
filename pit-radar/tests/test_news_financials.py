from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import gzip
from typing import Any

from sqlalchemy import select

from pit_radar.collectors.base import CollectionContext, CollectionResult, RawCollectionItem
from pit_radar.db.models import (
    EarningTranscriptSnapshot,
    FinancialFactSnapshot,
    MetricDefinition,
    NewsItemSnapshot,
    SecFilingSnapshot,
    SourceDocumentSnapshot,
)
from pit_radar.services.ingest import IngestService


@dataclass
class SinglePayloadCollector:
    dataset_code: str
    data: dict[str, Any]
    source_code: str = "fmp"

    async def collect(self, context: CollectionContext) -> CollectionResult:
        return CollectionResult(
            items=[
                RawCollectionItem(
                    request_key=f"fmp-test:{self.dataset_code}:{self.data['symbol']}",
                    data=self.data,
                    http_status=200,
                )
            ]
        )


def test_fmp_news_payload_is_mapped_to_pit_snapshot(session, store):
    fetched_at = datetime(2026, 7, 14, 13, 30, tzinfo=UTC)
    payload = {
        "symbol": "MU",
        "profile": {
            "symbol": "MU",
            "companyName": "Micron Technology, Inc.",
            "currency": "USD",
        },
        "news": [
            {
                "_news_type": "stock_news",
                "title": "Micron raises outlook",
                "url": "https://example.com/mu-outlook",
                "site": "Example Wire",
                "publishedDate": "2026-07-14 08:15:00",
                "text": "Micron updated its near-term demand commentary.",
                "sentiment": "positive",
                "sentimentScore": 0.73,
            }
        ],
    }

    service = IngestService(session, store)
    service.ingest(SinglePayloadCollector("news", payload), CollectionContext("live", ["MU"], fetched_at))
    service.ingest(SinglePayloadCollector("news", payload), CollectionContext("live", ["MU"], fetched_at + timedelta(days=1)))
    session.commit()

    assert len(session.scalars(select(NewsItemSnapshot)).all()) == 1
    row = session.scalar(select(NewsItemSnapshot))
    assert row.title == "Micron raises outlook"
    assert row.publisher == "Example Wire"
    assert row.sentiment_score == Decimal("0.730000")
    assert row.news_type == "stock_news"
    assert row.source_published_at is not None

    assert len(session.scalars(select(SourceDocumentSnapshot)).all()) == 1
    document = session.scalar(select(SourceDocumentSnapshot))
    assert document.document_type == "stock_news"
    assert document.source_url == "https://example.com/mu-outlook"
    assert document.object_uri
    assert gzip.decompress(store.get_bytes(document.object_uri)).decode("utf-8") == "Micron updated its near-term demand commentary."

    metric_codes = set(session.scalars(select(MetricDefinition.metric_code)).all())
    assert {"option_iv", "borrow_fee", "short_interest"}.issubset(metric_codes)


def test_fmp_financial_payload_is_mapped_to_generic_fact_snapshots(session, store):
    fetched_at = datetime(2026, 7, 14, 13, 30, tzinfo=UTC)
    payload = {
        "symbol": "MU",
        "profile": {
            "symbol": "MU",
            "companyName": "Micron Technology, Inc.",
            "currency": "USD",
        },
        "financials": {
            "income_statement": [
                {
                    "symbol": "MU",
                    "date": "2025-08-28",
                    "period": "annual",
                    "calendarYear": "2025",
                    "reportedCurrency": "USD",
                    "acceptedDate": "2025-10-03 17:22:11",
                    "revenue": 37194840113,
                    "netIncome": 8123000000,
                    "epsdiluted": 8.09,
                    "unusedVerbosePayload": {"nested": ["not", "stored", "in", "pit"]},
                }
            ],
            "ratios": [
                {
                    "symbol": "MU",
                    "date": "2026-05-28",
                    "period": "quarter",
                    "calendarYear": "2026",
                    "priceToEarningsRatio": 18.4,
                    "priceToEarningsGrowthRatio": 1.25,
                    "forwardPriceToEarningsGrowthRatio": 0.93,
                    "returnOnEquity": 0.21,
                }
            ],
            "financial_scores": [
                {
                    "symbol": "MU",
                    "altmanZScore": 4.2,
                    "piotroskiScore": 7,
                }
            ],
        },
    }

    service = IngestService(session, store)
    service.ingest(SinglePayloadCollector("financials", payload), CollectionContext("live", ["MU"], fetched_at))
    session.commit()

    rows = session.scalars(select(FinancialFactSnapshot).order_by(FinancialFactSnapshot.dataset_code)).all()
    assert {row.dataset_code for row in rows} == {"financial_scores", "income_statement", "ratios"}

    income = next(row for row in rows if row.dataset_code == "income_statement")
    assert income.period_type == "fiscal_year"
    assert income.fiscal_year == 2025
    assert str(income.fiscal_period_end) == "2025-08-28"
    assert income.value_json["revenue"] == 37194840113
    assert "unusedVerbosePayload" not in income.value_json

    ratios = next(row for row in rows if row.dataset_code == "ratios")
    assert ratios.period_type == "quarter"
    assert ratios.value_json["returnOnEquity"] == 0.21
    assert ratios.value_json["priceToEarningsRatio"] == 18.4
    assert ratios.value_json["priceToEarningsGrowthRatio"] == 1.25
    assert ratios.value_json["forwardPriceToEarningsGrowthRatio"] == 0.93

    scores = next(row for row in rows if row.dataset_code == "financial_scores")
    assert scores.period_type == "unknown"
    assert scores.quality_flags["fiscal_period_end_missing"] is True


def test_fmp_sec_filings_payload_is_mapped_to_pit_snapshot(session, store):
    fetched_at = datetime(2026, 7, 14, 13, 30, tzinfo=UTC)
    payload = {
        "symbol": "MU",
        "profile": {
            "symbol": "MU",
            "companyName": "Micron Technology, Inc.",
            "cik": "0000723125",
        },
        "sec_filings": [
            {
                "symbol": "MU",
                "cik": "0000723125",
                "formType": "8-K",
                "filingDate": "2026-06-26 00:00:00",
                "acceptedDate": "2026-06-26 16:02:11",
                "link": "https://www.sec.gov/Archives/edgar/data/723125/index.htm",
                "finalLink": "https://www.sec.gov/Archives/edgar/data/723125/mu-8k.htm",
                "hasFinancials": "False",
            }
        ],
    }

    service = IngestService(session, store)
    service.ingest(SinglePayloadCollector("sec_filings", payload), CollectionContext("live", ["MU"], fetched_at))
    service.ingest(SinglePayloadCollector("sec_filings", payload), CollectionContext("live", ["MU"], fetched_at + timedelta(days=1)))
    session.commit()

    assert len(session.scalars(select(SecFilingSnapshot)).all()) == 1
    row = session.scalar(select(SecFilingSnapshot))
    assert row.form_type == "8-K"
    assert row.cik == "0000723125"
    assert str(row.filing_date) == "2026-06-26"
    assert row.final_url.endswith("mu-8k.htm")
    assert row.has_financials is False

    assert len(session.scalars(select(SourceDocumentSnapshot)).all()) == 1
    document = session.scalar(select(SourceDocumentSnapshot))
    assert document.document_type == "sec_filing"
    assert document.source_url.endswith("mu-8k.htm")
    assert document.object_uri is None
    assert document.quality_flags["link_only"] is True


def test_fmp_transcript_payload_is_mapped_to_pit_snapshot(session, store):
    fetched_at = datetime(2026, 7, 14, 13, 30, tzinfo=UTC)
    payload = {
        "symbol": "MU",
        "profile": {
            "symbol": "MU",
            "companyName": "Micron Technology, Inc.",
        },
        "transcripts": [
            {
                "symbol": "MU",
                "year": "2025",
                "period": "Q4",
                "date": "2025-09-23",
                "content": "Operator: Welcome to Micron's fiscal fourth quarter call. Management: Demand remains strong.",
            }
        ],
    }

    service = IngestService(session, store)
    service.ingest(SinglePayloadCollector("transcripts", payload), CollectionContext("live", ["MU"], fetched_at))
    service.ingest(SinglePayloadCollector("transcripts", payload), CollectionContext("live", ["MU"], fetched_at + timedelta(days=1)))
    session.commit()

    assert len(session.scalars(select(EarningTranscriptSnapshot)).all()) == 1
    row = session.scalar(select(EarningTranscriptSnapshot))
    assert row.fiscal_year == 2025
    assert row.fiscal_period == "Q4"
    assert str(row.call_date) == "2025-09-23"
    assert "Demand remains strong" in row.transcript_text
    assert row.word_count == 12

    assert len(session.scalars(select(SourceDocumentSnapshot)).all()) == 1
    document = session.scalar(select(SourceDocumentSnapshot))
    assert document.document_type == "earning_transcript"
    assert document.object_uri
    assert "Demand remains strong" in gzip.decompress(store.get_bytes(document.object_uri)).decode("utf-8")
