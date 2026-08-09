from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from pit_radar.collectors.base import CollectionContext, CollectionResult, RawCollectionItem


class MockEstimatesCollector:
    dataset_code = "estimates"
    source_code = "mock"

    async def collect(self, context: CollectionContext) -> CollectionResult:
        items: list[RawCollectionItem] = []
        for idx, symbol in enumerate(context.symbols):
            fiscal_year = context.fetched_at.year
            eps = Decimal("10.00") + Decimal(idx)
            revenue = Decimal("1000000000") + Decimal(idx * 1000000)
            payload = {
                "symbol": symbol,
                "profile": {
                    "symbol": symbol,
                    "companyName": f"{symbol} Mock Inc.",
                    "exchangeShortName": "NASDAQ",
                    "cik": f"000000{idx + 1:04d}",
                    "sector": "Technology",
                    "industry": "Software",
                    "currency": "USD",
                },
                "estimates": [
                    {
                        "date": f"{fiscal_year}-12-31",
                        "period": "annual",
                        "estimatedEpsAvg": str(eps),
                        "estimatedEpsHigh": str(eps + Decimal("1.00")),
                        "estimatedEpsLow": str(eps - Decimal("1.00")),
                        "numberAnalystEstimatedEps": 12 + idx,
                        "estimatedRevenueAvg": str(revenue),
                        "estimatedRevenueHigh": str(revenue + Decimal("100000000")),
                        "estimatedRevenueLow": str(revenue - Decimal("100000000")),
                        "numberAnalystsEstimatedRevenue": 10 + idx,
                    }
                ],
                "price_target": {
                    "targetConsensus": str(Decimal("120") + idx),
                    "targetHigh": str(Decimal("150") + idx),
                    "targetLow": str(Decimal("90") + idx),
                },
                "grades_consensus": {
                    "strongBuy": 3 + idx,
                    "buy": 6,
                    "hold": 4,
                    "sell": 1,
                    "strongSell": 0,
                },
            }
            items.append(RawCollectionItem(request_key=f"mock-estimates:{symbol}", data=payload))
        return CollectionResult(items=items)


class MockDailyBarsCollector:
    dataset_code = "daily_bars"
    source_code = "mock"

    async def collect(self, context: CollectionContext) -> CollectionResult:
        trade_day = context.to_date or context.fetched_at.date()
        items: list[RawCollectionItem] = []
        for idx, symbol in enumerate(context.symbols):
            base = Decimal("100") + Decimal(idx * 10)
            payload = {
                "symbol": symbol,
                "profile": {"symbol": symbol, "companyName": f"{symbol} Mock Inc.", "exchangeShortName": "NASDAQ"},
                "historical": [
                    {
                        "date": str(trade_day - timedelta(days=1)),
                        "open": str(base),
                        "high": str(base + 5),
                        "low": str(base - 3),
                        "close": str(base + 1),
                        "adjClose": str(base + 1),
                        "volume": 1000000 + idx,
                    }
                ],
            }
            items.append(RawCollectionItem(request_key=f"mock-daily-bars:{symbol}:{trade_day}", data=payload))
        return CollectionResult(items=items)


class MockEarningsCollector:
    dataset_code = "earnings"
    source_code = "mock"

    async def collect(self, context: CollectionContext) -> CollectionResult:
        items: list[RawCollectionItem] = []
        for idx, symbol in enumerate(context.symbols):
            period_end = date(context.fetched_at.year, 6, 30)
            payload = {
                "symbol": symbol,
                "profile": {"symbol": symbol, "companyName": f"{symbol} Mock Inc.", "exchangeShortName": "NASDAQ"},
                "earnings": [
                    {
                        "fiscalDateEnding": str(period_end),
                        "date": str(period_end + timedelta(days=25 + idx)),
                        "time": "amc",
                        "epsEstimated": str(Decimal("2.50") + idx),
                        "revenueEstimated": str(Decimal("100000000") + idx),
                    }
                ],
            }
            items.append(RawCollectionItem(request_key=f"mock-earnings:{symbol}", data=payload))
        return CollectionResult(items=items)
