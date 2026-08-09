from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select

from pit_radar.collectors.base import CollectionContext, CollectionResult, RawCollectionItem
from pit_radar.db.models import MacroEventSnapshot
from pit_radar.services.ingest import IngestService


@dataclass
class MacroPayloadCollector:
    data: dict[str, Any]
    dataset_code: str = "macro_events"
    source_code: str = "fmp"

    async def collect(self, context: CollectionContext) -> CollectionResult:
        return CollectionResult(
            items=[
                RawCollectionItem(
                    request_key="fmp-test:macro-events",
                    data=self.data,
                    http_status=200,
                )
            ]
        )


def test_macro_events_are_deduped_by_event_key_and_payload_hash(session, store):
    fetched_at = datetime(2026, 7, 14, 13, 30, tzinfo=UTC)
    row = {
        "date": "2026-07-14 12:30:00",
        "event": "Core CPI MoM (Jun)",
        "country": "US",
        "currency": "USD",
        "impact": "High",
        "actual": "0.3%",
        "estimate": "0.3%",
        "previous": "0.2%",
        "unit": "%",
    }
    payload = {"events": [row]}
    service = IngestService(session, store)
    context = CollectionContext("live", ["US"], fetched_at)
    service.ingest(MacroPayloadCollector(payload), context)
    service.ingest(MacroPayloadCollector(payload), CollectionContext("live", ["US"], fetched_at + timedelta(minutes=10)))
    session.commit()

    rows = session.scalars(select(MacroEventSnapshot)).all()
    assert len(rows) == 1
    event = rows[0]
    assert event.source == "fmp"
    assert event.event_name == "Core CPI MoM (Jun)"
    assert event.country == "US"
    assert event.currency == "USD"
    assert event.release_at_utc.replace(tzinfo=UTC) == datetime(2026, 7, 14, 12, 30, tzinfo=UTC)
    assert event.actual_raw == "0.3%"
    assert event.actual_value == Decimal("0.30000000")
    assert event.estimate_value == Decimal("0.30000000")
    assert event.previous_value == Decimal("0.20000000")
    assert event.unit == "%"
    assert event.is_backfill is False
    assert event.raw_json["impact"] == "High"


def test_macro_event_changed_payload_inserts_new_snapshot(session, store):
    fetched_at = datetime(2026, 7, 14, 13, 30, tzinfo=UTC)
    base_row = {
        "date": "2026-07-14 12:30:00",
        "event": "Initial Jobless Claims",
        "country": "US",
        "currency": "USD",
        "impact": "High",
        "actual": "235K",
        "estimate": "240K",
        "previous": "245K",
        "unit": "K",
    }
    changed_row = dict(base_row, actual="238K")
    service = IngestService(session, store)
    service.ingest(MacroPayloadCollector({"events": [base_row]}), CollectionContext("live", ["US"], fetched_at))
    service.ingest(MacroPayloadCollector({"events": [changed_row]}), CollectionContext("live", ["US"], fetched_at + timedelta(minutes=30)))
    session.commit()

    rows = session.scalars(select(MacroEventSnapshot).order_by(MacroEventSnapshot.observed_at_utc)).all()
    assert len(rows) == 2
    assert rows[0].event_key == rows[1].event_key
    assert rows[0].payload_hash != rows[1].payload_hash
    assert rows[0].actual_value == Decimal("235000.00000000")
    assert rows[1].actual_value == Decimal("238000.00000000")


def test_macro_event_backfill_flag(session, store):
    fetched_at = datetime(2026, 7, 14, 13, 30, tzinfo=UTC)
    payload = {
        "events": [
            {
                "date": "2026-06-12 12:30:00",
                "event": "PPI YoY (May)",
                "country": "US",
                "currency": "USD",
                "impact": "Medium",
                "actual": "2.6%",
            }
        ]
    }
    service = IngestService(session, store)
    service.ingest(MacroPayloadCollector(payload), CollectionContext("backfill", ["US"], fetched_at))
    session.commit()

    event = session.scalar(select(MacroEventSnapshot))
    assert event.is_backfill is True
