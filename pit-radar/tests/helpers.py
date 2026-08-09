from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from pit_radar.collectors.base import CollectionContext, CollectionResult, RawCollectionItem


@dataclass
class ScenarioEstimatesCollector:
    eps: Decimal
    symbol: str = "MU"
    source_code: str = "mock"
    dataset_code: str = "estimates"
    request_suffix: str = "default"

    async def collect(self, context: CollectionContext) -> CollectionResult:
        fiscal_end = date(2026, 12, 31)
        return CollectionResult(
            items=[
                RawCollectionItem(
                    request_key=f"scenario-estimates:{self.symbol}:{self.request_suffix}",
                    data={
                        "symbol": self.symbol,
                        "profile": {
                            "symbol": self.symbol,
                            "companyName": "Micron Technology Mock",
                            "exchangeShortName": "NASDAQ",
                            "cik": "0000723125",
                            "sector": "Technology",
                            "industry": "Memory",
                            "currency": "USD",
                        },
                        "estimates": [
                            {
                                "date": str(fiscal_end),
                                "period": "annual",
                                "estimatedEpsAvg": str(self.eps),
                                "estimatedEpsHigh": str(self.eps + Decimal("1")),
                                "estimatedEpsLow": str(self.eps - Decimal("1")),
                                "numberAnalystEstimatedEps": 10,
                                "estimatedRevenueAvg": "100000000",
                                "estimatedRevenueHigh": "110000000",
                                "estimatedRevenueLow": "90000000",
                                "numberAnalystsEstimatedRevenue": 8,
                            }
                        ],
                        "price_target": {
                            "targetConsensus": "120",
                            "targetHigh": "150",
                            "targetLow": "90",
                        },
                        "grades_consensus": {
                            "strongBuy": 3,
                            "buy": 6,
                            "hold": 4,
                            "sell": 1,
                            "strongSell": 0,
                        },
                    },
                )
            ]
        )


@dataclass
class ScenarioDailyBarsCollector:
    close: Decimal
    symbol: str = "MU"
    source_code: str = "mock"
    dataset_code: str = "daily_bars"
    request_suffix: str = "default"

    async def collect(self, context: CollectionContext) -> CollectionResult:
        return CollectionResult(
            items=[
                RawCollectionItem(
                    request_key=f"scenario-daily-bars:{self.symbol}:{self.request_suffix}",
                    data={
                        "symbol": self.symbol,
                        "profile": {
                            "symbol": self.symbol,
                            "companyName": "Micron Technology Mock",
                            "exchangeShortName": "NASDAQ",
                        },
                        "historical": [
                            {
                                "date": "2026-07-13",
                                "open": "90",
                                "high": "110",
                                "low": "80",
                                "close": str(self.close),
                                "adjClose": str(self.close),
                                "volume": "1000000",
                            }
                        ],
                    },
                )
            ]
        )
