from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "build_core_universe.py"
    spec = importlib.util.spec_from_file_location("build_core_universe", script_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_core_universe_filters_dirty_rows_and_ranks_by_quality():
    module = _load_module()
    rows = [
        _row("SMALL", market_cap="10", country="US"),
        _row("ADR", market_cap="9000", country="NL"),
        _row("ETF", market_cap="9000", is_etf="True"),
        _row("B", market_cap="2000", dollar_volume="500"),
        _row("A", market_cap="3000", dollar_volume="100"),
        _row("C", market_cap="2000", dollar_volume="900"),
    ]
    criteria = {
        "country": "US",
        "exchanges": ["NASDAQ", "NYSE", "AMEX"],
        "min_price": module.decimal_or_zero("1"),
        "min_market_cap": module.decimal_or_zero("20"),
        "min_volume": module.decimal_or_zero("3"),
        "min_dollar_volume": module.decimal_or_zero("20"),
        "size": 2,
    }

    eligible = [row for row in rows if not module.reject_reasons(row, criteria)]
    eligible.sort(key=module.quality_rank, reverse=True)

    assert [row["symbol"] for row in eligible[:2]] == ["A", "C"]
    rejected = {row["symbol"]: module.reject_reasons(row, criteria) for row in rows if module.reject_reasons(row, criteria)}
    assert "market_cap" in rejected["SMALL"]
    assert "non_us_company" in rejected["ADR"]
    assert "etf" in rejected["ETF"]


def test_write_symbols_contains_only_core_rows(tmp_path):
    module = _load_module()
    path = tmp_path / "core_symbols.txt"
    module.write_symbols(
        path,
        [_row("AAPL"), _row("MU")],
        {
            "size": 2,
            "country": "US",
            "exchanges": ["NASDAQ", "NYSE"],
            "min_market_cap": "20",
            "min_volume": "3",
            "min_dollar_volume": "20",
            "min_price": "1",
        },
    )

    symbols = [line.strip() for line in path.read_text().splitlines() if line.strip() and not line.startswith("#")]
    assert symbols == ["AAPL", "MU"]


def _row(
    symbol: str,
    market_cap: str = "1000",
    dollar_volume: str = "100",
    volume: str = "100",
    price: str = "10",
    country: str = "US",
    is_etf: str = "False",
    is_fund: str = "False",
    is_actively_trading: str = "True",
) -> dict[str, str]:
    return {
        "symbol": symbol,
        "company_name": f"{symbol} Inc.",
        "market_cap": market_cap,
        "price": price,
        "volume": volume,
        "dollar_volume": dollar_volume,
        "exchange": "NASDAQ",
        "exchange_short_name": "NASDAQ",
        "country": country,
        "sector": "",
        "industry": "",
        "is_etf": is_etf,
        "is_fund": is_fund,
        "is_actively_trading": is_actively_trading,
        "reason": "",
    }
