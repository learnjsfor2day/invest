from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime
from typing import Any

from pit_radar.collectors.base import CollectionContext
from pit_radar.collectors.fmp import FmpDailyBarsCollector, FmpEarningsCollector, FmpMacroCalendarCollector, FmpNewsCollector


class FakeFmpClient:
    def get_json(self, path: str, params: dict[str, str]) -> tuple[Any, int]:
        if path == "/stable/profile":
            return [{"symbol": "MU", "companyName": "Micron Technology, Inc."}], 200
        if path == "/stable/news/stock":
            return [
                {"title": "same day", "url": "https://example.com/today", "publishedDate": "2026-07-14 08:00:00"},
                {"title": "old day", "url": "https://example.com/old", "publishedDate": "2026-07-13 08:00:00"},
            ], 200
        if path == "/stable/news/press-releases":
            return [{"title": "future day", "url": "https://example.com/future", "publishedDate": "2026-07-15 08:00:00"}], 200
        return [], 200


def test_fmp_news_collector_filters_to_requested_day():
    collector = FmpNewsCollector(client=FakeFmpClient(), limit=50)
    result = asyncio.run(
        collector.collect(
            CollectionContext(
                collection_mode="live",
                symbols=["MU"],
                fetched_at=datetime(2026, 7, 14, 13, 30, tzinfo=UTC),
                from_date=date(2026, 7, 14),
                to_date=date(2026, 7, 14),
            )
        )
    )

    assert not result.errors
    assert len(result.items) == 1
    assert [row["title"] for row in result.items[0].data["news"]] == ["same day"]


class FakeMacroFmpClient:
    def get_json(self, path: str, params: dict[str, str]) -> tuple[Any, int]:
        assert path == "/stable/economic-calendar"
        return [
            {"date": "2026-07-14 12:30:00", "event": "Core CPI MoM (Jun)", "country": "US", "currency": "USD"},
            {"date": "2026-07-14 06:00:00", "event": "GDP MoM", "country": "UK", "currency": "GBP"},
        ], 200


def test_fmp_macro_calendar_collector_filters_countries():
    collector = FmpMacroCalendarCollector(client=FakeMacroFmpClient(), countries=("US",))
    result = asyncio.run(
        collector.collect(
            CollectionContext(
                collection_mode="live",
                symbols=["US"],
                fetched_at=datetime(2026, 7, 14, 13, 30, tzinfo=UTC),
                from_date=date(2026, 7, 14),
                to_date=date(2026, 7, 14),
            )
        )
    )

    assert not result.errors
    assert len(result.items) == 1
    assert result.items[0].data["events"][0]["event"] == "Core CPI MoM (Jun)"
    assert result.items[0].metadata == {"total_rows": 2, "kept_rows": 1}


class FakeDailyBarsFmpClient:
    def __init__(self):
        self.paths: list[str] = []

    def get_json(self, path: str, params: dict[str, str]) -> tuple[Any, int]:
        self.paths.append(path)
        if path == "/stable/historical-price-eod/full":
            return [{"date": "2026-07-13", "close": 100, "volume": 1000000}], 200
        if path == "/stable/profile":
            return [{"symbol": "MU", "companyName": "Micron"}], 200
        return [], 200


def test_fmp_daily_bars_can_skip_profile_request():
    client = FakeDailyBarsFmpClient()
    collector = FmpDailyBarsCollector(client=client, include_profile=False)
    result = asyncio.run(
        collector.collect(
            CollectionContext(
                collection_mode="live",
                symbols=["MU"],
                fetched_at=datetime(2026, 7, 14, 13, 30, tzinfo=UTC),
                from_date=date(2026, 7, 13),
                to_date=date(2026, 7, 13),
            )
        )
    )

    assert not result.errors
    assert client.paths == ["/stable/historical-price-eod/full"]
    assert result.items[0].data["profile"] == {}


class FakeEarningsFmpClient:
    def __init__(self):
        self.paths: list[str] = []

    def get_json(self, path: str, params: dict[str, str]) -> tuple[Any, int]:
        self.paths.append(path)
        if path == "/stable/earnings":
            return [{"symbol": "MU", "date": "2026-09-22", "epsEstimated": 1.23}], 200
        if path == "/stable/profile":
            return [{"symbol": "MU", "companyName": "Micron"}], 200
        return [], 200


def test_fmp_earnings_can_skip_profile_request():
    client = FakeEarningsFmpClient()
    collector = FmpEarningsCollector(client=client, include_profile=False)
    result = asyncio.run(
        collector.collect(
            CollectionContext(
                collection_mode="live",
                symbols=["MU"],
                fetched_at=datetime(2026, 7, 14, 13, 30, tzinfo=UTC),
            )
        )
    )

    assert not result.errors
    assert client.paths == ["/stable/earnings"]
    assert result.items[0].data["profile"] == {}


def test_fmp_daily_bars_parallel_preserves_symbol_order():
    client = FakeDailyBarsFmpClient()
    collector = FmpDailyBarsCollector(client=client, include_profile=False, max_workers=2)
    result = asyncio.run(
        collector.collect(
            CollectionContext(
                collection_mode="live",
                symbols=["MU", "AAPL", "NVDA"],
                fetched_at=datetime(2026, 7, 14, 13, 30, tzinfo=UTC),
                from_date=date(2026, 7, 13),
                to_date=date(2026, 7, 13),
            )
        )
    )

    assert not result.errors
    assert [item.data["symbol"] for item in result.items] == ["MU", "AAPL", "NVDA"]
    assert client.paths == ["/stable/historical-price-eod/full"] * 3
