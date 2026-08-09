from __future__ import annotations

import math
from pathlib import Path

import pandas as pd

from finance_engine import (
    enrich_financial_data,
    enterprise_value_from_share_price,
    implied_growth_scenarios,
    normalize_financial_data,
    required_future_value,
    target_ev_from_equity_return,
)

APP_DIR = Path(__file__).resolve().parents[1]


def test_palantir_example_matches_requested_scenario() -> None:
    target_ev = required_future_value(308.0, 0.10, 4.44)
    scenarios = implied_growth_scenarios(
        target_enterprise_value=target_ev,
        terminal_fcf_margin=0.45,
        base_revenue=7.656,
        growth_years=4.0,
        terminal_multiples=[20, 25, 30],
    )

    assert math.isclose(target_ev, 470.34, rel_tol=0.001)
    assert scenarios["required_fcf"].round(1).tolist() == [23.5, 18.8, 15.7]
    assert scenarios["required_revenue"].round(1).tolist() == [52.3, 41.8, 34.8]
    assert scenarios["implied_revenue_cagr"].round(2).tolist() == [0.62, 0.53, 0.46]


def test_normalize_fills_fcf_from_ocf_less_capex() -> None:
    raw = pd.DataFrame(
        [
            {
                "公司": "测试公司",
                "财年": 2025,
                "营业收入": 100,
                "经营现金流": 30,
                "资本开支": 5,
            }
        ]
    )
    normalized, report = normalize_financial_data(raw)

    assert report.ok
    assert report.filled_fcf_rows == 1
    assert normalized.loc[0, "free_cash_flow"] == 25


def test_enrich_calculates_growth_margins_and_incremental_margin() -> None:
    raw = pd.DataFrame(
        [
            {
                "company": "A",
                "fiscal_year": 2024,
                "revenue": 100,
                "operating_income": 10,
                "free_cash_flow": 15,
            },
            {
                "company": "A",
                "fiscal_year": 2025,
                "revenue": 120,
                "operating_income": 16,
                "free_cash_flow": 21,
            },
        ]
    )
    normalized, _ = normalize_financial_data(raw)
    enriched = enrich_financial_data(normalized)

    assert math.isclose(enriched.loc[1, "revenue_growth"], 0.20)
    assert math.isclose(enriched.loc[1, "operating_margin"], 16 / 120)
    assert math.isclose(enriched.loc[1, "incremental_operating_margin"], 0.30)
    assert math.isclose(enriched.loc[1, "incremental_fcf_margin"], 0.30)


def test_share_price_enterprise_value_bridge() -> None:
    equity, ev = enterprise_value_from_share_price(
        share_price=100, diluted_shares_m=2_500, cash_m=5_000, debt_m=1_000
    )
    target_equity, target_ev = target_ev_from_equity_return(
        current_equity_value_b=equity,
        required_return=0.10,
        holding_years=4,
        terminal_net_debt_b=-4,
    )

    assert equity == 250
    assert ev == 246
    assert math.isclose(target_equity, 366.025)
    assert math.isclose(target_ev, 362.025)


def test_default_template_is_pltr_actuals_plus_2026_guidance() -> None:
    raw = pd.read_csv(APP_DIR / "templates" / "financial_data_template.csv")
    normalized, report = normalize_financial_data(raw)

    assert report.ok
    assert normalized["ticker"].unique().tolist() == ["PLTR"]
    assert normalized["fiscal_year"].tolist() == [2022, 2023, 2024, 2025, 2026]
    assert normalized.loc[normalized["fiscal_year"] == 2025, "revenue"].item() == 4475.446
    assert normalized.loc[normalized["fiscal_year"] == 2025, "free_cash_flow"].item() == 2100.591
    assert normalized.loc[normalized["fiscal_year"] == 2026, "revenue"].item() == 7656
    assert normalized.loc[normalized["fiscal_year"] == 2026, "is_estimate"].item()
    assert pd.isna(
        normalized.loc[normalized["fiscal_year"] == 2026, "free_cash_flow"].item()
    )
