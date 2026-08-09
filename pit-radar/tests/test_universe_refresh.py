from __future__ import annotations

import importlib.util
import sys
from decimal import Decimal
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "refresh_fmp_universe.py"
    spec = importlib.util.spec_from_file_location("refresh_fmp_universe", script_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _criteria(module):
    return module.UniverseCriteria(
        country="",
        exchanges=("NASDAQ", "NYSE", "AMEX"),
        min_market_cap=Decimal("20000000"),
        min_volume=Decimal("3000"),
        min_dollar_volume=Decimal("20000"),
        min_price=Decimal("1"),
        max_symbols=0,
    )


def test_universe_filter_accepts_liquid_common_stock_and_class_share():
    module = _load_module()
    criteria = _criteria(module)
    rows = [
        {
            "symbol": "AAPL",
            "companyName": "Apple Inc.",
            "marketCap": 4_000_000_000_000,
            "price": 200,
            "volume": 10_000_000,
            "exchangeShortName": "NASDAQ",
            "country": "US",
            "isEtf": False,
            "isFund": False,
            "isActivelyTrading": True,
        },
        {
            "symbol": "SPCX",
            "companyName": "Space Exploration Technologies Corp.",
            "marketCap": 1_800_000_000_000,
            "price": 140,
            "volume": 10_000_000,
            "exchangeShortName": "NASDAQ",
            "country": "US",
            "isEtf": False,
            "isFund": False,
            "isActivelyTrading": True,
        },
        {
            "symbol": "BRK-B",
            "companyName": "Berkshire Hathaway Inc.",
            "marketCap": 900_000_000_000,
            "price": 400,
            "volume": 1_000_000,
            "exchangeShortName": "NYSE",
            "country": "US",
            "isEtf": False,
            "isFund": False,
            "isActivelyTrading": True,
        },
    ]

    accepted, rejected = module.build_universe(rows, criteria)

    assert [row.symbol for row in accepted] == ["AAPL", "SPCX", "BRK-B"]
    assert rejected == []


def test_universe_filter_rejects_etfs_derivatives_and_illiquid_rows():
    module = _load_module()
    criteria = _criteria(module)
    rows = [
        {
            "symbol": "SPY",
            "companyName": "SPDR S&P 500 ETF Trust",
            "marketCap": 500_000_000_000,
            "price": 500,
            "volume": 50_000_000,
            "exchangeShortName": "AMEX",
            "country": "US",
            "isEtf": True,
            "isFund": True,
            "isActivelyTrading": True,
        },
        {
            "symbol": "XYZW",
            "companyName": "XYZ Acquisition Corp. Warrant",
            "marketCap": 2_000_000_000,
            "price": 5,
            "volume": 1_000_000,
            "exchangeShortName": "NASDAQ",
            "country": "US",
            "isEtf": False,
            "isFund": False,
            "isActivelyTrading": True,
        },
        {
            "symbol": "SMOL",
            "companyName": "Small Company Inc.",
            "marketCap": 10_000_000,
            "price": 10,
            "volume": 1_000,
            "exchangeShortName": "NASDAQ",
            "country": "US",
            "isEtf": False,
            "isFund": False,
            "isActivelyTrading": True,
        },
    ]

    accepted, rejected = module.build_universe(rows, criteria)

    assert accepted == []
    reasons = {row.symbol: row.reason for row in rejected}
    assert "etf" in reasons["SPY"]
    assert "derivative_or_fund_name" in reasons["XYZW"]
    assert "market_cap" in reasons["SMOL"]
    assert "volume" in reasons["SMOL"]


class FakePriceClient:
    def get_json(self, path: str, params: dict[str, str]):
        assert path == "/stable/historical-price-eod/full"
        if params["symbol"] == "AAPL":
            return [{"date": "2026-07-13", "close": 100, "volume": 1000000}], 200
        return [], 200


def test_price_validation_removes_symbols_without_daily_bar():
    module = _load_module()
    rows = [
        module.UniverseRow("AAPL", "Apple Inc.", Decimal("1"), Decimal("1"), Decimal("1"), Decimal("1"), "NASDAQ", "NASDAQ", "US", "", "", False, False, True),
        module.UniverseRow("SPCX", "Space Exploration Technologies Corp.", Decimal("1"), Decimal("1"), Decimal("1"), Decimal("1"), "NASDAQ", "NASDAQ", "US", "", "", False, False, True),
    ]

    accepted, rejected = module.validate_price_bars(rows, "2026-07-13", client=FakePriceClient())

    assert [row.symbol for row in accepted] == ["AAPL"]
    assert rejected[0].symbol == "SPCX"
    assert rejected[0].reason == "no_price_bar:2026-07-13"


class FakeBatchQuoteClient:
    def get_json(self, path: str, params: dict[str, str]):
        assert path == "/stable/batch-quote"
        assert params["symbols"] == "AAPL,NOPE"
        return [{"symbol": "AAPL", "price": 100, "volume": 1000000}], 200


def test_batch_quote_validation_removes_unquoted_symbols():
    module = _load_module()
    rows = [
        module.UniverseRow("AAPL", "Apple Inc.", Decimal("1"), Decimal("1"), Decimal("1"), Decimal("1"), "NASDAQ", "NASDAQ", "US", "", "", False, False, True),
        module.UniverseRow("NOPE", "No Quote Inc.", Decimal("1"), Decimal("1"), Decimal("1"), Decimal("1"), "NASDAQ", "NASDAQ", "US", "", "", False, False, True),
    ]

    accepted, rejected = module.validate_batch_quotes(rows, client=FakeBatchQuoteClient(), chunk_size=2)

    assert [row.symbol for row in accepted] == ["AAPL"]
    assert rejected[0].symbol == "NOPE"
    assert rejected[0].reason == "no_batch_quote"


def test_screener_params_filter_by_exchange_without_company_country_by_default():
    module = _load_module()
    criteria = _criteria(module)

    params = module.screener_params(100, criteria, exchange="NYSE")

    assert params["exchange"] == "NYSE"
    assert "country" not in params


def test_company_country_filter_is_optional():
    module = _load_module()
    criteria = _criteria(module)
    rows = [
        {
            "symbol": "ADR",
            "companyName": "ADR Company",
            "marketCap": 100_000_000,
            "price": 10,
            "volume": 20_000,
            "exchangeShortName": "NYSE",
            "country": "IE",
            "isEtf": False,
            "isFund": False,
            "isActivelyTrading": True,
        },
    ]

    accepted, rejected = module.build_universe(rows, criteria)

    assert [row.symbol for row in accepted] == ["ADR"]
    assert rejected == []
