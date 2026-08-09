from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select

from pit_radar.collectors.base import CollectionContext
from pit_radar.collectors.mock import MockEarningsCollector
from pit_radar.db.models import DailyMarketBar, EstimateSnapshot, RawPayload, SecurityIdentifier
from pit_radar.services.asof import AsOfService
from pit_radar.services.dictionary import rows as dictionary_rows
from pit_radar.services.ingest import IngestService
from pit_radar.time import NY_TZ, ensure_utc

from tests.helpers import ScenarioDailyBarsCollector, ScenarioEstimatesCollector


def ingest(session, store, collector, fetched_at: datetime, mode: str = "live"):
    service = IngestService(session, store)
    run = service.ingest(
        collector,
        CollectionContext(collection_mode=mode, symbols=["MU"], fetched_at=fetched_at),
    )
    session.commit()
    return run


def test_identifier_as_of_respects_valid_ranges(session, store):
    t1 = datetime(2026, 7, 14, 13, 30, tzinfo=UTC)
    ingest(session, store, ScenarioEstimatesCollector(Decimal("10")), t1)
    service = AsOfService(session)
    security_id = service.resolve_security_id("MU", t1)
    identifier = service.get_identifier_as_of(security_id, t1)
    assert identifier.identifier_value == "MU"

    identifier.valid_to = t1 + timedelta(days=1)
    session.add(
        SecurityIdentifier(
            security_id=security_id,
            identifier_type="ticker",
            identifier_value="MUN",
            valid_from=t1 + timedelta(days=1),
        )
    )
    session.commit()

    assert service.get_identifier_as_of(security_id, t1).identifier_value == "MU"
    assert service.get_identifier_as_of(security_id, t1 + timedelta(days=2)).identifier_value == "MUN"


def test_raw_payload_keeps_fetch_observations_but_pit_dedupes_same_content(session, store):
    t1 = datetime(2026, 7, 14, 13, 30, tzinfo=UTC)
    t2 = datetime(2026, 7, 15, 13, 30, tzinfo=UTC)
    ingest(session, store, ScenarioEstimatesCollector(Decimal("10")), t1)
    ingest(session, store, ScenarioEstimatesCollector(Decimal("10")), t2)

    payload_count = session.scalar(select(func.count(RawPayload.payload_id)))
    estimate_count = session.scalar(select(func.count(EstimateSnapshot.estimate_id)))
    hashes = session.scalars(select(RawPayload.content_hash)).all()
    assert payload_count == 2
    assert estimate_count == 1
    assert len(set(hashes)) == 1


def test_same_fetched_at_duplicate_is_idempotent(session, store):
    t1 = datetime(2026, 7, 14, 13, 30, tzinfo=UTC)
    collector = ScenarioEstimatesCollector(Decimal("10"))
    ingest(session, store, collector, t1)
    ingest(session, store, collector, t1)
    assert session.scalar(select(func.count(EstimateSnapshot.estimate_id))) == 1


def test_future_function_guard_with_backfill(session, store):
    t1 = datetime(2026, 7, 14, 13, 30, tzinfo=UTC)
    t2 = datetime(2026, 7, 15, 13, 30, tzinfo=UTC)
    t3 = datetime(2026, 7, 16, 13, 30, tzinfo=UTC)
    ingest(session, store, ScenarioEstimatesCollector(Decimal("10"), request_suffix="t1"), t1, "live")
    ingest(session, store, ScenarioEstimatesCollector(Decimal("11"), request_suffix="t2"), t2, "live")
    ingest(session, store, ScenarioEstimatesCollector(Decimal("12"), request_suffix="backfill"), t3, "backfill")

    service = AsOfService(session)
    security_id = service.resolve_security_id("MU", t3)
    at_t1 = service.get_estimates_as_of([security_id], t1 + timedelta(seconds=1), strict_live=True)[0]
    at_t2 = service.get_estimates_as_of([security_id], t2 + timedelta(seconds=1), strict_live=True)[0]
    at_t3_strict = service.get_estimates_as_of([security_id], t3 + timedelta(seconds=1), strict_live=True)[0]
    at_t3_all = service.get_estimates_as_of([security_id], t3 + timedelta(seconds=1), strict_live=False)[0]

    assert at_t1.eps_mean == Decimal("10.000000")
    assert at_t2.eps_mean == Decimal("11.000000")
    assert at_t3_strict.eps_mean == Decimal("11.000000")
    assert at_t3_all.eps_mean == Decimal("12.000000")


def test_cutoff_does_not_show_future_live_update(session, store):
    t1 = datetime(2026, 7, 14, 13, 30, tzinfo=UTC)
    t2 = datetime(2026, 7, 15, 13, 30, tzinfo=UTC)
    ingest(session, store, ScenarioEstimatesCollector(Decimal("10"), request_suffix="t1"), t1)
    ingest(session, store, ScenarioEstimatesCollector(Decimal("11"), request_suffix="t2"), t2)

    service = AsOfService(session)
    security_id = service.resolve_security_id("MU", t2)
    visible = service.get_estimates_as_of([security_id], t2 - timedelta(seconds=1))[0]
    assert visible.eps_mean == Decimal("10.000000")


def test_analyst_snapshot_as_of(session, store):
    t1 = datetime(2026, 7, 14, 13, 30, tzinfo=UTC)
    ingest(session, store, ScenarioEstimatesCollector(Decimal("10")), t1)
    service = AsOfService(session)
    security_id = service.resolve_security_id("MU", t1)
    analyst = service.get_analyst_snapshot_as_of([security_id], t1 + timedelta(seconds=1))[0]
    assert analyst.target_mean == Decimal("120.000000")
    assert analyst.buy_count == 6


def test_earnings_calendar_as_of(session, store):
    t1 = datetime(2026, 7, 14, 13, 30, tzinfo=UTC)
    service = IngestService(session, store)
    service.ingest(
        MockEarningsCollector(),
        CollectionContext(collection_mode="live", symbols=["MU"], fetched_at=t1),
    )
    session.commit()
    asof = AsOfService(session)
    security_id = asof.resolve_security_id("MU", t1)
    earnings = asof.get_earnings_calendar_as_of([security_id], t1 + timedelta(seconds=1))[0]
    assert earnings.expected_report_session == "after_close"


def test_timezone_conversion_to_utc():
    ny_time = datetime(2026, 7, 14, 9, 30, tzinfo=NY_TZ)
    assert ensure_utc(ny_time) == datetime(2026, 7, 14, 13, 30, tzinfo=UTC)


def test_daily_bar_revision_versions(session, store):
    t1 = datetime(2026, 7, 14, 13, 30, tzinfo=UTC)
    t2 = datetime(2026, 7, 15, 13, 30, tzinfo=UTC)
    ingest(session, store, ScenarioDailyBarsCollector(Decimal("100"), request_suffix="v1"), t1)
    ingest(session, store, ScenarioDailyBarsCollector(Decimal("101"), request_suffix="v2"), t2)

    bars = session.scalars(select(DailyMarketBar).order_by(DailyMarketBar.revision_no)).all()
    assert [bar.revision_no for bar in bars] == [1, 2]

    service = AsOfService(session)
    security_id = service.resolve_security_id("MU", t2)
    asof = service.get_daily_market_bars_as_of([security_id], t2 + timedelta(seconds=1))[0]
    assert asof.close == Decimal("101.000000")


def test_daily_bar_same_content_is_idempotent_across_fetches(session, store):
    t1 = datetime(2026, 7, 14, 13, 30, tzinfo=UTC)
    t2 = datetime(2026, 7, 15, 13, 30, tzinfo=UTC)
    ingest(session, store, ScenarioDailyBarsCollector(Decimal("100"), request_suffix="v1"), t1)
    ingest(session, store, ScenarioDailyBarsCollector(Decimal("100"), request_suffix="v2"), t2)

    bars = session.scalars(select(DailyMarketBar)).all()
    assert len(bars) == 1
    assert bars[0].revision_no == 1


def test_chinese_dictionary_contains_required_fields():
    fields = {(row["table"], row["field"]): row for row in dictionary_rows()}
    assert ("pit.estimate_snapshot", "fetched_at") in fields
    assert fields[("pit.estimate_snapshot", "fetched_at")]["name_zh"]
    assert ("raw.payload", "object_uri") in fields
    macro_release_at = fields[("pit.macro_event_snapshot", "release_at_utc")]
    assert macro_release_at["name_zh"] == "公布时间UTC"
    assert "公布时间调整" in macro_release_at["description_zh"]
